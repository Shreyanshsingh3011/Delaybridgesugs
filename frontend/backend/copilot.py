"""Sheet-grounded Copilot.

Builds a rich, grounded context pack for each session:
  - Schema: column names, types, distinct counts
  - Exact aggregates: numeric sum/avg/min/max, category distributions
  - Pre-computed module outputs: data_quality, recommendations, anomalies, digest
  - type_kpis if available

The LLM answers ONLY from these computed values — never from raw rows or
outside knowledge. Conversation history is maintained in-process per session_id
(evicted after 50 turns). Tool results are cached per (session_id, sheet_labels).
"""
import json
import re
import logging
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from dashboards import _infer_columns, _to_number
from insights import _is_total_row, _quality_for_sheet, build_digest, _fmt

logger = logging.getLogger(__name__)

# ── In-process caches ────────────────────────────────────────────────────────

_HISTORY: Dict[str, List[Dict[str, str]]] = {}
_MAX_HISTORY = 50


# ── Helpers ───────────────────────────────────────────────────────────────────

def _trim(v, limit: int = 80) -> str:
    s = "" if v is None else str(v)
    return s if len(s) <= limit else s[:limit] + "…"


def _numeric_summary(rows: List[Dict], col: str) -> Optional[Dict]:
    vals = [_to_number(r.get(col)) for r in rows]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    n = len(vals)
    s = sum(vals)
    return {"count": n, "sum": round(s, 2), "avg": round(s / n, 2),
            "min": round(min(vals), 2), "max": round(max(vals), 2)}


# ── Context builder ───────────────────────────────────────────────────────────

