"""
Yahoo Finance Stock Researcher

This script uses Yahoo Finance only. It is a research tool, not a buy or sell
recommendation.
"""

import math

import yfinance as yf


FUND_TYPES = {"ETF", "MUTUALFUND", "INDEX"}


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
        cash_flow_result = bool(latest_free_cash_flow > previous_free_cash_flow)
        cash_flow_value = (
            f"Latest: {money(latest_free_cash_flow, currency)} "
            f"({period_text(latest_period)}) | Previous: "
            f"{money(previous_free_cash_flow, currency)} "
            f"({period_text(previous_period)})"
        )
        cash_flow_reason = (
            "Pass: latest annual free cash flow is higher than the previous year."
            if cash_flow_result
            else "Needs review: latest annual free cash flow did not increase."
        )

        if latest_free_cash_flow < 0:
            cash_flow_reason += " Latest free cash flow is negative."

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
            "pass_rule": "Latest annual free cash flow is higher than the previous year",
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


def cagr_check(section, name, what_it_analyses, values, currency, measure_name):
    """Build an annualised-growth check using the longest Yahoo history available."""
    latest, earlier = values

    if latest is None or earlier is None:
        return {
            "section": section,
            "name": name,
            "what_it_analyses": what_it_analyses,
            "result": None,
            "result_value": "Not available",
            "pass_rule": "Positive annualised growth across the available annual history",
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
            "pass_rule": "Positive annualised growth across the available annual history",
            "reason": (
                f"{measure_name} CAGR is not meaningful when a comparison figure "
                "is zero or negative."
            ),
        }

    cagr = (latest_value / earlier_value) ** (1 / years) - 1
    result = bool(cagr > 0)
    history_description = f"{years:.1f} years of available annual history"

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
        "pass_rule": "Positive annualised growth across the available annual history",
        "reason": (
            f"Favourable: {measure_name} has grown across the available annual history."
            if result
            else f"Needs review: {measure_name} has shrunk across the available annual history."
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
            "pass_rule": "Average annual return on ending equity is positive",
            "reason": "Yahoo Finance did not provide matching annual net-income and shareholder-equity figures.",
        }
    else:
        average_roe = sum(value for _, value in annual_roe_values) / len(annual_roe_values)
        roe_history_result = bool(average_roe > 0)
        return_on_equity_history = {
            "section": "INCOME STATEMENT + BALANCE SHEET",
            "name": "Return on equity history",
            "what_it_analyses": "Whether the company has produced positive profit relative to shareholder equity across the available annual history.",
            "result": roe_history_result,
            "result_value": (
                f"Average: {percentage(average_roe)} across "
                f"{len(annual_roe_values)} annual periods"
            ),
            "pass_rule": "Average annual return on ending equity is positive",
            "reason": (
                "Favourable: the company has generated a positive average return on shareholder equity."
                if roe_history_result
                else "Needs review: the company has not generated a positive average return on shareholder equity."
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


def overall_score_percentage(checks):
    """Return the percentage of passed checks among checks with usable data."""
    passed_checks, available_checks = tilbury_score(checks)

    if not available_checks:
        return None, passed_checks, available_checks

    return (passed_checks / available_checks) * 100, passed_checks, available_checks


def print_overall_research_score(data, is_fund):
    """Print a transparent summary without presenting it as a buy recommendation."""
    print("\nOVERALL FINANCIAL-RESEARCH SUMMARY")

    if is_fund:
        print(
            "Not applicable: the three company financial-statement frameworks "
            "do not suit funds or indexes."
        )
        return

    frameworks = [
        ("Mark Tilbury", data["tilbury_checks"]),
        ("Drew Cohen", data["drew_checks"]),
        ("Plain Bagel", data["plain_bagel_checks"]),
    ]
    usable_frameworks = []

    for name, checks in frameworks:
        score, passed_checks, available_checks = overall_score_percentage(checks)

        if score is None:
            print(f"{name}: No score — Yahoo Finance data was unavailable.")
            continue

        usable_frameworks.append(score)
        print(
            f"{name}: {score:.0f}/100 "
            f"({passed_checks}/{available_checks} available checks favourable)"
        )

    if not usable_frameworks:
        print("Overall financial-research score: Not available")
        return

    overall_score = sum(usable_frameworks) / len(usable_frameworks)
    print(f"\nOverall financial-research score: {overall_score:.0f}/100")
    print(
        "Calculation: equal-weight average of the available framework percentages. "
        "The frameworks overlap, so this is a research summary—not a buy signal."
    )
    print(
        "Business quality, strategy, peer comparison, valuation, and your risk "
        "tolerance still require manual review."
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
