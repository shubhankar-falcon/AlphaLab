"""Forward-only, EOD paper holdings, explicitly *not* executable brokerage orders.

New accounts begin PENDING. Entries are simulated at the first common raw close
on a trading date strictly AFTER the signal's actual India recording date,
only after that day is fully complete. Prices are unadjusted. Corporate actions,
taxes and exchange fees aren't modeled. No automatic/scheduled background jobs.
"""

import csv
import io
import json
import math
import sqlite3
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

IST = ZoneInfo("Asia/Kolkata")


def _utc_datetime(value: str | datetime) -> datetime:
    try:
        obj = datetime.fromisoformat(value) if isinstance(value, str) else value
        if obj.tzinfo is None:
            raise ValueError("Timestamp must have a time zone")
        return obj.astimezone(UTC)
    except (TypeError, AttributeError) as exc:
        raise ValueError("Invalid UTC recording timestamp") from exc


def _db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS paper_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            journal_signal_id INTEGER NOT NULL UNIQUE,
            source TEXT NOT NULL,
            signal_recorded_utc TEXT NOT NULL,
            signal_asof TEXT NOT NULL,
            signal_sha256 TEXT NOT NULL,
            signal_json TEXT NOT NULL,
            initial_cash REAL NOT NULL,
            cost_bps REAL NOT NULL,
            cash_after REAL NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'active')),
            fill_date TEXT,
            created_at_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS paper_fills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL REFERENCES paper_accounts(id),
            ticker TEXT NOT NULL,
            fill_date TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            raw_close REAL NOT NULL CHECK (raw_close > 0),
            gross_inr REAL NOT NULL CHECK (gross_inr > 0),
            estimated_cost_inr REAL NOT NULL CHECK (estimated_cost_inr >= 0),
            UNIQUE (account_id, ticker)
        );
        """
    )
    return conn


def _account(conn: sqlite3.Connection, account_id: int) -> dict:
    row = conn.execute("SELECT * FROM paper_accounts WHERE id = ?", (account_id,)).fetchone()
    if row is None:
        raise ValueError(f"Paper account #{account_id} not found")
    result = dict(row)
    result["signal"] = json.loads(result["signal_json"])
    fills = conn.execute(
        "SELECT ticker, fill_date, quantity, raw_close, gross_inr, estimated_cost_inr "
        "FROM paper_fills WHERE account_id = ? ORDER BY ticker", (account_id,)
    ).fetchall()
    result["fills"] = [dict(fill) for fill in fills]
    return result


def create_paper_account(
    path: str | Path,
    saved_signal: dict,
    *,
    initial_cash: float = 100_000.0,
    cost_bps: float = 10.0,
) -> tuple[int, bool]:
    """Create immutable pending orders from a real, timestamped journal entry.

    Re-clicking with the same saved signal always returns the existing account;
    it never changes its cash, fees or orders.
    """
    required = {"id", "created_at_utc", "asof_date", "source", "picks", "prices_sha256"}
    if not required.issubset(saved_signal):
        raise ValueError("Create a recorded journal signal first")
    if saved_signal["source"] != "yahoo":
        raise ValueError("Only Yahoo-recorded signals are supported for forward paper trading")
    recorded = _utc_datetime(saved_signal["created_at_utc"])
    try:
        observed = date.fromisoformat(saved_signal["asof_date"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid signal observation date") from exc
    if observed > recorded.astimezone(IST).date():
        raise ValueError("Signal observation date cannot be after recording")
    picks = saved_signal["picks"]
    if not isinstance(picks, list) or not picks:
        raise ValueError("Signal requires at least one stock selection")
    tickers = [p.get("ticker") for p in picks]
    if any(not isinstance(t, str) or not t.strip() for t in tickers):
        raise ValueError("Invalid symbol in journal signal")
    if len(tickers) != len(set(tickers)):
        raise ValueError("Duplicate symbols in journal signal")
    try:
        weights = [float(p["target_weight_pct"]) for p in picks]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Signal is missing portfolio target weights") from exc
    if not all(math.isfinite(w) and w > 0 for w in weights):
        raise ValueError("Target weights must be positive and finite")
    if abs(sum(weights) - 100.0) > 0.001:
        raise ValueError("Target weights must sum to 100%")
    if not math.isfinite(initial_cash) or initial_cash <= 0:
        raise ValueError("Starting paper cash must be positive")
    if not math.isfinite(cost_bps) or not 0 <= cost_bps <= 1000:
        raise ValueError("Transaction cost must be between 0 and 1000 bps")
    try:
        signal_id = int(saved_signal["id"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid journal signal ID") from exc
    if signal_id <= 0:
        raise ValueError("Invalid journal signal ID")
    payload = json.dumps(saved_signal, sort_keys=True, separators=(",", ":"))
    digest = sha256(payload.encode()).hexdigest()
    now = datetime.now(UTC).isoformat(timespec="seconds")
    with _db(Path(path)) as conn:
        existing = conn.execute(
            "SELECT id, signal_sha256 FROM paper_accounts WHERE journal_signal_id = ?",
            (signal_id,)
        ).fetchone()
        if existing is not None:
            if existing["signal_sha256"] != digest:
                raise ValueError(
                    "Journal signal ID was reused with different saved content; "
                    "restore the original journal database before proceeding"
                )
            return int(existing["id"]), False
        cur = conn.execute(
            """INSERT INTO paper_accounts (
               journal_signal_id, source, signal_recorded_utc, signal_asof,
               signal_sha256, signal_json, initial_cash, cost_bps, cash_after,
               status, fill_date, created_at_utc
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, ?)""",
            (
                signal_id, saved_signal["source"], recorded.isoformat(),
                observed.isoformat(), digest, payload, float(initial_cash),
                float(cost_bps), float(initial_cash), now,
            ),
        )
        return int(cur.lastrowid), True


def get_paper_account(path: str | Path, account_id: int) -> dict:
    if not Path(path).exists():
        raise ValueError("No paper portfolio database yet")
    with _db(Path(path)) as conn:
        return _account(conn, account_id)


def list_paper_accounts(path: str | Path) -> list[dict]:
    if not Path(path).exists():
        return []
    with _db(Path(path)) as conn:
        ids = conn.execute("SELECT id FROM paper_accounts ORDER BY id DESC").fetchall()
        return [_account(conn, int(row["id"])) for row in ids]


def _normalized_closes(prices: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "ticker", "close"}
    if not required.issubset(prices.columns):
        raise ValueError("Prices need date, ticker, close")
    if prices.empty:
        raise ValueError("No market prices available")
    data = prices[["date", "ticker", "close"]].copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    if data["date"].isna().any():
        raise ValueError("Invalid market dates")
    if data["date"].dt.tz is not None:
        data["date"] = data["date"].dt.tz_localize(None)
    data["date"] = data["date"].dt.normalize()
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    if not np.isfinite(data["close"]).all() or (data["close"] <= 0).any():
        raise ValueError("Raw closes must be positive and finite")
    if data["ticker"].isna().any() or (data["ticker"].astype(str).str.strip() == "").any():
        raise ValueError("Missing ticker")
    if data.duplicated(["date", "ticker"]).any():
        raise ValueError("Duplicate market observations")
    return data.pivot(index="date", columns="ticker", values="close").sort_index()


def _completed_date(now_utc: datetime) -> date:
    # Conservatively exclude today's Indian session, even after market close.
    return now_utc.astimezone(IST).date() - timedelta(days=1)


def settle_pending_paper_account(
    path: str | Path,
    account_id: int,
    raw_closes: pd.DataFrame,
    *,
    now_utc: datetime | None = None,
) -> dict:
    """Fill all names once at the first common EOD close after recording.

    No same-day or historical pre-recording fills are permitted. All simulated
    fills are transactional: missing / unaffordable names leave account PENDING.
    """
    now = _utc_datetime(now_utc or datetime.now(UTC))
    with _db(Path(path)) as conn:
        account = _account(conn, account_id)
        if account["status"] == "active":
            return account  # idempotent; don't execute again
        recorded = _utc_datetime(account["signal_recorded_utc"])
        if now < recorded:
            raise ValueError("Cannot simulate fills before the signal was recorded")
        last_complete = _completed_date(now)
        earliest_date = recorded.astimezone(IST).date() + timedelta(days=1)
        if last_complete < earliest_date:
            return account  # too soon; remain pending
        matrix = _normalized_closes(raw_closes)
        picks = account["signal"]["picks"]
        symbols = [str(p["ticker"]) for p in picks]
        missing = sorted(set(symbols) - set(matrix.columns))
        if missing:
            raise ValueError(f"No raw-close history for: {', '.join(missing)}")
        eligible_dates = matrix.index[
            (matrix.index.date >= earliest_date) & (matrix.index.date <= last_complete)
        ]
        valid = matrix.loc[eligible_dates, symbols].dropna(how="any")
        if valid.empty:
            return account  # no completed shared bar yet
        session = valid.index[0]
        prices = valid.iloc[0]
        budget = float(account["initial_cash"])
        fee_rate = float(account["cost_bps"]) / 10_000.0
        fills: list[dict] = []
        total_debit = 0.0
        for pick in picks:
            ticker = str(pick["ticker"])
            px = float(prices[ticker])
            target = budget * (float(pick["target_weight_pct"]) / 100.0)
            qty = math.floor(target / (px * (1 + fee_rate)))
            if qty < 1:
                raise ValueError(f"Paper cash is too low to buy one share of {ticker}")
            gross = qty * px
            fees = gross * fee_rate
            total_debit += gross + fees
            fills.append({
                "ticker": ticker, "fill_date": session.date().isoformat(),
                "quantity": qty, "raw_close": px,
                "gross_inr": gross, "estimated_cost_inr": fees,
            })
        cash_after = budget - total_debit
        if cash_after < -0.000001:
            raise ValueError("Orders cost more than available paper cash")
        for f in fills:
            conn.execute(
                """INSERT INTO paper_fills (
                   account_id, ticker, fill_date, quantity, raw_close,
                   gross_inr, estimated_cost_inr
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (account_id, f["ticker"], f["fill_date"], f["quantity"],
                 f["raw_close"], f["gross_inr"], f["estimated_cost_inr"]),
            )
        conn.execute(
            "UPDATE paper_accounts SET status='active', fill_date=?, cash_after=? WHERE id=?",
            (session.date().isoformat(), max(0.0, cash_after), account_id),
        )
        return _account(conn, account_id)


