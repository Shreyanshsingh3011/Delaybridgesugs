$ cat /home/user/Delaybridgesugs/frontend/backend/header_detector.py

"""Smart header-row detection for Google Sheets ingestion.

Given rows_raw (list of dicts keyed by whatever the Apps Script returned —
often column letters like A, B, K, M when the sheet has no first-row header),
find the best header row and return (resolved_headers, resolved_data_rows).
"""
import re
from typing import Any, Dict, List, Optional, Tuple

_LETTER_KEY = re.compile(r"^[A-Z]{1,3}$")
_INDEX_KEY = re.compile(r"^\d+$")
_EXCEL_SERIAL = re.compile(r"^\d{5}$")  # 5-digit numbers likely Excel date serials


def _looks_like_positional_keys(keys: List[str]) -> bool:
    """Return True when the majority of dict keys look like column letters or indices."""
    if not keys:
        return False
    positional = sum(1 for k in keys if _LETTER_KEY.match(str(k)) or _INDEX_KEY.match(str(k)))
    return positional / len(keys) > 0.5


def _is_numeric(val: Any) -> bool:
    try:
        float(str(val).replace(",", "").replace("%", ""))
        return True
    except (ValueError, TypeError):
        return False


def _is_excel_serial(val: Any) -> bool:
    """Return True for 5-digit integers in the range typical of Excel date serials (40000-60000)."""
    try:
        n = float(str(val).replace(",", ""))
        return 40000 <= n <= 60000 and n == int(n)
    except (ValueError, TypeError):
        return False


def _score_as_header(values: List[Any], data_rows_below: List[List[Any]]) -> float:
    """Score a row as a potential header (0.0 – 1.0+). Higher = better header candidate."""
    if not values:
        return 0.0
    n = len(values)
    non_empty = [v for v in values if str(v).strip()]
    if not non_empty:
        return 0.0

    fill_ratio = len(non_empty) / n
    # Excel date serials count as numeric for header scoring purposes
    text_ratio = sum(1 for v in non_empty if not _is_numeric(v)) / len(non_empty)
    unique_ratio = len({str(v).strip().lower() for v in non_empty}) / len(non_empty)

    # Strong penalty: if most non-empty values are Excel serials, this is a data row not a header
    serial_ratio = sum(1 for v in non_empty if _is_excel_serial(v)) / len(non_empty)
    if serial_ratio > 0.3:
        return 0.0

    # Bonus: data below is more numeric/serial than this row (header precedes data)
    data_bonus = 0.0
    if data_rows_below:
        flat_data = [v for row in data_rows_below[:5] for v in row if str(v).strip()]
        if flat_data:
            data_numeric = sum(1 for v in flat_data if _is_numeric(v)) / len(flat_data)
            row_numeric = sum(1 for v in non_empty if _is_numeric(v)) / len(non_empty)
            data_bonus = max(0.0, data_numeric - row_numeric) * 1.5  # amplify this signal

    # Extra bonus for short, readable, unique text values (hallmarks of real headers)
    readability_bonus = 0.0
    if text_ratio > 0.7 and unique_ratio > 0.8:
        avg_len = sum(len(str(v).strip()) for v in non_empty) / len(non_empty)
        if 2 <= avg_len <= 40:
            readability_bonus = 0.15

    score = fill_ratio * 0.20 + text_ratio * 0.30 + unique_ratio * 0.20 + data_bonus * 0.20 + readability_bonus
    return score


def _remap_rows(
    rows: List[Dict[str, Any]],
    old_keys: List[str],
    new_keys: List[str],
) -> List[Dict[str, Any]]:
    """Rebuild row dicts replacing old_keys with new_keys positionally."""
    key_map = dict(zip(old_keys, new_keys))
    result = []
    for row in rows:
        new_row: Dict[str, Any] = {}
        for k, v in row.items():
            new_row[key_map.get(str(k), str(k))] = v
        result.append(new_row)
    return result


def detect_header_row(rows_raw: List[Dict[str, Any]], max_scan: int = 12) -> Tuple[int, float]:
    """Return (best_row_index, best_score) by scoring rows as header candidates.
    Returns (0, 0.0) if rows_raw is empty."""
    if not rows_raw:
        return 0, 0.0
    candidates = rows_raw[:max_scan]
    best_score = -1.0
    best_idx = 0
    for i, row in enumerate(candidates):
        values = list(row.values())
        below = [list(r.values()) for r in candidates[i + 1: i + 6]]
        score = _score_as_header(values, below)
        if score > best_score:
            best_score = score
            best_idx = i
    return best_idx, best_score


