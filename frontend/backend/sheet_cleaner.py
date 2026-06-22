"""Post-header-resolution cleaning: date-serial conversion and empty-column pruning.

Called AFTER resolve_headers(), so column names are already real.
"""
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

_EXCEL_BASE = date(1899, 12, 30)

# Columns whose resolved header suggests they hold dates
_DATE_HEADER = re.compile(
    r"date|day|planned|actual|start|finish|due|deadline|schedule|begin|end|target",
    re.IGNORECASE,
)

# Headers that look like a bare Excel Date(...) token or a date serial label
_DATE_TOKEN = re.compile(r"^(date\s*\(|[A-Z][a-z]{2}-\d{2}|\d{5}$)", re.IGNORECASE)

# Minimum fill-rate to keep a column (5%)
_MIN_FILL_RATE = 0.05


def _is_excel_serial(val: Any) -> bool:
    try:
        n = float(str(val).replace(",", ""))
        return 40000 <= n <= 60000 and n == int(n)
    except (ValueError, TypeError):
        return False


def _serial_to_iso(serial: Any) -> str:
    try:
        n = int(float(str(serial)))
        d = _EXCEL_BASE + timedelta(days=n)
        return d.isoformat()
    except Exception:
        return str(serial)


def _is_date_column(header: str) -> bool:
    return bool(_DATE_HEADER.search(header) or _DATE_TOKEN.match(header.strip()))


def convert_date_serials(
    headers: List[str],
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert Excel date serials to ISO strings in columns with date-like headers."""
    date_cols = {h for h in headers if _is_date_column(h)}
    if not date_cols:
        return rows
    out = []
    for row in rows:
        new_row = dict(row)
        for col in date_cols:
            val = new_row.get(col)
            if val is not None and _is_excel_serial(val):
                new_row[col] = _serial_to_iso(val)
        out.append(new_row)
    return out


def prune_empty_columns(
    headers: List[str],
    rows: List[Dict[str, Any]],
    protected_cols: Optional[Set[str]] = None,
    min_fill_rate: float = _MIN_FILL_RATE,
) -> Tuple[List[str], List[Dict[str, Any]], int]:
    """
    Remove columns whose fill-rate across data rows is below min_fill_rate.
    Never removes columns in protected_cols (user's explicit overrides).
    Returns (kept_headers, pruned_rows, n_pruned).
    """
    if not rows:
        return headers, rows, 0
    protected = protected_cols or set()
    total = len(rows)

    keep: List[str] = []
    for h in headers:
        if h in protected:
            keep.append(h)
            continue
        filled = sum(1 for r in rows if str(r.get(h, "")).strip())
        if filled / total >= min_fill_rate:
            keep.append(h)

    n_pruned = len(headers) - len(keep)
    keep_set = set(keep)
    pruned_rows = [{k: v for k, v in r.items() if k in keep_set} for r in rows]
    return keep, pruned_rows, n_pruned


def clean_sheet(
    headers: List[str],
    rows: List[Dict[str, Any]],
    protected_cols: Optional[Set[str]] = None,
) -> Tuple[List[str], List[Dict[str, Any]], int]:
    """
    Full cleaning pipeline: date-serial conversion then empty-column pruning.
    Returns (final_headers, final_rows, n_pruned_columns).
    """
    rows = convert_date_serials(headers, rows)
    headers, rows, n_pruned = prune_empty_columns(headers, rows, protected_cols)
    return headers, rows, n_pruned
