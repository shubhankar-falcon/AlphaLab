"""Streamlit multipage route for AlphaLab's first educational strategy backtest."""

import math

import streamlit as st

from alphalab.backtesting import BacktestConfig, run_momentum_backtest
from alphalab.data.demo import DemoPriceProvider
from alphalab.data.yahoo import MarketDataError, YahooFinancePriceProvider

st.set_page_config(page_title="AlphaLab | Backtesting Lab", page_icon="🧪", layout="wide")


@st.cache_data(show_spinner=False)
def demo_history():
    return DemoPriceProvider().get_prices()


@st.cache_data(ttl=3600, show_spinner=False)
def yahoo_history():
    # More history than the screener's 2-year default, for a longer test window.
    return YahooFinancePriceProvider(period="5y").get_prices()


st.title("🧪 AlphaLab — Backtesting Lab")
st.caption("v0.3 · Historical simulation · Long-only 12–1 momentum · No live orders")
st.warning(
    "RESEARCH PROTOTYPE: Current tickers only (survivorship bias); adjusted Yahoo data "
    "may be incomplete. Backtests are not investment advice or future predictions."
)

with st.sidebar:
    st.header("Backtest settings")
    source = st.radio("Data source", ["Demo (synthetic)", "Yahoo (historical)"], index=0)
    st.caption("Ranks use only the past; results always measure subsequent returns.")
    top_n = st.slider("Top stocks", min_value=2, max_value=10, value=5)
    lookback = st.selectbox("Lookback", [126, 252], index=1, format_func=lambda x: f"{x} sessions")
    skip = st.selectbox("Skip recent sessions", [21, 42], index=0)
    costs = st.slider("Cost per traded side (bps)", 0, 50, 10, 5)
    capital = st.number_input("Starting cash (₹)", min_value=10_000, value=100_000, step=10_000)
    if source == "Yahoo (historical)" and st.button("Refresh Yahoo history"):
        yahoo_history.clear()

try:
    with st.spinner("Loading prices and running simulation..."):
        price_data = demo_history() if source.startswith("Demo") else yahoo_history()
        config = BacktestConfig(
            lookback_sessions=lookback,
            skip_sessions=skip,
            top_n=top_n,
            cost_bps=costs,
            starting_cash=float(capital),
        )
        backtest = run_momentum_backtest(price_data, config)
except (MarketDataError, ValueError) as exc:
    st.error(f"Cannot run backtest: {exc}")
    st.stop()

stats = backtest.summary
cols = st.columns(5)
cols[0].metric("Total return", f"{stats['total_return_pct']:+.1f}%")
cols[1].metric("CAGR", f"{stats['cagr_pct']:+.1f}%")
cols[2].metric("Max drawdown", f"{stats['max_drawdown_pct']:.1f}%")
cols[3].metric(
    "Sharpe (0% RF)",
    f"{stats['sharpe_zero_rf']:.2f}" if math.isfinite(stats["sharpe_zero_rf"]) else "N/A",
)
cols[4].metric("Total trading costs", f"₹{stats['total_cost_inr']:,.0f}")

st.subheader("Portfolio value")
st.line_chart(backtest.equity_curve.set_index("date")["portfolio_inr"], y_label="Value (₹)")
st.caption(
    f"{stats['days_tested']} trading sessions tested · "
    f"{stats['rebalance_count']} rebalances · Starting capital ₹{capital:,.0f}. "
    "No official Nifty 500 TRI comparison is included yet."
)

col1, col2 = st.columns(2)
with col1:
    st.subheader("Drawdown")
    st.line_chart(backtest.equity_curve.set_index("date")["drawdown_pct"], y_label="Drawdown (%)")
with col2:
    st.subheader("Rebalance log")
    st.dataframe(
        backtest.rebalances.style.format(
            {"gross_turnover_pct": "{:.1f}%", "cost_inr": "₹{:,.2f}"}
        ),
        use_container_width=True,
        hide_index=True,
    )

st.subheader("Every selection (audit trail)")
st.dataframe(
    backtest.selections.style.format(
        {"signal_pct": "{:+.2f}%", "target_weight_pct": "{:.1f}%"}
    ),
    use_container_width=True,
    hide_index=True,
)

with st.expander("Methodology and limitations — read before interpreting results"):
    st.markdown(
        """
        - **Strategy:** on the first observed trading day of each new month, rank
          eligible stocks by adjusted-price change from **t−1−252** through
          **t−1−21**, measured in observed sessions. Hold top N at equal weights.
        - **No look-ahead:** the newest price used for *selecting* stocks is
          yesterday's close; simplified execution is at today's close. Thus a
          newly selected stock contributes returns starting the next session.
        - **P&L:** positions are shares held between rebalances; their weights drift.
          Trading fees are deducted from available cash at each rebalance.
        - **Costs:** basis points per side × total buy-and-sell traded notional.
          This is a fee/slippage **approximation**, not Indian brokerage/tax modelling.
        - **Quality control:** held stocks with missing valuation prices cause an error.
          Newly listed stocks require a complete formation history before eligibility.
        - **Big limitations:** current ticker universe causes survivorship bias;
          no historical index membership, delistings, volume/liquidity screens,
          market-impact model, bid-ask spreads, taxes, IPO/demerger event model,
          proper Nifty 500 **TRI** benchmark or out-of-sample validation yet.
        - **Sharpe:** annualized using 252 sessions and assumed risk-free rate of 0%.
        - **Real source:** Yahoo adjusted closes are intended for personal research,
          not licensed public redistribution. Demo prices are entirely fictional.
        """
    )
