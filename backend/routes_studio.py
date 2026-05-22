"""Dependency Resolver — Apps Script ingestion only. No persistence.
Strict HARD FILTER: returns only structural metadata (headers + rowIds),
never cell-level scalar values."""
import logging
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from sheet_fetcher import fetch_apps_script

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/studio")


class FetchRequest(BaseModel):
    url: str


def _row_id(idx: int, raw: Dict[str, Any]) -> str:
    # Prefer explicit id-like fields if present, else ordinal index.
    for k in ("id", "ID", "Id", "Sr. No.", "row_id", "uuid"):
        v = raw.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return f"r{idx}"


@router.post("/fetch")
async def studio_fetch(payload: FetchRequest, current=Depends(get_current_user)):
    """Fetch records from an Apps Script Web App URL.

    HARD FILTER: discards all cell-level scalar values. Returns only:
      - headers:    list of column labels (col namespace)
      - rowIds:     ordinal row identifiers (row index namespace)
      - rowCount:   convenience integer
    """
    ok, msg, rows = fetch_apps_script(payload.url)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    # Headers — preserve first-seen order across rows.
    headers: List[str] = []
    seen: set = set()
    for r in rows:
        if isinstance(r, dict):
            for k in r.keys():
                if k not in seen:
                    seen.add(k)
                    headers.append(str(k))

    row_ids: List[str] = []
    used: set = set()
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            continue
        rid = _row_id(i, r)
        # Disambiguate duplicates
        base = rid
        suffix = 1
        while rid in used:
            rid = f"{base}#{suffix}"
            suffix += 1
        used.add(rid)
        row_ids.append(rid)

    return {
        "headers": headers,
        "rowIds": row_ids,
        "rowCount": len(row_ids),
        "message": msg,
    }
