<div align="center">

# 📈 Stock Market Dashboard

### AI-Powered Indian Stock Screener — Natural Language Filters, Live Charts & Screener.in Fundamentals

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-red?logo=streamlit)](https://streamlit.io)
[![Claude AI](https://img.shields.io/badge/Claude-Haiku_4.5-orange?logo=anthropic)](https://anthropic.com)
[![yfinance](https://img.shields.io/badge/yfinance-1.3+-green)](https://pypi.org/project/yfinance)
[![Plotly](https://img.shields.io/badge/Plotly-5.18+-purple?logo=plotly)](https://plotly.com)
[![SQLite](https://img.shields.io/badge/SQLite-3-lightgrey?logo=sqlite)](https://sqlite.org)
[![Streamlit Cloud](https://img.shields.io/badge/Deploy-Streamlit_Cloud-ff4b4b?logo=streamlit)](https://share.streamlit.io)

<div align="center">

| 📊 Universe | 🎯 Near 52W High | ⚡ NL Filter | 💰 Running Cost |
|:---:|:---:|:---:|:---:|
| **163 NSE stocks** | **auto-filtered** | **Claude Haiku** | **~$1–3 / month** |

</div>

A personal stock research dashboard for Indian markets — type what you want in plain English, get a filtered list of NSE stocks, and click any stock to see its full fundamental profile: key ratios, candlestick chart (daily/weekly), quarterly results, annual P&L, balance sheet, cash flow, and peer comparison — all sourced from Screener.in.

</div>

---

## 🎯 The Problem

Researching Indian stocks typically means juggling three or four tabs:

- **Screener.in** for fundamentals and historical financials
- **NSE/BSE** for live prices and 52-week data
- **TradingView** or Moneycontrol for charts
- A notebook to track which stocks you already looked at

**This dashboard collapses all of that into one screen**, with a persistent natural-language filter that remembers every query you've ever run.

---

## ✨ Demo

### Natural Language Filter Flow
```
You type: "Show me stocks within 2% of their 52-week high with positive change today"
              ↓
     Claude parses → filter criteria JSON
              ↓
     Applied to 163-stock NSE universe (yfinance)
              ↓
     Filtered list saved to history + displayed
              ↓  (click any stock)
     Screener.in fundamentals fetched + cached 24h
```

### Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  📈 Stock Market Dashboard                                          │
├───────────────────┬─────────────────────────────────────────────────┤
│  STOCK FILTER     │  BAJFINANCE                    ₹936  -2.02%     │
│                   │  52W High: ₹1,102   Low: ₹788   15.1% discount  │
│  ┌─────────────┐  ├─────────────────────────────────────────────────┤
│  │ Type query  │  │  KEY RATIOS                                      │
│  │ in plain    │  │  Mkt Cap ₹5,82,780 Cr  │ P/E    30.3           │
│  │ English...  │  │  ROCE        10.8%      │ ROE    18.2%          │
│  └─────────────┘  │  Book Value   ₹183      │ Div    0.58%          │
│  [Run Filter]     │  Sales 5Y     25.2%     │ D/E    3.82           │
│  [52W High]       ├─────────────────────────────────────────────────┤
│                   │  CHART  [Daily 1Y] [Daily 6M] [Weekly 2Y] [5Y]  │
│  FILTER HISTORY   │  ┌─────────────────────────────────────────────┐ │
│  • 2026-05-11     │  │  ▲ candlestick + volume  ── 52W High/Low   │ │
│    "NBFC > 18 ROE"│  └─────────────────────────────────────────────┘ │
│  • 2026-05-10     ├─────────────────────────────────────────────────┤
│    "52wk high"    │  [Quarterly] [P&L] [Balance Sheet] [Cash Flow]  │
│                   │  [Peers]                                         │
│  STOCKS (48)      │  ┌─────────────────────────────────────────────┐ │
│  ─────────────    │  │  Mar'23 Jun'23 Sep'23 … Mar'26             │ │
│  ADANIPORTS  ✓   │  │  Revenue  11,364  12,498 … 21,606          │ │
│  APOLLOHOSP       │  │  Net Profit 3,158  3,437 …  5,553          │ │
│  BAJAJ-AUTO       │  │  EPS         5.22   5.67 …   8.78          │ │
│  BAJFINANCE       │  └─────────────────────────────────────────────┘ │
│  GRASIM           │                                                   │
│  ...              │  [View on Screener.in ↗]                         │
└───────────────────┴─────────────────────────────────────────────────┘
```

---

## 🏗️ Architecture

```mermaid
flowchart TD
    U([👤 User\nBrowser]) --> ST

    subgraph APP ["📊 Streamlit App (Python)"]
        ST[app.py\nUI Layout + Session State]
        ST --> NL[nl_filter.py\nNatural Language → JSON criteria]
        ST --> NSE[nse_client.py\nStock Universe + OHLC]
        ST --> SC[screener_client.py\nFundamentals Scraper]
        ST --> CH[charts.py\nPlotly Candlestick]
        ST <--> DB[database.py\nSQLite Cache + History]
    end

    subgraph DATA ["📡 Data Sources"]
        YF[(yfinance\n163 NSE stocks\n52W high/low/price)]
        SR[(Screener.in\nRatios · Quarterly\nP&L · Balance Sheet)]
        CL[(Claude Haiku\nAnthropic API\nNL → filter criteria)]
    end

    subgraph CACHE ["💾 SQLite — stocks.db"]
        FC[filter_history\nquery · results · timestamp]
        SC2[screener_cache\n24h TTL per symbol]
        NC[nse_cache\n15min TTL full universe]
    end

    NSE -->|bulk download 1Y daily| YF
    SC -->|HTML scrape + BeautifulSoup| SR
    NL -->|claude-haiku-4-5| CL
    DB <--> FC
    DB <--> SC2
    DB <--> NC

    style APP fill:#1a1d27,stroke:#4e9af1,color:#fff
    style DATA fill:#1a2e1a,stroke:#4aff9e,color:#fff
    style CACHE fill:#2e2a1a,stroke:#ffa500,color:#fff
```

### Data Flow

1. **On startup** — `nse_client.py` runs `yfinance.download()` for all 163 symbols in one bulk call, computes `pct_from_52wk_high`, and caches results in SQLite for 15 minutes.
2. **Default view** — stocks where `pct_from_52wk_high ≤ 5%` sorted nearest-to-high first (typically 40–60 stocks depending on market conditions).
3. **Natural language filter** — query goes to Claude Haiku with a structured system prompt; Claude returns JSON filter criteria; criteria are applied to the in-memory DataFrame; query + result symbols persisted to `filter_history`.
4. **Stock click** — `screener_client.py` fetches `screener.in/company/{SYMBOL}/consolidated/`, parses all HTML sections (ratios, quarterly, P&L, balance sheet, cash flow, peers), caches the result for 24 hours.
5. **Chart** — `yfinance.Ticker.history()` with the selected period/interval, rendered as a dark-themed Plotly candlestick with a volume subplot and 52W high/low reference lines.

---

## 💼 Why This Exists

| Before | After |
|---|---|
| Open 4 tabs (Screener, NSE, TradingView, notes) | Single dashboard — everything in one screen |
| Manually scan 500 stocks for 52W high candidates | Auto-filtered to ~50 stocks within 5% of high |
| Write Python scripts to filter by ratios | Type in plain English — Claude does the parsing |
| Lose filter history between sessions | All queries + results persisted in SQLite |
| Stuck to your laptop | Deployed on Streamlit Cloud — access from anywhere |

### Key Metrics

- 📊 **Universe:** 163 NSE stocks (Nifty 50 + Next 50 + Midcap 100 selection)
- ⚡ **Data refresh:** Universe cached 15 min, fundamentals cached 24h — no redundant scraping
- 🧠 **Filter cost:** ~$0.001–0.002 per Claude Haiku query (< $3/month at 30 queries/day)
- 📈 **Chart modes:** Daily (1Y, 6M) and Weekly (2Y, 5Y) with volume and 52W markers
- 💾 **Storage:** SQLite — zero infrastructure, works locally and on Streamlit Cloud

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **UI** | Streamlit 1.35 | Dashboard layout, session state, dark theme |
| **Charts** | Plotly 5.18 | Candlestick + volume subplots |
| **Stock Data** | yfinance 1.3 | Bulk OHLCV download for NSE universe (`.NS` suffix) |
| **Fundamentals** | requests + BeautifulSoup4 + lxml | Screener.in HTML scraping |
| **AI Filter** | Claude Haiku 4.5 via Anthropic SDK | NL query → JSON filter criteria |
| **Persistence** | SQLite (stdlib) | Filter history, screener cache, NSE price cache |
| **Config** | python-dotenv | Local `.env` + Streamlit Cloud `st.secrets` |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com) (for AI filtering — optional; the 52W High view works without it)

### 1. Clone & Install

```bash
git clone https://github.com/DevMLAI01/stock-market-dashboard.git
cd stock-market-dashboard
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env — add your Anthropic API key
```

```env
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Run

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501). The dashboard loads with ~163 NSE stocks and auto-filters to those near their 52-week high. First load takes ~30–60s (yfinance bulk download); subsequent loads are instant from cache.

---

## ☁️ Deploy to Streamlit Cloud

### 1. Fork or push to GitHub

The repo is already public at [github.com/DevMLAI01/stock-market-dashboard](https://github.com/DevMLAI01/stock-market-dashboard).

### 2. Deploy

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. **New app** → Repository: `DevMLAI01/stock-market-dashboard` → Branch: `master` → Main file: `app.py`
4. Click **Deploy**

### 3. Add API key as a secret

In your deployed app → ⋮ → **Settings** → **Secrets**:

```toml
ANTHROPIC_API_KEY = "sk-ant-your-key-here"
```

Your dashboard is now accessible from any browser, any device.

---

## 📁 Project Structure

```
stock-market-dashboard/
├── app.py                      # Streamlit entry point — layout, session state, UI components
├── requirements.txt
├── .env.example                # ANTHROPIC_API_KEY placeholder
├── .streamlit/
│   └── config.toml             # Dark theme + server settings for Streamlit Cloud
├── src/
│   ├── __init__.py
│   ├── nse_client.py           # yfinance bulk download, NSE_UNIVERSE dict, get_historical_ohlc()
│   ├── screener_client.py      # Screener.in HTML scraper — ratios, quarterly, P&L, balance sheet
│   ├── database.py             # SQLite init + helpers: filter_history, screener_cache, nse_cache
│   ├── nl_filter.py            # Claude Haiku: NL query → filter_spec JSON → applied to DataFrame
│   └── charts.py               # Plotly candlestick + volume chart with 52W high/low markers
└── data/
    └── stocks.db               # Auto-created SQLite database (gitignored)
```

---

## 🔬 How the Natural Language Filter Works

The system prompt constrains Claude to **only use columns available in the NSE DataFrame**:

```
Columns: symbol, name, last_price, year_high, year_low,
         pct_change (today's % move), pct_from_high (% below 52W high)

Return JSON:
{
  "filters": [{"column": "...", "operator": "gt|lt|gte|lte|eq|contains", "value": ...}],
  "sort_by": "column_name",
  "sort_ascending": true,
  "summary": "one sentence description"
}
```

**Example queries that work:**

| Query | What Claude generates |
|---|---|
| `"stocks within 2% of 52-week high"` | `pct_from_high lte 2` |
| `"stocks up more than 1% today"` | `pct_change gt 1` |
| `"stocks AT their 52-week high"` | `pct_from_high lte 0.1` |
| `"show me the biggest losers today"` | `sort by pct_change ascending` |

> **Fundamental filters** (P/E, ROE, ROCE) require per-stock Screener.in data which isn't available in bulk — Claude notes this and filters on what's available.

Every query is saved to `filter_history` with its result symbols and timestamp, so you can re-run any past filter with one click.

---

## 🗺️ Roadmap

- [ ] **Watchlist** — pin stocks permanently to the top of the list
- [ ] **Price alerts** — notify when a stock crosses its 52W high
- [ ] **Bulk fundamentals** — background job to pre-fetch Screener.in data for all filtered stocks
- [ ] **Fundamental NL filters** — enable P/E, ROE, ROCE filtering by caching ratios in SQLite
- [ ] **Export** — download filtered list as CSV with key ratios
- [ ] **Compare mode** — overlay two stocks on the same chart
- [ ] **Add more indices** — Nifty Bank, Nifty IT, Nifty Pharma sector filters
- [ ] **Technical indicators** — EMA 20/50/200, RSI overlay on chart

---

## 📄 License

MIT © [DevMLAI01](https://github.com/DevMLAI01)

---

<div align="center">

Built with ❤️ using [Claude AI](https://anthropic.com) · [Streamlit](https://streamlit.io) · [yfinance](https://pypi.org/project/yfinance) · [Screener.in](https://screener.in)

</div>
