"""Flag generation from delay analysis and variance results."""
from typing import List, Dict, Any
from datetime import datetime, timezone
import uuid

from analysis import is_delayed


def _severity(overdue: float, criticality: str) -> str:
    if criticality == "Critical" or overdue >= 48:
        return "Critical"
    if overdue >= 24:
        return "High"
    return "Medium"


def generate_flags(
    primary_rows: List[Dict[str, Any]],
    deps: Dict[str, Any],
    variance: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """Create flags for delayed activities; attach downstream impact; add variance flags."""
    flags: List[Dict[str, Any]] = []

    # Build downstream lookup from deps.chains: root_activity -> list of nodes
    downstream_map: Dict[str, List[Dict[str, Any]]] = {}
    for chain in deps.get("chains", []) if deps else []:
        root = (chain.get("root_activity") or "").lower().strip()
        if not root:
            continue
        nodes = [n for n in chain.get("nodes", []) if n.get("activity")
                 and (n.get("activity") or "").lower().strip() != root]
        downstream_map[root] = nodes

    counter = 1
    for r in primary_rows:
        if not is_delayed(r):
            continue
        activity = r.get("activity") or "Unknown Activity"
        overdue = float(r.get("overdue_days") or 0)
        criticality = r.get("criticality") or "Normal"
        severity = _severity(overdue, criticality)
        ds_nodes = downstream_map.get(activity.lower().strip(), [])
        downstream_persons = []
        for n in ds_nodes:
            if n.get("person") and n.get("activity"):
                downstream_persons.append({
                    "person": n.get("person"),
                    "email": n.get("email"),
                    "activity": n.get("activity"),
                })

        flags.append({
            "id": f"FLAG-{counter:03d}",
            "uid": str(uuid.uuid4()),
            "type": "delay",
            "activity": activity,
            "flagged_to": {
                "person": r.get("responsible_person"),
                "email": r.get("responsible_email"),
                "phone": r.get("responsible_phone"),
            },
            "reason": r.get("reason_class") or "Other",
            "reason_text": r.get("reason"),
            "tat": r.get("tat"),
            "days_taken": r.get("days_taken"),
            "overdue_days": round(overdue, 1),
            "dependency_impact_count": len(ds_nodes),
            "downstream_persons": downstream_persons,
            "severity": severity,
            "status": "Open",
            "stage": r.get("stage"),
            "criticality": criticality,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "escalation_level": 1,
            "acknowledged_at": None,
            "resolved_at": None,
        })
        counter += 1

    # Variance flags (only multi-sheet)
    if variance:
        for vrow in variance.get("variance_rows", []):
            if vrow.get("flag") == "red" and vrow.get("max_variance_pct", 0) > 50:
                flags.append({
                    "id": f"FLAG-{counter:03d}",
                    "uid": str(uuid.uuid4()),
                    "type": "variance",
                    "activity": vrow.get("activity"),
                    "flagged_to": {"person": None, "email": None, "phone": None},
                    "reason": "Cross-sheet Variance",
                    "reason_text": f"Max variance {vrow.get('max_variance_pct')}% across sheets",
                    "variance_detail": vrow,
                    "severity": "High",
                    "status": "Open",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "escalation_level": 1,
                    "downstream_persons": [],
                    "dependency_impact_count": 0,
                    "acknowledged_at": None,
                    "resolved_at": None,
                })
                counter += 1

    return flags


def downstream_for_email(
    email: str, flags: List[Dict[str, Any]], rows: List[Dict[str, Any]], deps: Dict[str, Any]
) -> Dict[str, Any]:
    """Return what is blocking the given person's activities."""
    if not email:
        return {"email": None, "blocked": [], "message": "No email provided."}
    email_l = email.strip().lower()
    my_rows = [r for r in rows if (r.get("responsible_email") or "").lower() == email_l]
    if not my_rows:
        # try by name fallback
        my_rows = [r for r in rows if (r.get("responsible_person") or "").lower() == email_l]

    blocked: List[Dict[str, Any]] = []
    for my in my_rows:
        my_act_key = (my.get("activity") or "").strip().lower()
        # find chains where my activity appears as a downstream node
        for chain in deps.get("chains", []) if deps else []:
            for node in chain.get("nodes", []):
                if (node.get("activity") or "").strip().lower() == my_act_key and node.get("path_depth", 0) > 0:
                    blocked.append({
                        "your_activity": my.get("activity"),
                        "your_due_in_days": my.get("tat"),
                        "blocking_activity": chain.get("root_activity"),
                        "blocker_person": chain.get("root_person"),
                        "reason": chain.get("root_reason"),
                        "overdue_days": chain.get("nodes", [{}])[0].get("overdue_days"),
                    })

    return {
        "email": email,
        "activities": [
            {"activity": r.get("activity"), "status": r.get("status"), "tat": r.get("tat")}
            for r in my_rows
        ],
        "blocked": blocked,
    }
