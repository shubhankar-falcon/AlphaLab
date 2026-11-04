"""Business rules have automated tests independent of the UI."""

import pandas as pd
import pytest

from alphalab.strategies.momentum import screen_momentum


def prices_for(ticker: str, closes: list[float], start: str = "2026-01-01") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.bdate_range(start, periods=len(closes)),
            "ticker": ticker,
            "close": closes,
        }
    )


def test_momentum_ranks_highest_return_first():
    prices = pd.concat(
        [prices_for("UP", [100, 105, 110]), prices_for("DOWN", [100, 95, 90])],
        ignore_index=True,
    )

    result = screen_momentum(prices, lookback_sessions=2, top_n=2)

    assert result["ticker"].tolist() == ["UP", "DOWN"]
    assert result["momentum_pct"].tolist() == pytest.approx([10.0, -10.0])
    assert result["rank"].tolist() == [1, 2]


def test_insufficient_history_is_excluded():
    prices = pd.concat(
        [prices_for("OLD", [10, 11, 12]), prices_for("NEW", [20, 21])],
        ignore_index=True,
    )
    result = screen_momentum(prices, lookback_sessions=2)
    assert result["ticker"].tolist() == ["OLD"]


def test_stale_stock_is_excluded():
    prices = pd.concat(
        [
            prices_for("CURRENT", [100, 105, 110]),
            prices_for("STALE", [100, 110, 120], "2025-12-31"),
        ],
        ignore_index=True,
    )
    result = screen_momentum(prices, lookback_sessions=2)
    assert result["ticker"].tolist() == ["CURRENT"]


def test_reject_invalid_prices():
    with pytest.raises(ValueError, match="positive"):
        screen_momentum(prices_for("BAD", [10, 0, 20]), lookback_sessions=2)


def test_empty_frame_returns_empty_result():
    empty = pd.DataFrame(columns=["date", "ticker", "close"])
    assert screen_momentum(empty).empty
