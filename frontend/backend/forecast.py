"""Forecasting module — projects a numeric measure over time with confidence bands.
Pure-Python (no numpy/pandas): parses a date column, aggregates the measure per period,
fits a least-squares linear trend, and projects forward with P80/P95 bands derived from
the residual spread. Degrades clearly when there's no usable date + measure."""
import math
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from collections import defaultdict

from dashboards import _infer_columns, _to_number

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _parse_date(v) -> Optional[date]:
    if v in (None, ""):
        return None
    s = str(v).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", s)
    if m:
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if c < 100:
            c += 2000
        # assume D/M/Y; fall back to M/D/Y if day>12
        d_, mo = (a, b) if a > 12 else (a, b)
        try:
            return date(c, b, a) if a <= 12 and b <= 12 else date(c, (b if a > 12 else a) if False else b, a)
        except ValueError:
            try:
                return date(c, a, b)
            except ValueError:
                return None
    m = re.match(r"^(\d{1,2})[ -]([A-Za-z]{3})[A-Za-z]*[ -](\d{2,4})", s)
    if m and m.group(2).lower() in _MONTHS:
        y = int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return date(y, _MONTHS[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            return None
    return None


def _period_key(d: date, gran: str) -> str:
    if gran == "month":
        return f"{d.year:04d}-{d.month:02d}"
    if gran == "week":
        iso = d.isocalendar()
        return f"{iso[0]:04d}-W{iso[1]:02d}"
    return d.isoformat()


def _next_label(last: date, i: int, gran: str) -> str:
    if gran == "month":
        m = last.month - 1 + i
        y = last.year + m // 12
        return f"{y:04d}-{(m % 12) + 1:02d}"
    if gran == "week":
        return _period_key(last + timedelta(weeks=i), "week")
    return (last + timedelta(days=i)).isoformat()


def _linfit(xs, ys):
    n = len(xs)
    sx, sy = sum(xs), sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0.0, sy / n
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    return slope, intercept


def build_forecast(sheets: List[Dict[str, Any]], periods: int = 6, date_col: Optional[str] = None,
                   measure_col: Optional[str] = None, granularity: Optional[str] = None,
                   sheet_label: Optional[str] = None) -> Dict[str, Any]:
    sheet = None
    for s in sheets:
        if not sheet_label or s.get("label") == sheet_label:
            sheet = s
            break
    if not sheet:
        return {"enabled": True, "error": "No sheet available"}
    rows = sheet.get("rows_raw") or []
    headers = list(rows[0].keys()) if rows else (sheet.get("headers") or [])
    cols = _infer_columns(rows, headers)
    date_cols = [c["name"] for c in cols if c["type"] == "date"]
    measures = [c["name"] for c in cols if c["type"] == "number"]

    date_col = date_col if date_col in headers else (date_cols[0] if date_cols else None)
    measure_col = measure_col if measure_col in measures else (measures[0] if measures else None)

    if not date_col:
        return {"enabled": True, "ready": False,
                "message": "Forecasting needs a date column. None detected in this sheet.",
                "available_dates": date_cols, "available_measures": measures,
                "available_sheets": [s.get("label") for s in sheets]}

    # collect (date, value)
    pairs = []
    for r in rows:
        d = _parse_date(r.get(date_col))
        if not d:
            continue
        v = _to_number(r.get(measure_col)) if measure_col else 1
        pairs.append((d, v if v is not None else 0))
    if len(pairs) < 3:
        return {"enabled": True, "ready": False,
                "message": "Not enough dated rows to forecast (need at least 3).",
                "available_dates": date_cols, "available_measures": measures}

    dmin, dmax = min(p[0] for p in pairs), max(p[0] for p in pairs)
    span = (dmax - dmin).days
    gran = granularity or ("month" if span > 365 else "week" if span > 90 else "day")

    agg = defaultdict(float)
    for d, v in pairs:
        agg[_period_key(d, gran)] += v
    series = sorted(agg.items())
    xs = list(range(len(series)))
    ys = [v for _, v in series]
    slope, intercept = _linfit(xs, ys)
    fitted = [intercept + slope * x for x in xs]
    n = len(xs)
    resid_std = math.sqrt(sum((y - f) ** 2 for y, f in zip(ys, fitted)) / (n - 2)) if n > 2 else 0.0
    clamp0 = min(ys) >= 0

    history = [{"period": p, "value": round(v, 2)} for (p, v) in series]
    forecast = []
    for i in range(1, periods + 1):
        x = n - 1 + i
        yhat = intercept + slope * x
        p80 = 1.2816 * resid_std
        p95 = 1.9600 * resid_std
        lo80, lo95 = yhat - p80, yhat - p95
        if clamp0:
            yhat = max(0, yhat); lo80 = max(0, lo80); lo95 = max(0, lo95)
        forecast.append({
            "period": _next_label(dmax, i, gran),
            "p50": round(yhat, 2),
            "p80_low": round(lo80, 2), "p80_high": round(yhat + p80, 2),
            "p95_low": round(lo95, 2), "p95_high": round(yhat + p95, 2),
        })

    return {
        "enabled": True, "ready": True,
        "sheet": sheet.get("label"),
        "date_col": date_col, "measure_col": measure_col or "(row count)",
        "granularity": gran, "periods": periods,
        "trend_per_period": round(slope, 3),
        "available_dates": date_cols, "available_measures": measures,
        "available_sheets": [s.get("label") for s in sheets],
        "history": history, "forecast": forecast,
    }
