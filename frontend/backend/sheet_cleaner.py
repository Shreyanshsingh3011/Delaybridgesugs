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


def _serial_to_iso(val: Any) -> str:
    n = int(float(str(val).replace(",", "")))
    return (_EXCEL_BASE + timedelta(days=n)).isoformat()


def convert_date_serials(
    headers: List[str],
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    date_cols = {
        h for h in headers
        if _DATE_HEADER.search(h) or _DATE_TOKEN.match(h)
    }
    if not date_cols:
        return rows
    out = []
    for row in rows:
        new_row = dict(row)
        for col in date_cols:
            v = row.get(col)
            if v is not None and _is_excel_serial(v):
                new_row[col] = _serial_to_iso(v)
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


def _rename_blank_headers(
    headers: List[str],
    rows: List[Dict[str, Any]],
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Replace blank/None/whitespace-only header names with content-inferred names.

    Naming rule per blank column:
      - If the column's values are predominantly numeric -> "Value"
      - Otherwise -> "Column {n}" (1-based position)
    Collision with an existing header -> append the position (e.g. "Value 2").
    Row dicts are rewritten so the new key replaces the old blank key.
    """
    _BLANK = {"none", ""}

    def _is_blank(h: str) -> bool:
        return str(h).strip().lower() in _BLANK

    if not any(_is_blank(h) for h in headers):
        return headers, rows

    existing_names = {h for h in headers if not _is_blank(h)}
    used: set = set(existing_names)

    def _unique(name: str, pos: int) -> str:
        if name not in used:
            return name
        candidate = f"{name} {pos}"
        while candidate in used:
            pos += 1
            candidate = f"{name} {pos}"
        return candidate

    sample = rows[:50]
    new_headers: List[str] = []
    renames: List[Tuple[str, str]] = []

    for i, h in enumerate(headers):
        if not _is_blank(h):
            new_headers.append(h)
            continue
        values = [r.get(h) for r in sample if r.get(h) is not None]
        numeric = sum(1 for v in values if isinstance(v, (int, float))
                      or (isinstance(v, str) and v.replace(".", "", 1).replace("-", "", 1).replace(",", "").strip().isdigit()))
        base = "Value" if values and numeric / len(values) >= 0.6 else f"Column {i + 1}"
        new_name = _unique(base, i + 1)
        used.add(new_name)
        new_headers.append(new_name)
        if h != new_name:
            renames.append((h, new_name))

    if not renames:
        return new_headers, rows

    rename_map = dict(renames)
    new_rows = [
        {rename_map.get(k, k): v for k, v in r.items()}
        for r in rows
    ]
    return new_headers, new_rows


def clean_sheet(
    headers: List[str],
    rows: List[Dict[str, Any]],
    protected_cols: Optional[Set[str]] = None,
) -> Tuple[List[str], List[Dict[str, Any]], int]:
    """
    Full cleaning pipeline: date-serial conversion then empty-column pruning.
    Returns (final_headers, final_rows, n_pruned_columns).
    """
    headers, rows = _rename_blank_headers(headers, rows)
    rows = convert_date_serials(headers, rows)
    headers, rows, n_pruned = prune_empty_columns(headers, rows, protected_cols)
    return headers, rows, n_pruned
