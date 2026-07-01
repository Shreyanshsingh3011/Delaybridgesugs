"""Universal, domain-agnostic analytics modules computed from raw sheet rows:
- Data-quality audit: missing values, duplicates, inconsistent category casing,
  subtotal/total rows, numeric type mismatches, and an overall score.
- Pivot/segmentation: group any dimension by an aggregate of any measure.
Pure-Python, no API key required.
"""
import re
import statistics
from typing import Any, Dict, List, Optional
from collections import Counter, defaultdict

from dashboards import _infer_columns, _to_number, _ID_PAT

_TOTAL_RE = re.compile(r"\b(sub\s*total|grand\s*total|total)\b", re.I)


def _norm_key(v):
    return re.sub(r"\s+", " ", str(v).strip().lower())


def _is_total_row(row):
    for v in row.values():
        if isinstance(v, str) and _TOTAL_RE.search(v):
            return True
    return False


# ── Generic, data-driven column-role inference (works for ANY sheet) ──────────
# Everything below is derived from the rows+columns themselves. A sheet-type may
# optionally supply `column_roles` to refine these guesses, but nothing here
# depends on a type existing.

def _nums(rows, col):
    out = []
    for r in rows:
        x = _to_number(r.get(col))
        if x is not None:
            out.append(x)
    return out


def _distinct(rows, col):
    return len(set(str(r.get(col)) for r in rows if r.get(col) not in (None, "")))


def _looks_serial(vals):
    """Values look like a row serial/index: mostly distinct integers packed into ~1..N."""
    nums = [v for v in (_to_number(x) for x in vals) if v is not None]
    if len(nums) < 5:
        return False
    ints = [n for n in nums if float(n).is_integer()]
    if len(ints) < 0.95 * len(nums):
        return False
    distinct = len(set(ints))
    if distinct >= 0.95 * len(ints):
        lo, hi = min(ints), max(ints)
        if lo >= 0 and (hi - lo + 1) <= 1.2 * len(ints):
            return True
    return False


def _is_identifier(name, vals):
    """A numeric column is an identifier if its NAME looks id-like or its VALUES look serial."""
    if _ID_PAT.search(str(name or "")):
        return True
    return _looks_serial(vals)


def _roles(sheet):
    r = sheet.get("column_roles") if isinstance(sheet, dict) else None
    return r if isinstance(r, dict) else {}


def _measure_cols(rows, cols, roles):
    """Real numeric measures: numeric columns minus identifiers (by name or serial values)."""
    numeric = [c["name"] for c in cols if c["type"] == "number"]
    ids = set(roles.get("identifiers") or [])
    sample = rows[:200]
    out = []
    for name in numeric:
        if name in ids:
            continue
        if _is_identifier(name, [r.get(name) for r in sample]):
            continue
        out.append(name)
    return out or numeric


def _dim_cols(rows, cols, roles):
    """Usable dimensions: categorical/text columns that aren't constant or unique-per-row."""
    cats = [c["name"] for c in cols if c["type"] in ("category", "text")]
    n = len(rows) or 1
    good = []
    for name in cats:
        d = _distinct(rows, name)
        if d <= 1 or d >= 0.9 * n:
            continue
        good.append(name)
    return good or cats


def _default_dimension(rows, cols, roles, headers):
    dd = roles.get("default_dimension")
    if dd and dd in headers:
        return dd
    for d in (roles.get("dimensions") or []):
        if d in headers:
            return d
    good = _dim_cols(rows, cols, roles)
    if good:
        return min(good, key=lambda c: _distinct(rows, c))
    return headers[0] if headers else None


def _default_measure(rows, roles, measures):
    dm = roles.get("default_measure")
    if dm and dm in measures:
        return dm
    qty = [c for c in (roles.get("quantity_columns") or []) if c in measures]
    rate = set(roles.get("rate_columns") or [])
    pool = qty or [m for m in measures if m not in rate] or measures
    best, best_abs = None, -1.0
    for c in pool:
        a = abs(sum(_nums(rows, c)))
        if a > best_abs:
            best_abs, best = a, c
    return best


