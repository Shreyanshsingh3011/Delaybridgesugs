"""Fetch and validate Google Apps Script Web App URLs."""
import requests
import logging
from typing import Tuple, List, Dict, Any

logger = logging.getLogger(__name__)

ALLOWED_HOST_HINTS = ("script.google.com", "script.googleusercontent.com")


def fetch_apps_script(url: str, timeout: int = 25) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """
    Fetch an Apps Script Web App URL and validate it returns {status:"ok", data:[...]}.
    Returns (ok, message, rows).
    """
    if not url or not url.strip().startswith(("http://", "https://")):
        return False, "URL must start with http(s)://", []

    try:
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
    except requests.exceptions.Timeout:
        return False, "Request timed out reaching the Apps Script URL.", []
    except requests.exceptions.RequestException as e:
        return False, f"Could not reach URL: {e}", []

    if resp.status_code != 200:
        return False, f"URL returned HTTP {resp.status_code}.", []

    try:
        payload = resp.json()
    except ValueError:
        return (
            False,
            "This URL did not return valid JSON. Make sure your Apps Script is deployed as a Web App with Anyone access.",
            [],
        )

    if not isinstance(payload, dict):
        # Some sources return list directly; accept as data
        if isinstance(payload, list):
            return True, f"Fetched {len(payload)} rows.", payload
        return False, "Unexpected response shape.", []

    status_val = str(payload.get("status", "")).lower()
    data = payload.get("data")

    # Accept either {status: 'ok', data:[...]} or any dict containing data list
    if data is None:
        # Try to find a list-of-dicts field
        for k, v in payload.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                data = v
                break

    if not isinstance(data, list):
        return (
            False,
            "Response missing a 'data' array. Your Apps Script must return JSON like {status:'ok', data:[...]}",
            [],
        )

    # Normalize each row to dict
    rows: List[Dict[str, Any]] = []
    for r in data:
        if isinstance(r, dict):
            rows.append(r)

    if status_val and status_val != "ok":
        return False, f"Apps Script reported status='{status_val}'.", []

    return True, f"Connected — {len(rows)} rows fetched.", rows
