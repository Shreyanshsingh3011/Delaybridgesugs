"""Build a generic, auto-inferred dashboard spec from raw sheet rows.

Given each connected sheet's raw rows (list of dicts), infer column types and produce
KPI cards, suggested charts, and a (capped) row table. Pure-Python, no external deps —
the frontend renders the returned spec with recharts + a table.

In addition to the original KPIs/charts/rows, this module emits a richer BI payload
(bi_kpis, numeric_profiles, extra_charts, elements, pivot_tables, signals, measure,
item_dim). All additions are additive — existing keys are unchanged.
"""
from typing import Any, Dict, List, Optional
from collections import Counter, defaultdict
import math
import re

_NUM_RE = re.compile(r"^-?\d{1,3}(,\d{3})*(\.\d+)?$|^-?\d+(\.\d+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}|^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")
# Columns whose NAME looks like an identifier (not a real measure to sum/average).
_ID_PAT = re.compile(r"\b(id|code|no|sl|serial|row|index|rank)\b|#", re.IGNORECASE)


def _to_number(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    # Tolerate Indian grouping ("2,08,13,53,972"), quotes, and stray % — strip ALL
    # thousands separators, keep the decimal point and leading minus.
    s = str(v).strip().strip('"').strip("'").strip().replace("%", "").replace(",", "")
    if s in ("", "-", "—", "–"):
        return None
    if not re.match(r"^-?\d*\.?\d+$", s):
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


_SUBTOTAL_PAT = re.compile(r"^\s*(total|sub.?total|grand.?total)\s*$", re.IGNORECASE)


def _is_subtotal(row: Dict[str, Any], headers: List[str]) -> bool:
    if not headers:
        return False
    first = str(row.get(headers[0], "")).strip()
    return bool(_SUBTOTAL_PAT.match(first))


def _sum_by_text(rows, text_col, num_col, top=10):
    """Sum num_col grouped by text_col, excluding subtotal rows, top N by value."""
    agg: Dict[str, float] = defaultdict(float)
    headers = list(rows[0].keys()) if rows else []
    for r in rows:
        if _is_subtotal(r, headers):
            continue
        key = r.get(text_col)
        num = _to_number(r.get(num_col))
        if key in (None, "") or num is None:
            continue
        agg[str(key)] += num
    items = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:top]
    return [{"name": k, "value": round(v, 2)} for k, v in items]


def _count_by_text(rows, text_col, top=10):
    """Count occurrences of text_col values, excluding subtotal rows, top N."""
    headers = list(rows[0].keys()) if rows else []
    c: Counter = Counter()
    for r in rows:
        if _is_subtotal(r, headers):
            continue
        v = r.get(text_col)
        if v not in (None, ""):
            c[str(v)] += 1
    items = c.most_common(top)
    return [{"name": k, "value": v} for k, v in items]


# ---------------------------------------------------------------------------
# BI helpers (additive)
# ---------------------------------------------------------------------------

def _numeric_values(rows, col):
    """All non-null numeric values for col across rows (subtotals already excluded)."""
    out = []
    for r in rows:
        n = _to_number(r.get(col))
        if n is not None:
            out.append(n)
    return out


