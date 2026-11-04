"""Yahoo Finance daily adjusted-close provider for personal research only.

This adapter deliberately returns the same three-column schema as the demo
provider so strategies never depend directly on a vendor's API response.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from alphalab.data.demo import DEMO_TICKERS


class MarketDataError(RuntimeError):
    """Raised when requested market data cannot be used safely."""


def normalize_yahoo_prices(raw: pd.DataFrame, tickers: tuple[str, ...]) -> pd.DataFrame:
    """Convert Yahoo's wide daily price response into date/ticker/close rows.

    Handles flat columns (one ticker) and ticker-first MultiIndex columns.
    Missing symbols and invalid prices are omitted, never fabricated.
    """
    frames: list[pd.DataFrame] = []
    if raw.empty:
        raise MarketDataError("Yahoo Finance returned no historical prices.")

    dates = pd.DatetimeIndex(pd.to_datetime(raw.index)).tz_localize(None).normalize()
    for ticker in tickers:
        if isinstance(raw.columns, pd.MultiIndex):
            if ticker not in raw.columns.get_level_values(0):
                continue
            ticker_frame = raw[ticker]
        elif len(tickers) == 1:
            ticker_frame = raw
        else:
            raise MarketDataError("Unexpected Yahoo Finance response columns.")

        if "Close" not in ticker_frame:
            continue
        closes = pd.to_numeric(ticker_frame["Close"], errors="coerce")
        frame = pd.DataFrame({"date": dates, "ticker": ticker, "close": closes.to_numpy()})
        frame = frame.loc[np.isfinite(frame["close"]) & (frame["close"] > 0)]
        if not frame.empty:
            frames.append(frame)

    if not frames:
        raise MarketDataError("No valid closing prices were returned for these tickers.")
    return pd.concat(frames, ignore_index=True).sort_values(["ticker", "date"])


@dataclass(frozen=True)
class YahooFinancePriceProvider:
    """Historical prices via yfinance. Not suitable for licensed redistribution."""

    tickers: tuple[str, ...] = DEMO_TICKERS
    period: str = "2y"

    def get_prices(self) -> pd.DataFrame:
        import yfinance as yf

        try:
            raw = yf.download(
                tickers=list(self.tickers),
                period=self.period,
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=False,
                multi_level_index=True,
                timeout=20,
            )
        except Exception as exc:
            raise MarketDataError("Market data download failed. Retry later.") from exc
        if not isinstance(raw, pd.DataFrame):
            raise MarketDataError("Market data provider returned an unexpected response.")
        return normalize_yahoo_prices(raw, self.tickers)
