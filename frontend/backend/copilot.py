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


# ---- Keyless fallback: answer common questions from exact computed aggregates ----
from collections import Counter, defaultdict  # noqa: E402
from insights import _is_total_row, _quality_for_sheet, build_digest, _fmt  # noqa: E402


def answer_locally(question: str, sheets) -> str:
    """Deterministic copilot used when no LLM key is set. Computes exact answers for
    common quantitative/quality/summary questions from the selected sheet."""
    if not sheets:
        return "No connected sheets to answer from yet."
    s = sheets[0]
    rows = [r for r in (s.get("rows_raw") or []) if not _is_total_row(r)]
    headers = list(rows[0].keys()) if rows else (s.get("headers") or [])
    cols = _infer_columns(rows, headers)
    numeric = [c["name"] for c in cols if c["type"] == "number"]
    cats = [c["name"] for c in cols if c["type"] in ("category", "text")]
    q = (question or "").lower()

    def find_col(cands):
        for c in sorted(cands, key=len, reverse=True):
            if c.lower() in q:
                return c
        return None

    # Summary
    if any(w in q for w in ["summar", "overview", "describe", "tell me about", "what is this"]):
        return " ".join(build_digest([s])["sheets"][0]["highlights"])

    # Data quality
    if any(w in q for w in ["quality", "issue", "problem", "duplicate", "missing", "clean", "casing", "wrong"]):
        qd = _quality_for_sheet(s); i = qd["issues"]; parts = [f"Quality score {qd['score']}/100."]
        if i["total_subtotal_rows"]:
            parts.append(f"{i['total_subtotal_rows']} total/subtotal rows inflate sums.")
        if i["inconsistent_categories"]:
            parts.append("casing/duplicate variants in " + ", ".join(c["column"] for c in i["inconsistent_categories"]) + ".")
        if i["missing"]:
            parts.append("missing values in " + ", ".join(m["column"] for m in i["missing"][:3]) + ".")
        if i["type_mismatches"]:
            parts.append("non-numeric values in " + ", ".join(t["column"] for t in i["type_mismatches"]) + ".")
        return " ".join(parts) if len(parts) > 1 else parts[0] + " No major issues detected."

    # Row count
    if any(w in q for w in ["how many row", "number of row", "row count", "count of row", "total rows", "how many record", "how many entries"]):
        return f"{len(rows)} rows (excluding total/subtotal rows)."

    superlative = any(w in q for w in ["highest", "top", "most", "largest", "biggest", "lowest", "least", "smallest", "maximum", "minimum"])
    low = any(w in q for w in ["lowest", "least", "smallest", "minimum", "min "])
    grouping = ("which" in q) or (" by " in q) or ("per " in q) or ("each" in q)

    # Group-by superlative first: "which <dim> has the highest <measure>"
    if superlative and (grouping or (find_col(cats) and find_col(numeric))):
        dim = find_col(cats) or (cats[0] if cats else None)
        measure = find_col(numeric)
        if dim:
            if measure:
                agg = defaultdict(float)
                for r in rows:
                    k = r.get(dim); m = _to_number(r.get(measure))
                    if k not in (None, "") and m is not None:
                        agg[str(k)] += m
                if agg:
                    k, v = (min if low else max)(agg.items(), key=lambda x: x[1])
                    return f"{dim} with the {'lowest' if low else 'highest'} total {measure}: '{k}' ({_fmt(v)})."
            cnt = Counter(str(r.get(dim)) for r in rows if r.get(dim) not in (None, ""))
            if cnt:
                items = cnt.most_common()
                k, v = (items[-1] if low else items[0])
                return f"{'Least' if low else 'Most'} common {dim}: '{k}' ({v} rows)."

    col = find_col(numeric)
    if col and any(w in q for w in ["average", "avg", "mean"]):
        vals = [v for v in (_to_number(r.get(col)) for r in rows) if v is not None]
        return f"Average {col}: {_fmt(sum(vals) / len(vals))} across {len(vals)} rows." if vals else f"No numeric values in {col}."
    if col and superlative and not low:
        vals = [v for v in (_to_number(r.get(col)) for r in rows) if v is not None]
        return f"Maximum {col}: {_fmt(max(vals))}." if vals else f"No numeric values in {col}."
    if col and superlative and low:
        vals = [v for v in (_to_number(r.get(col)) for r in rows) if v is not None]
        return f"Minimum {col}: {_fmt(min(vals))}." if vals else f"No numeric values in {col}."
    if col and any(w in q for w in ["total", "sum"]):
        tot = sum(_to_number(r.get(col)) or 0 for r in rows)
        return f"Total {col}: {_fmt(tot)} across {len(rows)} rows (total/subtotal rows excluded)."

    # Distinct / list values
    dim = find_col(cats)
    if dim and any(w in q for w in ["distinct", "unique", "list", "what are", "which values", "categories", "breakdown"]):
        cnt = Counter(str(r.get(dim)) for r in rows if r.get(dim) not in (None, ""))
        return f"{dim} values: " + ", ".join(f"{k} ({v})" for k, v in cnt.most_common(12)) + "."

    # Fallback: profile + guidance
    return ("Here's what I can read from this sheet: " + " ".join(build_digest([s])["sheets"][0]["highlights"]) +
            " Ask me about a total, average, count, the top/least category, distinct values, or data-quality issues. "
            "(Set ANTHROPIC_API_KEY on the server to unlock free-form AI answers.)")
