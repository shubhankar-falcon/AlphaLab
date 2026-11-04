"""Offline tests for Yahoo market-data normalization (no API calls)."""

import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from alphalab.data.yahoo import (
    MarketDataError,
    YahooFinancePriceProvider,
    normalize_yahoo_prices,
)


def test_normalize_multi_ticker_response():
    dates = pd.date_range("2026-10-27", periods=3, freq="D")
    columns = pd.MultiIndex.from_tuples([("TCS.NS", "Close"), ("INFY.NS", "Close")])
    raw = pd.DataFrame([[100, 200], [110, 190], [120, 195]], index=dates, columns=columns)
    result = normalize_yahoo_prices(raw, ("TCS.NS", "INFY.NS"))

    assert list(result.columns) == ["date", "ticker", "close"]
    assert len(result) == 6
    assert result.loc[result["ticker"] == "TCS.NS", "close"].tolist() == [100, 110, 120]


def test_normalize_single_flat_ticker():
    dates = pd.date_range("2026-10-27", periods=2)
    raw = pd.DataFrame({"Close": [42.0, 43.0]}, index=dates)
    result = normalize_yahoo_prices(raw, ("TCS.NS",))
    assert result["close"].tolist() == [42.0, 43.0]


def test_normalize_skips_missing_symbols_and_bad_prices():
    dates = pd.date_range("2026-10-27", periods=3)
    columns = pd.MultiIndex.from_tuples([("TCS.NS", "Close")])
    raw = pd.DataFrame([[100.0], [float("inf")], [-5.0]], index=dates, columns=columns)
    result = normalize_yahoo_prices(raw, ("TCS.NS", "BAD.NS"))
    assert len(result) == 1
    assert result.iloc[0]["ticker"] == "TCS.NS"


def test_no_prices_raises_clear_error():
    with pytest.raises(MarketDataError, match="no historical prices"):
        normalize_yahoo_prices(pd.DataFrame(), ("TCS.NS",))


def test_provider_uses_adjusted_daily_prices(monkeypatch):
    dates = pd.date_range("2026-10-27", periods=2)
    columns = pd.MultiIndex.from_tuples([("TCS.NS", "Close")])
    raw = pd.DataFrame([[100.0], [103.0]], index=dates, columns=columns)
    captured = {}

    def fake_download(**kwargs):
        captured.update(kwargs)
        return raw

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=fake_download))
    result = YahooFinancePriceProvider(tickers=("TCS.NS",)).get_prices()
    assert captured["auto_adjust"] is True
    assert captured["interval"] == "1d"
    assert result["close"].tolist() == [100.0, 103.0]


def test_provider_explains_download_failure(monkeypatch):
    def fake_download(**kwargs):
        raise ConnectionError("simulated provider failure")

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=fake_download))
    with pytest.raises(MarketDataError, match="download failed"):
        YahooFinancePriceProvider(tickers=("TCS.NS",)).get_prices()
