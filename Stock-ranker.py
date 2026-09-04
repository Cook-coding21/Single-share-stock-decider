import yfinance as yf


def money(value):
    """Format a number as dollars, or show Not available."""
    if value is None:
        return "Not available"
    return f"${value:,.2f}"


def percentage(value):
    """Format a decimal as a percentage, or show Not available."""
    if value is None:
        return "Not available"
    return f"{value * 100:.2f}%"


def check_stock(ticker):
    ticker = ticker.strip().upper()
    stock = yf.Ticker(ticker)

    try:
        # Latest available price data from Yahoo Finance
        intraday = stock.history(
            period="5d",
            interval="1m",
            auto_adjust=False,
            prepost=True
        )

        # Daily history for the longer-term trend
        daily = stock.history(period="1y", interval="1d", auto_adjust=True)

        if intraday.empty or daily.empty:
            print("\nNo data was found. Check the ticker symbol and try again.")
            return

        # Latest price and time
        latest_price = intraday["Close"].iloc[-1]
        latest_time = intraday.index[-1]

        # Trend calculations
        daily["50_day_average"] = daily["Close"].rolling(50).mean()
        daily["200_day_average"] = daily["Close"].rolling(200).mean()

        average_50 = daily["50_day_average"].iloc[-1]
        average_200 = daily["200_day_average"].iloc[-1]

        one_year_return = (
            (daily["Close"].iloc[-1] / daily["Close"].iloc[0]) - 1
        ) * 100

        # Company information from Yahoo Finance
        info = stock.info
        company_name = info.get("longName", ticker)

        print("\n" + "=" * 45)
        print(f"{company_name} ({ticker})")
        print("=" * 45)

        print("\nLatest available price")
        print(f"Price: {money(latest_price)}")
        print(f"Timestamp: {latest_time}")

        print("\nPrice trend")
        print(f"One-year price change: {one_year_return:.2f}%")
        print(f"50-day average: {money(average_50)}")
        print(f"200-day average: {money(average_200)}")

        if average_50 > average_200:
            print("Trend result: The recent price trend is upward.")
        else:
            print("Trend result: The recent price trend is downward.")

        print("\nCompany figures")
        print(f"Market value: {money(info.get('marketCap'))}")
        print(f"P/E ratio: {info.get('trailingPE', 'Not available')}")
        print(f"Profit margin: {percentage(info.get('profitMargins'))}")
        print(f"Return on equity: {percentage(info.get('returnOnEquity'))}")
        print(f"Revenue growth: {percentage(info.get('revenueGrowth'))}")

        debt_to_equity = info.get("debtToEquity")
        if debt_to_equity is None:
            print("Debt to equity: Not available")
        else:
            print(f"Debt to equity: {debt_to_equity:.2f}")

        print("\nThis is research information, not a buy or sell recommendation.")

    except Exception as error:
        print(f"\nCould not retrieve data: {error}")


def main():
    print("Yahoo Finance Stock Checker")
    print("Type a ticker such as AAPL, MSFT, or GOOGL.")
    print("Type 'quit' to close the program.")

    while True:
        ticker = input("\nWhich stock would you like to check? ")

        if ticker.strip().lower() in {"quit", "exit", "q"}:
            print("Goodbye.")
            break

        check_stock(ticker)


if __name__ == "__main__":
    main()