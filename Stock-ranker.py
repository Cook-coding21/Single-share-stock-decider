"""
Yahoo Finance Stock Researcher

This script uses Yahoo Finance only. It is a research tool, not a buy or sell
recommendation.
"""

import json
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf


FUND_TYPES = {"ETF", "MUTUALFUND", "INDEX"}
SECTOR_SPECIFIC_SCORE_SECTORS = {"FINANCIAL SERVICES", "REAL ESTATE"}

# The two stock universes are fetched fresh on every screen run. The financial
# score is based on annual statements, which normally change only when a company
# reports results, so it is reused briefly to avoid excessive Yahoo requests.
# Live price, day change, volume, and market-cap details are never read from this
# cache: they come from the fresh screen response each time.
SCREEN_CACHE_FILE = Path(__file__).with_name("stock_screener_cache.json")
SCREEN_CACHE_MAX_AGE = timedelta(hours=6)
SCREEN_REQUEST_DELAY_SECONDS = 0.25
DEFAULT_SCREEN_RESULTS = 15
MAX_SCREEN_RESULTS = 50
DEFAULT_ACTIVE_STOCKS = 100
DEFAULT_EMERGING_STOCKS = 100
MAX_SCREEN_UNIVERSE = 250

# "Emerging" here means smaller, US-listed operating companies; it does not
# mean companies based in emerging-market countries. These limits are deliberately
# set above penny-stock territory and require reasonable liquidity. The financial
# model below is still the actual quality filter.
EMERGING_MIN_MARKET_CAP = 50_000_000
EMERGING_MAX_MARKET_CAP = 2_000_000_000
EMERGING_MIN_PRICE = 2.00
EMERGING_MIN_DAY_VOLUME = 200_000
EMERGING_MIN_AVERAGE_VOLUME = 250_000


# These weights are for a first-pass financial-quality screen, not a prediction
# of investment returns. They deliberately select distinct checks across the
# three frameworks so that the same idea is not counted repeatedly.
#
# The largest weights are given to sustainable profitability, meaningful sales
# growth, and cash generation. Balance-sheet strength remains important, but a
# company with debt is not automatically a poor investment, so the conservative
# "cash covers debt" test is medium priority. Current ratio and ROE can differ
# widely by industry (and ROE can be distorted by leverage or share buy-backs),
# so they are supporting checks rather than deciding ones.
WEIGHTED_SCORE_ITEMS = [
    {
        "framework": "Mark Tilbury",
        "check_name": "Operating margin",
        "weight": 15,
        "priority": "HIGH",
        "why": "Profitability from the core business",
    },
    {
        "framework": "Plain Bagel",
        "check_name": "Revenue CAGR (available history)",
        "weight": 15,
        "priority": "HIGH",
        "why": "Meaningful longer-term sales growth",
    },
    {
        "framework": "Mark Tilbury",
        "check_name": "Current ratio",
        "weight": 5,
        "priority": "LOWER",
        "why": "Short-term liquidity; varies substantially by industry",
    },
    {
        "framework": "Drew Cohen",
        "check_name": "Cash versus total debt",
        "weight": 15,
        "priority": "MEDIUM",
        "why": "Conservative balance-sheet strength and debt protection",
    },
    {
        "framework": "Mark Tilbury",
        "check_name": "Free cash flow trend",
        "weight": 15,
        "priority": "HIGH",
        "why": "Positive and improving cash generation",
    },
    {
        "framework": "Plain Bagel",
        "check_name": "Capital-expenditure coverage",
        "weight": 10,
        "priority": "HIGH",
        "why": "Whether operating cash flow funds investment spending",
    },
    {
        "framework": "Plain Bagel",
        "check_name": "Return on equity history",
        "weight": 5,
        "priority": "LOWER",
        "why": "Supporting profitability measure; can be distorted by leverage",
    },
    {
        "framework": "Plain Bagel",
        "check_name": "Operating income CAGR (available history)",
        "weight": 10,
        "priority": "MEDIUM",
        "why": "Longer-term core-profit growth",
    },
    {
        "framework": "Plain Bagel",
        "check_name": "Operating-cost share trend",
        "weight": 5,
        "priority": "LOWER",
        "why": "Cost discipline as the business grows",
    },
    {
        "framework": "Drew Cohen",
        "check_name": "Stock-based compensation trend",
        "weight": 5,
        "priority": "LOWER",
        "why": "Potential shareholder dilution",
    },
]


def is_number(value):
    """Return True only for usable numeric values."""
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def number(value):
    """Return a float when possible, otherwise None."""
    return float(value) if is_number(value) else None


def money(value, currency="$"):
    """Format a number as money, or show Not available."""
    if not is_number(value):
        return "Not available"

    prefix = "$" if currency == "$" else f"{currency} "
    return f"{prefix}{float(value):,.2f}"


def percentage(value):
    """Format a decimal as a percentage, or show Not available."""
    if not is_number(value):
        return "Not available"
    return f"{float(value) * 100:.2f}%"


def number_text(value):
    """Format a plain number, or show Not available."""
    if not is_number(value):
        return "Not available"
    return f"{float(value):.2f}"


def short_description(value, maximum_length=500):
    """Return a clean, readable version of Yahoo Finance's business summary."""
    if not value or value == "Not available":
        return "Not available"

    cleaned = " ".join(str(value).split())

    if len(cleaned) <= maximum_length:
        return cleaned

    shortened = cleaned[:maximum_length].rsplit(" ", 1)[0]
    return f"{shortened}..."


def safe_info(stock):
    """Get Yahoo Finance company information without stopping on an error."""
    try:
        return stock.info
    except Exception:
        return {}


def safe_statement(stock, attribute_names):
    """Return the first available annual Yahoo Finance financial statement."""
    for attribute_name in attribute_names:
        try:
            statement = getattr(stock, attribute_name)
            if statement is not None and not statement.empty:
                return statement
        except Exception:
            continue

    return None


def statement_values(statement, row_names):
    """Return usable annual values for the first matching Yahoo statement row."""
    if statement is None or statement.empty:
        return []

    for row_name in row_names:
        if row_name not in statement.index:
            continue

        values = []
        row = statement.loc[row_name]

        for period in statement.columns:
            value = number(row[period])
            if value is not None:
                values.append((period, value))

        try:
            return sorted(values, key=lambda item: item[0], reverse=True)
        except TypeError:
            return values

    return []


def latest_statement_value(statement, row_names):
    """Return the latest annual value for one or more possible row names."""
    values = statement_values(statement, row_names)
    return values[0][1] if values else None


def period_text(period):
    """Format a financial-statement period for the report."""
    return period.strftime("%Y-%m-%d") if hasattr(period, "strftime") else str(period)


def free_cash_flow_values(cash_flow):
    """Get annual free cash flow, deriving it when Yahoo does not provide it."""
    direct_values = statement_values(cash_flow, ["Free Cash Flow"])
    if direct_values:
        return direct_values

    operating_values = dict(
        statement_values(
            cash_flow,
            [
                "Operating Cash Flow",
                "Total Cash From Operating Activities",
                "Cash Flow From Continuing Operating Activities",
            ],
        )
    )
    capital_expenditure_values = dict(
        statement_values(cash_flow, ["Capital Expenditure", "Capital Expenditures"])
    )

    values = []
    for period, operating_cash_flow in operating_values.items():
        capital_expenditure = capital_expenditure_values.get(period)

        if capital_expenditure is None:
            continue

        free_cash_flow = (
            operating_cash_flow + capital_expenditure
            if capital_expenditure < 0
            else operating_cash_flow - capital_expenditure
        )
        values.append((period, free_cash_flow))

    try:
        return sorted(values, key=lambda item: item[0], reverse=True)
    except TypeError:
        return values


