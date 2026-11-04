"""AlphaLab research dashboard: reproducible demo or historical NSE prices."""

import streamlit as st

from alphalab.data.demo import DEMO_TICKERS, DemoPriceProvider
from alphalab.data.yahoo import MarketDataError, YahooFinancePriceProvider
from alphalab.strategies.momentum import screen_momentum

st.set_page_config(page_title="AlphaLab | Strategy Research", page_icon="📈", layout="wide")


@st.cache_data
def load_demo_prices():
    """Deterministic synthetic prices cached across widget interactions."""
    return DemoPriceProvider().get_prices()


@st.cache_data(ttl=3600, show_spinner=False)
def load_yahoo_prices():
    """Research data cached for one hour to avoid repeated provider requests."""
    return YahooFinancePriceProvider().get_prices()


st.title("AlphaLab")
st.caption("Indian equities · Strategy research sandbox · v0.2")

with st.sidebar:
    st.header("Screener settings")
    source = st.radio("Price data", ["Demo (synthetic)", "Yahoo (historical)"], index=0)
    lookback = st.selectbox(
        "Momentum lookback (trading sessions)",
        options=[21, 63, 126, 252],
        index=2,
        help="Approximately 1, 3, 6, or 12 trading months.",
    )
    top_n = st.slider("Number of stocks", min_value=5, max_value=15, value=10)
    if source == "Yahoo (historical)" and st.button("Refresh historical prices"):
        load_yahoo_prices.clear()
    st.divider()
    st.caption("Yahoo data is for personal research, not redistribution or live trading.")

is_demo = source == "Demo (synthetic)"
if is_demo:
    st.warning("DEMO MODE — all prices are synthetic. No real returns or recommendations.")
    prices = load_demo_prices()
else:
    st.info(
        "HISTORICAL MODE — real adjusted daily prices (not a live market feed). "
        "Source: Yahoo Finance, via yfinance. Data may be delayed or incomplete."
    )
    with st.spinner("Fetching historical prices..."):
        try:
            prices = load_yahoo_prices()
        except (MarketDataError, ValueError) as exc:
            st.error(f"Historical data unavailable: {exc}")
            st.stop()

results = screen_momentum(prices, lookback_sessions=lookback, top_n=top_n)
as_of = prices["date"].max().date().isoformat()

if not is_demo:
    received = set(prices["ticker"].unique())
    missing = sorted(set(DEMO_TICKERS) - received)
    if missing:
        st.warning(
            f"No usable historical prices for {len(missing)} symbol(s): {', '.join(missing)}"
        )

left, middle, right = st.columns(3)
left.metric("Universe loaded", f"{prices['ticker'].nunique()} symbols")
middle.metric("Latest data date", as_of)
right.metric("Ranked stocks", str(len(results)))

st.subheader("Momentum stock screener")
st.write(
    "Stocks ranked by **trailing adjusted-price return** over the selected period. "
    "Past performance does not predict future returns."
)
if results.empty:
    st.info("No stocks have sufficient usable history for this selection.")
else:
    st.dataframe(
        results.style.format(
            {
                "momentum_pct": "{:+.2f}%",
                "volatility_pct": "{:.2f}%",
                "last_close": "{:.2f}",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )
    st.caption("last_close = latest adjusted closing price, in INR for NSE equity symbols.")

    st.subheader("Explore price history")
    selected = st.selectbox("Ticker", results["ticker"].tolist())
    ticker_prices = prices.loc[prices["ticker"] == selected, ["date", "close"]]
    y_label = "Synthetic price" if is_demo else "Adjusted close (INR)"
    st.line_chart(ticker_prices.set_index("date")["close"], y_label=y_label)

with st.expander("Research methodology and limitations"):
    st.markdown(
        """
        - Momentum = (last close / close **N sessions earlier** − 1) × 100.
        - Volatility = sample standard deviation of daily returns × √252 × 100.
        - Stocks without enough prices, or with stale last dates, are excluded.
        - **Historical mode** uses split- and dividend-adjusted daily closes from Yahoo.
          A stock absent from the feed is not treated as having zero return.
        - This is a **screener**, not a backtest; no rebalancing, transaction costs,
          universe survivorship-bias treatment, or benchmark calculation yet.
        - **Demo mode** uses prices from a fixed random seed for reproducibility.
        - Market-data licensing must be reviewed before publishing real-price displays.
        """
    )
