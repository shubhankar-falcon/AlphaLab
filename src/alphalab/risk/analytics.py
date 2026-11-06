"""Historically observed risk and *signal-time* target-allocation risk.

These calculations are descriptive educational research, not risk forecasts.
No prices are fetched here. No trading, broker or paper-portfolio state is changed.
"""

from dataclasses import dataclass
from math import sqrt

import numpy as np
import pandas as pd

from alphalab.backtesting.engine import BacktestResult, _make_matrix


@dataclass(frozen=True)
class HistoricalRisk:
    """Realized risk from a complete historical strategy equity curve."""

    history: pd.DataFrame
    summary: dict[str, float | int]


@dataclass(frozen=True)
class TargetRisk:
    """Covariance estimate for targets at the *last historical rebalance*."""

    exposures: pd.DataFrame
    rebalance_date: pd.Timestamp
    estimation_start: pd.Timestamp
    estimation_end: pd.Timestamp
    estimated_vol_pct: float
    sessions: int


def analyze_historical_risk(
    backtest: BacktestResult,
    *,
    confidence: float = 0.95,
    rolling_sessions: int = 63,
) -> HistoricalRisk:
    """Historical one-day VaR / ES and rolling annual volatility.

    Uses daily *net* strategy returns, including modeled transaction costs.
    VaR and ES are empirical return-tail statistics; NOT worst-case limits or
    future-loss guarantees. The latest NAV converts percent loss to INR.
    """
    if confidence not in (0.95, 0.99):
        raise ValueError("Confidence must be 0.95 or 0.99")
    if not isinstance(rolling_sessions, int) or not 5 <= rolling_sessions <= 252:
        raise ValueError("Rolling window must be 5 to 252 trading sessions")

    curve = backtest.equity_curve
    required = {"date", "portfolio_inr", "daily_return"}
    if curve.empty or not required.issubset(curve.columns):
        raise ValueError("Equity curve must include date, portfolio_inr and daily_return")
    initial = float(backtest.summary["starting_cash"])
    if not np.isfinite(initial) or initial <= 0:
        raise ValueError("Starting cash must be positive and finite")

    dates = pd.DatetimeIndex(pd.to_datetime(curve["date"], errors="coerce"))
    if dates.hasnans or dates.has_duplicates or not dates.is_monotonic_increasing:
        raise ValueError("Equity dates must be valid, unique and chronological")
    if dates.tz is not None:
        raise ValueError("Equity dates must be timezone-naive trading dates")
    dates = dates.normalize()
    if dates.has_duplicates:
        raise ValueError("Equity dates must be unique trading dates")
    nav = pd.to_numeric(curve["portfolio_inr"], errors="coerce").to_numpy(dtype=float)
    reported_returns = pd.to_numeric(curve["daily_return"], errors="coerce").to_numpy(
        dtype=float
    )
    if not np.isfinite(nav).all() or (nav <= 0).any():
        raise ValueError("Portfolio values must be positive and finite")
    if not np.isfinite(reported_returns).all():
        raise ValueError("Daily returns must be finite")
    previous = np.r_[initial, nav[:-1]]
    returns = nav / previous - 1.0
    if not np.allclose(returns, reported_returns, atol=1e-8, rtol=1e-8):
        raise ValueError("Daily returns do not agree with the equity curve")
    minimum = 100 if confidence == 0.99 else 60
    if len(returns) < max(minimum, rolling_sessions):
        raise ValueError(
            f"Insufficient daily observations: need at least {max(minimum, rolling_sessions)}"
        )

    lower_quantile = float(np.quantile(returns, 1.0 - confidence))
    tail = returns[returns <= lower_quantile]
    var_fraction = max(0.0, -lower_quantile)
    es_fraction = max(0.0, -float(np.mean(tail)))
    std = float(np.std(returns, ddof=1))
    peaks = np.maximum.accumulate(np.r_[initial, nav])[1:]
    drawdowns = 100.0 * (nav / peaks - 1.0)
    rolling_vol = (
        pd.Series(returns).rolling(rolling_sessions, min_periods=rolling_sessions).std()
        * sqrt(252)
        * 100.0
    )
    history = pd.DataFrame(
        {
            "date": dates,
            "portfolio_inr": nav,
            "daily_return_pct": 100.0 * returns,
            "drawdown_pct": drawdowns,
            "rolling_vol_pct": rolling_vol.to_numpy(),
        }
    )
    return HistoricalRisk(
        history=history,
        summary={
            "observations": len(returns),
            "latest_nav_inr": float(nav[-1]),
            "annual_volatility_pct": 100.0 * std * sqrt(252),
            "max_drawdown_pct": float(np.min(drawdowns)),
            "worst_day_pct": 100.0 * float(np.min(returns)),
            "var_pct": 100.0 * var_fraction,
            "expected_shortfall_pct": 100.0 * es_fraction,
            "var_inr": float(nav[-1]) * var_fraction,
            "expected_shortfall_inr": float(nav[-1]) * es_fraction,
            "confidence_pct": 100.0 * confidence,
        },
    )


