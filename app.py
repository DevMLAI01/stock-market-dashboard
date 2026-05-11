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

from src.database import init_db, get_filter_history
from src.nse_client import get_stocks_near_52wk_high, get_nifty_universe, get_historical_ohlc
from src.screener_client import get_stock_data
from src.nl_filter import run_nl_filter
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
  /* Dark theme base */
  .stApp { background-color: #0e1117; }

  /* Metric cards */
  .ratio-card {
    background: #1a1d27;
    border: 1px solid #2a2d3e;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 4px 0;
  }
  .ratio-label { color: #8b9dc3; font-size: 12px; margin-bottom: 2px; }
  .ratio-value { color: #f0f2f6; font-size: 16px; font-weight: 600; }

  /* Stock list item */
  .stock-item {
    padding: 10px 12px;
    border-radius: 6px;
    cursor: pointer;
    border-left: 3px solid transparent;
    margin-bottom: 2px;
  }
  .stock-item:hover { background: #1a1d27; }
  .stock-item.selected {
    background: #1a2744;
    border-left-color: #4e9af1;
  }
  .stock-sym { font-weight: 700; font-size: 14px; color: #f0f2f6; }
  .stock-price { font-size: 13px; color: #a0a8be; }
  .stock-badge {
    font-size: 11px;
    padding: 2px 6px;
    border-radius: 4px;
    font-weight: 600;
  }
  .badge-green { background: #1b3a2a; color: #26a69a; }
  .badge-red { background: #3a1b1b; color: #ef5350; }

  /* Table styling */
  .fin-table th {
    background: #1a1d27 !important;
    color: #8b9dc3 !important;
    font-size: 12px !important;
    font-weight: 600 !important;
  }
  .fin-table td { font-size: 12px !important; }

  /* Section headers */
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

  /* Price header */
  .price-big { font-size: 28px; font-weight: 700; color: #f0f2f6; }
  .change-pos { color: #26a69a; font-size: 16px; font-weight: 600; }
  .change-neg { color: #ef5350; font-size: 16px; font-weight: 600; }

  /* History item */
  .hist-item {
    padding: 6px 8px;
    border-radius: 4px;
    margin-bottom: 3px;
    cursor: pointer;
    font-size: 12px;
    color: #8b9dc3;
    background: #1a1d27;
  }
  .hist-item:hover { background: #252837; }
  .hist-date { color: #4e9af1; font-size: 10px; }

  /* Hide streamlit chrome */
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


# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def load_universe() -> pd.DataFrame:
    return get_nifty_universe()


@st.cache_data(ttl=1800, show_spinner=False)
def load_ohlc(symbol: str, period: str, interval: str) -> pd.DataFrame:
    return get_historical_ohlc(symbol, period=period, interval=interval)


@st.cache_data(ttl=86400, show_spinner=False)
def load_screener(symbol: str) -> dict:
    return get_stock_data(symbol)


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

    # Build DataFrame
    df_rows = []
    for row_name, row_data in rows.items():
        row = {"": row_name}
        for h in headers:
            row[h] = row_data.get(h, "")
        df_rows.append(row)

    if not df_rows:
        return

    df = pd.DataFrame(df_rows)
    # Show only last 12 quarters / last 12 years
    cols_to_show = [""] + headers[-12:]
    df = df[[c for c in cols_to_show if c in df.columns]]

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=min(400, 35 * (len(df) + 1) + 10),
    )


def render_peers_table(peers: list[dict]) -> None:
    if not peers:
        return
    st.markdown('<div class="section-header">Peer Comparison</div>', unsafe_allow_html=True)
    df = pd.DataFrame(peers)
    st.dataframe(df, use_container_width=True, hide_index=True, height=200)


def render_stock_list(df: pd.DataFrame) -> None:
    if df.empty:
        st.warning("No stocks found.")
        return

    for _, row in df.iterrows():
        sym = row["symbol"]
        price = row.get("last_price", 0)
        pct = row.get("pct_change", 0)
        pct_high = row.get("pct_from_high", 0)
        is_selected = st.session_state.selected_symbol == sym

        badge_cls = "badge-green" if pct >= 0 else "badge-red"
        sign = "+" if pct >= 0 else ""

        col1, col2 = st.columns([3, 1])
        with col1:
            if st.button(
                f"{sym}",
                key=f"btn_{sym}",
                use_container_width=True,
                type="primary" if is_selected else "secondary",
            ):
                st.session_state.selected_symbol = sym
                st.rerun()
        with col2:
            color = "#26a69a" if pct >= 0 else "#ef5350"
            st.markdown(
                f'<div style="color:{color};font-size:12px;padding-top:8px;text-align:right">'
                f'{sign}{pct:.1f}%<br>'
                f'<span style="color:#555;font-size:10px">{pct_high:.1f}% from high</span>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ── MAIN LAYOUT ───────────────────────────────────────────────────────────────
st.markdown("## 📈 Stock Market Dashboard")

left_col, right_col = st.columns([1, 3], gap="medium")

# ══════════════════════════════════════════════════════════════════════════════
# LEFT PANEL
# ══════════════════════════════════════════════════════════════════════════════
with left_col:
    # Natural language filter
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
        st.rerun()

    if run_filter and nl_query.strip():
        if not os.environ.get("ANTHROPIC_API_KEY"):
            st.error("Set ANTHROPIC_API_KEY in your .env file to use AI filtering.")
        else:
            with st.spinner("Loading stock universe..."):
                universe = load_universe()
            with st.spinner("Applying AI filter..."):
                try:
                    filtered_df, spec = run_nl_filter(nl_query.strip(), universe)
                    st.session_state.stock_df = filtered_df
                    st.session_state.filter_active = True
                    st.session_state.filter_summary = spec.get("summary", nl_query)
                    st.rerun()
                except Exception as e:
                    st.error(f"Filter error: {e}")

    # Filter history
    history = get_filter_history(limit=10)
    if history:
        st.markdown('<div class="section-header">Filter History</div>', unsafe_allow_html=True)
        for h in history:
            run_at = h.get("run_at", "")[:16].replace("T", " ")
            query_text = h.get("query_text", "")
            symbols = json.loads(h.get("result_symbols", "[]") or "[]")
            n = len(symbols)
            if st.button(
                f"[{run_at}] {query_text[:30]}{'...' if len(query_text) > 30 else ''} ({n})",
                key=f"hist_{h['id']}",
                use_container_width=True,
            ):
                # Restore this historical filter
                with st.spinner("Restoring filter..."):
                    universe = load_universe()
                    if symbols:
                        restored = universe[universe["symbol"].isin(symbols)]
                    else:
                        restored = pd.DataFrame()
                st.session_state.stock_df = restored
                st.session_state.filter_active = True
                st.session_state.filter_summary = query_text
                st.rerun()

    # Stock list
    st.markdown('<div class="section-header">Stocks</div>', unsafe_allow_html=True)

    if st.session_state.filter_active and not st.session_state.stock_df.empty:
        if st.session_state.filter_summary:
            st.caption(f"Filter: {st.session_state.filter_summary}")
        display_df = st.session_state.stock_df
    else:
        with st.spinner("Loading stocks near 52-week high..."):
            display_df = get_stocks_near_52wk_high(threshold_pct=5.0)

    if not display_df.empty and st.session_state.selected_symbol is None:
        st.session_state.selected_symbol = display_df.iloc[0]["symbol"]

    render_stock_list(display_df)

# ══════════════════════════════════════════════════════════════════════════════
# RIGHT PANEL — Stock Detail
# ══════════════════════════════════════════════════════════════════════════════
with right_col:
    symbol = st.session_state.selected_symbol

    if symbol is None:
        st.info("Select a stock from the left panel.")
    else:
        # ── Stock header ───────────────────────────────────────────────────
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

        h1, h2, h3 = st.columns([2, 1, 1])
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

        st.markdown("---")

        # ── Screener fundamentals ──────────────────────────────────────────
        with st.spinner(f"Loading fundamentals for {symbol}..."):
            screener_data = load_screener(symbol)

        name = screener_data.get("name", symbol)
        if name and name != symbol:
            st.markdown(f"**{name}**", unsafe_allow_html=False)

        # Ratios grid
        st.markdown('<div class="section-header">Key Ratios</div>', unsafe_allow_html=True)
        render_ratio_grid(screener_data.get("ratios", {}))

        st.markdown("---")

        # ── Chart ─────────────────────────────────────────────────────────
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

        # ── Financial tables ───────────────────────────────────────────────
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "Quarterly Results",
            "Profit & Loss",
            "Balance Sheet",
            "Cash Flow",
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
            render_peers_table(screener_data.get("peers", []))

        # Screener link
        st.markdown(
            f'<div style="margin-top:12px;color:#4e9af1;font-size:12px">'
            f'<a href="https://www.screener.in/company/{symbol}/consolidated/" target="_blank" '
            f'style="color:#4e9af1">View on Screener.in ↗</a></div>',
            unsafe_allow_html=True,
        )
