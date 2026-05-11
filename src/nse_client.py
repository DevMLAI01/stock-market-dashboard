import pandas as pd
import yfinance as yf
from src.database import get_cached_nse, set_cached_nse

# NSE display symbol → yfinance ticker (without .NS suffix)
# Covers Nifty 50 + Next 50 + Midcap 150 + Smallcap 250 (~500 stocks)
# Symbols where NSE name ≠ yfinance name are explicitly mapped; all others are identity.
NSE_UNIVERSE: dict[str, str] = {
    # ── Nifty 50 ──────────────────────────────────────────────────────────────
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
    # ── Nifty Next 50 ─────────────────────────────────────────────────────────
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
    "VOLTAS": "VOLTAS", "ZOMATO": "ETERNAL",   # Zomato rebranded to Eternal in 2026
    "ZYDUSLIFE": "ZYDUSLIFE", "POLICYBZR": "POLICYBZR",
    # ── Nifty Midcap 150 ──────────────────────────────────────────────────────
    "ABCAPITAL": "ABCAPITAL", "ABB": "ABB", "AAVAS": "AAVAS",
    "ALKEM": "ALKEM", "APLLTD": "APLLTD", "APLAPOLLO": "APLAPOLLO",
    "APOLLOTYRE": "APOLLOTYRE", "ASHOKLEYLAND": "ASHOKLEYLAND",
    "ASTRAL": "ASTRAL", "ATGL": "ATGL", "AUBANK": "AUBANK",
    "AUROPHARMA": "AUROPHARMA", "BALKRISIND": "BALKRISIND",
    "BANKINDIA": "BANKINDIA", "BATAINDIA": "BATAINDIA",
    "BIRLASOFT": "BIRLASOFT", "BSOFT": "BSOFT", "CAMS": "CAMS",
    "CANFINHOME": "CANFINHOME", "CEATLTD": "CEATLTD", "CDSL": "CDSL",
    "CGPOWER": "CGPOWER", "CLEAN": "CLEAN", "COFORGE": "COFORGE",
    "CONCOR": "CONCOR", "CROMPTON": "CROMPTON", "CUB": "CUB",
    "CUMMINSIND": "CUMMINSIND", "DALBHARAT": "DALBHARAT", "DBREALTY": "DBREALTY",
    "DEEPAKFERT": "DEEPAKFERT", "DEEPAKNTR": "DEEPAKNTR", "DIXON": "DIXON",
    "ELGIEQUIP": "ELGIEQUIP", "EMAMILTD": "EMAMILTD", "ESCORTS": "ESCORTS",
    "EXIDEIND": "EXIDEIND", "FINEORG": "FINEORG", "FIVESTAR": "FIVESTAR",
    "GLAND": "GLAND", "GLAXO": "GLAXO", "GLENMARK": "GLENMARK",
    "GMRAIRPORT": "GMRAIRPORT", "GODREJIND": "GODREJIND", "GRANULES": "GRANULES",
    "GUJGASLTD": "GUJGASLTD", "HAPPSTMNDS": "HAPPSTMNDS", "HDFCAMC": "HDFCAMC",
    "HINDCOPPER": "HINDCOPPER", "HINDPETRO": "HINDPETRO", "HONAUT": "HONAUT",
    "IDBI": "IDBI", "IDFCFIRSTB": "IDFCFIRSTB", "IEX": "IEX",
    "INDHOTEL": "INDHOTEL", "INDIAMART": "INDIAMART", "INDIGO": "INDIGO",
    "INTELLECT": "INTELLECT", "IOB": "IOB", "IPCALAB": "IPCALAB",
    "IRCTC": "IRCTC", "IREDA": "IREDA", "JBCHEPHARM": "JBCHEPHARM",
    "JKCEMENT": "JKCEMENT", "JSWINFRA": "JSWINFRA", "JUBLFOOD": "JUBLFOOD",
    "KAJARIACER": "KAJARIACER", "KALYANKJIL": "KALYANKJIL", "KANSAINER": "KANSAINER",
    "KAYNES": "KAYNES", "KEC": "KEC", "KFINTECH": "KFINTECH",
    "KNRCON": "KNRCON", "KPIL": "KPIL", "KPITTECH": "KPITTECH",
    "LALPATHLAB": "LALPATHLAB", "LATENTVIEW": "LATENTVIEW", "LAURUSLABS": "LAURUSLABS",
    "LICI": "LICI", "LICHSGFIN": "LICHSGFIN", "LTTS": "LTTS",
    "LUXIND": "LUXIND", "MANAPPURAM": "MANAPPURAM", "MAPMYINDIA": "MAPMYINDIA",
    "MCX": "MCX", "MEDANTA": "MEDANTA", "METROPOLIS": "METROPOLIS",
    "MFSL": "MFSL", "MOTHERSON": "MOTHERSON", "MOTILALOFS": "MOTILALOFS",
    "MPHASIS": "MPHASIS", "MRF": "MRF", "MTAR": "MTAR",
    "MUTHOOTFIN": "MUTHOOTFIN", "NATIONALUM": "NATIONALUM", "NATCOPHARM": "NATCOPHARM",
    "NAVINFLUOR": "NAVINFLUOR", "NBCC": "NBCC", "NCC": "NCC",
    "NIACL": "NIACL", "NILKAMAL": "NILKAMAL", "NLCINDIA": "NLCINDIA",
    "NOCIL": "NOCIL", "NUVAMA": "NUVAMA", "NUVOCO": "NUVOCO",
    "OBEROIRLTY": "OBEROIRLTY", "AARTIIND": "AARTIIND", "OIL": "OIL",
    "OLECTRA": "OLECTRA", "PETRONET": "PETRONET", "PFC": "PFC",
    "PGHH": "PGHH", "PHOENIXLTD": "PHOENIXLTD", "PIIND": "PIIND",
    "PNCINFRA": "PNCINFRA", "POLYMED": "POLYMED", "POONAWALLA": "POONAWALLA",
    "PRESTIGE": "PRESTIGE", "PRINCEPIPE": "PRINCEPIPE", "PVRINOX": "PVRINOX",
    "RAMCOCEM": "RAMCOCEM", "RATNAMANI": "RATNAMANI", "RAYMOND": "RAYMOND",
    "RITES": "RITES", "ROUTE": "ROUTE", "RVNL": "RVNL",
    "SAIL": "SAIL", "SCHAEFFLER": "SCHAEFFLER", "SCI": "SCI",
    "SJVN": "SJVN", "SOBHA": "SOBHA", "SOLARINDS": "SOLARINDS",
    "SONACOMS": "SONACOMS", "SRF": "SRF", "STARHEALTH": "STARHEALTH",
    "STLTECH": "STLTECH", "SUNDARMFIN": "SUNDARMFIN", "SUNTECK": "SUNTECK",
    "SUNTV": "SUNTV", "SUPREMEIND": "SUPREMEIND", "SYNGENE": "SYNGENE",
    "TANLA": "TANLA", "TATACHEM": "TATACHEM", "TATAINVEST": "TATAINVEST",
    "TATAELXSI": "TATAELXSI", "THERMAX": "THERMAX", "TITAGARH": "TITAGARH",
    "TIMKEN": "TIMKEN", "TORNTPOWER": "TORNTPOWER", "TRIDENT": "TRIDENT",
    "TRITURBINE": "TRITURBINE", "UCOBANK": "UCOBANK", "UJJIVANSFB": "UJJIVANSFB",
    "UNITDSPR": "UNITDSPR", "UTIAMC": "UTIAMC", "UTKARSHBNK": "UTKARSHBNK",
    "VAIBHAVGBL": "VAIBHAVGBL", "VBL": "VBL", "VGUARD": "VGUARD",
    "VINATIORGA": "VINATIORGA", "WELCORP": "WELCORP", "WELSPUNLIV": "WELSPUNLIV",
    "360ONE": "360ONE", "PERSISTENT": "PERSISTENT", "ABFRL": "ABFRL",
    "BLUEDART": "BLUEDART", "ZEEL": "ZEEL",
    # ── Nifty Smallcap 250 ────────────────────────────────────────────────────
    "AARTIDRUGS": "AARTIDRUGS", "ACE": "ACE", "AFFLE": "AFFLE",
    "AJANTPHARM": "AJANTPHARM", "AKZOINDIA": "AKZOINDIA", "ALEMBICLTD": "ALEMBICLTD",
    "ALKYLAMINE": "ALKYLAMINE", "AMBER": "AMBER", "ANANTRAJ": "ANANTRAJ",
    "ANANDRATHI": "ANANDRATHI", "ANGELONE": "ANGELONE", "APARINDS": "APARINDS",
    "APTUS": "APTUS", "ARVINDFASN": "ARVINDFASN", "ASAHIINDIA": "ASAHIINDIA",
    "ASHOKA": "ASHOKA", "ASTERDM": "ASTERDM", "ATFL": "ATFL",
    "AVANTIFEED": "AVANTIFEED", "BAJAJELEC": "BAJAJELEC", "BALAMINES": "BALAMINES",
    "BAYERCROP": "BAYERCROP", "BEML": "BEML", "BIKAJI": "BIKAJI",
    "BRIGADE": "BRIGADE", "CAMPUS": "CAMPUS", "CAPACITE": "CAPACITE",
    "CAPLIPOINT": "CAPLIPOINT", "CASTROLIND": "CASTROLIND", "CCL": "CCL",
    "CENTURYPLY": "CENTURYPLY", "CENTURYTEX": "CENTURYTEX", "CERA": "CERA",
    "CHAMBLFERT": "CHAMBLFERT", "CHENNPETRO": "CHENNPETRO", "CMSINFO": "CMSINFO",
    "COCHINSHIP": "COCHINSHIP", "COROMANDEL": "COROMANDEL", "CRAFTSMAN": "CRAFTSMAN",
    "CRISIL": "CRISIL", "CSBBANK": "CSBBANK", "DCB": "DCB",
    "DCMSHRIRAM": "DCMSHRIRAM", "DELHIVERY": "DELHIVERY", "DELTACORP": "DELTACORP",
    "DEVYANI": "DEVYANI", "DHANUKA": "DHANUKA", "DMART": "DMART",
    "EASEMYTRIP": "EASEMYTRIP", "ELECON": "ELECON", "EMCURE": "EMCURE",
    "EPIGRAL": "EPIGRAL", "EQUITASBNK": "EQUITASBNK", "ESTER": "ESTER",
    "FACT": "FACT", "FLAIR": "FLAIR", "FLUOROCHEM": "FLUOROCHEM",
    "GAEL": "GAEL", "GALAXYSURF": "GALAXYSURF", "GARFIBRES": "GARFIBRES",
    "GHCL": "GHCL", "GPIL": "GPIL", "GPPL": "GPPL",
    "GREENPLY": "GREENPLY", "GRINDWELL": "GRINDWELL", "GSFC": "GSFC",
    "GSPL": "GSPL", "GUFICBIO": "GUFICBIO", "GUJALKALI": "GUJALKALI",
    "HBLPOWER": "HBLPOWER", "HFCL": "HFCL", "HINDWAREAP": "HINDWAREAP",
    "HONASA": "HONASA", "IBULHSGFIN": "IBULHSGFIN", "ICRA": "ICRA",
    "IGL": "IGL", "IIFL": "IIFL", "IIFLSEC": "IIFLSEC",
    "IMFA": "IMFA", "INDIANB": "INDIANB", "INDIGOPNTS": "INDIGOPNTS",
    "INFIBEAM": "INFIBEAM", "INOXGREEN": "INOXGREEN", "INOXWIND": "INOXWIND",
    "IONEXCHANG": "IONEXCHANG", "IOLCP": "IOLCP", "ITDCEM": "ITDCEM",
    "JAIBALAJI": "JAIBALAJI", "JINDALSAW": "JINDALSAW", "JKIL": "JKIL",
    "JKPAPER": "JKPAPER", "JMFINANCIL": "JMFINANCIL", "JUBLPHARMA": "JUBLPHARMA",
    "JUSTDIAL": "JUSTDIAL", "JYOTHYLAB": "JYOTHYLAB", "KALPATPOWR": "KALPATPOWR",
    "KRBL": "KRBL", "KSCL": "KSCL", "KTKBANK": "KTKBANK",
    "LAOPALA": "LAOPALA", "LAXMIMACH": "LAXMIMACH", "LTFOODS": "LTFOODS",
    "MAHINDCIE": "MAHINDCIE", "MAHLIFE": "MAHLIFE", "MANINFRA": "MANINFRA",
    "MARKSANS": "MARKSANS", "MASTEK": "MASTEK", "MAZDOCK": "MAZDOCK",
    "MEDPLUS": "MEDPLUS", "MINDA": "MINDA", "MMTC": "MMTC",
    "MOIL": "MOIL", "MRPL": "MRPL", "MSTCLTD": "MSTCLTD",
    "NAVA": "NAVA", "NAZARA": "NAZARA", "NSLNISP": "NSLNISP",
    "NUCLEUS": "NUCLEUS", "OLAELECTRIC": "OLAELECTRIC", "ORCHPHARMA": "ORCHPHARMA",
    "ORIENTCEM": "ORIENTCEM", "ORIENTELEC": "ORIENTELEC", "PATELENG": "PATELENG",
    "PATANJALI": "PATANJALI", "PEL": "PEL", "PFIZER": "PFIZER",
    "PIDLITIND": "PIDLITIND", "POLYPLEX": "POLYPLEX", "PRAJIND": "PRAJIND",
    "RBLBANK": "RBLBANK", "REDINGTON": "REDINGTON", "RELAXO": "RELAXO",
    "RKFORGE": "RKFORGE", "RTNINDIA": "RTNINDIA", "SAFARI": "SAFARI",
    "SAREGAMA": "SAREGAMA", "SAPPHIRE": "SAPPHIRE", "SHYAMMETL": "SHYAMMETL",
    "SKIPPER": "SKIPPER", "SPANDANA": "SPANDANA", "SUDARSCHEM": "SUDARSCHEM",
    "SULA": "SULA", "SUMICHEM": "SUMICHEM", "SUNDRMBRAK": "SUNDRMBRAK",
    "SUVEN": "SUVEN", "SWSOLAR": "SWSOLAR", "TATAMETALI": "TATAMETALI",
    "TCIEXP": "TCIEXP", "THYROCARE": "THYROCARE", "TIINDIA": "TIINDIA",
    "TINPLATE": "TINPLATE", "TRIL": "TRIL", "TRIVENI": "TRIVENI",
    "TTK": "TTKPRESTIG", "TVSHLTD": "TVSHLTD", "TVSSRICHAK": "TVSSRICHAK",
    "UNOMINDA": "UNOMINDA", "V2RETAIL": "V2RETAIL", "VARDHACRLC": "VARDHACRLC",
    "VIPIND": "VIPIND", "VMART": "VMART", "VSTIND": "VSTIND",
    "WHIRLPOOL": "WHIRLPOOL", "WOCKHARDT": "WOCKHARDT", "ZENSARTECH": "ZENSARTECH",
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
    for col in ["datetime", "date"]:
        if col in df.columns:
            df = df.rename(columns={col: "date"})
            break
    keep = [c for c in ["date", "open", "high", "low", "close", "volume"] if c in df.columns]
    return df[keep]