def _quality_for_sheet(sheet):
    rows = sheet.get("rows_raw") or []
    headers = list(rows[0].keys()) if rows else (sheet.get("headers") or [])
    cols = _infer_columns(rows, headers)
    n = len(rows)
    issues = {}

    # Missing values per column
    missing = []
    for h in headers:
        m = sum(1 for r in rows if r.get(h) in (None, ""))
        if m:
            missing.append({"column": h, "missing": m, "pct": round(100 * m / n, 1) if n else 0})
    missing.sort(key=lambda x: -x["missing"])

    # Exact duplicate rows
    seen = set()
    dups = 0
    for r in rows:
        key = tuple(sorted((k, str(v)) for k, v in r.items()))
        if key in seen:
            dups += 1
        else:
            seen.add(key)

    # Inconsistent category casing/whitespace
    inconsistent = []
    for c in cols:
        if c["type"] not in ("category", "text"):
            continue
        groups = defaultdict(set)
        for r in rows:
            v = r.get(c["name"])
            if v in (None, ""):
                continue
            groups[_norm_key(v)].add(str(v))
        variants = {k: sorted(vs) for k, vs in groups.items() if len(vs) > 1}
        if variants:
            inconsistent.append({"column": c["name"],
                                 "groups": [{"normalized": k, "variants": v} for k, v in list(variants.items())[:10]]})

    # Subtotal / total rows
    total_rows = sum(1 for r in rows if _is_total_row(r))

    # Numeric type mismatches
    type_mismatch = []
    for c in cols:
        if c["type"] != "number":
            continue
        bad = sum(1 for r in rows if r.get(c["name"]) not in (None, "") and _to_number(r.get(c["name"])) is None)
        if bad:
            type_mismatch.append({"column": c["name"], "non_numeric": bad})

    issues = {
        "missing": missing,
        "duplicate_rows": dups,
        "inconsistent_categories": inconsistent,
        "total_subtotal_rows": total_rows,
        "type_mismatches": type_mismatch,
    }

    # Overall score (100 = clean). Penalize each issue class.
    avg_missing_pct = (sum(m["pct"] for m in missing) / len(missing)) if missing else 0
    penalty = min(40, avg_missing_pct * 0.3)
    penalty += min(20, (dups / n * 100) if n else 0)
    penalty += min(15, len(inconsistent) * 5)
    penalty += min(15, (total_rows / n * 100) if n else 0)
    penalty += min(10, len(type_mismatch) * 5)
    score = max(0, round(100 - penalty))

    return {"label": sheet.get("label"), "name": sheet.get("name") or sheet.get("label"),
            "row_count": n, "score": score, "issues": issues}


def build_data_quality(sheets: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"sheets": [_quality_for_sheet(s) for s in sheets]}


def _pick_sheet(sheets, label):
    if label:
        for s in sheets:
            if s.get("label") == label:
                return s
    return sheets[0] if sheets else None


def build_pivot(sheets: List[Dict[str, Any]], dimension: Optional[str] = None,
                measure: Optional[str] = None, agg: str = "sum",
                include_totals: bool = False, sheet_label: Optional[str] = None) -> Dict[str, Any]:
    sheet = _pick_sheet(sheets, sheet_label)
    if not sheet:
        return {"enabled": True, "error": "No sheet available"}
    rows = sheet.get("rows_raw") or []
    headers = list(rows[0].keys()) if rows else (sheet.get("headers") or [])
    cols = _infer_columns(rows, headers)
    roles = _roles(sheet)

    if not include_totals:
        rows = [r for r in rows if not _is_total_row(r)]

    dims = _dim_cols(rows, cols, roles)
    measures = _measure_cols(rows, cols, roles)  # excludes identifiers/serials like "Sr. No."

    dimension = dimension if dimension in headers else _default_dimension(rows, cols, roles, headers)
    if agg != "count":
        measure = measure if measure in measures else _default_measure(rows, roles, measures)
        if measure is None:
            agg = "count"

    buckets = defaultdict(list)
    for r in rows:
        key = r.get(dimension)
        if key in (None, ""):
            key = "(blank)"
        buckets[str(key)].append(r)

    out = []
    for key, group in buckets.items():
        if agg == "count":
            val = len(group)
        else:
            nums = [_to_number(r.get(measure)) for r in group]
            nums = [x for x in nums if x is not None]
            if agg == "avg":
                val = round(sum(nums) / len(nums), 2) if nums else 0
            else:  # sum
                val = round(sum(nums), 2)
        out.append({"key": key, "value": val, "rows": len(group)})
    out.sort(key=lambda x: -x["value"])
    total = round(sum(x["value"] for x in out), 2) if agg != "avg" else None

    return {
        "enabled": True,
        "sheet": sheet.get("label"),
        "dimension": dimension,
        "measure": measure if agg != "count" else None,
        "agg": agg,
        "include_totals": include_totals,
        "available_dimensions": dims,
        "available_measures": measures,
        "available_sheets": [s.get("label") for s in sheets],
        "data": out,
        "total": total,
    }


