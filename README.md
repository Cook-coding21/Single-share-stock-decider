Yahoo Finance Stock Researcher

A simple Python research tool for stocks, ETFs, index funds, and indexes. Enter a ticker symbol and the program creates a readable report using data returned by Yahoo Finance.

This project is for research and learning. It does not give buy or sell instructions.

What the program does

For a ticker such as AAPL, MSFT, GOOGL, or 0P00013P6I.L, the program:

Asks which investment you want to research.

Retrieves up to two years of daily Yahoo Finance price history.

Uses the latest available one-minute price data when Yahoo Finance provides it; otherwise, it uses the latest daily price.

Shows the latest price and its timestamp.

Calculates the one-year price change.

Calculates 50-day and 200-day moving averages.

Labels the moving-average trend as Upward or Downward.

Shows company figures where they are available:

market value

P/E ratio

profit margin

return on equity

revenue growth

debt to equity

Calculates simple historical-risk observations from the last year of prices:

annualised volatility

largest fall from an earlier high (maximum drawdown)

current distance below the one-year high

Produces a transparent research score and shows exactly which checks passed, need attention, or have no data.

Suggests neutral topics to investigate next, based on checks that did not pass.

For ETFs, mutual funds, and indexes, company-specific measures such as profit margin, debt, and P/E are marked as not applicable. The price, trend, risk, and price-based score checks still work.

Research score

The score is a screening aid, not an investment recommendation. It is based on these checks:

Check

Points

50-day average above 200-day average

25

Positive one-year price change

15

Profit margin of at least 10%

10

Return on equity of at least 15%

10

Debt to equity no higher than 100

10

Revenue growth of at least 5%

10

P/E ratio between 0 and 30

10

If Yahoo Finance does not have a figure, the program shows NO DATA and leaves that check out of the calculation. This prevents missing figures from being treated as failures. For funds and indexes, the company-only checks are excluded.

Requirements

Python 3

Internet connection

The yfinance package

This version uses Yahoo Finance only. It does not need an Alpha Vantage account or API key.

Installation

Open the project folder in PyCharm. In PyCharm's Terminal, create a virtual environment and install the project packages:

python -m venv .venv
python -m pip install -r requirements.txt

If you do not have a requirements.txt file yet, install the required package with:

python -m pip install yfinance

Then create requirements.txt if needed:

python -m pip freeze > requirements.txt

Running the program

In PyCharm, right-click Stock-ranker.py and choose Run.

Or, from the Terminal:

python Stock-ranker.py

When prompted, enter a ticker symbol:

Which investment would you like to research? AAPL

Enter quit, q, or exit to close the program.

Understanding the report

Price & momentum

Latest price: the most recent price Yahoo Finance returned, with its timestamp.

One-year return: the percentage change over roughly the last 252 trading days.

50-day / 200-day averages: average closing prices over those periods.

Trend: upward when the 50-day average is above the 200-day average; otherwise downward.

Company metrics

P/E ratio: share price compared with earnings per share.

Profit margin: the share of revenue kept as profit.

Return on equity: profit relative to shareholder equity.

Revenue growth: Yahoo Finance's reported revenue-growth measure.

Debt to equity: debt compared with shareholder equity.

Risk

Volatility: how widely daily prices have moved over the last year. It is not a forecast.

Largest fall: the worst fall from a previous high during the last year.

Below one-year high: how far the latest price is below the highest price in that period.

Important limits

Yahoo Finance may provide delayed rather than real-time prices. Always check the timestamp.

One-minute data is often unavailable for funds, indexes, or some exchanges; the program will use the latest daily value instead.

Company figures do not update every minute. They typically change when new financial results are reported.

A score does not tell you whether to invest. Compare similar investments, review the latest official company or fund documents, and consider your own goals and risk tolerance.

Project files

Stock-ranker.py     Main program
requirements.txt    Python packages needed to run the program
.gitignore          Files Git should not upload
README.md           Project guide

Keeping the project safe on GitHub

Commit Stock-ranker.py, requirements.txt, .gitignore, and this README to GitHub. Do not commit .venv/, because it is a local Python environment that can be recreated from requirements.txt.
