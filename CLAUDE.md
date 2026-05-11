# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
streamlit run app.py
```

Requires a `.env` file with `ANTHROPIC_API_KEY=sk-ant-...` (copy from `.env.example`).

## Architecture

This is a single-page Streamlit dashboard with a 1:3 column layout (stock list left, stock detail right). All Python modules live in `src/`.

**Data flow:**
1. On load, `nse_client.py` fetches the ~160-stock universe via `yfinance.download()` (bulk, 1-year daily data) and caches the result in SQLite for 15 minutes. NSE India's API was dropped — it uses Akamai bot detection that `requests` cannot bypass.
2. Clicking a stock triggers `screener_client.py` to scrape Screener.in (BeautifulSoup4) and cache results for 24 hours in SQLite.
3. Chart data comes from `yfinance` (`SYMBOL.NS` suffix) — not NSE directly, since NSE's chart API is harder to scrape.
4. The natural language filter (`nl_filter.py`) sends the query to Claude Haiku, gets back JSON filter criteria, applies them to the in-memory DataFrame, then persists the query + result symbols to SQLite.

**Module responsibilities:**
- `src/database.py` — all SQLite I/O: `init_db()`, screener cache (24h TTL), NSE cache (15min TTL), filter history
- `src/nse_client.py` — NSE cookie session, `get_nifty_universe()`, `get_stocks_near_52wk_high(threshold_pct)`, `get_historical_ohlc()`
- `src/screener_client.py` — `get_stock_data(symbol)` returns `{ratios, quarterly, annual_pl, balance_sheet, cash_flow, shareholding, peers}`
- `src/nl_filter.py` — `run_nl_filter(query, df)` → `(filtered_df, filter_spec_dict)`; the system prompt constrains Claude to only filter on columns present in the NSE DataFrame
- `src/charts.py` — `build_candlestick_chart(ohlc_df, symbol, year_high, year_low)` returns a dark-themed Plotly figure with a volume subplot
- `app.py` — Streamlit session state (`selected_symbol`, `stock_df`, `filter_active`, `chart_period`, `chart_interval`); uses `@st.cache_data` for OHLC and screener data

**SQLite schema** (`data/stocks.db`):
- `filter_history(id, query_text, filter_json, result_symbols, run_at)`
- `screener_cache(symbol, data_json, fetched_at)`
- `nse_cache(id=1, data_json, fetched_at)` — single-row cache for the full universe

## Key Constraints

- **yfinance symbol mapping**: `NSE_UNIVERSE` in `nse_client.py` is a `dict[display_symbol → yfinance_ticker]`. Some NSE symbols differ from their yfinance equivalents (e.g. `ZOMATO → ETERNAL`, `INFY → INFY`). When adding new stocks, verify the yfinance ticker works before adding. `get_historical_ohlc()` also uses this map so Screener.in symbol names resolve to the correct yfinance ticker.
- **Screener.in scraping**: The parser targets `id="top-ratios"` for the ratios list, and section IDs `quarters`, `profit-loss`, `balance-sheet`, `cash-flow`, `shareholding` for tables. If Screener changes their HTML, update `_parse_ratios()` and `_parse_table()` in `screener_client.py`.
- **NL filter only operates on NSE DataFrame columns**: The Claude system prompt in `nl_filter.py` lists the available columns explicitly. Fundamental metrics (P/E, ROE, etc.) are NOT in the NSE DataFrame — they require a per-stock Screener fetch and cannot be bulk-filtered.
- **`app.py` must be run from the project root** so that `src/` is on the Python path (Streamlit sets CWD to the script directory automatically).
