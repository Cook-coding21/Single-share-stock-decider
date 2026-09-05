import math
import yfinance as yf


def is_number(value):
    """Return True only for usable numeric values."""
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def money(value, currency="$"):
    if not is_number(value):
        return "Not available"
    return f"{currency}{float(value):,.2f}"


def percentage(value):
    if not is_number(value):
        return "Not available"
    return f"{float(value) * 100:.2f}%"


def safe_info(stock):
    """Get Yahoo Finance company data without stopping the program if it fails."""
    try:
        return stock.info
    except Exception:
        return {}


def get_stock_data(ticker):
    """Retrieve price history and company data for one ticker."""
    ticker = ticker.strip().upper()

    if not ticker:
        raise ValueError("Please enter a ticker symbol.")

    stock = yf.Ticker(ticker)

    # Daily history is used for one-year performance and moving averages.
    daily = stock.history(period="1y", interval="1d", auto_adjust=True)

    if daily.empty:
        raise ValueError("No daily price data was found. Check the ticker symbol.")

    # One-minute data is used where Yahoo Finance makes it available.
    intraday = stock.history(
        period="5d",
        interval="1m",
        auto_adjust=False,
        prepost=True
    )

    info = safe_info(stock)
    currency = info.get("currency", "$")

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

    one_year_return = (
        (daily_close.iloc[-1] / daily_close.iloc[0]) - 1
        if len(daily_close) >= 2
        else None
    )

    return {
        "ticker": ticker,
        "name": info.get("longName", info.get("shortName", ticker)),
        "type": info.get("quoteType", "Unknown"),
        "sector": info.get("sector", "Not available"),
        "industry": info.get("industry", "Not available"),
        "summary": info.get("longBusinessSummary", "Not available"),
        "currency": currency,
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
    }


def calculate_score(data):
    """
    Produce a transparent research score out of 100.
    Missing figures are ignored rather than treated as failures.
    """
    checks = [
        ("50-day average above 200-day average",
         data["average_50"] > data["average_200"]
         if is_number(data["average_50"]) and is_number(data["average_200"])
         else None, 25),

        ("Positive one-year price change",
         data["one_year_return"] > 0
         if is_number(data["one_year_return"])
         else None, 15),

        ("Profit margin of at least 10%",
         data["profit_margin"] >= 0.10
         if is_number(data["profit_margin"])
         else None, 10),

        ("Return on equity of at least 15%",
         data["return_on_equity"] >= 0.15
         if is_number(data["return_on_equity"])
         else None, 10),

        ("Debt-to-equity no higher than 100",
         data["debt_to_equity"] <= 100
         if is_number(data["debt_to_equity"])
         else None, 10),

        ("Revenue growth of at least 5%",
         data["revenue_growth"] >= 0.05
         if is_number(data["revenue_growth"])
         else None, 10),

        ("P/E ratio between 0 and 30",
         0 < data["pe_ratio"] <= 30
         if is_number(data["pe_ratio"])
         else None, 10),
    ]

    available_points = sum(points for _, result, points in checks if result is not None)
    earned_points = sum(points for _, result, points in checks if result is True)

    score = (earned_points / available_points * 100) if available_points else 0
    return score, checks


