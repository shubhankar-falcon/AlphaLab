"""Independent risk wing for the historical momentum backtesting strategy."""

import streamlit as st

from alphalab.backtesting import BacktestConfig, run_momentum_backtest
from alphalab.data.demo import DemoPriceProvider
from alphalab.data.yahoo import MarketDataError, YahooFinancePriceProvider
from alphalab.risk import (
    analyze_historical_risk,
    estimate_target_risk,
    stress_target_portfolio,
)

st.set_page_config(page_title="AlphaLab | Risk Intelligence", page_icon="🛡️", layout="wide")


@st.cache_data(show_spinner=False)
def demo_history():
    return DemoPriceProvider().get_prices()


@st.cache_data(ttl=3600, show_spinner=False)
def yahoo_history():
    return YahooFinancePriceProvider(period="5y").get_prices()


st.title("🛡️ AlphaLab — Risk Intelligence")
st.caption("v0.7 · Historical strategy risk + point-in-time target exposures · No trading")
st.warning(
    "RESEARCH PROTOTYPE: Historical statistics and hypothetical shocks are not forecasts. "
    "The stock universe includes today's survivors; corporate actions and execution "
    "costs are simplified. This is NOT risk analysis of your forward paper holdings."
)

with st.sidebar:
    st.header("Risk Lab settings")
    source = st.radio("Market prices", ["Demo (synthetic)", "Yahoo (historical)"], index=0)
    top_n = st.slider("Top momentum stocks", 2, 10, 5)
    lookback = st.selectbox("Momentum lookback", [126, 252], index=1)
    skip = st.selectbox("Skip recent sessions", [21, 42], index=0)
    cost_bps = st.slider("Trading cost per side (bps)", 0, 50, 10, 5)
    starting_cash = st.number_input(
        "Historical starting capital (₹)", min_value=10_000, value=100_000, step=10_000
    )
    st.divider()
    confidence = st.selectbox("Historical VaR confidence", [95, 99], index=0)
    window = st.selectbox("Rolling volatility (sessions)", [21, 63, 126], index=1)
    estimation = st.selectbox("Target risk lookback (sessions)", [63, 126], index=0)
    st.caption("VaR and expected shortfall use the entire backtest return sample.")
    if source == "Yahoo (historical)" and st.button("Refresh Yahoo history"):
        yahoo_history.clear()

try:
    with st.spinner("Reconstructing strategy risk from historical prices..."):
        prices = demo_history() if source.startswith("Demo") else yahoo_history()
        config = BacktestConfig(
            lookback_sessions=lookback,
            skip_sessions=skip,
            top_n=top_n,
            cost_bps=cost_bps,
            starting_cash=float(starting_cash),
        )
        backtest = run_momentum_backtest(prices, config)
        risk = analyze_historical_risk(
            backtest, confidence=confidence / 100.0, rolling_sessions=window
        )
        target = estimate_target_risk(
            prices, backtest.selections, estimation_sessions=estimation
        )
except (MarketDataError, ValueError, KeyError) as exc:
    st.error(f"Unable to calculate risk: {exc}")
    st.stop()

s = risk.summary
st.subheader("Realized historical risk")
metrics = st.columns(5)
metrics[0].metric("Annualized volatility", f"{s['annual_volatility_pct']:.1f}%")
metrics[1].metric("Max drawdown", f"{s['max_drawdown_pct']:.1f}%")
metrics[2].metric("Worst trading day", f"{s['worst_day_pct']:.2f}%")
metrics[3].metric(f"1-day VaR ({confidence}%)", f"₹{s['var_inr']:,.0f}")
metrics[4].metric(
    f"1-day expected shortfall ({confidence}%)", f"₹{s['expected_shortfall_inr']:,.0f}"
)
st.caption(
    f"Historical sample: {s['observations']} simulated sessions · "
    f"Latest *backtest* NAV ₹{s['latest_nav_inr']:,.0f}. "
    "VaR is an empirical loss quantile; expected shortfall is the mean loss "
    "in that historical tail. Neither is a worst-case loss limit."
)

