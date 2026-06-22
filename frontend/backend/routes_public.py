
"""Public routes — accessed by public token (e.g. for Lovable dashboard, Apps Script).
No JWT required. Read mostly; some mutating endpoints (ack/resolve, chat, refresh)."""
import os
import re
import uuid
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models import (
    ChatRequest, CopilotRequest, FlagAction, SHEET_COLORS,
    ConcernCreate, ConcernUpdate, ReminderCreate,
)
from people import column_map, extract_people, upsert_people_and_departments
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
from header_detector import resolve_headers
from sheet_cleaner import clean_sheet


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/public")


async def _clean_sheets(db, token: str, sheets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    hm_list = await db.raw_select("dbridge_header_mappings", {"token": token})
    hm_by_label = {r["sheet_label"]: r for r in (hm_list or [])}
    cleaned = []
    for s in sheets:
        s = dict(s)
        rows_raw = s.get("rows_raw") or []
        hm = hm_by_label.get(s.get("label", ""))
        protected = set((hm or {}).get("column_overrides", {}).values())
        headers, resolved_rows = resolve_headers(rows_raw, hm)
        headers, resolved_rows, n_pruned = clean_sheet(headers, resolved_rows, protected)
        s["rows_raw"] = resolved_rows
        s["headers"] = headers
        s["columns"] = len(headers)
        s["pruned_empty_columns"] = n_pruned
        cleaned.append(s)
    return cleaned
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


def _want_field(sess: Dict[str, Any], key: str) -> bool:
    fields = sess.get("export_fields") or []
    return (not fields) or (key in fields)


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


@router.get("/{token}/dashboard")
async def get_dashboard(token: str):
    """Composite dashboard representing ALL enabled export fields: the generic data
    dashboard (auto KPIs/charts/table) plus the analysis sections (summary, totals,
    status_breakdown, flags) and a copilot flag — each gated by configure-export."""
    from server import db
    from dashboards import build_data_dashboard
    sess = await _get_by_token(db, token)
    fields = sess.get("export_fields") or []

    def want(f):
        return (not fields) or (f in fields)

    sheets = [s for s in sess.get("sheets", []) if s.get("connected")]
    sheets = await _clean_sheets(db, token, sheets)
    out = {"enabled": True, "project": sess.get("name"), "enabled_fields": fields}

    # Data dashboard (KPIs / charts / table per sheet)
    out["data_dashboard_enabled"] = want("data_dashboard")
    if want("data_dashboard"):
        out.update(build_data_dashboard(sheets))
    else:
        out["sheets"] = []

    # Analysis sections (summary / totals / status_breakdown / flags + extended fields)
    analysis = sess.get("analysis") or {}
    sections = {}
    if want("summary") and analysis.get("summary") is not None:
        sections["summary"] = analysis.get("summary")
    if want("totals") and analysis.get("totals") is not None:
        sections["totals"] = analysis.get("totals")
    if want("status_breakdown") and analysis.get("status_breakdown") is not None:
        sections["status_breakdown"] = analysis.get("status_breakdown")
    if want("flags"):
        sections["flags"] = analysis.get("flags", [])
    # Extended analytical outputs (delay-analysis), included only if enabled + present
    for f in ("risk_score", "top_delay_reasons", "correlation_matrix",
              "dependency_chains", "person_ranking", "department_ranking",
              "timeline_correlation", "tat_performance", "variance"):
        if want(f) and analysis.get(f) is not None:
            sections[f] = analysis.get(f)
    sections["mode_badge"] = ("Variance Analysis Enabled" if analysis.get("mode") == "multi-sheet"
                              else "Single Sheet Mode — Delay Analysis Active")
    sections["copilot_enabled"] = want("copilot")
    out["analysis"] = sections

    # Computed modules (from raw sheet rows) — each gated by export field and isolated
    modules = {}

    def add(name, fn):
        if not want(name):
            return
        try:
            modules[name] = fn()
        except Exception as e:  # one module failing must not break the rest
            logger.warning("dashboard module %s failed: %s", name, e)

    try:
        from insights import (build_data_quality, build_pivot, build_anomalies,
                              build_digest, build_recommendations, build_whatif)
        from forecast import build_forecast
        add("data_quality", lambda: build_data_quality(sheets))
        add("pivot", lambda: build_pivot(sheets))
        add("anomalies", lambda: build_anomalies(sheets))
        add("digest", lambda: build_digest(sheets))
        add("recommendations", lambda: build_recommendations(sheets))
        add("whatif", lambda: build_whatif(sheets))
        add("forecast", lambda: build_forecast(sheets))
    except Exception as e:
        logger.warning("dashboard module import failed: %s", e)

    if want("trends"):
        try:
            from snapshots import compute_trends
            snaps = []
            async for it in db.snapshots.find({"token": token}).sort("date", 1):
                snaps.append(it)
            t = compute_trends(snaps)
            t["ready"] = len(t.get("series", [])) >= 2
            t["snapshot_count"] = len(t.get("series", []))
            modules["trends"] = t
        except Exception as e:
            logger.warning("dashboard module trends failed: %s", e)

    if modules:
        out["modules"] = modules
    return out


@router.get("/{token}/quality")
async def get_quality(token: str):
    """Data-quality audit: missing values, duplicates, inconsistent category casing,
    subtotal/total rows, numeric type mismatches, and a score. Enabled via 'data_quality'."""
    from server import db
    from insights import build_data_quality
    sess = await _get_by_token(db, token)
    fields = sess.get("export_fields") or []
    if not ((not fields) or ("data_quality" in fields)):
        return {"enabled": False, "message": "Data-quality module is not enabled for this export."}
    sheets = [s for s in sess.get("sheets", []) if s.get("connected")]
    return {"enabled": True, "project": sess.get("name"), **build_data_quality(sheets)}


@router.get("/{token}/pivot")
async def get_pivot(token: str, dimension: Optional[str] = None, measure: Optional[str] = None,
                    agg: str = "sum", include_totals: bool = False, sheet: Optional[str] = None):
    """Pivot/segmentation: group any dimension by sum/avg/count of any measure.
    Excludes subtotal/total rows by default. Enabled via 'pivot'."""
    from server import db
    from insights import build_pivot
    sess = await _get_by_token(db, token)
    fields = sess.get("export_fields") or []
    if not ((not fields) or ("pivot" in fields)):
        return {"enabled": False, "message": "Pivot module is not enabled for this export."}
    sheets = [s for s in sess.get("sheets", []) if s.get("connected")]
    return build_pivot(sheets, dimension=dimension, measure=measure, agg=agg,
                       include_totals=include_totals, sheet_label=sheet)


@router.get("/{token}/forecast")
async def get_forecast(token: str, periods: int = 6, date: Optional[str] = None,
                       measure: Optional[str] = None, granularity: Optional[str] = None,
                       sheet: Optional[str] = None):
    """Time-series forecast with P80/P95 bands. Needs a date column + numeric measure.
    Enabled via 'forecast'."""
    from server import db
    from forecast import build_forecast
    sess = await _get_by_token(db, token)
    fields = sess.get("export_fields") or []
    if not ((not fields) or ("forecast" in fields)):
        return {"enabled": False, "message": "Forecast module is not enabled for this export."}
    sheets = [s for s in sess.get("sheets", []) if s.get("connected")]
    return build_forecast(sheets, periods=max(1, min(36, periods)), date_col=date,
                          measure_col=measure, granularity=granularity, sheet_label=sheet)


@router.get("/{token}/anomalies")
async def get_anomalies(token: str, column: Optional[str] = None, sensitivity: str = "medium",
                        sheet: Optional[str] = None):
    """Outlier detection (robust median/MAD z-score). Enabled via 'anomalies'."""
    from server import db
    from insights import build_anomalies
    sess = await _get_by_token(db, token)
    fields = sess.get("export_fields") or []
    if not ((not fields) or ("anomalies" in fields)):
        return {"enabled": False, "message": "Anomaly module is not enabled for this export."}
    sheets = [s for s in sess.get("sheets", []) if s.get("connected")]
    return build_anomalies(sheets, column=column, sensitivity=sensitivity, sheet_label=sheet)


@router.get("/{token}/digest")
async def get_digest(token: str):
    """Executive summary computed from the data; AI-polished into prose when a key is set.
    Enabled via 'digest'."""
    from server import db
    from insights import build_digest
    sess = await _get_by_token(db, token)
    fields = sess.get("export_fields") or []
    if not ((not fields) or ("digest" in fields)):
        return {"enabled": False, "message": "Digest module is not enabled for this export."}
    sheets = [s for s in sess.get("sheets", []) if s.get("connected")]
    digest = build_digest(sheets)
    generated_by = "computed"
    summary = " ".join(digest.get("facts", [])[:8])
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("EMERGENT_LLM_KEY") or ""
    if api_key and digest.get("facts"):
        try:
            sys_prompt = ("Turn these computed dataset facts into a crisp 3-4 sentence executive summary "
                          "for a manager. Use only these facts; do not invent numbers.\n\n- " +
                          "\n- ".join(digest["facts"]))
            polished = await chat_send(api_key, str(uuid.uuid4()), sys_prompt, "Write the executive summary.")
            if polished and "disabled" not in polished.lower():
                summary = polished
                generated_by = "ai"
        except Exception:
            pass
    return {"enabled": True, "project": sess.get("name"), "generated_by": generated_by,
            "summary": summary, **digest}


@router.get("/{token}/recommendations")
async def get_recommendations(token: str):
    """Rule-based next-best-actions from quality + anomaly signals. Enabled via 'recommendations'."""
    from server import db
    from insights import build_recommendations
    sess = await _get_by_token(db, token)
    fields = sess.get("export_fields") or []
    if not ((not fields) or ("recommendations" in fields)):
        return {"enabled": False, "message": "Recommendations module is not enabled for this export."}
    sheets = [s for s in sess.get("sheets", []) if s.get("connected")]
    return {"enabled": True, "project": sess.get("name"), **build_recommendations(sheets)}


@router.get("/{token}/whatif")
async def get_whatif(token: str, dimension: Optional[str] = None, measure: Optional[str] = None,
                     adjust: Optional[str] = None, global_pct: float = 0.0, sheet: Optional[str] = None):
    """Scenario modelling. `adjust` is 'KeyA:20,KeyB:-10' (% changes); global_pct applies to all.
    Enabled via 'whatif'."""
    from server import db
    from insights import build_whatif
    sess = await _get_by_token(db, token)
    fields = sess.get("export_fields") or []
    if not ((not fields) or ("whatif" in fields)):
        return {"enabled": False, "message": "What-if module is not enabled for this export."}
    adjustments = {}
    if adjust:
        for part in adjust.split(","):
            if ":" in part:
                k, _, p = part.rpartition(":")
                try:
                    adjustments[k.strip()] = float(p)
                except ValueError:
                    pass
    sheets = [s for s in sess.get("sheets", []) if s.get("connected")]
    return build_whatif(sheets, dimension=dimension, measure=measure, adjustments=adjustments,
                        global_pct=global_pct, sheet_label=sheet)


async def _capture_snapshot(db, token, sess, sheets):
    """Upsert today's snapshot (one per token per day)."""
    from snapshots import snapshot_metrics
    today = datetime.now(timezone.utc).date().isoformat()
    rowid = f"{token}:{today}"
    doc = {"id": rowid, "token": token, "session_id": sess.get("id"), "date": today,
           "captured_at": datetime.now(timezone.utc).isoformat(), "sheets": snapshot_metrics(sheets)}
    try:
        await db.snapshots.update_one({"id": rowid}, {"$set": doc}, upsert=True)
    except Exception as e:
        logger.warning("snapshot capture failed: %s", e)


@router.get("/{token}/trends")
async def get_trends(token: str):
    """Time series + 'what changed' from daily snapshots. Captures today's on access.
    Enabled via 'trends'."""
    from server import db
    from snapshots import compute_trends
    sess = await _get_by_token(db, token)
    fields = sess.get("export_fields") or []
    if not ((not fields) or ("trends" in fields)):
        return {"enabled": False, "message": "Trends module is not enabled for this export."}
    sheets = [s for s in sess.get("sheets", []) if s.get("connected")]
    await _capture_snapshot(db, token, sess, sheets)
    snaps = []
    cur = db.snapshots.find({"token": token}).sort("date", 1)
    async for it in cur:
        snaps.append(it)
    t = compute_trends(snaps)
    ready = len(t["series"]) >= 2
    return {"enabled": True, "ready": ready, "project": sess.get("name"),
            "snapshot_count": len(t["series"]),
            "message": None if ready else "Trends need at least 2 daily snapshots. Today's is captured — check back after the next daily capture.",
            **t}


@router.post("/{token}/snapshot")
async def post_snapshot(token: str):
    """Force-capture a snapshot now (e.g. from a daily cron)."""
    from server import db
    sess = await _get_by_token(db, token)
    sheets = [s for s in sess.get("sheets", []) if s.get("connected")]
    await _capture_snapshot(db, token, sess, sheets)
    return {"ok": True, "date": datetime.now(timezone.utc).date().isoformat()}


class AlertRules(BaseModel):
    rules: list = []


@router.get("/{token}/alerts/rules")
async def get_alert_rules(token: str):
    from server import db
    sess = await _get_by_token(db, token)
    return {"rules": sess.get("export_alert_rules") or []}


@router.post("/{token}/alerts/rules")
async def set_alert_rules(token: str, payload: AlertRules):
    from server import db
    await db.sessions.update_one(
        {"public_token": token},
        {"$set": {"export_alert_rules": payload.rules,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True, "rules": payload.rules}


async def _run_alerts(db, token, sess, cur, prev):
    """Evaluate this export's alert rules, log triggered ones, and POST any webhooks."""
    from alerts import evaluate_rules
    triggered = evaluate_rules(sess.get("export_alert_rules") or [], cur, prev)
    for t in triggered:
        entry = {"id": str(uuid.uuid4()), "token": token, "type": "alert_rule",
                 "metric": t["metric"], "value": t["value"], "message": t["message"],
                 "created_at": datetime.now(timezone.utc).isoformat()}
        try:
            await db.alert_log.insert_one(entry)
        except Exception:
            pass
        if t.get("webhook_url"):
            try:
                await db.client.post(t["webhook_url"],
                                     json={"project": sess.get("name"), "token": token, "alert": t},
                                     timeout=10)
            except Exception as e:
                logger.warning("webhook failed: %s", e)
    return triggered


@router.post("/{token}/alerts/test")
async def test_alerts(token: str):
    """Evaluate alert rules against current data right now (logs + fires webhooks)."""
    from server import db
    from snapshots import snapshot_metrics
    from alerts import aggregate_metrics
    sess = await _get_by_token(db, token)
    sheets = [s for s in sess.get("sheets", []) if s.get("connected")]
    cur = aggregate_metrics(snapshot_metrics(sheets))
    prev = None
    snaps = []
    async for it in db.snapshots.find({"token": token}).sort("date", -1).limit(1):
        snaps.append(it)
    if snaps:
        prev = aggregate_metrics(snaps[0].get("sheets", []))
    triggered = await _run_alerts(db, token, sess, cur, prev)
    return {"ok": True, "current": cur, "triggered": triggered, "count": len(triggered)}


# -------- Concerns --------
@router.post("/{token}/concerns")
async def create_concern(token: str, payload: ConcernCreate):
    """Raise a concern against another department. Also refreshes the people/department
    directory from the connected sheets. Enabled via 'concerns'."""
    from server import db
    sess = await _get_by_token(db, token)
    if not _want_field(sess, "concerns"):
        return {"enabled": False, "message": "Concerns module is not enabled for this export."}
    sheets = [s for s in sess.get("sheets", []) if s.get("connected")]
    try:
        people, departments = extract_people(sheets)
        await upsert_people_and_departments(db, people, departments, token)
    except Exception as e:
        logger.warning("people extraction failed: %s", e)
    concern_id = str(uuid.uuid4())
    doc = {
        "id": concern_id,
        "token": token,
        "raised_by": payload.raised_by,
        "raised_by_department": payload.raised_by_department,
        "target_department": payload.target_department,
        "sheet_label": payload.sheet_label,
        "activity_ref": payload.activity_ref,
        "title": payload.title,
        "detail": payload.detail,
        "severity": payload.severity or "medium",
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.concerns.insert_one(doc)
    return {"ok": True, "id": concern_id, "status": "open"}


@router.get("/{token}/concerns")
async def list_concerns(token: str, status: Optional[str] = None, department: Optional[str] = None):
    """List concerns for this export, plus a per-department open/ack/resolved/total
    summary from the dbridge_concerns_by_department view. Enabled via 'concerns'."""
    from server import db
    sess = await _get_by_token(db, token)
    if not _want_field(sess, "concerns"):
        return {"enabled": False, "message": "Concerns module is not enabled for this export."}

    concerns = []
    async for c in db.concerns.find({"token": token}, {"_id": 0}):
        if status and (c.get("status") or "open") != status:
            continue
        if department and c.get("target_department") != department:
            continue
        concerns.append(c)

    by_department: Dict[str, Any] = {}
    try:
        rows = await db.raw_select("dbridge_concerns_by_department", {"token": token})
        for r in rows:
            dept = r.get("department")
            if dept is None:
                continue
            by_department[dept] = {
                "open": r.get("open") or 0,
                "ack": r.get("ack") or 0,
                "resolved": r.get("resolved") or 0,
                "total": r.get("total") or 0,
            }
    except Exception as e:
        logger.warning("concerns_by_department query failed: %s", e)

    return {"enabled": True, "concerns": concerns, "by_department": by_department}


@router.patch("/{token}/concerns/{concern_id}")
async def update_concern(token: str, concern_id: str, payload: ConcernUpdate):
    """Update a concern's status (open/ack/resolved) and append an audit row to db.actions.
    Enabled via 'concerns'."""
    from server import db
    sess = await _get_by_token(db, token)
    if not _want_field(sess, "concerns"):
        return {"enabled": False, "message": "Concerns module is not enabled for this export."}
    concern = await db.concerns.find_one({"id": concern_id, "token": token})
    if not concern:
        raise HTTPException(status_code=404, detail="Concern not found.")
    now = datetime.now(timezone.utc).isoformat()
    await db.concerns.update_one({"id": concern_id}, {"$set": {"status": payload.status, "updated_at": now}})
    await db.actions.insert_one({
        "id": str(uuid.uuid4()),
        "token": token,
        "concern_id": concern_id,
        "type": "concern_status_change",
        "status": payload.status,
        "note": payload.note,
        "created_at": now,
    })
    return {"ok": True, "id": concern_id, "status": payload.status}


# -------- Reminders --------
@router.get("/{token}/reminders")
async def list_reminders(token: str, status: Optional[str] = None):
    """List scheduled reminders for this export. Enabled via 'concerns'."""
    from server import db
    sess = await _get_by_token(db, token)
    if not _want_field(sess, "concerns"):
        return {"enabled": False, "message": "Reminders module is not enabled for this export."}
    reminders = []
    async for r in db.reminders.find({"token": token}, {"_id": 0}):
        if status and (r.get("status") or "pending") != status:
            continue
        reminders.append(r)
    return {"enabled": True, "reminders": reminders}


@router.post("/{token}/reminders")
async def create_reminder(token: str, payload: ReminderCreate):
    """Schedule an email reminder; sent by the /api/cron/snapshot reminder pass.
    Enabled via 'concerns'."""
    from server import db
    sess = await _get_by_token(db, token)
    if not _want_field(sess, "concerns"):
        return {"enabled": False, "message": "Reminders module is not enabled for this export."}
    reminder_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": reminder_id,
        "token": token,
        "related_type": payload.related_type,
        "related_id": payload.related_id,
        "recipient_email": payload.recipient_email,
        "subject": payload.subject,
        "body": payload.body,
        "schedule_at": payload.schedule_at or now,
        "recurrence": payload.recurrence or "none",
        "status": "pending",
        "created_at": now,
    }
    await db.reminders.insert_one(doc)
    return {"ok": True, "id": reminder_id}


# -------- Column map --------
@router.get("/{token}/column-map")
async def get_column_map(token: str):
    """Detected owner/department/email/status/date columns for each connected sheet.
    Enabled via 'concerns'."""
    from server import db
    sess = await _get_by_token(db, token)
    if not _want_field(sess, "concerns"):
        return {"enabled": False, "message": "Column-map module is not enabled for this export."}
    sheets = [s for s in sess.get("sheets", []) if s.get("connected")]
    out: Dict[str, Any] = {}
    for s in sheets:
        rows = s.get("rows_raw") or []
        headers = list(rows[0].keys()) if rows else (s.get("headers") or [])
        out[s.get("label")] = column_map(headers)
    return {"enabled": True, **out}


# -------- Harmonize --------
def _harmonize_deterministic(sheets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flag columns whose detected role (owner/dept/email/status/date) uses a different
    header name than the most common name for that role across sheets."""
    from collections import Counter
    maps = {}
    for s in sheets:
        rows = s.get("rows_raw") or []
        headers = list(rows[0].keys()) if rows else (s.get("headers") or [])
        maps[s.get("label")] = column_map(headers)

    suggestions: List[Dict[str, Any]] = []
    for role in ("owner", "dept", "email", "status", "date"):
        names = Counter(cmap[role] for cmap in maps.values() if cmap.get(role))
        if len(names) <= 1:
            continue
        canonical, _ = names.most_common(1)[0]
        for label, cmap in maps.items():
            col = cmap.get(role)
            if col and col != canonical:
                suggestions.append({
                    "sheet_label": label,
                    "column": col,
                    "issue": f"Column name for '{role}' differs from other sheets",
                    "current": col,
                    "suggested": canonical,
                })
    return suggestions


def _parse_harmonize_json(raw: str):
    import json as _json
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = _json.loads(text)
    except Exception:
        return None
    return data if isinstance(data, list) else None


@router.get("/{token}/harmonize")
async def get_harmonize(token: str):
    """Compare column headings + item descriptions across connected sheets and suggest
    consistent naming. Uses the AI copilot when an API key is set, else a deterministic
    heuristic based on detected column roles. Enabled via 'harmonize'."""
    from server import db
    from copilot import build_sheet_context
    sess = await _get_by_token(db, token)
    if not _want_field(sess, "harmonize"):
        return {"enabled": False, "message": "Harmonize module is not enabled for this export."}
    sheets = [s for s in sess.get("sheets", []) if s.get("connected")]
    if len(sheets) < 2:
        return {"enabled": True, "generated_by": "computed", "suggestions": [],
                "message": "Harmonize needs 2+ connected sheets."}

    suggestions = _harmonize_deterministic(sheets)
    generated_by = "computed"
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("EMERGENT_LLM_KEY") or ""
    if api_key:
        try:
            ctx = build_sheet_context(sheets, max_sample=5)
            sys_prompt = (
                "Compare the column headings and item/activity descriptions across these sheets. "
                "Identify inconsistent naming for the same concept (e.g. 'Status' vs 'State', "
                "'Resp Person' vs 'Owner', or differently-worded descriptions for the same activity). "
                "Return ONLY a JSON array (no prose, no markdown fences) of objects with keys: "
                "sheet_label, column, issue, current, suggested.\n\n" + ctx["text"]
            )
            raw = await chat_send(api_key, str(uuid.uuid4()), sys_prompt, "Return the JSON array now.")
            parsed = _parse_harmonize_json(raw)
            if parsed is not None:
                suggestions = parsed
                generated_by = "ai"
        except Exception as e:
            logger.warning("harmonize AI failed: %s", e)

    return {"enabled": True, "generated_by": generated_by, "suggestions": suggestions}


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
    api_key = os.environ.get("EMERGENT_LLM_KEY") or os.environ.get("ANTHROPIC_API_KEY") or ""
    # No hard failure if unset — chat_send returns a graceful 'disabled' message.

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


@router.post("/{token}/copilot")
async def copilot(token: str, payload: CopilotRequest, sheet: Optional[str] = None):
    """Sheet-grounded AI Q&A. Answers from server-computed exact aggregates + a data sample.
    Pass ?sheet=<label> to ground answers on one selected sheet, or `sheets: [labels]` in the
    body to combine context across multiple sheets (requires 'multi_copilot').
    Enabled when 'copilot' is selected in configure-export (or no field filter is set)."""
    from server import db
    from copilot import build_sheet_context, build_copilot_system_prompt
    sess = await _get_by_token(db, token)
    if not _want_field(sess, "copilot"):
        return {"enabled": False, "answer": "The Copilot module is not enabled for this export."}
    all_sheets = [s for s in sess.get("sheets", []) if s.get("connected")]

    if payload.sheets:
        if not _want_field(sess, "multi_copilot"):
            return {"enabled": False, "answer": "Multi-sheet copilot is not enabled for this export."}
        sheets = [s for s in all_sheets if s.get("label") in payload.sheets] or all_sheets
    elif sheet:
        sheets = [s for s in all_sheets if s.get("label") == sheet] or all_sheets
    else:
        sheets = all_sheets

    if not sheets:
        return {"enabled": True, "answer": "No connected sheets to answer from yet.", "used_sheets": []}

    used_sheets = [s.get("label") for s in sheets]
    ctx = build_sheet_context(sheets)
    if len(sheets) > 1:
        scope = f" (combining sheets {', '.join(used_sheets)})"
    elif sheet and len(sheets) == 1:
        scope = f" (focused on sheet '{sheet}')"
    else:
        scope = ""
    system_prompt = build_copilot_system_prompt(ctx["text"], (sess.get("name") or "this dataset") + scope)
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("EMERGENT_LLM_KEY") or ""
    chat_session_id = payload.session_id or str(uuid.uuid4())
    if api_key:
        answer = await chat_send(api_key, chat_session_id, system_prompt, payload.message)
        generated_by = "ai"
    else:
        from copilot import answer_locally
        answer = answer_locally(payload.message, sheets)
        generated_by = "computed"
    return {
        "enabled": True,
        "session_id": chat_session_id,
        "question": payload.message,
        "answer": answer,
        "generated_by": generated_by,
        "profile": ctx["profile"],
        "used_sheets": used_sheets,
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

# ── Header detection support ──────────────────────────────────────────────────

@router.get("/{token}/raw-head")
async def get_raw_head(token: str, sheet: str = "", rows: int = 10):
    from server import db
    sess = await _get_by_token(db, token)
    sheets = [s for s in sess.get("sheets", []) if s.get("connected")]
    if sheet:
        target = next((s for s in sheets if s["label"] == sheet), None)
    else:
        target = sheets[0] if sheets else None
    if not target:
        raise HTTPException(status_code=404, detail="Sheet not found.")
    rows_raw = (target.get("rows_raw") or [])[:max(1, min(rows, 50))]
    if not rows_raw:
        return {"sheet": sheet or target["label"], "raw_rows": [], "keys": []}
    keys = list(rows_raw[0].keys())
    raw_rows = [[r.get(k) for k in keys] for r in rows_raw]
    return {"sheet": target["label"], "keys": keys, "raw_rows": raw_rows}


class HeaderMappingCreate(BaseModel):
    sheet_label: str
    header_row_index: Optional[int] = None
    column_overrides: Optional[Dict[str, Any]] = None


@router.post("/{token}/header-mapping")
async def upsert_header_mapping(token: str, payload: HeaderMappingCreate):
    from server import db
    from datetime import datetime, timezone
    await _get_by_token(db, token)
    record_id = f"{token}__{payload.sheet_label}"
    record = {
        "id": record_id,
        "token": token,
        "sheet_label": payload.sheet_label,
        "header_row_index": payload.header_row_index,
        "column_overrides": payload.column_overrides or {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.raw_upsert("dbridge_header_mappings", record)
    return {"ok": True, "id": record_id}
