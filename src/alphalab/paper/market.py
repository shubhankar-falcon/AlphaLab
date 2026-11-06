"""Experimental *unadjusted* close fetcher for simulated paper executions.

This is deliberately independent of the research signal provider, which uses
historically adjusted prices. Yahoo data is for personal research only.
"""

import pandas as pd

from alphalab.data.yahoo import MarketDataError, normalize_yahoo_prices


def fetch_yahoo_raw_closes(tickers: tuple[str, ...], period: str = "5y") -> pd.DataFrame:
    """Fetch EOD raw Close, not retrospectively adjusted Close."""
    if not tickers:
        raise ValueError("At least one symbol is required")
    if len(tickers) != len(set(tickers)):
        raise ValueError("Duplicate symbols supplied")
    import yfinance as yf

    try:
        raw = yf.download(
            tickers=list(tickers),
            period=period,
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=False,
            multi_level_index=True,
            timeout=20,
        )
    except Exception as exc:
        raise MarketDataError("Could not retrieve raw stock closes") from exc
    if not isinstance(raw, pd.DataFrame):
        raise MarketDataError("Yahoo returned unexpected price data")
    return normalize_yahoo_prices(raw, tickers)
