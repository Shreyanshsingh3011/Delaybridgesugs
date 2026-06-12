"""Build a generic, auto-inferred dashboard spec from raw sheet rows.

Given each connected sheet's raw rows (list of dicts), infer column types and produce
KPI cards, suggested charts, and a (capped) row table. Pure-Python, no external deps —
the frontend renders the returned spec with recharts + a table.
"""
from typing import Any, Dict, List
from collections import Counter, defaultdict
import re

_NUM_RE = re.compile(r"^-?\d{1,3}(,\d{3})*(\.\d+)?$|^-?\d+(\.\d+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}|^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")


def _to_number(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    if s == "" or not _NUM_RE.match(str(v).strip()):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _looks_date(v):
    if v is None:
        return False
    return bool(_DATE_RE.match(str(v).strip()))


def _infer_columns(rows: List[Dict[str, Any]], headers: List[str]) -> List[Dict[str, Any]]:
    cols = []
    sample = rows[:200]
    for h in headers:
        vals = [r.get(h) for r in sample if r.get(h) not in (None, "")]
        n = len(vals)
        if n == 0:
            cols.append({"name": h, "type": "text", "distinct": 0})
            continue
        num_ct = sum(1 for v in vals if _to_number(v) is not None)
        date_ct = sum(1 for v in vals if _looks_date(v))
        distinct = len(set(str(v) for v in vals))
        if num_ct >= 0.8 * n and not (date_ct >= 0.8 * n):
            t = "number"
        elif date_ct >= 0.7 * n:
            t = "date"
        elif distinct <= 15 and distinct <= 0.5 * n + 1:
            t = "category"
        else:
            t = "text"
        cols.append({"name": h, "type": t, "distinct": distinct})
    return cols


def _counts(rows, col, top=8):
    c = Counter(str(r.get(col)) for r in rows if r.get(col) not in (None, ""))
    common = c.most_common(top)
    data = [{"name": k, "value": v} for k, v in common]
    other = sum(c.values()) - sum(v for _, v in common)
    if other > 0:
        data.append({"name": "Other", "value": other})
    return data


def _sum_by(rows, cat_col, num_col, top=8):
    agg = defaultdict(float)
    for r in rows:
        key = r.get(cat_col)
        num = _to_number(r.get(num_col))
        if key in (None, "") or num is None:
            continue
        agg[str(key)] += num
    items = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:top]
    return [{"name": k, "value": round(v, 2)} for k, v in items]


def _build_one(sheet: Dict[str, Any], max_rows: int) -> Dict[str, Any]:
    rows = sheet.get("rows_raw") or []
    headers = list(rows[0].keys()) if rows else (sheet.get("headers") or [])
    cols = _infer_columns(rows, headers)
    by_type = defaultdict(list)
    for c in cols:
        by_type[c["type"]].append(c["name"])

    # KPIs
    kpis = [{"label": "Rows", "value": len(rows)}]
    for num_col in by_type["number"][:3]:
        total = sum(_to_number(r.get(num_col)) or 0 for r in rows)
        kpis.append({"label": f"Σ {num_col}", "value": round(total, 2)})
    if by_type["category"]:
        kpis.append({"label": f"{by_type['category'][0]} types",
                     "value": next((c["distinct"] for c in cols if c["name"] == by_type["category"][0]), 0)})

    # Charts
    charts = []
    cat_cols = by_type["category"]
    for cat in cat_cols[:3]:
        charts.append({"type": "bar", "title": f"Count by {cat}", "x": "name", "y": "value",
                       "data": _counts(rows, cat)})
    if cat_cols and by_type["number"]:
        cat, num = cat_cols[0], by_type["number"][0]
        charts.append({"type": "bar", "title": f"{num} by {cat}", "x": "name", "y": "value",
                       "data": _sum_by(rows, cat, num)})
    if not cat_cols and by_type["category"] == [] and len(cat_cols) == 0 and by_type["number"]:
        # fall back: distribution of the first numeric column bucketed is overkill; skip
        pass

    return {
        "label": sheet.get("label"),
        "name": sheet.get("name") or sheet.get("label"),
        "color": sheet.get("color", "blue"),
        "row_count": len(rows),
        "columns": cols,
        "kpis": kpis,
        "charts": charts,
        "rows": rows[:max_rows],
        "truncated": len(rows) > max_rows,
    }


def build_data_dashboard(sheets: List[Dict[str, Any]], max_rows: int = 500) -> Dict[str, Any]:
    return {"sheets": [_build_one(s, max_rows) for s in sheets]}
