"""Benchmark data contracts and apples-to-apples portfolio comparisons.

A *real* Nifty 500 total-return comparison requires an externally sourced
Total Return Index CSV. We never silently substitute a price-only index.
"""

import re
from dataclasses import dataclass
from io import BytesIO
from math import sqrt

import numpy as np
import pandas as pd

from alphalab.backtesting.engine import BacktestResult


@dataclass(frozen=True)
class BenchmarkComparison:
    """Aligned net strategy equity and a normalized buy-and-hold benchmark."""

    curve: pd.DataFrame
    summary: dict[str, float | int]
    label: str


def _column_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def parse_nifty_500_tri_csv(file_bytes: bytes) -> pd.DataFrame:
    """Parse exported *gross TRI* history, rejecting price-only/NTR columns.

    Accepts NSE UI CSV variants such as `IndexName`, `Date`,
    `Total Returns Index` or `TotalReturnsIndex`; sorts newest-first exports.
    """
    if not file_bytes or len(file_bytes) > 15_000_000:
        raise ValueError("Upload a nonempty Nifty 500 TRI CSV (maximum 15 MB)")
    try:
        source = pd.read_csv(BytesIO(file_bytes), encoding="utf-8-sig")
    except (UnicodeDecodeError, pd.errors.ParserError, ValueError) as exc:
        raise ValueError(
            "Could not read CSV; export the TRI table as CSV from NSE Indices"
        ) from exc
    columns = {_column_key(col): col for col in source.columns}
    date_col = columns.get("date")
    # Exact TRI field; never use Net TRI (NTR) or price-index close.
    tri_col = columns.get("totalreturnsindex") or columns.get("totalreturnindex")
    if not date_col or not tri_col:
        raise ValueError(
            "CSV must contain Date and Total Returns Index columns; "
            "download the Total returns Index Values report, not Historical Index Data"
        )
    index_col = columns.get("indexname") or columns.get("index")
    if index_col is not None:
        names = source[index_col].dropna().astype(str).map(_column_key).unique().tolist()
        if not names or any(name != "nifty500" for name in names):
            raise ValueError("CSV Index Name must be NIFTY 500, not another benchmark")

    raw_date = source[date_col].astype(str).str.strip()
    # NSE exports dates as DD Mon YYYY, e.g. '03 Nov 2026'.
    # Explicit formats prevent dd/mm ambiguity and silent US-style parsing.
    dates = pd.to_datetime(raw_date, format="%d %b %Y", errors="coerce")
    if dates.isna().any():
        dates = pd.to_datetime(raw_date, format="%d-%b-%Y", errors="coerce")
    if dates.isna().any():
        dates = pd.to_datetime(raw_date, format="%Y-%m-%d", errors="coerce")
    if dates.isna().any():
        dates = pd.to_datetime(raw_date, format="%d/%m/%Y", errors="coerce")
    if dates.isna().any():
        raise ValueError("Unrecognized or missing dates in TRI CSV")

    raw_tri = source[tri_col].astype(str).str.replace(",", "", regex=False)
    tri_values = pd.to_numeric(raw_tri, errors="coerce")
    if not np.isfinite(tri_values).all() or (tri_values <= 0).any():
        raise ValueError("TRI levels must all be positive, finite numbers")

    out = pd.DataFrame({"date": dates.dt.normalize(), "tri": tri_values.astype(float)})
    if out["date"].duplicated().any():
        raise ValueError("TRI CSV has duplicate dates")
    if len(out) < 3:
        raise ValueError("TRI CSV needs at least three dated observations")
    return out.sort_values("date").reset_index(drop=True)


def combine_nifty_500_tri_csv(csv_files: list[bytes]) -> pd.DataFrame:
    """Join NSE downloads split into date windows; reject conflicting duplicates."""
    if not csv_files:
        raise ValueError("At least one TRI CSV file is required")
    joined = pd.concat([parse_nifty_500_tri_csv(blob) for blob in csv_files], ignore_index=True)
    duplicates = joined.groupby("date")["tri"].nunique()
    if (duplicates > 1).any():
        raise ValueError("Conflicting TRI levels found for overlapping dates")
    return joined.drop_duplicates("date").sort_values("date").reset_index(drop=True)


def make_demo_market_proxy(prices: pd.DataFrame) -> pd.DataFrame:
    """Deterministic daily rebalanced equal-weight proxy for synthetic DEMO only.

    This is **not** a licensed or calculated Nifty 500 TRI series.
    """
    from alphalab.backtesting.engine import _make_matrix

    matrix = _make_matrix(prices)
    if matrix.isna().any().any():
        raise ValueError("Demo market proxy requires complete synthetic price histories")
    daily_returns = matrix.pct_change(fill_method=None).mean(axis=1).fillna(0)
    levels = 1_000.0 * (1.0 + daily_returns).cumprod()
    return pd.DataFrame({"date": matrix.index, "tri": levels.to_numpy()})