def build_anomalies(sheets: List[Dict[str, Any]], column: Optional[str] = None,
                    sensitivity: str = "medium", sheet_label: Optional[str] = None) -> Dict[str, Any]:
    """Outlier detection via robust modified z-score (median + MAD). Excludes total rows."""
    sheet = _pick_sheet(sheets, sheet_label)
    if not sheet:
        return {"enabled": True, "error": "No sheet available"}
    rows = [r for r in (sheet.get("rows_raw") or []) if not _is_total_row(r)]
    headers = list(rows[0].keys()) if rows else (sheet.get("headers") or [])
    cols = _infer_columns(rows, headers)
    roles = _roles(sheet)
    numeric_all = [c["name"] for c in cols if c["type"] == "number"]
    numeric = _measure_cols(rows, cols, roles)  # drop identifiers/serials (e.g. "Sr. No.")
    rate = set(roles.get("rate_columns") or [])
    scan = [n for n in numeric if n not in rate] or numeric  # rates are noisy across mixed items
    label_col = next((c["name"] for c in cols if c["type"] in ("category", "text")), None)
    thr = {"low": 5.0, "medium": 3.5, "high": 2.5}.get(sensitivity, 3.5)
    targets = [column] if column in numeric_all else scan

    anomalies = []
    for col in targets:
        vals, idxs = [], []
        for i, r in enumerate(rows):
            x = _to_number(r.get(col))
            if x is not None:
                vals.append(x)
                idxs.append(i)
        if len(vals) < 5:
            continue
        med = statistics.median(vals)
        mad = statistics.median([abs(v - med) for v in vals])
        if mad > 0:
            scores = [0.6745 * (v - med) / mad for v in vals]
        else:
            sd = statistics.pstdev(vals)
            if sd == 0:
                continue
            scores = [(v - med) / sd for v in vals]
        for v, sc, i in zip(vals, scores, idxs):
            if abs(sc) >= thr:
                r = rows[i]
                anomalies.append({
                    "column": col, "value": round(v, 2), "score": round(sc, 2),
                    "direction": "high" if sc > 0 else "low",
                    "label": str(r.get(label_col)) if label_col else f"row {i + 1}",
                })
    anomalies.sort(key=lambda a: -abs(a["score"]))
    return {
        "enabled": True, "sheet": sheet.get("label"), "sensitivity": sensitivity,
        "available_columns": numeric, "available_sheets": [s.get("label") for s in sheets],
        "count": len(anomalies), "anomalies": anomalies[:100],
    }


def _fmt(n):
    try:
        return f"{round(float(n), 2):,}"
    except Exception:
        return str(n)


