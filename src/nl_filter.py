import json
import os
import re
import anthropic
import pandas as pd
from src.database import save_filter

SYSTEM_PROMPT = """You are a stock screening assistant. Convert a natural language stock filter query into structured JSON criteria.

The DataFrame columns available are:
- symbol (string): NSE ticker symbol
- name (string): Company name
- last_price (float): Current stock price in INR
- year_high (float): 52-week high price
- year_low (float): 52-week low price
- pct_change (float): Today's % price change
- pct_from_high (float): % below 52-week high (0 = AT high, 5 = 5% below high)
- market_cap_cr (float): Market capitalisation in Indian Crores (₹). Examples: Reliance ~1,800,000 Cr, small-cap ~5,000 Cr. Use this for any query about market cap, company size, large-cap/mid-cap/small-cap. Large-cap > 20,000 Cr, Mid-cap 5,000–20,000 Cr, Small-cap < 5,000 Cr.

For fundamental metrics NOT yet in the main list (require per-stock Screener.in lookup):
- pe_ratio, roe, roce, book_value, debt_equity, sales_growth

Indian number system reminders — always convert before filtering:
- "1 lakh" = 100, "1 crore" = 1 (market_cap_cr is already in crores)
- "10,000 crores" → value: 10000
- "1 lakh crore" → value: 100000
- "large cap" → market_cap_cr > 20000
- "mid cap" → market_cap_cr between 5000 and 20000
- "small cap" → market_cap_cr < 5000

Return a JSON object with this exact structure:
{
  "filters": [
    {
      "column": "column_name",
      "operator": "gt|lt|gte|lte|eq|contains",
      "value": <number or string>,
      "description": "human readable description of this filter"
    }
  ],
  "sort_by": "column_name",
  "sort_ascending": true,
  "summary": "one sentence describing what this filter does"
}

Only use columns listed above. Return ONLY valid JSON, no markdown, no explanation."""


def parse_nl_filter(query: str) -> dict:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": query}],
    )
    text = message.content[0].text.strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # Extract the outermost JSON object — Claude sometimes appends explanation text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


def apply_filters(df: pd.DataFrame, filter_spec: dict) -> pd.DataFrame:
    result = df.copy()

    for f in filter_spec.get("filters", []):
        col = f.get("column")
        op = f.get("operator")
        val = f.get("value")

        if col not in result.columns:
            continue

        try:
            if op == "gt":
                result = result[result[col] > float(val)]
            elif op == "lt":
                result = result[result[col] < float(val)]
            elif op == "gte":
                result = result[result[col] >= float(val)]
            elif op == "lte":
                result = result[result[col] <= float(val)]
            elif op == "eq":
                result = result[result[col] == val]
            elif op == "contains":
                result = result[result[col].astype(str).str.contains(str(val), case=False, na=False)]
        except (ValueError, TypeError):
            continue

    sort_col = filter_spec.get("sort_by")
    if sort_col and sort_col in result.columns:
        result = result.sort_values(sort_col, ascending=filter_spec.get("sort_ascending", True))

    return result


def run_nl_filter(query: str, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    filter_spec = parse_nl_filter(query)
    filtered_df = apply_filters(df, filter_spec)
    symbols = filtered_df["symbol"].tolist() if not filtered_df.empty else []
    save_filter(query, filter_spec, symbols)
    return filtered_df, filter_spec
