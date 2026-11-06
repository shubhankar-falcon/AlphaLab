"""Risk wing tests: historical loss math, temporal safety, covariance and shocks."""

import numpy as np
import pandas as pd
import pytest

from alphalab.backtesting import BacktestConfig, run_momentum_backtest
from alphalab.backtesting.engine import BacktestResult
from alphalab.risk import (
    analyze_historical_risk,
    estimate_target_risk,
    stress_target_portfolio,
)


def historical_result(returns=None):
    if returns is None:
        returns = np.array([-0.03] * 12 + [0.005] * 108)
    returns = np.asarray(returns, dtype=float)
    equity = 100_000.0 * np.cumprod(1.0 + returns)
    curve = pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=len(returns)),
            "portfolio_inr": equity,
            "daily_return": returns,
        }
    )
    return BacktestResult(
        equity_curve=curve,
        rebalances=pd.DataFrame(),
        selections=pd.DataFrame(),
        summary={"starting_cash": 100_000.0},
    )


def prior_prices(n=130):
    dates = pd.bdate_range("2024-01-01", periods=n)
    rng = np.random.default_rng(13)
    a = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.01, n)))
    b = 200 * np.exp(np.cumsum(rng.normal(0.0005, 0.018, n)))
    return pd.concat(
        [
            pd.DataFrame({"date": dates, "ticker": t, "close": values})
            for t, values in [("AAA", a), ("BBB", b)]
        ],
        ignore_index=True,
    )


def selections_at(prices):
    when = prices["date"].max()
    return pd.DataFrame(
        {
            "date": [when, when],
            "ticker": ["AAA", "BBB"],
            "target_weight_pct": [50.0, 50.0],
        }
    )


def exposures():
    return pd.DataFrame({"ticker": ["AAA", "BBB"], "target_weight_pct": [50.0, 50.0]})


def test_tail_var_and_es_empirical():
    risk = analyze_historical_risk(historical_result())
    s = risk.summary
    assert s["var_pct"] == pytest.approx(3.0, abs=0.01)
    assert s["expected_shortfall_pct"] == pytest.approx(3.0, abs=0.01)
    assert s["var_inr"] == pytest.approx(s["latest_nav_inr"] * 0.03, abs=1)
    assert len(risk.history) == 120


def test_es_is_at_least_var_for_negative_tail():
    returns = np.array([-0.06] * 3 + [-0.02] * 5 + [0.004] * 112)
    r = analyze_historical_risk(historical_result(returns))
    assert r.summary["expected_shortfall_pct"] >= r.summary["var_pct"]


def test_history_drawdown_includes_initial_cash_peak():
    returns = np.array([-0.2, 0.1] + [0.0] * 118)
    r = analyze_historical_risk(historical_result(returns))
    assert r.summary["max_drawdown_pct"] == pytest.approx(-20.0)
    assert r.summary["worst_day_pct"] == pytest.approx(-20.0)


def test_all_zero_returns_have_zero_loss_risk():
    r = analyze_historical_risk(historical_result(np.zeros(120)))
    assert r.summary["annual_volatility_pct"] == pytest.approx(0)
    assert r.summary["var_inr"] == pytest.approx(0)
    assert r.summary["expected_shortfall_inr"] == pytest.approx(0)
    assert r.summary["max_drawdown_pct"] == pytest.approx(0)


def test_first_rolling_window_is_blank():
    r = analyze_historical_risk(historical_result(), rolling_sessions=21)
    assert r.history["rolling_vol_pct"].iloc[:20].isna().all()
    assert np.isfinite(r.history["rolling_vol_pct"].iloc[20:]).all()


def test_high_confidence_requires_more_observations():
    with pytest.raises(ValueError, match="at least 100"):
        analyze_historical_risk(historical_result(np.zeros(90)), confidence=0.99)


def test_historical_rejects_bad_confidence_and_window():
    with pytest.raises(ValueError, match="Confidence"):
        analyze_historical_risk(historical_result(), confidence=0.88)
    with pytest.raises(ValueError, match="Rolling window"):
        analyze_historical_risk(historical_result(), rolling_sessions=4)


def test_historical_rejects_inconsistent_daily_returns():
    result = historical_result()
    result.equity_curve.loc[5, "daily_return"] = -0.8
    with pytest.raises(ValueError, match="do not agree"):
        analyze_historical_risk(result)


def test_historical_rejects_duplicate_dates():
    result = historical_result()
    result.equity_curve.loc[2, "date"] = result.equity_curve.loc[1, "date"]
    with pytest.raises(ValueError, match="unique"):
        analyze_historical_risk(result)


def test_historical_rejects_invalid_or_negative_nav():
    result = historical_result()
    result.equity_curve.loc[5, "portfolio_inr"] = -1
    with pytest.raises(ValueError, match="positive"):
        analyze_historical_risk(result)


def test_target_weights_and_variance_attributions_conserve():
    prices = prior_prices()
    target = estimate_target_risk(prices, selections_at(prices))
    assert target.rebalance_date == prices["date"].max()
    assert target.estimation_end < target.rebalance_date
    assert target.exposures["target_weight_pct"].sum() == pytest.approx(100)
    assert target.exposures["risk_contribution_pct"].sum() == pytest.approx(100)
    assert target.estimated_vol_pct > 0


