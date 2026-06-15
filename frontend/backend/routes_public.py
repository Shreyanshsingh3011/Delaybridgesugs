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
    out = {}
    for s in _connected_sheets(sess):
        try:
            out[s.get("label")] = column_map(s.get("columns") or [])
        except Exception:
            out[s.get("label")] = {"owner": None, "dept": None, "email": None,
                                   "status": None, "date": None}
    return out

@router.post("/{token}/concerns")
async def create_concern(token: str, body: dict = Body(...)):
    from server import db
    sess = await _get_by_token(db, token)
    if not _want(sess, "concerns"):
        raise HTTPException(404, "Not enabled")
    try:
        people, depts = extract_people(_connected_sheets(sess))
    except Exception:
        people, depts = [], []
    for p in people:
        pid = (p.get("email") or p.get("name") or "").lower()
        if pid:
            await db.people.update_one({"id": pid},
                {"$set": {**p, "id": pid, "token": token}}, upsert=True)
    for d in depts:
        await db.departments.update_one({"id": d.lower()},
            {"$set": {"id": d.lower(), "name": d, "token": token}}, upsert=True)
    cid = uuid.uuid4().hex
    doc = {"id": cid, "token": token, "raised_by": body.get("raised_by"),
           "raised_by_department": body.get("raised_by_department"),
           "target_department": body.get("target_department"),
           "sheet_label": body.get("sheet_label"), "activity_ref": body.get("activity_ref"),
           "title": body.get("title"), "detail": body.get("detail"),
           "severity": body.get("severity", "medium"), "status": "open",
           "created_at": _now_iso()}
    await db.concerns.insert_one(doc)
    return {"ok": True, "id": cid, "status": "open"}

@router.get("/{token}/concerns")
async def list_concerns(token: str, status: str = None, department: str = None):
    from server import db
    sess = await _get_by_token(db, token)
    if not _want(sess, "concerns"):
        raise HTTPException(404, "Not enabled")
    out = []
    async for d in db.concerns.find({"token": token}):
        d.pop("_id", None)
        if status and d.get("status") != status:
            continue
        if department and d.get("target_department") != department:
            continue
        out.append(d)
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
    new_status = body.get("status", row.get("status"))
    await db.concerns.update_one({"id": cid}, {"$set": {"status": new_status}})
    await db.actions.insert_one({"id": uuid.uuid4().hex, "token": token,
        "concern_id": cid, "action_type": "status_change",
        "note": body.get("note"), "to_status": new_status, "created_at": _now_iso()})
    return {"ok": True, "id": cid, "status": new_status}

@router.post("/{token}/reminders")
async def create_reminder(token: str, body: dict = Body(...)):
    from server import db
    sess = await _get_by_token(db, token)
    if not _want(sess, "concerns"):
        raise HTTPException(404, "Not enabled")
    rid = uuid.uuid4().hex
    doc = {"id": rid, "token": token, "related_type": body.get("related_type"),
           "related_id": body.get("related_id"), "recipient_email": body.get("recipient_email"),
           "subject": body.get("subject"), "body": body.get("body"),
           "recurrence": body.get("recurrence", "none"), "status": "pending",
           "schedule_at": body.get("schedule_at") or _now_iso()}
    await db.reminders.insert_one(doc)
    return {"ok": True, "id": rid}

@router.get("/{token}/reminders")
async def list_reminders(token: str, status: str = None):
    from server import db
    sess = await _get_by_token(db, token)
    if not _want(sess, "concerns"):
        raise HTTPException(404, "Not enabled")
    out = []
    async for d in db.reminders.find({"token": token}):
        d.pop("_id", None)
        if status and d.get("status", "pending") != status:
            continue
        out.append(d)
    return {"reminders": out}

@router.get("/{token}/harmonize")
async def harmonize(token: str):
    import re as _re
    from server import db
    sess = await _get_by_token(db, token)
    if not _want(sess, "harmonize"):
        raise HTTPException(404, "Not enabled")
    seen, suggestions = {}, []
    try:
        for s in _connected_sheets(sess):
            cols = s.get("columns") or []
            if not isinstance(cols, (list, tuple)):
                continue
            for c in cols:
                name = c.get("name", "") if isinstance(c, dict) else str(c)
                if not name:
                    continue
                norm = _re.sub(r"\s+", " ", name).strip().lower()
                canon = seen.setdefault(norm, name)
                if name != canon:
                    suggestions.append({"sheet_label": s.get("label"), "column": name,
                                        "issue": "Heading differs from other sheets",
                                        "current": name, "suggested": canon})
    except Exception as e:
        logger.warning("harmonize failed: %s", e)
        return {"suggestions": []}
    return {"suggestions": suggestions}
