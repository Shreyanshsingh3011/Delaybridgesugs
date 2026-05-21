"""Dependency Mapping Studio routes."""
import os
import uuid
import secrets
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Set, Tuple
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user
from sheet_fetcher import fetch_apps_script

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/studio")


# -------- Models --------
class NodeIn(BaseModel):
    id: str
    type: Optional[str] = "custom"
    position: Dict[str, float] = Field(default_factory=lambda: {"x": 0, "y": 0})
    data: Dict[str, Any] = Field(default_factory=dict)
    style: Optional[Dict[str, Any]] = None
    width: Optional[float] = None
    height: Optional[float] = None


class EdgeIn(BaseModel):
    id: str
    source: str
    target: str
    type: Optional[str] = "dependency"
    label: Optional[str] = None
    animated: Optional[bool] = True
    data: Dict[str, Any] = Field(default_factory=dict)
    style: Optional[Dict[str, Any]] = None


class MapCreate(BaseModel):
    title: str = "Untitled Architecture Map"


class MapSave(BaseModel):
    title: Optional[str] = None
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    source_url: Optional[str] = None
    notes: Optional[str] = None


class ShareConfig(BaseModel):
    mode: str = "public"  # public | private | readonly | editable


class FetchRequest(BaseModel):
    url: str


# -------- Helpers --------
async def _get_map(db, map_id: str, owner_id: str) -> Dict[str, Any]:
    m = await db.studio_maps.find_one({"id": map_id, "owner_id": owner_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Map not found.")
    return m


async def _get_map_by_token(db, token: str) -> Dict[str, Any]:
    m = await db.studio_maps.find_one({"share_token": token}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Shared map not found.")
    if m.get("share_mode") == "private":
        raise HTTPException(status_code=403, detail="This map is private.")
    return m


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# -------- Analytics --------
def analyze_graph(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Dict[str, Any]:
    node_ids: Set[str] = {n["id"] for n in nodes}
    adj: Dict[str, List[str]] = defaultdict(list)
    rev_adj: Dict[str, List[str]] = defaultdict(list)
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s in node_ids and t in node_ids:
            adj[s].append(t)
            rev_adj[t].append(s)

    in_deg: Dict[str, int] = {nid: len(rev_adj.get(nid, [])) for nid in node_ids}
    out_deg: Dict[str, int] = {nid: len(adj.get(nid, [])) for nid in node_ids}

    # Orphans: 0 in + 0 out
    orphans = [nid for nid in node_ids if in_deg[nid] == 0 and out_deg[nid] == 0]

    # Roots / sinks
    roots = [nid for nid in node_ids if in_deg[nid] == 0 and out_deg[nid] > 0]
    sinks = [nid for nid in node_ids if out_deg[nid] == 0 and in_deg[nid] > 0]

    # Cycle detection (Tarjan-lite via DFS)
    color: Dict[str, int] = {nid: 0 for nid in node_ids}  # 0=white,1=gray,2=black
    cycles: List[List[str]] = []
    stack: List[str] = []

    def dfs(u: str) -> None:
        color[u] = 1
        stack.append(u)
        for v in adj.get(u, []):
            if color.get(v, 0) == 0:
                dfs(v)
            elif color.get(v) == 1:
                # cycle from v..u
                if v in stack:
                    i = stack.index(v)
                    cycles.append(stack[i:] + [v])
        stack.pop()
        color[u] = 2

    for nid in node_ids:
        if color[nid] == 0:
            try:
                dfs(nid)
            except RecursionError:
                pass

    # De-dup cycles by sorted tuple
    uniq_cycles: List[List[str]] = []
    seen: Set[Tuple[str, ...]] = set()
    for c in cycles:
        key = tuple(sorted(set(c)))
        if key not in seen and len(key) > 1:
            seen.add(key)
            uniq_cycles.append(c)

    # Topological order (Kahn) on a DAG (ignoring cycles)
    indeg = {nid: in_deg[nid] for nid in node_ids}
    q = deque([nid for nid in node_ids if indeg[nid] == 0])
    topo: List[str] = []
    indeg_local = dict(indeg)
    while q:
        u = q.popleft()
        topo.append(u)
        for v in adj.get(u, []):
            indeg_local[v] -= 1
            if indeg_local[v] == 0:
                q.append(v)
    has_full_topo = len(topo) == len(node_ids)

    # Bottlenecks: top by (in+out) degree
    deg = [
        {
            "id": nid,
            "in": in_deg[nid],
            "out": out_deg[nid],
            "total": in_deg[nid] + out_deg[nid],
        }
        for nid in node_ids
    ]
    deg.sort(key=lambda x: x["total"], reverse=True)
    bottlenecks = [d for d in deg[:5] if d["total"] >= 4]

    # Excessive coupling: > 6 connections
    high_coupling = [d for d in deg if d["total"] > 6]

    # Redundant: duplicate edges (same source,target)
    pair_count = defaultdict(int)
    for e in edges:
        pair_count[(e.get("source"), e.get("target"))] += 1
    redundant = [
        {"source": s, "target": t, "count": c}
        for (s, t), c in pair_count.items() if c > 1
    ]

    # Broken chain: edges referencing missing node ids
    broken = [
        {"id": e.get("id"), "source": e.get("source"), "target": e.get("target")}
        for e in edges
        if e.get("source") not in node_ids or e.get("target") not in node_ids
    ]

    # Risky patterns by node category
    cat_lookup: Dict[str, str] = {
        n["id"]: ((n.get("data") or {}).get("category") or "").lower()
        for n in nodes
    }
    bad_pairs: List[Dict[str, Any]] = []
    for e in edges:
        cs = cat_lookup.get(e.get("source"), "")
        ct = cat_lookup.get(e.get("target"), "")
        if ("ui" in cs or "frontend" in cs) and ("database" in ct or "db" in ct):
            bad_pairs.append({
                "source": e.get("source"),
                "target": e.get("target"),
                "issue": "Frontend/UI directly accessing Database",
            })

    # Scores 0-100
    n_total = max(1, len(node_ids))
    cycle_penalty = min(40, len(uniq_cycles) * 15)
    orphan_penalty = min(20, len(orphans) * 4)
    coupling_penalty = min(20, len(high_coupling) * 5)
    pattern_penalty = min(20, len(bad_pairs) * 5)
    redundant_penalty = min(10, len(redundant) * 3)
    health = max(0, 100 - cycle_penalty - orphan_penalty - coupling_penalty - pattern_penalty - redundant_penalty)

    avg_deg = sum(d["total"] for d in deg) / n_total if n_total else 0
    dependency_score = min(100, int(avg_deg * 15))

    complexity_score = min(
        100,
        int(
            len(edges) * 1.5
            + len(node_ids) * 0.8
            + len(uniq_cycles) * 10
            + len(high_coupling) * 5
        ),
    )

    # Insights (rule-based)
    insights: List[Dict[str, str]] = []
    if uniq_cycles:
        insights.append({
            "severity": "danger",
            "text": f"Circular dependency detected involving {len(uniq_cycles)} cycle(s). Break the loop or extract a shared service.",
        })
    if orphans:
        insights.append({
            "severity": "warning",
            "text": f"{len(orphans)} orphan node(s) — connect them or remove if unused.",
        })
    if bottlenecks:
        first = bottlenecks[0]
        name = next((n.get("data", {}).get("name") or n["id"] for n in nodes if n["id"] == first["id"]), first["id"])
        insights.append({
            "severity": "warning",
            "text": f"\"{name}\" is a critical bottleneck — {first['in']} incoming and {first['out']} outgoing dependencies.",
        })
    if high_coupling:
        insights.append({
            "severity": "warning",
            "text": f"{len(high_coupling)} node(s) show excessive coupling (>6 connections). Consider splitting responsibilities.",
        })
    if redundant:
        insights.append({
            "severity": "info",
            "text": f"{len(redundant)} redundant edge(s) — duplicate links between the same pair of nodes.",
        })
    for bp in bad_pairs:
        sname = next((n.get("data", {}).get("name") or n["id"] for n in nodes if n["id"] == bp["source"]), bp["source"])
        tname = next((n.get("data", {}).get("name") or n["id"] for n in nodes if n["id"] == bp["target"]), bp["target"])
        insights.append({
            "severity": "danger",
            "text": f"\"{sname}\" is directly accessing \"{tname}\" — {bp['issue']}.",
        })
    if has_full_topo and not uniq_cycles and len(node_ids) > 3:
        insights.append({
            "severity": "success",
            "text": f"Clean directed-acyclic architecture with {len(node_ids)} nodes and {len(edges)} edges.",
        })
    if not insights:
        insights.append({"severity": "info", "text": "No issues detected yet — keep mapping or add more edges."})

    return {
        "nodes": len(node_ids),
        "edges": len(edges),
        "in_degree": in_deg,
        "out_degree": out_deg,
        "orphans": orphans,
        "roots": roots,
        "sinks": sinks,
        "cycles": uniq_cycles,
        "bottlenecks": bottlenecks,
        "high_coupling": high_coupling,
        "redundant": redundant,
        "broken_edges": broken,
        "bad_patterns": bad_pairs,
        "topological_order": topo if has_full_topo else None,
        "is_dag": has_full_topo and not uniq_cycles,
        "scores": {
            "health": health,
            "dependency": dependency_score,
            "complexity": complexity_score,
        },
        "insights": insights,
    }


# -------- Endpoints --------
@router.post("/fetch")
async def studio_fetch(payload: FetchRequest, current=Depends(get_current_user)):
    """Fetch records from an Apps Script Web App URL."""
    ok, msg, rows = fetch_apps_script(payload.url)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"count": len(rows), "rows": rows, "message": msg}


@router.post("/maps")
async def create_map(payload: MapCreate, current=Depends(get_current_user)):
    from server import db
    mid = str(uuid.uuid4())
    share_token = secrets.token_urlsafe(16)
    doc = {
        "id": mid,
        "owner_id": current["id"],
        "owner_email": current.get("email"),
        "title": payload.title,
        "nodes": [],
        "edges": [],
        "source_url": None,
        "notes": None,
        "share_token": share_token,
        "share_mode": "private",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.studio_maps.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/maps")
async def list_maps(current=Depends(get_current_user)):
    from server import db
    cur = db.studio_maps.find({"owner_id": current["id"]}, {"_id": 0}).sort("updated_at", -1)
    out: List[Dict[str, Any]] = []
    async for m in cur:
        out.append({
            "id": m["id"],
            "title": m.get("title"),
            "nodes_count": len(m.get("nodes", [])),
            "edges_count": len(m.get("edges", [])),
            "share_token": m.get("share_token"),
            "share_mode": m.get("share_mode"),
            "created_at": m.get("created_at"),
            "updated_at": m.get("updated_at"),
        })
    return out


@router.get("/maps/{mid}")
async def get_map(mid: str, current=Depends(get_current_user)):
    from server import db
    m = await _get_map(db, mid, current["id"])
    return m


@router.put("/maps/{mid}")
async def save_map(mid: str, payload: MapSave, current=Depends(get_current_user)):
    from server import db
    update = {"updated_at": _now_iso()}
    for k in ("title", "nodes", "edges", "source_url", "notes"):
        v = getattr(payload, k)
        if v is not None:
            update[k] = v
    res = await db.studio_maps.update_one(
        {"id": mid, "owner_id": current["id"]},
        {"$set": update},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Map not found.")
    m = await _get_map(db, mid, current["id"])
    return {"ok": True, "updated_at": m["updated_at"], "nodes": len(m["nodes"]), "edges": len(m["edges"])}


@router.delete("/maps/{mid}")
async def delete_map(mid: str, current=Depends(get_current_user)):
    from server import db
    res = await db.studio_maps.delete_one({"id": mid, "owner_id": current["id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Map not found.")
    return {"ok": True}


@router.post("/maps/{mid}/share")
async def set_share(mid: str, payload: ShareConfig, current=Depends(get_current_user)):
    from server import db
    if payload.mode not in ("public", "private", "readonly", "editable"):
        raise HTTPException(status_code=400, detail="Invalid mode.")
    res = await db.studio_maps.update_one(
        {"id": mid, "owner_id": current["id"]},
        {"$set": {"share_mode": payload.mode, "updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Map not found.")
    m = await _get_map(db, mid, current["id"])
    return {"share_token": m["share_token"], "share_mode": m["share_mode"]}


@router.post("/maps/{mid}/analyze")
async def analyze_map(mid: str, current=Depends(get_current_user)):
    from server import db
    m = await _get_map(db, mid, current["id"])
    return analyze_graph(m.get("nodes", []), m.get("edges", []))


# -------- Public --------
@router.get("/public/{token}")
async def public_map(token: str):
    from server import db
    m = await _get_map_by_token(db, token)
    return {
        "id": m["id"],
        "title": m.get("title"),
        "nodes": m.get("nodes", []),
        "edges": m.get("edges", []),
        "share_mode": m.get("share_mode"),
        "updated_at": m.get("updated_at"),
        "owner_email": m.get("owner_email"),
    }


@router.put("/public/{token}")
async def public_edit(token: str, payload: MapSave):
    from server import db
    m = await _get_map_by_token(db, token)
    if m.get("share_mode") != "editable":
        raise HTTPException(status_code=403, detail="This shared map is read-only.")
    update = {"updated_at": _now_iso()}
    for k in ("title", "nodes", "edges", "notes"):
        v = getattr(payload, k)
        if v is not None:
            update[k] = v
    await db.studio_maps.update_one({"share_token": token}, {"$set": update})
    return {"ok": True, "updated_at": update["updated_at"]}


@router.get("/public/{token}/analyze")
async def public_analyze(token: str):
    from server import db
    m = await _get_map_by_token(db, token)
    return analyze_graph(m.get("nodes", []), m.get("edges", []))