def research_stock(ticker):
    """Print a detailed research report for one stock, ETF, index, or fund."""
    try:
        data = get_stock_data(ticker)
        score, checks = calculate_score(data)

        print("\n" + "=" * 60)
        print(f"{data['name']} ({data['ticker']})")
        print("=" * 60)

        print(f"Type: {data['type']}")
        print(f"Sector: {data['sector']}")
        print(f"Industry: {data['industry']}")

        print("\nLatest available Yahoo Finance price")
        print(f"Price: {money(data['latest_price'], data['currency'])}")
        print(f"Timestamp: {data['latest_time']}")

        print("\nPrice trend")
        print(f"One-year price change: {percentage(data['one_year_return'])}")
        print(f"50-day average: {money(data['average_50'], data['currency'])}")
        print(f"200-day average: {money(data['average_200'], data['currency'])}")

        if is_number(data["average_50"]) and is_number(data["average_200"]):
            if data["average_50"] > data["average_200"]:
                print("Trend: Recent price trend is upward.")
            else:
                print("Trend: Recent price trend is downward.")

        print("\nCompany figures")
        print(f"Market value: {money(data['market_cap'], data['currency'])}")
        print(f"P/E ratio: {data['pe_ratio'] if is_number(data['pe_ratio']) else 'Not available'}")
        print(f"Profit margin: {percentage(data['profit_margin'])}")
        print(f"Return on equity: {percentage(data['return_on_equity'])}")
        print(f"Revenue growth: {percentage(data['revenue_growth'])}")

        if is_number(data["debt_to_equity"]):
            print(f"Debt to equity: {float(data['debt_to_equity']):.2f}")
        else:
            print("Debt to equity: Not available")

        print(f"\nResearch score: {score:.0f}/100")
        print("Score checks:")

        for description, result, _ in checks:
            if result is True:
                status = "Pass"
            elif result is False:
                status = "Does not meet"
            else:
                status = "No data"

            print(f"- {description}: {status}")

        if data["summary"] != "Not available":
            print("\nAbout the business")
            print(data["summary"][:600] + ("..." if len(data["summary"]) > 600 else ""))

        print("\nThis is a research tool, not a buy or sell recommendation.")

    except Exception as error:
        print(f"\nCould not research this ticker: {error}")


def rank_stocks(tickers):
    """Rank a list of tickers using the same visible research score."""
    results = []

    for ticker in tickers:
        try:
            data = get_stock_data(ticker)
            score, _ = calculate_score(data)
            data["score"] = score
            results.append(data)
        except Exception as error:
            print(f"\nCould not add {ticker.upper()}: {error}")

    if not results:
        print("\nNo stocks could be ranked.")
        return

    results.sort(key=lambda stock: stock["score"], reverse=True)

    print("\n" + "=" * 90)
    print("Stock research ranking")
    print("=" * 90)
    print(f"{'Rank':<6}{'Ticker':<10}{'Score':<10}{'1-year return':<16}{'Trend':<12}Name")
    print("-" * 90)

    for rank, stock in enumerate(results, start=1):
        trend = "N/A"

        if is_number(stock["average_50"]) and is_number(stock["average_200"]):
            trend = "Upward" if stock["average_50"] > stock["average_200"] else "Downward"

        print(
            f"{rank:<6}"
            f"{stock['ticker']:<10}"
            f"{stock['score']:<10.0f}"
            f"{percentage(stock['one_year_return']):<16}"
            f"{trend:<12}"
            f"{stock['name']}"
        )

    print("\nCompare similar types of investment where possible.")
    print("For example, compare companies with companies—not individual shares with index funds.")


def main():
    print("Yahoo Finance Stock Researcher")
    print("The program uses the latest data Yahoo Finance provides.")
    print("Company figures update less often than prices.")

    while True:
        print("\n1. Research one stock, fund, ETF, or index")
        print("2. Rank several tickers")
        print("3. Quit")

        choice = input("\nChoose an option (1-3): ").strip()

        if choice == "1":
            ticker = input("Enter a ticker, for example AAPL or 0P00013P6I.L: ")
            research_stock(ticker)

        elif choice == "2":
            entered_tickers = input(
                "Enter tickers separated by commas, for example AAPL, MSFT, GOOGL: "
            )

            tickers = [
                ticker.strip().upper()
                for ticker in entered_tickers.split(",")
                if ticker.strip()
            ]

            if len(tickers) < 2:
                print("Please enter at least two tickers to rank.")
            else:
                rank_stocks(tickers)

        elif choice in {"3", "q", "quit", "exit"}:
            print("Goodbye.")
            break

        else:
            print("Please choose 1, 2, or 3.")


if __name__ == "__main__":
    main()

#checking restoration