def test_target_risk_ignores_trade_day_and_future_prices():
    prices = prior_prices()
    selections = selections_at(prices)
    baseline = estimate_target_risk(prices, selections)
    altered = prices.copy()
    altered.loc[altered["date"] == selections["date"].max(), "close"] *= 10000
    later = altered[altered["date"] == selections["date"].max()].copy()
    later["date"] = later["date"] + pd.Timedelta(days=3)
    altered = pd.concat([altered, later], ignore_index=True)
    result = estimate_target_risk(altered, selections)
    pd.testing.assert_frame_equal(baseline.exposures, result.exposures)
    assert baseline.estimated_vol_pct == pytest.approx(result.estimated_vol_pct)


def test_target_risk_uses_latest_rebalance_only():
    prices = prior_prices()
    latest = selections_at(prices)
    old = latest.copy()
    old["date"] = old["date"] - pd.Timedelta(days=28)
    combined = pd.concat([old, latest], ignore_index=True)
    target = estimate_target_risk(prices, combined)
    expected = estimate_target_risk(prices, latest)
    pd.testing.assert_frame_equal(target.exposures, expected.exposures)


def test_target_invalid_weight_sum_rejected():
    prices = prior_prices()
    wrong = selections_at(prices)
    wrong["target_weight_pct"] = [60, 60]
    with pytest.raises(ValueError, match="100%"):
        estimate_target_risk(prices, wrong)


def test_target_missing_stock_rejected():
    prices = prior_prices()
    choice = selections_at(prices)
    choice.loc[1, "ticker"] = "MISSING"
    with pytest.raises(ValueError, match="Missing prices"):
        estimate_target_risk(prices, choice)


def test_target_missing_pre_rebalance_day_rejected():
    prices = prior_prices()
    choice = selections_at(prices)
    date_to_remove = prices["date"].sort_values().unique()[-25]
    prices = prices[~((prices.ticker == "AAA") & (prices.date == date_to_remove))]
    with pytest.raises(ValueError, match="complete pre-rebalance"):
        estimate_target_risk(prices, choice)


def test_target_insufficient_window_rejected():
    prices = prior_prices(n=40)
    with pytest.raises(ValueError, match="Not enough complete"):
        estimate_target_risk(prices, selections_at(prices))


def test_target_duplicate_selection_rejected():
    prices = prior_prices()
    choice = selections_at(prices)
    choice.loc[1, "ticker"] = "AAA"
    with pytest.raises(ValueError, match="unique"):
        estimate_target_risk(prices, choice)


def test_market_and_single_shock_are_separate():
    result = stress_target_portfolio(
        exposures(),
        portfolio_value_inr=100_000,
        market_shock_pct=-10,
        single_ticker="AAA",
        ticker_shock_pct=-20,
    )
    assert result["market_change_inr"] == pytest.approx(-10_000)
    assert result["market_stressed_value_inr"] == pytest.approx(90_000)
    assert result["ticker_change_inr"] == pytest.approx(-10_000)
    assert result["ticker_stressed_value_inr"] == pytest.approx(90_000)


def test_scenario_zero_shocks_do_nothing():
    result = stress_target_portfolio(
        exposures(),
        portfolio_value_inr=50_000,
        market_shock_pct=0,
        single_ticker="AAA",
        ticker_shock_pct=0,
    )
    assert result["market_change_inr"] == 0
    assert result["ticker_change_inr"] == 0


def test_scenario_rejects_bad_nav_and_shocks():
    kwargs = dict(
        exposures=exposures(),
        portfolio_value_inr=100_000,
        market_shock_pct=-10,
        single_ticker="AAA",
        ticker_shock_pct=-20,
    )
    with pytest.raises(ValueError, match="Portfolio value"):
        stress_target_portfolio(**(kwargs | {"portfolio_value_inr": 0}))
    with pytest.raises(ValueError, match="Shocks"):
        stress_target_portfolio(**(kwargs | {"ticker_shock_pct": -101}))


def test_scenario_rejects_unknown_stock_or_invalid_weights():
    kwargs = dict(
        exposures=exposures(),
        portfolio_value_inr=100_000,
        market_shock_pct=-10,
        single_ticker="AAA",
        ticker_shock_pct=-20,
    )
    with pytest.raises(ValueError, match="selected tickers"):
        stress_target_portfolio(**(kwargs | {"single_ticker": "CCC"}))
    bad = exposures()
    bad.loc[0, "target_weight_pct"] = 60
    with pytest.raises(ValueError, match="100%"):
        stress_target_portfolio(**(kwargs | {"exposures": bad}))


def test_integration_with_existing_momentum_engine():
    prices = prior_prices(n=400)
    config = BacktestConfig(lookback_sessions=80, skip_sessions=21, top_n=2)
    result = run_momentum_backtest(prices, config)
    risk = analyze_historical_risk(result)
    targets = estimate_target_risk(prices, result.selections)
    assert risk.summary["observations"] == len(result.equity_curve)
    assert set(targets.exposures.ticker) == {"AAA", "BBB"}
    assert np.isfinite(targets.estimated_vol_pct)
