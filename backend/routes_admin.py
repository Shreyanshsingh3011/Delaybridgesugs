"""Admin routes — JWT-protected. Manage sessions, sheets, and trigger analysis."""
import os
import uuid
import secrets
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel

from auth import (
    get_current_user,
    verify_password,
    create_access_token,
    create_refresh_token,
)
from models import (
    LoginRequest,
    UserOut,
    SessionCreate,
    SheetAdd,
    ColumnMapping,
    SHEET_COLORS,
)
from sheet_fetcher import fetch_apps_script
from normalizer import detect_columns, normalize_rows, data_quality
from analysis import analyze_single_sheet
from variance import compute_variances, column_similarity
from flags import generate_flags
from demo_data import get_demo_rows, get_demo_rows_variant_b


router = APIRouter(prefix="/api")


# -------- Auth --------
@router.post("/auth/login")
async def login(payload: LoginRequest, response: Response):
    from server import db
    email = payload.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    access = create_access_token(user["id"], user["email"])
    refresh = create_refresh_token(user["id"])
    response.set_cookie("access_token", access, httponly=True, secure=False, samesite="lax", max_age=86400, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    return {
        "user": {"id": user["id"], "email": user["email"], "name": user.get("name"), "role": user.get("role")},
        "access_token": access,
        "token_type": "bearer",
    }


@router.post("/auth/logout")
async def logout(response: Response, current=Depends(get_current_user)):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


@router.get("/auth/me", response_model=UserOut)
async def me(current=Depends(get_current_user)):
    return UserOut(**current)


# -------- Sessions --------
def _next_label(used: List[str]) -> str:
    for c in ["A", "B", "C", "D", "E"]:
        if c not in used:
            return c
    raise HTTPException(status_code=400, detail="Maximum 5 sheets per session.")


async def _get_session(db, session_id: str, owner_id: str) -> Dict[str, Any]:
    sess = await db.sessions.find_one({"id": session_id, "owner_id": owner_id}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess


@router.post("/sessions")
async def create_session(payload: SessionCreate, current=Depends(get_current_user)):
    from server import db
    sid = str(uuid.uuid4())
    token = secrets.token_urlsafe(24)
    doc = {
        "id": sid,
        "owner_id": current["id"],
        "name": payload.name,
        "public_token": token,
        "sheets": [],
        "analysis": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.sessions.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/sessions")
async def list_sessions(current=Depends(get_current_user)):
    from server import db
    cur = db.sessions.find({"owner_id": current["id"]}, {"_id": 0}).sort("created_at", -1)
    out = []
    async for s in cur:
        out.append({
            "id": s["id"],
            "name": s["name"],
            "public_token": s["public_token"],
            "sheet_count": len(s.get("sheets", [])),
            "has_analysis": s.get("analysis") is not None,
            "created_at": s.get("created_at"),
            "updated_at": s.get("updated_at"),
        })
    return out


@router.get("/sessions/{sid}")
async def get_session(sid: str, current=Depends(get_current_user)):
    from server import db
    sess = await _get_session(db, sid, current["id"])
    # Hide raw rows in summary; keep meta
    meta = {
        "id": sess["id"],
        "name": sess["name"],
        "public_token": sess["public_token"],
        "created_at": sess["created_at"],
        "updated_at": sess["updated_at"],
        "sheets": [
            {
                "label": s["label"],
                "url": s.get("url"),
                "name": s.get("name"),
                "rows": s.get("rows", 0),
                "columns": s.get("columns", 0),
                "last_fetched": s.get("last_fetched"),
                "connected": s.get("connected", False),
                "color": SHEET_COLORS.get(s["label"], "blue"),
                "headers": s.get("headers", []),
                "detected_mapping": s.get("detected_mapping", {}),
                "mapping": s.get("mapping", {}),
                "preview": (s.get("rows_raw") or [])[:10],
                "data_quality": s.get("data_quality"),
            }
            for s in sess.get("sheets", [])
        ],
        "analysis_summary": (sess.get("analysis") or {}).get("summary") if sess.get("analysis") else None,
        "has_analysis": sess.get("analysis") is not None,
    }
    return meta


@router.delete("/sessions/{sid}")
async def delete_session(sid: str, current=Depends(get_current_user)):
    from server import db
    res = await db.sessions.delete_one({"id": sid, "owner_id": current["id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


# -------- Sheets --------
def _build_sheet_record(label: str, url: str, name: Optional[str], rows_raw, status_msg: str, connected: bool) -> Dict[str, Any]:
    headers: List[str] = []
    if rows_raw:
        seen = []
        for r in rows_raw[:10]:
            for k in r.keys():
                if k not in seen:
                    seen.append(k)
        headers = seen
    detected = detect_columns(headers) if headers else {}
    return {
        "label": label,
        "url": url,
        "name": name or f"Sheet {label}",
        "rows": len(rows_raw or []),
        "columns": len(headers),
        "last_fetched": datetime.now(timezone.utc).isoformat() if connected else None,
        "connected": connected,
        "status_msg": status_msg,
        "headers": headers,
        "detected_mapping": detected,
        "mapping": detected,  # default to detected
        "rows_raw": rows_raw or [],
    }


@router.post("/sessions/{sid}/sheets")
async def add_sheet(sid: str, payload: SheetAdd, current=Depends(get_current_user)):
    from server import db
    sess = await _get_session(db, sid, current["id"])
    used = [s["label"] for s in sess.get("sheets", [])]
    if len(used) >= 5:
        raise HTTPException(status_code=400, detail="Maximum 5 sheets per session.")
    label = payload.label or _next_label(used)
    if label in used:
        raise HTTPException(status_code=400, detail=f"Sheet label {label} already used.")
    ok, msg, rows_raw = fetch_apps_script(payload.url)
    record = _build_sheet_record(label, payload.url, None, rows_raw, msg, ok)
    # quality only if connected
    if ok:
        normalized = normalize_rows(rows_raw, record["mapping"])
        record["data_quality"] = data_quality(rows_raw, normalized)
    await db.sessions.update_one(
        {"id": sid, "owner_id": current["id"]},
        {"$push": {"sheets": record}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {
        "label": record["label"],
        "rows": record["rows"],
        "columns": record["columns"],
        "headers": record["headers"],
        "detected_mapping": record["detected_mapping"],
        "preview": record["rows_raw"][:10],
        "last_fetched": record["last_fetched"],
        "connected": record["connected"],
        "data_quality": record.get("data_quality"),
        "color": SHEET_COLORS.get(label, "blue"),
    }


@router.delete("/sessions/{sid}/sheets/{label}")
async def remove_sheet(sid: str, label: str, current=Depends(get_current_user)):
    from server import db
    sess = await _get_session(db, sid, current["id"])
    new_sheets = [s for s in sess.get("sheets", []) if s["label"] != label]
    if len(new_sheets) == len(sess.get("sheets", [])):
        raise HTTPException(status_code=404, detail="Sheet not found in session.")
    await db.sessions.update_one(
        {"id": sid, "owner_id": current["id"]},
        {"$set": {"sheets": new_sheets, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True}


@router.post("/sessions/{sid}/sheets/{label}/refresh")
async def refresh_sheet(sid: str, label: str, current=Depends(get_current_user)):
    from server import db
    sess = await _get_session(db, sid, current["id"])
    target = next((s for s in sess.get("sheets", []) if s["label"] == label), None)
    if not target:
        raise HTTPException(status_code=404, detail="Sheet not found.")
    ok, msg, rows_raw = fetch_apps_script(target["url"])
    if not ok:
        await db.sessions.update_one(
            {"id": sid, "owner_id": current["id"], "sheets.label": label},
            {"$set": {"sheets.$.connected": False, "sheets.$.status_msg": msg}},
        )
        raise HTTPException(status_code=400, detail=msg)
    mapping = target.get("mapping") or detect_columns(list((rows_raw[0] or {}).keys()) if rows_raw else [])
    normalized = normalize_rows(rows_raw, mapping)
    await db.sessions.update_one(
        {"id": sid, "owner_id": current["id"], "sheets.label": label},
        {"$set": {
            "sheets.$.rows": len(rows_raw),
            "sheets.$.rows_raw": rows_raw,
            "sheets.$.last_fetched": datetime.now(timezone.utc).isoformat(),
            "sheets.$.connected": True,
            "sheets.$.status_msg": msg,
            "sheets.$.data_quality": data_quality(rows_raw, normalized),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"ok": True, "rows": len(rows_raw), "message": msg}


@router.post("/sessions/{sid}/sheets/{label}/mapping")
async def set_mapping(sid: str, label: str, mapping: ColumnMapping, current=Depends(get_current_user)):
    from server import db
    map_dict = {k: v for k, v in mapping.model_dump().items() if v}
    await db.sessions.update_one(
        {"id": sid, "owner_id": current["id"], "sheets.label": label},
        {"$set": {"sheets.$.mapping": map_dict, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True, "mapping": map_dict}


# -------- Analysis trigger --------
@router.post("/sessions/{sid}/analyze")
async def analyze(sid: str, current=Depends(get_current_user)):
    from server import db
    sess = await _get_session(db, sid, current["id"])
    sheets = [s for s in sess.get("sheets", []) if s.get("connected")]
    if not sheets:
        raise HTTPException(status_code=400, detail="No connected sheets to analyze.")
    return await _run_and_persist_analysis(db, sess, sheets)


async def _run_and_persist_analysis(db, sess: Dict[str, Any], sheets: List[Dict[str, Any]]) -> Dict[str, Any]:
    normalized_by_label: Dict[str, List[Dict[str, Any]]] = {}
    for s in sheets:
        mapping = s.get("mapping") or s.get("detected_mapping") or {}
        normalized_by_label[s["label"]] = normalize_rows(s.get("rows_raw") or [], mapping)

    primary_label = sorted(normalized_by_label.keys())[0]
    primary_rows = normalized_by_label[primary_label]

    delay = analyze_single_sheet(primary_rows)
    variance_result = None
    if len(normalized_by_label) >= 2:
        variance_result = compute_variances(normalized_by_label)
        # Column similarity check vs primary
        primary_headers = sheets[0].get("headers", [])
        for s in sheets[1:]:
            sim_val = column_similarity(primary_headers, s.get("headers", []))
            variance_result.setdefault("column_similarity", {})[s["label"]] = round(sim_val, 2)

    flags = generate_flags(primary_rows, delay.get("dependency_chains") or {}, variance_result)

    summary_text_parts = [
        f"{delay['totals']['rows']} rows analysed.",
        f"{delay['totals']['delayed']} delayed.",
        f"{delay['totals']['blocked']} blocked downstream.",
    ]
    if variance_result:
        s = variance_result["summary"]
        summary_text_parts.append(
            f"Variance: {s['matched']} matched, {s['conflicts']} conflicts, {s['outliers']} outliers across {s['compared_sheets']} sheets."
        )
    summary = " ".join(summary_text_parts)

    analysis = {
        "session_id": sess["id"],
        "public_token": sess["public_token"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "multi-sheet" if len(normalized_by_label) >= 2 else "single-sheet",
        "summary": summary,
        "sheets": [
            {
                "label": s["label"],
                "name": s.get("name"),
                "url": s.get("url"),
                "rows": s.get("rows", 0),
                "columns": s.get("columns", 0),
                "color": SHEET_COLORS.get(s["label"], "blue"),
                "last_fetched": s.get("last_fetched"),
            }
            for s in sheets
        ],
        "primary_label": primary_label,
        "totals": delay["totals"],
        "risk_score": delay["risk_score"],
        "status_breakdown": delay["status_breakdown"],
        "top_delay_reasons": delay["top_delay_reasons"],
        "correlation_matrix": delay["correlation_matrix"],
        "dependency_chains": delay["dependency_chains"],
        "person_ranking": delay["person_ranking"],
        "department_ranking": delay["department_ranking"],
        "timeline_correlation": delay["timeline_correlation"],
        "tat_performance": _tat_performance(primary_rows) if len(normalized_by_label) == 1 else None,
        "variance": variance_result,
        "flags": flags,
        "primary_rows": primary_rows,  # used by chatbot / downstream lookups
    }

    await db.sessions.update_one(
        {"id": sess["id"]},
        {"$set": {"analysis": analysis, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {
        "ok": True,
        "summary": summary,
        "risk_score": analysis["risk_score"],
        "totals": analysis["totals"],
        "public_token": sess["public_token"],
        "mode": analysis["mode"],
        "flags_count": len(flags),
    }


def _tat_performance(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    items = []
    for r in rows:
        tat = r.get("tat")
        dt = r.get("days_taken")
        if isinstance(tat, (int, float)) and isinstance(dt, (int, float)):
            delta = dt - tat
            pct = (delta / tat * 100.0) if tat > 0 else 0.0
            items.append({
                "activity": r.get("activity"),
                "tat": tat,
                "days_taken": dt,
                "delta": round(delta, 1),
                "overrun_pct": round(pct, 2),
                "status": r.get("status"),
                "person": r.get("responsible_person"),
            })
    items.sort(key=lambda x: x["overrun_pct"], reverse=True)
    return {
        "rows": items,
        "label": "Internal TAT Performance — single sheet",
        "prompt": "Add Sheet B to enable true cross-source Variance Analysis",
    }


# -------- Demo load --------
@router.post("/sessions/{sid}/load-demo")
async def load_demo(sid: str, current=Depends(get_current_user)):
    from server import db
    sess = await _get_session(db, sid, current["id"])
    rows_a = get_demo_rows()
    rows_b = get_demo_rows_variant_b()
    sheets: List[Dict[str, Any]] = []
    for label, rows in [("A", rows_a), ("B", rows_b)]:
        rec = _build_sheet_record(label, f"demo://nit76-{label}", f"NIT-76 Snapshot {label}", rows, f"Demo data loaded ({len(rows)} rows).", True)
        normalized = normalize_rows(rows, rec["mapping"])
        rec["data_quality"] = data_quality(rows, normalized)
        sheets.append(rec)
    await db.sessions.update_one(
        {"id": sid, "owner_id": current["id"]},
        {"$set": {"sheets": sheets, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    sess["sheets"] = sheets
    return await _run_and_persist_analysis(db, sess, sheets)
