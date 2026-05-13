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


def _get_sh_row(rows: dict, *variants: str):
    for k in variants:
        if k in rows:
            return rows[k]
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
    metrics["pledged_pct"] = _to_float(ratios.get("Pledged percentage"))
    metrics["price_to_book"] = _to_float(ratios.get("Price to book value"))
    metrics["eps_growth_3yr"] = _to_float(ratios.get("EPS growth 3Years"))
    metrics["free_cash_flow"] = _to_float(ratios.get("Free Cash Flow"))

    # ── Quarterly YoY growth ──────────────────────────────────────────────────
    quarterly = screener_data.get("quarterly", {})
    q_headers = quarterly.get("headers", [])
    q_rows = quarterly.get("rows", {})

    if q_headers and len(q_headers) >= 5:
        latest_h = q_headers[-1]
        yoy_h = q_headers[-5]  # same quarter, previous year

        profit_row = _get_sh_row(q_rows, "Net Profit", "Profit after tax", "Net profit", "PAT")
        revenue_row = _get_sh_row(q_rows, "Sales", "Revenue", "Net Sales", "Revenue from operations")
        opm_q_row = q_rows.get("OPM %")

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

        if opm_q_row:
            metrics["opm_quarterly_pct"] = _to_float(opm_q_row.get(latest_h))

    # ── Annual P&L ────────────────────────────────────────────────────────────
    annual = screener_data.get("annual_pl", {})
    a_headers = annual.get("headers", [])
    a_rows = annual.get("rows", {})

    if a_headers:
        latest_a = a_headers[-1]
        opm_row = a_rows.get("OPM %")
        if opm_row:
            metrics["opm_pct"] = _to_float(opm_row.get(latest_a))

        sales_row = _get_sh_row(a_rows, "Sales+", "Sales", "Revenue", "Net Sales")
        np_row = _get_sh_row(a_rows, "Net Profit+", "Net Profit", "Profit after tax", "PAT")

        # Net profit margin (annual)
        if sales_row and np_row:
            s = _to_float(sales_row.get(latest_a))
            p = _to_float(np_row.get(latest_a))
            if s and s != 0 and p is not None:
                metrics["net_profit_margin"] = round(p / s * 100, 2)

        # 3-year sales CAGR
        if sales_row and len(a_headers) >= 4:
            h_3yr = a_headers[-4]
            s_latest = _to_float(sales_row.get(latest_a))
            s_3yr = _to_float(sales_row.get(h_3yr))
            if s_latest and s_3yr and s_3yr > 0:
                metrics["sales_growth_3yr"] = round(
                    ((s_latest / s_3yr) ** (1 / 3) - 1) * 100, 2
                )

    # ── Shareholding ──────────────────────────────────────────────────────────
    sh = screener_data.get("shareholding", {})
    sh_headers = sh.get("headers", [])
    sh_rows = sh.get("rows", {})

    if sh_headers:
        latest_sh = sh_headers[-1]
        metrics["shareholding_quarter"] = latest_sh

        for col, *variants in [
            ("promoter_pct", "Promoters+", "Promoters"),
            ("fii_pct", "FIIs+", "FIIs"),
            ("dii_pct", "DIIs+", "DIIs"),
            ("public_pct", "Public+", "Public"),
        ]:
            row = _get_sh_row(sh_rows, *variants)
            if row:
                metrics[col] = _to_float(row.get(latest_sh))

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
