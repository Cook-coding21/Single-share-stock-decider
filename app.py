"""Streamlit dashboard for the Yahoo Finance Stock Researcher.

Keep this file in the same folder as the complete Stock-ranker.py file, then
start it with: python -m streamlit run app.py
"""

import importlib.util
import time
from pathlib import Path
from statistics import median

import pandas as pd
import streamlit as st
import yfinance as yf


st.set_page_config(
    page_title="Stock Researcher",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
        .block-container {max-width: 1400px; padding-top: 2rem;}
        div[data-testid="stMetric"] {
            background: #101827;
            border: 1px solid #26344d;
            border-radius: 12px;
            padding: 0.8rem;
        }
        div[data-testid="stMetricLabel"] {color: #c7d2e5;}
        div[data-testid="stMetricValue"] {color: #ffffff;}
    </style>
    """,
    unsafe_allow_html=True,
)


REQUIRED_LOGIC_FUNCTIONS = {
    "get_stock_data",
    "calculate_valuation_models",
    "valuation_verdict",
    "weighted_financial_score",
    "get_most_active_quotes",
    "get_emerging_stock_quotes",
    "make_screen_record",
    "load_screen_cache",
    "save_screen_cache",
    "update_record_with_live_quote",
}


@st.cache_resource
def load_stock_logic():
    """Load the existing research engine without running its terminal menu."""
    candidates = [
        Path(__file__).with_name("Stock-ranker.py"),
        Path(__file__).with_name("Stock-ranker-valuations.py"),
    ]
    errors = []

    for script_path in candidates:
        if not script_path.exists():
            continue

        try:
            spec = importlib.util.spec_from_file_location(
                f"stock_logic_{script_path.stem.replace('-', '_')}",
                script_path,
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as error:
            errors.append(f"{script_path.name}: {error}")
            continue

        missing = [
            function_name
            for function_name in REQUIRED_LOGIC_FUNCTIONS
            if not hasattr(module, function_name)
        ]
        if not missing:
            return module, script_path.name

        errors.append(
            f"{script_path.name}: this is an older version and is missing "
            f"{', '.join(missing[:3])}."
        )

    detail = "\n".join(errors) or "No Stock-ranker.py file was found."
    raise RuntimeError(
        "Put this app.py file beside the complete current Stock-ranker.py file.\n"
        + detail
    )


def clean_ticker_list(logic, text, excluded_ticker=None):
    """Parse up to six distinct peer tickers from a text field."""
    peer_tickers = []
    for raw_ticker in text.split(","):
        ticker = logic.normalise_yahoo_ticker(raw_ticker)
        if (
            ticker
            and ticker != excluded_ticker
            and ticker not in peer_tickers
        ):
            peer_tickers.append(ticker)

    return peer_tickers[:6]


def display_status(label, detail=None):
    """Display a report status with a calm, meaningful colour."""
    if label == "POTENTIALLY UNDERVALUED":
        st.success(label.replace("POTENTIALLY ", "Potentially ").title())
    elif label == "POTENTIALLY OVERVALUED":
        st.warning(label.replace("POTENTIALLY ", "Potentially ").title())
    elif label == "ROUGHLY FAIRLY VALUED":
        st.info(label.title())
    else:
        st.info(label.replace("_", " ").title())

    if detail:
        st.caption(detail)


def check_dataframe(logic, checks):
    """Convert a framework checklist into a clear, sortable table."""
    rows = []
    for check in checks:
        rows.append(
            {
                "Status": logic.tilbury_marker(check["result"]),
                "Check": check["name"],
                "Result": check["result_value"],
                "Pass rule": check["pass_rule"],
                "Explanation": check["reason"],
            }
        )
    return pd.DataFrame(rows)


def score_dataframe(logic, summary):
    """Show every item that contributes to the weighted quality score."""
    rows = []
    for item in summary["results"]:
        check = item["check"]
        rows.append(
            {
                "Status": logic.tilbury_marker(item["result"]),
                "Framework": item["framework"],
                "Check": item["check_name"],
                "Weight": item["weight"],
                "Priority": item["priority"].title(),
                "Why it matters": item["why"],
                "Detail": check["reason"] if check is not None else "No usable data.",
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(ttl=300, show_spinner=False)
def price_history(ticker):
    """Get chart history separately from the richer research calculation."""
    history = yf.Ticker(ticker).history(
        period="1y",
        interval="1d",
        auto_adjust=True,
    )
    return history[["Close"]] if not history.empty else pd.DataFrame()


def peer_comparison(logic, data, peer_text):
    """Replicate the terminal peer-multiple comparison in a dashboard table."""
    peer_tickers = clean_ticker_list(logic, peer_text, data["ticker"])
    if not peer_tickers:
        return None, [], []

    peer_metrics = []
    warnings = []
    for ticker in peer_tickers:
        try:
            info = logic.safe_info(yf.Ticker(ticker))
            if str(info.get("quoteType", "")).upper() in logic.FUND_TYPES:
                warnings.append(f"{ticker} was skipped because it is a fund or index.")
                continue

            metrics = logic.relative_valuation_metrics(info)
            if any(
                value is not None and value > 0
                for value in metrics.values()
            ):
                peer_metrics.append((ticker, metrics))
            else:
                warnings.append(f"{ticker} did not return usable peer multiples.")
        except Exception:
            warnings.append(f"{ticker} could not be loaded.")

    if not peer_metrics:
        return None, [], warnings

    target_metrics = logic.target_relative_valuation_metrics(data)
    rows = []
    for metric_name, target_value in target_metrics.items():
        peer_values = [
            metrics[metric_name]
            for _, metrics in peer_metrics
            if logic.is_number(metrics.get(metric_name))
            and metrics[metric_name] > 0
        ]

        if not logic.is_number(target_value) or not peer_values:
            rows.append(
                {
                    "Multiple": metric_name,
                    "This company": "n/a",
                    "Peer median": "n/a",
                    "Difference": "Not enough comparable data",
                }
            )
            continue

        peer_median = median(peer_values)
        difference = (target_value / peer_median) - 1
        position = "below" if difference < 0 else "above"
        rows.append(
            {
                "Multiple": metric_name,
                "This company": round(target_value, 2),
                "Peer median": round(peer_median, 2),
                "Difference": (
                    f"{logic.percentage(abs(difference))} {position} peer median"
                ),
            }
        )

    return pd.DataFrame(rows), [ticker for ticker, _ in peer_metrics], warnings


def investment_case(logic, data, valuation, summary):
    """Return the same concise upside/downside evidence as the terminal report."""
    positives = []
    risks = []

    if summary is None or summary["score"] is None:
        return positives, ["Not enough usable company financial data for a quality score."]

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

    dcf = valuation.get("dcf", {})
    if dcf.get("available"):
        base_value = dcf["scenarios"]["Base"]["value_per_share"]
        base_gap = logic.valuation_difference(base_value, data["latest_price"])
        if base_gap is not None and base_gap > 0:
            positives.append(
                "Base DCF value is "
                f"{logic.percentage(base_gap)} above the current price, if the cash-flow forecast happens."
            )
        elif base_gap is not None and base_gap < 0:
            risks.append(
                "Base DCF value is "
                f"{logic.percentage(abs(base_gap))} below the current price; future growth would need to beat the base model."
            )

    for item in passed_items[:2]:
        positives.append(f"{item['check_name']}: {item['why']}.")
    for item in concern_items[:2]:
        risks.append(f"{item['check_name']}: {item['why']}.")
    for item in missing_core_items[:1]:
        risks.append(
            f"Missing core evidence: {item['check_name']} could not be checked."
        )

    if logic.trend_label(data) == "Upward":
        positives.append("Price trend is upward: the 50-day average is above the 200-day average.")

    maximum_drawdown = data["risk"].get("maximum_drawdown")
    if logic.is_number(maximum_drawdown):
        risks.append(
            "Largest fall from a prior high in the last year: "
            f"{logic.percentage(maximum_drawdown)}."
        )

    if not positives:
        positives.append("No major financial strengths could be confirmed from the available data.")
    if not risks:
        risks.append("No weighted checks failed, but business and valuation risk still remain.")

    return positives, risks


def render_overview(logic, data, is_fund, summary):
    """Render company background, live-style metrics and a price chart."""
    chart_column, detail_column = st.columns([1.65, 1])

    with chart_column:
        st.subheader("One-year price history")
        history = price_history(data["ticker"])
        if history.empty:
            st.info("Yahoo Finance did not return chart data for this ticker.")
        else:
            st.line_chart(history, height=300)

    with detail_column:
        st.subheader("Company overview")
        st.write(f"**Type:** {data['type']}")
        st.write(f"**Sector:** {data['sector']}")
        st.write(f"**Industry:** {data['industry']}")
        st.write(f"**Trend:** {logic.trend_label(data)}")
        st.write(
            "**50-day average:** "
            f"{logic.money(data['average_50'], data['currency'])}"
        )
        st.write(
            "**200-day average:** "
            f"{logic.money(data['average_200'], data['currency'])}"
        )

        if not is_fund:
            st.write(f"**P/E ratio:** {logic.number_text(data['pe_ratio'])}")
            st.write(
                "**Market value:** "
                f"{logic.money(data['market_cap'], data['currency'])}"
            )
            if summary and summary["score"] is not None:
                st.write(
                    "**Financial quality score:** "
                    f"{summary['score']:.0f}/100"
                )

    st.subheader("About the business")
    st.write(logic.short_description(data["description"]))

    if is_fund:
        st.info(
            "This is a fund or index. Company profit, debt and valuation checks are not appropriate; review fees, holdings, benchmark and risk instead."
        )
        return

    st.subheader("Company metrics")
    metric_data = pd.DataFrame(
        [
            {"Metric": "Profit margin", "Value": logic.percentage(data["profit_margin"])},
            {"Metric": "Return on equity", "Value": logic.percentage(data["return_on_equity"])},
            {"Metric": "Revenue growth", "Value": logic.percentage(data["revenue_growth"])},
            {"Metric": "Debt to equity", "Value": logic.number_text(data["debt_to_equity"])},
            {"Metric": "EV / EBITDA", "Value": logic.number_text(data["enterprise_to_ebitda"])},
            {"Metric": "PEG ratio", "Value": logic.number_text(data["peg_ratio"])},
            {"Metric": "Price / book", "Value": logic.number_text(data["price_to_book"])},
        ]
    )
    st.dataframe(metric_data, use_container_width=True, hide_index=True)


def render_valuation(logic, data, is_fund, valuation, verdict, peer_text):
    """Render DCF, DDM, asset and direct-peer valuation views."""
    st.subheader("Valuation verdict")
    display_status(
        verdict["label"],
        verdict.get("explanation") or verdict.get("reason"),
    )

    if is_fund:
        return

    if verdict.get("available"):
        first, second, third = st.columns(3)
        first.metric(
            "Current price",
            logic.money(data["latest_price"], data["currency"]),
        )
        second.metric(
            "Base model value",
            logic.money(verdict["base_value"], data["currency"]),
        )
        third.metric("Model basis", verdict["basis"].title())

    dcf = valuation["dcf"]
    with st.expander("Discounted cash-flow model", expanded=True):
        if not dcf.get("available"):
            st.info(dcf.get("reason", "No suitable DCF data was available."))
        else:
            rows = []
            for scenario_name, scenario in dcf["scenarios"].items():
                rows.append(
                    {
                        "Scenario": scenario_name,
                        "Value per share": logic.money(
                            scenario["value_per_share"], data["currency"]
                        ),
                        "FCFF growth": logic.percentage(
                            scenario["cash_flow_growth"]
                        ),
                        "Discount rate": logic.percentage(
                            scenario["discount_rate"]
                        ),
                    }
                )
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.caption(
                "This is a five-year FCFF DCF with a terminal value. Growth and discount-rate assumptions can change the result materially."
            )

    dividend_column, asset_column = st.columns(2)
    ddm = valuation["ddm"]
    asset = valuation["asset"]

    with dividend_column:
        with st.expander("Dividend Discount Model"):
            if ddm.get("available"):
                st.metric(
                    "Indicative dividend value",
                    logic.money(ddm["value_per_share"], data["currency"]),
                )
                st.write(
                    f"Annual dividend: {logic.money(ddm['dividend'], data['currency'])}"
                )
                st.write(
                    f"Dividend growth assumption: {logic.percentage(ddm['growth'])}"
                )
                st.write(
                    f"Required return: {logic.percentage(ddm['discount_rate'])}"
                )
            else:
                st.info(ddm.get("reason", "No usable annual dividend was available."))

    with asset_column:
        with st.expander("Asset-based check"):
            if asset.get("available"):
                st.metric(
                    "Reported net assets per share",
                    logic.money(asset["value_per_share"], data["currency"]),
                )
                st.caption(
                    "This is accounting book value, not an independent appraisal of the business or its assets."
                )
            else:
                st.info(asset.get("reason", "No usable asset data was available."))

    st.subheader("Direct-peer valuation comparison")
    st.caption(
        "Enter 1–6 direct competitors in the search form. A lower multiple is not automatically better unless growth, risk and debt are comparable."
    )
    comparison, peer_tickers, warnings = peer_comparison(logic, data, peer_text)
    for warning in warnings:
        st.warning(warning)
    if comparison is not None:
        st.write(f"**Peers used:** {', '.join(peer_tickers)}")
        st.dataframe(comparison, use_container_width=True, hide_index=True)
    elif peer_text.strip():
        st.info("No usable peer valuation data was returned.")


def render_research_summary(logic, data, is_fund, valuation, summary):
    """Render the concise upside, downside and next-step research view."""
    st.subheader("Quick upside / downside summary")
    if is_fund:
        st.info(
            "This company model does not apply to a fund or index. Review its objective, benchmark, fees, holdings and risk instead."
        )
        return

    positives, risks = investment_case(logic, data, valuation, summary)
    upside_column, downside_column = st.columns(2)

    with upside_column:
        st.markdown("#### What could go right")
        for positive in positives:
            st.success(positive)

    with downside_column:
        st.markdown("#### What could go wrong")
        for risk in risks:
            st.warning(risk)

    if summary and summary["score"] is not None:
        screen_label = logic.financial_screen_label(
            summary["score"],
            summary["data_coverage"],
            summary["high_priority_failures"],
            summary["high_priority_missing"],
        )
        st.caption(
            f"Financial foundation: {summary['score']:.0f}/100 — {screen_label}"
        )


def render_checks(logic, data, is_fund, summary):
    """Render every original framework and its weighted-score contribution."""
    st.subheader("Analysis checks")
    if is_fund:
        st.info(
            "The Mark Tilbury, Drew Cohen and Plain Bagel company-statement checks do not suit funds or indexes."
        )
        return

    with st.expander("Mark Tilbury quantitative checks", expanded=True):
        st.dataframe(
            check_dataframe(logic, data["tilbury_checks"]),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Drew Cohen-inspired financial checklist"):
        st.dataframe(
            check_dataframe(logic, data["drew_checks"]),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Plain Bagel / Richard Coffin financial checklist"):
        st.dataframe(
            check_dataframe(logic, data["plain_bagel_checks"]),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Financial-quality score")
    if summary is None or summary["score"] is None:
        st.info("There was not enough usable data for a weighted financial score.")
        return

    score_column, confidence_column, status_column = st.columns(3)
    score_column.metric("Score", f"{summary['score']:.0f}/100")
    confidence_column.metric("Data coverage", f"{summary['data_coverage']:.0f}%")
    status_column.metric(
        "High-priority concerns",
        summary["high_priority_failures"] + summary["high_priority_missing"],
    )
    st.progress(min(max(summary["score"] / 100, 0), 1))
    st.dataframe(
        score_dataframe(logic, summary),
        use_container_width=True,
        hide_index=True,
    )


def render_risk(logic, data):
    """Render the existing historical-risk observations as clear cards."""
    st.subheader("Historical risk — last year")
    risk = data["risk"]
    volatility, drawdown, distance = st.columns(3)
    volatility.metric(
        "Annualised volatility",
        logic.percentage(risk["annualised_volatility"]),
    )
    drawdown.metric(
        "Largest fall from a prior high",
        logic.percentage(risk["maximum_drawdown"]),
    )
    distance.metric(
        "Below one-year high",
        logic.percentage(risk["current_drawdown"]),
    )
    st.caption("These are historical observations, not forecasts of future loss.")


def render_company_research(logic):
    """Build the complete individual-company research page."""
    st.title("Company research")
    st.caption("Use a listed company ticker such as AAPL, MSFT, GOOGL or VWRP.L.")

    with st.form("research_form"):
        ticker = st.text_input("Ticker", value="AAPL").strip().upper()
        peer_text = st.text_input(
            "Optional direct peers (1–6 tickers, separated by commas)",
            placeholder="For example: MSFT, GOOGL, META",
        )
        submitted = st.form_submit_button("Research company", type="primary")

    if submitted:
        if not ticker:
            st.error("Enter a ticker symbol first.")
        else:
            try:
                with st.spinner(f"Loading current Yahoo Finance data for {ticker}..."):
                    data = logic.get_stock_data(ticker)
                st.session_state["research_data"] = data
                st.session_state["research_peers"] = peer_text
            except Exception as error:
                st.error(f"Could not research {ticker}: {error}")

    data = st.session_state.get("research_data")
    if data is None:
        st.info("Enter a ticker above and select **Research company**.")
        return

    peer_text = st.session_state.get("research_peers", "")
    is_fund = str(data["type"]).upper() in logic.FUND_TYPES
    valuation = logic.calculate_valuation_models(data, is_fund)
    verdict = logic.valuation_verdict(data, is_fund, valuation)
    summary = logic.weighted_financial_score(data) if not is_fund else None

    st.divider()
    st.header(f"{data['name']} ({data['ticker']})")
    st.caption(f"Latest Yahoo Finance timestamp: {data['latest_time']}")

    price, yearly_return, trend, valuation_status = st.columns(4)
    price.metric(
        "Latest price",
        logic.money(data["latest_price"], data["currency"]),
    )
    yearly_return.metric(
        "One-year return",
        logic.percentage(data["one_year_return"]),
    )
    trend.metric("Trend", logic.trend_label(data))
    valuation_status.metric("Valuation", verdict["label"].replace("POTENTIALLY ", "").title())

    overview_tab, valuation_tab, summary_tab, checks_tab, risk_tab = st.tabs(
        ["Overview", "Valuation", "Upside / downside", "Analysis checks", "Risk"]
    )

    with overview_tab:
        render_overview(logic, data, is_fund, summary)
    with valuation_tab:
        render_valuation(logic, data, is_fund, valuation, verdict, peer_text)
    with summary_tab:
        render_research_summary(logic, data, is_fund, valuation, summary)
    with checks_tab:
        render_checks(logic, data, is_fund, summary)
    with risk_tab:
        render_risk(logic, data)


def build_live_universe(logic, choice, active_limit, emerging_limit):
    """Create the same stock universes used by the terminal screener."""
    ticker_sources = {}
    source_loaders = []
    messages = []

    if choice in {"Most Active", "Both"}:
        active_quotes = logic.get_most_active_quotes(active_limit)
        logic.add_source_quotes(ticker_sources, active_quotes)
        source_loaders.append(
            lambda active_limit=active_limit: logic.get_most_active_quotes(active_limit)
        )
        messages.append(f"Loaded {len(active_quotes)} current Most Active companies.")

    if choice in {"Small / emerging", "Both"}:
        emerging_quotes = logic.get_emerging_stock_quotes(emerging_limit)
        logic.add_source_quotes(ticker_sources, emerging_quotes)
        source_loaders.append(
            lambda emerging_limit=emerging_limit: logic.get_emerging_stock_quotes(
                emerging_limit
            )
        )
        messages.append(
            f"Loaded {len(emerging_quotes)} liquid small / emerging companies."
        )

    return ticker_sources, source_loaders, messages


def run_live_screener(logic, ticker_sources, source_loaders, force_refresh):
    """Score a live universe without using terminal print/input functions."""
    cache = logic.load_screen_cache()
    financial_records = []
    failed_count = 0
    fresh_count = 0
    cached_count = 0
    total = len(ticker_sources)
    progress = st.progress(0, text="Preparing the financial screen...")
    status = st.empty()

    for position, (ticker, source_data) in enumerate(ticker_sources.items(), start=1):
        status.caption(f"Checking annual financial data: {position}/{total} — {ticker}")
        cached_record = cache.get(ticker)

        if not force_refresh and logic.cached_record_is_fresh(cached_record):
            record = dict(cached_record)
            cached_count += 1
        else:
            try:
                record = logic.make_screen_record(ticker)
                cache[ticker] = record
                fresh_count += 1
                time.sleep(logic.SCREEN_REQUEST_DELAY_SECONDS)
            except Exception:
                failed_count += 1
                progress.progress(int(position / total * 100))
                continue

        financial_records.append((ticker, record))
        progress.progress(int(position / total * 100))

    status.caption("Refreshing live price, volume and market-value data...")
    refreshed_sources = {}
    refresh_errors = []
    for source_loader in source_loaders:
        try:
            logic.add_source_quotes(refreshed_sources, source_loader())
        except Exception as error:
            refresh_errors.append(str(error))

    for ticker, source_data in refreshed_sources.items():
        if ticker in ticker_sources:
            ticker_sources[ticker] = source_data

    records = []
    for ticker, record in financial_records:
        source_data = ticker_sources.get(ticker)
        if source_data is None:
            continue
        records.append(
            logic.update_record_with_live_quote(
                record,
                source_data["quote"],
                source_data["sources"],
            )
        )

    logic.save_screen_cache(cache)
    progress.empty()
    status.empty()

    return {
        "records": records,
        "failed_count": failed_count,
        "fresh_count": fresh_count,
        "cached_count": cached_count,
        "refresh_errors": refresh_errors,
    }


def screener_dataframe(logic, records):
    """Turn compact screen records into an interactive Streamlit table."""
    rows = []
    for record in sorted(records, key=logic.screen_sort_key):
        rows.append(
            {
                "Status": logic.screen_result_status(record),
                "Ticker": record["ticker"],
                "Company": record.get("name", record["ticker"]),
                "Sector": record.get("sector", "Not available"),
                "Score": round(record["score"], 1) if logic.is_number(record.get("score")) else None,
                "Data coverage": (
                    round(record["data_coverage"], 1)
                    if logic.is_number(record.get("data_coverage"))
                    else None
                ),
                "Today": logic.signed_percentage_points(record.get("day_change")),
                "Relative volume": (
                    f"{record['relative_volume']:.1f}x"
                    if logic.is_number(record.get("relative_volume"))
                    else "n/a"
                ),
                "Price": logic.compact_money(
                    record.get("price"), record.get("currency", "$")
                ),
                "Market value": logic.compact_money(
                    record.get("market_cap"), record.get("currency", "$")
                ),
                "Source": ", ".join(record.get("sources", [])),
            }
        )
    return pd.DataFrame(rows)


def render_screener_results(logic, payload, top_count):
    """Display strict matches and the emerging watchlist in separate tables."""
    records = payload["records"]
    strict_matches = [record for record in records if record["candidate"]]
    emerging_watchlist = [
        record for record in records if record.get("emerging_watchlist")
    ]

    st.subheader("Live screener results")
    first, second, third, fourth = st.columns(4)
    first.metric("Companies scored", len(records))
    second.metric("Strict model matches", len(strict_matches))
    third.metric("Emerging watchlist", len(emerging_watchlist))
    fourth.metric("Could not score", payload["failed_count"])
    st.caption(
        f"Financial scores: {payload['fresh_count']} refreshed now; "
        f"{payload['cached_count']} reused from the six-hour cache. "
        "Live price, daily change, volume and market value are refreshed on every screen run."
    )

    for error in payload["refresh_errors"]:
        st.warning(
            "A live-quote refresh was unavailable, so the table may use the quote snapshot from the start of this run."
        )
        break

    st.markdown("#### Strict model matches")
    st.caption(
        "Score 70+; data coverage 85%+; no failed high-priority checks; no missing high-priority checks. These are research candidates, not buy recommendations."
    )
    strict_frame = screener_dataframe(logic, strict_matches).head(top_count)
    st.dataframe(strict_frame, use_container_width=True, hide_index=True)

    st.markdown("#### Small / emerging watchlist")
    st.caption(
        "Smaller companies can have shorter reporting histories. This list allows one missing high-priority history check but no failed high-priority check."
    )
    emerging_frame = screener_dataframe(logic, emerging_watchlist).head(top_count)
    st.dataframe(emerging_frame, use_container_width=True, hide_index=True)

    all_frame = screener_dataframe(logic, records)
    st.download_button(
        "Download all screen results as CSV",
        all_frame.to_csv(index=False).encode("utf-8"),
        file_name="stock_screener_results.csv",
        mime="text/csv",
    )


def clear_screen_cache(logic):
    """Clear the original ranker's cache using the existing cache location."""
    try:
        logic.SCREEN_CACHE_FILE.unlink(missing_ok=True)
        st.session_state.pop("screener_payload", None)
        st.success("Saved screener scores cleared.")
    except OSError as error:
        st.error(f"Could not clear the screener cache: {error}")


def render_live_screener(logic):
    """Build the complete live Most Active / emerging-screen page."""
    st.title("Live US stock screener")
    st.caption(
        "Yahoo Finance Most Active and liquid smaller US companies, filtered by the same weighted financial model used in company research."
    )
    st.warning(
        "A first-time large screen can take several minutes because annual statements are checked company by company."
    )

    clear_column, spacer = st.columns([1, 5])
    with clear_column:
        if st.button("Clear screener cache"):
            clear_screen_cache(logic)

    with st.form("screener_form"):
        choice = st.radio(
            "Universe",
            ["Most Active", "Small / emerging", "Both"],
            horizontal=True,
        )
        settings_one, settings_two, settings_three = st.columns(3)
        with settings_one:
            active_limit = st.slider(
                "Most Active companies to check",
                min_value=1,
                max_value=logic.MAX_SCREEN_UNIVERSE,
                value=logic.DEFAULT_ACTIVE_STOCKS,
            )
        with settings_two:
            emerging_limit = st.slider(
                "Small / emerging companies to check",
                min_value=1,
                max_value=logic.MAX_SCREEN_UNIVERSE,
                value=logic.DEFAULT_EMERGING_STOCKS,
            )
        with settings_three:
            top_count = st.slider(
                "Rows to show in each results table",
                min_value=1,
                max_value=logic.MAX_SCREEN_RESULTS,
                value=logic.DEFAULT_SCREEN_RESULTS,
            )
        force_refresh = st.checkbox(
            "Refresh every annual financial score now",
            help="Live quote data is always refreshed. Tick this only when you also want to bypass the six-hour financial-score cache.",
        )
        submitted = st.form_submit_button("Run live screen", type="primary")

    if submitted:
        try:
            with st.spinner("Loading the live Yahoo Finance universe..."):
                ticker_sources, source_loaders, messages = build_live_universe(
                    logic,
                    choice,
                    active_limit,
                    emerging_limit,
                )
            for message in messages:
                st.caption(message)

            if not ticker_sources:
                st.info("Yahoo Finance did not return any companies for this screen.")
            else:
                payload = run_live_screener(
                    logic,
                    ticker_sources,
                    source_loaders,
                    force_refresh,
                )
                st.session_state["screener_payload"] = payload
                st.session_state["screener_top_count"] = top_count
        except Exception as error:
            st.error(f"Could not run the live screen: {error}")

    payload = st.session_state.get("screener_payload")
    if payload is None:
        st.info("Choose a universe above, then select **Run live screen**.")
    else:
        render_screener_results(
            logic,
            payload,
            st.session_state.get("screener_top_count", logic.DEFAULT_SCREEN_RESULTS),
        )


def render_model_notes(logic):
    """Explain the same safeguards and assumptions shown in the terminal README."""
    st.title("How to use the model")
    st.info(
        "This is a research dashboard, not a buy/sell tool. A high score or a potentially undervalued label is a prompt for more research, not an instruction to invest."
    )

    st.subheader("Valuation labels")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Label": "Potentially undervalued",
                    "Meaning": "Current price is materially below the cautious DCF case, after the uncertainty margin.",
                },
                {
                    "Label": "Roughly fairly valued",
                    "Meaning": "Current price sits within or close to the DCF scenario range.",
                },
                {
                    "Label": "Potentially overvalued",
                    "Meaning": "Current price is materially above the optimistic DCF case, after the uncertainty margin.",
                },
                {
                    "Label": "Inconclusive",
                    "Meaning": "The statement data or the valuation method is not suitable for a reliable modelled-value verdict.",
                },
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Key DCF assumptions")
    st.code(
        "\n".join(
            [
                f"DCF forecast years = {logic.DCF_FORECAST_YEARS}",
                f"Risk-free rate assumption = {logic.percentage(logic.RISK_FREE_RATE_ASSUMPTION)}",
                f"Equity risk premium assumption = {logic.percentage(logic.EQUITY_RISK_PREMIUM_ASSUMPTION)}",
                f"Terminal growth rate = {logic.percentage(logic.TERMINAL_GROWTH_RATE)}",
                f"Valuation uncertainty margin = {logic.percentage(logic.VALUATION_BUFFER)}",
            ]
        )
    )
    st.caption(
        "These are generic US-market starting assumptions. They are not live market rates or price targets."
    )

    st.subheader("Important limits")
    st.markdown(
        """
        - Yahoo Finance can provide delayed or incomplete data; always read the timestamp.
        - One-minute price data is not available for every ticker, fund or exchange.
        - Financial statements update when companies report results, not every minute.
        - Banks, insurers, property companies, ETFs, mutual funds and indexes need different analysis methods.
        - Check the latest official company results before making any investment decision.
        """
    )


def main():
    """Start the Streamlit navigation and render the selected dashboard page."""
    try:
        logic, source_file = load_stock_logic()
    except Exception as error:
        st.error(str(error))
        st.stop()

    with st.sidebar:
        st.title("📈 Stock Researcher")
        page = st.radio(
            "Navigate",
            ["Research a company", "Live US screener", "How to use the model"],
        )
        st.divider()
        st.caption(f"Research engine: {source_file}")
        st.caption("Yahoo Finance data • Research tool only")

    if page == "Research a company":
        render_company_research(logic)
    elif page == "Live US screener":
        render_live_screener(logic)
    else:
        render_model_notes(logic)

    st.divider()
    st.caption(
        "This dashboard is for educational research. It is not personal financial advice or a recommendation to buy or sell any investment."
    )


if __name__ == "__main__":
    main()