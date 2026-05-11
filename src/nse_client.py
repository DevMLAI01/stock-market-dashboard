import pandas as pd
import yfinance as yf
from src.database import get_cached_nse, set_cached_nse

# NSE symbols mapped to their yfinance .NS tickers
# Key = display symbol (used for Screener.in), Value = yfinance ticker (without .NS)
NSE_UNIVERSE: dict[str, str] = {
    # Nifty 50
    "RELIANCE": "RELIANCE", "TCS": "TCS", "HDFCBANK": "HDFCBANK",
    "BHARTIARTL": "BHARTIARTL", "ICICIBANK": "ICICIBANK", "SBIN": "SBIN",
    "INFY": "INFY", "HINDUNILVR": "HINDUNILVR", "ITC": "ITC", "LT": "LT",
    "KOTAKBANK": "KOTAKBANK", "AXISBANK": "AXISBANK", "BAJFINANCE": "BAJFINANCE",
    "MARUTI": "MARUTI", "SUNPHARMA": "SUNPHARMA", "TITAN": "TITAN",
    "ULTRACEMCO": "ULTRACEMCO", "ASIANPAINT": "ASIANPAINT", "WIPRO": "WIPRO",
    "HCLTECH": "HCLTECH", "POWERGRID": "POWERGRID", "NTPC": "NTPC",
    "ONGC": "ONGC", "COALINDIA": "COALINDIA", "BAJAJFINSV": "BAJAJFINSV",
    "ADANIENT": "ADANIENT", "ADANIPORTS": "ADANIPORTS", "TATACONSUM": "TATACONSUM",
    "NESTLEIND": "NESTLEIND", "DIVISLAB": "DIVISLAB", "DRREDDY": "DRREDDY",
    "CIPLA": "CIPLA", "APOLLOHOSP": "APOLLOHOSP", "JSWSTEEL": "JSWSTEEL",
    "TATASTEEL": "TATASTEEL", "HINDALCO": "HINDALCO", "BPCL": "BPCL",
    "BRITANNIA": "BRITANNIA", "INDUSINDBK": "INDUSINDBK", "M&M": "M&M",
    "TECHM": "TECHM", "EICHERMOT": "EICHERMOT", "GRASIM": "GRASIM",
    "SHRIRAMFIN": "SHRIRAMFIN", "HEROMOTOCO": "HEROMOTOCO", "TRENT": "TRENT",
    "BEL": "BEL", "SBILIFE": "SBILIFE", "HDFCLIFE": "HDFCLIFE",
    # Nifty Next 50
    "ADANIGREEN": "ADANIGREEN", "ADANIPOWER": "ADANIPOWER",
    "AMBUJACEM": "AMBUJACEM", "BAJAJ-AUTO": "BAJAJ-AUTO", "BANKBARODA": "BANKBARODA",
    "BERGEPAINT": "BERGEPAINT", "BOSCHLTD": "BOSCHLTD", "CANBK": "CANBK",
    "CHOLAFIN": "CHOLAFIN", "COLPAL": "COLPAL", "DABUR": "DABUR",
    "DLF": "DLF", "FEDERALBNK": "FEDERALBNK", "GAIL": "GAIL",
    "GODREJCP": "GODREJCP", "HAVELLS": "HAVELLS", "ICICIGI": "ICICIGI",
    "ICICIPRULI": "ICICIPRULI", "INDUSTOWER": "INDUSTOWER", "IRFC": "IRFC",
    "JINDALSTEL": "JINDALSTEL", "JSWENERGY": "JSWENERGY", "LODHA": "LODHA",
    "LUPIN": "LUPIN", "MARICO": "MARICO", "NHPC": "NHPC",
    "NMDC": "NMDC", "NYKAA": "NYKAA", "OFSS": "OFSS",
    "PAGEIND": "PAGEIND", "PNB": "PNB", "RECLTD": "RECLTD",
    "SBICARD": "SBICARD", "SIEMENS": "SIEMENS", "TATACOMM": "TATACOMM",
    "TATAPOWER": "TATAPOWER", "TORNTPHARM": "TORNTPHARM", "TVSMOTOR": "TVSMOTOR",
    "UBL": "UBL", "UNIONBANK": "UNIONBANK", "VEDL": "VEDL",
    "VOLTAS": "VOLTAS", "ZOMATO": "ETERNAL",   # Zomato rebranded to Eternal
    "ZYDUSLIFE": "ZYDUSLIFE", "POLICYBZR": "POLICYBZR",
    # Midcap selection
    "ABCAPITAL": "ABCAPITAL", "ALKEM": "ALKEM", "APLLTD": "APLLTD",
    "ASTRAL": "ASTRAL", "AUROPHARMA": "AUROPHARMA", "BALKRISIND": "BALKRISIND",
    "BATAINDIA": "BATAINDIA", "CAMS": "CAMS", "CANFINHOME": "CANFINHOME",
    "CEATLTD": "CEATLTD", "CROMPTON": "CROMPTON", "CUMMINSIND": "CUMMINSIND",
    "DEEPAKNTR": "DEEPAKNTR", "DIXON": "DIXON", "ELGIEQUIP": "ELGIEQUIP",
    "ESCORTS": "ESCORTS", "EXIDEIND": "EXIDEIND", "GLENMARK": "GLENMARK",
    "GMRAIRPORT": "GMRAIRPORT", "GODREJIND": "GODREJIND", "GRANULES": "GRANULES",
    "GUJGASLTD": "GUJGASLTD", "HINDPETRO": "HINDPETRO", "IDFCFIRSTB": "IDFCFIRSTB",
    "INDIAMART": "INDIAMART", "INDIGO": "INDIGO", "IRCTC": "IRCTC",
    "JKCEMENT": "JKCEMENT", "JUBLFOOD": "JUBLFOOD", "KAJARIACER": "KAJARIACER",
    "KPITTECH": "KPITTECH", "LALPATHLAB": "LALPATHLAB", "LAURUSLABS": "LAURUSLABS",
    "LICHSGFIN": "LICHSGFIN", "MPHASIS": "MPHASIS", "MRF": "MRF",
    "MUTHOOTFIN": "MUTHOOTFIN", "NATIONALUM": "NATIONALUM", "NAVINFLUOR": "NAVINFLUOR",
    "OBEROIRLTY": "OBEROIRLTY", "AARTIIND": "AARTIIND", "PETRONET": "PETRONET",
    "PFC": "PFC", "PHOENIXLTD": "PHOENIXLTD", "PRESTIGE": "PRESTIGE",
    "RAMCOCEM": "RAMCOCEM", "RATNAMANI": "RATNAMANI", "RITES": "RITES",
    "SAIL": "SAIL", "SCHAEFFLER": "SCHAEFFLER", "SONACOMS": "SONACOMS",
    "SUPREMEIND": "SUPREMEIND", "SYNGENE": "SYNGENE", "TANLA": "TANLA",
    "TATAELXSI": "TATAELXSI", "THERMAX": "THERMAX", "TORNTPOWER": "TORNTPOWER",
    "TRIDENT": "TRIDENT", "UTIAMC": "UTIAMC", "VBL": "VBL",
    "WELCORP": "WELCORP", "UNITDSPR": "UNITDSPR", "360ONE": "360ONE",
    "PERSISTENT": "PERSISTENT", "KANSAINER": "KANSAINER", "PIIND": "PIIND",
    "STARHEALTH": "STARHEALTH", "ABFRL": "ABFRL", "BLUEDART": "BLUEDART",
}


