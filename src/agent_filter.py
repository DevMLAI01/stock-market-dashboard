"""
Multi-agent NL filter pipeline.

Pipeline:
  Agent 1 (Query Analyst)  — Claude Haiku + tool use: inspects available columns, identifies intent
  Agent 2 (Data Enricher)  — pure Python: re-syncs shareholding/extended metrics from screener_cache
  Agent 3 (Filter Builder) — Claude Haiku: generates JSON filter spec from confirmed columns
  Agent 4 (Validator)      — Claude Haiku: sanity-checks results and adds coverage caveats
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import anthropic
import pandas as pd


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class AgentStep:
    agent_name: str
    status: str          # "done" | "warning" | "error"
    reasoning: str
    details: dict = field(default_factory=dict)


@dataclass
class PipelineResult:
    filtered_df: pd.DataFrame
    filter_spec: dict
    steps: list[AgentStep]
    summary: str
    caveat: str
    valid: bool


# ── Column metadata ───────────────────────────────────────────────────────────

COLUMN_META: dict[str, tuple[str, str]] = {
    "symbol":             ("string", "NSE ticker symbol"),
    "name":               ("string", "Company name"),
    "last_price":         ("float",  "Current price in INR"),
    "year_high":          ("float",  "52-week high price INR"),
    "year_low":           ("float",  "52-week low price INR"),
    "pct_change":         ("float",  "Today's % price change"),
    "pct_from_high":      ("float",  "% below 52-week high (0=AT high)"),
    "market_cap_cr":      ("float",  "Market cap in Crores (large-cap>20000, mid 5000-20000, small<5000)"),
    # fundamentals
    "pe_ratio":           ("float",  "P/E ratio"),
    "roce":               ("float",  "Return on Capital Employed %"),
    "roe":                ("float",  "Return on Equity %"),
    "book_value":         ("float",  "Book value per share INR"),
    "debt_equity":        ("float",  "Debt to Equity ratio"),
    "dividend_yield":     ("float",  "Dividend yield %"),
    "sales_growth_5yr":   ("float",  "5-year sales CAGR %"),
    "profit_growth_yoy":  ("float",  "Latest quarter YoY net profit growth %"),
    "revenue_growth_yoy": ("float",  "Latest quarter YoY revenue growth %"),
    # extended fundamentals
    "pledged_pct":        ("float",  "Promoter pledged shares %"),
    "price_to_book":      ("float",  "Price to Book ratio"),
    "eps_growth_3yr":     ("float",  "EPS 3-year CAGR %"),
    "free_cash_flow":     ("float",  "Free cash flow in Crores"),
    "opm_pct":            ("float",  "Operating Profit Margin % (annual)"),
    "opm_quarterly_pct":  ("float",  "Operating Profit Margin % (latest quarter)"),
    "net_profit_margin":  ("float",  "Net Profit Margin % (annual)"),
    "sales_growth_3yr":   ("float",  "3-year sales CAGR %"),
    # shareholding
    "promoter_pct":       ("float",  "Promoter holding % (latest quarter)"),
    "fii_pct":            ("float",  "FII (Foreign Institutional Investor) holding % (latest quarter)"),
    "dii_pct":            ("float",  "DII (Domestic Institutional Investor) holding % (latest quarter)"),
    "public_pct":         ("float",  "Public holding % (latest quarter)"),
}

COLUMN_GROUPS = {
    "price":        ["symbol", "name", "last_price", "year_high", "year_low",
                     "pct_change", "pct_from_high", "market_cap_cr"],
    "fundamental":  ["pe_ratio", "roce", "roe", "book_value", "debt_equity",
                     "dividend_yield", "sales_growth_5yr", "profit_growth_yoy",
                     "revenue_growth_yoy"],
    "extended":     ["pledged_pct", "price_to_book", "eps_growth_3yr", "free_cash_flow",
                     "opm_pct", "opm_quarterly_pct", "net_profit_margin", "sales_growth_3yr"],
    "shareholding": ["promoter_pct", "fii_pct", "dii_pct", "public_pct"],
}


# ── Shared helpers ────────────────────────────────────────────────────────────

def _parse_json_safe(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _get_column_info(df: pd.DataFrame, group: str = "all") -> str:
    total = len(df)
    if group == "all":
        cols = [c for c in df.columns if c in COLUMN_META]
        missing: list[str] = []
    else:
        group_cols = COLUMN_GROUPS.get(group, [])
        cols = [c for c in group_cols if c in df.columns]
        missing = [c for c in group_cols if c not in df.columns]

    info: dict = {"total_stocks": total, "columns": {}, "missing_from_df": missing}
    for col in cols:
        series = df[col]
        non_null = int(series.notna().sum())
        dtype_str, desc = COLUMN_META.get(col, ("", ""))
        entry: dict = {
            "description": desc,
            "coverage": non_null,
            "coverage_pct": round(non_null / total * 100, 1) if total else 0,
            "dtype": dtype_str,
        }
        if pd.api.types.is_numeric_dtype(series) and non_null > 0:
            entry["min"] = round(float(series.min()), 2)
            entry["max"] = round(float(series.max()), 2)
        info["columns"][col] = entry

    return json.dumps(info, indent=2)


# ── Agent 1: Query Analyst ────────────────────────────────────────────────────

_ANALYST_SYSTEM = """You are a financial data analyst for an Indian stock screening system.
Analyze the user's query and determine what columns from the DataFrame are required to answer it.

