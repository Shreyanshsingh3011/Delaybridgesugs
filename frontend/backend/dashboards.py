"""Build a generic, auto-inferred BI dashboard spec from raw sheet rows.

All aggregates computed over ALL data rows (never a sample), excluding
subtotal/total rows. Existing response fields are 100% unchanged;
new richness goes into bi_kpis, extra_charts, elements, signals, and pivot_tables.
"""
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter, defaultdict
import re
import math

_NUM_RE = re.compile(r"^-?\d{1,3}(,\d{3})*(\.\d+)?$|^-?\d+(\.\d+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}|^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")
_SUBTOTAL_PAT = re.compile(r"^\s*(total|sub.?total|grand.?total)\s*$", re.IGNORECASE)
_ID_PAT = re.compile(r"(^|\b|_)(no\.?|id|sl|sr|serial|row|order|code|index|rank|#)(\b|_|$)", re.I)


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


def _is_subtotal(row: Dict[str, Any], headers: List[str]) -> bool:
    if not headers:
        return False
    first = str(row.get(headers[0], "")).strip()
    return bool(_SUBTOTAL_PAT.match(first))


def _infer_columns(rows: List[Dict[str, Any]], headers: List[str]) -> List[Dict[str, Any]]:
    """Infer column types using ALL rows."""
    cols = []
    for h in headers:
        vals = [r.get(h) for r in rows if r.get(h) not in (None, "")]
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


def _counts(rows: List[Dict], col: str, top: int = 8) -> List[Dict]:
    c: Counter = Counter(str(r.get(col)) for r in rows if r.get(col) not in (None, ""))
    common = c.most_common(top)
    data = [{"name": k, "value": v} for k, v in common]
    other = sum(c.values()) - sum(v for _, v in common)
    if other > 0:
        data.append({"name": "Other", "value": other})
    return data


def _sum_by(rows: List[Dict], cat_col: str, num_col: str, top: int = 8) -> List[Dict]:
    agg: Dict[str, float] = defaultdict(float)
    for r in rows:
        key = r.get(cat_col)
        num = _to_number(r.get(num_col))
        if key in (None, "") or num is None:
            continue
        agg[str(key)] += num
    items = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:top]
    return [{"name": k, "value": round(v, 2)} for k, v in items]


def _sum_by_text(rows: List[Dict], text_col: str, num_col: str, top: int = 10) -> List[Dict]:
    agg: Dict[str, float] = defaultdict(float)
    for r in rows:
        key = r.get(text_col)
        num = _to_number(r.get(num_col))
        if key in (None, "") or num is None:
            continue
        agg[str(key)] += num
    items = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:top]
    return [{"name": k, "value": round(v, 2)} for k, v in items]


def _count_by_text(rows: List[Dict], text_col: str, top: int = 10) -> List[Dict]:
    c: Counter = Counter(str(r.get(text_col)) for r in rows if r.get(text_col) not in (None, ""))
    return [{"name": k, "value": v} for k, v in c.most_common(top)]


def _primary_measure(data_rows: List[Dict], num_cols: List[str]) -> Optional[str]:
    cands = [c for c in num_cols if not _ID_PAT.search(c)] or num_cols
    best, best_sum = None, -1.0
    for c in cands:
        s = sum(abs(_to_number(r.get(c)) or 0) for r in data_rows)
        if s > best_sum:
            best, best_sum = c, s
    return best