def compare_to_benchmark(
    backtest: BacktestResult,
    benchmark: pd.DataFrame,
    label: str,
) -> BenchmarkComparison:
    """Align by market dates; fail closed on incomplete/invalid benchmarks.

    Accept a small number of interior missing benchmark dates and carry forward
    the previous known level, but never extrapolate before/after its coverage.
    """
    if benchmark.empty or not {"date", "tri"}.issubset(benchmark.columns):
        raise ValueError("Benchmark must contain date and tri columns")
    if not label.strip():
        raise ValueError("Benchmark label cannot be empty")
    b = benchmark.loc[:, ["date", "tri"]].copy()
    b["date"] = pd.to_datetime(b["date"], errors="coerce")
    if b["date"].isna().any():
        raise ValueError("Benchmark has invalid or missing dates")
    if getattr(b["date"].dt, "tz", None) is not None:
        b["date"] = b["date"].dt.tz_localize(None)
    b["date"] = b["date"].dt.normalize()
    b["tri"] = pd.to_numeric(b["tri"], errors="coerce")
    if not np.isfinite(b["tri"]).all() or (b["tri"] <= 0).any():
        raise ValueError("Benchmark TRI levels must be positive and finite")
    if b["date"].duplicated().any():
        raise ValueError("Benchmark has duplicate dates")
    b = b.set_index("date").sort_index()["tri"]

    dates = pd.DatetimeIndex(pd.to_datetime(backtest.equity_curve["date"])).normalize()
    if dates.empty or dates.has_duplicates or not dates.is_monotonic_increasing:
        raise ValueError("Strategy equity dates must be unique and sorted")
    if dates[0] < b.index[0] or dates[-1] > b.index[-1]:
        raise ValueError(
            "Benchmark history must cover the full strategy period "
            f"({dates[0].date()} through {dates[-1].date()}); "
            "download a wider date range from NSE Indices"
        )
    coverage = float(dates.isin(b.index).mean())
    if coverage < 0.98:
        raise ValueError(
            f"Only {coverage:.1%} of strategy dates have benchmark observations; "
            "check that you uploaded daily TRI, not monthly data"
        )
    aligned = b.reindex(dates).ffill()
    if aligned.isna().any():
        raise ValueError("Missing benchmark level at strategy start date")

    initial = float(backtest.summary["starting_cash"])
    nav = backtest.equity_curve["portfolio_inr"].to_numpy(dtype=float)
    bench_nav = initial * aligned.to_numpy(dtype=float) / float(aligned.iloc[0])
    result = pd.DataFrame({"date": dates, "strategy_inr": nav, "benchmark_inr": bench_nav})
    # Percentage-point excess return is descriptive, not a regression alpha.
    strategy_ret_pct = 100.0 * (nav[-1] / initial - 1.0)
    benchmark_ret_pct = 100.0 * (bench_nav[-1] / initial - 1.0)
    n = len(result)
    benchmark_cagr_pct = 100.0 * ((bench_nav[-1] / initial) ** (252.0 / n) - 1.0)
    benchmark_daily = pd.Series(bench_nav).pct_change().fillna(0)
    annual_std = float(benchmark_daily.std(ddof=1) * sqrt(252))
    sharpe = (
        float(sqrt(252) * benchmark_daily.mean() / benchmark_daily.std(ddof=1))
        if annual_std > 0
        else float("nan")
    )
    peaks = np.maximum.accumulate(np.r_[initial, bench_nav])[1:]
    drawdown_pct = 100.0 * (bench_nav / peaks - 1.0)
    result["benchmark_drawdown_pct"] = drawdown_pct
    result["benchmark_daily_return"] = benchmark_daily.to_numpy()
    result["excess_growth_inr"] = nav - bench_nav

    return BenchmarkComparison(
        curve=result,
        summary={
            "benchmark_return_pct": benchmark_ret_pct,
            "benchmark_cagr_pct": float(benchmark_cagr_pct),
            "benchmark_max_drawdown_pct": float(drawdown_pct.min()),
            "benchmark_sharpe_zero_rf": sharpe,
            "excess_total_return_pp": strategy_ret_pct - benchmark_ret_pct,
            "excess_cagr_pp": float(backtest.summary["cagr_pct"]) - benchmark_cagr_pct,
            "strategy_wins": int(nav[-1] > bench_nav[-1]),
            "strategy_days": n,
            "matched_dates_pct": 100.0 * coverage,
        },
        label=label,
    )
