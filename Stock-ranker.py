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
        "type": info.get("quoteType", "Unknown"),
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
    }


def calculate_score(data):
    """Calculate a transparent Yahoo Finance research score out of 100."""
    is_fund = str(data["type"]).upper() in FUND_TYPES
    not_applicable = "Not applicable to a fund or index" if is_fund else None

    checks = [
        (
            "50-day average is above 200-day average",
            bool(data["average_50"] > data["average_200"])
            if is_number(data["average_50"])
            and is_number(data["average_200"])
            else None,
            25,
            "Yahoo Finance price history",
        ),
        (
            "One-year price change is positive",
            bool(data["one_year_return"] > 0)
            if is_number(data["one_year_return"])
            else None,
            15,
            "Yahoo Finance price history",
        ),
        (
            "Profit margin is at least 10%",
            bool(number(data["profit_margin"]) >= 0.10)
            if not is_fund and number(data["profit_margin"]) is not None
            else None,
            10,
            not_applicable or "Yahoo Finance",
        ),
        (
            "Return on equity is at least 15%",
            bool(number(data["return_on_equity"]) >= 0.15)
            if not is_fund and number(data["return_on_equity"]) is not None
            else None,
            10,
            not_applicable or "Yahoo Finance",
        ),
        (
            "Debt to equity is no higher than 100",
            bool(number(data["debt_to_equity"]) <= 100)
            if not is_fund and number(data["debt_to_equity"]) is not None
            else None,
            10,
            not_applicable or "Yahoo Finance",
        ),
        (
            "Revenue growth is at least 5%",
            bool(number(data["revenue_growth"]) >= 0.05)
            if not is_fund and number(data["revenue_growth"]) is not None
            else None,
            10,
            not_applicable or "Yahoo Finance",
        ),
        (
            "P/E ratio is between 0 and 30",
            bool(0 < number(data["pe_ratio"]) <= 30)
            if not is_fund and number(data["pe_ratio"]) is not None
            else None,
            10,
            not_applicable or "Yahoo Finance",
        ),
    ]

    available_points = sum(
        points for _, result, points, _ in checks if result is not None
    )
    earned_points = sum(
        points for _, result, points, _ in checks if result is True
    )
    score = (earned_points / available_points * 100) if available_points else None
    return score, checks


def score_marker(result, source):
    """Return a short, readable label for a research check."""
    if source == "Not applicable to a fund or index":
        return "N/A"
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


def next_steps(checks):
    """Return neutral, evidence-led subjects to investigate further."""
    steps = [
        f"Investigate: {description.lower()}."
        for description, result, _, _ in checks
        if result is False
    ]

    if not steps:
        steps.append("Read the latest results and compare the company with similar businesses.")

    return steps[:3]


def print_report(data):
    """Print a concise Yahoo Finance research report."""
    risk = data["risk"]
    score, checks = calculate_score(data)
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

    relevant_checks = sum(
        1
        for _, _, _, source in checks
        if source != "Not applicable to a fund or index"
    )
    checks_with_data = sum(
        1
        for _, result, _, source in checks
        if result is not None and source != "Not applicable to a fund or index"
    )
    score_text = f"{score:.0f}/100" if score is not None else "Not available"

    print("\nRESEARCH SCREEN")
    print(
        f"Score: {score_text}"
        f"  |  Data available for {checks_with_data}/{relevant_checks} relevant checks"
    )

    for description, result, _, source in checks:
        print(f"[{score_marker(result, source):7}] {description} ({source})")

    print("\nWHAT TO CHECK NEXT")
    for step in next_steps(checks):
        print(f"- {step}")

    print(
        "\nThis is a research screen, not a buy or sell instruction. "
        "Read the latest official results before investing."
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