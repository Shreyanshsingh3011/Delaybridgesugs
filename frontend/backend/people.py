import re

OWNER_PATS  = [r"owner", r"resp", r"assign", r"engineer", r"in[\s_-]?charge", r"\bperson\b", r"\bby\b"]
DEPT_PATS   = [r"dept", r"department", r"section", r"discipline", r"\bteam\b", r"service group"]
EMAIL_PATS  = [r"e[\s_-]?mail"]
STATUS_PATS = [r"status", r"state", r"stage", r"progress"]
DATE_PATS   = [r"date", r"\bdue\b", r"target", r"\bplan", r"actual", r"completion"]

_TOTAL_ROW = re.compile(r"^\s*(grand\s+total|sub\s*total|total)\s*$", re.I)


def _find(names, pats):
    for n in names:
        ln = str(n).lower()
        if any(re.search(p, ln) for p in pats):
            return n
    return None


def column_map(columns):
    names = [c.get("name") if isinstance(c, dict) else c for c in (columns or [])]
    return {
        "owner":  _find(names, OWNER_PATS),
        "dept":   _find(names, DEPT_PATS),
        "email":  _find(names, EMAIL_PATS),
        "status": _find(names, STATUS_PATS),
        "date":   _find(names, DATE_PATS),
    }


def _is_total(row):
    for v in row.values():
        if isinstance(v, str) and _TOTAL_ROW.match(v):
            return True
    return False


def extract_people(sheets):
    """Return (people[], departments[]) derived from sheet rows."""
    people, depts = {}, set()
    for sh in sheets or []:
        cm = column_map(sh.get("columns", []))
        if not (cm["owner"] or cm["dept"] or cm["email"]):
            continue
        for r in sh.get("rows", []):
            if _is_total(r):
                continue
            name  = str(r.get(cm["owner"]) or "").strip() if cm["owner"] else ""
            dept  = str(r.get(cm["dept"])  or "").strip() if cm["dept"]  else ""
            email = str(r.get(cm["email"]) or "").strip() if cm["email"] else ""
            if dept:
                depts.add(dept)
            if name or email:
                key = (email or name).lower()
                people.setdefault(key, {"name": name or email, "email": email, "department": dept})
    return list(people.values()), sorted(depts)

import uuid
from datetime import datetime, timezone
from fastapi import Body
from people import column_map, extract_people

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _connected_sheets(sess):
    return [s for s in sess.get("sheets", []) if s.get("connected")]

def _want(sess, key):
    fields = sess.get("export_fields") or []
    return (not fields) or (key in fields)

@router.get("/{token}/column-map")
async def get_column_map(token: str):
    from server import db
    sess = await _get_by_token(db, token)
    if not _want(sess, "concerns"):
        raise HTTPException(404, "Not enabled")
    return {s.get("label"): column_map(s.get("columns", [])) for s in _connected_sheets(sess)}

@router.post("/{token}/concerns")
async def create_concern(token: str, body: dict = Body(...)):
    from server import db
    sess = await _get_by_token(db, token)
    if not _want(sess, "concerns"):
        raise HTTPException(404, "Not enabled")
    people, depts = extract_people(_connected_sheets(sess))
    for p in people:
        await db.people.update_one({"id": (p["email"] or p["name"]).lower()},
                                   {"$set": {"data": {**p, "token": token}}}, upsert=True)
    for d in depts:
        await db.departments.update_one({"id": d.lower()},
                                        {"$set": {"data": {"name": d, "token": token}}}, upsert=True)
    cid = uuid.uuid4().hex
    doc = {"token": token, "raised_by": body.get("raised_by"),
           "raised_by_department": body.get("raised_by_department"),
           "target_department": body.get("target_department"),
           "sheet_label": body.get("sheet_label"), "activity_ref": body.get("activity_ref"),
           "title": body.get("title"), "detail": body.get("detail"),
           "severity": body.get("severity", "medium"), "status": "open", "created_at": _now_iso()}
    await db.concerns.insert_one({"id": cid, "data": doc})
    return {"ok": True, "id": cid, "status": "open"}

