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

For fundamental metrics from Screener.in (available only after clicking a stock, NOT in the main list):
- market_cap, pe_ratio, roe, roce, book_value, debt_equity, sales_growth

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

Only use columns available in the DataFrame listed above. If the query mentions fundamentals not in the list (like P/E ratio), include them in a "note" field explaining they require per-stock lookup.

Return ONLY valid JSON, no markdown, no explanation."""


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
