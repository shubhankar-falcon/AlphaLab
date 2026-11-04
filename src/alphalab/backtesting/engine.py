"""Educational, close-price, long-only momentum backtester.

Financial assumptions are documented in docs/backtesting_v03.md.
No network or Streamlit dependencies are used by this engine.
"""

from dataclasses import dataclass
from math import sqrt

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BacktestConfig:
    """Parameters for 12-1 (or another lookback/skip) momentum research."""

    lookback_sessions: int = 252
    skip_sessions: int = 21
    top_n: int = 5
    cost_bps: float = 10.0
    starting_cash: float = 100_000.0

    def __post_init__(self) -> None:
        if not (self.lookback_sessions > self.skip_sessions >= 1):
            raise ValueError("lookback_sessions must exceed skip_sessions >= 1")
        if self.top_n < 1:
            raise ValueError("top_n must be at least 1")
        if not 0 <= self.cost_bps <= 1000 or not np.isfinite(self.cost_bps):
            raise ValueError("cost_bps must be finite and between 0 and 1000")
        if not np.isfinite(self.starting_cash) or self.starting_cash <= 0:
            raise ValueError("starting_cash must be positive and finite")


@dataclass
class BacktestResult:
    """Equity curve, rebalance records, and reproducible summary statistics."""

    equity_curve: pd.DataFrame
    rebalances: pd.DataFrame
    selections: pd.DataFrame
    summary: dict[str, float | int]


def _make_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "ticker", "close"}
    if not required.issubset(prices.columns):
        raise ValueError("Prices must include date, ticker, and close columns")
    if prices.empty:
        raise ValueError("Price input is empty")

    data = prices.loc[:, ["date", "ticker", "close"]].copy()
    data["date"] = pd.to_datetime(data["date"], errors="raise")
    if data["date"].isna().any():
        raise ValueError("Price dates must not be missing")
    if getattr(data["date"].dt, "tz", None) is not None:
        data["date"] = data["date"].dt.tz_localize(None)
    data["date"] = data["date"].dt.normalize()
    data["close"] = pd.to_numeric(data["close"], errors="raise")
    if data["ticker"].isna().any() or (data["ticker"].astype(str).str.strip() == "").any():
        raise ValueError("Every row must have a valid ticker")
    if not np.isfinite(data["close"]).all() or (data["close"] <= 0).any():
        raise ValueError("Closing prices must be finite and positive")
    if data.duplicated(["date", "ticker"]).any():
        raise ValueError("Duplicate date/ticker price observations are not allowed")

    matrix = data.pivot(index="date", columns="ticker", values="close").sort_index()
    matrix = matrix.sort_index(axis=1)
    return matrix.astype(float)


def _weights_for_rebalance(
    matrix: pd.DataFrame, i: int, config: BacktestConfig
) -> tuple[dict[str, float], dict[str, float]]:
    """Use data through the *previous* close to pick today's close orders."""
    old_idx = i - 1 - config.lookback_sessions
    recent_idx = i - 1 - config.skip_sessions
    prior_history = matrix.iloc[old_idx:i]
    # A symbol needs uninterrupted historical closes and a tradable close today.
    eligible = prior_history.notna().all(axis=0) & matrix.iloc[i].notna()
    if not eligible.any():
        return {}, {}
    scores = matrix.iloc[recent_idx] / matrix.iloc[old_idx] - 1.0
    scores = scores[eligible].dropna().sort_index().sort_values(ascending=False, kind="stable")
    chosen = scores.head(config.top_n)
    if chosen.empty:
        return {}, {}
    weight = 1.0 / len(chosen)
    return {str(ticker): weight for ticker in chosen.index}, {
        str(ticker): float(score) for ticker, score in chosen.items()
    }


def _rebalance_portfolio(
    nav: float,
    old_values: dict[str, float],
    weights: dict[str, float],
    closes: pd.Series,
    cost_rate: float,
) -> tuple[dict[str, float], float, float, float]:
    """Allocate a post-fee NAV, charging bps on all buy AND sell notional.

    Solve the tiny fixed-point equation so costs are actually funded from cash,
    rather than quietly treating pre-fee value as fully investable.
    """
    candidates = set(old_values) | set(weights)
    post_fee = nav
    for _ in range(100):
        traded = sum(
            abs(weights.get(ticker, 0.0) * post_fee - old_values.get(ticker, 0.0))
            for ticker in candidates
        )
        next_post_fee = nav - traded * cost_rate
        if next_post_fee <= 0:
            raise ValueError("Transaction costs would exhaust the portfolio")
        if abs(next_post_fee - post_fee) < 1e-10:
            post_fee = next_post_fee
            break
        post_fee = next_post_fee

    traded = sum(
        abs(weights.get(ticker, 0.0) * post_fee - old_values.get(ticker, 0.0))
        for ticker in candidates
    )
    fee = cost_rate * traded
    post_fee = nav - fee
    shares = {
        ticker: weight * post_fee / float(closes[ticker]) for ticker, weight in weights.items()
    }
    residual_cash = post_fee - sum(shares[ticker] * float(closes[ticker]) for ticker in shares)
    return shares, residual_cash, traded, fee