def build_digest(sheets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministic executive summary computed from the data (no API key needed)."""
    blocks = []
    flat = []
    for s in sheets:
        all_rows = s.get("rows_raw") or []
        rows = [r for r in all_rows if not _is_total_row(r)]
        headers = list(all_rows[0].keys()) if all_rows else (s.get("headers") or [])
        cols = _infer_columns(all_rows, headers)
        by_type = defaultdict(list)
        for c in cols:
            by_type[c["type"]].append(c["name"])
        hi = [f"{len(all_rows)} rows across {len(cols)} columns "
              f"({len(by_type['number'])} numeric, {len(by_type['category'])} categorical, {len(by_type['date'])} date)."]
        for col in by_type["number"][:2]:
            tot = sum(_to_number(r.get(col)) or 0 for r in rows)
            hi.append(f"Total {col} (line items only): {_fmt(tot)}.")
        if by_type["category"]:
            cat = by_type["category"][0]
            cnt = Counter(str(r.get(cat)) for r in rows if r.get(cat) not in (None, ""))
            if cnt:
                k, v = cnt.most_common(1)[0]
                hi.append(f"Most common {cat}: '{k}' ({v} rows).")
        q = _quality_for_sheet(s)
        extra = []
        if q["issues"]["total_subtotal_rows"]:
            extra.append(f"{q['issues']['total_subtotal_rows']} total/subtotal rows")
        if q["issues"]["inconsistent_categories"]:
            extra.append(f"{len(q['issues']['inconsistent_categories'])} columns with casing issues")
        hi.append(f"Data-quality score: {q['score']}/100" + (f" ({', '.join(extra)})." if extra else "."))
        an = build_anomalies([s])
        if an.get("count"):
            a0 = an["anomalies"][0]
            hi.append(f"{an['count']} outlier rows (largest: '{a0['label']}' = {_fmt(a0['value'])} in {a0['column']}).")
        blocks.append({"label": s.get("label"), "name": s.get("name") or s.get("label"), "highlights": hi})
        flat.extend(hi)
    return {"sheets": blocks, "facts": flat}


def build_recommendations(sheets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Rule-based next-best-actions derived from quality + anomaly signals (no API key)."""
    recs = []
    for s in sheets:
        q = _quality_for_sheet(s)
        i = q["issues"]
        if i["total_subtotal_rows"]:
            recs.append({"severity": "high", "title": "Exclude total/subtotal rows",
                         "detail": f"{i['total_subtotal_rows']} rows look like totals and inflate sums. "
                                   "Pivot/forecast already drop them; remove from source for clean dashboards."})
        for c in i["inconsistent_categories"]:
            ex = "; ".join(" / ".join(g["variants"][:2]) for g in c["groups"][:3])
            recs.append({"severity": "medium", "title": f"Normalize casing in '{c['column']}'",
                         "detail": f"Variants collapse to the same value: {ex}."})
        for m in i["missing"][:4]:
            if m["pct"] >= 20:
                recs.append({"severity": "high" if m["pct"] >= 50 else "medium",
                             "title": f"High missingness in '{m['column']}'",
                             "detail": f"{m['pct']}% of rows are empty ({m['missing']} rows)."})
        for t in i["type_mismatches"]:
            recs.append({"severity": "medium", "title": f"Non-numeric values in '{t['column']}'",
                         "detail": f"{t['non_numeric']} values aren't numbers and are excluded from sums."})
        an = build_anomalies([s])
        if an.get("count"):
            a0 = an["anomalies"][0]
            recs.append({"severity": "low", "title": f"Review {an['count']} outliers",
                         "detail": f"Largest: '{a0['label']}' = {_fmt(a0['value'])} in {a0['column']} (score {a0['score']})."})
        if q["score"] >= 90 and not recs:
            recs.append({"severity": "low", "title": "Data looks clean",
                         "detail": f"Quality score {q['score']}/100 with no major issues detected."})
    order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: order.get(r["severity"], 3))
    return {"recommendations": recs}


