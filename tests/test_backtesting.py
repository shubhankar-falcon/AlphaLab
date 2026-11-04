"""Backtest engine contracts, including prevention of look-ahead bias."""

import numpy as np
import pandas as pd
import pytest

from alphalab.backtesting import BacktestConfig, run_momentum_backtest


def prices_fixture(length=340):
    dates = pd.bdate_range("2024-01-01", periods=length)
    rows = []
    for ticker, growth in [("AAA", 1.003), ("BBB", 1.001), ("CCC", 0.999)]:
        close = 100.0 * growth ** np.arange(length)
        rows.append(pd.DataFrame({"date": dates, "ticker": ticker, "close": close}))
    return pd.concat(rows, ignore_index=True)


def cfg(**kwargs):
    return BacktestConfig(lookback_sessions=60, skip_sessions=5, top_n=1, **kwargs)


def test_selects_strongest_momentum_and_logs_it():
    result = run_momentum_backtest(prices_fixture(), cfg(cost_bps=0))
    assert set(result.selections["ticker"]) == {"AAA"}
    assert result.summary["ending_value"] > 100_000
    assert result.summary["rebalance_count"] > 1


def test_first_trade_does_not_use_same_day_price_for_ranking():
    prices = prices_fixture()
    out1 = run_momentum_backtest(prices, cfg(cost_bps=0))
    first_trade = out1.selections.iloc[0]["date"]
    # A massive *trade-day* gain in the weakest stock can't change trade-day picks.
    prices.loc[(prices.ticker == "CCC") & (prices.date == first_trade), "close"] *= 1_000
    out2 = run_momentum_backtest(prices, cfg(cost_bps=0))
    assert out1.selections.iloc[0]["ticker"] == out2.selections.iloc[0]["ticker"]


def test_new_position_earns_no_trade_day_return():
    result = run_momentum_backtest(prices_fixture(), cfg(cost_bps=0))
    assert result.equity_curve.iloc[0]["portfolio_inr"] == pytest.approx(100_000)
    assert result.equity_curve.iloc[0]["daily_return"] == pytest.approx(0)
    assert result.equity_curve.iloc[1]["portfolio_inr"] > 100_000


def test_fees_reduce_portfolio_equity():
    data = prices_fixture()
    free = run_momentum_backtest(data, cfg(cost_bps=0))
    paid = run_momentum_backtest(data, cfg(cost_bps=10))
    assert paid.summary["total_cost_inr"] > 0
    assert paid.summary["ending_value"] < free.summary["ending_value"]
    assert paid.equity_curve.iloc[0]["portfolio_inr"] < 100_000


def test_first_trade_buy_only_cost_is_correct():
    paid = run_momentum_backtest(prices_fixture(), cfg(cost_bps=10))
    first = paid.rebalances.iloc[0]
    # 10 bps invested at post-fee NAV: 100000/1.001 is invested.
    assert first["cost_inr"] == pytest.approx(100_000 / 1001, rel=1e-9)
    assert first["gross_turnover_pct"] == pytest.approx(100 / 1.001)


def test_monthly_rebalance_at_most_once_per_calendar_month():
    out = run_momentum_backtest(prices_fixture(), cfg(cost_bps=0))
    months = out.rebalances["date"].dt.to_period("M")
    assert months.is_unique
    assert (out.rebalances["stocks"] == 1).all()


def test_require_sufficient_history():
    with pytest.raises(ValueError, match="Not enough"):
        run_momentum_backtest(prices_fixture(60), cfg(cost_bps=0))


def test_zero_or_duplicate_prices_are_rejected():
    data = prices_fixture(100)
    data.loc[0, "close"] = 0
    with pytest.raises(ValueError, match="positive"):
        run_momentum_backtest(data, cfg(cost_bps=0))

    data = prices_fixture(100)
    data = pd.concat([data, data.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="Duplicate"):
        run_momentum_backtest(data, cfg(cost_bps=0))


def test_missing_owned_price_fails_instead_of_faking_flat_return():
    data = prices_fixture()
    first_trade_date = pd.bdate_range("2024-01-01", periods=62)[-1]
    next_date = first_trade_date + pd.offsets.BDay(1)
    data = data[~((data.ticker == "AAA") & (data.date == next_date))]
    with pytest.raises(ValueError, match="Missing prices for held securities"):
        run_momentum_backtest(data, cfg(cost_bps=0))


def test_tie_break_is_alphabetical():
    dates = pd.bdate_range("2024-01-01", periods=100)
    data = pd.concat(
        [
            pd.DataFrame({"date": dates, "ticker": symbol, "close": np.arange(1, 101)})
            for symbol in ("Z", "A")
        ],
        ignore_index=True,
    )
    out = run_momentum_backtest(data, cfg(cost_bps=0))
    assert out.selections.iloc[0]["ticker"] == "A"


def test_returns_and_drawdown_finite():
    out = run_momentum_backtest(prices_fixture(), cfg(cost_bps=10))
    assert np.isfinite(out.equity_curve["daily_return"]).all()
    assert np.isfinite(out.equity_curve["drawdown_pct"]).all()
    assert (out.equity_curve["drawdown_pct"] <= 0).all()


def test_config_rejects_bad_values():
    with pytest.raises(ValueError, match="lookback"):
        BacktestConfig(lookback_sessions=10, skip_sessions=10)
    with pytest.raises(ValueError, match="cost_bps"):
        BacktestConfig(cost_bps=-1)
    with pytest.raises(ValueError, match="starting_cash"):
        BacktestConfig(starting_cash=0)