Use the get_column_info tool to check what columns are available and their coverage.
Call it once with column_group="all" to get a full overview, or with a specific group to zoom in.

After using the tool, respond ONLY with valid JSON (no markdown) matching this schema:
{
  "can_filter": true,
  "required_columns": ["col1", "col2"],
  "needs_enrichment": false,
  "enrichment_columns": [],
  "column_domain": "price|fundamental|shareholding|extended|mixed",
  "reasoning": "one paragraph explaining what data is needed and why",
  "filter_hints": "plain English: filter where fii_pct > 20 and market_cap_cr > 5000",
  "cannot_answer_reason": ""
}

Set needs_enrichment=true if any required column is in the shareholding or extended group
(promoter_pct, fii_pct, dii_pct, public_pct, opm_pct, net_profit_margin, etc.),
because these require re-syncing from the local screener cache.

If a query genuinely cannot be answered with available data (e.g., broker recommendations,
news sentiment), set can_filter=false and explain in cannot_answer_reason."""


def agent1_query_analyst(query: str, df: pd.DataFrame) -> dict:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    tools = [
        {
            "name": "get_column_info",
            "description": (
                "Returns information about available columns in the stock DataFrame, "
                "including coverage (non-null count out of 426 stocks), min, max, and description. "
                "Use this to confirm which columns exist before deciding if the query can be answered."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "column_group": {
                        "type": "string",
                        "enum": ["all", "price", "fundamental", "shareholding", "extended"],
                        "description": "Which group of columns to inspect",
                    }
                },
                "required": ["column_group"],
            },
        }
    ]

    messages: list[dict] = [{"role": "user", "content": query}]

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=_ANALYST_SYSTEM,
            tools=tools,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _get_column_info(df, block.input.get("column_group", "all"))
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": result}
                    )
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            continue

        text = next((b.text for b in response.content if hasattr(b, "text")), "{}")
        result = _parse_json_safe(text)
        # If Claude returned prose instead of JSON, treat as unanswerable
        if "can_filter" not in result:
            result = {
                "can_filter": False,
                "required_columns": [],
                "needs_enrichment": False,
                "enrichment_columns": [],
                "column_domain": "unknown",
                "reasoning": text[:300] if text else "Could not parse query intent.",
                "filter_hints": "",
                "cannot_answer_reason": "This query does not appear to be a stock filter request.",
            }
        return result


# ── Agent 2: Data Enricher (pure Python) ─────────────────────────────────────

def _sync_extended_from_screener_cache() -> int:
    """Re-extract all cached Screener.in data with the extended extract_metrics()."""
    from src.database import get_all_screener_cache_symbols, upsert_fundamentals
    from src.fundamentals_cache import extract_metrics

    entries = get_all_screener_cache_symbols()
    count = 0
    for symbol, data_json in entries:
        try:
            data = json.loads(data_json)
            metrics = extract_metrics(data)
            upsert_fundamentals(symbol, metrics)
            count += 1
        except Exception as e:
            print(f"[Agent2] sync error for {symbol}: {e}")
    return count


def agent2_data_enricher(
    required_columns: list[str],
    needs_enrichment: bool,
    current_df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    from src.database import get_all_fundamentals

    if needs_enrichment:
        _sync_extended_from_screener_cache()

    # Reload fundamentals and re-merge with universe price columns
    fundamentals = get_all_fundamentals()
    price_cols = ["symbol", "name", "last_price", "year_high", "year_low",
                  "pct_change", "pct_from_high", "market_cap_cr"]
    universe_cols = [c for c in price_cols if c in current_df.columns]
    universe_only = current_df[universe_cols].copy()

    if not fundamentals.empty:
        excl = {"symbol", "fetched_at", "latest_quarter", "shareholding_quarter"}
        fund_cols = [c for c in fundamentals.columns if c not in excl]
        enriched = universe_only.merge(
            fundamentals[["symbol"] + fund_cols], on="symbol", how="left"
        )
    else:
        enriched = universe_only

    total = len(enriched)
    coverage_report: dict = {"warnings": []}

    for col in required_columns:
        if col not in enriched.columns:
            coverage_report[col] = {"available": 0, "total": total, "pct": 0}
            coverage_report["warnings"].append(
                f"'{col}' is not available in the current dataset"
            )
            continue
        n = int(enriched[col].notna().sum())
        pct = round(n / total * 100, 1) if total else 0
        coverage_report[col] = {"available": n, "total": total, "pct": pct}
        if pct == 0:
            coverage_report["warnings"].append(
                f"'{col}': no data available — click stocks to build coverage"
            )
        elif pct < 20:
            coverage_report["warnings"].append(
                f"'{col}': only {n}/{total} stocks ({pct}%) — results cover a small subset"
            )
        elif pct < 60:
            coverage_report["warnings"].append(
                f"'{col}': {n}/{total} stocks ({pct}%) — partial coverage, use cautiously"
            )

    return enriched, coverage_report


# ── Agent 3: Filter Builder ───────────────────────────────────────────────────

def _build_filter_prompt(df: pd.DataFrame, coverage_report: dict) -> str:
    total = len(df)
    lines = [
        "You are a stock screening assistant. Convert the user's query into a JSON filter spec.",
        "",
        f"AVAILABLE COLUMNS (total stocks: {total}):",
    ]
    for col, (dtype, desc) in COLUMN_META.items():
        if col not in df.columns:
            continue
        cov = coverage_report.get(col)
        if isinstance(cov, dict):
            cov_str = f"{cov['available']}/{total} stocks ({cov['pct']}%)"
        else:
            n = int(df[col].notna().sum())
            cov_str = f"{n}/{total} stocks"
        lines.append(f"- {col} ({dtype}): {desc} [coverage: {cov_str}]")

    lines += [
        "",
        "Indian number system: 1 lakh=100 crores, 1 crore=1 (market_cap_cr is already in crores).",
        "large-cap: market_cap_cr > 20000 | mid-cap: 5000-20000 | small-cap: < 5000",
        "",
        "Return ONLY valid JSON, no markdown:",
        '{"filters":[{"column":"col","operator":"gt|lt|gte|lte|eq|contains","value":N,"description":"..."}],'
        '"sort_by":"col","sort_ascending":true,"summary":"one sentence"}',
    ]
    return "\n".join(lines)


def _apply_filters(df: pd.DataFrame, filter_spec: dict) -> pd.DataFrame:
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


def agent3_filter_builder(
    query: str,
    df: pd.DataFrame,
    coverage_report: dict,
    filter_hints: str,
) -> tuple[pd.DataFrame, dict]:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    system_prompt = _build_filter_prompt(df, coverage_report)
    user_content = query
    if filter_hints:
        user_content = f"{query}\n\nHint from analyst: {filter_hints}"

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    text = next((b.text for b in message.content if hasattr(b, "text")), "{}")
    filter_spec = _parse_json_safe(text)
    filtered_df = _apply_filters(df, filter_spec)
    return filtered_df, filter_spec


# ── Agent 4: Validator ────────────────────────────────────────────────────────

_VALIDATOR_SYSTEM = """You are a financial analyst validating stock screening results.
Review the query, the filter applied, data coverage warnings, and a sample of results.

