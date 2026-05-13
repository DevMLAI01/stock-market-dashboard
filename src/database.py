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
                result_count INTEGER,
                run_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS filter_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filter_id INTEGER NOT NULL,
                rating INTEGER NOT NULL,
                correction TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (filter_id) REFERENCES filter_history(id)
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
        _migrate_fundamentals(conn)
        _migrate_filter_history(conn)


def _migrate_filter_history(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("ALTER TABLE filter_history ADD COLUMN result_count INTEGER")
    except sqlite3.OperationalError:
        pass


_NEW_FUNDAMENTALS_COLUMNS = [
    ("promoter_pct", "REAL"),
    ("fii_pct", "REAL"),
    ("dii_pct", "REAL"),
    ("public_pct", "REAL"),
    ("pledged_pct", "REAL"),
    ("opm_pct", "REAL"),
    ("opm_quarterly_pct", "REAL"),
    ("net_profit_margin", "REAL"),
    ("sales_growth_3yr", "REAL"),
    ("price_to_book", "REAL"),
    ("eps_growth_3yr", "REAL"),
    ("free_cash_flow", "REAL"),
    ("shareholding_quarter", "TEXT"),
]


def _migrate_fundamentals(conn: sqlite3.Connection) -> None:
    for col_name, col_type in _NEW_FUNDAMENTALS_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE fundamentals ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass


def save_filter(query_text: str, filter_json: dict, result_symbols: list[str]) -> int:
    """Save a filter run and return the inserted row ID."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO filter_history (query_text, filter_json, result_symbols, result_count, run_at) VALUES (?, ?, ?, ?, ?)",
            (query_text, json.dumps(filter_json), json.dumps(result_symbols), len(result_symbols), datetime.now().isoformat()),
        )
        return cur.lastrowid


def get_filter_history(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM filter_history ORDER BY run_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_successful_filter_examples(limit: int = 5) -> list[dict]:
    """Return recent queries that returned results, for Agent 3 few-shot prompting."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT query_text, filter_json, result_count
               FROM filter_history
               WHERE result_count > 0 AND filter_json IS NOT NULL
               ORDER BY run_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    examples = []
    for r in rows:
        try:
            fj = json.loads(r["filter_json"] or "{}")
            if fj.get("filters"):
                examples.append({"query": r["query_text"], "filter": fj, "result_count": r["result_count"]})
        except Exception:
            pass
    return examples


def get_zero_result_queries(limit: int = 20) -> list[str]:
    """Return recent queries that returned 0 results, for Agent 1 awareness."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT query_text FROM filter_history
               WHERE result_count = 0
               ORDER BY run_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [r["query_text"] for r in rows]


def save_filter_feedback(filter_id: int, rating: int, correction: str = "") -> None:
    """Persist user feedback: rating=1 (good) or -1 (bad), with optional correction text."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO filter_feedback (filter_id, rating, correction, created_at) VALUES (?, ?, ?, ?)",
            (filter_id, rating, correction, datetime.now().isoformat()),
        )


def get_feedback_examples(limit: int = 5) -> list[dict]:
    """Return positively-rated filter examples (thumbs-up) for few-shot prompting."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT fh.query_text, fh.filter_json, fh.result_count
               FROM filter_feedback ff
               JOIN filter_history fh ON fh.id = ff.filter_id
               WHERE ff.rating = 1 AND fh.filter_json IS NOT NULL AND fh.result_count > 0
               ORDER BY ff.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    examples = []
    for r in rows:
        try:
            fj = json.loads(r["filter_json"] or "{}")
            if fj.get("filters"):
                examples.append({"query": r["query_text"], "filter": fj, "result_count": r["result_count"]})
        except Exception:
            pass
    return examples


def get_user_corrections(limit: int = 10) -> list[dict]:
    """Return past thumbs-down entries that include a correction, for Agent 1 awareness."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT fh.query_text, ff.correction
               FROM filter_feedback ff
               JOIN filter_history fh ON fh.id = ff.filter_id
               WHERE ff.rating = -1 AND ff.correction IS NOT NULL AND ff.correction != ''
               ORDER BY ff.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [{"query": r["query_text"], "correction": r["correction"]} for r in rows]


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
                 profit_growth_yoy, revenue_growth_yoy, sales_growth_5yr, latest_quarter,
                 promoter_pct, fii_pct, dii_pct, public_pct, pledged_pct,
                 opm_pct, opm_quarterly_pct, net_profit_margin, sales_growth_3yr,
                 price_to_book, eps_growth_3yr, free_cash_flow, shareholding_quarter,
                 fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            metrics.get("promoter_pct"),
            metrics.get("fii_pct"),
            metrics.get("dii_pct"),
            metrics.get("public_pct"),
            metrics.get("pledged_pct"),
            metrics.get("opm_pct"),
            metrics.get("opm_quarterly_pct"),
            metrics.get("net_profit_margin"),
            metrics.get("sales_growth_3yr"),
            metrics.get("price_to_book"),
            metrics.get("eps_growth_3yr"),
            metrics.get("free_cash_flow"),
            metrics.get("shareholding_quarter"),
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
