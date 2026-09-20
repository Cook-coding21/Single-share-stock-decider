# Run the Stock Researcher in Streamlit

This dashboard keeps the calculations from your existing stock ranker and
displays them in a browser-based interface.

## Files to place in the same PyCharm project folder

```text
Stock-ranker.py        Your complete original stock-ranker code
                       (or Stock-ranker-valuations.py)
app.py                 The new Streamlit dashboard
requirements.txt       The packages to install
```

Your ranker file must be the complete latest version of the original code. Do
not paste only part of it into the file. The dashboard recognises either
`Stock-ranker.py` or `Stock-ranker-valuations.py` automatically.

## Install the packages

Open **Terminal** at the bottom of PyCharm. In your project folder, run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If your virtual environment has a different name, choose the interpreter shown
in PyCharm’s bottom-right corner and use its Python executable instead.

## Start the dashboard

In the same PyCharm Terminal, run:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Do not use the normal green Python **Run** button for `app.py`. Streamlit starts
a local server and opens the dashboard in a browser. If a browser does not open,
copy the `Local URL` shown in the Terminal into your browser.

## What the dashboard includes

- Individual-company research with current price, price chart, one-year return,
  trend, company metrics and historical risk.
- DCF, dividend and asset valuation views, plus the same under-/fair-/over-
  valued verdict from the original code.
- Quick upside/downside summary.
- Mark Tilbury, Drew Cohen-inspired and Plain Bagel / Richard Coffin checklists.
- Weighted financial-quality score and data coverage.
- Direct-peer comparison using P/E, EV/EBITDA, PEG and price-to-book.
- Yahoo Finance Most Active, small/emerging and combined live screens.
- Six-hour annual-financial-data cache, live quote refresh and a CSV download of
  screener results.

## Common problems

### `ModuleNotFoundError: No module named 'streamlit'`

Run the installation command again in the same PyCharm Terminal:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### The dashboard says the original code is missing or too old

Make sure the complete original script is in the same folder and is called
`Stock-ranker.py` or `Stock-ranker-valuations.py`. It must contain the current
valuation and screener functions, not an earlier short version of the ranker.

### The screener takes a long time

This is expected on the first run because Yahoo Finance annual statements are
checked for many companies. Later runs reuse financial scores for up to six
hours; live price and volume fields still refresh every time.
