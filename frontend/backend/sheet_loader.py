"""Shared sheet loader and type-KPI evaluator.

Imports ONLY from stdlib and local helpers (header_detector, sheet_cleaner, supadb).
Never imports from routes_public or routes_admin to avoid circular imports.
Every public function is wrapped in try/except and falls back gracefully.
"""
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from header_detector import resolve_headers
from sheet_cleaner import clean_sheet, _is_excel_serial, _serial_to_iso

logger = logging.getLogger(__name__)

# ── Date helpers ─────────────────────────────────────────────────────────────

_DATE_TOKEN_RE = re.compile(
    r"^Date\s*\(\s*(\d{4})\s*,\s*(\d{1,2})\s*,\s*(\d{1,2})\s*\)$", re.IGNORECASE
)
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_SKIP_DESCRIPTIONS = {"total", "sub total", "subtotal", "grand total"}


def _parse_date(val: Any) -> Optional[date]:
    """Parse Date(y,m,d), Excel serial, or ISO string → date. Returns None on failure."""
    if val is None:
        return None
    s = str(val).strip()
    m = _DATE_TOKEN_RE.match(s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    if _is_excel_serial(val):
        try:
            iso = _serial_to_iso(val)
            return date.fromisoformat(iso[:10])
        except Exception:
            return None
    if _ISO_RE.match(s):
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None
    return None


def _coerce_float(val: Any) -> Optional[float]:
    try:
        return float(str(val).replace(",", "").replace("%", "").strip())
    except (ValueError, TypeError):
        return None


def _is_skip_row(row: Dict[str, Any], headers: List[str]) -> bool:
    """Skip subtotal/grand-total rows by checking the first cell."""
    if not headers:
        return False
    first = str(row.get(headers[0], "")).strip().lower()
    return first in _SKIP_DESCRIPTIONS


# ── Core loader ──────────────────────────────────────────────────────────────

async def load_clean_sheet(db, token: str, sheet: Dict[str, Any]) -> Dict[str, Any]:
    """Apply header mapping + cleaning to one sheet dict (as stored in session).

    Returns a copy of the sheet with rows_raw, headers, columns, sheet_type updated.
    Falls back to the original sheet on any error.
    """
    orig = sheet
    try:
        label = sheet.get("label", "")
        hm = None
        try:
            hm_rows = await db.raw_select("dbridge_header_mappings", {"token": token, "sheet_label": label})
            if hm_rows:
                hm = hm_rows[0]
        except Exception as e:
            logger.warning("load_clean_sheet: header mapping fetch failed for %r: %s", label, e)

        s = dict(sheet)
        rows_raw = s.get("rows_raw") or []
        protected = set((hm or {}).get("column_overrides", {}).values()) if hm else set()
        headers, resolved_rows = resolve_headers(rows_raw, hm)
        headers, resolved_rows, n_pruned = clean_sheet(headers, resolved_rows, protected)
        s["rows_raw"] = resolved_rows
        s["headers"] = headers
        s["columns"] = len(headers)
        s["pruned_empty_columns"] = n_pruned
        if hm and hm.get("sheet_type"):
            s["sheet_type"] = hm["sheet_type"]
        return s
    except Exception as e:
        logger.warning("load_clean_sheet: failed for sheet %r, using raw: %s",
                       orig.get("label"), e)
        return orig


async def load_clean_sheets(db, token: str, sheets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Clean all sheets in a list. Each sheet falls back independently on error."""
    result = []
    for s in sheets:
        result.append(await load_clean_sheet(db, token, s))
    return result


# ── Type-KPI evaluator ───────────────────────────────────────────────────────

def _resolve_columns(headers: List[str], match_columns: Dict[str, List[str]]) -> Dict[str, str]:
    """Map logical keys like '@status' to the first real column whose name matches any alias."""
    resolved: Dict[str, str] = {}
    headers_lower = {h.lower(): h for h in headers}
    for logical, aliases in match_columns.items():
        for alias in aliases:
            alias_l = alias.lower()
            # exact match first
            if alias_l in headers_lower:
                resolved[logical] = headers_lower[alias_l]
                break
            # substring match
            for hl, h in headers_lower.items():
                if alias_l in hl:
                    resolved[logical] = h
                    break
            if logical in resolved:
                break
    return resolved


def _eval_kpi(kpi: Dict[str, Any], rows: List[Dict[str, Any]],
              col_map: Dict[str, str], headers: List[str]) -> Optional[Any]:
    """Evaluate one KPI definition. Returns the value or None if it can't be computed."""
    agg = kpi.get("aggregation", "")
    col_ref = kpi.get("column")  # e.g. "@status" or a literal column name
    col = col_map.get(col_ref, col_ref) if col_ref else None

    # Verify required column exists
    if col and col not in headers:
        return None

    today = date.today()

    try:
        if agg == "count":
            return sum(1 for r in rows if not _is_skip_row(r, headers))

        elif agg == "count_where":
            values = [str(v).lower() for v in (kpi.get("value") or [])]
            if not col or not values:
                return None
            return sum(1 for r in rows
                       if not _is_skip_row(r, headers)
                       and str(r.get(col, "")).lower() in values)

        elif agg == "count_where_numeric":
            op = kpi.get("op", "==")
            threshold = kpi.get("value")
            if not col or threshold is None:
                return None
            ops = {"<": float.__lt__, ">": float.__gt__, "==": float.__eq__,
                   "<=": float.__le__, ">=": float.__ge__}
            fn = ops.get(op)
            if not fn:
                return None
            count = 0
            for r in rows:
                if _is_skip_row(r, headers):
                    continue
                v = _coerce_float(r.get(col))
                if v is not None and fn(v, float(threshold)):
                    count += 1
            return count

        elif agg == "count_where_blank":
            if not col:
                return None
            return sum(1 for r in rows
                       if not _is_skip_row(r, headers)
                       and not str(r.get(col, "")).strip())

        elif agg == "count_where_notblank":
            if not col:
                return None
            return sum(1 for r in rows
                       if not _is_skip_row(r, headers)
                       and str(r.get(col, "")).strip())

        elif agg == "sum":
            if not col:
                return None
            total = 0.0
            for r in rows:
                if _is_skip_row(r, headers):
                    continue
                v = _coerce_float(r.get(col))
                if v is not None:
                    total += v
            return total

        elif agg == "date_overdue":
            date_col_ref = kpi.get("date_column")
            status_col_ref = kpi.get("status_column")
            done_values = [str(v).lower() for v in (kpi.get("done_values") or [])]
            date_col = col_map.get(date_col_ref, date_col_ref) if date_col_ref else None
            status_col = col_map.get(status_col_ref, status_col_ref) if status_col_ref else None
            if not date_col or date_col not in headers:
                return None
            count = 0
            for r in rows:
                if _is_skip_row(r, headers):
                    continue
                d = _parse_date(r.get(date_col))
                if d is None or d >= today:
                    continue
                if status_col and status_col in r:
                    if str(r[status_col]).lower() in done_values:
                        continue
                count += 1
            return count

    except Exception as e:
        logger.warning("_eval_kpi: error evaluating %r: %s", kpi.get("label"), e)
        return None

    return None


async def compute_type_kpis(
    db, sheet: Dict[str, Any]
) -> Dict[str, Any]:
    """Compute type-specific KPIs for a (already-cleaned) sheet.

    Returns {"type_kpis": [...], "matched_columns": {...}, "skipped_kpis": [...]}.
    Falls back to empty on any error.
    """
    empty = {"type_kpis": [], "matched_columns": {}, "skipped_kpis": []}
    try:
        sheet_type = sheet.get("sheet_type")
        if not sheet_type:
            return empty

        # Load analysis_rules from dbridge_sheet_types
        rules = None
        try:
            type_rows = await db.raw_select("dbridge_sheet_types", {"id": sheet_type})
            if type_rows:
                rules = type_rows[0].get("analysis_rules") or {}
        except Exception as e:
            logger.warning("compute_type_kpis: failed to load sheet type %r: %s", sheet_type, e)
            return empty

        if not rules:
            return empty

        rows = sheet.get("rows_raw") or []
        headers = sheet.get("headers") or [k for k in (rows[0].keys() if rows else [])]
        match_columns = rules.get("match_columns") or {}
        kpi_defs = rules.get("kpis") or []

        col_map = _resolve_columns(headers, match_columns)

        type_kpis = []
        skipped = []
        for kpi in kpi_defs:
            val = _eval_kpi(kpi, rows, col_map, headers)
            if val is None:
                skipped.append(kpi.get("label", "?"))
            else:
                type_kpis.append({"label": kpi.get("label", ""), "value": val})

        return {"type_kpis": type_kpis, "matched_columns": col_map, "skipped_kpis": skipped}

    except Exception as e:
        logger.warning("compute_type_kpis: unexpected error: %s", e)
        return empty
