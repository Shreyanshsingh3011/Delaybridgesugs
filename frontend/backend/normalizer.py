"""Normalize heterogeneous sheet rows into a standard schema."""
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from models import STANDARD_FIELDS

# Default detector — maps lowercased column name keywords to standard fields.
DETECT_PATTERNS = {
    "activity": [
        "process description", "activity name", "activity", "task", "task title",
        "process", "step", "stage of process", "stage description",
    ],
    "criticality": ["criticality", "critical", "priority"],
    "responsible_person": [
        "responsible person", "responsible", "owner", "assigned to", "team member",
        "assignee", "person",
    ],
    "responsible_email": [
        "responsible person email", "email", "responsible email", "person email", "owner email",
    ],
    "responsible_phone": [
        "responsible person phone", "phone", "responsible phone", "person phone", "mobile", "contact",
    ],
    "start_date": ["start date", "start", "begin date", "kickoff"],
    "tat": ["tat", "planned days", "planned duration", "target days", "planned"],
    "days_taken": ["days taken", "actual duration", "days used", "actual days", "elapsed", "actual"],
    "status": ["status", "current status", "progress", "state"],
    "reason": ["reason for delay", "reason", "delay reason", "cause", "remarks"],
    "dependency": [
        "project dependency", "dependency", "dependencies", "depends on", "blocked by", "predecessor",
    ],
    "stage": ["stage", "department", "stage of process", "phase", "section"],
}


def detect_columns(headers: List[str]) -> Dict[str, str]:
    """Return mapping of standard_field -> original column name for headers we can detect."""
    mapping: Dict[str, str] = {}
    lowered = {(h or "").strip().lower(): h for h in headers if h}
    used: set = set()
    for std, keys in DETECT_PATTERNS.items():
        for k in keys:
            for low, orig in lowered.items():
                if orig in used:
                    continue
                if low == k:
                    mapping[std] = orig
                    used.add(orig)
                    break
            if std in mapping:
                break
        if std in mapping:
            continue
        # partial contains match
        for k in keys:
            for low, orig in lowered.items():
                if orig in used:
                    continue
                if k in low:
                    mapping[std] = orig
                    used.add(orig)
                    break
            if std in mapping:
                break
    return mapping


def _to_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        s = str(v)
        m = re.search(r"-?\d+(\.\d+)?", s)
        if m:
            try:
                return float(m.group())
            except ValueError:
                return None
    return None


def _to_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _split_deps(v: Any) -> List[str]:
    s = _to_str(v)
    if not s:
        return []
    parts = re.split(r"[;,|\n/]+", s)
    return [p.strip() for p in parts if p.strip()]


def _norm_status(v: Any) -> str:
    s = _to_str(v).lower()
    if not s:
        return "Unknown"
    if "complete" in s or "done" in s:
        return "Completed"
    if "delay" in s or "overdue" in s or "late" in s:
        return "Delayed"
    if "progress" in s or "ongoing" in s or "wip" in s:
        return "In Progress"
    if "yet" in s or "not start" in s or "pending start" in s:
        return "Yet to Start"
    if "block" in s:
        return "Blocked"
    return s.title()


def normalize_rows(rows: List[Dict[str, Any]], mapping: Dict[str, str]) -> List[Dict[str, Any]]:
    """Apply column mapping to produce a list of standard-field row dicts."""
    out: List[Dict[str, Any]] = []
    for idx, raw in enumerate(rows):
        rec: Dict[str, Any] = {"_row_index": idx}
        for std in STANDARD_FIELDS:
            src = mapping.get(std)
            val = raw.get(src) if src else None
            if std in ("tat", "days_taken"):
                rec[std] = _to_float(val)
            elif std == "dependency":
                rec[std] = _split_deps(val)
            elif std == "status":
                rec[std] = _norm_status(val)
            elif std == "criticality":
                s = _to_str(val).lower()
                rec[std] = "Critical" if "critic" in s else ("Normal" if s else "Normal")
            else:
                rec[std] = _to_str(val)
        # Compute overdue
        tat = rec.get("tat")
        dt = rec.get("days_taken")
        if tat is not None and dt is not None:
            rec["overdue_days"] = max(0.0, dt - tat)
            rec["overrun_pct"] = ((dt - tat) / tat * 100.0) if tat > 0 else 0.0
        else:
            rec["overdue_days"] = 0.0
            rec["overrun_pct"] = 0.0
        out.append(rec)
    return out


def data_quality(rows: List[Dict[str, Any]], normalized: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(normalized)
    missing = {f: 0 for f in STANDARD_FIELDS}
    invalid_dates = 0
    for r in normalized:
        for f in STANDARD_FIELDS:
            v = r.get(f)
            if v is None or v == "" or (isinstance(v, list) and not v):
                missing[f] += 1
        sd = r.get("start_date")
        if sd:
            try:
                datetime.fromisoformat(str(sd).replace("Z", "+00:00"))
            except Exception:
                invalid_dates += 1
    return {
        "total_rows": total,
        "missing_per_field": missing,
        "invalid_dates": invalid_dates,
    }
