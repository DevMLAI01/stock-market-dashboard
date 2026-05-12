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

            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS watchlist_stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                watchlist_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                added_at TEXT NOT NULL,
                FOREIGN KEY (watchlist_id) REFERENCES watchlist(id) ON DELETE CASCADE,
                UNIQUE(watchlist_id, symbol)
            );

            CREATE TABLE IF NOT EXISTS fundamentals (
                symbol TEXT PRIMARY KEY,
                pe_ratio REAL,
                roce REAL,
                roe REAL,
                book_value REAL,
                debt_equity REAL,
                dividend_yield REAL,
                profit_growth_yoy REAL,
                revenue_growth_yoy REAL,
                sales_growth_5yr REAL,
                latest_quarter TEXT,
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


# ── Watchlist helpers ─────────────────────────────────────────────────────────

def create_watchlist(name: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO watchlist (name, created_at) VALUES (?, ?)",
            (name.strip(), datetime.now().isoformat()),
        )
        return cur.lastrowid


def get_watchlists() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT w.id, w.name, w.created_at,
                   COUNT(ws.id) AS count
            FROM watchlist w
            LEFT JOIN watchlist_stocks ws ON ws.watchlist_id = w.id
            GROUP BY w.id
            ORDER BY w.created_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


def add_to_watchlist(watchlist_id: int, symbol: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO watchlist_stocks (watchlist_id, symbol, added_at) VALUES (?, ?, ?)",
            (watchlist_id, symbol, datetime.now().isoformat()),
        )


def remove_from_watchlist(watchlist_id: int, symbol: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM watchlist_stocks WHERE watchlist_id = ? AND symbol = ?",
            (watchlist_id, symbol),
        )


def get_watchlist_stocks(watchlist_id: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT symbol FROM watchlist_stocks WHERE watchlist_id = ? ORDER BY added_at",
            (watchlist_id,),
        ).fetchall()
    return [r["symbol"] for r in rows]


def delete_watchlist(watchlist_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM watchlist_stocks WHERE watchlist_id = ?", (watchlist_id,))
        conn.execute("DELETE FROM watchlist WHERE id = ?", (watchlist_id,))


def save_filter_as_watchlist(name: str, symbols: list[str]) -> int:
    wl_id = create_watchlist(name)
    with get_conn() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO watchlist_stocks (watchlist_id, symbol, added_at) VALUES (?, ?, ?)",
            [(wl_id, sym, datetime.now().isoformat()) for sym in symbols],
        )
    return wl_id


# ── Fundamentals cache ────────────────────────────────────────────────────────

def upsert_fundamentals(symbol: str, metrics: dict) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO fundamentals
                (symbol, pe_ratio, roce, roe, book_value, debt_equity, dividend_yield,
                 profit_growth_yoy, revenue_growth_yoy, sales_growth_5yr, latest_quarter, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol,
            metrics.get("pe_ratio"),
            metrics.get("roce"),
            metrics.get("roe"),
            metrics.get("book_value"),
            metrics.get("debt_equity"),
            metrics.get("dividend_yield"),
            metrics.get("profit_growth_yoy"),
            metrics.get("revenue_growth_yoy"),
            metrics.get("sales_growth_5yr"),
            metrics.get("latest_quarter"),
            datetime.now().isoformat(),
        ))


def get_all_fundamentals() -> "pd.DataFrame":
    import pandas as pd
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM fundamentals"
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([dict(r) for r in rows])


def get_fundamentals_count() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM fundamentals").fetchone()
    return row["n"] if row else 0


def get_all_screener_cache_symbols() -> list[str]:
    """Return all symbols currently in screener_cache (for bulk extraction)."""
    with get_conn() as conn:
        rows = conn.execute("SELECT symbol, data_json FROM screener_cache").fetchall()
    return [(r["symbol"], r["data_json"]) for r in rows]
