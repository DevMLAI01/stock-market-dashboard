import os
import json
from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Streamlit Cloud stores secrets in st.secrets; sync to env so all modules can use os.environ
if hasattr(st, "secrets"):
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k, _v)

from src.database import (
    init_db, get_filter_history,
    create_watchlist, get_watchlists, add_to_watchlist,
    remove_from_watchlist, get_watchlist_stocks,
    delete_watchlist, save_filter_as_watchlist,
    get_all_fundamentals, get_fundamentals_count,
)
from src.nse_client import get_stocks_near_52wk_high, get_nifty_universe, get_historical_ohlc
from src.screener_client import get_stock_data
from src.nl_filter import run_nl_filter
from src.agent_filter import run_agent_filter
from src.charts import build_candlestick_chart

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stock Market Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .stApp { background-color: #0e1117; }

  .ratio-card {
    background: #1a1d27;
    border: 1px solid #2a2d3e;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 4px 0;
  }
  .ratio-label { color: #8b9dc3; font-size: 12px; margin-bottom: 2px; }
  .ratio-value { color: #f0f2f6; font-size: 16px; font-weight: 600; }

  .stock-item {
    padding: 10px 12px;
    border-radius: 6px;
    cursor: pointer;
    border-left: 3px solid transparent;
    margin-bottom: 2px;
  }
  .stock-item:hover { background: #1a1d27; }
  .stock-item.selected { background: #1a2744; border-left-color: #4e9af1; }
  .stock-sym { font-weight: 700; font-size: 14px; color: #f0f2f6; }
  .stock-price { font-size: 13px; color: #a0a8be; }

  .fin-table th {
    background: #1a1d27 !important;
    color: #8b9dc3 !important;
    font-size: 12px !important;
    font-weight: 600 !important;
  }
  .fin-table td { font-size: 12px !important; }

  .section-header {
    color: #8b9dc3;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin: 16px 0 8px 0;
    padding-bottom: 4px;
    border-bottom: 1px solid #2a2d3e;
  }

  .price-big { font-size: 28px; font-weight: 700; color: #f0f2f6; }
  .change-pos { color: #26a69a; font-size: 16px; font-weight: 600; }
  .change-neg { color: #ef5350; font-size: 16px; font-weight: 600; }

  .hist-item {
    padding: 6px 8px;
    border-radius: 4px;
    margin-bottom: 3px;
    font-size: 12px;
    color: #8b9dc3;
    background: #1a1d27;
  }
  .hist-date { color: #4e9af1; font-size: 10px; }

  #MainMenu { visibility: hidden; }
  footer { visibility: hidden; }
  header { visibility: hidden; }
  .block-container { padding-top: 1rem; }
</style>
""", unsafe_allow_html=True)

# ── Init ──────────────────────────────────────────────────────────────────────
init_db()

if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = None
if "stock_df" not in st.session_state:
    st.session_state.stock_df = pd.DataFrame()
if "filter_active" not in st.session_state:
    st.session_state.filter_active = False
if "filter_summary" not in st.session_state:
    st.session_state.filter_summary = ""
if "chart_period" not in st.session_state:
    st.session_state.chart_period = "1y"
if "chart_interval" not in st.session_state:
    st.session_state.chart_interval = "1d"
if "active_watchlist_id" not in st.session_state:
    st.session_state.active_watchlist_id = None
if "fundamentals_refresh_started" not in st.session_state:
    st.session_state.fundamentals_refresh_started = False
if "agent_steps" not in st.session_state:
    st.session_state.agent_steps = []
if "filter_caveat" not in st.session_state:
    st.session_state.filter_caveat = ""


# ── Fundamentals background refresh ──────────────────────────────────────────
def _start_fundamentals_refresh() -> None:
    """On first load: extract from screener_cache (instant), then fetch displayed stocks."""
    from src.fundamentals_cache import sync_from_screener_cache, start_background_refresh
    sync_from_screener_cache()
    try:
        from src.nse_client import get_stocks_near_52wk_high
        near_high = get_stocks_near_52wk_high(threshold_pct=5.0)
        if not near_high.empty:
            start_background_refresh(near_high["symbol"].tolist(), delay=0.4)
    except Exception:
        pass


if not st.session_state.fundamentals_refresh_started:
    st.session_state.fundamentals_refresh_started = True
    _start_fundamentals_refresh()


# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def load_universe() -> pd.DataFrame:
    return get_nifty_universe()


@st.cache_data(ttl=1800, show_spinner=False)
def load_ohlc(symbol: str, period: str, interval: str) -> pd.DataFrame:
    return get_historical_ohlc(symbol, period=period, interval=interval)


@st.cache_data(ttl=86400, show_spinner=False)
def load_screener(symbol: str) -> dict:
    data = get_stock_data(symbol)
    # Also cache fundamentals whenever screener data is freshly loaded
    if data:
        try:
            from src.fundamentals_cache import extract_metrics
            from src.database import upsert_fundamentals
            upsert_fundamentals(symbol, extract_metrics(data))
        except Exception:
            pass
    return data


def get_enriched_universe() -> pd.DataFrame:
    """Universe df merged with cached fundamentals (LEFT JOIN — NaN for uncached stocks)."""
    universe = load_universe()
    fundamentals = get_all_fundamentals()
    if fundamentals.empty:
        return universe
    fund_cols = [c for c in fundamentals.columns if c not in ("symbol", "fetched_at", "latest_quarter", "shareholding_quarter")]
    merged = universe.merge(fundamentals[["symbol"] + fund_cols], on="symbol", how="left")
    return merged


# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_inr(val) -> str:
    try:
        v = float(str(val).replace(",", ""))
        if v >= 1e7:
            return f"₹{v/1e7:.2f} Cr"
        return f"₹{v:,.2f}"
    except (ValueError, TypeError):
        return str(val)


def render_ratio_grid(ratios: dict) -> None:
    if not ratios:
        st.info("Fundamental data not available.")
        return

    ORDER = [
        "Market Cap", "Current Price", "High / Low",
        "Stock P/E", "Book Value", "Dividend Yield",
        "ROCE", "ROE", "Face Value",
        "ROCE 5Yr", "ROE 5Yr", "Industry PE",
        "ROCE 10Yr", "ROE 10Yr", "Current Discount",
        "Sales growth", "Sales growth 5Years", "Sales growth 7Years",
        "Debt to equity", "Profit Var 5Yrs", "Free Cash Flow",
        "Pledged percentage", "EPS growth 3Years", "EPS growth 5Years",
        "Return on assets", "Price to book value", "EV / EBIT",
    ]
    shown = {k: v for k, v in ratios.items() if k in ORDER}
    extras = {k: v for k, v in ratios.items() if k not in ORDER}
    display = {k: shown.get(k, extras.get(k, "")) for k in ORDER if k in shown or k in extras}
    display.update({k: v for k, v in extras.items() if k not in display})

    items = list(display.items())
    cols = st.columns(3)
    for i, (label, value) in enumerate(items):
        with cols[i % 3]:
            st.markdown(
                f'<div class="ratio-card">'
                f'<div class="ratio-label">{label}</div>'
                f'<div class="ratio-value">{value}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def render_financial_table(table_data: dict, title: str) -> None:
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)
    if not table_data or not table_data.get("rows"):
        st.info("Data not available.")
        return

    headers = table_data.get("headers", [])
    rows = table_data.get("rows", {})

    if not headers or not rows:
        st.info("Data not available.")
        return

    df_rows = []
    for row_name, row_data in rows.items():
        row = {"": row_name}
        for h in headers:
            row[h] = row_data.get(h, "")
        df_rows.append(row)

    if not df_rows:
        return

    df = pd.DataFrame(df_rows)
    cols_to_show = [""] + headers[-12:]
    df = df[[c for c in cols_to_show if c in df.columns]]

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=min(400, 35 * (len(df) + 1) + 10),
    )


def render_shareholding(data: dict) -> None:
    st.markdown('<div class="section-header">Shareholding Pattern</div>', unsafe_allow_html=True)
    if not data or not data.get("rows"):
        st.info("Shareholding data not available.")
        return

    headers = data.get("headers", [])
    rows = data.get("rows", {})

    if not headers or not rows:
        st.info("Shareholding data not available.")
        return

    df_rows = []
    for row_name, row_data in rows.items():
        row = {"Holder": row_name}
        for h in headers:
            row[h] = row_data.get(h, "")
        df_rows.append(row)

    if not df_rows:
        return

    df = pd.DataFrame(df_rows)
    cols_to_show = ["Holder"] + headers[-12:]
    df = df[[c for c in cols_to_show if c in df.columns]]

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=min(300, 35 * (len(df) + 1) + 10),
    )


def render_peers_table(peers: list[dict]) -> None:
    if not peers:
        return
    st.markdown('<div class="section-header">Peer Comparison</div>', unsafe_allow_html=True)
    df = pd.DataFrame(peers)
    st.dataframe(df, use_container_width=True, hide_index=True, height=200)


def render_stock_list(df: pd.DataFrame, key_prefix: str = "") -> None:
    if df.empty:
        st.warning("No stocks found.")
        return

    for _, row in df.iterrows():
        sym = row["symbol"]
        price = row.get("last_price", 0)
        pct = row.get("pct_change", 0)
        pct_high = row.get("pct_from_high", 0)
        is_selected = st.session_state.selected_symbol == sym

        col1, col2 = st.columns([3, 1])
        with col1:
            if st.button(
                f"{sym}",
                key=f"{key_prefix}btn_{sym}",
                use_container_width=True,
                type="primary" if is_selected else "secondary",
            ):
                st.session_state.selected_symbol = sym
                st.rerun()
        with col2:
            color = "#26a69a" if pct >= 0 else "#ef5350"
            sign = "+" if pct >= 0 else ""
            st.markdown(
                f'<div style="color:{color};font-size:12px;padding-top:8px;text-align:right">'
                f'{sign}{pct:.1f}%<br>'
                f'<span style="color:#555;font-size:10px">{pct_high:.1f}% from high</span>'
                f'</div>',
                unsafe_allow_html=True,
            )


def render_watchlist_popover(symbol: str) -> None:
    with st.popover("⭐ Watchlist"):
        watchlists = get_watchlists()
        if watchlists:
            wl_options = {w["name"]: w["id"] for w in watchlists}
            chosen_name = st.selectbox(
                "Add to existing", list(wl_options.keys()), key=f"wl_sel_{symbol}"
            )
            if st.button("Add to Watchlist", key=f"wl_add_{symbol}"):
                add_to_watchlist(wl_options[chosen_name], symbol)
                st.success(f"Added to {chosen_name}")
            st.divider()
        new_wl_name = st.text_input("Create new watchlist", key=f"wl_new_name_{symbol}", placeholder="Watchlist name...")
        if st.button("Create & Add", key=f"wl_create_{symbol}") and new_wl_name.strip():
            try:
                wl_id = create_watchlist(new_wl_name.strip())
                add_to_watchlist(wl_id, symbol)
                st.success(f"Created '{new_wl_name}' and added {symbol}")
            except Exception:
                st.error("A watchlist with that name already exists.")


# ── MAIN LAYOUT ───────────────────────────────────────────────────────────────
st.markdown("## 📈 Stock Market Dashboard")

tab_screener, tab_watchlists, tab_history = st.tabs(["📈 Screener", "⭐ Watchlists", "📋 Filter History"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — SCREENER
# ══════════════════════════════════════════════════════════════════════════════
with tab_screener:
    left_col, right_col = st.columns([1, 3], gap="medium")

    # ── LEFT PANEL ────────────────────────────────────────────────────────────
    with left_col:
        st.markdown('<div class="section-header">Stock Filter</div>', unsafe_allow_html=True)

        nl_query = st.text_area(
            "Natural language query",
            placeholder='e.g. "stocks within 2% of 52-week high with positive change today"',
            height=80,
            label_visibility="collapsed",
        )

        col_run, col_reset = st.columns(2)
        with col_run:
            run_filter = st.button("Run Filter", type="primary", use_container_width=True)
        with col_reset:
            reset_filter = st.button("52W High", use_container_width=True)

        if reset_filter:
            st.session_state.filter_active = False
            st.session_state.filter_summary = ""
            st.session_state.stock_df = pd.DataFrame()
            st.session_state.agent_steps = []
            st.session_state.filter_caveat = ""
            st.rerun()

        if run_filter and nl_query.strip():
            if not os.environ.get("ANTHROPIC_API_KEY"):
                st.error("Set ANTHROPIC_API_KEY in your .env file to use AI filtering.")
            else:
                with st.spinner("Running multi-agent filter pipeline…"):
                    try:
                        enriched = get_enriched_universe()
                        result = run_agent_filter(nl_query.strip(), enriched)
                        st.session_state.stock_df = result.filtered_df
                        st.session_state.filter_active = True
                        st.session_state.filter_summary = result.summary
                        st.session_state.agent_steps = result.steps
                        st.session_state.filter_caveat = result.caveat
                        st.rerun()
                    except Exception as e:
                        st.error(f"Filter error: {e}")

        # Fundamentals coverage
        n_fund = get_fundamentals_count()
        if n_fund > 0:
            st.caption(f"🧠 Fundamentals cached: {n_fund} / 426 stocks — fundamental filters active")
        else:
            st.caption("🧠 Fundamentals loading in background…")

        # Agent reasoning expander (visible after a filter run)
        if st.session_state.filter_active and st.session_state.get("agent_steps"):
            _STATUS_ICON = {"done": "✓", "warning": "⚠", "error": "✗", "running": "…"}
            _STATUS_COLOR = {"done": "#26a69a", "warning": "#ffa500", "error": "#ef5350", "running": "#8b9dc3"}
            with st.expander("🧠 Agent reasoning", expanded=False):
                for step in st.session_state.agent_steps:
                    icon = _STATUS_ICON.get(step.status, "•")
                    color = _STATUS_COLOR.get(step.status, "#8b9dc3")
                    st.markdown(
                        f'<div style="border-left:3px solid {color};padding:4px 10px;margin:4px 0">'
                        f'<b style="color:{color}">{icon} {step.agent_name}</b><br>'
                        f'<span style="color:#c0c4cc;font-size:12px">{step.reasoning}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    # Show per-column coverage for the Data Enricher step
                    if step.agent_name == "Data Enricher":
                        for col, cov in step.details.items():
                            if col == "warnings" or not isinstance(cov, dict):
                                continue
                            pct = cov.get("pct", 0)
                            bar_col = "#26a69a" if pct > 60 else ("#ffa500" if pct > 20 else "#ef5350")
                            st.markdown(
                                f'<div style="font-size:11px;color:#8b9dc3;margin-left:16px">'
                                f'{col}: {cov["available"]}/{cov["total"]} stocks '
                                f'<span style="color:{bar_col}">({pct}%)</span></div>',
                                unsafe_allow_html=True,
                            )

        # Caveat warning from Validator
        if st.session_state.filter_active and st.session_state.get("filter_caveat"):
            st.warning(st.session_state.filter_caveat)

        # Save filtered result as watchlist
        if st.session_state.filter_active and not st.session_state.stock_df.empty:
            with st.popover("💾 Save as Watchlist", use_container_width=True):
                wl_save_name = st.text_input("Watchlist name", key="wl_save_name", placeholder="My filter...")
                if st.button("Save", key="wl_save_btn") and wl_save_name.strip():
                    syms = st.session_state.stock_df["symbol"].tolist()
                    try:
                        save_filter_as_watchlist(wl_save_name.strip(), syms)
                        st.success(f"Saved {len(syms)} stocks to '{wl_save_name}'")
                    except Exception:
                        st.error("A watchlist with that name already exists.")

        # Stock search
        st.markdown('<div class="section-header">Stocks</div>', unsafe_allow_html=True)
        search_q = st.text_input(
            "Search",
            placeholder="🔍 Symbol or company name...",
            label_visibility="collapsed",
            key="stock_search",
        )

        if st.session_state.filter_active and not st.session_state.stock_df.empty:
            if st.session_state.filter_summary:
                st.caption(f"Filter: {st.session_state.filter_summary}")
            display_df = st.session_state.stock_df
        else:
            with st.spinner("Loading stocks near 52-week high..."):
                display_df = get_stocks_near_52wk_high(threshold_pct=5.0)

        if search_q:
            sq = search_q.strip()
            mask = (
                display_df["symbol"].str.contains(sq, case=False, na=False)
                | display_df["name"].str.contains(sq, case=False, na=False)
            )
            display_df = display_df[mask]

        if not display_df.empty and st.session_state.selected_symbol is None:
            st.session_state.selected_symbol = display_df.iloc[0]["symbol"]

        st.caption(f"{len(display_df)} stocks")
        render_stock_list(display_df)

    # ── RIGHT PANEL ───────────────────────────────────────────────────────────
    with right_col:
        symbol = st.session_state.selected_symbol

        if symbol is None:
            st.info("Select a stock from the left panel.")
        else:
            # Stock header
            stock_row = pd.DataFrame()
            if not display_df.empty:
                match = display_df[display_df["symbol"] == symbol]
                if not match.empty:
                    stock_row = match.iloc[0]

            price = float(stock_row.get("last_price", 0)) if not stock_row.empty else 0
            pct = float(stock_row.get("pct_change", 0)) if not stock_row.empty else 0
            yr_high = float(stock_row.get("year_high", 0)) if not stock_row.empty else 0
            yr_low = float(stock_row.get("year_low", 0)) if not stock_row.empty else 0
            pct_from_high = float(stock_row.get("pct_from_high", 0)) if not stock_row.empty else 0

            sign = "+" if pct >= 0 else ""
            chg_color = "#26a69a" if pct >= 0 else "#ef5350"

            h1, h2, h3, h4 = st.columns([2, 1, 1, 1])
            with h1:
                st.markdown(
                    f'<div class="price-big">{symbol}</div>'
                    f'<div style="color:#8b9dc3;font-size:13px;margin-bottom:4px">NSE</div>',
                    unsafe_allow_html=True,
                )
            with h2:
                st.markdown(
                    f'<div style="text-align:right">'
                    f'<div class="price-big">₹{price:,.2f}</div>'
                    f'<div style="color:{chg_color};font-size:14px">{sign}{pct:.2f}%</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with h3:
                st.markdown(
                    f'<div style="text-align:right;color:#8b9dc3;font-size:12px;padding-top:6px">'
                    f'52W High: <b style="color:#ffa500">₹{yr_high:,.2f}</b><br>'
                    f'52W Low: <b style="color:#6495ed">₹{yr_low:,.2f}</b><br>'
                    f'<span style="color:#555">{pct_from_high:.1f}% from high</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with h4:
                st.markdown("<br>", unsafe_allow_html=True)
                render_watchlist_popover(symbol)

            st.markdown("---")

            # Screener fundamentals
            with st.spinner(f"Loading fundamentals for {symbol}..."):
                screener_data = load_screener(symbol)

            name = screener_data.get("name", symbol)
            if name and name != symbol:
                st.markdown(f"**{name}**", unsafe_allow_html=False)

            # Key ratios
            st.markdown('<div class="section-header">Key Ratios</div>', unsafe_allow_html=True)
            render_ratio_grid(screener_data.get("ratios", {}))

            st.markdown("---")

            # Chart
            st.markdown('<div class="section-header">Price Chart</div>', unsafe_allow_html=True)

            tf_col1, tf_col2, tf_col3, tf_col4 = st.columns(4)
            with tf_col1:
                if st.button("Daily 1Y", key="tf_d1y", use_container_width=True,
                             type="primary" if st.session_state.chart_period == "1y" and st.session_state.chart_interval == "1d" else "secondary"):
                    st.session_state.chart_period = "1y"
                    st.session_state.chart_interval = "1d"
                    st.rerun()
            with tf_col2:
                if st.button("Daily 6M", key="tf_d6m", use_container_width=True,
                             type="primary" if st.session_state.chart_period == "6mo" and st.session_state.chart_interval == "1d" else "secondary"):
                    st.session_state.chart_period = "6mo"
                    st.session_state.chart_interval = "1d"
                    st.rerun()
            with tf_col3:
                if st.button("Weekly 2Y", key="tf_w2y", use_container_width=True,
                             type="primary" if st.session_state.chart_period == "2y" and st.session_state.chart_interval == "1wk" else "secondary"):
                    st.session_state.chart_period = "2y"
                    st.session_state.chart_interval = "1wk"
                    st.rerun()
            with tf_col4:
                if st.button("Weekly 5Y", key="tf_w5y", use_container_width=True,
                             type="primary" if st.session_state.chart_period == "5y" and st.session_state.chart_interval == "1wk" else "secondary"):
                    st.session_state.chart_period = "5y"
                    st.session_state.chart_interval = "1wk"
                    st.rerun()

            with st.spinner("Loading chart data..."):
                ohlc = load_ohlc(symbol, st.session_state.chart_period, st.session_state.chart_interval)

            fig = build_candlestick_chart(ohlc, symbol, year_high=yr_high, year_low=yr_low)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

            st.markdown("---")

            # Financial tables + Shareholding
            tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
                "Quarterly Results",
                "Profit & Loss",
                "Balance Sheet",
                "Cash Flow",
                "Shareholding",
                "Peers",
            ])

            with tab1:
                render_financial_table(screener_data.get("quarterly", {}), "Quarterly Results")
            with tab2:
                render_financial_table(screener_data.get("annual_pl", {}), "Profit & Loss (Annual)")
            with tab3:
                render_financial_table(screener_data.get("balance_sheet", {}), "Balance Sheet")
            with tab4:
                render_financial_table(screener_data.get("cash_flow", {}), "Cash Flow")
            with tab5:
                render_shareholding(screener_data.get("shareholding", {}))
            with tab6:
                render_peers_table(screener_data.get("peers", []))

            st.markdown(
                f'<div style="margin-top:12px;color:#4e9af1;font-size:12px">'
                f'<a href="https://www.screener.in/company/{symbol}/consolidated/" target="_blank" '
                f'style="color:#4e9af1">View on Screener.in ↗</a></div>',
                unsafe_allow_html=True,
            )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — WATCHLISTS
# ══════════════════════════════════════════════════════════════════════════════
with tab_watchlists:
    st.markdown("### ⭐ Watchlists")

    wl_left, wl_right = st.columns([1, 3], gap="medium")

    with wl_left:
        st.markdown('<div class="section-header">Manage</div>', unsafe_allow_html=True)
        new_wl = st.text_input("New watchlist name", key="new_wl_input", placeholder="e.g. NBFC Picks")
        if st.button("+ Create Watchlist", use_container_width=True) and new_wl.strip():
            try:
                create_watchlist(new_wl.strip())
                st.success(f"Created '{new_wl}'")
                st.rerun()
            except Exception:
                st.error("A watchlist with that name already exists.")

        watchlists = get_watchlists()
        if watchlists:
            st.markdown('<div class="section-header">Your Watchlists</div>', unsafe_allow_html=True)
            for wl in watchlists:
                is_active = st.session_state.active_watchlist_id == wl["id"]
                if st.button(
                    f"{'▶ ' if is_active else ''}{wl['name']} ({wl['count']})",
                    key=f"wl_btn_{wl['id']}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    st.session_state.active_watchlist_id = wl["id"]
                    st.rerun()

        # Delete active watchlist
        if st.session_state.active_watchlist_id:
            st.markdown("---")
            if st.button("🗑 Delete this Watchlist", type="secondary", use_container_width=True):
                delete_watchlist(st.session_state.active_watchlist_id)
                st.session_state.active_watchlist_id = None
                st.rerun()

    with wl_right:
        watchlists = get_watchlists()
        active_id = st.session_state.active_watchlist_id

        if active_id is None:
            if watchlists:
                st.info("Select a watchlist on the left to view its stocks.")
            else:
                st.info("No watchlists yet. Create one on the left, then add stocks via the ⭐ Watchlist button on any stock.")
        else:
            # Find active watchlist name
            active_wl = next((w for w in watchlists if w["id"] == active_id), None)
            if active_wl is None:
                st.session_state.active_watchlist_id = None
                st.rerun()

            st.markdown(f'<div class="section-header">{active_wl["name"]} — {active_wl["count"]} stocks</div>', unsafe_allow_html=True)

            symbols = get_watchlist_stocks(active_id)
            if not symbols:
                st.info("This watchlist is empty. Add stocks from the Screener tab using the ⭐ Watchlist button.")
            else:
                with st.spinner("Loading stock data..."):
                    universe = load_universe()
                wl_df = universe[universe["symbol"].isin(symbols)].copy()

                # Preserve watchlist order
                sym_order = {s: i for i, s in enumerate(symbols)}
                wl_df["_order"] = wl_df["symbol"].map(sym_order)
                wl_df = wl_df.sort_values("_order").drop(columns=["_order"])

                # Per-stock remove button + stock button
                for _, row in wl_df.iterrows():
                    sym = row["symbol"]
                    pct = row.get("pct_change", 0)
                    pct_high = row.get("pct_from_high", 0)
                    color = "#26a69a" if pct >= 0 else "#ef5350"
                    sign = "+" if pct >= 0 else ""

                    c1, c2, c3 = st.columns([3, 1, 1])
                    with c1:
                        if st.button(sym, key=f"wl_stock_{sym}", use_container_width=True,
                                     type="primary" if st.session_state.selected_symbol == sym else "secondary"):
                            st.session_state.selected_symbol = sym
                            st.rerun()
                    with c2:
                        st.markdown(
                            f'<div style="color:{color};font-size:12px;padding-top:8px;text-align:right">'
                            f'{sign}{pct:.1f}%<br>'
                            f'<span style="color:#555;font-size:10px">{pct_high:.1f}% from high</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    with c3:
                        if st.button("✕", key=f"wl_rm_{sym}", help=f"Remove {sym} from watchlist"):
                            remove_from_watchlist(active_id, sym)
                            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — FILTER HISTORY
# ══════════════════════════════════════════════════════════════════════════════
with tab_history:
    st.markdown("### 📋 Filter History")

    history = get_filter_history(limit=50)
    if not history:
        st.info("No filter history yet. Run a natural language filter in the Screener tab.")
    else:
        st.caption(f"{len(history)} saved queries")
        for h in history:
            run_at = h.get("run_at", "")[:16].replace("T", " ")
            query_text = h.get("query_text", "")
            symbols = json.loads(h.get("result_symbols", "[]") or "[]")

            with st.container():
                c1, c2, c3 = st.columns([4, 1, 1])
                with c1:
                    st.markdown(f"**{query_text}**")
                    st.caption(f"{run_at} · {len(symbols)} stocks")
                with c2:
                    if st.button("Replay", key=f"replay_{h['id']}", use_container_width=True):
                        with st.spinner("Restoring filter..."):
                            universe = load_universe()
                        restored = universe[universe["symbol"].isin(symbols)] if symbols else pd.DataFrame()
                        st.session_state.stock_df = restored
                        st.session_state.filter_active = True
                        st.session_state.filter_summary = query_text
                        st.rerun()
                with c3:
                    # Save history entry as watchlist
                    if symbols:
                        with st.popover("💾", help="Save as watchlist"):
                            wl_name_h = st.text_input("Name", key=f"hist_wl_name_{h['id']}", placeholder="Watchlist name...")
                            if st.button("Save", key=f"hist_wl_save_{h['id']}") and wl_name_h.strip():
                                try:
                                    save_filter_as_watchlist(wl_name_h.strip(), symbols)
                                    st.success(f"Saved to '{wl_name_h}'")
                                except Exception:
                                    st.error("Name already exists.")
                st.divider()
