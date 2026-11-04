"""Deterministic synthetic data for local development. NOT REAL STOCK PRICES."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Labels are recognizable NSE tickers, but their prices below are entirely made up.
DEMO_TICKERS: tuple[str, ...] = (
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "INFY.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "ITC.NS",
    "LT.NS",
    "AXISBANK.NS",
    "KOTAKBANK.NS",
    "HINDUNILVR.NS",
    "BAJFINANCE.NS",
    "MARUTI.NS",
    "SUNPHARMA.NS",
    "TITAN.NS",
    "NTPC.NS",
    "TMPV.NS",
    "WIPRO.NS",
    "POWERGRID.NS",
)


@dataclass(frozen=True)
class DemoPriceProvider:
    """Reproducible sample data. A future NSE/paid vendor can implement the same interface."""

    seed: int = 42

    def get_prices(self) -> pd.DataFrame:
        dates = pd.bdate_range("2025-01-01", "2026-10-30")
        rng = np.random.default_rng(self.seed)
        frames: list[pd.DataFrame] = []

        for index, ticker in enumerate(DEMO_TICKERS):
            # Intentional variation between stocks makes the screener interesting.
            daily_drift = 0.0001 + 0.00007 * (index % 6)
            returns = rng.normal(
                loc=daily_drift,
                scale=0.012 + 0.001 * (index % 4),
                size=len(dates),
            )
            prices = (100.0 * np.cumprod(1.0 + returns)).round(2)
            frames.append(pd.DataFrame({"date": dates, "ticker": ticker, "close": prices}))

        return pd.concat(frames, ignore_index=True)