def calculate_tilbury_checks(balance_sheet, income_statement, cash_flow, currency):
    """Calculate Mark Tilbury-style quantitative checks from annual Yahoo data."""
    current_assets = latest_statement_value(
        balance_sheet,
        ["Current Assets", "Total Current Assets"],
    )
    current_liabilities = latest_statement_value(
        balance_sheet,
        ["Current Liabilities", "Total Current Liabilities"],
    )

    if current_assets is None or current_liabilities in {None, 0}:
        current_ratio_result = None
        current_ratio_value = "Not available"
        current_ratio_reason = (
            "Yahoo Finance did not provide both current assets and current "
            "liabilities in the latest annual balance sheet."
        )
    else:
        current_ratio = current_assets / current_liabilities
        current_ratio_result = bool(current_ratio > 1)
        current_ratio_value = (
            f"{current_ratio:.2f} "
            f"({money(current_assets, currency)} current assets / "
            f"{money(current_liabilities, currency)} current liabilities)"
        )
        current_ratio_reason = (
            "Pass: current assets are greater than current liabilities."
            if current_ratio_result
            else "Needs review: current liabilities are greater than current assets."
        )

    operating_income = latest_statement_value(income_statement, ["Operating Income"])
    total_revenue = latest_statement_value(income_statement, ["Total Revenue"])

    if operating_income is None or total_revenue in {None, 0}:
        operating_margin_result = None
        operating_margin_value = "Not available"
        operating_margin_reason = (
            "Yahoo Finance did not provide both operating income and total "
            "revenue in the latest annual income statement."
        )
    else:
        operating_margin = operating_income / total_revenue
        operating_margin_result = bool(operating_margin > 0.15)
        operating_margin_value = (
            f"{percentage(operating_margin)} "
            f"({money(operating_income, currency)} operating income / "
            f"{money(total_revenue, currency)} revenue)"
        )
        operating_margin_reason = (
            "Pass: operating margin is above 15.00%."
            if operating_margin_result
            else "Needs review: operating margin is not above 15.00%."
        )

    free_cash_flow = free_cash_flow_values(cash_flow)

    if len(free_cash_flow) < 2:
        cash_flow_result = None
        cash_flow_value = "Not available"
        cash_flow_reason = (
            "Yahoo Finance did not provide two annual free-cash-flow figures "
            "to compare."
        )
    else:
        latest_period, latest_free_cash_flow = free_cash_flow[0]
        previous_period, previous_free_cash_flow = free_cash_flow[1]
        # A smaller loss is an improvement, but it is not yet positive cash
        # generation. Requiring both avoids awarding a high-weight pass to a
        # company that is still burning cash.
        cash_flow_result = bool(
            latest_free_cash_flow > 0
            and latest_free_cash_flow > previous_free_cash_flow
        )
        cash_flow_value = (
            f"Latest: {money(latest_free_cash_flow, currency)} "
            f"({period_text(latest_period)}) | Previous: "
            f"{money(previous_free_cash_flow, currency)} "
            f"({period_text(previous_period)})"
        )
        if cash_flow_result:
            cash_flow_reason = (
                "Pass: latest annual free cash flow is positive and higher "
                "than the previous year."
            )
        elif latest_free_cash_flow <= 0:
            cash_flow_reason = (
                "Needs review: latest annual free cash flow is not positive, "
                "even if it improved from the previous year."
            )
        else:
            cash_flow_reason = (
                "Needs review: latest annual free cash flow is positive but "
                "did not increase from the previous year."
            )

    return [
        {
            "section": "BALANCE SHEET",
            "name": "Current ratio",
            "result": current_ratio_result,
            "result_value": current_ratio_value,
            "pass_rule": "Above 1.00",
            "reason": current_ratio_reason,
        },
        {
            "section": "INCOME STATEMENT",
            "name": "Operating margin",
            "result": operating_margin_result,
            "result_value": operating_margin_value,
            "pass_rule": "Above 15.00%",
            "reason": operating_margin_reason,
        },
        {
            "section": "CASH FLOW STATEMENT",
            "name": "Free cash flow trend",
            "result": cash_flow_result,
            "result_value": cash_flow_value,
            "pass_rule": "Latest annual free cash flow is positive and higher than the previous year",
            "reason": cash_flow_reason,
        },
    ]


def comparison_values(statement, row_names, years_back=3):
    """Return the latest and an earlier annual value for a trend comparison."""
    values = statement_values(statement, row_names)

    if len(values) < 2:
        return None, None

    earlier_index = min(years_back, len(values) - 1)
    return values[0], values[earlier_index]


def trend_check(
    section,
    name,
    what_it_analyses,
    values,
    currency,
    positive_reason,
    negative_reason,
):
    """Build a transparent latest-versus-earlier-year financial check."""
    latest, earlier = values

    if latest is None or earlier is None:
        return {
            "section": section,
            "name": name,
            "what_it_analyses": what_it_analyses,
            "result": None,
            "result_value": "Not available",
            "pass_rule": "Latest annual figure is higher than an earlier annual figure",
            "reason": "Yahoo Finance did not provide enough annual figures to compare.",
        }

    latest_period, latest_value = latest
    earlier_period, earlier_value = earlier
    result = bool(latest_value > earlier_value)

    if earlier_value != 0:
        change_text = percentage((latest_value / earlier_value) - 1)
    else:
        change_text = "Not available because the earlier figure was zero"

    return {
        "section": section,
        "name": name,
        "what_it_analyses": what_it_analyses,
        "result": result,
        "result_value": (
            f"Latest: {money(latest_value, currency)} ({period_text(latest_period)}) "
            f"| Earlier: {money(earlier_value, currency)} ({period_text(earlier_period)}) "
            f"| Change: {change_text}"
        ),
        "pass_rule": "Latest annual figure is higher than the earlier annual figure",
        "reason": positive_reason if result else negative_reason,
    }


def calculate_drew_checks(balance_sheet, income_statement, cash_flow, currency):
    """Create a Drew Cohen-inspired financial screening checklist.

    The video describes a research process rather than fixed buy rules. These
    checks turn the observable financial signals he discusses into a clear,
    first-pass screen; they do not decide whether a stock should be bought.
    """
    revenue_values = statement_values(income_statement, ["Total Revenue"])
    revenue_trend = trend_check(
        "INCOME STATEMENT",
        "Revenue trend",
        "Whether the company is growing sales over time.",
        comparison_values(income_statement, ["Total Revenue"]),
        currency,
        "Favourable: annual revenue is higher than the earlier year.",
        "Needs review: annual revenue is not higher than the earlier year.",
    )

    latest_operating_income = latest_statement_value(
        income_statement,
        ["Operating Income"],
    )
    if latest_operating_income is None:
        operating_profit = {
            "section": "INCOME STATEMENT",
            "name": "Operating profitability",
            "what_it_analyses": "Whether the core business produced an operating profit in the latest annual report.",
            "result": None,
            "result_value": "Not available",
            "pass_rule": "Latest annual operating income is positive",
            "reason": "Yahoo Finance did not provide annual operating income.",
        }
    else:
        operating_profit_result = bool(latest_operating_income > 0)
        operating_profit = {
            "section": "INCOME STATEMENT",
            "name": "Operating profitability",
            "what_it_analyses": "Whether the core business produced an operating profit in the latest annual report.",
            "result": operating_profit_result,
            "result_value": money(latest_operating_income, currency),
            "pass_rule": "Latest annual operating income is positive",
            "reason": (
                "Favourable: the latest annual operating income is positive."
                if operating_profit_result
                else "Needs review: the latest annual operating income is negative."
            ),
        }

    operating_income_trend = trend_check(
        "INCOME STATEMENT",
        "Operating income trend",
        "Whether profit from the core business is improving over time.",
        comparison_values(income_statement, ["Operating Income"]),
        currency,
        "Favourable: annual operating income is higher than the earlier year.",
        "Needs review: annual operating income is not higher than the earlier year.",
    )

    cash = latest_statement_value(
        balance_sheet,
        [
            "Cash Cash Equivalents And Short Term Investments",
            "Cash And Cash Equivalents",
            "Cash Financial",
        ],
    )
    total_debt = latest_statement_value(balance_sheet, ["Total Debt"])
    if cash is None or total_debt is None:
        debt_and_cash = {
            "section": "BALANCE SHEET",
            "name": "Cash versus total debt",
            "what_it_analyses": "Whether available cash covers the company's reported total debt.",
            "result": None,
            "result_value": "Not available",
            "pass_rule": "Cash is at least as high as total debt",
            "reason": "Yahoo Finance did not provide both cash and total debt in the latest annual balance sheet.",
        }
    else:
        net_cash = cash - total_debt
        debt_and_cash_result = bool(net_cash >= 0)
        debt_and_cash = {
            "section": "BALANCE SHEET",
            "name": "Cash versus total debt",
            "what_it_analyses": "Whether available cash covers the company's reported total debt.",
            "result": debt_and_cash_result,
            "result_value": (
                f"Cash: {money(cash, currency)} | Debt: {money(total_debt, currency)} "
                f"| Net cash/(debt): {money(net_cash, currency)}"
            ),
            "pass_rule": "Cash is at least as high as total debt",
            "reason": (
                "Favourable: the company reports more cash than total debt."
                if debt_and_cash_result
                else "Needs review: total debt is higher than reported cash."
            ),
        }

    latest_operating_cash_flow = latest_statement_value(
        cash_flow,
        [
            "Operating Cash Flow",
            "Total Cash From Operating Activities",
            "Cash Flow From Continuing Operating Activities",
        ],
    )
    if latest_operating_cash_flow is None:
        operating_cash_flow = {
            "section": "CASH FLOW STATEMENT",
            "name": "Operating cash flow",
            "what_it_analyses": "Whether the core business generated cash in the latest annual report.",
            "result": None,
            "result_value": "Not available",
            "pass_rule": "Latest annual operating cash flow is positive",
            "reason": "Yahoo Finance did not provide annual operating cash flow.",
        }
    else:
        operating_cash_flow_result = bool(latest_operating_cash_flow > 0)
        operating_cash_flow = {
            "section": "CASH FLOW STATEMENT",
            "name": "Operating cash flow",
            "what_it_analyses": "Whether the core business generated cash in the latest annual report.",
            "result": operating_cash_flow_result,
            "result_value": money(latest_operating_cash_flow, currency),
            "pass_rule": "Latest annual operating cash flow is positive",
            "reason": (
                "Favourable: the core business generated cash in the latest annual report."
                if operating_cash_flow_result
                else "Needs review: the core business did not generate positive annual cash flow."
            ),
        }

    free_cash_flow = free_cash_flow_values(cash_flow)
    if not free_cash_flow:
        free_cash_flow_check = {
            "section": "CASH FLOW STATEMENT",
            "name": "Free cash flow after capital expenditure",
            "what_it_analyses": "Whether cash remains after the company has funded capital spending.",
            "result": None,
            "result_value": "Not available",
            "pass_rule": "Latest annual free cash flow is positive",
            "reason": "Yahoo Finance did not provide enough information to calculate annual free cash flow.",
        }
    else:
        free_cash_flow_period, latest_free_cash_flow = free_cash_flow[0]
        free_cash_flow_result = bool(latest_free_cash_flow > 0)
        free_cash_flow_check = {
            "section": "CASH FLOW STATEMENT",
            "name": "Free cash flow after capital expenditure",
            "what_it_analyses": "Whether cash remains after the company has funded capital spending.",
            "result": free_cash_flow_result,
            "result_value": (
                f"{money(latest_free_cash_flow, currency)} "
                f"({period_text(free_cash_flow_period)})"
            ),
            "pass_rule": "Latest annual free cash flow is positive",
            "reason": (
                "Favourable: cash remains after capital expenditure."
                if free_cash_flow_result
                else "Needs review: free cash flow is negative after capital expenditure."
            ),
        }

    revenue_by_period = dict(revenue_values)
    stock_compensation_values = statement_values(
        cash_flow,
        ["Stock Based Compensation", "Stock Based Compensation To Non Employees"],
    )
    stock_compensation_ratios = []
    for period, stock_compensation in stock_compensation_values:
        revenue = revenue_by_period.get(period)
        if revenue is not None and revenue > 0:
            stock_compensation_ratios.append((period, stock_compensation / revenue))

    if len(stock_compensation_ratios) < 2:
        dilution = {
            "section": "CASH FLOW STATEMENT",
            "name": "Stock-based compensation trend",
            "what_it_analyses": "Whether employee share awards are taking a growing share of revenue, which can dilute shareholders.",
            "result": None,
            "result_value": "Not available",
            "pass_rule": "Stock-based compensation is the same or a smaller share of revenue than the earlier year",
            "reason": "Yahoo Finance did not provide enough matching annual revenue and stock-compensation figures to compare.",
        }
    else:
        latest_period, latest_ratio = stock_compensation_ratios[0]
        earlier_index = min(3, len(stock_compensation_ratios) - 1)
        earlier_period, earlier_ratio = stock_compensation_ratios[earlier_index]
        dilution_result = bool(latest_ratio <= earlier_ratio)
        dilution = {
            "section": "CASH FLOW STATEMENT",
            "name": "Stock-based compensation trend",
            "what_it_analyses": "Whether employee share awards are taking a growing share of revenue, which can dilute shareholders.",
            "result": dilution_result,
            "result_value": (
                f"Latest: {percentage(latest_ratio)} of revenue ({period_text(latest_period)}) "
                f"| Earlier: {percentage(earlier_ratio)} of revenue ({period_text(earlier_period)})"
            ),
            "pass_rule": "Stock-based compensation is the same or a smaller share of revenue than the earlier year",
            "reason": (
                "Favourable: stock-based compensation is not taking a larger share of revenue."
                if dilution_result
                else "Needs review: stock-based compensation is taking a larger share of revenue."
            ),
        }

    return [
        revenue_trend,
        operating_profit,
        operating_income_trend,
        debt_and_cash,
        operating_cash_flow,
        free_cash_flow_check,
        dilution,
    ]