left, right = st.columns(2)
with left:
    st.subheader("Rolling annualized volatility")
    st.line_chart(
        risk.history.set_index("date")["rolling_vol_pct"], y_label="Volatility (%)"
    )
with right:
    st.subheader("Drawdown from previous peak")
    st.line_chart(risk.history.set_index("date")["drawdown_pct"], y_label="Drawdown (%)")

st.subheader("Latest rebalance target exposure")
st.caption(
    f"Historical rebalance date: **{target.rebalance_date.date()}** · "
    f"Covariance window: **{target.estimation_start.date()}–{target.estimation_end.date()}** "
    f"({target.sessions} daily returns, ending *before* the rebalance). "
    "These are historical *target* weights, not today's drifted or paper-trading holdings."
)
st.metric("Estimated target portfolio volatility (annualized)", f"{target.estimated_vol_pct:.1f}%")
exposure = target.exposures.copy()
st.dataframe(
    exposure.style.format(
        {
            "target_weight_pct": "{:.1f}%",
            "standalone_vol_pct": "{:.1f}%",
            "risk_contribution_pct": "{:+.1f}%",
        }
    ),
    use_container_width=True,
    hide_index=True,
)
st.caption(
    "Risk contribution is each stock's share of estimated portfolio variance, "
    "not its return contribution. Values can be negative with hedging correlations. "
    "The covariance estimate uses retrospectively adjusted prices and may change with revisions."
)

st.subheader("What-if shock scenarios")
st.caption(
    "Simple linear shocks on the *latest rebalance's equal-weight targets*, "
    "scaled to the latest simulated backtest NAV. Scenarios are independent, "
    "not combined; they ignore weight drift, cash, correlations and market impact."
)
market_col, ticker_col, drop_col = st.columns(3)
with market_col:
    market_shock = st.slider("If ALL selected stocks fall (%)", -30, 0, -10, 5)
with ticker_col:
    chosen_ticker = st.selectbox("If only this stock falls", exposure["ticker"].tolist())
with drop_col:
    ticker_shock = st.slider("Individual stock fall (%)", -50, 0, -20, 5)

scenarios = stress_target_portfolio(
    exposure,
    portfolio_value_inr=float(s["latest_nav_inr"]),
    market_shock_pct=float(market_shock),
    single_ticker=chosen_ticker,
    ticker_shock_pct=float(ticker_shock),
)
scenario_cols = st.columns(2)
scenario_cols[0].metric(
    f"All stocks {market_shock}% — change",
    f"₹{scenarios['market_change_inr']:,.0f}",
)
scenario_cols[1].metric(
    f"{chosen_ticker} {ticker_shock}% — change",
    f"₹{scenarios['ticker_change_inr']:,.0f}",
)

with st.expander("Methodology and limitations (important)"):
    st.markdown(
        """
        - **Historical volatility:** sample standard deviation of net daily strategy
          returns, annualized with √252. Includes modeled trading costs.
        - **Historical VaR:** empirical 5th (or 1st) percentile of one-day *net*
          returns. Expected shortfall averages returns below that threshold.
          Both are scaled by the final historical backtest NAV for INR display;
          these are neither forecasts nor guarantees.
        - **Maximum drawdown:** largest peak-to-trough loss on the simulated equity
          path, including the starting capital as the initial peak.
        - **Target risk:** last rebalance's target weights × covariance estimated
          from 63 or 126 complete daily stock returns available *before* the
          rebalance date. Variance contributions may be negative.
        - **Scenario analysis:** parallel or single-stock fixed percentage drops
          applied to the most recent *historical targets*. No current-position
          reconstruction or corporate action modeling. Not a live or paper NAV.
        - **Major limitations:** 20 current stocks (survivorship bias), Yahoo
          retroactively adjusted data, no historical index memberships,
          no calibrated distributional VaR model, no market liquidity or
          stress-regime liquidity, no leverage or sector metadata.
        - **Zero live integration:** this wing does not read or update the
          forward Signal Journal or Paper Portfolio. Nothing here trades.
        """
    )