Assess:
1. Are the results financially plausible given the query?
2. Are there data coverage gaps that could mislead the user?
3. Is the result count reasonable (0 or 426 may indicate a problem)?

Respond ONLY with valid JSON (no markdown):
{
  "valid": true,
  "confidence": "high|medium|low",
  "summary": "user-facing one sentence about what was found",
  "caveat": "data quality or coverage warnings for the user (empty string if none)",
  "suggestions": "optional: suggest a related filter or next step"
}"""


def agent4_validator(
    query: str,
    filtered_df: pd.DataFrame,
    filter_spec: dict,
    coverage_report: dict,
    original_len: int,
) -> dict:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    filter_cols = [f["column"] for f in filter_spec.get("filters", [])]
    show_cols = ["symbol", "name"] + filter_cols
    show_cols = [c for c in show_cols if c in filtered_df.columns]
    sample = filtered_df[show_cols].head(5).to_dict(orient="records") if not filtered_df.empty else []

    context = {
        "user_query": query,
        "result_count": len(filtered_df),
        "total_universe": original_len,
        "filter_applied": filter_spec.get("summary", ""),
        "filters": filter_spec.get("filters", []),
        "data_coverage_warnings": coverage_report.get("warnings", []),
        "sample_results": sample,
    }

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=_VALIDATOR_SYSTEM,
        messages=[{"role": "user", "content": json.dumps(context, indent=2)}],
    )
    text = next((b.text for b in message.content if hasattr(b, "text")), "{}")
    return _parse_json_safe(text)


# ── Fallback ──────────────────────────────────────────────────────────────────

def _fallback_single_agent(
    query: str,
    df: pd.DataFrame,
    steps: list[AgentStep],
) -> PipelineResult:
    from src.nl_filter import run_nl_filter

    step = AgentStep(
        agent_name="Fallback (single-agent)",
        status="warning",
        reasoning="Multi-agent pipeline encountered an error. Using single-agent fallback.",
    )
    steps.append(step)

    try:
        filtered_df, filter_spec = run_nl_filter(query, df)
        return PipelineResult(
            filtered_df=filtered_df,
            filter_spec=filter_spec,
            steps=steps,
            summary=filter_spec.get("summary", query),
            caveat="",
            valid=True,
        )
    except Exception as e:
        return PipelineResult(
            filtered_df=pd.DataFrame(),
            filter_spec={},
            steps=steps,
            summary=f"Filter failed: {e}",
            caveat="",
            valid=False,
        )


# ── Pipeline orchestrator ─────────────────────────────────────────────────────

def run_agent_filter(query: str, df: pd.DataFrame) -> PipelineResult:
    """Run the full 4-agent pipeline. Falls back to single-agent on failure."""
    from src.database import save_filter

    steps: list[AgentStep] = []
    original_len = len(df)

    # ── Agent 1 ───────────────────────────────────────────────────────────────
    step1 = AgentStep(agent_name="Query Analyst", status="running", reasoning="")
    steps.append(step1)

    try:
        analysis = agent1_query_analyst(query, df)
        step1.status = "done" if analysis.get("can_filter", True) else "warning"
        step1.reasoning = analysis.get("reasoning", "")
        step1.details = {
            "required_columns": analysis.get("required_columns", []),
            "needs_enrichment": analysis.get("needs_enrichment", False),
            "domain": analysis.get("column_domain", ""),
        }
    except Exception as e:
        step1.status = "error"
        step1.reasoning = f"Agent 1 failed: {e}"
        return _fallback_single_agent(query, df, steps)

    if not analysis.get("can_filter", True):
        return PipelineResult(
            filtered_df=pd.DataFrame(),
            filter_spec={},
            steps=steps,
            summary="Cannot filter",
            caveat=analysis.get("cannot_answer_reason", "This query cannot be answered with the available data."),
            valid=False,
        )

    # ── Agent 2 ───────────────────────────────────────────────────────────────
    step2 = AgentStep(agent_name="Data Enricher", status="running", reasoning="")
    steps.append(step2)

    try:
        enriched_df, coverage_report = agent2_data_enricher(
            required_columns=analysis.get("required_columns", []),
            needs_enrichment=analysis.get("needs_enrichment", False),
            current_df=df,
        )
        warnings = coverage_report.get("warnings", [])
        step2.status = "warning" if warnings else "done"
        n_cached = sum(1 for v in coverage_report.values()
                       if isinstance(v, dict) and v.get("available", 0) > 0)
        step2.reasoning = (
            f"Loaded {original_len} stocks. "
            + ("; ".join(warnings) if warnings else "All required columns have sufficient coverage.")
        )
        step2.details = coverage_report
    except Exception as e:
        step2.status = "error"
        step2.reasoning = f"Enrichment failed: {e}"
        enriched_df = df
        coverage_report = {"warnings": [str(e)]}

    # ── Agent 3 ───────────────────────────────────────────────────────────────
    step3 = AgentStep(agent_name="Filter Builder", status="running", reasoning="")
    steps.append(step3)

    try:
        filtered_df, filter_spec = agent3_filter_builder(
            query=query,
            df=enriched_df,
            coverage_report=coverage_report,
            filter_hints=analysis.get("filter_hints", ""),
        )
        step3.status = "done"
        step3.reasoning = filter_spec.get("summary", "Filter applied.")
        step3.details = {
            "filters": filter_spec.get("filters", []),
            "result_count": len(filtered_df),
        }
    except Exception as e:
        step3.status = "error"
        step3.reasoning = f"Filter build failed: {e}"
        return _fallback_single_agent(query, df, steps)

    # ── Agent 4 ───────────────────────────────────────────────────────────────
    step4 = AgentStep(agent_name="Validator", status="running", reasoning="")
    steps.append(step4)

    try:
        validation = agent4_validator(
            query=query,
            filtered_df=filtered_df,
            filter_spec=filter_spec,
            coverage_report=coverage_report,
            original_len=original_len,
        )
        step4.status = "done" if validation.get("valid", True) else "warning"
        step4.reasoning = validation.get("summary", "")
        step4.details = validation
    except Exception as e:
        step4.status = "warning"
        step4.reasoning = f"Validation skipped: {e}"
        validation = {
            "valid": True,
            "summary": filter_spec.get("summary", ""),
            "caveat": "; ".join(coverage_report.get("warnings", [])),
            "suggestions": "",
        }

    # ── Persist ───────────────────────────────────────────────────────────────
    symbols = filtered_df["symbol"].tolist() if not filtered_df.empty else []
    save_filter(query, filter_spec, symbols)

    return PipelineResult(
        filtered_df=filtered_df,
        filter_spec=filter_spec,
        steps=steps,
        summary=validation.get("summary", filter_spec.get("summary", "")),
        caveat=validation.get("caveat", ""),
        valid=validation.get("valid", True),
    )
