"""Streamlit multipage route for AlphaLab's first educational strategy backtest."""

import math

import streamlit as st

from alphalab.backtesting import (
    BacktestConfig,
    combine_nifty_500_tri_csv,
    compare_to_benchmark,
    make_demo_market_proxy,
    run_momentum_backtest,
)
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
st.caption("v0.4 · Historical simulation + benchmark comparison · No live orders")
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
    csv_files = None
    if source == "Yahoo (historical)":
        st.divider()
        st.subheader("Benchmark")
        st.caption(
            "For a real benchmark, download **NIFTY 500** from the NSE "
            "**Total returns Index Values** report, then upload the CSV here. "
            "You can select multiple date-window files."
        )
        st.link_button(
            "Get official Nifty TRI data",
            "https://www.niftyindices.com/reports/historical-data",
        )
        csv_files = st.file_uploader(
            "Nifty 500 TRI CSV file(s)",
            type=["csv"],
            accept_multiple_files=True,
            help="Must include Date and Total Returns Index, not Close (price index).",
        )
    else:
        st.caption("Demo benchmark: synthetic daily-rebalanced equal-weight proxy — NOT Nifty 500.")
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
        benchmark_comparison = None
        benchmark_error = None
        if source.startswith("Demo"):
            proxy = make_demo_market_proxy(price_data)
            benchmark_comparison = compare_to_benchmark(
                backtest, proxy, label="Synthetic equal-weight market proxy"
            )
        elif csv_files:
            try:
                tri = combine_nifty_500_tri_csv([f.getvalue() for f in csv_files])
                benchmark_comparison = compare_to_benchmark(
                    backtest, tri, label="Nifty 500 TRI (user-uploaded NSE CSV)"
                )
            except ValueError as exc:
                benchmark_error = str(exc)
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

st.subheader("Strategy vs benchmark")
if benchmark_comparison is not None:
    comp = benchmark_comparison
    bstats = comp.summary
    metrics = st.columns(4)
    metrics[0].metric("Benchmark total return", f"{bstats['benchmark_return_pct']:+.1f}%")
    metrics[1].metric("Benchmark CAGR", f"{bstats['benchmark_cagr_pct']:+.1f}%")
    metrics[2].metric("Excess return (pp)", f"{bstats['excess_total_return_pp']:+.1f}")
    metrics[3].metric(
        "Strategy vs benchmark",
        "Outperformed" if bstats["strategy_wins"] else "Did not outperform",
    )
    st.line_chart(
        comp.curve.set_index("date")[["strategy_inr", "benchmark_inr"]].rename(
            columns={"strategy_inr": "Momentum strategy", "benchmark_inr": comp.label}
        ),
        y_label="Value (₹)",
    )
    st.caption(
        f"Benchmark: **{comp.label}** · Matched actual dates: "
        f"{bstats['matched_dates_pct']:.1f}% · "
        f"Strategy CAGR minus benchmark CAGR: {bstats['excess_cagr_pp']:+.1f} pp. "
        "Excess return here means percentage-point difference, NOT risk-adjusted alpha."
    )
    with st.expander("Full benchmark statistics"):
        st.dataframe(
            {
                "Metric": ["Total return (%)", "CAGR (%)", "Max drawdown (%)", "Sharpe (0% RF)"],
                "Strategy": [
                    stats["total_return_pct"],
                    stats["cagr_pct"],
                    stats["max_drawdown_pct"],
                    stats["sharpe_zero_rf"],
                ],
                "Benchmark": [
                    bstats["benchmark_return_pct"],
                    bstats["benchmark_cagr_pct"],
                    bstats["benchmark_max_drawdown_pct"],
                    bstats["benchmark_sharpe_zero_rf"],
                ],
            }
        )
else:
    st.line_chart(backtest.equity_curve.set_index("date")["portfolio_inr"], y_label="Value (₹)")
    if benchmark_error:
        st.error(f"Benchmark unavailable: {benchmark_error}")
    else:
        st.info(
            "Real strategy loaded. Upload official Nifty 500 TRI daily CSV above to "
            "display a fair side-by-side comparison. No substitute benchmark will be shown."
        )
st.caption(
    f"{stats['days_tested']} trading sessions tested · "
    f"{stats['rebalance_count']} rebalances · Starting capital ₹{capital:,.0f}. "
    "Index levels assume no ETF fees, tracking error, brokerage or investor taxes."
)

col1, col2 = st.columns(2)
with col1:
    st.subheader("Drawdown")
    st.line_chart(backtest.equity_curve.set_index("date")["drawdown_pct"], y_label="Drawdown (%)")
with col2:
    st.subheader("Rebalance log")
    st.dataframe(
        backtest.rebalances.style.format({"gross_turnover_pct": "{:.1f}%", "cost_inr": "₹{:,.2f}"}),
        use_container_width=True,
        hide_index=True,
    )

st.subheader("Every selection (audit trail)")
st.dataframe(
    backtest.selections.style.format({"signal_pct": "{:+.2f}%", "target_weight_pct": "{:.1f}%"}),
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
          historical Nifty 500 constituents, or out-of-sample validation yet.
        - **v0.4 benchmark:** Nifty 500 TRI is loaded from user-selected NSE
          official daily historical CSV. Comparison normalizes both to the same
          starting capital and dates; no TRI values are bundled or invented.
          Small gaps on nonmatching calendar dates may be forward-filled if
          at least 98% of strategy dates have actual TRI entries. A real index
          is not a cost-adjusted, investable ETF return.
        - **Demo comparison:** synthetic equal-weight daily-rebalanced market proxy,
          unrelated to NSE's Nifty 500; its returns must never be interpreted
          as a real benchmark.
        - **Sharpe:** annualized using 252 sessions and assumed risk-free rate of 0%.
        - **Real source:** Yahoo adjusted closes are intended for personal research,
          not licensed public redistribution. Demo prices are entirely fictional.
        """
    )