def build_whatif(sheets: List[Dict[str, Any]], dimension: Optional[str] = None,
                 measure: Optional[str] = None, adjustments: Optional[Dict[str, float]] = None,
                 global_pct: float = 0.0, sheet_label: Optional[str] = None) -> Dict[str, Any]:
    """Scenario modelling: baseline = sum(measure) per dimension; adjusted applies per-category
    and global % changes. Excludes total/subtotal rows."""
    sheet = _pick_sheet(sheets, sheet_label)
    if not sheet:
        return {"enabled": True, "error": "No sheet available"}
    rows = [r for r in (sheet.get("rows_raw") or []) if not _is_total_row(r)]
    headers = list(rows[0].keys()) if rows else (sheet.get("headers") or [])
    cols = _infer_columns(rows, headers)
    roles = _roles(sheet)
    dims = _dim_cols(rows, cols, roles)
    measures = _measure_cols(rows, cols, roles)  # excludes identifiers/serials
    dimension = dimension if dimension in headers else _default_dimension(rows, cols, roles, headers)
    measure = measure if measure in measures else _default_measure(rows, roles, measures)
    if not measure or not dimension:
        return {"enabled": True, "error": "Need a categorical dimension and a numeric measure.",
                "available_dimensions": dims, "available_measures": measures,
                "available_sheets": [s.get("label") for s in sheets]}
    base = defaultdict(float)
    for r in rows:
        k = r.get(dimension)
        m = _to_number(r.get(measure))
        if k in (None, "") or m is None:
            continue
        base[str(k)] += m
    adj = adjustments or {}
    baseline = [{"key": k, "value": round(v, 2)} for k, v in sorted(base.items(), key=lambda x: -x[1])]
    base_total = round(sum(base.values()), 2)
    adjusted = []
    for k, v in base.items():
        pct = adj.get(k, 0.0) + global_pct
        adjusted.append({"key": k, "value": round(v * (1 + pct / 100.0), 2)})
    adjusted.sort(key=lambda x: -x["value"])
    adj_total = round(sum(x["value"] for x in adjusted), 2)
    return {
        "enabled": True, "sheet": sheet.get("label"), "dimension": dimension, "measure": measure,
        "available_dimensions": dims, "available_measures": measures,
        "available_sheets": [s.get("label") for s in sheets],
        "baseline": baseline, "baseline_total": base_total,
        "adjusted": adjusted, "adjusted_total": adj_total,
        "delta": round(adj_total - base_total, 2),
        "delta_pct": round((adj_total - base_total) / base_total * 100, 2) if base_total else 0,
    }


def build_stock_views(sheets: List[Dict[str, Any]], sheet_label: Optional[str] = None) -> Dict[str, Any]:
    """Inventory-specific views (top consumers, low-balance items). Gated to sheets whose
    resolved type supplies column_roles (item_dimension + consumption/balance). For any
    sheet without those roles this returns enabled=False and renders nothing."""
    sheet = _pick_sheet(sheets, sheet_label)
    if not sheet:
        return {"enabled": False, "reason": "no sheet"}
    roles = _roles(sheet)
    rows_all = sheet.get("rows_raw") or []
    headers = sheet.get("headers") or (list(rows_all[0].keys()) if rows_all else [])
    headers = [h["name"] if isinstance(h, dict) else str(h) for h in headers]
    item_dim = roles.get("item_dimension")
    if not roles or not item_dim or item_dim not in headers:
        return {"enabled": False, "reason": "not an inventory-typed sheet"}

    rows = [r for r in rows_all if not _is_total_row(r)]

    def _rank(measure_col, reverse=True, limit=15):
        agg = defaultdict(float)
        for r in rows:
            k = r.get(item_dim)
            m = _to_number(r.get(measure_col))
            if k in (None, "") or m is None:
                continue
            agg[str(k)] += m
        ordered = sorted(agg.items(), key=lambda x: (-x[1] if reverse else x[1]))
        return [{"key": k, "value": round(v, 2)} for k, v in ordered[:limit]]

    out = {"enabled": True, "sheet": sheet.get("label"), "item_dimension": item_dim, "views": []}

    cons = roles.get("consumption_column")
    if cons and cons in headers:
        out["top_consumers"] = {"measure": cons, "data": _rank(cons, reverse=True)}
        out["views"].append("top_consumers")

    bal = next((b for b in (roles.get("balance_columns") or []) if b in headers), None)
    if bal:
        out["low_balance"] = {"measure": bal, "data": _rank(bal, reverse=False)}
        out["views"].append("low_balance")

    if not out["views"]:
        return {"enabled": False, "reason": "no consumption/balance columns present"}
    return out