def build_grounded_context(sheets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a full grounded context dict for the copilot.

    Returns {text, profile, cache_key}.
    Does NOT include raw rows — only schema + exact aggregates + module outputs.
    """
    blocks = []
    profile = []

    for s in sheets:
        rows_all = s.get("rows_raw") or []
        rows = [r for r in rows_all if not _is_total_row(r)]
        headers = s.get("headers") or (list(rows[0].keys()) if rows else [])
        cols = _infer_columns(rows, headers)

        label = s.get("label", "")
        lines = [
            f"=== SHEET: {label} ({s.get('name') or label}) — {len(rows)} data rows ===",
        ]

        # Schema
        lines.append("COLUMNS:")
        for c in cols:
            lines.append(f"  {c['name']} [{c['type']}] — {c.get('distinct', '?')} distinct values")

        # Numeric aggregates
        num_cols = [c for c in cols if c["type"] == "number"]
        if num_cols:
            lines.append("NUMERIC AGGREGATES (exact, computed from all data rows):")
            for c in num_cols:
                ns = _numeric_summary(rows, c["name"])
                if ns:
                    lines.append(
                        f"  {c['name']}: sum={ns['sum']}, avg={ns['avg']}, "
                        f"min={ns['min']}, max={ns['max']}, non_empty={ns['count']}"
                    )

        # Category distributions
        cat_cols = [c for c in cols if c["type"] in ("category", "text")]
        if cat_cols:
            lines.append("CATEGORY DISTRIBUTIONS (top 20 per column, exact counts):")
            for c in cat_cols:
                cnt = Counter(
                    str(r.get(c["name"]))
                    for r in rows if r.get(c["name"]) not in (None, "")
                )
                top = cnt.most_common(20)
                lines.append(f"  {c['name']}: " + ", ".join(f"{k}={v}" for k, v in top))

        # type_kpis
        type_kpis = s.get("type_kpis") or []
        if type_kpis:
            lines.append("TYPE KPIs (exact computed values):")
            for kpi in type_kpis:
                lines.append(f"  {kpi['label']}: {kpi['value']}")

        # data_quality
        try:
            dq = _quality_for_sheet(s)
            lines.append(f"DATA QUALITY SCORE: {dq['score']}/100")
            issues = dq.get("issues", {})
            if issues.get("total_subtotal_rows"):
                lines.append(f"  Subtotal rows detected: {issues['total_subtotal_rows']} (excluded from aggregates)")
            if issues.get("missing"):
                lines.append("  Missing values in: " + ", ".join(
                    f"{m['column']} ({m['missing_count']} missing)" for m in issues["missing"][:5]
                ))
            if issues.get("inconsistent_categories"):
                lines.append("  Casing/variant issues in: " + ", ".join(
                    c["column"] for c in issues["inconsistent_categories"][:5]
                ))
            if issues.get("type_mismatches"):
                lines.append("  Type mismatches in: " + ", ".join(
                    t["column"] for t in issues["type_mismatches"][:5]
                ))
            if issues.get("duplicate_rows"):
                lines.append(f"  Duplicate rows: {issues['duplicate_rows']}")
        except Exception as e:
            logger.warning("copilot: data_quality failed for %r: %s", label, e)

        # digest highlights
        try:
            dg = build_digest([s])
            sh = (dg.get("sheets") or [{}])[0]
            highlights = sh.get("highlights") or []
            if highlights:
                lines.append("DIGEST HIGHLIGHTS:")
                for h in highlights[:6]:
                    lines.append(f"  * {h}")
        except Exception as e:
            logger.warning("copilot: digest failed for %r: %s", label, e)

        # anomalies
        try:
            from insights import build_anomalies
            anom = build_anomalies([s])
            sheet_anom = next((a for a in (anom.get("sheets") or []) if a.get("label") == label), None)
            if sheet_anom:
                flagged = sheet_anom.get("flagged_rows") or []
                if flagged:
                    lines.append(f"ANOMALIES DETECTED: {len(flagged)} outlier rows")
                    for a in flagged[:4]:
                        lines.append(f"  Row {a.get('row_index')}: {a.get('column')} = {a.get('value')} (z-score {a.get('zscore')})")
        except Exception as e:
            logger.warning("copilot: anomalies failed for %r: %s", label, e)

        # recommendations
        try:
            from insights import build_recommendations
            recs = build_recommendations([s])
            rec_list = recs.get("recommendations") or []
            if rec_list:
                lines.append("COMPUTED RECOMMENDATIONS (grounded in this sheet's signals):")
                for r in rec_list[:5]:
                    lines.append(f"  [{r.get('priority','?')}] {r.get('text') or r.get('recommendation','')}")
        except Exception as e:
            logger.warning("copilot: recommendations failed for %r: %s", label, e)

        blocks.append("\n".join(lines))
        profile.append({"label": label, "row_count": len(rows), "columns": cols})

    cache_key = "|".join(s.get("label", "") for s in sheets)
    return {"text": "\n\n".join(blocks), "profile": profile, "cache_key": cache_key}


def build_copilot_system_prompt(context_text: str, project_name: str) -> str:
    return f"""You are a grounded data copilot for "{project_name}".

GROUNDING RULES — follow without exception:
1. Every number you state must come verbatim from the DATASET CONTEXT below. Never round, recompute, or estimate a number that is given exactly. Never invent a number.
2. Every piece of advice must be tied to a specific signal in the DATASET CONTEXT (a quality issue, anomaly, recommendation, or distribution). Label suggestions clearly as "Suggestion:" so the user knows they are interpretive, not hard facts.
3. If a question cannot be answered from the data below, say so plainly and state what the data CAN address.
4. Do not use any world knowledge about what numbers "should" be. Describe only what this dataset shows.
5. At the end of answers, offer 1-3 concrete follow-up questions the copilot can actually answer from this data.

CAPABILITIES:
- Quantitative Q&A: answer from the exact aggregates and KPIs in the context.
- Advice: ground every suggestion in a quality score, anomaly, recommendation, or distribution from the context.
- Interpretation: explain what a result means in terms of the data's own patterns.
- Follow-ups: suggest next analyses grounded in available columns and modules.

=== DATASET CONTEXT ===
{context_text}
=== END DATASET CONTEXT ==="""


# ── History management ────────────────────────────────────────────────────────

def get_history(session_id: str) -> List[Dict[str, str]]:
    return _HISTORY.get(session_id, [])


def push_history(session_id: str, question: str, answer: str) -> None:
    hist = _HISTORY.setdefault(session_id, [])
    hist.append({"role": "user", "content": question})
    hist.append({"role": "assistant", "content": answer})
    if len(hist) > _MAX_HISTORY:
        _HISTORY[session_id] = hist[-_MAX_HISTORY:]


def clear_history(session_id: str) -> None:
    _HISTORY.pop(session_id, None)


# ── Keyless fallback ──────────────────────────────────────────────────────────

_ID_PAT = re.compile(r"(^|\b|_)(no\.?|id|sl|sr|serial|row|order|code|index|rank|#)(\b|_|$)", re.I)


def _primary_measure(rows, numeric):
    cand = [c for c in numeric if not _ID_PAT.search(c)] or list(numeric)
    best, best_sum = None, -1.0
    for c in cand:
        s = sum(abs(_to_number(r.get(c)) or 0) for r in rows)
        if s > best_sum:
            best, best_sum = c, s
    return best


def answer_locally(question: str, sheets: List[Dict[str, Any]]) -> str:
    """Deterministic copilot used when no LLM key is set."""
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

    if any(w in q for w in ["summar", "overview", "describe", "tell me about", "what is this"]):
        return " ".join(build_digest([s])["sheets"][0]["highlights"])

    if any(w in q for w in ["quality", "issue", "problem", "duplicate", "missing", "clean", "casing", "wrong"]):
        dq = _quality_for_sheet(s)
        i = dq["issues"]
        parts = [f"Quality score {dq['score']}/100."]
        if i["total_subtotal_rows"]:
            parts.append(f"{i['total_subtotal_rows']} total/subtotal rows inflate sums.")
        if i["inconsistent_categories"]:
            parts.append("Casing/variant issues in " + ", ".join(c["column"] for c in i["inconsistent_categories"]) + ".")
        if i["missing"]:
            parts.append("Missing values in " + ", ".join(m["column"] for m in i["missing"][:3]) + ".")
        if i["type_mismatches"]:
            parts.append("Non-numeric values in " + ", ".join(t["column"] for t in i["type_mismatches"]) + ".")
        return " ".join(parts) if len(parts) > 1 else parts[0] + " No major issues detected."

    if any(w in q for w in ["how many row", "number of row", "row count", "total rows", "how many record"]):
        return f"{len(rows)} rows (excluding total/subtotal rows)."

    superlative = any(w in q for w in ["highest", "top", "most", "largest", "lowest", "least", "smallest", "maximum", "minimum"])
    low = any(w in q for w in ["lowest", "least", "smallest", "minimum"])
    grouping = ("which" in q) or (" by " in q) or ("per " in q) or ("each" in q)
    sum_intent = any(w in q for w in ["total", "sum", "value", "amount"])
    count_intent = any(w in q for w in ["common", "count", "how many", "frequency"])

    if superlative and (grouping or (find_col(cats) and (find_col(numeric) or sum_intent))):
        dim = find_col(cats) or (cats[0] if cats else None)
        measure = find_col(numeric)
        if measure is None and numeric and (sum_intent or not count_intent):
            measure = _primary_measure(rows, numeric)
        if dim:
            if measure and not count_intent:
                agg: Dict[str, float] = defaultdict(float)
                for r in rows:
                    k = r.get(dim)
                    m = _to_number(r.get(measure))
                    if k not in (None, "") and m is not None:
                        agg[str(k)] += m
                if agg:
                    k, v = (min if low else max)(agg.items(), key=lambda x: x[1])
                    return f"By total {measure}, {dim} '{k}' is {'lowest' if low else 'highest'} ({_fmt(v)})."
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
        return f"Total {col}: {_fmt(tot)} across {len(rows)} rows."

    dim = find_col(cats)
    if dim and any(w in q for w in ["distinct", "unique", "list", "what are", "which values", "categories", "breakdown"]):
        cnt = Counter(str(r.get(dim)) for r in rows if r.get(dim) not in (None, ""))
        return f"{dim} values: " + ", ".join(f"{k} ({v})" for k, v in cnt.most_common(12)) + "."

    return ("Here's what I can read from this sheet: " +
            " ".join(build_digest([s])["sheets"][0]["highlights"]) +
            " Ask about row counts, totals, averages, category breakdowns, or data quality.")


# ── Legacy aliases ────────────────────────────────────────────────────────────

def build_sheet_context(sheets: List[Dict[str, Any]], max_sample: int = 12) -> Dict[str, Any]:
    """Legacy alias — returns {text, profile} compatible with old callers."""
    ctx = build_grounded_context(sheets)
    return {"text": ctx["text"], "profile": ctx["profile"]}
