"""A simple trailing-return screener; NOT a prediction or backtest."""

from math import sqrt

import pandas as pd

OUTPUT_COLUMNS = ["rank", "ticker", "momentum_pct", "volatility_pct", "last_close"]


def screen_momentum(
    prices: pd.DataFrame, lookback_sessions: int = 126, top_n: int = 10
) -> pd.DataFrame:
    """Rank stocks by trailing return using only prices available at the latest date.

    A 'session' is one available trading-price observation. We require the latest
    observation on the same date for all ranked securities to avoid stale picks.
    Volatility is annualized historical daily return std dev, not a risk forecast.
    """
    if lookback_sessions < 2 or top_n < 1:
        raise ValueError("lookback_sessions must be >= 2 and top_n must be >= 1")

    required = {"date", "ticker", "close"}
    if not required.issubset(prices.columns):
        raise ValueError(f"Expected price columns: {', '.join(sorted(required))}")

    df = prices.loc[:, ["date", "ticker", "close"]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="raise")
    df["close"] = pd.to_numeric(df["close"], errors="raise")
    if df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    if df["close"].isna().any() or (df["close"] <= 0).any():
        raise ValueError("Close prices must be positive and non-null")
    if df["ticker"].isna().any():
        raise ValueError("Tickers must not be null")

    df = df.sort_values(["ticker", "date"]).drop_duplicates(
        subset=["ticker", "date"], keep="last"
    )
    latest_date = df["date"].max()
    picks: list[dict[str, float | str]] = []

    for ticker, group in df.groupby("ticker", sort=True):
        # Inactive/stale symbols aren't included in current rankings.
        if group["date"].iloc[-1] != latest_date or len(group) < lookback_sessions + 1:
            continue
        window = group.tail(lookback_sessions + 1)
        start_close = float(window["close"].iloc[0])
        end_close = float(window["close"].iloc[-1])
        daily_returns = window["close"].pct_change().dropna()
        momentum = (end_close / start_close - 1.0) * 100.0
        annual_vol = float(daily_returns.std(ddof=1) * sqrt(252) * 100.0)
        picks.append(
            {
                "ticker": str(ticker),
                "momentum_pct": momentum,
                "volatility_pct": annual_vol,
                "last_close": end_close,
            }
        )

    if not picks:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    result = pd.DataFrame(picks).sort_values(
        ["momentum_pct", "ticker"], ascending=[False, True]
    )
    result = result.head(top_n).reset_index(drop=True)
    result.insert(0, "rank", range(1, len(result) + 1))
    return result.loc[:, OUTPUT_COLUMNS]
