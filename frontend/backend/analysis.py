"""Delay analysis: reason classification, correlation, dependency chains, person/dept/timeline ranks."""
from typing import List, Dict, Any, Tuple
from collections import defaultdict, Counter
from datetime import datetime
import re

REASON_BUCKETS = [
    "Approval Pending",
    "Resource Unavailable",
    "Dependency Not Cleared",
    "External Factor",
    "Design Change",
    "Documentation Missing",
    "Other",
]

REASON_KEYWORDS = {
    "Approval Pending": [
        "approval", "approve", "sign-off", "signoff", "sign off", "pending sign", "authoris",
        "authoriz", "clearance pending", "awaiting approval",
    ],
    "Resource Unavailable": [
        "resource", "manpower", "staff", "unavailable", "leave", "absent", "shortage",
        "no team", "not available",
    ],
    "Dependency Not Cleared": [
        "dependency", "depends on", "blocked by", "upstream", "predecessor", "waiting for",
        "prerequisite", "linked task",
    ],
    "External Factor": [
        "weather", "rain", "monsoon", "government", "govt", "vendor", "supplier delay",
        "force majeure", "regulatory", "license", "permit", "court", "strike",
    ],
    "Design Change": [
        "design change", "scope change", "revision", "rework", "redesign", "spec change",
        "drawing change", "requirement change",
    ],
    "Documentation Missing": [
        "document", "documentation", "missing doc", "paperwork", "form", "report missing",
        "certificate", "boq", "invoice missing",
    ],
}


def classify_reason(text: str) -> str:
    if not text:
        return "Other"
    low = text.lower()
    scores: Dict[str, int] = {}
    for bucket, kws in REASON_KEYWORDS.items():
        score = sum(1 for k in kws if k in low)
        if score:
            scores[bucket] = score
    if scores:
        return max(scores.items(), key=lambda kv: kv[1])[0]
    return "Other"


def is_delayed(row: Dict[str, Any]) -> bool:
    """A row is currently delayed/blocking if it is NOT completed AND
    (explicit Delayed status OR running over TAT)."""
    if row.get("status") == "Completed":
        return False
    if row.get("status") == "Delayed":
        return True
    tat = row.get("tat")
    dt = row.get("days_taken")
    if tat is not None and dt is not None and tat > 0 and dt > tat:
        return True
    return False


def annotate_reasons(rows: List[Dict[str, Any]]) -> None:
    """Mutates rows to add reason_class."""
    for r in rows:
        r["reason_class"] = classify_reason(r.get("reason", ""))


