"""
Yahoo Finance Stock Researcher

This script uses Yahoo Finance only. It is a research tool, not a buy or sell
recommendation.
"""

import math

import yfinance as yf


FUND_TYPES = {"ETF", "MUTUALFUND", "INDEX"}
SECTOR_SPECIFIC_SCORE_SECTORS = {"FINANCIAL SERVICES", "REAL ESTATE"}


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
    print("Type a ticker such as AAPL, MSFT, GOOGL, or 0P00013P6I.L.")
    print("Type 'quit' to close the program.")

    while True:
        ticker = input("\nWhich investment would you like to research? ")

        if ticker.strip().lower() in {"quit", "exit", "q"}:
            print("Goodbye.")
            break

        research_stock(ticker)


if __name__ == "__main__":
    main()