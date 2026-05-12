"""
Builds and maintains the `fundamentals` SQLite table by extracting key metrics
from Screener.in data (either already-cached or freshly fetched).

Extraction logic:
- pe_ratio, roce, roe, book_value, debt_equity, dividend_yield, sales_growth_5yr
  come from the `ratios` dict (Screener.in top-ratios section).
- profit_growth_yoy, revenue_growth_yoy come from the `quarterly` table:
  latest quarter vs same quarter one year earlier (4 positions back in headers).
"""

import json
import re
import threading
import time

from src.database import (
    get_all_screener_cache_symbols,
    upsert_fundamentals,
    get_fundamentals_count,
)

_lock = threading.Lock()
_running = False


def _to_float(text) -> float | None:
    if text is None:
        return None
    clean = re.sub(r"[^\d.\-]", "", str(text).replace(",", ""))
    try:
        return float(clean) if clean not in ("", "-") else None
    except ValueError:
        return None


def extract_metrics(screener_data: dict) -> dict:
    """Pull filterable numeric metrics out of a screener data dict."""
    metrics: dict = {}

    # ── Ratios ────────────────────────────────────────────────────────────────
    ratios = screener_data.get("ratios", {})
    metrics["pe_ratio"] = _to_float(ratios.get("Stock P/E"))
    metrics["roce"] = _to_float(ratios.get("ROCE"))
    metrics["roe"] = _to_float(ratios.get("ROE"))
    metrics["book_value"] = _to_float(ratios.get("Book Value"))
    metrics["debt_equity"] = _to_float(ratios.get("Debt to equity"))
    metrics["dividend_yield"] = _to_float(ratios.get("Dividend Yield"))
    metrics["sales_growth_5yr"] = _to_float(ratios.get("Sales growth 5Years"))

    # ── Quarterly YoY growth ──────────────────────────────────────────────────
    quarterly = screener_data.get("quarterly", {})
    headers = quarterly.get("headers", [])
    rows = quarterly.get("rows", {})

    if headers and len(headers) >= 5:
        latest_h = headers[-1]
        yoy_h = headers[-5]  # same quarter, previous year

        # Net Profit row — Screener uses different names for different companies
        profit_row = (
            rows.get("Net Profit")
            or rows.get("Profit after tax")
            or rows.get("Net profit")
            or rows.get("PAT")
        )
        revenue_row = (
            rows.get("Sales")
            or rows.get("Revenue")
            or rows.get("Net Sales")
            or rows.get("Revenue from operations")
        )

        if profit_row:
            latest_p = _to_float(profit_row.get(latest_h))
            yoy_p = _to_float(profit_row.get(yoy_h))
            if latest_p is not None and yoy_p and yoy_p != 0:
                metrics["profit_growth_yoy"] = round(
                    (latest_p - yoy_p) / abs(yoy_p) * 100, 2
                )
                metrics["latest_quarter"] = latest_h

        if revenue_row:
            latest_r = _to_float(revenue_row.get(latest_h))
            yoy_r = _to_float(revenue_row.get(yoy_h))
            if latest_r is not None and yoy_r and yoy_r != 0:
                metrics["revenue_growth_yoy"] = round(
                    (latest_r - yoy_r) / abs(yoy_r) * 100, 2
                )

    return metrics


def sync_from_screener_cache() -> int:
    """
    Extract fundamentals from every entry already in screener_cache.
    No HTTP requests — purely reads the local SQLite cache.
    Returns the number of symbols processed.
    """
    entries = get_all_screener_cache_symbols()
    count = 0
    for symbol, data_json in entries:
        try:
            data = json.loads(data_json)
            metrics = extract_metrics(data)
            upsert_fundamentals(symbol, metrics)
            count += 1
        except Exception as e:
            print(f"[Fundamentals] sync error for {symbol}: {e}")
    return count


def refresh_fundamentals(symbols: list[str], delay: float = 0.4) -> int:
    """
    Fetch Screener.in data for each symbol and extract fundamentals.
    Respects the existing screener_cache (no duplicate HTTP if already cached).
    Returns the number of symbols successfully processed.
    """
    global _running

    with _lock:
        if _running:
            return 0
        _running = True

    try:
        from src.screener_client import get_stock_data

        processed = 0
        for sym in symbols:
            try:
                data = get_stock_data(sym)
                if data:
                    metrics = extract_metrics(data)
                    upsert_fundamentals(sym, metrics)
                    processed += 1
            except Exception as e:
                print(f"[Fundamentals] fetch error for {sym}: {e}")
            time.sleep(delay)

        return processed
    finally:
        with _lock:
            _running = False


def start_background_refresh(symbols: list[str], delay: float = 0.4) -> None:
    """Fire a daemon thread to fetch fundamentals for the given symbols."""
    global _running
    with _lock:
        if _running:
            return

    def _run():
        refresh_fundamentals(symbols, delay=delay)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
