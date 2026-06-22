"""Smart header-row detection for Google Sheets ingestion.

Given rows_raw (list of dicts keyed by whatever the Apps Script returned —
often column letters like A, B, K, M when the sheet has no first-row header),
find the best header row and return (resolved_headers, resolved_data_rows).
"""
import re
from typing import Any, Dict, List, Optional, Tuple

_LETTER_KEY = re.compile(r"^[A-Z]{1,3}$")
_INDEX_KEY = re.compile(r"^\d+$")


def _looks_like_positional_keys(keys: List[str]) -> bool:
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


def _score_as_header(values: List[Any], data_rows_below: List[List[Any]]) -> float:
    if not values:
        return 0.0
    n = len(values)
    non_empty = [v for v in values if str(v).strip()]
    if not non_empty:
        return 0.0
    fill_ratio = len(non_empty) / n
    text_ratio = sum(1 for v in non_empty if not _is_numeric(v)) / len(non_empty)
    unique_ratio = len({str(v).strip().lower() for v in non_empty}) / len(non_empty)
    data_bonus = 0.0
    if data_rows_below:
        flat_data = [v for row in data_rows_below[:4] for v in row if str(v).strip()]
        if flat_data:
            data_numeric = sum(1 for v in flat_data if _is_numeric(v)) / len(flat_data)
            row_numeric = sum(1 for v in non_empty if _is_numeric(v)) / len(non_empty)
            data_bonus = max(0.0, data_numeric - row_numeric)
    return fill_ratio * 0.25 + text_ratio * 0.30 + unique_ratio * 0.25 + data_bonus * 0.20


def _remap_rows(
    rows: List[Dict[str, Any]],
    old_keys: List[str],
    new_keys: List[str],
) -> List[Dict[str, Any]]:
    key_map = dict(zip(old_keys, new_keys))
    result = []
    for row in rows:
        new_row: Dict[str, Any] = {}
        for k, v in row.items():
            new_row[key_map.get(str(k), str(k))] = v
        result.append(new_row)
    return result


def resolve_headers(
    rows_raw: List[Dict[str, Any]],
    header_mapping: Optional[Dict[str, Any]] = None,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    if not rows_raw:
        return [], []

    existing_keys = [str(k) for k in rows_raw[0].keys()]

    if header_mapping:
        hri = header_mapping.get("header_row_index")
        overrides: Dict[str, str] = header_mapping.get("column_overrides") or {}
        if hri is not None and isinstance(hri, int) and 0 <= hri < len(rows_raw):
            raw_header_vals = list(rows_raw[hri].values())
            raw_headers = [
                str(v).strip() if str(v).strip() else f"Column {i + 1}"
                for i, v in enumerate(raw_header_vals)
            ]
            data_rows = rows_raw[hri + 1:]
        else:
            raw_headers = existing_keys
            data_rows = rows_raw
        headers = [overrides.get(h, h) for h in raw_headers]
        resolved = _remap_rows(data_rows, existing_keys, headers)
        return headers, resolved

    if not _looks_like_positional_keys(existing_keys):
        return existing_keys, list(rows_raw)

    candidates = rows_raw[:12]
    best_score = -1.0
    best_idx = 0
    for i, row in enumerate(candidates):
        values = list(row.values())
        below = [list(r.values()) for r in candidates[i + 1: i + 5]]
        score = _score_as_header(values, below)
        if score > best_score:
            best_score = score
            best_idx = i

    if best_score < 0.35:
        fallback = [f"Column {i + 1}" for i in range(len(existing_keys))]
        return fallback, _remap_rows(rows_raw, existing_keys, fallback)

    raw_header_vals = list(rows_raw[best_idx].values())
    headers = [
        str(v).strip() if str(v).strip() else f"Column {i + 1}"
        for i, v in enumerate(raw_header_vals)
    ]
    data_rows = rows_raw[best_idx + 1:]
    return headers, _remap_rows(data_rows, existing_keys, headers)
