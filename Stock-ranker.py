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
