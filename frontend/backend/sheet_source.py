"""Direct Google Sheets ingestion — read the sheet's CSV export ourselves,
without depending on the external JS sheet2api proxy.

Pipeline:  fetch_google_sheet_csv() → csv_to_rows_raw() → (header_detector +
sheet_loader do the rest).  parse_number() handles Indian-grouped/quoted numbers
so downstream KPI sums are correct.

Self-contained: stdlib csv + requests only. Never imports routes_*."""
import csv
import io
import re
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (compatible; DelayBridge/1.0; +https://delaybridge.app)"
_SIGNIN_HINTS = ("sign in", "request access", "accounts.google.com", "you need access")

# (sheet_id, gid) → (epoch_fetched, rows_raw)
_CACHE: Dict[Tuple[str, str], Tuple[float, List[Dict[str, str]]]] = {}
_DEFAULT_TTL = 300  # seconds


# ── Number parsing ────────────────────────────────────────────────────────────

def parse_number(s: Any) -> Optional[float]:
    """Coerce a spreadsheet cell to float, tolerating Indian grouping and quotes.

    Examples: '2,08,13,53,972' → 2081353972.0, '"1,420"' → 1420.0,
    '1,265.000' → 1265.0, '-43,293,402' → -43293402.0.
    Empty / '-' / non-numeric → None.
    """
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).strip().strip('"').strip("'").strip()
    if t in ("", "-", "—", "–", "NA", "N/A", "n/a"):
        return None
    t = t.replace("%", "").strip()
    # Strip ALL thousands separators (commas) — keep decimal point and leading minus.
    t = t.replace(",", "")
    if not re.match(r"^-?\d*\.?\d+$", t):
        return None
    try:
        return float(t)
    except (ValueError, TypeError):
        return None


# ── Direct CSV fetch ──────────────────────────────────────────────────────────

class SheetAccessError(Exception):
    """Raised when the sheet is not publicly readable (private / sign-in wall)."""


def fetch_google_sheet_csv(sheet_id: str, gid: str = "0", timeout: int = 25) -> List[List[str]]:
    """Fetch a Google Sheet's CSV export as a list-of-lists, preserving empty cells.

    Raises SheetAccessError if the sheet is not publicly readable (Google serves
    an HTML sign-in / request-access page instead of CSV)."""
    if not sheet_id:
        raise SheetAccessError("No sheetId configured for this connector.")
    url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/export"
        f"?format=csv&gid={gid or '0'}"
    )
    try:
        resp = requests.get(
            url, timeout=timeout, allow_redirects=True,
            headers={"User-Agent": _UA, "Accept": "text/csv,*/*"},
        )
    except requests.exceptions.Timeout:
        raise SheetAccessError("Timed out reaching Google Sheets.")
    except requests.exceptions.RequestException as e:
        raise SheetAccessError(f"Could not reach Google Sheets: {e}")

    if resp.status_code != 200:
        raise SheetAccessError(
            "Sheet is not publicly readable — share it as 'Anyone with the link: "
            f"Viewer' or connect a Google account. (HTTP {resp.status_code})"
        )

    ctype = (resp.headers.get("content-type") or "").lower()
    body = resp.text or ""
    head = body[:2000].lower()
    looks_html = (
        "text/html" in ctype
        or "<html" in head
        or any(h in head for h in _SIGNIN_HINTS)
    )
    if looks_html:
        raise SheetAccessError(
            "Sheet is not publicly readable — share it as 'Anyone with the link: "
            "Viewer' or connect a Google account."
        )

    reader = csv.reader(io.StringIO(body))
    rows = [list(r) for r in reader]  # preserves empty cells
    return rows


# ── CSV → rows_raw (positional keys so header_detector can auto-detect) ────────

def _col_letter(i: int) -> str:
    s = ""
    i += 1
    while i > 0:
        i -= 1
        s = chr(65 + (i % 26)) + s
        i //= 26
    return s


def csv_to_rows_raw(rows: List[List[str]]) -> List[Dict[str, str]]:
    """Turn a list-of-lists into list-of-dicts keyed by column letters (A, B, …).

    Keying by column letters makes the keys *positional*, so resolve_headers'
    auto-detection kicks in and picks the real header row from the data."""
    if not rows:
        return []
    width = max((len(r) for r in rows), default=0)
    keys = [_col_letter(i) for i in range(width)]
    out: List[Dict[str, str]] = []
    for r in rows:
        padded = list(r) + [""] * (width - len(r))
        out.append({keys[i]: padded[i] for i in range(width)})
    return out


# ── High-level loader with TTL cache ──────────────────────────────────────────

def load_direct_sheet(
    sheet_id: str,
    gid: str = "0",
    ttl: int = _DEFAULT_TTL,
    force: bool = False,
) -> List[Dict[str, str]]:
    """Fetch + parse a sheet into rows_raw (positional dict rows), cached per
    (sheet_id, gid) for `ttl` seconds. Raises SheetAccessError on private sheets."""
    key = (sheet_id, gid or "0")
    now = time.time()
    if not force:
        cached = _CACHE.get(key)
        if cached and (now - cached[0]) < max(0, ttl):
            return cached[1]
    rows = fetch_google_sheet_csv(sheet_id, gid)
    rows_raw = csv_to_rows_raw(rows)
    _CACHE[key] = (now, rows_raw)
    return rows_raw


def clear_cache(sheet_id: Optional[str] = None, gid: Optional[str] = None) -> None:
    if sheet_id is None:
        _CACHE.clear()
        return
    _CACHE.pop((sheet_id, gid or "0"), None)