def _percentile(sorted_vals, pct):
    """Linear-interpolation percentile (pct in 0..100). sorted_vals must be sorted."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    frac = k - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def _stats(vals):
    """Summary stats for a list of numbers. Returns None-safe dict."""
    n = len(vals)
    if n == 0:
        return {"count": 0, "sum": 0.0, "mean": None, "median": None,
                "min": None, "max": None, "std": None, "p20": None, "p80": None}
    s = sorted(vals)
    total = sum(s)
    mean = total / n
    if n > 1:
        var = sum((x - mean) ** 2 for x in s) / n
        std = math.sqrt(var)
    else:
        std = 0.0
    return {
        "count": n,
        "sum": round(total, 2),
        "mean": round(mean, 2),
        "median": round(_percentile(s, 50), 2),
        "min": round(s[0], 2),
        "max": round(s[-1], 2),
        "std": round(std, 2),
        "p20": round(_percentile(s, 20), 2),
        "p80": round(_percentile(s, 80), 2),
    }


def _distinct_over_all(rows, col):
    """True distinct count of col over all provided rows."""
    return len(set(str(r.get(col)) for r in rows if r.get(col) not in (None, "")))


def _pick_measure(rows, number_cols):
    """Primary numeric column = non-identifier numeric col with largest absolute sum."""
    best = None
    best_abs = -1.0
    candidates = [c for c in number_cols if not _ID_PAT.search(c)] or list(number_cols)
    for c in candidates:
        vals = _numeric_values(rows, c)
        a = abs(sum(vals))
        if a > best_abs:
            best_abs = a
            best = c
    return best


def _histogram(vals, buckets=10):
    """Distribution buckets for numeric values, as bar chart data."""
    if not vals:
        return []
    lo = min(vals)
    hi = max(vals)
    if lo == hi:
        return [{"name": f"{round(lo, 2)}", "value": len(vals)}]
    width = (hi - lo) / buckets
    edges = [lo + i * width for i in range(buckets + 1)]
    counts = [0] * buckets
    for v in vals:
        idx = int((v - lo) / width)
        if idx >= buckets:
            idx = buckets - 1
        if idx < 0:
            idx = 0
        counts[idx] += 1
    data = []
    for i in range(buckets):
        label = f"{round(edges[i], 2)}–{round(edges[i + 1], 2)}"
        data.append({"name": label, "value": counts[i]})
    return data


def _pareto(rows, text_col, num_col, top=15):
    """Pareto data: top groups by summed measure with cumulative_pct."""
    pairs = _sum_by_text(rows, text_col, num_col, top=10 ** 9)
    total = sum(p["value"] for p in pairs)
    if total <= 0:
        return [], 0.0
    cum = 0.0
    out = []
    for p in pairs[:top]:
        cum += p["value"]
        out.append({
            "name": p["name"],
            "value": p["value"],
            "cumulative_pct": round(cum / total * 100.0, 2),
        })
    # share of total measure from top 20% of distinct groups
    n_groups = len(pairs)
    top20_n = max(1, int(round(n_groups * 0.2)))
    top20_sum = sum(p["value"] for p in pairs[:top20_n])
    top20_pct = round(top20_sum / total * 100.0, 2)
    return out, top20_pct


def _breakdown_table(rows, text_col, num_col, top=20):
    """Full breakdown rows by text_col: [name, value, share_pct]."""
    pairs = _sum_by_text(rows, text_col, num_col, top=10 ** 9)
    total = sum(p["value"] for p in pairs)
    out = []
    for p in pairs[:top]:
        share = round(p["value"] / total * 100.0, 2) if total > 0 else 0.0
        out.append([p["name"], p["value"], share])
    return out, total


def _cross_pivot(rows, row_dim, col_dim, num_col, top_rows=10, top_cols=8):
    """Cross-tab: sum num_col by row_dim x col_dim. Returns {rows, columns, cells}."""
    if not row_dim or not col_dim:
        return None
    measure_mode = num_col is not None
    agg: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    row_tot: Dict[str, float] = defaultdict(float)
    col_tot: Dict[str, float] = defaultdict(float)
    for r in rows:
        rk = r.get(row_dim)
        ck = r.get(col_dim)
        if rk in (None, "") or ck in (None, ""):
            continue
        if measure_mode:
            val = _to_number(r.get(num_col))
            if val is None:
                continue
        else:
            val = 1.0
        rk, ck = str(rk), str(ck)
        agg[rk][ck] += val
        row_tot[rk] += val
        col_tot[ck] += val
    if not agg:
        return None
    row_keys = [k for k, _ in sorted(row_tot.items(), key=lambda kv: kv[1], reverse=True)[:top_rows]]
    col_keys = [k for k, _ in sorted(col_tot.items(), key=lambda kv: kv[1], reverse=True)[:top_cols]]
    cells = []
    for rk in row_keys:
        cells.append([round(agg[rk].get(ck, 0.0), 2) for ck in col_keys])
    return {"row_dim": row_dim, "col_dim": col_dim,
            "rows": row_keys, "columns": col_keys, "cells": cells}


def _build_one(sheet: Dict[str, Any], max_rows: int) -> Dict[str, Any]:
    rows = sheet.get("rows_raw") or []
    headers = list(rows[0].keys()) if rows else (sheet.get("headers") or [])
    cols = _infer_columns(rows, headers)
    by_type: Dict[str, List[str]] = defaultdict(list)
    for c in cols:
        by_type[c["type"]].append(c["name"])

    data_rows = [r for r in rows if not _is_subtotal(r, headers)]

    number_cols = by_type["number"]
    cat_cols = by_type["category"]
    text_cols = by_type["text"]

    # ---- Role detection (generic) ----
    measure = _pick_measure(data_rows, number_cols) if number_cols else None
    # text columns ranked by distinct (highest cardinality first) = "items".
    # Prefer non-identifier text cols (exclude code/id/no/serial/... like the measure).
    _non_id_text = [c for c in text_cols if not _ID_PAT.search(c)]
    _ranked_pool = _non_id_text if _non_id_text else text_cols
    text_ranked = sorted(
        _ranked_pool,
        key=lambda c: _distinct_over_all(data_rows, c),
        reverse=True,
    )
    item_dim = text_ranked[0] if text_ranked else None
    secondary_text_dim = text_ranked[1] if len(text_ranked) > 1 else None

    # ===================== EXISTING KPIs (unchanged) =====================
    kpis = [{"label": "Rows", "value": len(data_rows)}]
    for num_col in number_cols[:3]:
        total = sum(_to_number(r.get(num_col)) or 0 for r in data_rows)
        kpis.append({"label": f"Σ {num_col}", "value": round(total, 2)})
    if cat_cols:
        kpis.append({"label": f"{cat_cols[0]} types",
                     "value": next((c["distinct"] for c in cols if c["name"] == cat_cols[0]), 0)})
    if text_cols:
        text_col = text_cols[0]
        distinct_count = len(set(
            str(r.get(text_col)) for r in data_rows if r.get(text_col) not in (None, "")
        ))
        kpis.append({"label": f"{text_col} (distinct)", "value": distinct_count})

    # ===================== EXISTING charts (unchanged) =====================
    charts = []
    for cat in cat_cols[:3]:
        charts.append({"type": "bar", "title": f"Count by {cat}", "x": "name", "y": "value",
                       "data": _counts(data_rows, cat)})
    if cat_cols and number_cols:
        cat, num = cat_cols[0], number_cols[0]
        charts.append({"type": "bar", "title": f"{num} by {cat}", "x": "name", "y": "value",
                       "data": _sum_by(data_rows, cat, num)})
    if text_cols:
        text_col = text_cols[0]
        if number_cols:
            num_col = number_cols[0]
            chart_data = _sum_by_text(data_rows, text_col, num_col, top=10)
            title = f"Top 10 {text_col} by {num_col}"
        else:
            chart_data = _count_by_text(data_rows, text_col, top=10)
            title = f"Top 10 {text_col} by count"
        if chart_data:
            charts.append({"type": "bar", "title": title, "x": "name", "y": "value",
                           "data": chart_data})

    # ===================== NEW: BI payload (additive) =====================
    measure_vals = _numeric_values(data_rows, measure) if measure else []
    measure_stats = _stats(measure_vals) if measure else None

    # bi_kpis
    bi_kpis: List[Dict[str, Any]] = []
    if measure and measure_stats and measure_stats["count"] > 0:
        zero_blank = sum(1 for r in data_rows
                         if _to_number(r.get(measure)) in (None, 0.0))
        bi_kpis.extend([
            {"label": f"Total {measure}", "value": measure_stats["sum"]},
            {"label": f"Average {measure}", "value": measure_stats["mean"]},
            {"label": f"Median {measure}", "value": measure_stats["median"]},
            {"label": f"Largest {measure}", "value": measure_stats["max"]},
            {"label": f"Smallest {measure}", "value": measure_stats["min"]},
            {"label": f"Std Dev {measure}", "value": measure_stats["std"]},
            {"label": f"P80 {measure}", "value": measure_stats["p80"]},
            {"label": f"P20 {measure}", "value": measure_stats["p20"]},
            {"label": f"Zero/Blank {measure}", "value": zero_blank},
        ])
    for c in cat_cols:
        bi_kpis.append({"label": f"{c} (distinct)", "value": _distinct_over_all(data_rows, c)})
    for c in text_cols:
        bi_kpis.append({"label": f"{c} (distinct)", "value": _distinct_over_all(data_rows, c)})

    # numeric_profiles
    numeric_profiles = []
    for c in number_cols:
        vals = _numeric_values(data_rows, c)
        st = _stats(vals)
        zero_count = sum(1 for v in vals if v == 0.0)
        blank_count = sum(1 for r in data_rows if _to_number(r.get(c)) is None)
        numeric_profiles.append({
            "column": c,
            "count": st["count"], "sum": st["sum"], "mean": st["mean"],
            "median": st["median"], "min": st["min"], "max": st["max"],
            "std": st["std"], "p20": st["p20"], "p80": st["p80"],
            "zero_count": zero_count, "blank_count": blank_count,
        })

    # extra_charts
    extra_charts: List[Dict[str, Any]] = []
    if item_dim and measure:
        d = _sum_by_text(data_rows, item_dim, measure, top=10)
        if d:
            extra_charts.append({"type": "bar", "title": f"Top 10 {item_dim} by {measure}",
                                 "x": "name", "y": "value", "data": d})
    if secondary_text_dim and measure:
        d = _sum_by_text(data_rows, secondary_text_dim, measure, top=10)
        if d:
            extra_charts.append({"type": "bar", "title": f"Top 10 {secondary_text_dim} by {measure}",
                                 "x": "name", "y": "value", "data": d})
    if measure:
        for cat in cat_cols:
            d = _sum_by(data_rows, cat, measure)
            if d:
                extra_charts.append({"type": "bar", "title": f"{measure} by {cat}",
                                     "x": "name", "y": "value", "data": d})
        hist = _histogram(measure_vals)
        if hist:
            extra_charts.append({"type": "bar", "title": f"{measure} distribution",
                                 "x": "name", "y": "value", "data": hist})

    # signals + pareto
    signals: Dict[str, Any] = {}
    pareto_data: List[Dict[str, Any]] = []
    if item_dim and measure:
        pareto_data, top20_pct = _pareto(data_rows, item_dim, measure, top=15)
        if pareto_data:
            extra_charts.append({"type": "pareto", "title": f"Pareto: {item_dim} by {measure}",
                                 "x": "name", "y": "value", "data": pareto_data})
        signals["pareto_top20_pct"] = top20_pct
    if measure:
        total_cells = len(data_rows)
        blank_cells = sum(1 for r in data_rows if _to_number(r.get(measure)) is None)
        blank_pct = round(blank_cells / total_cells * 100.0, 2) if total_cells else 0.0
        signals["blank_pct"] = blank_pct
        signals["fill_pct"] = round(100.0 - blank_pct, 2)

    # elements (ordered render list: charts + tables)
    elements: List[Dict[str, Any]] = []
    for ch in extra_charts:
        elements.append(ch)
    if item_dim and measure:
        top20 = _sum_by_text(data_rows, item_dim, measure, top=20)
        if top20:
            elements.append({
                "type": "table",
                "title": f"Top 20 {item_dim} by {measure}",
                "columns": [item_dim, measure],
                "rows": [[p["name"], p["value"]] for p in top20],
            })
        breakdown, _tot = _breakdown_table(data_rows, item_dim, measure, top=50)
        if breakdown:
            elements.append({
                "type": "table",
                "title": f"{item_dim} breakdown by {measure}",
                "columns": [item_dim, measure, "share_pct"],
                "rows": breakdown,
            })

    # pivot_tables (cross-tabs)
    pivot_tables: List[Dict[str, Any]] = []
    if item_dim and cat_cols:
        ct = _cross_pivot(data_rows, item_dim, cat_cols[0], measure)
        if ct:
            pivot_tables.append(ct)
    if len(cat_cols) >= 2:
        ct = _cross_pivot(data_rows, cat_cols[0], cat_cols[1], measure)
        if ct:
            pivot_tables.append(ct)

    return {
        "label": sheet.get("label"),
        "name": sheet.get("name") or sheet.get("label"),
        "color": sheet.get("color", "blue"),
        "row_count": len(data_rows),
        "columns": cols,
        "kpis": kpis,
        "charts": charts,
        "rows": rows[:max_rows],
        "truncated": len(rows) > max_rows,
        # ---- additive BI payload ----
        "measure": measure,
        "item_dim": item_dim,
        "secondary_text_dim": secondary_text_dim,
        "bi_kpis": bi_kpis,
        "numeric_profiles": numeric_profiles,
        "extra_charts": extra_charts,
        "elements": elements,
        "pivot_tables": pivot_tables,
        "signals": signals,
    }


def build_data_dashboard(sheets: List[Dict[str, Any]], max_rows: int = 500) -> Dict[str, Any]:
    return {"sheets": [_build_one(s, max_rows) for s in sheets]}