def _numeric_stats(vals: List[float]) -> Dict[str, float]:
    if not vals:
        return {}
    n = len(vals)
    total = sum(vals)
    avg = total / n
    sorted_v = sorted(vals)
    median = sorted_v[n // 2] if n % 2 else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
    variance = sum((v - avg) ** 2 for v in vals) / n
    std_dev = math.sqrt(variance)
    p80 = sorted_v[int(0.8 * n)]
    p20 = sorted_v[int(0.2 * n)]
    return {
        "total": round(total, 2),
        "count": n,
        "avg": round(avg, 2),
        "median": round(median, 2),
        "std_dev": round(std_dev, 2),
        "min": round(sorted_v[0], 2),
        "max": round(sorted_v[-1], 2),
        "p20": round(p20, 2),
        "p80": round(p80, 2),
    }


def _pareto_data(rows: List[Dict], dim: str, measure: str) -> Tuple[List[Dict], float]:
    agg: Dict[str, float] = defaultdict(float)
    for r in rows:
        k = r.get(dim)
        v = _to_number(r.get(measure))
        if k not in (None, "") and v is not None and v > 0:
            agg[str(k)] += v
    if not agg:
        return [], 0.0
    total = sum(agg.values())
    if total == 0:
        return [], 0.0
    ranked = sorted(agg.items(), key=lambda x: x[1], reverse=True)
    cumulative = 0.0
    data = []
    for k, v in ranked[:20]:
        cumulative += v
        data.append({"name": k, "value": round(v, 2), "cumulative_pct": round(cumulative / total * 100, 1)})
    top_n = max(1, len(ranked) // 5)
    top_share = round(sum(v for _, v in ranked[:top_n]) / total * 100, 1)
    return data, top_share


def _distribution_buckets(vals: List[float], n_buckets: int = 8) -> List[Dict]:
    if len(vals) < 2:
        return []
    lo, hi = min(vals), max(vals)
    if lo == hi:
        return [{"name": str(round(lo, 2)), "value": len(vals)}]
    width = (hi - lo) / n_buckets
    buckets: Dict[str, int] = defaultdict(int)
    for v in vals:
        idx = min(int((v - lo) / width), n_buckets - 1)
        label = f"{round(lo + idx * width, 2)}–{round(lo + (idx + 1) * width, 2)}"
        buckets[label] += 1
    return [{"name": k, "value": v} for k, v in buckets.items()]


def _cross_pivot(rows: List[Dict], dim1: str, dim2: str, measure: str, top: int = 6) -> List[Dict]:
    agg: Dict[Tuple, float] = defaultdict(float)
    for r in rows:
        k1, k2 = r.get(dim1), r.get(dim2)
        v = _to_number(r.get(measure))
        if k1 not in (None, "") and k2 not in (None, "") and v is not None:
            agg[(str(k1), str(k2))] += v
    dim1_totals: Dict[str, float] = defaultdict(float)
    dim2_totals: Dict[str, float] = defaultdict(float)
    for (k1, k2), v in agg.items():
        dim1_totals[k1] += v
        dim2_totals[k2] += v
    top_dim1 = [k for k, _ in sorted(dim1_totals.items(), key=lambda x: x[1], reverse=True)[:top]]
    top_dim2 = [k for k, _ in sorted(dim2_totals.items(), key=lambda x: x[1], reverse=True)[:top]]
    result = []
    for k1 in top_dim1:
        row: Dict[str, Any] = {"name": k1}
        for k2 in top_dim2:
            row[k2] = round(agg.get((k1, k2), 0), 2)
        result.append(row)
    return result


def _build_one(sheet: Dict[str, Any], max_rows: int) -> Dict[str, Any]:
    rows = sheet.get("rows_raw") or []
    headers = list(rows[0].keys()) if rows else (sheet.get("headers") or [])
    cols = _infer_columns(rows, headers)
    by_type: Dict[str, List[str]] = defaultdict(list)
    for c in cols:
        by_type[c["type"]].append(c["name"])

    data_rows = [r for r in rows if not _is_subtotal(r, headers)]

    num_cols = by_type["number"]
    cat_cols = by_type["category"]
    text_cols_ranked = sorted(
        by_type["text"],
        key=lambda c: next((col["distinct"] for col in cols if col["name"] == c), 0),
        reverse=True,
    )

    measure = _primary_measure(data_rows, num_cols) if num_cols else None
    item_dim = text_cols_ranked[0] if text_cols_ranked else None
    secondary_text_dim = text_cols_ranked[1] if len(text_cols_ranked) > 1 else None

    # ── EXISTING KPIs — unchanged ─────────────────────────────────────────────
    kpis = [{"label": "Rows", "value": len(data_rows)}]
    for num_col in num_cols[:3]:
        total = sum(_to_number(r.get(num_col)) or 0 for r in data_rows)
        kpis.append({"label": f"Σ {num_col}", "value": round(total, 2)})
    if cat_cols:
        kpis.append({"label": f"{cat_cols[0]} types",
                     "value": next((c["distinct"] for c in cols if c["name"] == cat_cols[0]), 0)})
    if by_type["text"]:
        text_col = by_type["text"][0]
        distinct_count = len(set(
            str(r.get(text_col)) for r in data_rows if r.get(text_col) not in (None, "")
        ))
        kpis.append({"label": f"{text_col} (distinct)", "value": distinct_count})

    # ── EXISTING CHARTS — unchanged ───────────────────────────────────────────
    charts = []
    for cat in cat_cols[:3]:
        charts.append({"type": "bar", "title": f"Count by {cat}", "x": "name", "y": "value",
                       "data": _counts(data_rows, cat)})
    if cat_cols and num_cols:
        cat, num = cat_cols[0], num_cols[0]
        charts.append({"type": "bar", "title": f"{num} by {cat}", "x": "name", "y": "value",
                       "data": _sum_by(data_rows, cat, num)})

    # ── BI KPIs (additive) ────────────────────────────────────────────────────
    bi_kpis = []
    measure_stats: Dict[str, float] = {}

    if measure:
        m_vals = [v for v in (_to_number(r.get(measure)) for r in data_rows) if v is not None]
        measure_stats = _numeric_stats(m_vals)
        if measure_stats:
            bi_kpis += [
                {"label": f"Total {measure}", "value": measure_stats["total"]},
                {"label": f"Avg {measure} per line", "value": measure_stats["avg"]},
                {"label": f"Median {measure}", "value": measure_stats["median"]},
                {"label": f"Largest {measure}", "value": measure_stats["max"]},
                {"label": f"Smallest {measure}", "value": measure_stats["min"]},
                {"label": f"Std Dev {measure}", "value": measure_stats["std_dev"]},
                {"label": f"P80 {measure}", "value": measure_stats["p80"]},
                {"label": f"P20 {measure}", "value": measure_stats["p20"]},
            ]
        blank_count = sum(1 for r in data_rows if str(r.get(measure, "")).strip() == "")
        bi_kpis.append({"label": f"Zero/Blank {measure}", "value": blank_count})

    for cat in cat_cols:
        d = len(set(str(r.get(cat)) for r in data_rows if r.get(cat) not in (None, "")))
        bi_kpis.append({"label": f"{cat} (distinct)", "value": d})
    for txt in text_cols_ranked:
        if txt != (by_type["text"][0] if by_type["text"] else None):
            d = len(set(str(r.get(txt)) for r in data_rows if r.get(txt) not in (None, "")))
            bi_kpis.append({"label": f"{txt} (distinct)", "value": d})

    # ── EXTRA CHARTS (additive) ───────────────────────────────────────────────
    extra_charts = []

    if measure:
        for txt in [item_dim, secondary_text_dim]:
            if txt:
                data = _sum_by_text(data_rows, txt, measure, top=10)
                if data:
                    extra_charts.append({
                        "type": "bar",
                        "title": f"Top 10 {txt} by {measure}",
                        "x": "name", "y": "value", "data": data,
                    })
        for cat in cat_cols[1:3]:
            data = _sum_by(data_rows, cat, measure, top=8)
            if data:
                extra_charts.append({
                    "type": "bar",
                    "title": f"{measure} by {cat}",
                    "x": "name", "y": "value", "data": data,
                })
        if measure_stats:
            m_vals_pos = [v for v in (_to_number(r.get(measure)) for r in data_rows)
                          if v is not None and v > 0]
            dist = _distribution_buckets(m_vals_pos)
            if dist:
                extra_charts.append({
                    "type": "bar",
                    "title": f"{measure} distribution",
                    "x": "name", "y": "value", "data": dist,
                })
        if item_dim:
            pareto_data, top20_share = _pareto_data(data_rows, item_dim, measure)
            if pareto_data:
                extra_charts.append({
                    "type": "pareto",
                    "title": f"Pareto: {item_dim} by {measure}",
                    "x": "name", "y": "value", "cumulative_key": "cumulative_pct",
                    "data": pareto_data,
                })
    else:
        if item