def run_momentum_backtest(prices: pd.DataFrame, config: BacktestConfig) -> BacktestResult:
    """Run one forward-only historical simulation against adjusted daily closes.

    At day t, a selection uses prices at or before day t-1, trades at day t
    close (a simplified fill), and is exposed to returns beginning day t+1.
    Rebalances happen on the first observed trading session of each new month.
    Missing marks for an owned stock stop the simulation rather than being
    assumed to equal a zero return.
    """
    matrix = _make_matrix(prices)
    first_idx = config.lookback_sessions + 1
    if len(matrix.index) <= first_idx:
        raise ValueError("Not enough trading sessions for lookback plus signal lag")

    cash = config.starting_cash
    shares: dict[str, float] = {}
    last_rebalance_month = None
    previous_nav = config.starting_cash
    total_fees = 0.0
    equity_rows: list[dict] = []
    rebalance_rows: list[dict] = []
    selection_rows: list[dict] = []
    cost_rate = config.cost_bps / 10_000.0

    for i in range(first_idx, len(matrix.index)):
        today = matrix.index[i]
        closes = matrix.iloc[i]
        unavailable = sorted(ticker for ticker in shares if pd.isna(closes[ticker]))
        if unavailable:
            raise ValueError(
                f"Missing prices for held securities on {today.date()}: " + ", ".join(unavailable)
            )
        old_values = {ticker: qty * float(closes[ticker]) for ticker, qty in shares.items()}
        gross_nav = cash + sum(old_values.values())
        fees_today = 0.0
        turnover_today = 0.0
        month = today.to_period("M")

        if last_rebalance_month != month:
            weights, scores = _weights_for_rebalance(matrix, i, config)
            if not weights and not shares:
                raise ValueError("No eligible stocks had a complete formation window")
            if weights:
                shares, cash, traded, fees_today = _rebalance_portfolio(
                    gross_nav, old_values, weights, closes, cost_rate
                )
                turnover_today = traded / gross_nav
                total_fees += fees_today
                last_rebalance_month = month
                rebalance_rows.append(
                    {
                        "date": today,
                        "stocks": len(weights),
                        "gross_turnover_pct": 100.0 * turnover_today,
                        "cost_inr": fees_today,
                    }
                )
                selection_rows.extend(
                    {
                        "date": today,
                        "ticker": ticker,
                        "signal_pct": 100.0 * scores[ticker],
                        "target_weight_pct": 100.0 * weight,
                    }
                    for ticker, weight in weights.items()
                )

        nav = gross_nav - fees_today
        if nav <= 0:
            raise ValueError("Portfolio value became nonpositive")
        equity_rows.append(
            {
                "date": today,
                "portfolio_inr": nav,
                "daily_return": nav / previous_nav - 1.0,
                "cost_inr": fees_today,
                "gross_turnover_pct": 100.0 * turnover_today,
            }
        )
        previous_nav = nav

    curve = pd.DataFrame(equity_rows)
    peaks = np.maximum.accumulate(np.r_[config.starting_cash, curve["portfolio_inr"].to_numpy()])
    curve["drawdown_pct"] = 100.0 * (curve["portfolio_inr"] / peaks[1:] - 1.0)
    returns = curve["daily_return"]
    std = float(returns.std(ddof=1))
    sharpe = float(sqrt(252) * returns.mean() / std) if std > 0 else float("nan")
    final_nav = float(curve["portfolio_inr"].iloc[-1])
    summary: dict[str, float | int] = {
        "starting_cash": config.starting_cash,
        "ending_value": final_nav,
        "total_return_pct": 100.0 * (final_nav / config.starting_cash - 1.0),
        "cagr_pct": 100.0 * ((final_nav / config.starting_cash) ** (252 / len(curve)) - 1.0),
        "max_drawdown_pct": float(curve["drawdown_pct"].min()),
        "annual_volatility_pct": 100.0 * std * sqrt(252),
        "sharpe_zero_rf": sharpe,
        "total_cost_inr": total_fees,
        "rebalance_count": len(rebalance_rows),
        "days_tested": len(curve),
    }
    return BacktestResult(
        equity_curve=curve,
        rebalances=pd.DataFrame(rebalance_rows),
        selections=pd.DataFrame(selection_rows),
        summary=summary,
    )
