"""Dynamic owner/department extraction from sheet rows via column-name heuristics.

Sheets vary in column naming, so we detect the relevant columns by regex rather than
relying on a fixed mapping. Used to build a people/department directory for the
concerns workflow.
"""
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

OWNER_RE = re.compile(r"owner|resp|assign|engineer|in.?charge|person|by", re.I)
DEPT_RE = re.compile(r"dept|department|section|discipline|team|service group", re.I)
EMAIL_RE = re.compile(r"e.?mail", re.I)
STATUS_RE = re.compile(r"status|state|stage|progress", re.I)
DATE_RE = re.compile(r"date|due|target|plan|actual|completion", re.I)

_TOTAL_RE = re.compile(r"^\s*(grand\s+)?(sub[\s-]?)?total\s*$", re.I)


def column_map(columns: List[str]) -> Dict[str, Any]:
    """Detect owner/department/email/status/date columns from a list of header names."""
    m: Dict[str, Any] = {"owner": None, "dept": None, "email": None, "status": None, "date": None}
    for c in columns:
        if not isinstance(c, str):
            continue
        if m["owner"] is None and OWNER_RE.search(c):
            m["owner"] = c
        if m["dept"] is None and DEPT_RE.search(c):
            m["dept"] = c
        if m["email"] is None and EMAIL_RE.search(c):
            m["email"] = c
        if m["status"] is None and STATUS_RE.search(c):
            m["status"] = c
        if m["date"] is None and DATE_RE.search(c):
            m["date"] = c
    return m


def _is_blank_or_total(row: Dict[str, Any]) -> bool:
    vals = [v for v in row.values() if v not in (None, "")]
    if not vals:
        return True
    return any(_TOTAL_RE.match(str(v).strip()) for v in vals)


def extract_people(sheets: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Scan connected sheets and return (people, departments).

    Each person is {name, email, department, sheets, statuses}. Blank rows and
    Total/Sub Total/Grand Total rows are skipped.
    """
    people_by_key: Dict[str, Dict[str, Any]] = {}
    departments = set()

    for s in sheets:
        rows = s.get("rows_raw") or []
        headers = list(rows[0].keys()) if rows else (s.get("headers") or [])
        cmap = column_map(headers)
        owner_col, dept_col, email_col, status_col = (
            cmap["owner"], cmap["dept"], cmap["email"], cmap["status"],
        )
        if not owner_col and not dept_col:
            continue

        for row in rows:
            if _is_blank_or_total(row):
                continue
            name = str(row.get(owner_col) or "").strip() if owner_col else ""
            email = str(row.get(email_col) or "").strip() if email_col else ""
            dept = str(row.get(dept_col) or "").strip() if dept_col else ""
            status = str(row.get(status_col) or "").strip() if status_col else ""

            if dept:
                departments.add(dept)
            if not name and not email:
                continue

            key = email.lower() if email else f"{name.lower()}|{dept.lower()}"
            entry = people_by_key.setdefault(key, {
                "name": None, "email": None, "department": None,
                "sheets": set(), "statuses": set(),
            })
            entry["name"] = entry["name"] or (name or None)
            entry["email"] = entry["email"] or (email or None)
            entry["department"] = entry["department"] or (dept or None)
            entry["sheets"].add(s.get("label"))
            if status:
                entry["statuses"].add(status)

    people = [
        {
            "name": e["name"],
            "email": e["email"],
            "department": e["department"],
            "sheets": sorted(e["sheets"]),
            "statuses": sorted(e["statuses"]),
        }
        for e in people_by_key.values()
    ]
    return people, sorted(departments)


async def upsert_people_and_departments(db, people: List[Dict[str, Any]], departments: List[str], token: str) -> None:
    """Upsert extracted people (keyed by email, falling back to name) and departments
    into db.people / db.departments, scoped by token."""
    now = datetime.now(timezone.utc).isoformat()

    for p in people:
        key = (p.get("email") or p.get("name") or "").strip().lower()
        if not key:
            continue
        doc_id = f"{token}:{key}"
        await db.people.update_one(
            {"id": doc_id},
            {"$set": {
                "id": doc_id, "token": token,
                "name": p.get("name"), "email": p.get("email"), "department": p.get("department"),
                "updated_at": now,
            }},
            upsert=True,
        )

    for d in departments:
        key = d.strip().lower()
        if not key:
            continue
        doc_id = f"{token}:{key}"
        await db.departments.update_one(
            {"id": doc_id},
            {"$set": {"id": doc_id, "token": token, "name": d, "updated_at": now}},
            upsert=True,
        )
