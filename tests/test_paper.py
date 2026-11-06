"""Offline tests for conservative paper fills and position accounting."""

from datetime import UTC, datetime

import pandas as pd
import pytest

from alphalab.paper import (
    create_paper_account,
    get_paper_account,
    list_paper_accounts,
    mark_paper_account,
    paper_trades_to_csv,
    settle_pending_paper_account,
)


@pytest.fixture
def signal():
    return {
        "id": 7,
        "created_at_utc": "2026-11-06T04:00:00+00:00",  # Fri 09:30 IST
        "asof_date": "2026-11-05",
        "source": "yahoo",
        "prices_sha256": "sample-hash",
        "picks": [
            {"ticker": "AAA.NS", "target_weight_pct": 50.0, "momentum_pct": 20},
            {"ticker": "BBB.NS", "target_weight_pct": 50.0, "momentum_pct": 10},
        ],
    }


@pytest.fixture
def raw_prices():
    prices = {
        "2026-11-05": {"AAA.NS": 10.0, "BBB.NS": 30.0},
        "2026-11-06": {"AAA.NS": 11.0, "BBB.NS": 32.0},
        "2026-11-09": {"AAA.NS": 20.0, "BBB.NS": 40.0},
        "2026-11-10": {"AAA.NS": 25.0, "BBB.NS": 35.0},
    }
    return pd.DataFrame(
        {"date": date, "ticker": ticker, "close": close}
        for date, prices_by_symbol in prices.items()
        for ticker, close in prices_by_symbol.items()
    )


def create_account(tmp_path, signal, **kwargs):
    path = tmp_path / "paper.sqlite3"
    number, created = create_paper_account(path, signal, initial_cash=1000, cost_bps=100, **kwargs)
    assert created
    return path, number


def test_new_orders_pending_and_journal_linked(tmp_path, signal):
    db, number = create_account(tmp_path, signal)
    paper = get_paper_account(db, number)
    assert paper["journal_signal_id"] == 7
    assert paper["signal_asof"] == "2026-11-05"
    assert paper["status"] == "pending"
    assert paper["cash_after"] == 1000
    assert paper["fills"] == []
    assert len(list_paper_accounts(db)) == 1


def test_signal_idempotent_original_settings_preserved(tmp_path, signal):
    db, number = create_account(tmp_path, signal)
    other_id, created = create_paper_account(db, signal, initial_cash=5000, cost_bps=0)
    assert (other_id, created) == (number, False)
    assert get_paper_account(db, number)["initial_cash"] == 1000


def test_missing_signal_rejected(tmp_path):
    with pytest.raises(ValueError, match="recorded journal"):
        create_paper_account(tmp_path / "x.sqlite3", {"source": "yahoo"})


def test_only_forward_yahoo_signals(tmp_path, signal):
    signal["source"] = "synthetic_demo"
    with pytest.raises(ValueError, match="Yahoo-recorded"):
        create_paper_account(tmp_path / "x.sqlite3", signal)


def test_invalid_weight_rejected(tmp_path, signal):
    signal["picks"][0]["target_weight_pct"] = 30
    with pytest.raises(ValueError, match="sum to 100"):
        create_paper_account(tmp_path / "x.sqlite3", signal)


def test_future_dated_observation_rejected(tmp_path, signal):
    signal["asof_date"] = "2026-11-10"
    with pytest.raises(ValueError, match="after recording"):
        create_paper_account(tmp_path / "x.sqlite3", signal)


def test_no_same_day_or_weekend_fills(tmp_path, signal, raw_prices):
    db, number = create_account(tmp_path, signal)
    for now in ("2026-11-06T16:00:00+00:00", "2026-11-08T07:00:00+00:00"):
        result = settle_pending_paper_account(
            db, number, raw_prices, now_utc=datetime.fromisoformat(now)
        )
        assert result["status"] == "pending"
        assert result["fills"] == []


def test_first_later_completed_common_close(tmp_path, signal, raw_prices):
    db, number = create_account(tmp_path, signal)
    result = settle_pending_paper_account(
        db, number, raw_prices, now_utc=datetime(2026, 11, 10, 4, tzinfo=UTC)
    )
    assert result["status"] == "active"
    assert result["fill_date"] == "2026-11-09"
    assert {p["ticker"]: p["quantity"] for p in result["fills"]} == {"AAA.NS": 24, "BBB.NS": 12}
    assert result["cash_after"] == pytest.approx(30.4)
    assert sum(p["estimated_cost_inr"] for p in result["fills"]) == pytest.approx(9.6)


def test_repeated_sync_does_not_duplicate_fills(tmp_path, signal, raw_prices):
    db, number = create_account(tmp_path, signal)
    now = datetime(2026, 11, 11, 4, tzinfo=UTC)
    first = settle_pending_paper_account(db, number, raw_prices, now_utc=now)
    second = settle_pending_paper_account(db, number, raw_prices, now_utc=now)
    assert second["fills"] == first["fills"]
    assert len(second["fills"]) == 2


