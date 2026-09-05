# Yahoo Finance Stock Researcher

A simple Python research tool for stocks, ETFs, index funds, and indexes. Enter a ticker symbol and the program creates a readable report using data returned by Yahoo Finance.

This project is for research and learning. It does **not** give buy or sell instructions.

## What the program does

For a ticker such as `AAPL`, `MSFT`, `GOOGL`, or `0P00013P6I.L`, the program:

- Asks which investment you want to research.
- Retrieves up to two years of daily Yahoo Finance price history.
- Uses the latest available one-minute price data when Yahoo Finance provides it; otherwise, it uses the latest daily price.
- Shows the latest price and its timestamp.
- Calculates the one-year price change.
- Calculates 50-day and 200-day moving averages.
- Labels the moving-average trend as **Upward** or **Downward**.
- Shows company figures where they are available:
  - market value
  - P/E ratio
  - profit margin
  - return on equity
  - revenue growth
  - debt to equity
- Calculates simple historical-risk observations from the last year of prices:
  - annualised volatility
  - largest fall from an earlier high (maximum drawdown)
  - current distance below the one-year high
- Retrieves annual balance-sheet, income-statement, and cash-flow data where Yahoo Finance provides it.
- Produces a three-check quantitative financial score based on the rules of thumb discussed by Mark Tilbury.
- Produces a separate seven-check financial screen inspired by Drew Cohen's research process, followed by a manual valuation step.

For ETFs, mutual funds, and indexes, company-specific measures such as profit margin, debt, and P/E are marked as not applicable. The Mark Tilbury and Drew Cohen financial-statement checks are also not used, because they are designed for individual companies.

## Mark Tilbury quantitative checks

The score is a screening aid, not an investment recommendation. It shows how many of these three financial checks passed:

| Check | Calculation | Pass rule |
| --- | --- | --- |
| Current ratio | Current assets ÷ current liabilities | Above 1.00 |
| Operating margin | Operating income ÷ total revenue | Above 15.00% |
| Free-cash-flow trend | Latest annual free cash flow compared with the previous annual figure | Latest figure is higher |

The output shows a score such as `2/3 checks passed`. Each line is labelled **Balance Sheet**, **Income Statement**, or **Cash Flow Statement**, and then shows the result, the pass rule, and a plain-English reason for the pass, review flag, or missing data. If Yahoo Finance does not provide enough annual financial data, the check shows **NO DATA** rather than failing. The existing price, trend, P/E, debt, and risk figures remain in the report, but they do **not** affect this score.

## Drew Cohen-inspired financial checklist

This is a first-pass screen based on the financial signals discussed in Drew Cohen's stock-research process. The video does not provide fixed buy thresholds, so the program marks simple, observable signs as favourable or needing review; it does not treat this as a buy score.

| Financial statement area | Check | What it analyses | Favourable result in this screen |
| --- | --- | --- | --- |
| Income Statement | Revenue trend | Whether sales are growing | Latest annual revenue is higher than an earlier annual figure |
| Income Statement | Operating profitability | Whether the core business makes an operating profit | Latest annual operating income is positive |
| Income Statement | Operating income trend | Whether core-business profit is improving | Latest annual operating income is higher than an earlier annual figure |
| Balance Sheet | Cash versus total debt | Whether reported cash covers reported debt | Cash is at least as high as total debt |
| Cash Flow Statement | Operating cash flow | Whether the business itself generates cash | Latest annual operating cash flow is positive |
| Cash Flow Statement | Free cash flow after capital expenditure | Whether cash remains after investment spending | Latest annual free cash flow is positive |
| Cash Flow Statement | Stock-based compensation trend | Whether employee share awards are increasing dilution risk | Stock-based compensation is the same or a smaller share of revenue than an earlier year |

Every line states what it analyses, the result, the favourable result, and a plain-English explanation. **NO DATA** means Yahoo Finance did not return the annual figures needed for that check.

### Valuation is a separate manual step

The program displays the current P/E and market value but deliberately does not give them a pass or fail. To follow the valuation part of the process, make conservative revenue, earnings, and cash-flow forecasts for up to three years and then use a DCF or reverse DCF. A high financial-screening score alone is not a buy signal.

## Requirements

- Python 3
- Internet connection
- The `yfinance` package

This version uses **Yahoo Finance only**. It does not need an Alpha Vantage account or API key.

## Installation

Open the project folder in PyCharm. In PyCharm's Terminal, create a virtual environment and install the project packages:

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

If you do not have a `requirements.txt` file yet, install the required package with:

```bash
python -m pip install yfinance
```

Then create `requirements.txt` if needed:

```bash
python -m pip freeze > requirements.txt
```

## Running the program

In PyCharm, right-click `Stock-ranker.py` and choose **Run**.

Or, from the Terminal:

```bash
python Stock-ranker.py
```

When prompted, enter a ticker symbol:

```text
Which investment would you like to research? AAPL
```

Enter `quit`, `q`, or `exit` to close the program.

## Understanding the report

### Price & momentum

- **Latest price**: the most recent price Yahoo Finance returned, with its timestamp.
- **One-year return**: the percentage change over roughly the last 252 trading days.
- **50-day / 200-day averages**: average closing prices over those periods.
- **Trend**: upward when the 50-day average is above the 200-day average; otherwise downward.

### Company metrics

- **P/E ratio**: share price compared with earnings per share.
- **Profit margin**: the share of revenue kept as profit.
- **Return on equity**: profit relative to shareholder equity.
- **Revenue growth**: Yahoo Finance's reported revenue-growth measure.
- **Debt to equity**: debt compared with shareholder equity.

### Risk

- **Volatility**: how widely daily prices have moved over the last year. It is not a forecast.
- **Largest fall**: the worst fall from a previous high during the last year.
- **Below one-year high**: how far the latest price is below the highest price in that period.

### Mark Tilbury quantitative checks

- **Current ratio**: whether the company had enough current assets to cover current liabilities in the latest annual report.
- **Operating margin**: the share of revenue remaining after operating costs in the latest annual report.
- **Free-cash-flow trend**: whether annual free cash flow increased compared with the previous annual report. A negative latest free-cash-flow figure is highlighted for review.

## Important limits

- Yahoo Finance may provide delayed rather than real-time prices. Always check the timestamp.
- One-minute data is often unavailable for funds, indexes, or some exchanges; the program will use the latest daily value instead.
- Company figures do not update every minute. They typically change when new financial results are reported.
- Yahoo Finance may not provide annual financial statements for every ticker, especially funds, indexes, or some international listings. In that case, a quantitative check will show **NO DATA**.
- A score does not tell you whether to invest. Compare similar investments, review the latest official company or fund documents, and consider your own goals and risk tolerance.

## Project files

```text
Stock-ranker.py     Main program
requirements.txt    Python packages needed to run the program
.gitignore          Files Git should not upload
README.md           Project guide
```

## Keeping the project safe on GitHub

Commit `Stock-ranker.py`, `requirements.txt`, `.gitignore`, and this README to GitHub. Do not commit `.venv/`, because it is a local Python environment that can be recreated from `requirements.txt`.
