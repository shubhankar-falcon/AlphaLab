"""Point-in-time momentum snapshots: no brokerage orders or implied fills."""

import json
from datetime import date
from hashlib import sha256

import numpy as np
import pandas as pd


def _digest(payload: object) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_momentum_snapshot(
    prices: pd.DataFrame,
    *,
    source: str,
    lookback_sessions: int = 252,
    skip_sessions: int = 21,
    top_n: int = 5,
    cutoff_date: date | None = None,
) -> dict:
    """Build an auditable signal from available closes, without using future data.

    The signal is *recorded*, not filled at the latest close. The observation
    date may predate the recording date; it never constitutes a live track record.
    """
    if not source or not source.strip():
        raise ValueError("A nonempty data source is required")
    if not isinstance(lookback_sessions, int) or not isinstance(skip_sessions, int):
        raise ValueError("Lookback and skip must be integers")
    if lookback_sessions <= skip_sessions or skip_sessions < 1 or top_n < 1:
        raise ValueError("Require lookback > skip >= 1, and top_n >= 1")
    required = {"date", "ticker", "close"}
    if not required.issubset(prices.columns):
        raise ValueError("Prices must have date, ticker and close columns")
    if prices.empty:
        raise ValueError("No market prices available")
    data = prices[["date", "ticker", "close"]].copy()
    data["date"] = (
        pd.to_datetime(data["date"], errors="raise", utc=True).dt.tz_localize(None).dt.normalize()
    )
    data["close"] = pd.to_numeric(data["close"], errors="raise")
    if not np.isfinite(data["close"]).all() or (data["close"] <= 0).any():
        raise ValueError("Prices must be finite and strictly positive")
    if data["ticker"].isna().any() or (data["ticker"].astype(str).str.strip() == "").any():
        raise ValueError("All tickers must be present")
    if data.duplicated(["date", "ticker"]).any():
        raise ValueError("Duplicate date/ticker observations aren't allowed")
    if cutoff_date is not None:
        data = data.loc[data["date"] <= pd.Timestamp(cutoff_date)]
    if data.empty:
        raise ValueError("No dates available before the cutoff")
    matrix = (
        data.pivot(index="date", columns="ticker", values="close").sort_index().sort_index(axis=1)
    )
    i = len(matrix.index) - 1
    if i < lookback_sessions:
        raise ValueError("Insufficient market sessions for the momentum lookback")
    # Score from t-lookback to t-skip, using the last observed close t only to
    # reject stale securities, not to compute the momentum signal.
    full_window = matrix.iloc[i - lookback_sessions : i + 1]
    eligible = full_window.notna().all(axis=0)
    scores = matrix.iloc[i - skip_sessions] / matrix.iloc[i - lookback_sessions] - 1.0
    scores = scores.loc[eligible].dropna().sort_index().sort_values(ascending=False, kind="stable")
    chosen = scores.head(top_n)
    if chosen.empty:
        raise ValueError("No stocks with complete price history")
    picks = [
        {
            "rank": rank,
            "ticker": str(ticker),
            "momentum_pct": round(float(score) * 100, 6),
            "target_weight_pct": round(100 / len(chosen), 6),
        }
        for rank, (ticker, score) in enumerate(chosen.items(), 1)
    ]
    # Capture the *formation window* hash, including prices for all candidate
    # securities; subsequent vendor revisions do not rewrite saved snapshots.
    price_fingerprint = [
        [dt.strftime("%Y-%m-%d"), str(ticker), round(float(close), 10)]
        for dt, ticker, close in data.sort_values(["date", "ticker"])
        .loc[lambda df: df["date"] >= matrix.index[i - lookback_sessions]][
            ["date", "ticker", "close"]
        ]
        .itertuples(index=False, name=None)
    ]
    settings = {
        "source": source.strip(),
        "asof_date": matrix.index[i].strftime("%Y-%m-%d"),
        "lookback_sessions": lookback_sessions,
        "skip_sessions": skip_sessions,
        "top_n": top_n,
        "universe_sha256": _digest(sorted(str(ticker) for ticker in matrix.columns)),
    }
    return {
        **settings,
        "strategy": (
            "12-1 momentum" if (lookback_sessions, skip_sessions) == (252, 21) else "momentum"
        ),
        "formation_start": matrix.index[i - lookback_sessions].strftime("%Y-%m-%d"),
        "formation_end": matrix.index[i - skip_sessions].strftime("%Y-%m-%d"),
        "prices_sha256": _digest(price_fingerprint),
        "settings_sha256": _digest(settings),
        "picks": picks,
    }
