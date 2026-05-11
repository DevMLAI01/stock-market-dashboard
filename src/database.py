import sqlite3
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "stocks.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS filter_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_text TEXT NOT NULL,
                filter_json TEXT,
                result_symbols TEXT,
                run_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS screener_cache (
                symbol TEXT PRIMARY KEY,
                data_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS nse_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );
        """)


def save_filter(query_text: str, filter_json: dict, result_symbols: list[str]) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO filter_history (query_text, filter_json, result_symbols, run_at) VALUES (?, ?, ?, ?)",
            (query_text, json.dumps(filter_json), json.dumps(result_symbols), datetime.now().isoformat()),
        )


def get_filter_history(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM filter_history ORDER BY run_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_cached_screener(symbol: str, ttl_hours: int = 24) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT data_json, fetched_at FROM screener_cache WHERE symbol = ?", (symbol,)
        ).fetchone()
    if row is None:
        return None
    fetched_at = datetime.fromisoformat(row["fetched_at"])
    if datetime.now() - fetched_at > timedelta(hours=ttl_hours):
        return None
    return json.loads(row["data_json"])


def set_cached_screener(symbol: str, data: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO screener_cache (symbol, data_json, fetched_at) VALUES (?, ?, ?)",
            (symbol, json.dumps(data), datetime.now().isoformat()),
        )


def get_cached_nse(ttl_minutes: int = 15) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT data_json, fetched_at FROM nse_cache WHERE id = 1").fetchone()
    if row is None:
        return None
    fetched_at = datetime.fromisoformat(row["fetched_at"])
    if datetime.now() - fetched_at > timedelta(minutes=ttl_minutes):
        return None
    return json.loads(row["data_json"])


def set_cached_nse(data: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO nse_cache (id, data_json, fetched_at) VALUES (1, ?, ?)",
            (json.dumps(data), datetime.now().isoformat()),
        )
