import importlib.util
from pathlib import Path

import streamlit as st


st.set_page_config(page_title="Stock Researcher", page_icon="📈")

# Load your existing Stock-ranker.py file.
script_path = Path(__file__).with_name("Stock-ranker.py")
spec = importlib.util.spec_from_file_location("stock_logic", script_path)
stock_logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stock_logic)

st.title("📈 Stock Researcher")
st.write("Research tool only — not investment advice.")

ticker = st.text_input("Enter a ticker", "AAPL").strip().upper()

if st.button("Research stock"):
    try:
        with st.spinner("Loading stock data..."):
            data = stock_logic.get_stock_data(ticker)

        is_fund = str(data["type"]).upper() in stock_logic.FUND_TYPES
        valuation = stock_logic.calculate_valuation_models(data, is_fund)
        verdict = stock_logic.valuation_verdict(data, is_fund, valuation)

        st.header(f"{data['name']} ({data['ticker']})")

        price, return_one_year, trend = st.columns(3)

        price.metric(
            "Latest price",
            stock_logic.money(data["latest_price"], data["currency"]),
        )
        return_one_year.metric(
            "One-year return",
            stock_logic.percentage(data["one_year_return"]),
        )
        trend.metric(
            "Price trend",
            stock_logic.trend_label(data),
        )

        st.subheader("Valuation verdict")

        if verdict["label"] == "POTENTIALLY UNDERVALUED":
            st.success(verdict["label"])
        elif verdict["label"] == "POTENTIALLY OVERVALUED":
            st.warning(verdict["label"])
        else:
            st.info(verdict["label"])

        if verdict["available"]:
            st.write(f"**Basis:** {verdict['basis']}")
            st.write(
                f"**Base model value:** "
                f"{stock_logic.money(verdict['base_value'], data['currency'])}"
            )
            st.write(verdict["explanation"])
        else:
            st.write(verdict["reason"])

        st.subheader("Company metrics")
        st.write(f"**Sector:** {data['sector']}")
        st.write(f"**P/E ratio:** {stock_logic.number_text(data['pe_ratio'])}")
        st.write(
            f"**Market value:** "
            f"{stock_logic.money(data['market_cap'], data['currency'])}"
        )
        st.write(
            f"**Profit margin:** "
            f"{stock_logic.percentage(data['profit_margin'])}"
        )

        if not is_fund:
            st.subheader("Mark Tilbury checks")

            for check in data["tilbury_checks"]:
                status = stock_logic.tilbury_marker(check["result"])

                st.write(
                    f"**{status} — {check['name']}**  \n"
                    f"Result: {check['result_value']}  \n"
                    f"Rule: {check['pass_rule']}  \n"
                    f"{check['reason']}"
                )

    except Exception as error:
        st.error(f"Could not research this ticker: {error}")