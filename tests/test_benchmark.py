"""Offline benchmark correctness tests: no live NSE network dependency."""

import numpy as np
import pandas as pd
import pytest

from alphalab.backtesting import (
    BacktestConfig,
    combine_nifty_500_tri_csv,
    compare_to_benchmark,
    make_demo_market_proxy,
    parse_nifty_500_tri_csv,
    run_momentum_backtest,
)


def sample_csv(rows: list[tuple[str, float]], index_name: str = "NIFTY 500") -> bytes:
    lines = ["IndexName,Date,TotalReturnsIndex,NTR_Value"]
    lines.extend(f"{index_name},{date},{value},{value * 0.8}" for date, value in rows)
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_backtest() -> object:
    dates = pd.bdate_range("2024-01-01", periods=170)
    data = pd.concat(
        [
            pd.DataFrame({"date": dates, "ticker": name, "close": 100 * factor ** np.arange(170)})
            for name, factor in [("AAA", 1.002), ("BBB", 1.001)]
        ],
        ignore_index=True,
    )
    return run_momentum_backtest(
        data,
        BacktestConfig(lookback_sessions=60, skip_sessions=5, top_n=1, cost_bps=0),
    )


def bench_for_backtest(backtest, pct_daily=0.001):
    dates = pd.DatetimeIndex(backtest.equity_curve["date"])
    values = 2000 * (1 + pct_daily) ** np.arange(len(dates))
    return pd.DataFrame({"date": dates, "tri": values})


def test_parse_official_nse_headers_and_reverse_chronology():
    body = sample_csv([("03 Nov 2026", 1240), ("02 Nov 2026", 1200), ("30 Oct 2026", 1190)])
    table = parse_nifty_500_tri_csv(body)
    assert table.date.is_monotonic_increasing
    assert table.iloc[-1].tri == pytest.approx(1240)
    assert len(table) == 3


def test_accept_space_separated_tri_column_and_bom():
    file = (
        "\ufeffIndex Name,Date,Total Returns Index\n"
        "Nifty 500,2026-10-28,1000\n"
        "Nifty 500,2026-10-29,1002\n"
        "Nifty 500,2026-10-30,1004\n"
    )
    assert len(parse_nifty_500_tri_csv(file.encode("utf-8"))) == 3


def test_price_index_not_silently_accepted():
    body = b"IndexName,Date,Close\nNifty 500,01 Oct 2026,1000\n"
    with pytest.raises(ValueError, match="Total Returns Index"):
        parse_nifty_500_tri_csv(body)


def test_ntr_only_not_silently_accepted():
    body = b"IndexName,Date,Net Total Return Index\nNifty 500,01 Oct 2026,1000\n"
    with pytest.raises(ValueError, match="Total Returns Index"):
        parse_nifty_500_tri_csv(body)


def test_wrong_index_rejected():
    body = sample_csv(
        [("01 Oct 2026", 1000), ("02 Oct 2026", 1001), ("03 Oct 2026", 1002)],
        "NIFTY 50",
    )
    with pytest.raises(ValueError, match="NIFTY 500"):
        parse_nifty_500_tri_csv(body)


@pytest.mark.parametrize(
    "rows,expected",
    [
        ([("01 Oct 2026", 100), ("01 Oct 2026", 101), ("03 Oct 2026", 102)], "duplicate"),
        ([("01 Oct 2026", 100), ("02 Oct 2026", 0), ("03 Oct 2026", 102)], "positive"),
        ([("bad", 100), ("02 Oct 2026", 101), ("03 Oct 2026", 102)], "dates"),
    ],
)
def test_bad_rows_are_rejected(rows, expected):
    with pytest.raises(ValueError, match=expected):
        parse_nifty_500_tri_csv(sample_csv(rows))


def test_merge_identical_overlapping_windows():
    a = sample_csv([("01 Oct 2026", 100), ("02 Oct 2026", 101), ("03 Oct 2026", 102)])
    b = sample_csv([("03 Oct 2026", 102), ("04 Oct 2026", 103), ("05 Oct 2026", 104)])
    merged = combine_nifty_500_tri_csv([a, b])
    assert len(merged) == 5
    assert merged.iloc[-1].tri == 104