@router.get("/{token}/concerns")
async def list_concerns(token: str, status: str = None, department: str = None):
    from server import db
    sess = await _get_by_token(db, token)
    if not _want(sess, "concerns"):
        raise HTTPException(404, "Not enabled")
    out = []
    async for row in db.concerns.find({}):
        d = row.get("data", {})
        if d.get("token") != token: continue
        if status and d.get("status") != status: continue
        if department and d.get("target_department") != department: continue
        out.append({"id": row["id"], **d})
    by_dept = {}
    for c in out:
        dep = c.get("target_department") or "—"
        by_dept.setdefault(dep, {"open": 0, "ack": 0, "resolved": 0, "total": 0})
        st = c.get("status", "open")
        by_dept[dep][st] = by_dept[dep].get(st, 0) + 1
        by_dept[dep]["total"] += 1
    return {"concerns": out, "by_department": by_dept}

@router.patch("/{token}/concerns/{cid}")
async def update_concern(token: str, cid: str, body: dict = Body(...)):
    from server import db
    sess = await _get_by_token(db, token)
    if not _want(sess, "concerns"):
        raise HTTPException(404, "Not enabled")
    row = await db.concerns.find_one({"id": cid})
    if not row:
        raise HTTPException(404, "Concern not found")
    d = row.get("data", {})
    d["status"] = body.get("status", d.get("status"))
    await db.concerns.update_one({"id": cid}, {"$set": {"data": d}})
    await db.actions.insert_one({"id": uuid.uuid4().hex, "data": {
        "token": token, "concern_id": cid, "action_type": "status_change",
        "note": body.get("note"), "to_status": d["status"], "created_at": _now_iso()}})
    return {"ok": True, "id": cid, "status": d["status"]}

@router.post("/{token}/reminders")
async def create_reminder(token: str, body: dict = Body(...)):
    from server import db
    sess = await _get_by_token(db, token)
    if not _want(sess, "concerns"):
        raise HTTPException(404, "Not enabled")
    rid = uuid.uuid4().hex
    doc = {"token": token, "related_type": body.get("related_type"),
           "related_id": body.get("related_id"), "recipient_email": body.get("recipient_email"),
           "subject": body.get("subject"), "body": body.get("body"),
           "recurrence": body.get("recurrence", "none"), "status": "pending",
           "schedule_at": body.get("schedule_at") or _now_iso()}
    await db.reminders.insert_one({"id": rid, "data": doc})
    return {"ok": True, "id": rid}

@router.get("/{token}/reminders")
async def list_reminders(token: str, status: str = None):
    from server import db
    sess = await _get_by_token(db, token)
    if not _want(sess, "concerns"):
        raise HTTPException(404, "Not enabled")
    out = []
    async for row in db.reminders.find({}):
        d = row.get("data", {})
        if d.get("token") != token: continue
        if status and d.get("status", "pending") != status: continue
        out.append({"id": row["id"], **d})
    return {"reminders": out}

@router.get("/{token}/harmonize")
async def harmonize(token: str):
    import re as _re
    from server import db
    sess = await _get_by_token(db, token)
    if not _want(sess, "harmonize"):
        raise HTTPException(404, "Not enabled")
    seen, suggestions = {}, []
    for s in _connected_sheets(sess):
        for c in s.get("columns", []):
            name = c.get("name", "")
            norm = _re.sub(r"\s+", " ", name).strip().lower()
            canon = seen.setdefault(norm, name)
            if name != canon:
                suggestions.append({"sheet_label": s.get("label"), "column": name,
                                    "issue": "Heading differs from other sheets",
                                    "current": name, "suggested": canon})
    return {"suggestions": suggestions}
