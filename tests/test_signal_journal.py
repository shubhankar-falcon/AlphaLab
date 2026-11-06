"""Offline tests for immutable, point-in-time signal journaling."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from alphalab.research import (
    build_momentum_snapshot,
    load_snapshots,
    save_snapshot,
    snapshots_to_csv,
)


def sample_prices() -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-01", periods=300)
    stocks = {
        "WINNER.NS": np.linspace(100, 200, len(dates)),
        "FLAT.NS": np.full(len(dates), 100.0),
        "LOSER.NS": np.linspace(200, 100, len(dates)),
    }
    return pd.concat(
        [
            pd.DataFrame({"date": dates, "ticker": ticker, "close": series})
            for ticker, series in stocks.items()
        ],
        ignore_index=True,
    )


def make_signal(**kwargs) -> dict:
    return build_momentum_snapshot(sample_prices(), source="synthetic_demo", **kwargs)


def test_ranks_momentum_and_equal_weights():
    signal = make_signal()
    assert [s["ticker"] for s in signal["picks"]] == ["WINNER.NS", "FLAT.NS", "LOSER.NS"]
    assert [s["target_weight_pct"] for s in signal["picks"]] == [
        pytest.approx(100 / 3, abs=0.000001)
    ] * 3


def test_signal_ignores_recent_prices_for_momentum():
    baseline = make_signal()
    changed = sample_prices()
    end = changed["date"].max()
    win_mask = (changed["ticker"] == "WINNER.NS") & (changed["date"] > end - pd.Timedelta(days=10))
    changed.loc[win_mask, "close"] *= 8
    after = build_momentum_snapshot(changed, source="synthetic_demo")
    assert [p["momentum_pct"] for p in baseline["picks"]] == [
        p["momentum_pct"] for p in after["picks"]
    ]
    assert baseline["prices_sha256"] != after["prices_sha256"]


def test_cutoff_ignores_future_dates():
    prices = sample_prices()
    cutoff = prices["date"].iloc[280].date()
    signal = build_momentum_snapshot(prices, source="demo", cutoff_date=cutoff)
    assert signal["asof_date"] == cutoff.isoformat()
    assert signal["formation_end"] < signal["asof_date"]


def test_ineligible_missing_history_excluded():
    prices = sample_prices()
    middle_date = sorted(prices["date"].unique())[-125]
    prices = prices.loc[~((prices["ticker"] == "WINNER.NS") & (prices["date"] == middle_date))]
    snapshot = build_momentum_snapshot(prices, source="demo")
    assert "WINNER.NS" not in [row["ticker"] for row in snapshot["picks"]]


def test_stale_ticker_not_selected():
    prices = sample_prices()
    final_date = prices["date"].max()
    prices = prices.loc[~((prices["ticker"] == "WINNER.NS") & (prices["date"] == final_date))]
    snapshot = build_momentum_snapshot(prices, source="demo")
    assert "WINNER.NS" not in [row["ticker"] for row in snapshot["picks"]]


def test_no_eligible_stocks_fails():
    prices = sample_prices().loc[lambda x: x["ticker"] == "FLAT.NS"].tail(10)
    with pytest.raises(ValueError, match="Insufficient"):
        build_momentum_snapshot(prices, source="demo")


def test_invalid_price_rejected():
    prices = sample_prices()
    prices.loc[0, "close"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        build_momentum_snapshot(prices, source="demo")


def test_duplicate_market_rows_rejected():
    prices = sample_prices()
    prices = pd.concat([prices, prices.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="Duplicate"):
        build_momentum_snapshot(prices, source="demo")


def test_cutoff_before_any_observation_fails():
    with pytest.raises(ValueError, match="before the cutoff"):
        make_signal(cutoff_date=date(2020, 1, 1))


def test_save_and_read_immutable_snapshot(tmp_path):
    db = tmp_path / "signals.sqlite3"
    original = make_signal()
    first_id, created = save_snapshot(db, original)
    assert created
    # Same parameters and date, but revised vendor data: old snapshot stays.
    revised = dict(original, prices_sha256="changed-data", picks=[{"ticker": "FAKE.NS"}])
    second_id, created_again = save_snapshot(db, revised)
    assert second_id == first_id
    assert not created_again
    records = load_snapshots(db)
    assert len(records) == 1
    assert records[0]["prices_sha256"] == original["prices_sha256"]
    assert records[0]["created_at_utc"]


def test_distinct_settings_create_distinct_snapshots(tmp_path):
    db = tmp_path / "journal.sqlite3"
    first_id, _ = save_snapshot(db, make_signal())
    second_id, created = save_snapshot(db, make_signal(skip_sessions=42))
    assert second_id != first_id and created
    assert len(load_snapshots(db, source="synthetic_demo")) == 2
    assert load_snapshots(db, source="yahoo") == []


def test_csv_export_contains_both_dates_and_picks(tmp_path):
    db = tmp_path / "journal.sqlite3"
    save_snapshot(db, make_signal())
    records = load_snapshots(db)
    csv_content = snapshots_to_csv(records)
    assert "created_at_utc,asof_date" in csv_content
    assert "WINNER.NS" in csv_content
    assert "prices_sha256" in csv_content
    assert len(csv_content.splitlines()) == 4


def test_uncreated_database_has_no_records(tmp_path):
    assert load_snapshots(tmp_path / "missing.sqlite3") == []


def test_invalid_settings_rejected():
    with pytest.raises(ValueError, match="lookback"):
        make_signal(lookback_sessions=21, skip_sessions=21)
