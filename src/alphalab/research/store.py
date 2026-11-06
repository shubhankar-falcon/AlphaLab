"""Durable SQLite signal journal, using only Python's standard library."""

import csv
import io
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signal_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at_utc TEXT NOT NULL,
            asof_date TEXT NOT NULL,
            source TEXT NOT NULL,
            settings_sha256 TEXT NOT NULL,
            snapshot_json TEXT NOT NULL,
            UNIQUE(source, asof_date, settings_sha256)
        )
    """)
    return conn


def save_snapshot(path: str | Path, snapshot: dict) -> tuple[int, bool]:
    """Save once; later data revisions never overwrite an earlier observation."""
    required = {"asof_date", "source", "settings_sha256", "picks", "prices_sha256"}
    if not required.issubset(snapshot):
        raise ValueError("Signal snapshot missing required fields")
    if not snapshot["picks"]:
        raise ValueError("Cannot save a signal without picks")
    created_at = datetime.now(UTC).isoformat(timespec="seconds")
    with _connect(Path(path)) as conn:
        existing = conn.execute(
            "SELECT id FROM signal_snapshots "
            "WHERE source = ? AND asof_date = ? AND settings_sha256 = ?",
            (snapshot["source"], snapshot["asof_date"], snapshot["settings_sha256"]),
        ).fetchone()
        if existing is not None:
            return int(existing["id"]), False
        cur = conn.execute(
            """INSERT INTO signal_snapshots
               (created_at_utc, asof_date, source, settings_sha256, snapshot_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                created_at,
                snapshot["asof_date"],
                snapshot["source"],
                snapshot["settings_sha256"],
                json.dumps(snapshot, sort_keys=True),
            ),
        )
        return int(cur.lastrowid), True


def load_snapshots(path: str | Path, source: str | None = None) -> list[dict]:
    """Return immutable recorded decisions, newest first."""
    if not Path(path).exists():
        return []
    with _connect(Path(path)) as conn:
        if source is None:
            rows = conn.execute("SELECT * FROM signal_snapshots ORDER BY id DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM signal_snapshots WHERE source = ? ORDER BY id DESC", (source,)
            ).fetchall()
    return [
        {
            "id": row["id"],
            "created_at_utc": row["created_at_utc"],
            **json.loads(row["snapshot_json"]),
        }
        for row in rows
    ]


def snapshots_to_csv(snapshots: list[dict]) -> str:
    """Export every recorded stock pick with observation and recording dates."""
    out = io.StringIO()
    writer = csv.DictWriter(
        out,
        fieldnames=[
            "id",
            "created_at_utc",
            "asof_date",
            "source",
            "strategy",
            "ticker",
            "rank",
            "momentum_pct",
            "target_weight_pct",
            "formation_start",
            "formation_end",
            "prices_sha256",
            "settings_sha256",
        ],
    )
    writer.writeheader()
    for s in snapshots:
        for pick in s["picks"]:
            writer.writerow(
                {k: (pick[k] if k in pick else s.get(k, "")) for k in writer.fieldnames}
            )
    return out.getvalue()