def years_between_periods(latest_period, earlier_period):
    """Return the approximate number of years between two statement dates."""
    try:
        years = (latest_period - earlier_period).days / 365.25
        return years if years > 0 else None
    except (AttributeError, TypeError):
        return None


def cagr_check(
    section,
    name,
    what_it_analyses,
    values,
    currency,
    measure_name,
    minimum_growth=0.0,
):
    """Build an annualised-growth check using the longest Yahoo history available."""
    latest, earlier = values

    if latest is None or earlier is None:
        return {
            "section": section,
            "name": name,
            "what_it_analyses": what_it_analyses,
            "result": None,
            "result_value": "Not available",
            "pass_rule": (
                "Positive annualised growth across the available annual history"
                if minimum_growth == 0
                else f"At least {percentage(minimum_growth)} annualised growth across the available annual history"
            ),
            "reason": "Yahoo Finance did not provide enough annual figures to calculate growth.",
        }

    latest_period, latest_value = latest
    earlier_period, earlier_value = earlier
    years = years_between_periods(latest_period, earlier_period)

    if years is None or latest_value <= 0 or earlier_value <= 0:
        return {
            "section": section,
            "name": name,
            "what_it_analyses": what_it_analyses,
            "result": None,
            "result_value": (
                f"Latest: {money(latest_value, currency)} ({period_text(latest_period)}) "
                f"| Earlier: {money(earlier_value, currency)} ({period_text(earlier_period)})"
            ),
            "pass_rule": (
                "Positive annualised growth across the available annual history"
                if minimum_growth == 0
                else f"At least {percentage(minimum_growth)} annualised growth across the available annual history"
            ),
            "reason": (
                f"{measure_name} CAGR is not meaningful when a comparison figure "
                "is zero or negative."
            ),
        }

    cagr = (latest_value / earlier_value) ** (1 / years) - 1
    result = bool(cagr >= minimum_growth)
    history_description = f"{years:.1f} years of available annual history"
    growth_requirement = (
        "positive annualised growth"
        if minimum_growth == 0
        else f"at least {percentage(minimum_growth)} annualised growth"
    )

    return {
        "section": section,
        "name": name,
        "what_it_analyses": what_it_analyses,
        "result": result,
        "result_value": (
            f"CAGR: {percentage(cagr)} over {history_description} "
            f"| Latest: {money(latest_value, currency)} ({period_text(latest_period)}) "
            f"| Earlier: {money(earlier_value, currency)} ({period_text(earlier_period)})"
        ),
        "pass_rule": f"{growth_requirement.capitalize()} across the available annual history",
        "reason": (
            f"Favourable: {measure_name} meets the {growth_requirement} requirement."
            if result
            else f"Needs review: {measure_name} does not meet the {growth_requirement} requirement."
        ),
    }


def calculate_plain_bagel_checks(
    balance_sheet,
    income_statement,
    cash_flow,
    currency,
):
    """Create a Plain Bagel-inspired long-term financial checklist.

    Yahoo Finance usually supplies only a few annual periods. This adapts the
    video's long-term process to the longest annual history Yahoo provides; it
    is not a replacement for five-, ten-, or fifteen-year report analysis.
    """
    revenue_values = statement_values(income_statement, ["Total Revenue"])
    revenue_cagr = cagr_check(
        "INCOME STATEMENT",
        "Revenue CAGR (available history)",
        "Whether sales have grown at an annualised rate across the available annual history.",
        comparison_values(income_statement, ["Total Revenue"]),
        currency,
        "Revenue",
        minimum_growth=0.05,
    )

    operating_income_cagr = cagr_check(
        "INCOME STATEMENT",
        "Operating income CAGR (available history)",
        "Whether core-business profit has grown at an annualised rate across the available annual history.",
        comparison_values(income_statement, ["Operating Income"]),
        currency,
        "Operating income",
    )

    revenue_by_period = dict(revenue_values)
    operating_expense_values = statement_values(
        income_statement,
        ["Operating Expense", "Operating Expenses"],
    )
    operating_expense_ratios = [
        (period, operating_expense / revenue_by_period[period])
        for period, operating_expense in operating_expense_values
        if period in revenue_by_period and revenue_by_period[period] > 0
    ]

    if len(operating_expense_ratios) < 2:
        operating_cost_share = {
            "section": "INCOME STATEMENT",
            "name": "Operating-cost share trend",
            "what_it_analyses": "Whether operating costs are taking a larger or smaller share of revenue over time.",
            "result": None,
            "result_value": "Not available",
            "pass_rule": "Operating expenses are the same or a smaller share of revenue than the earlier year",
            "reason": "Yahoo Finance did not provide enough matching annual operating-expense and revenue figures to compare.",
        }
    else:
        latest_period, latest_ratio = operating_expense_ratios[0]
        earlier_index = min(3, len(operating_expense_ratios) - 1)
        earlier_period, earlier_ratio = operating_expense_ratios[earlier_index]
        operating_cost_share_result = bool(latest_ratio <= earlier_ratio)
        operating_cost_share = {
            "section": "INCOME STATEMENT",
            "name": "Operating-cost share trend",
            "what_it_analyses": "Whether operating costs are taking a larger or smaller share of revenue over time.",
            "result": operating_cost_share_result,
            "result_value": (
                f"Latest: {percentage(latest_ratio)} of revenue ({period_text(latest_period)}) "
                f"| Earlier: {percentage(earlier_ratio)} of revenue ({period_text(earlier_period)})"
            ),
            "pass_rule": "Operating expenses are the same or a smaller share of revenue than the earlier year",
            "reason": (
                "Favourable: operating expenses are not taking a larger share of revenue."
                if operating_cost_share_result
                else "Needs review: operating expenses are taking a larger share of revenue."
            ),
        }

    cash_by_period = dict(
        statement_values(
            balance_sheet,
            [
                "Cash Cash Equivalents And Short Term Investments",
                "Cash And Cash Equivalents",
                "Cash Financial",
            ],
        )
    )
    debt_by_period = dict(statement_values(balance_sheet, ["Total Debt"]))
    net_cash_values = [
        (period, cash - debt_by_period[period])
        for period, cash in cash_by_period.items()
        if period in debt_by_period
    ]
    try:
        net_cash_values.sort(key=lambda item: item[0], reverse=True)
    except TypeError:
        pass

    if len(net_cash_values) < 2:
        net_debt_trend = {
            "section": "BALANCE SHEET",
            "name": "Net cash/(debt) trend",
            "what_it_analyses": "Whether the company's cash position relative to total debt is improving over time.",
            "result": None,
            "result_value": "Not available",
            "pass_rule": "Net cash/(debt) is better than or equal to the earlier year",
            "reason": "Yahoo Finance did not provide enough matching annual cash and total-debt figures to compare.",
        }
    else:
        latest_period, latest_net_cash = net_cash_values[0]
        earlier_index = min(3, len(net_cash_values) - 1)
        earlier_period, earlier_net_cash = net_cash_values[earlier_index]
        net_debt_trend_result = bool(latest_net_cash >= earlier_net_cash)
        net_debt_trend = {
            "section": "BALANCE SHEET",
            "name": "Net cash/(debt) trend",
            "what_it_analyses": "Whether the company's cash position relative to total debt is improving over time.",
            "result": net_debt_trend_result,
            "result_value": (
                f"Latest: {money(latest_net_cash, currency)} ({period_text(latest_period)}) "
                f"| Earlier: {money(earlier_net_cash, currency)} ({period_text(earlier_period)})"
            ),
            "pass_rule": "Net cash/(debt) is better than or equal to the earlier year",
            "reason": (
                "Favourable: cash relative to total debt has improved or remained stable."
                if net_debt_trend_result
                else "Needs review: cash relative to total debt has weakened."
            ),
        }

    net_income_by_period = dict(statement_values(income_statement, ["Net Income"]))
    equity_by_period = dict(
        statement_values(
            balance_sheet,
            ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"],
        )
    )
    annual_roe_values = [
        (period, net_income / equity_by_period[period])
        for period, net_income in net_income_by_period.items()
        if period in equity_by_period and equity_by_period[period] != 0
    ]

    if not annual_roe_values:
        return_on_equity_history = {
            "section": "INCOME STATEMENT + BALANCE SHEET",
            "name": "Return on equity history",
            "what_it_analyses": "Whether the company has produced positive profit relative to shareholder equity across the available annual history.",
            "result": None,
            "result_value": "Not available",
            "pass_rule": "Average annual return on ending equity is at least 10.00%",
            "reason": "Yahoo Finance did not provide matching annual net-income and shareholder-equity figures.",
        }
    else:
        average_roe = sum(value for _, value in annual_roe_values) / len(annual_roe_values)
        roe_history_result = bool(average_roe >= 0.10)
        return_on_equity_history = {
            "section": "INCOME STATEMENT + BALANCE SHEET",
            "name": "Return on equity history",
            "what_it_analyses": "Whether the company has produced positive profit relative to shareholder equity across the available annual history.",
            "result": roe_history_result,
            "result_value": (
                f"Average: {percentage(average_roe)} across "
                f"{len(annual_roe_values)} annual periods"
            ),
            "pass_rule": "Average annual return on ending equity is at least 10.00%",
            "reason": (
                "Favourable: the company has generated at least a 10.00% average return on shareholder equity."
                if roe_history_result
                else "Needs review: the company has not generated at least a 10.00% average return on shareholder equity."
            ),
        }

    operating_cash_flow_by_period = dict(
        statement_values(
            cash_flow,
            [
                "Operating Cash Flow",
                "Total Cash From Operating Activities",
                "Cash Flow From Continuing Operating Activities",
            ],
        )
    )
    capital_expenditure_by_period = dict(
        statement_values(cash_flow, ["Capital Expenditure", "Capital Expenditures"])
    )
    cash_after_capex_values = [
        (
            period,
            operating_cash_flow,
            capital_expenditure_by_period[period],
            operating_cash_flow - abs(capital_expenditure_by_period[period]),
        )
        for period, operating_cash_flow in operating_cash_flow_by_period.items()
        if period in capital_expenditure_by_period
    ]
    try:
        cash_after_capex_values.sort(key=lambda item: item[0], reverse=True)
    except TypeError:
        pass

    if not cash_after_capex_values:
        capital_expenditure_coverage = {
            "section": "CASH FLOW STATEMENT",
            "name": "Capital-expenditure coverage",
            "what_it_analyses": "Whether cash from operations covers the company's latest capital spending.",
            "result": None,
            "result_value": "Not available",
            "pass_rule": "Operating cash flow is greater than capital expenditure",
            "reason": "Yahoo Finance did not provide matching annual operating-cash-flow and capital-expenditure figures.",
        }
    else:
        latest_period, operating_cash_flow, capital_expenditure, cash_after_capex = (
            cash_after_capex_values[0]
        )
        capital_expenditure_coverage_result = bool(cash_after_capex > 0)
        capital_expenditure_coverage = {
            "section": "CASH FLOW STATEMENT",
            "name": "Capital-expenditure coverage",
            "what_it_analyses": "Whether cash from operations covers the company's latest capital spending.",
            "result": capital_expenditure_coverage_result,
            "result_value": (
                f"Operating cash flow: {money(operating_cash_flow, currency)} "
                f"| Capital expenditure: {money(abs(capital_expenditure), currency)} "
                f"| Cash after spending: {money(cash_after_capex, currency)} "
                f"({period_text(latest_period)})"
            ),
            "pass_rule": "Operating cash flow is greater than capital expenditure",
            "reason": (
                "Favourable: operating cash flow covered the latest capital spending."
                if capital_expenditure_coverage_result
                else "Needs review: capital spending was greater than operating cash flow."
            ),
        }

    return [
        revenue_cagr,
        operating_income_cagr,
        operating_cost_share,
        net_debt_trend,
        return_on_equity_history,
        capital_expenditure_coverage,
    ]