def estimate_target_risk(
    prices: pd.DataFrame,
    selections: pd.DataFrame,
    *,
    estimation_sessions: int = 63,
) -> TargetRisk:
    """Estimate risk of the last rebalance's *target* weights using only prior closes.

    This is NOT the current paper portfolio or drifted, currently held weights.
    The rebalancing date's adjusted close and every later observation are
    explicitly excluded to avoid look-ahead in the covariance estimate.
    """
    if not isinstance(estimation_sessions, int) or not 20 <= estimation_sessions <= 252:
        raise ValueError("Estimation window must be 20 to 252 sessions")
    needed = {"date", "ticker", "target_weight_pct"}
    if selections.empty or not needed.issubset(selections.columns):
        raise ValueError("Selections must include date, ticker and target_weight_pct")
    selections = selections.copy()
    selections["date"] = pd.to_datetime(selections["date"], errors="coerce")
    if selections["date"].isna().any():
        raise ValueError("Selection dates must be valid")
    if getattr(selections["date"].dt, "tz", None) is not None:
        raise ValueError("Selection dates must be timezone-naive")
    selections["date"] = selections["date"].dt.normalize()
    rebalance_date = selections["date"].max()
    latest = selections[selections["date"] == rebalance_date].copy()
    if latest["ticker"].isna().any() or latest["ticker"].astype(str).str.strip().eq("").any():
        raise ValueError("Selected tickers must be valid")
    if latest["ticker"].duplicated().any():
        raise ValueError("Selected tickers must be unique")
    weights = pd.to_numeric(latest["target_weight_pct"], errors="coerce").to_numpy(
        dtype=float
    ) / 100.0
    if not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError("All target weights must be positive and finite")
    if not np.isclose(weights.sum(), 1.0, atol=1e-6):
        raise ValueError("Target weights must add to 100%")
    tickers = latest["ticker"].astype(str).to_list()

    matrix = _make_matrix(prices)
    missing = sorted(set(tickers) - set(matrix.columns))
    if missing:
        raise ValueError("Missing prices for selected stocks: " + ", ".join(missing))
    # Crucial: estimate risk using only data available before rebalance date.
    history = matrix.loc[matrix.index < rebalance_date, tickers].tail(estimation_sessions + 1)
    if len(history) != estimation_sessions + 1 or history.isna().any().any():
        raise ValueError("Not enough complete pre-rebalance price history for target risk")
    returns = history.pct_change(fill_method=None).iloc[1:]
    if not np.isfinite(returns.to_numpy(dtype=float)).all():
        raise ValueError("Target risk returns must be finite")
    covariance_daily = np.atleast_2d(np.cov(returns.to_numpy(), rowvar=False, ddof=1))
    variance_daily = float(weights @ covariance_daily @ weights)
    if not np.isfinite(variance_daily) or variance_daily < -1e-12:
        raise ValueError("Invalid covariance estimate")
    variance_daily = max(variance_daily, 0.0)
    variance_contributions = (
        100.0 * weights * (covariance_daily @ weights) / variance_daily
        if variance_daily > 1e-20
        else np.zeros(len(weights))
    )
    standalone_vol = 100.0 * np.sqrt(np.diag(covariance_daily).clip(min=0) * 252)
    exposure = pd.DataFrame(
        {
            "ticker": tickers,
            "target_weight_pct": 100.0 * weights,
            "standalone_vol_pct": standalone_vol,
            "risk_contribution_pct": variance_contributions,
        }
    )
    return TargetRisk(
        exposures=exposure,
        rebalance_date=rebalance_date,
        estimation_start=history.index[0],
        estimation_end=history.index[-1],
        estimated_vol_pct=100.0 * sqrt(variance_daily * 252),
        sessions=estimation_sessions,
    )


def stress_target_portfolio(
    exposures: pd.DataFrame,
    *,
    portfolio_value_inr: float,
    market_shock_pct: float,
    single_ticker: str,
    ticker_shock_pct: float,
) -> dict[str, float]:
    """Independent linear shocks to frozen *target* weights, not real holdings.

    Market shock: all selected stocks move by the same percent; single-stock
    shock: only the selected name moves. Cash, correlations, taxes and
    second-order effects are absent. The two scenarios are NOT combined.
    """
    if not np.isfinite(portfolio_value_inr) or portfolio_value_inr <= 0:
        raise ValueError("Portfolio value must be positive and finite")
    for shock in (market_shock_pct, ticker_shock_pct):
        if not np.isfinite(shock) or not -100 <= shock <= 100:
            raise ValueError("Shocks must be finite percentages between -100 and +100")
    if exposures.empty or not {"ticker", "target_weight_pct"}.issubset(exposures.columns):
        raise ValueError("Target exposures are required")
    if exposures["ticker"].duplicated().any() or single_ticker not in set(exposures["ticker"]):
        raise ValueError("Choose exactly one of the selected tickers")
    weights = pd.to_numeric(exposures["target_weight_pct"], errors="coerce").to_numpy(
        dtype=float
    ) / 100.0
    if not np.isfinite(weights).all() or (weights < 0).any():
        raise ValueError("Target exposure weights must be finite and nonnegative")
    if not np.isclose(weights.sum(), 1.0, atol=1e-6):
        raise ValueError("Target exposure weights must add to 100%")
    target_weight = float(
        exposures.loc[exposures["ticker"] == single_ticker, "target_weight_pct"].iloc[0]
    ) / 100.0
    market_change = portfolio_value_inr * float(weights.sum()) * market_shock_pct / 100.0
    ticker_change = portfolio_value_inr * target_weight * ticker_shock_pct / 100.0
    return {
        "market_change_inr": market_change,
        "market_stressed_value_inr": portfolio_value_inr + market_change,
        "ticker_change_inr": ticker_change,
        "ticker_stressed_value_inr": portfolio_value_inr + ticker_change,
    }