def test_marks_latest_completed_date_only(tmp_path, signal, raw_prices):
    db, number = create_account(tmp_path, signal)
    account = settle_pending_paper_account(
        db, number, raw_prices, now_utc=datetime(2026, 11, 11, 3, tzinfo=UTC)
    )
    valued = mark_paper_account(account, raw_prices, now_utc=datetime(2026, 11, 11, 4, tzinfo=UTC))
    assert valued["mark_date"] == "2026-11-10"
    assert valued["nav_inr"] == pytest.approx(1050.4)
    assert valued["return_pct"] == pytest.approx(5.04)
    assert valued["pnl_inr"] == pytest.approx(50.4)
    assert len(valued["holdings"]) == 2


def test_future_close_not_used_before_completion(tmp_path, signal, raw_prices):
    db, number = create_account(tmp_path, signal)
    account = settle_pending_paper_account(
        db, number, raw_prices, now_utc=datetime(2026, 11, 10, 4, tzinfo=UTC)
    )
    valued = mark_paper_account(account, raw_prices, now_utc=datetime(2026, 11, 10, 4, tzinfo=UTC))
    assert valued["mark_date"] == "2026-11-09"
    assert valued["nav_inr"] == pytest.approx(990.4)  # fee drag


def test_missing_symbol_cannot_partially_fill(tmp_path, signal, raw_prices):
    db, number = create_account(tmp_path, signal)
    data = raw_prices[raw_prices["ticker"] != "BBB.NS"]
    with pytest.raises(ValueError, match="BBB.NS"):
        settle_pending_paper_account(
            db, number, data, now_utc=datetime(2026, 11, 11, 4, tzinfo=UTC)
        )
    assert get_paper_account(db, number)["fills"] == []


def test_insufficient_cash_fails_atomically(tmp_path, signal, raw_prices):
    db = tmp_path / "cash.sqlite3"
    number, _ = create_paper_account(db, signal, initial_cash=10, cost_bps=10)
    with pytest.raises(ValueError, match="too low"):
        settle_pending_paper_account(
            db, number, raw_prices, now_utc=datetime(2026, 11, 11, 4, tzinfo=UTC)
        )
    assert get_paper_account(db, number)["status"] == "pending"
    assert get_paper_account(db, number)["fills"] == []


def test_invalid_duplicate_prices_rejected(tmp_path, signal, raw_prices):
    db, number = create_account(tmp_path, signal)
    data = pd.concat([raw_prices, raw_prices.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="Duplicate"):
        settle_pending_paper_account(
            db, number, data, now_utc=datetime(2026, 11, 11, 4, tzinfo=UTC)
        )


def test_pending_portfolio_cannot_be_marked(tmp_path, signal, raw_prices):
    db, number = create_account(tmp_path, signal)
    with pytest.raises(ValueError, match="pending"):
        mark_paper_account(get_paper_account(db, number), raw_prices)


def test_csv_export(tmp_path, signal, raw_prices):
    db, number = create_account(tmp_path, signal)
    account = settle_pending_paper_account(
        db, number, raw_prices, now_utc=datetime(2026, 11, 11, 4, tzinfo=UTC)
    )
    csv_data = paper_trades_to_csv(account)
    assert "quantity,raw_close,gross_inr" in csv_data
    assert "AAA.NS" in csv_data
    assert len(csv_data.splitlines()) == 3


def test_nonexistent_database_and_account(tmp_path):
    db = tmp_path / "notyet.sqlite3"
    assert list_paper_accounts(db) == []
    with pytest.raises(ValueError, match="No paper portfolio database"):
        get_paper_account(db, 1)


def test_reused_journal_id_with_new_content_rejected(tmp_path, signal):
    db, _ = create_account(tmp_path, signal)
    signal["prices_sha256"] = "different-prices"
    with pytest.raises(ValueError, match="ID was reused"):
        create_paper_account(db, signal)


def test_raw_price_provider_requests_unadjusted_closes(monkeypatch):
    import sys
    from types import SimpleNamespace

    from alphalab.paper.market import fetch_yahoo_raw_closes

    captured = {}

    def fake_download(**kwargs):
        captured.update(kwargs)
        dates = pd.to_datetime(["2026-11-06", "2026-11-09"])
        return pd.DataFrame({("AAA.NS", "Close"): [50.0, 55.0]}, index=dates)

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=fake_download))
    observed = fetch_yahoo_raw_closes(("AAA.NS",), "1mo")
    assert captured["auto_adjust"] is False
    assert observed["close"].tolist() == [50.0, 55.0]