def resolve_headers(
    rows_raw: List[Dict[str, Any]],
    header_mapping: Optional[Dict[str, Any]] = None,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Determine the real column headers for a sheet and return
    (resolved_headers, resolved_data_rows).

    header_mapping (from dbridge_header_mappings) may contain:
      - header_row_index: int  → use that exact row as headers (MODE A)
      - by_index: bool         → name columns by position (MODE B)
      - column_overrides: dict → rename {detected_name: real_name} (MODE A) or
                                 {"<pos_index>": "<name>"} (MODE B)
      - drop_empty_named: bool → drop columns where header cell was blank (MODE A)
      - keep_only_mapped: bool → drop unmapped columns (MODE B)
    """
    if not rows_raw:
        return [], []

    existing_keys = [str(k) for k in rows_raw[0].keys()]

    # ── USER OVERRIDE ──────────────────────────────────────────────────────
    if header_mapping:
        overrides: Dict[str, str] = header_mapping.get("column_overrides") or {}

        # MODE B: position-based column naming
        if header_mapping.get("by_index"):
            keep_only = header_mapping.get("keep_only_mapped", False)
            kept_old: List[str] = []
            new_names: List[str] = []
            for i, k in enumerate(existing_keys):
                name = overrides.get(str(i)) or overrides.get(k)
                if name:
                    kept_old.append(k)
                    new_names.append(name)
                elif not keep_only:
                    kept_old.append(k)
                    new_names.append(f"Column {i + 1}")
            filtered = [{k: r.get(k) for k in kept_old} for r in rows_raw]
            return new_names, _remap_rows(filtered, kept_old, new_names)

        # MODE A: header_row_index
        hri = header_mapping.get("header_row_index")
        drop_empty = header_mapping.get("drop_empty_named", False)

        if hri is not None and isinstance(hri, int) and 0 <= hri < len(rows_raw):
            raw_header_vals = list(rows_raw[hri].values())
            data_rows = rows_raw[hri + 1:]
        else:
            raw_header_vals = existing_keys
            data_rows = rows_raw

        # Build (index, raw_name) pairs, respecting drop_empty_named
        kept_pairs: List[Tuple[int, str]] = []
        for i, v in enumerate(raw_header_vals):
            cell = str(v).strip()
            raw_name = cell if cell else f"Column {i + 1}"
            is_empty_generated = not cell
            if drop_empty and is_empty_generated and not overrides.get(raw_name):
                continue
            kept_pairs.append((i, raw_name))

        kept_indices = [p[0] for p in kept_pairs]
        raw_headers = [p[1] for p in kept_pairs]
        headers = [overrides.get(h, h) for h in raw_headers]

        # Filter rows to kept columns then remap
        old_keys_kept = [existing_keys[i] for i in kept_indices if i < len(existing_keys)]
        filtered = [{k: r.get(k) for k in old_keys_kept} for r in data_rows]
        resolved = _remap_rows(filtered, old_keys_kept, headers)
        return headers, resolved

    # ── AUTO-DETECTION ─────────────────────────────────────────────────────
    if not _looks_like_positional_keys(existing_keys):
        # Keys are already real names (normal case); nothing to do.
        return existing_keys, list(rows_raw)

    # Keys are column letters/indices — scan first 15 rows for the best header.
    candidates = rows_raw[:15]
    best_score = -1.0
    best_idx = 0
    for i, row in enumerate(candidates):
        values = list(row.values())
        below = [list(r.values()) for r in candidates[i + 1: i + 6]]
        score = _score_as_header(values, below)
        if score > best_score:
            best_score = score
            best_idx = i

    if best_score < 0.35:
        # No convincing header found — use "Column N" labels.
        fallback = [f"Column {i + 1}" for i in range(len(existing_keys))]
        return fallback, _remap_rows(rows_raw, existing_keys, fallback)

    raw_header_vals = list(rows_raw[best_idx].values())
    headers = [
        str(v).strip() if str(v).strip() else f"Column {i + 1}"
        for i, v in enumerate(raw_header_vals)
    ]
    data_rows = rows_raw[best_idx + 1:]
    return headers, _remap_rows(data_rows, existing_keys, headers)
