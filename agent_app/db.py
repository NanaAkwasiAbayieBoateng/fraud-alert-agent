"""Local SQLite database with deterministic synthetic seed data.

Tables: ``accounts``, ``transactions``, ``alerts``. Alert ``A1`` is the
demo alert: a $2,450 electronics purchase at 03:12 from a brand-new
merchant on an account whose typical spend is under $120, preceded by two
small "test" charges. One transaction memo deliberately contains an email
address and a card number so PII redaction is exercised end-to-end.

Run ``python -m agent_app.db`` to (re)create and seed the database.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE accounts (
    account_id TEXT PRIMARY KEY,
    holder     TEXT NOT NULL,
    email      TEXT NOT NULL,
    phone      TEXT NOT NULL,
    opened_on  TEXT NOT NULL,
    status     TEXT NOT NULL
);
CREATE TABLE transactions (
    txn_id     TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    ts         TEXT NOT NULL,
    amount     REAL NOT NULL,
    merchant   TEXT NOT NULL,
    category   TEXT NOT NULL,
    status     TEXT NOT NULL,
    memo       TEXT NOT NULL DEFAULT ''
);
CREATE TABLE alerts (
    alert_id   TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    txn_id     TEXT NOT NULL REFERENCES transactions(txn_id),
    rule       TEXT NOT NULL,
    severity   TEXT NOT NULL,
    status     TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

ACCOUNTS = [
    ("ACC-1001", "Jordan Miles", "jordan.miles@example.com", "555-010-1001", "2021-03-14", "active"),
    ("ACC-1002", "Priya Nair", "priya.nair@example.com", "555-010-1002", "2020-07-02", "active"),
    ("ACC-1003", "Sam Whitaker", "sam.whitaker@example.com", "555-010-1003", "2022-11-19", "active"),
]

TRANSACTIONS = [
    # ACC-1001 — ordinary pattern
    ("TXN-8001", "ACC-1001", "2026-11-02T09:14:00", 82.40, "FreshMart", "groceries", "posted", ""),
    ("TXN-8002", "ACC-1001", "2026-11-03T18:02:00", 96.10, "City Utilities", "utilities", "posted", ""),
    ("TXN-8003", "ACC-1001", "2026-11-05T08:31:00", 6.50, "Blue Cup Coffee", "dining", "posted", ""),
    ("TXN-8004", "ACC-1001", "2026-11-07T12:45:00", 54.99, "Metro Fuel", "transport", "posted", ""),
    ("TXN-8005", "ACC-1001", "2026-11-09T10:20:00", 118.75, "FreshMart", "groceries", "posted", ""),
    ("TXN-8006", "ACC-1001", "2026-11-11T08:15:00", 6.50, "Blue Cup Coffee", "dining", "posted", ""),
    ("TXN-8007", "ACC-1001", "2026-11-12T19:40:00", 73.20, "Luigi's", "dining", "posted", ""),
    # ACC-1001 — suspicious sequence leading to alert A1
    ("TXN-8998", "ACC-1001", "2026-11-14T03:04:00", 1.00, "Unknown Vendor 7", "misc", "posted", ""),
    ("TXN-8999", "ACC-1001", "2026-11-14T03:07:00", 1.50, "Unknown Vendor 7", "misc", "posted", ""),
    (
        "TXN-9001", "ACC-1001", "2026-11-14T03:12:00", 2450.00, "ElectroWorld Online",
        "electronics", "flagged",
        "Order help contact jordan.miles@example.com, card 4111 1111 1111 1111",
    ),
    # ACC-1002
    ("TXN-9101", "ACC-1002", "2026-11-13T09:00:00", 210.00, "Northwind Air", "travel", "posted", ""),
    ("TXN-9102", "ACC-1002", "2026-11-13T09:01:00", 205.00, "Northwind Air", "travel", "posted", ""),
    ("TXN-9103", "ACC-1002", "2026-11-13T09:02:00", 198.00, "Northwind Air", "travel", "posted", ""),
    ("TXN-9104", "ACC-1002", "2026-11-10T14:22:00", 45.60, "FreshMart", "groceries", "posted", ""),
    # ACC-1003
    ("TXN-9201", "ACC-1003", "2026-11-08T16:30:00", 320.00, "Harbor Hotel", "travel", "posted", ""),
    ("TXN-9202", "ACC-1003", "2026-11-12T11:05:00", 28.99, "StreamBox", "subscriptions", "posted", ""),
    ("TXN-9203", "ACC-1003", "2026-11-13T22:48:00", 640.00, "ElectroWorld Online", "electronics", "flagged", ""),
]

ALERTS = [
    ("A1", "ACC-1001", "TXN-9001", "high_value_new_merchant", "high", "open", "2026-11-14T03:15:00"),
    ("A2", "ACC-1002", "TXN-9102", "velocity_burst", "medium", "open", "2026-11-13T09:05:00"),
    ("A3", "ACC-1003", "TXN-9203", "geo_mismatch", "low", "open", "2026-11-13T22:50:00"),
]


def default_db_path() -> Path:
    return Path(os.environ.get("AGENT_DB_PATH", "data/fraud.db"))


def seed(path: Path | str) -> Path:
    """Create a fresh database at *path* and load the deterministic seed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO accounts VALUES (?,?,?,?,?,?)", ACCOUNTS)
        conn.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?)", TRANSACTIONS)
        conn.executemany("INSERT INTO alerts VALUES (?,?,?,?,?,?,?)", ALERTS)
        conn.commit()
    finally:
        conn.close()
    return path


def ensure_db(path: Path | str) -> Path:
    path = Path(path)
    if not path.exists():
        seed(path)
    return path


def _row_dicts(conn: sqlite3.Connection, sql: str, params: tuple) -> list[dict]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def get_alert(db_path: Path | str, alert_id: str) -> dict | None:
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        rows = _row_dicts(conn, "SELECT * FROM alerts WHERE alert_id = ?", (alert_id,))
    finally:
        conn.close()
    return rows[0] if rows else None


def get_account(db_path: Path | str, account_id: str) -> dict | None:
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        rows = _row_dicts(conn, "SELECT * FROM accounts WHERE account_id = ?", (account_id,))
    finally:
        conn.close()
    return rows[0] if rows else None


def get_transaction(db_path: Path | str, txn_id: str) -> dict | None:
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        rows = _row_dicts(conn, "SELECT * FROM transactions WHERE txn_id = ?", (txn_id,))
    finally:
        conn.close()
    return rows[0] if rows else None


def set_alert_status(db_path: Path | str, alert_id: str, status: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE alerts SET status = ? WHERE alert_id = ?", (status, alert_id))
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and seed the local fraud demo database.")
    parser.add_argument("--path", default=str(default_db_path()), help="Database file path")
    args = parser.parse_args()
    path = seed(args.path)
    conn = sqlite3.connect(path)
    try:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("accounts", "transactions", "alerts")
        }
    finally:
        conn.close()
    print(f"Seeded {path}: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