def calculate_risk_metrics(daily_close):
    """Calculate simple one-year risk observations from Yahoo price history."""
    daily_returns = daily_close.pct_change().dropna()

    if daily_returns.empty:
        return {
            "annualised_volatility": None,
            "maximum_drawdown": None,
            "current_drawdown": None,
        }

    running_high = daily_close.cummax()
    drawdowns = (daily_close / running_high) - 1

    return {
        "annualised_volatility": daily_returns.std() * math.sqrt(252),
        "maximum_drawdown": drawdowns.min(),
        "current_drawdown": (daily_close.iloc[-1] / daily_close.max()) - 1,
    }


def utc_timestamp():
    """Return a timezone-aware timestamp for the screener cache."""
    return datetime.now(timezone.utc).isoformat()


def load_screen_cache():
    """Load prior financial-screen summaries without failing the program."""
    try:
        with SCREEN_CACHE_FILE.open("r", encoding="utf-8") as cache_file:
            cache = json.load(cache_file)
        records = cache.get("records", {})
        return records if isinstance(records, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_screen_cache(records):
    """Save the reusable score summaries safely beside this script."""
    temporary_file = SCREEN_CACHE_FILE.with_suffix(".tmp")
    try:
        with temporary_file.open("w", encoding="utf-8") as cache_file:
            json.dump({"records": records}, cache_file, indent=2, sort_keys=True)
        temporary_file.replace(SCREEN_CACHE_FILE)
    except OSError:
        try:
            temporary_file.unlink(missing_ok=True)
        except OSError:
            pass


def cached_record_is_fresh(record):
    """Return True only when a cached financial score is less than one day old."""
    try:
        updated_at = datetime.fromisoformat(record["financial_data_checked_at"])
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - updated_at.astimezone(timezone.utc)
        return timedelta(0) <= age <= SCREEN_CACHE_MAX_AGE
    except (KeyError, TypeError, ValueError):
        return False


def normalise_yahoo_ticker(value):
    """Convert a component-list ticker into Yahoo Finance ticker format."""
    ticker = str(value).strip().upper()
    if not ticker or ticker in {"NAN", "NONE", "NULL", "-"}:
        return ""
    return ticker.replace(".", "-")


def get_screen_quotes(response, source_name):
    """Return valid live Yahoo Finance quote dictionaries from a screen result."""
    quotes = response.get("quotes", []) if isinstance(response, dict) else []
    cleaned_quotes = []

    for quote in quotes:
        if not isinstance(quote, dict):
            continue

        ticker = normalise_yahoo_ticker(quote.get("symbol", ""))
        if ticker:
            cleaned_quotes.append({**quote, "symbol": ticker, "source": source_name})

    if not cleaned_quotes:
        raise RuntimeError(
            f"Yahoo Finance did not return any {source_name} stocks. "
            "Try again during US market hours or later today."
        )

    return cleaned_quotes


def get_most_active_quotes(limit=DEFAULT_ACTIVE_STOCKS):
    """Get a larger, current US Most Active list with live quote details."""
    screen = getattr(yf, "screen", None)
    if screen is None:
        raise RuntimeError(
            "This yfinance version cannot load Yahoo Finance screens. "
            "Update it with: pip install --upgrade yfinance"
        )

    response = screen("most_actives", count=min(limit, MAX_SCREEN_UNIVERSE))
    return get_screen_quotes(response, "Yahoo Most Active")


def get_emerging_stock_quotes(limit=DEFAULT_EMERGING_STOCKS):
    """Get liquid smaller US companies, then let the financial model rank them.

    The Yahoo query only defines a tradeable small-company universe. It does
    not award any model points itself, so every result still has to pass the
    same financial checks as an established company.
    """
    screen = getattr(yf, "screen", None)
    query_class = getattr(yf, "EquityQuery", None)

    if screen is None or query_class is None:
        raise RuntimeError(
            "This yfinance version cannot run the emerging-company screen. "
            "Update it with: pip install --upgrade yfinance"
        )

    query = query_class(
        "and",
        [
            query_class("eq", ["region", "us"]),
            query_class("is-in", ["exchange", "NMS", "NYQ", "ASE"]),
            query_class(
                "btwn",
                [
                    "intradaymarketcap",
                    EMERGING_MIN_MARKET_CAP,
                    EMERGING_MAX_MARKET_CAP,
                ],
            ),
            query_class("gte", ["intradayprice", EMERGING_MIN_PRICE]),
            query_class("gte", ["dayvolume", EMERGING_MIN_DAY_VOLUME]),
            query_class("gte", ["avgdailyvol3m", EMERGING_MIN_AVERAGE_VOLUME]),
        ],
    )
    response = screen(
        query,
        size=min(limit, MAX_SCREEN_UNIVERSE),
        sortField="dayvolume",
        sortAsc=False,
    )
    return get_screen_quotes(response, "Liquid small / emerging company")


def get_screening_data(ticker):
    """Get only the financial data needed for a fast weighted-score screen."""
    ticker = normalise_yahoo_ticker(ticker)
    if not ticker:
        raise ValueError("Yahoo Finance returned an invalid ticker symbol.")

    stock = yf.Ticker(ticker)
    info = safe_info(stock)
    quote_type = str(info.get("quoteType", "Unknown"))

    if quote_type.upper() in FUND_TYPES:
        raise ValueError("This is a fund or index, not an individual company.")

    currency = info.get("currency", "$")
    balance_sheet = safe_statement(stock, ["balance_sheet"])
    income_statement = safe_statement(stock, ["income_stmt", "financials"])
    cash_flow = safe_statement(stock, ["cashflow", "cash_flow"])

    return {
        "ticker": ticker,
        "name": info.get("longName", info.get("shortName", ticker)),
        "sector": info.get("sector", "Not available"),
        "currency": currency,
        "tilbury_checks": calculate_tilbury_checks(
            balance_sheet, income_statement, cash_flow, currency
        ),
        "drew_checks": calculate_drew_checks(
            balance_sheet, income_statement, cash_flow, currency
        ),
        "plain_bagel_checks": calculate_plain_bagel_checks(
            balance_sheet, income_statement, cash_flow, currency
        ),
    }


def first_quote_value(quote, field_names):
    """Return the first present field from a Yahoo Finance screen quote."""
    if not isinstance(quote, dict):
        return None

    for field_name in field_names:
        value = quote.get(field_name)
        if value is not None and value != "":
            return value

    return None


def live_quote_snapshot(quote):
    """Keep just the fresh, readable fields used in the screener output."""
    price = number(first_quote_value(quote, ["regularMarketPrice", "price"]))
    day_change = number(
        first_quote_value(
            quote,
            ["regularMarketChangePercent", "percentchange", "changePercent"],
        )
    )
    day_volume = number(
        first_quote_value(quote, ["regularMarketVolume", "dayVolume", "volume"])
    )
    average_volume = number(
        first_quote_value(
            quote,
            ["averageDailyVolume3Month", "avgDailyVolume3Month"],
        )
    )
    market_cap = number(first_quote_value(quote, ["marketCap", "marketcap"]))

    return {
        "name": first_quote_value(quote, ["longName", "shortName", "displayName"]),
        "currency": first_quote_value(quote, ["currency"]) or "$",
        "price": price,
        "day_change": day_change,
        "day_volume": day_volume,
        "average_volume": average_volume,
        "relative_volume": (
            day_volume / average_volume
            if is_number(day_volume) and is_number(average_volume) and average_volume > 0
            else None
        ),
        "market_cap": market_cap,
    }


def update_record_with_live_quote(record, quote, sources):
    """Attach a fresh quote to a cached-or-new financial score."""
    updated_record = dict(record)
    snapshot = live_quote_snapshot(quote)

    if snapshot["name"]:
        updated_record["name"] = str(snapshot["name"])

    updated_record.update(snapshot)
    updated_record["sources"] = list(sources)
    updated_record["live_quote_checked_at"] = utc_timestamp()
    updated_record["emerging_watchlist"] = is_emerging_watchlist_candidate(
        updated_record
    )
    return updated_record


def is_screen_candidate(summary):
    """Apply the same high-score safeguards used in the full stock report."""
    return bool(
        summary["score"] is not None
        and summary["score"] >= 70
        and summary["data_coverage"] >= 85
        and not summary["high_priority_failures"]
        and not summary["high_priority_missing"]
    )


def make_screen_record(ticker):
    """Create the compact, cacheable result for one company's financial screen."""
    data = get_screening_data(ticker)
    summary = weighted_financial_score(data)
    score = summary["score"]

    if score is None:
        raise ValueError("Yahoo Finance did not provide usable weighted financial data.")

    return {
        "ticker": data["ticker"],
        "name": str(data["name"]),
        "sector": str(data["sector"]),
        "score": score,
        "data_coverage": summary["data_coverage"],
        "high_priority_failures": summary["high_priority_failures"],
        "high_priority_missing": summary["high_priority_missing"],
        "status": financial_screen_label(
            score,
            summary["data_coverage"],
            summary["high_priority_failures"],
            summary["high_priority_missing"],
        ),
        "candidate": is_screen_candidate(summary),
        "financial_data_checked_at": utc_timestamp(),
    }


def is_emerging_watchlist_candidate(record):
    """Flag promising smaller companies with one missing core-history check.

    Newer public companies can have a shorter statement history, so this is a
    watchlist label rather than a full model match. No failed high-priority
    checks are allowed.
    """
    is_emerging = "Liquid small / emerging company" in record.get("sources", [])
    return bool(
        is_emerging
        and not record.get("candidate")
        and is_number(record.get("score"))
        and record["score"] >= 70
        and record.get("data_coverage", 0) >= 70
        and record.get("high_priority_failures", 0) == 0
        and record.get("high_priority_missing", 0) <= 1
    )


def add_source_quotes(ticker_sources, quotes):
    """Keep each ticker once while retaining its freshest screen quote."""
    for quote in quotes:
        ticker = normalise_yahoo_ticker(quote.get("symbol", ""))
        source_name = str(quote.get("source", "Yahoo Finance screen"))

        if not ticker:
            continue

        entry = ticker_sources.setdefault(
            ticker,
            {"sources": [], "quote": quote},
        )
        if source_name not in entry["sources"]:
            entry["sources"].append(source_name)
        entry["quote"] = quote


def screen_result_status(record):
    """Return a short status that keeps the results table easy to read."""
    if record["candidate"]:
        return "MODEL MATCH"
    if record.get("emerging_watchlist"):
        return "EMERGING WATCHLIST"
    if record["high_priority_failures"]:
        return "CORE CONCERN"
    if record["high_priority_missing"] or record["data_coverage"] < 85:
        return "INCOMPLETE"
    return "MIXED"


def compact_number(value):
    """Format a large quantity compactly for the screener table."""
    if not is_number(value):
        return "n/a"

    value = float(value)
    absolute_value = abs(value)

    if absolute_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if absolute_value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if absolute_value >= 1_000:
        return f"{value / 1_000:.0f}K"
    return f"{value:.0f}"


def compact_money(value, currency="$"):
    """Format a market price or market value without an overly wide table."""
    if not is_number(value):
        return "n/a"

    prefix = "$" if currency == "$" else f"{currency} "
    value = float(value)
    absolute_value = abs(value)

    if absolute_value >= 1_000_000_000:
        return f"{prefix}{value / 1_000_000_000:.2f}B"
    if absolute_value >= 1_000_000:
        return f"{prefix}{value / 1_000_000:.1f}M"
    if absolute_value >= 1_000:
        return f"{prefix}{value / 1_000:.1f}K"
    return f"{prefix}{value:.2f}"


def signed_percentage_points(value):
    """Format Yahoo's already-percent day-change field."""
    if not is_number(value):
        return "n/a"
    return f"{float(value):+.2f}%"


def score_sort_value(value):
    """Use missing live values at the end of a ranked result list."""
    return float(value) if is_number(value) else -1.0


def screen_sort_key(record):
    """Rank quality first, then put the most actively traded matches first."""
    return (
        -score_sort_value(record.get("score")),
        -score_sort_value(record.get("data_coverage")),
        -score_sort_value(record.get("relative_volume")),
        -score_sort_value(record.get("day_volume")),
        record.get("ticker", ""),
    )


def print_screen_table(title, records, top_count, watchlist=False):
    """Print a compact, current-data table for one group of screen results."""
    records = sorted(records, key=screen_sort_key)

    print(f"\n{title}")
    if not records:
        print("  None in this run.")
        return

    print(
        f"{'#':<3}{'Ticker':<9}{'Score':>8}{'Data':>7}{'Today':>9}"
        f"{'Rel vol':>9}{'Price':>11}{'Mkt cap':>12}  Company"
    )
    print("-" * 112)

    for rank, record in enumerate(records[:top_count], start=1):
        score = f"{record['score']:.0f}/100" if is_number(record.get("score")) else "n/a"
        coverage = (
            f"{record['data_coverage']:.0f}%"
            if is_number(record.get("data_coverage"))
            else "n/a"
        )
        relative_volume = (
            f"{record['relative_volume']:.1f}x"
            if is_number(record.get("relative_volume"))
            else "n/a"
        )
        name = str(record.get("name", record["ticker"]))[:34]

        print(
            f"{rank:<3}{record['ticker']:<9}{score:>8}{coverage:>7}"
            f"{signed_percentage_points(record.get('day_change')):>9}"
            f"{relative_volume:>9}"
            f"{compact_money(record.get('price'), record.get('currency', '$')):>11}"
            f"{compact_money(record.get('market_cap'), record.get('currency', '$')):>12}  "
            f"{name}"
        )

    if len(records) > top_count:
        label = "watchlist names" if watchlist else "model matches"
        print(f"Showing the top {top_count} of {len(records)} {label}.")


def print_screening_results(records, failed_count, fresh_count, cached_count, top_count):
    """Print strict model matches plus a transparent emerging-stock watchlist."""
    candidates = [record for record in records if record["candidate"]]
    emerging_watchlist = [
        record for record in records if record.get("emerging_watchlist")
    ]

    print("\n" + "=" * 112)
    print("LIVE US STOCK SCREENER — FINANCIAL MODEL MATCHES")
    print("=" * 112)
    quote_times = [
        record.get("live_quote_checked_at")
        for record in records
        if record.get("live_quote_checked_at")
    ]
    latest_quote_time = max(quote_times) if quote_times else "Not available"
    print(
        f"Live quote snapshot: {latest_quote_time} | "
        f"Companies scored: {len(records)} | Could not score: {failed_count}"
    )
    print(
        f"Financial scores used: {fresh_count} refreshed now, {cached_count} "
        f"reused from the last {int(SCREEN_CACHE_MAX_AGE.total_seconds() // 3600)} hours"
    )
    print(
        "Live price, day change, volume and market value are refreshed on every run. "
        "The financial score uses annual company statements."
    )
    print(
        "Strict model match: score 70+; data coverage 85%+; no failed or missing "
        "high-priority check."
    )

    print_screen_table(
        "STRICT MODEL MATCHES — RESEARCH CANDIDATES, NOT BUY RECOMMENDATIONS",
        candidates,
        top_count,
    )

    print_screen_table(
        "SMALL / EMERGING WATCHLIST — ONE CORE HISTORY CHECK MAY BE MISSING",
        emerging_watchlist,
        top_count,
        watchlist=True,
    )

    print(
        "\nRel vol = today's volume ÷ the three-month average daily volume. "
        "High activity can be caused by either good or bad news, so it is not a score bonus."
    )
    print(
        "The small / emerging universe is US-listed companies with market value "
        "$50m–$2bn, price $2+, and minimum day/average-volume checks. "
        "Research any name individually before considering it."
    )


def refresh_live_quote_sources(ticker_sources, source_loaders):
    """Refresh quotes after financial scoring, without redoing statements."""
    refreshed_sources = {}
    errors = []

    for source_loader in source_loaders:
        try:
            add_source_quotes(refreshed_sources, source_loader())
        except Exception as error:
            errors.append(str(error))

    for ticker, source_data in refreshed_sources.items():
        if ticker in ticker_sources:
            ticker_sources[ticker] = source_data

    if refreshed_sources:
        return

    if errors:
        print(
            "Could not refresh live quotes after the financial screen. "
            "Showing the quote snapshot from the start of this run."
        )


def screen_stock_universe(
    ticker_sources,
    top_count,
    force_refresh=False,
    source_loaders=None,
):
    """Score a live stock universe and rank the strongest research candidates."""
    cache = load_screen_cache()
    financial_records = []
    failed_count = 0
    fresh_count = 0
    cached_count = 0
    total = len(ticker_sources)

    print(
        f"\nScreening {total} companies. A first-time screen can take several minutes "
        "because annual statements are checked company by company."
    )

    for position, (ticker, source_data) in enumerate(ticker_sources.items(), start=1):
        if position == 1 or position == total or position % 25 == 0:
            print(f"Progress: {position}/{total} companies checked...")

        cached_record = cache.get(ticker)
        if not force_refresh and cached_record_is_fresh(cached_record):
            record = dict(cached_record)
            cached_count += 1
        else:
            try:
                record = make_screen_record(ticker)
                cache[ticker] = record
                fresh_count += 1
                time.sleep(SCREEN_REQUEST_DELAY_SECONDS)
            except Exception:
                failed_count += 1
                continue

        financial_records.append((ticker, record))

    if source_loaders:
        print("Refreshing live quotes for the final results...")
        refresh_live_quote_sources(ticker_sources, source_loaders)

    scored_records = []
    for ticker, record in financial_records:
        source_data = ticker_sources[ticker]
        scored_records.append(
            update_record_with_live_quote(
                record,
                source_data["quote"],
                source_data["sources"],
            )
        )

    save_screen_cache(cache)
    print_screening_results(
        scored_records, failed_count, fresh_count, cached_count, top_count
    )


def read_screen_result_count():
    """Ask for a sensible number of ranked screen results."""
    response = input(
        f"How many top research candidates should be shown? "
        f"[default {DEFAULT_SCREEN_RESULTS}, maximum {MAX_SCREEN_RESULTS}]: "
    ).strip()
    if not response:
        return DEFAULT_SCREEN_RESULTS
    try:
        return max(1, min(int(response), MAX_SCREEN_RESULTS))
    except ValueError:
        print(f"Using the default of {DEFAULT_SCREEN_RESULTS} results.")
        return DEFAULT_SCREEN_RESULTS


def read_screen_universe_size(label, default_size):
    """Ask how much of a current Yahoo screen should be financially checked."""
    response = input(
        f"How many {label} should be screened? "
        f"[default {default_size}, maximum {MAX_SCREEN_UNIVERSE}]: "
    ).strip()

    if not response:
        return default_size

    try:
        return max(1, min(int(response), MAX_SCREEN_UNIVERSE))
    except ValueError:
        print(f"Using the default of {default_size} companies.")
        return default_size


def should_force_screen_refresh():
    """Let the user refresh annual data while always refreshing live quotes."""
    response = input(
        "Refresh every annual financial score now? Live quotes are always fresh. [y/N]: "
    ).strip().lower()
    return response in {"y", "yes"}


def run_stock_screener(choice):
    """Build the selected live universe and run the weighted financial screen."""
    ticker_sources = {}
    source_loaders = []

    try:
        if choice in {"2", "4"}:
            active_limit = read_screen_universe_size(
                "current Most Active companies",
                DEFAULT_ACTIVE_STOCKS,
            )
            active_quotes = get_most_active_quotes(active_limit)
            add_source_quotes(ticker_sources, active_quotes)
            source_loaders.append(
                lambda: get_most_active_quotes(active_limit)
            )
            print(
                f"Loaded {len(active_quotes)} current Yahoo Finance Most Active companies."
            )

        if choice in {"3", "4"}:
            emerging_limit = read_screen_universe_size(
                "liquid small / emerging companies",
                DEFAULT_EMERGING_STOCKS,
            )
            emerging_quotes = get_emerging_stock_quotes(emerging_limit)
            add_source_quotes(ticker_sources, emerging_quotes)
            source_loaders.append(
                lambda: get_emerging_stock_quotes(emerging_limit)
            )
            print(
                f"Loaded {len(emerging_quotes)} liquid small / emerging companies."
            )
    except Exception as error:
        print(f"\nCould not build the live screen list: {error}")
        return

    if not ticker_sources:
        print("\nNo companies were available to screen.")
        return

    top_count = read_screen_result_count()
    force_refresh = should_force_screen_refresh()
    screen_stock_universe(
        ticker_sources,
        top_count,
        force_refresh,
        source_loaders,
    )


def get_stock_data(ticker):
    """Retrieve Yahoo Finance price history and company data for one ticker."""
    ticker = ticker.strip().upper()

    if not ticker:
        raise ValueError("Please enter a ticker symbol.")

    stock = yf.Ticker(ticker)

    # Two years of daily data supports the 200-day average and one-year return.
    daily = stock.history(period="2y", interval="1d", auto_adjust=True)

    if daily.empty:
        raise ValueError("No daily price data was found. Check the ticker symbol.")

    # Yahoo Finance may provide one-minute data for recent days. Funds often
    # have daily prices only, so the script safely falls back to daily data.
    intraday = stock.history(
        period="5d",
        interval="1m",
        auto_adjust=False,
        prepost=True,
    )

    info = safe_info(stock)
    quote_type = info.get("quoteType", "Unknown")

    if str(quote_type).upper() in FUND_TYPES:
        tilbury_checks = None
        drew_checks = None
        plain_bagel_checks = None
    else:
        balance_sheet = safe_statement(stock, ["balance_sheet"])
        income_statement = safe_statement(stock, ["income_stmt", "financials"])
        cash_flow = safe_statement(stock, ["cashflow", "cash_flow"])
        tilbury_checks = calculate_tilbury_checks(
            balance_sheet,
            income_statement,
            cash_flow,
            info.get("currency", "$"),
        )
        drew_checks = calculate_drew_checks(
            balance_sheet,
            income_statement,
            cash_flow,
            info.get("currency", "$"),
        )
        plain_bagel_checks = calculate_plain_bagel_checks(
            balance_sheet,
            income_statement,
            cash_flow,
            info.get("currency", "$"),
        )

    daily_close = daily["Close"].dropna()
    latest_price = daily_close.iloc[-1]
    latest_time = daily_close.index[-1]

    if not intraday.empty:
        intraday_close = intraday["Close"].dropna()
        if not intraday_close.empty:
            latest_price = intraday_close.iloc[-1]
            latest_time = intraday_close.index[-1]

    average_50 = (
        daily_close.rolling(50).mean().iloc[-1]
        if len(daily_close) >= 50
        else None
    )
    average_200 = (
        daily_close.rolling(200).mean().iloc[-1]
        if len(daily_close) >= 200
        else None
    )

    one_year_start = -253 if len(daily_close) >= 253 else 0
    one_year_return = (
        (daily_close.iloc[-1] / daily_close.iloc[one_year_start]) - 1
        if len(daily_close) >= 2
        else None
    )
    one_year_close = (
        daily_close.iloc[-253:]
        if len(daily_close) >= 253
        else daily_close
    )

    return {
        "ticker": ticker,
        "name": info.get("longName", info.get("shortName", ticker)),
        "type": quote_type,
        "sector": info.get("sector", "Not available"),
        "industry": info.get("industry", "Not available"),
        "description": info.get("longBusinessSummary", "Not available"),
        "currency": info.get("currency", "$"),
        "latest_price": latest_price,
        "latest_time": latest_time,
        "one_year_return": one_year_return,
        "average_50": average_50,
        "average_200": average_200,
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE"),
        "profit_margin": info.get("profitMargins"),
        "return_on_equity": info.get("returnOnEquity"),
        "revenue_growth": info.get("revenueGrowth"),
        "debt_to_equity": info.get("debtToEquity"),
        "risk": calculate_risk_metrics(one_year_close),
        "tilbury_checks": tilbury_checks,
        "drew_checks": drew_checks,
        "plain_bagel_checks": plain_bagel_checks,
    }


def tilbury_score(checks):
    """Return passed and available checks for the three quantitative tests."""
    available_checks = [check for check in checks if check["result"] is not None]
    passed_checks = [check for check in available_checks if check["result"] is True]
    return len(passed_checks), len(available_checks)


def tilbury_marker(result):
    """Return a short, readable label for a quantitative check."""
    if result is True:
        return "PASS"
    if result is False:
        return "WATCH"
    return "NO DATA"


def print_drew_checklist(checks):
    """Print the Drew Cohen-inspired checklist with clear analysis labels."""
    passed_checks, available_checks = tilbury_score(checks)

    print(
        f"Screening score: {passed_checks}/{len(checks)} favourable checks"
        f"  |  Data available for {available_checks}/{len(checks)} checks"
    )
    print(
        "This is a first-pass financial screen. It does not include valuation "
        "or decide whether to buy."
    )

    for check in checks:
        print(
            f"\n[{tilbury_marker(check['result']):7}] "
            f"{check['section']} — {check['name']}"
        )
        print(f"          Analyses: {check['what_it_analyses']}")
        print(f"          Result: {check['result_value']}")
        print(f"          Favourable result: {check['pass_rule']}")
        print(f"          {check['reason']}")


def print_drew_valuation_step(data):
    """Explain the manual valuation work that cannot be scored reliably."""
    print("\nDREW COHEN VALUATION STEP — MANUAL REVIEW REQUIRED")
    print(
        "Analyses: whether the current market price is reasonable versus "
        "conservative future earnings and cash-flow expectations."
    )
    print(
        f"Available starting figures: P/E {number_text(data['pe_ratio'])}"
        f"  |  Market value {money(data['market_cap'], data['currency'])}"
    )
    print(
        "Next step: make conservative forecasts for up to three years, then "
        "use a DCF or reverse DCF. A strong screening score is not a buy signal "
        "unless the valuation also looks attractive."
    )


def print_plain_bagel_checklist(checks):
    """Print the Plain Bagel-inspired checklist with clear analysis labels."""
    passed_checks, available_checks = tilbury_score(checks)

    print(
        f"Screening score: {passed_checks}/{len(checks)} favourable checks"
        f"  |  Data available for {available_checks}/{len(checks)} checks"
    )
    print(
        "Yahoo Finance usually supplies only a few annual periods. These checks "
        "use the longest available history, not a full 5-, 10-, or 15-year study."
    )

    for check in checks:
        print(
            f"\n[{tilbury_marker(check['result']):7}] "
            f"{check['section']} — {check['name']}"
        )
        print(f"          Analyses: {check['what_it_analyses']}")
        print(f"          Result: {check['result_value']}")
        print(f"          Favourable result: {check['pass_rule']}")
        print(f"          {check['reason']}")


def print_plain_bagel_valuation_step(data):
    """Explain the Plain Bagel valuation and peer-comparison work still needed."""
    print("\nPLAIN BAGEL VALUATION & PEER COMPARISON — MANUAL REVIEW REQUIRED")
    print(
        "Analyses: whether this stock is fairly priced against its own history, "
        "similar companies, and conservative future cash flows."
    )
    print(
        f"Available starting figures: P/E {number_text(data['pe_ratio'])}"
        f"  |  Market value {money(data['market_cap'], data['currency'])}"
    )
    print(
        "Next step: compare valuation multiples with direct peers and the "
        "company's history. Use a DCF with conservative forecasts and test how "
        "the result changes when assumptions change."
    )


def weighted_financial_score(data):
    """Score selected, distinct financial checks using their assigned weights."""
    framework_checks = {
        "Mark Tilbury": data["tilbury_checks"],
        "Drew Cohen": data["drew_checks"],
        "Plain Bagel": data["plain_bagel_checks"],
    }
    results = []
    total_weight = sum(item["weight"] for item in WEIGHTED_SCORE_ITEMS)
    available_weight = 0
    earned_weight = 0
    high_priority_failures = 0
    high_priority_missing = 0

    for item in WEIGHTED_SCORE_ITEMS:
        checks = framework_checks[item["framework"]]
        check = next(
            (
                candidate
                for candidate in checks
                if candidate["name"] == item["check_name"]
            ),
            None,
        )
        result = check["result"] if check is not None else None

        if result is not None:
            available_weight += item["weight"]
            if result is True:
                earned_weight += item["weight"]
            elif item["priority"] == "HIGH":
                high_priority_failures += 1
        elif item["priority"] == "HIGH":
            high_priority_missing += 1

        results.append({**item, "check": check, "result": result})

    score = (earned_weight / available_weight * 100) if available_weight else None
    data_coverage = (
        available_weight / total_weight * 100 if total_weight else 0
    )

    return {
        "score": score,
        "total_weight": total_weight,
        "earned_weight": earned_weight,
        "available_weight": available_weight,
        "unearned_weight": available_weight - earned_weight,
        "unavailable_weight": total_weight - available_weight,
        "data_coverage": data_coverage,
        "high_priority_failures": high_priority_failures,
        "high_priority_missing": high_priority_missing,
        "results": results,
    }


def data_confidence_label(data_coverage):
    """Describe how much of the weighted screen had usable source data."""
    if data_coverage >= 85:
        return "HIGH — most weighted checks had usable data"
    if data_coverage >= 70:
        return "MODERATE — some weighted checks were unavailable"
    return "LOW — too much weighted data is missing"


def financial_screen_label(
    score,
    data_coverage,
    high_priority_failures,
    high_priority_missing,
):
    """Describe the financial screen without treating it as investment advice."""
    if score is None:
        return "INCONCLUSIVE — NO USABLE FINANCIAL DATA"
    if data_coverage < 70:
        return "INCONCLUSIVE — TOO MUCH WEIGHTED DATA IS MISSING"
    if high_priority_failures >= 2:
        return "WEAK FINANCIAL FOUNDATION — MULTIPLE CORE CONCERNS"
    if score < 50:
        return "WEAK FINANCIAL FOUNDATION — MORE CONCERNS THAN STRENGTHS"
    if high_priority_missing:
        return "INCOMPLETE FINANCIAL SCREEN — CORE DATA IS MISSING"
    if high_priority_failures:
        return "MIXED FINANCIAL FOUNDATION — A CORE CONCERN NEEDS EXPLAINING"
    if score < 70:
        return "MIXED FINANCIAL FOUNDATION — FURTHER RESEARCH NEEDED"
    if data_coverage < 85:
        return "PROMISING BUT INCOMPLETE — MORE DATA IS NEEDED"
    if score < 85:
        return "GOOD FINANCIAL FOUNDATION — COMPLETE THE INVESTMENT REVIEW"
    return "STRONG FINANCIAL FOUNDATION — COMPLETE THE INVESTMENT REVIEW"


def print_score_group(title, items, item_type):
    """Print one clearly labelled group within the financial-quality score."""
    print(f"\n{title}")

    if not items:
        if item_type == "pass":
            print("  No weighted checks passed with the available data.")
        elif item_type == "concern":
            print("  No weighted checks currently need explaining.")
        else:
            print("  All weighted checks had usable Yahoo Finance data.")
        return

    for item in items:
        check = item["check"]
        priority = item["priority"].title()

        if item_type == "pass":
            points = f"+{item['weight']}/{item['weight']}"
            marker = "PASS"
        elif item_type == "concern":
            points = f" 0/{item['weight']}"
            marker = "WATCH"
        else:
            points = f"--/{item['weight']}"
            marker = "NO DATA"

        print(
            f"  [{marker:7}] {points:>6} pts | {priority:<6} | "
            f"{item['check_name']}"
        )
        print(f"             Why it matters: {item['why']}")

        if item_type == "concern" and check is not None:
            print(f"             {check['reason']}")
        elif item_type == "missing":
            print("             No points awarded or lost; this lowers confidence.")


def print_overall_research_score(data, is_fund):
    """Print a readable, safeguarded financial-quality score."""
    print("\n" + "=" * 68)
    print("FINANCIAL-QUALITY SCORE (COMPANY ONLY)")
    print("=" * 68)

    if is_fund:
        print(
            "Not applicable: this weighted company financial screen does not "
            "suit funds or indexes."
        )
        return

    summary = weighted_financial_score(data)
    score = summary["score"]

    if score is None:
        print("Financial-research score: Not available")
        return

    screen_result = financial_screen_label(
        score,
        summary["data_coverage"],
        summary["high_priority_failures"],
        summary["high_priority_missing"],
    )

    print(f"Financial-quality score: {score:.0f}/100")
    print(f"Financial-screen status: {screen_result}")
    print(
        f"Score calculation: {summary['earned_weight']:.0f} passing points / "
        f"{summary['available_weight']:.0f} points with usable data"
    )
    print(
        f"Data confidence: {data_confidence_label(summary['data_coverage'])} "
        f"({summary['available_weight']:.0f}/{summary['total_weight']:.0f} weighted points available)"
    )
    print(
        "A higher score means more of this script's weighted financial-quality "
        "checks passed. It does not mean the share is automatically a better buy."
    )

    high_priority_concerns = []
    high_priority_missing = []
    passed_items = []
    concern_items = []
    missing_items = []

    for item in summary["results"]:
        if item["result"] is True:
            passed_items.append(item)
        elif item["result"] is False:
            concern_items.append(item)
            if item["priority"] == "HIGH":
                high_priority_concerns.append(item)
        else:
            missing_items.append(item)
            if item["priority"] == "HIGH":
                high_priority_missing.append(item)

    print_score_group("WHAT IS SUPPORTING THE SCORE", passed_items, "pass")
    print_score_group("WHAT NEEDS EXPLAINING", concern_items, "concern")
    print_score_group("WHAT COULD NOT BE SCORED", missing_items, "missing")

    if high_priority_concerns:
        print("\nCORE CONCERNS TO INVESTIGATE")
        for item in high_priority_concerns:
            print(f"- {item['check_name']}: {item['why']}")

    if high_priority_missing:
        print("\nCORE DATA STILL MISSING")
        for item in high_priority_missing:
            print(f"- {item['check_name']}: {item['why']}")

    print(
        "\nSCORE BANDS (only when data confidence is high and there are no "
        "core concerns): below 50 = weak; 50-69 = mixed; 70-84 = good; "
        "85-100 = strong."
    )
    print(
        "Before considering any investment, also review valuation, the latest "
        "official results, competitive risks, management, peer comparisons, "
        "diversification, and your own risk tolerance."
    )

    if str(data.get("sector", "")).upper() in SECTOR_SPECIFIC_SCORE_SECTORS:
        print(
            "Sector caution: banks, insurers, and property companies need "
            "sector-specific measures. Treat this score as preliminary only."
        )


def print_investment_case(data, is_fund):
    """Summarise the main upside, downside, and next research step."""
    print("\n" + "=" * 68)
    print("UPSIDE, DOWNSIDE & RESEARCH OUTCOME")
    print("=" * 68)

    if is_fund:
        print(
            "This company financial screen does not apply to a fund or index. "
            "Research its objective, benchmark, fees, holdings, and risk level "
            "instead."
        )
        return

    summary = weighted_financial_score(data)
    score = summary["score"]

    if score is None:
        print(
            "Research outcome: Inconclusive. Yahoo Finance did not provide "
            "enough usable company financial data for this screen."
        )
        return

    passed_items = sorted(
        (item for item in summary["results"] if item["result"] is True),
        key=lambda item: item["weight"],
        reverse=True,
    )
    concern_items = sorted(
        (item for item in summary["results"] if item["result"] is False),
        key=lambda item: item["weight"],
        reverse=True,
    )
    missing_core_items = [
        item
        for item in summary["results"]
        if item["result"] is None and item["priority"] == "HIGH"
    ]

    print("\nPOTENTIAL UPSIDE — EVIDENCE FROM YOUR CHECKS")
    if passed_items:
        for item in passed_items[:3]:
            print(
                f"- {item['check_name']} passed (+{item['weight']} points): "
                f"{item['why']}."
            )
    else:
        print("- No weighted financial-strength checks passed with the available data.")

    if is_number(data["one_year_return"]) and data["one_year_return"] > 0:
        print(
            f"- Recent price momentum: one-year return is "
            f"{percentage(data['one_year_return'])}. This is historical, not a forecast."
        )

    if trend_label(data) == "Upward":
        print(
            "- Recent trend: the 50-day average is above the 200-day average. "
            "This can change quickly and is not a financial-quality measure."
        )

    print("\nPOTENTIAL DOWNSIDE — EVIDENCE TO INVESTIGATE")
    if concern_items:
        for item in concern_items[:3]:
            print(
                f"- {item['check_name']} did not pass (0/{item['weight']} points): "
                f"{item['why']}."
            )
    else:
        print("- No weighted financial checks failed, but that does not remove investment risk.")

    for item in missing_core_items:
        print(
            f"- Missing core data: {item['check_name']} could not be checked, "
            "so the financial picture is incomplete."
        )

    risk = data["risk"]
    if is_number(risk["maximum_drawdown"]):
        print(
            f"- Historical price risk: the largest fall from a prior peak in the "
            f"last year was {percentage(risk['maximum_drawdown'])}."
        )

    if is_number(data["pe_ratio"]):
        if data["pe_ratio"] > 30:
            print(
                f"- Valuation requires care: the P/E ratio is "
                f"{number_text(data['pe_ratio'])}. Compare it with direct peers "
                "and expected growth before investing."
            )
        elif data["pe_ratio"] <= 0:
            print(
                "- Valuation requires care: a positive P/E ratio is not available, "
                "so this simple valuation comparison is not useful."
            )
    else:
        print("- Valuation is not available from a usable P/E ratio.")

    screen_result = financial_screen_label(
        score,
        summary["data_coverage"],
        summary["high_priority_failures"],
        summary["high_priority_missing"],
    )

    print("\nWHAT YOUR ANALYSIS SIGNALS")
    print(f"- Financial-quality score: {score:.0f}/100")
    print(f"- Status: {screen_result}")

    if (
        score >= 70
        and summary["data_coverage"] >= 85
        and not summary["high_priority_failures"]
        and not summary["high_priority_missing"]
    ):
        print(
            "- Outcome: this is a potential candidate for a valuation and "
            "business-risk review. It is not yet a buy recommendation."
        )
    else:
        print(
            "- Outcome: do not treat this as an investment candidate yet. "
            "First explain the failed checks or obtain the missing data, then "
            "complete valuation and risk research."
        )

    print(
        "- Final step: read the latest annual report and results release, then "
        "compare valuation and financial measures with direct competitors."
    )


def trend_label(data):
    """Return a plain-English moving-average trend summary."""
    if not is_number(data["average_50"]) or not is_number(data["average_200"]):
        return "Not available"
    return "Upward" if data["average_50"] > data["average_200"] else "Downward"


def print_report(data):
    """Print a concise Yahoo Finance research report."""
    risk = data["risk"]
    is_fund = str(data["type"]).upper() in FUND_TYPES

    print("\n" + "=" * 68)
    print(f"{data['name']} ({data['ticker']}) | {data['type']}")
    print("=" * 68)
    print(
        f"Latest Yahoo Finance price: {money(data['latest_price'], data['currency'])}"
        f"  |  {data['latest_time']}"
    )

    print("\nCOMPANY / INVESTMENT OVERVIEW")
    print(f"Sector: {data['sector']}")

    if data["industry"] != "Not available":
        print(f"Industry: {data['industry']}")

    print("What it does:")
    print(short_description(data["description"]))

    print("\nPRICE & MOMENTUM")
    print(
        f"One-year return: {percentage(data['one_year_return'])}"
        f"  |  Trend: {trend_label(data)}"
    )
    print(
        f"50-day average: {money(data['average_50'], data['currency'])}"
        f"  |  200-day average: {money(data['average_200'], data['currency'])}"
    )

    if is_fund:
        print("\nFUND / INDEX NOTE")
        print("Company profit, debt, and P/E checks are not meaningful for this investment type.")
    else:
        print("\nCOMPANY METRICS (YAHOO FINANCE)")
        print(
            f"Profit margin: {percentage(data['profit_margin'])}"
            f"  |  Return on equity: {percentage(data['return_on_equity'])}"
        )
        print(
            f"Revenue growth: {percentage(data['revenue_growth'])}"
            f"  |  Debt to equity: {number_text(data['debt_to_equity'])}"
        )
        print(
            f"P/E ratio: {number_text(data['pe_ratio'])}"
            f"  |  Market value: {money(data['market_cap'], data['currency'])}"
        )

    print("\nRISK (LAST YEAR)")
    print(
        f"Volatility: {percentage(risk['annualised_volatility'])}"
        f"  |  Largest fall: {percentage(risk['maximum_drawdown'])}"
        f"  |  Below one-year high: {percentage(risk['current_drawdown'])}"
    )

    print("\nMARK TILBURY QUANTITATIVE CHECKS")
    if is_fund:
        print("Not applicable: these company financial-statement checks do not suit funds or indexes.")
    else:
        checks = data["tilbury_checks"]
        passed_checks, available_checks = tilbury_score(checks)
        print(
            f"Score: {passed_checks}/3 checks passed"
            f"  |  Data available for {available_checks}/3 checks"
        )

        print("Each check shows: result, pass rule, and explanation.")

        for check in checks:
            print(
                f"\n[{tilbury_marker(check['result']):7}] "
                f"{check['section']} — {check['name']}"
            )
            print(f"          Result: {check['result_value']}")
            print(f"          Pass rule: {check['pass_rule']}")
            print(f"          {check['reason']}")

    print("\nDREW COHEN-INSPIRED FINANCIAL CHECKLIST")
    if is_fund:
        print(
            "Not applicable: this company financial-statement checklist does "
            "not suit funds or indexes."
        )
    else:
        print_drew_checklist(data["drew_checks"])
        print_drew_valuation_step(data)

    print("\nPLAIN BAGEL / RICHARD COFFIN FINANCIAL CHECKLIST")
    if is_fund:
        print(
            "Not applicable: this company financial-statement checklist does "
            "not suit funds or indexes."
        )
    else:
        print_plain_bagel_checklist(data["plain_bagel_checks"])
        print_plain_bagel_valuation_step(data)

    print_overall_research_score(data, is_fund)
    print_investment_case(data, is_fund)

    print(
        "\nThese are simple financial rules of thumb, not a buy or sell "
        "instruction. Read the latest official results before investing."
    )


def research_stock(ticker):
    """Research one stock, fund, ETF, or index."""
    try:
        print_report(get_stock_data(ticker))
    except Exception as error:
        print(f"\nCould not research this ticker: {error}")


def main():
    print("Yahoo Finance Stock Researcher")
    print("Research individual companies or screen live US stock lists.")

    while True:
        print("\n1. Research one ticker")
        print("2. Screen more of Yahoo Finance's current Most Active companies")
        print("3. Screen liquid small / emerging US companies")
        print("4. Screen both live lists together (duplicates removed)")
        print("5. Clear saved screener scores")
        print("Q. Quit")
        choice = input("\nChoose an option: ").strip().lower()

        if choice in {"quit", "exit", "q"}:
            print("Goodbye.")
            break

        if choice == "1":
            ticker = input("\nEnter a ticker such as AAPL, MSFT, GOOGL, or VWRP.L: ")
            research_stock(ticker)
        elif choice in {"2", "3", "4"}:
            run_stock_screener(choice)
        elif choice == "5":
            try:
                SCREEN_CACHE_FILE.unlink(missing_ok=True)
                print("Saved screener scores cleared. The next screen will fetch fresh financial data.")
            except OSError as error:
                print(f"Could not clear the screener cache: {error}")
        else:
            print("Please choose 1, 2, 3, 4, 5, or Q.")


if __name__ == "__main__":
    main()