def mark_paper_account(
    account: dict,
    raw_closes: pd.DataFrame,
    *,
    now_utc: datetime | None = None,
) -> dict:
    """Mark positions on a common fully completed date; never fabricate quotes."""
    if account["status"] != "active" or not account["fills"]:
        raise ValueError("Paper orders are still pending")
    now = _utc_datetime(now_utc or datetime.now(UTC))
    matrix = _normalized_closes(raw_closes)
    tickers = [f["ticker"] for f in account["fills"]]
    missing = sorted(set(tickers) - set(matrix.columns))
    if missing:
        raise ValueError(f"Missing market prices for held shares: {', '.join(missing)}")
    valid = matrix.loc[
        (matrix.index >= pd.Timestamp(account["fill_date"]))
        & (matrix.index.date <= _completed_date(now)),
        tickers,
    ].dropna(how="any")
    if valid.empty:
        raise ValueError("No completed shared price date available to mark holdings")
    asof = valid.index[-1]
    marks = valid.iloc[-1]
    holdings = []
    market_value = 0.0
    for f in account["fills"]:
        ticker = f["ticker"]
        last_px = float(marks[ticker])
        value = int(f["quantity"]) * last_px
        market_value += value
        holdings.append({
            "ticker": ticker, "shares": int(f["quantity"]),
            "entry_price": float(f["raw_close"]), "last_close": last_px,
            "market_value_inr": value,
            "unrealized_pnl_inr": value - float(f["gross_inr"]),
        })
    nav = float(account["cash_after"]) + market_value
    initial = float(account["initial_cash"])
    return {
        "mark_date": asof.date().isoformat(),
        "nav_inr": nav,
        "return_pct": 100.0 * (nav / initial - 1.0),
        "pnl_inr": nav - initial,
        "cash_inr": float(account["cash_after"]),
        "estimated_fees_inr": sum(float(f["estimated_cost_inr"]) for f in account["fills"]),
        "holdings": holdings,
    }


def paper_trades_to_csv(account: dict) -> str:
    out = io.StringIO()
    fields = [
        "ticker", "fill_date", "quantity", "raw_close", "gross_inr", "estimated_cost_inr"
    ]
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    writer.writerows(account["fills"])
    return out.getvalue()
