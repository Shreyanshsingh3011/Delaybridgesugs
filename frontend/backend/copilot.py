"""Sheet-grounded Copilot. Builds a deterministic context pack (schema + EXACT aggregates
+ a small sample) from the raw sheet rows, so the LLM answers quantitative questions from
real computed numbers instead of guessing. Falls back gracefully when no API key is set."""
import json
from typing import Any, Dict, List
from collections import Counter

from dashboards import _infer_columns, _to_number


def _numeric_summary(rows, col):
    vals = [_to_number(r.get(col)) for r in rows]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    n = len(vals)
    s = sum(vals)
    return {"count": n, "sum": round(s, 2), "avg": round(s / n, 2),
            "min": round(min(vals), 2), "max": round(max(vals), 2)}


def _trim(v, limit=120):
    s = "" if v is None else str(v)
    return s if len(s) <= limit else s[:limit] + "…"


def build_sheet_context(sheets: List[Dict[str, Any]], max_sample: int = 12) -> Dict[str, Any]:
    """Returns {text, columns} — text is the prompt context, columns is structured profile."""
    blocks = []
    profile = []
    for s in sheets:
        rows = s.get("rows_raw") or []
        headers = list(rows[0].keys()) if rows else (s.get("headers") or [])
        cols = _infer_columns(rows, headers)
        lines = [f"SHEET: {s.get('label')} — {s.get('name') or s.get('label')} ({len(rows)} rows)"]
        lines.append("COLUMNS: " + ", ".join(f"{c['name']} [{c['type']}]" for c in cols))
        for c in cols:
            if c["type"] == "number":
                ns = _numeric_summary(rows, c["name"])
                if ns:
                    lines.append(
                        f"NUMERIC {c['name']}: sum={ns['sum']}, avg={ns['avg']}, "
                        f"min={ns['min']}, max={ns['max']}, non_empty={ns['count']}")
            elif c["type"] == "category":
                cnt = Counter(str(r.get(c["name"])) for r in rows if r.get(c["name"]) not in (None, ""))
                top = ", ".join(f"{k}={v}" for k, v in cnt.most_common(15))
                lines.append(f"CATEGORY {c['name']} counts: {top}")
        sample = rows[:max_sample]
        lines.append(f"SAMPLE ROWS (first {len(sample)} of {len(rows)} — preview only, NOT the full data):")
        for r in sample:
            lines.append("  " + json.dumps({k: _trim(v) for k, v in r.items()}, default=str))
        blocks.append("\n".join(lines))
        profile.append({"label": s.get("label"), "row_count": len(rows), "columns": cols})
    return {"text": "\n\n".join(blocks), "profile": profile}


def build_copilot_system_prompt(context_text: str, project_name: str) -> str:
    return (
        f"You are a data copilot for the project '{project_name}'. Answer questions ONLY using the "
        "dataset facts provided below. For any total, count, average, min, or max, use the exact "
        "NUMERIC and CATEGORY aggregates given — do NOT recompute from the SAMPLE ROWS, which are only "
        "a partial preview, never the complete data. If a question can't be answered from the dataset, "
        "say so plainly rather than inventing an answer. Be concise, cite the exact numbers, and when "
        "useful suggest which column or breakdown would answer a follow-up.\n\n"
        f"=== DATASET ===\n{context_text}\n=== END DATASET ==="
    )