def correlation_matrix(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Co-occurrence of reason classes within the same Stage (dept)."""
    by_stage: Dict[str, List[str]] = defaultdict(list)
    for r in rows:
        if is_delayed(r):
            by_stage[r.get("stage") or "Unknown"].append(r.get("reason_class") or "Other")
    pair_counts: Counter = Counter()
    reason_count: Counter = Counter()
    for stage, reasons in by_stage.items():
        unique = list(set(reasons))
        for r in unique:
            reason_count[r] += reasons.count(r)
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                key = tuple(sorted([unique[i], unique[j]]))
                pair_counts[key] += 1
    matrix = []
    reasons = REASON_BUCKETS
    for a in reasons:
        row = []
        for b in reasons:
            if a == b:
                row.append(reason_count.get(a, 0))
            else:
                key = tuple(sorted([a, b]))
                row.append(pair_counts.get(key, 0))
        matrix.append({"reason": a, "values": row})
    return {"axis": reasons, "matrix": matrix}


def _key(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def dependency_chains(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build chain map. Each row's dependency strings are matched to other row activities by name."""
    by_name: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        k = _key(r.get("activity") or "")
        if k:
            by_name[k] = r

    # Adjacency: activity -> list of activities that depend on it (downstream)
    downstream: Dict[str, List[str]] = defaultdict(list)
    upstream: Dict[str, List[str]] = defaultdict(list)
    for r in rows:
        me_k = _key(r.get("activity") or "")
        for dep in r.get("dependency") or []:
            dep_k = _key(dep)
            if dep_k and dep_k in by_name and dep_k != me_k:
                downstream[dep_k].append(me_k)
                upstream[me_k].append(dep_k)

    delayed_keys = {_key(r["activity"]) for r in rows if r.get("activity") and is_delayed(r)}

    # For each delayed activity, BFS downstream to find at-risk
    at_risk: Dict[str, Dict[str, Any]] = {}  # key -> info
    chains: List[Dict[str, Any]] = []
    for start in delayed_keys:
        if start not in by_name:
            continue
        seen = {start}
        stack = [(start, [start], 0.0)]
        chain_nodes: List[Dict[str, Any]] = []
        accumulated = 0.0
        while stack:
            node, path, acc = stack.pop()
            r = by_name.get(node)
            if not r:
                continue
            overdue = float(r.get("overdue_days") or 0.0)
            new_acc = acc + overdue
            chain_nodes.append({
                "key": node,
                "activity": r.get("activity"),
                "person": r.get("responsible_person"),
                "email": r.get("responsible_email"),
                "status": r.get("status"),
                "reason": r.get("reason_class"),
                "overdue_days": overdue,
                "accumulated_days": new_acc,
                "path_depth": len(path) - 1,
            })
            accumulated = max(accumulated, new_acc)
            for child in downstream.get(node, []):
                if child in seen:
                    continue
                seen.add(child)
                stack.append((child, path + [child], new_acc))
                if child != start:
                    cr = by_name.get(child)
                    if cr:
                        at_risk.setdefault(child, {
                            "activity": cr.get("activity"),
                            "person": cr.get("responsible_person"),
                            "email": cr.get("responsible_email"),
                            "blocked_by": [],
                        })["blocked_by"].append(by_name[start].get("activity"))
        if len(chain_nodes) > 1:
            chains.append({
                "root_activity": by_name[start].get("activity"),
                "root_person": by_name[start].get("responsible_person"),
                "root_reason": by_name[start].get("reason_class"),
                "downstream_count": len(chain_nodes) - 1,
                "accumulated_days": round(accumulated, 1),
                "nodes": chain_nodes,
            })

    chains.sort(key=lambda c: (c["downstream_count"], c["accumulated_days"]), reverse=True)
    critical_path = chains[0] if chains else None

    return {
        "chains": chains,
        "critical_path": critical_path,
        "at_risk_activities": list(at_risk.values()),
    }


def person_ranking(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bucket: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if not is_delayed(r):
            continue
        person = r.get("responsible_person") or "Unknown"
        rec = bucket.setdefault(person, {
            "person": person,
            "email": r.get("responsible_email"),
            "phone": r.get("responsible_phone"),
            "delay_count": 0,
            "total_overdue_days": 0.0,
            "reasons": Counter(),
            "activities": [],
        })
        rec["delay_count"] += 1
        rec["total_overdue_days"] += float(r.get("overdue_days") or 0)
        rec["reasons"][r.get("reason_class") or "Other"] += 1
        rec["activities"].append(r.get("activity"))
    out = []
    for v in bucket.values():
        v["reasons"] = dict(v["reasons"])
        v["total_overdue_days"] = round(v["total_overdue_days"], 1)
        out.append(v)
    out.sort(key=lambda x: (x["delay_count"], x["total_overdue_days"]), reverse=True)
    return out


def department_ranking(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bucket: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if not is_delayed(r):
            continue
        dept = r.get("stage") or "Unknown"
        rec = bucket.setdefault(dept, {
            "department": dept,
            "delay_count": 0,
            "total_overdue_days": 0.0,
            "reasons": Counter(),
        })
        rec["delay_count"] += 1
        rec["total_overdue_days"] += float(r.get("overdue_days") or 0)
        rec["reasons"][r.get("reason_class") or "Other"] += 1
    out = []
    for v in bucket.values():
        v["reasons"] = dict(v["reasons"])
        v["total_overdue_days"] = round(v["total_overdue_days"], 1)
        out.append(v)
    out.sort(key=lambda x: (x["delay_count"], x["total_overdue_days"]), reverse=True)
    return out


def timeline_correlation(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    weekly: Counter = Counter()
    monthly: Counter = Counter()
    for r in rows:
        if not is_delayed(r):
            continue
        sd = r.get("start_date")
        if not sd:
            continue
        try:
            d = datetime.fromisoformat(str(sd).replace("Z", "+00:00"))
        except Exception:
            try:
                d = datetime.strptime(str(sd)[:10], "%Y-%m-%d")
            except Exception:
                continue
        iso_year, iso_week, _ = d.isocalendar()
        weekly[f"{iso_year}-W{iso_week:02d}"] += 1
        monthly[d.strftime("%Y-%m")] += 1
    return {
        "weekly": [{"period": k, "delays": v} for k, v in sorted(weekly.items())],
        "monthly": [{"period": k, "delays": v} for k, v in sorted(monthly.items())],
    }


def status_breakdown(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    c: Counter = Counter()
    for r in rows:
        c[r.get("status") or "Unknown"] += 1
    return dict(c)


def top_delay_reasons(rows: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
    c: Counter = Counter()
    days: Dict[str, float] = defaultdict(float)
    for r in rows:
        if is_delayed(r):
            reason = r.get("reason_class") or "Other"
            c[reason] += 1
            days[reason] += float(r.get("overdue_days") or 0)
    out = []
    for reason, count in c.most_common(top_n):
        out.append({
            "reason": reason,
            "count": count,
            "total_overdue_days": round(days[reason], 1),
        })
    return out


def risk_score(rows: List[Dict[str, Any]], deps: Dict[str, Any]) -> int:
    total = len(rows) or 1
    delayed = sum(1 for r in rows if is_delayed(r))
    blocked = len(deps.get("at_risk_activities", []))
    critical_delayed = sum(1 for r in rows if is_delayed(r) and r.get("criticality") == "Critical")
    delay_ratio = delayed / total
    block_ratio = blocked / total
    crit_ratio = critical_delayed / max(1, sum(1 for r in rows if r.get("criticality") == "Critical"))
    raw = delay_ratio * 40 + block_ratio * 35 + crit_ratio * 25
    return int(round(min(100.0, raw * 100)))


def analyze_single_sheet(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run all delay analysis on normalized rows."""
    annotate_reasons(rows)
    deps = dependency_chains(rows)
    return {
        "status_breakdown": status_breakdown(rows),
        "correlation_matrix": correlation_matrix(rows),
        "dependency_chains": deps,
        "person_ranking": person_ranking(rows),
        "department_ranking": department_ranking(rows),
        "timeline_correlation": timeline_correlation(rows),
        "top_delay_reasons": top_delay_reasons(rows),
        "risk_score": risk_score(rows, deps),
        "totals": {
            "rows": len(rows),
            "delayed": sum(1 for r in rows if is_delayed(r)),
            "blocked": len(deps.get("at_risk_activities", [])),
            "completed": sum(1 for r in rows if r.get("status") == "Completed"),
            "at_risk": len(deps.get("at_risk_activities", [])),
        },
    }