def test_merge_conflicting_overlaps_rejected():
    a = sample_csv([("01 Oct 2026", 100), ("02 Oct 2026", 101), ("03 Oct 2026", 102)])
    b = sample_csv([("01 Oct 2026", 100), ("02 Oct 2026", 999), ("03 Oct 2026", 102)])
    with pytest.raises(ValueError, match="Conflicting"):
        combine_nifty_500_tri_csv([a, b])


def test_empty_list_rejected():
    with pytest.raises(ValueError, match="At least one"):
        combine_nifty_500_tri_csv([])


def test_synthetic_equal_weight_proxy_compounds_average_returns():
    dates = pd.bdate_range("2026-01-01", periods=3)
    data = pd.DataFrame(
        [
            (dates[0], "A", 100),
            (dates[1], "A", 110),
            (dates[2], "A", 110),
            (dates[0], "B", 100),
            (dates[1], "B", 100),
            (dates[2], "B", 110),
        ],
        columns=["date", "ticker", "close"],
    )
    proxy = make_demo_market_proxy(data)
    assert proxy.tri.tolist() == pytest.approx([1000, 1050, 1102.5])


def test_comparison_normalizes_to_same_starting_capital():
    bt = build_backtest()
    b = bench_for_backtest(bt)
    comparison = compare_to_benchmark(bt, b, "Nifty 500 TRI")
    assert comparison.curve.iloc[0].benchmark_inr == pytest.approx(100_000)
    assert comparison.summary["benchmark_return_pct"] == pytest.approx(
        100 * ((1.001) ** (len(comparison.curve) - 1) - 1)
    )
    assert comparison.summary["matched_dates_pct"] == pytest.approx(100)


def test_excess_is_strategy_minus_benchmark_percentage_points():
    bt = build_backtest()
    comparison = compare_to_benchmark(bt, bench_for_backtest(bt), "Nifty 500 TRI")
    assert comparison.summary["excess_total_return_pp"] == pytest.approx(
        bt.summary["total_return_pct"] - comparison.summary["benchmark_return_pct"]
    )


def test_future_missing_benchmark_is_not_extrapolated():
    bt = build_backtest()
    b = bench_for_backtest(bt).iloc[:-1]
    with pytest.raises(ValueError, match="full strategy period"):
        compare_to_benchmark(bt, b, "Nifty 500 TRI")


def test_old_benchmark_not_extrapolated_backwards():
    bt = build_backtest()
    b = bench_for_backtest(bt).iloc[1:]
    with pytest.raises(ValueError, match="full strategy period"):
        compare_to_benchmark(bt, b, "Nifty 500 TRI")


def test_sparse_monthly_benchmark_is_rejected():
    bt = build_backtest()
    b = bench_for_backtest(bt)
    b = pd.concat([b.iloc[[0]], b.iloc[1:-1:20], b.iloc[[-1]]], ignore_index=True)
    with pytest.raises(ValueError, match="daily TRI"):
        compare_to_benchmark(bt, b, "Nifty 500 TRI")


def test_small_interior_gap_can_be_carried_forward():
    bt = build_backtest()
    b = bench_for_backtest(bt)
    b = b.drop(index=3).reset_index(drop=True)
    comparison = compare_to_benchmark(bt, b, "Nifty 500 TRI")
    assert comparison.summary["matched_dates_pct"] < 100
    assert np.isfinite(comparison.curve.benchmark_inr).all()


def test_duplicate_benchmark_dates_rejected():
    bt = build_backtest()
    b = bench_for_backtest(bt)
    b = pd.concat([b, b.iloc[[3]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        compare_to_benchmark(bt, b, "Nifty 500 TRI")


def test_zero_benchmark_levels_rejected():
    bt = build_backtest()
    b = bench_for_backtest(bt)
    b.loc[3, "tri"] = 0
    with pytest.raises(ValueError, match="positive"):
        compare_to_benchmark(bt, b, "Nifty 500 TRI")