def get_nifty_universe() -> pd.DataFrame:
    """Fetch prices and 52-week high/low for the full NSE universe via yfinance bulk download."""
    cached = get_cached_nse()
    if cached:
        return pd.DataFrame(cached)

    yf_symbols = [f"{v}.NS" for v in NSE_UNIVERSE.values()]
    display_map = {f"{v}.NS": k for k, v in NSE_UNIVERSE.items()}

    print(f"[yfinance] Downloading {len(yf_symbols)} symbols...")
    try:
        raw = yf.download(
            yf_symbols,
            period="1y",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as e:
        print(f"[yfinance] Bulk download failed: {e}")
        return pd.DataFrame()

    rows = []
    for yf_sym in yf_symbols:
        display_sym = display_map.get(yf_sym, yf_sym.replace(".NS", ""))
        try:
            if len(yf_symbols) == 1:
                df_sym = raw
            else:
                if yf_sym not in raw.columns.get_level_values(0):
                    continue
                df_sym = raw[yf_sym]

            if df_sym is None or (hasattr(df_sym, "empty") and df_sym.empty):
                continue

            close = df_sym["Close"].dropna()
            if close.empty or len(close) < 2:
                continue

            last_price = float(close.iloc[-1])
            year_high = float(close.max())
            year_low = float(close.min())
            pct_change = round((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100, 2)
            pct_from_high = round((year_high - last_price) / year_high * 100, 2) if year_high > 0 else 999

            rows.append({
                "symbol": display_sym,
                "name": display_sym,
                "last_price": round(last_price, 2),
                "year_high": round(year_high, 2),
                "year_low": round(year_low, 2),
                "pct_change": pct_change,
                "pct_from_high": pct_from_high,
            })
        except Exception as e:
            print(f"[yfinance] Skipping {yf_sym}: {e}")
            continue

    if rows:
        set_cached_nse(rows)

    return pd.DataFrame(rows)


def get_stocks_near_52wk_high(threshold_pct: float = 5.0) -> pd.DataFrame:
    df = get_nifty_universe()
    if df.empty:
        return df
    return df[df["pct_from_high"] <= threshold_pct].sort_values("pct_from_high")


def get_historical_ohlc(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Fetch OHLCV data via yfinance. Uses display symbol → mapped yfinance ticker."""
    yf_sym = NSE_UNIVERSE.get(symbol, symbol)
    ticker = yf.Ticker(f"{yf_sym}.NS")
    df = ticker.history(period=period, interval=interval, auto_adjust=True)
    if df.empty:
        return pd.DataFrame()
    df = df.dropna(subset=["Close"])
    df = df.reset_index()
    df.columns = [c.lower() for c in df.columns]
    # Normalise date column name
    for col in ["datetime", "date"]:
        if col in df.columns:
            df = df.rename(columns={col: "date"})
            break
    keep = [c for c in ["date", "open", "high", "low", "close", "volume"] if c in df.columns]
    return df[keep]
