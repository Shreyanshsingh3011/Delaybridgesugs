"""Public routes — accessed by public token (e.g. for Lovable dashboard, Apps Script).
No JWT required. Read mostly; some mutating endpoints (ack/resolve, chat, refresh)."""
import os
import re
import uuid
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from models import ChatRequest, FlagAction, SHEET_COLORS
from flags import downstream_for_email
from chatbot import (
    build_admin_system_prompt,
    build_dependent_system_prompt,
    chat_send,
    ADMIN_SUGGESTIONS,
    DEPENDENT_SUGGESTIONS,
)
from sheet_fetcher import fetch_apps_script
from normalizer import normalize_rows
from routes_admin import _run_and_persist_analysis


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/public")


APPS_SCRIPT_SAMPLE = """function doGet(e) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const data = sheet.getDataRange().getValues();
  const headers = data[0];
  const rows = data.slice(1).map(row => {
    const obj = {};
    headers.forEach((h, i) => obj[h] = row[i]);
    return obj;
  });
  return ContentService
    .createTextOutput(JSON.stringify({ status: "ok", count: rows.length, data: rows }))
    .setMimeType(ContentService.MimeType.JSON);
}"""


async def _get_by_token(db, token: str) -> Dict[str, Any]:
    sess = await db.sessions.find_one({"public_token": token}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found for token.")
    return sess


def _ensure_analysis(sess: Dict[str, Any]) -> Dict[str, Any]:
    analysis = sess.get("analysis")
    if not analysis:
        raise HTTPException(status_code=400, detail="Analysis not yet generated for this session.")
    return analysis


def _strip_for_public(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Remove heavy internal fields from public payloads."""
    a = dict(analysis)
    a.pop("primary_rows", None)
    return a


# -------- Full analysis JSON --------
@router.get("/{token}")
async def get_full_analysis(token: str):
    from server import db
    sess = await _get_by_token(db, token)
    analysis = _ensure_analysis(sess)
    out = _strip_for_public(analysis)
    out["session_id"] = sess["id"]
    out["mode_badge"] = "Variance Analysis Enabled" if out.get("mode") == "multi-sheet" else "Single Sheet Mode — Delay Analysis Active"
    return out


# -------- Slices --------
@router.get("/{token}/flags")
async def get_flags(token: str, severity: Optional[str] = None, status: Optional[str] = None, person: Optional[str] = None):
    from server import db
    sess = await _get_by_token(db, token)
    analysis = _ensure_analysis(sess)
    flags = analysis.get("flags", [])
    if severity:
        flags = [f for f in flags if f.get("severity", "").lower() == severity.lower()]
    if status:
        flags = [f for f in flags if f.get("status", "").lower() == status.lower()]
    if person:
        p = person.lower()
        flags = [f for f in flags if p in (f.get("flagged_to", {}).get("person") or "").lower()
                 or p in (f.get("flagged_to", {}).get("email") or "").lower()]
    return {"count": len(flags), "flags": flags}


@router.get("/{token}/variances")
async def get_variances(token: str):
    from server import db
    sess = await _get_by_token(db, token)
    analysis = _ensure_analysis(sess)
    v = analysis.get("variance")
    if not v:
        return {"enabled": False, "message": "Variance requires 2+ connected sheets."}
    return {"enabled": True, **v}


@router.get("/{token}/correlations")
async def get_correlations(token: str):
    from server import db
    sess = await _get_by_token(db, token)
    analysis = _ensure_analysis(sess)
    return {
        "correlation_matrix": analysis.get("correlation_matrix"),
        "person_ranking": analysis.get("person_ranking"),
        "department_ranking": analysis.get("department_ranking"),
        "timeline_correlation": analysis.get("timeline_correlation"),
        "top_delay_reasons": analysis.get("top_delay_reasons"),
    }


@router.get("/{token}/dependencies")
async def get_dependencies(token: str):
    from server import db
    sess = await _get_by_token(db, token)
    analysis = _ensure_analysis(sess)
    return analysis.get("dependency_chains") or {}


# -------- Composable export --------
EXPORT_FIELDS = [
    "summary", "mode", "mode_badge", "totals", "risk_score", "status_breakdown",
    "top_delay_reasons", "correlation_matrix", "dependency_chains",
    "person_ranking", "department_ranking", "timeline_correlation",
    "tat_performance", "variance", "flags", "sheets", "primary_label",
    "session_id", "public_token", "created_at",
]


@router.get("/{token}/export")
async def export_filtered(token: str, fields: Optional[str] = None):
    """Return a slice of the analysis JSON containing only the requested fields.
    `fields` is a comma-separated list. If omitted, returns all standard fields.
    """
    from server import db
    sess = await _get_by_token(db, token)
    analysis = _ensure_analysis(sess)
    full = _strip_for_public(analysis)
    full["session_id"] = sess["id"]
    full["mode_badge"] = "Variance Analysis Enabled" if full.get("mode") == "multi-sheet" else "Single Sheet Mode — Delay Analysis Active"

    if not fields:
        return full
    requested = [f.strip() for f in fields.split(",") if f.strip()]
    out: Dict[str, Any] = {
        "session_id": full.get("session_id"),
        "public_token": full.get("public_token"),
        "created_at": full.get("created_at"),
        "mode": full.get("mode"),
        "mode_badge": full.get("mode_badge"),
    }
    for f in requested:
        if f in full:
            out[f] = full[f]
    out["_fields_returned"] = [f for f in requested if f in full]
    out["_fields_unknown"] = [f for f in requested if f not in full]
    return out


@router.get("/{token}/downstream/{email}")
async def get_downstream(token: str, email: str):
    from server import db
    sess = await _get_by_token(db, token)
    analysis = _ensure_analysis(sess)
    rows = analysis.get("primary_rows", [])
    return downstream_for_email(email, analysis.get("flags", []), rows, analysis.get("dependency_chains") or {})


# -------- Onboarding + status --------
@router.get("/{token}/onboarding")
async def onboarding():
    return {
        "steps": [
            "Step 1 — Open your Google Sheet",
            "Step 2 — Click Extensions → Apps Script",
            "Step 3 — Paste the code (copy button provided)",
            "Step 4 — Click Deploy → New Deployment",
            "Step 5 — Type: Web App | Execute as: Me | Who has access: Anyone",
            "Step 6 — Click Deploy → Copy the Web App URL",
            "Step 7 — Paste that URL into DelayBridge",
        ],
        "apps_script_code": APPS_SCRIPT_SAMPLE,
    }


@router.get("/{token}/status")
async def get_status(token: str):
    from server import db
    sess = await _get_by_token(db, token)
    return {
        "session_id": sess["id"],
        "name": sess["name"],
        "sheets": [
            {
                "label": s["label"],
                "color": SHEET_COLORS.get(s["label"], "blue"),
                "name": s.get("name"),
                "url": s.get("url"),
                "rows": s.get("rows", 0),
                "connected": s.get("connected", False),
                "last_fetched": s.get("last_fetched"),
            }
            for s in sess.get("sheets", [])
        ],
        "has_analysis": sess.get("analysis") is not None,
    }


@router.post("/{token}/refresh")
async def public_refresh(token: str):
    """Re-fetch all sheets and re-analyze. Open endpoint scoped to this token."""
    from server import db
    sess = await _get_by_token(db, token)
    updated_sheets: List[Dict[str, Any]] = []
    for s in sess.get("sheets", []):
        url = s.get("url")
        if not url or not url.startswith(("http://", "https://")):
            updated_sheets.append(s)
            continue
        ok, msg, rows_raw = fetch_apps_script(url)
        if ok:
            s = dict(s)
            s["rows_raw"] = rows_raw
            s["rows"] = len(rows_raw)
            s["last_fetched"] = datetime.now(timezone.utc).isoformat()
            s["connected"] = True
            s["status_msg"] = msg
        else:
            s = dict(s)
            s["connected"] = False
            s["status_msg"] = msg
        updated_sheets.append(s)
    await db.sessions.update_one({"public_token": token}, {"$set": {"sheets": updated_sheets, "updated_at": datetime.now(timezone.utc).isoformat()}})
    connected_sheets = [s for s in updated_sheets if s.get("connected")]
    if not connected_sheets:
        raise HTTPException(status_code=400, detail="No connected sheets after refresh.")
    sess["sheets"] = updated_sheets
    return await _run_and_persist_analysis(db, sess, connected_sheets)


# -------- Flag actions --------
@router.post("/{token}/flag/{flag_id}/acknowledge")
async def acknowledge_flag(token: str, flag_id: str, payload: Optional[FlagAction] = None):
    from server import db
    sess = await _get_by_token(db, token)
    analysis = _ensure_analysis(sess)
    flags = analysis.get("flags", [])
    found = None
    for f in flags:
        if f.get("id") == flag_id or f.get("uid") == flag_id:
            f["status"] = "Acknowledged"
            f["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
            if payload and payload.note:
                f["ack_note"] = payload.note
            found = f
            break
    if not found:
        raise HTTPException(status_code=404, detail="Flag not found.")
    await db.sessions.update_one({"public_token": token}, {"$set": {"analysis.flags": flags, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return found


@router.post("/{token}/flag/{flag_id}/resolve")
async def resolve_flag(token: str, flag_id: str, payload: Optional[FlagAction] = None):
    from server import db
    sess = await _get_by_token(db, token)
    analysis = _ensure_analysis(sess)
    flags = analysis.get("flags", [])
    found = None
    for f in flags:
        if f.get("id") == flag_id or f.get("uid") == flag_id:
            f["status"] = "Resolved"
            f["resolved_at"] = datetime.now(timezone.utc).isoformat()
            if payload and payload.note:
                f["resolve_note"] = payload.note
            found = f
            break
    if not found:
        raise HTTPException(status_code=404, detail="Flag not found.")
    await db.sessions.update_one({"public_token": token}, {"$set": {"analysis.flags": flags, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return found


# -------- Chat --------
@router.get("/{token}/chat/suggestions")
async def chat_suggestions(token: str, email: Optional[str] = None):
    from server import db
    sess = await _get_by_token(db, token)
    analysis = _ensure_analysis(sess)
    mode = "admin"
    if email:
        rows = analysis.get("primary_rows", [])
        email_l = email.strip().lower()
        if any((r.get("responsible_email") or "").lower() == email_l for r in rows):
            mode = "dependent"
    return {
        "mode": mode,
        "suggestions": DEPENDENT_SUGGESTIONS if mode == "dependent" else ADMIN_SUGGESTIONS,
    }


@router.post("/{token}/chat")
async def chat(token: str, payload: ChatRequest):
    from server import db
    sess = await _get_by_token(db, token)
    analysis = _ensure_analysis(sess)
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="EMERGENT_LLM_KEY not configured.")

    chat_session_id = payload.session_id or str(uuid.uuid4())
    rows = analysis.get("primary_rows", [])
    sheets_meta = analysis.get("sheets", [])

    mode = "admin"
    person_record: Optional[Dict[str, Any]] = None
    blocked_info: List[Dict[str, Any]] = []
    my_activities: List[Dict[str, Any]] = []

    if payload.email:
        email_l = payload.email.strip().lower()
        my_rows = [r for r in rows if (r.get("responsible_email") or "").lower() == email_l]
        if my_rows:
            mode = "dependent"
            person_record = {
                "email": payload.email,
                "name": my_rows[0].get("responsible_person"),
                "phone": my_rows[0].get("responsible_phone"),
            }
            my_activities = [
                {
                    "activity": r.get("activity"),
                    "status": r.get("status"),
                    "tat": r.get("tat"),
                    "days_taken": r.get("days_taken"),
                    "dependency": r.get("dependency"),
                }
                for r in my_rows
            ]
            ds = downstream_for_email(payload.email, analysis.get("flags", []), rows, analysis.get("dependency_chains") or {})
            blocked_info = ds.get("blocked", [])

    if mode == "dependent":
        system_prompt = build_dependent_system_prompt(analysis, person_record, blocked_info, my_activities)
    else:
        system_prompt = build_admin_system_prompt(analysis, sheets_meta)

    try:
        reply = await chat_send(api_key, chat_session_id, system_prompt, payload.message)
    except Exception as e:
        logger.exception("Chatbot error")
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    # Log interaction
    log_entry = {
        "id": str(uuid.uuid4()),
        "token": token,
        "session_id": chat_session_id,
        "mode": mode,
        "email": payload.email,
        "user_message": payload.message,
        "assistant_reply": reply,
        "blocked_info_count": len(blocked_info),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.chat_logs.insert_one(dict(log_entry))

    # Dependent pressure-loop: every time a dependent person checks, notify blocker (mocked)
    auto_actions: List[Dict[str, Any]] = []
    if mode == "dependent" and blocked_info:
        for b in blocked_info:
            mock = {
                "id": str(uuid.uuid4()),
                "type": "dependent_pressure_loop",
                "channel": "email+sms",
                "to": b.get("blocker_person"),
                "from_person": person_record.get("name") if person_record else payload.email,
                "blocking_activity": b.get("blocking_activity"),
                "dependent_activity": b.get("your_activity"),
                "status": "MOCKED — alerts disabled (no Twilio/SendGrid credentials configured)",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "token": token,
            }
            auto_actions.append(mock)
            await db.alert_log.insert_one(dict(mock))
        # Update related flags to "Escalated by Dependent"
        flags = analysis.get("flags", [])
        for f in flags:
            for b in blocked_info:
                if (f.get("activity") or "").lower() == (b.get("blocking_activity") or "").lower():
                    f["status"] = "Escalated by Dependent"
        await db.sessions.update_one({"public_token": token}, {"$set": {"analysis.flags": flags}})

    log_entry.pop("_id", None)
    return {
        "session_id": chat_session_id,
        "mode": mode,
        "reply": reply,
        "auto_actions": auto_actions,
        "suggestions": DEPENDENT_SUGGESTIONS if mode == "dependent" else ADMIN_SUGGESTIONS,
    }


@router.get("/{token}/chat/history")
async def chat_history(token: str, chat_session_id: Optional[str] = None, limit: int = 50):
    from server import db
    await _get_by_token(db, token)
    query = {"token": token}
    if chat_session_id:
        query["session_id"] = chat_session_id
    cur = db.chat_logs.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    items = []
    async for it in cur:
        items.append(it)
    items.reverse()
    return {"count": len(items), "history": items}


@router.get("/{token}/alerts")
async def get_alerts(token: str, limit: int = 100):
    from server import db
    await _get_by_token(db, token)
    cur = db.alert_log.find({"token": token}, {"_id": 0}).sort("created_at", -1).limit(limit)
    items = []
    async for it in cur:
        items.append(it)
    return {"count": len(items), "alerts": items}
