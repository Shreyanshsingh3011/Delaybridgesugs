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
    # Tolerate Indian grouping and surrounding quotes; strip ALL thousands commas.
    try:
        s = str(val).strip().strip('"').strip("'").strip().replace("%", "").replace(",", "")
        if s in ("", "-", "—", "–"):
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def _is_skip_row(row: Dict[str, Any], headers: List[str]) -> bool:
    """Skip subtotal/grand-total rows by checking the first cell."""
    if not headers:
        return False
    first = str(row.get(headers[0], "")).strip().lower()
    return first in _SKIP_DESCRIPTIONS


# ── Sheet-type detection ─────────────────────────────────────────────────────

_WS_RE = re.compile(r"\s+")


def _norm_name(v: Any) -> str:
    """Normalize a column name: lowercase, trim, collapse internal whitespace."""
    if isinstance(v, dict):
        v = v.get("name", "")
    return _WS_RE.sub(" ", str(v or "").strip().lower())


def score_sheet_type(headers: List[Any], sheet_types: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Score every non-generic type's signature_columns against the headers.

    Returns {"best": <id or None>, "score": float, "matched": int, "scores": {id: score}}.
    Match is case-insensitive exact-or-substring (signature found in a column name).
    Never divides by zero on empty signatures.
    """
    norm_headers = [h for h in (_norm_name(h) for h in (headers or [])) if h]
    scores: Dict[str, float] = {}
    best_id: Optional[str] = None
    best_score = 0.0
    best_matched = 0
    if not norm_headers:
        return {"best": None, "score": 0.0, "matched": 0, "scores": scores}

    for st in sheet_types or []:
        tid = st.get("id")
        if not tid or tid == "type_generic":
            continue
        sigs = st.get("signature_columns") or []
        if not sigs:
            continue
        matched = 0
        for sig in sigs:
            ns = _norm_name(sig)
            if not ns:
                continue
            if any(ns == h or ns in h for h in norm_headers):
                matched += 1
        score = matched / len(sigs)
        scores[tid] = round(score, 3)
        if score > best_score or (score == best_score and matched > best_matched):
            best_id, best_score, best_matched = tid, score, matched

    return {"best": best_id, "score": best_score, "matched": best_matched, "scores": scores}


async def detect_sheet_type(
    db, headers: List[Any], override_type: Optional[str] = None
) -> str:
    """Resolve a sheet's type id.

    Order: explicit override (when non-null) → signature auto-detection → 'type_generic'.
    Auto-detection picks the highest-scoring type; if best score < 0.4 OR fewer than
    2 signature columns matched, falls back to 'type_generic'. Never raises.
    """
    if override_type:
        return override_type
    try:
        sheet_types = await db.raw_select("dbridge_sheet_types") or []
        result = score_sheet_type(headers, sheet_types)
        if result["best"] and result["score"] >= 0.4 and result["matched"] >= 2:
            return result["best"]
        return "type_generic"
    except Exception as e:
        logger.warning("detect_sheet_type: failed, using generic: %s", e)
        return "type_generic"


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
        # Override first; otherwise auto-detect by signature; otherwise generic.
        override_type = hm.get("sheet_type") if hm else None
        s["sheet_type"] = await detect_sheet_type(db, headers, override_type)
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
            if alias_l in headers_lower:
                resolved[logical] = headers_lower[alias_l]
                break
            for hl, h in headers_lower.items():
                if alias_l in hl:
                    resolved[logical] = h
                    break
            if logical in resolved:
                break
    return resolved


def _resolve_col_ref(col_ref: Optional[str], col_map: Dict[str, str]) -> Optional[str]:
    """Look up a column reference like '@status' or 'status' in col_map.
    Tries: exact key, key without leading '@', lowercased variants."""
    if not col_ref:
        return None
    if col_ref in col_map:
        return col_map[col_ref]
    stripped = col_ref.lstrip("@")
    if stripped in col_map:
        return col_map[stripped]
    col_ref_l = col_ref.lower().lstrip("@")
    for k, v in col_map.items():
        if k.lower().lstrip("@") == col_ref_l:
            return v
    return col_ref


def _eval_kpi(kpi: Dict[str, Any], rows: List[Dict[str, Any]],
              col_map: Dict[str, str], headers: List[str]) -> Optional[Any]:
    """Evaluate one KPI definition. Returns the value or None if it can't be computed."""
    agg = kpi.get("agg", "")
    col_ref = kpi.get("column")
    col = _resolve_col_ref(col_ref, col_map) if col_ref else None

    if col_ref and col and col not in headers:
        return None
    if col_ref and not col:
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
                       and str(r.get(col, "")).strip().lower() in values)

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
            date_col = _resolve_col_ref(date_col_ref, col_map) if date_col_ref else None
            status_col = _resolve_col_ref(status_col_ref, col_map) if status_col_ref else None
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
    debug: Dict[str, Any] = {"reached_compute": True}
    try:
        sheet_type = sheet.get("sheet_type")
        debug["sheet_type"] = sheet_type
        if not sheet_type:
            debug["exit"] = "no sheet_type"
            empty["debug"] = debug
            return empty

        rules = None
        try:
            type_rows = await db.raw_select("dbridge_sheet_types", {"id": sheet_type})
            debug["type_rows_count"] = len(type_rows) if type_rows else 0
            if type_rows:
                rules = type_rows[0].get("analysis_rules") or {}
                debug["rules_keys"] = list(rules.keys()) if rules else []
        except Exception as e:
            debug["rules_fetch_error"] = f"{type(e).__name__}: {e}"
            logger.warning("compute_type_kpis: failed to load sheet type %r: %s", sheet_type, e)
            empty["debug"] = debug
            return empty

        if not rules:
            debug["exit"] = "rules empty"
            empty["debug"] = debug
            return empty

        rows = sheet.get("rows_raw") or []
        raw_headers = sheet.get("headers") or list(rows[0].keys() if rows else [])
        headers = [h["name"] if isinstance(h, dict) else str(h) for h in raw_headers]
        match_columns = rules.get("match_columns") or {}
        kpi_defs = rules.get("kpis") or []

        col_map = _resolve_columns(headers, match_columns)

        debug["row_count"] = len(rows)
        debug["headers"] = headers[:10]
        debug["col_map"] = col_map
        debug["kpi_count_input"] = len(kpi_defs)
        debug["per_kpi"] = []

        type_kpis = []
        skipped = []
        for kpi in kpi_defs:
            refs = [v for v in kpi.values() if isinstance(v, str) and v.startswith("@")]
            resolved_refs = [(r, _resolve_col_ref(r, col_map)) for r in refs]
            would_skip = refs and not all(rv in headers for _, rv in resolved_refs)
            kpi_debug = {
                "label": kpi.get("label", "?"),
                "agg": kpi.get("aggregation"),
                "refs": refs,
                "resolved": [{"ref": r, "resolved": rv, "in_headers": rv in headers} for r, rv in resolved_refs],
                "would_skip_because": ("ref not in headers" if would_skip else None),
            }
            if would_skip:
                skipped.append(kpi.get("label", "?"))
                kpi_debug["outcome"] = "skipped_pre"
                debug["per_kpi"].append(kpi_debug)
                continue
            try:
                val = _eval_kpi(kpi, rows, col_map, headers)
            except Exception as e:
                val = None
                kpi_debug["eval_error"] = f"{type(e).__name__}: {e}"
            if val is None:
                skipped.append(kpi.get("label", "?"))
                kpi_debug["outcome"] = "skipped_eval_none"
            else:
                type_kpis.append({"label": kpi.get("label", ""), "value": val})
                kpi_debug["outcome"] = f"ok:{val}"
            debug["per_kpi"].append(kpi_debug)

        return {"type_kpis": type_kpis, "matched_columns": col_map, "skipped_kpis": skipped, "debug": debug}

    except Exception as e:
        debug["outer_error"] = f"{type(e).__name__}: {e}"
        logger.warning("compute_type_kpis: unexpected error: %s", e)
        empty["debug"] = debug
        return empty
