import re
import requests
from bs4 import BeautifulSoup
from src.database import get_cached_screener, set_cached_screener

SCREENER_BASE = "https://www.screener.in"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _clean_num(text: str) -> str:
    return text.strip().replace(",", "").replace("\xa0", "").replace("₹", "").strip()


def _parse_ratios(soup: BeautifulSoup) -> dict:
    ratios = {}
    top_ratios = soup.find("ul", id="top-ratios")
    if not top_ratios:
        return ratios
    for li in top_ratios.find_all("li"):
        name_el = li.find("span", class_="name")
        value_el = li.find("span", class_="number")
        if name_el and value_el:
            key = name_el.get_text(strip=True)
            val = _clean_num(value_el.get_text(strip=True))
            ratios[key] = val
    return ratios


def _parse_table(section_id: str, soup: BeautifulSoup) -> dict:
    """Parse a Screener.in financial table into {row_name: {col_header: value}}."""
    section = soup.find("section", id=section_id)
    if not section:
        return {}

    table = section.find("table")
    if not table:
        return {}

    headers = []
    thead = table.find("thead")
    if thead:
        for th in thead.find_all("th"):
            headers.append(th.get_text(strip=True))

    rows = {}
    tbody = table.find("tbody")
    if tbody:
        for tr in tbody.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            row_name = cells[0].get_text(strip=True)
            row_data = {}
            for i, td in enumerate(cells[1:], start=1):
                col = headers[i] if i < len(headers) else str(i)
                val = _clean_num(td.get_text(strip=True))
                row_data[col] = val
            if row_name:
                rows[row_name] = row_data
    return {"headers": headers[1:] if headers else [], "rows": rows}


def _parse_shareholding(soup: BeautifulSoup) -> dict:
    section = soup.find("section", id="shareholding")
    if not section:
        return {}
    result = {}
    table = section.find("table")
    if not table:
        return {}
    headers = []
    thead = table.find("thead")
    if thead:
        for th in thead.find_all("th"):
            headers.append(th.get_text(strip=True))
    tbody = table.find("tbody")
    if tbody:
        rows = {}
        for tr in tbody.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            row_name = cells[0].get_text(strip=True)
            row_data = {}
            for i, td in enumerate(cells[1:], start=1):
                col = headers[i] if i < len(headers) else str(i)
                row_data[col] = _clean_num(td.get_text(strip=True))
            if row_name:
                rows[row_name] = row_data
        result = {"headers": headers[1:] if headers else [], "rows": rows}
    return result


def _parse_peers(soup: BeautifulSoup) -> list[dict]:
    section = soup.find("section", id="peers")
    if not section:
        return []
    table = section.find("table")
    if not table:
        return []
    headers = []
    thead = table.find("thead")
    if thead:
        for th in thead.find_all("th"):
            headers.append(th.get_text(strip=True))
    peers = []
    tbody = table.find("tbody")
    if tbody:
        for tr in tbody.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            row = {}
            for i, td in enumerate(cells):
                col = headers[i] if i < len(headers) else str(i)
                row[col] = _clean_num(td.get_text(strip=True))
            if row:
                peers.append(row)
    return peers


def get_stock_data(symbol: str) -> dict:
    cached = get_cached_screener(symbol)
    if cached:
        return cached

    url = f"{SCREENER_BASE}/company/{symbol}/consolidated/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 404:
            # Try standalone
            url = f"{SCREENER_BASE}/company/{symbol}/"
            resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[Screener] Failed to fetch {symbol}: {e}")
        return {}

    soup = BeautifulSoup(resp.text, "lxml")

    # Company name and price
    name_el = soup.find("h1", class_="company-name") or soup.find("h1")
    name = name_el.get_text(strip=True) if name_el else symbol

    # BSE/NSE links
    bse_el = soup.find("a", string=re.compile(r"BSE"))
    nse_el = soup.find("a", string=re.compile(r"NSE"))

    data = {
        "symbol": symbol,
        "name": name,
        "ratios": _parse_ratios(soup),
        "quarterly": _parse_table("quarters", soup),
        "annual_pl": _parse_table("profit-loss", soup),
        "balance_sheet": _parse_table("balance-sheet", soup),
        "cash_flow": _parse_table("cash-flow", soup),
        "shareholding": _parse_shareholding(soup),
        "peers": _parse_peers(soup),
    }

    set_cached_screener(symbol, data)
    return data
