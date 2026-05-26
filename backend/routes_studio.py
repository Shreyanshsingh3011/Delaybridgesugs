"""Dependency Resolver — Apps Script ingestion only. No persistence.
Strict HARD FILTER: returns only structural metadata (headers + rowIds),
never cell-level scalar values."""
import base64
import json
import logging
from collections import deque
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import get_current_user
from sheet_fetcher import fetch_apps_script

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/studio")


class FetchRequest(BaseModel):
    url: str


def _row_id(idx: int, raw: Dict[str, Any]) -> str:
    # Prefer explicit id-like fields if present, else ordinal index.
    for k in ("id", "ID", "Id", "Sr. No.", "row_id", "uuid"):
        v = raw.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return f"r{idx}"


_MOCK_HEADERS = [
    "Task ID", "Task Name", "Owner", "Department",
    "Permit Issued", "Material Ordered", "Material Delivered",
    "Foundation Cast", "Wall Erection", "Roofing",
    "Electrical Wiring", "Plumbing", "Plastering",
    "Inspection", "Handover",
]

_MOCK_ROWS = [
    {"Task ID": "T01", "Task Name": "North wing — foundation",   "Owner": "R. Sharma", "Department": "Civil",
     "Permit Issued": "2026-01-08", "Material Ordered": "2026-01-10", "Material Delivered": "2026-01-18",
     "Foundation Cast": "2026-01-25", "Wall Erection": "2026-02-04", "Roofing": "2026-02-18",
     "Electrical Wiring": "2026-02-22", "Plumbing": "2026-02-23", "Plastering": "2026-03-01",
     "Inspection": "2026-03-08", "Handover": "2026-03-12"},
    {"Task ID": "T02", "Task Name": "South wing — foundation",   "Owner": "A. Verma",  "Department": "Civil",
     "Permit Issued": "2026-01-10", "Material Ordered": "2026-01-12", "Material Delivered": "2026-01-22",
     "Foundation Cast": "2026-01-28", "Wall Erection": "2026-02-08", "Roofing": "2026-02-21",
     "Electrical Wiring": "2026-02-26", "Plumbing": "2026-02-27", "Plastering": "2026-03-05",
     "Inspection": "2026-03-12", "Handover": "2026-03-16"},
    {"Task ID": "T03", "Task Name": "East tower — slab L1",      "Owner": "S. Iyer",   "Department": "Civil",
     "Permit Issued": "2026-01-15", "Material Ordered": "2026-01-17", "Material Delivered": "2026-01-27",
     "Foundation Cast": "2026-02-02", "Wall Erection": "2026-02-12", "Roofing": "2026-02-28",
     "Electrical Wiring": "2026-03-04", "Plumbing": "2026-03-05", "Plastering": "2026-03-12",
     "Inspection": "2026-03-19", "Handover": "2026-03-23"},
    {"Task ID": "T04", "Task Name": "West tower — slab L1",      "Owner": "P. Joshi",  "Department": "Civil",
     "Permit Issued": "2026-01-18", "Material Ordered": "2026-01-20", "Material Delivered": "2026-01-30",
     "Foundation Cast": "2026-02-06", "Wall Erection": "2026-02-16", "Roofing": "2026-03-02",
     "Electrical Wiring": "2026-03-08", "Plumbing": "2026-03-09", "Plastering": "2026-03-16",
     "Inspection": "2026-03-23", "Handover": "2026-03-27"},
    {"Task ID": "T05", "Task Name": "Clubhouse — civil",         "Owner": "M. Khan",   "Department": "Civil",
     "Permit Issued": "2026-01-22", "Material Ordered": "2026-01-25", "Material Delivered": "2026-02-04",
     "Foundation Cast": "2026-02-10", "Wall Erection": "2026-02-20", "Roofing": "2026-03-06",
     "Electrical Wiring": "2026-03-11", "Plumbing": "2026-03-12", "Plastering": "2026-03-19",
     "Inspection": "2026-03-26", "Handover": "2026-03-30"},
    {"Task ID": "T06", "Task Name": "Parking deck",              "Owner": "K. Bose",   "Department": "Civil",
     "Permit Issued": "2026-01-25", "Material Ordered": "2026-01-28", "Material Delivered": "2026-02-07",
     "Foundation Cast": "2026-02-13", "Wall Erection": "2026-02-23", "Roofing": "2026-03-09",
     "Electrical Wiring": "2026-03-15", "Plumbing": "2026-03-16", "Plastering": "2026-03-23",
     "Inspection": "2026-03-30", "Handover": "2026-04-03"},
]


@router.post("/fetch")
async def studio_fetch(payload: FetchRequest, current=Depends(get_current_user)):
    """Fetch records from an Apps Script Web App URL.

    HARD FILTER: discards all cell-level scalar values. Returns only:
      - headers:    list of column labels (col namespace)
      - rowIds:     ordinal row identifiers (row index namespace)
      - rowCount:   convenience integer
    """
    # Short-circuit when the URL points to our own mock endpoint — saves a
    # k8s loopback request that the ingress routinely refuses.
    if payload.url.rstrip("/").endswith("/api/studio/_mock_sheet"):
        rows = list(_MOCK_ROWS)
        msg = f"Mock sheet — {len(rows)} rows."
        ok = True
    else:
        ok, msg, rows = fetch_apps_script(payload.url)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    # Headers — preserve first-seen order across rows.
    headers: List[str] = []
    seen: set = set()
    for r in rows:
        if isinstance(r, dict):
            for k in r.keys():
                if k not in seen:
                    seen.add(k)
                    headers.append(str(k))

    row_ids: List[str] = []
    used: set = set()
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            continue
        rid = _row_id(i, r)
        # Disambiguate duplicates
        base = rid
        suffix = 1
        while rid in used:
            rid = f"{base}#{suffix}"
            suffix += 1
        used.add(rid)
        row_ids.append(rid)

    return {
        "headers": headers,
        "rowIds": row_ids,
        "rowCount": len(row_ids),
        "message": msg,
    }


# ---------------------------------------------------------------------------
# Demo Apps Script-style endpoint. Mirrors the JSON shape an Apps Script Web
# App returns for a realistic construction-project sheet. Public, GET, no auth.
# Use this URL as input to /api/studio/fetch when you don't have a real sheet.
# ---------------------------------------------------------------------------


@router.get("/_mock_sheet")
async def studio_mock_sheet():
    return {"status": "ok", "data": _MOCK_ROWS, "headers": _MOCK_HEADERS, "rowCount": len(_MOCK_ROWS)}


# ---------------------------------------------------------------------------
# Resolver — decodes a Base64URL share token, derives transitive closure, and
# returns the canonical chain graph in clean JSON (consumable by any frontend).
# Public on purpose: the token itself is the auth — without it, nothing leaks.
# ---------------------------------------------------------------------------


def _b64url_decode(token: str) -> dict:
    s = token.replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    raw = base64.b64decode(s).decode("utf-8")
    return json.loads(raw)


def _bfs(adj: Dict[str, set], start: str) -> set:
    visited: set = set()
    q: deque = deque(adj.get(start, []))
    visited.update(q)
    while q:
        cur = q.popleft()
        for nxt in adj.get(cur, []):
            if nxt not in visited:
                visited.add(nxt)
                q.append(nxt)
    return visited


def _topo(nodes: List[str], edges: List[dict]) -> List[str]:
    out: Dict[str, set] = {n: set() for n in nodes}
    indeg: Dict[str, int] = {n: 0 for n in nodes}
    for e in edges:
        if e["from"] in out and e["to"] in indeg:
            if e["to"] not in out[e["from"]]:
                out[e["from"]].add(e["to"])
                indeg[e["to"]] += 1
    q = deque([n for n in nodes if indeg[n] == 0])
    order: List[str] = []
    while q:
        u = q.popleft()
        order.append(u)
        for v in out[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    return order if len(order) == len(nodes) else []


@router.get("/resolve")
async def studio_resolve(d: str = Query(..., description="Base64URL share token from /studio#d=...")):
    """Decode a Studio share token and emit the canonical resolved graph.

    Returns:
      - source: { url, headers, rowIds } (or null)
      - chain: {
          nodes:        [columnId,...],
          directEdges:  [{from,to,label}],
          skipEdges:    [{from,to,label}],
          transitive:   { columnId: {ancestors:[], descendants:[]} },
          topoOrder:    [columnId,...]  (empty if cyclic — should never happen)
        }
      - edges:  the row/col/group dependency edges (passthrough)
      - version: codec version
    """
    try:
        j = _b64url_decode(d)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid share token: {exc}")

    if not isinstance(j, dict) or j.get("v") not in (1, 2):
        raise HTTPException(status_code=400, detail="Unsupported share-link version.")

    # ---- source ----
    src = j.get("src") or None
    source = None
    if src:
        source = {
            "url": src.get("u", ""),
            "headers": src.get("h", []) or [],
            "rowIds": src.get("r", []) or [],
        }

    # ---- row/col/group edges (passthrough; row+col resolver) ----
    edges = []
    for x in (j.get("e") or []):
        edges.append({
            "id": x.get("i"),
            "from": x.get("f", []),
            "to": x.get("t", []),
            "cardinality": x.get("c", "1:1"),
            "label": x.get("l", ""),
            "fanIn": bool(x.get("fi")),
        })

    # ---- chain DAG ----
    chain_nodes: List[str] = list(j.get("cn") or [])
    chain_edges_raw = j.get("ce") or []

    direct_edges: List[dict] = []
    skip_edges: List[dict] = []
    for x in chain_edges_raw:
        kind = "skip" if x.get("k") == "s" else "direct"
        rec = {"from": x.get("f"), "to": x.get("t"), "label": x.get("l", "")}
        (skip_edges if kind == "skip" else direct_edges).append(rec)

    # Reachability over (direct ∪ skip)
    out_adj: Dict[str, set] = {n: set() for n in chain_nodes}
    in_adj: Dict[str, set] = {n: set() for n in chain_nodes}
    for e in direct_edges + skip_edges:
        if e["from"] in out_adj and e["to"] in in_adj:
            out_adj[e["from"]].add(e["to"])
            in_adj[e["to"]].add(e["from"])

    transitive: Dict[str, dict] = {}
    for n in chain_nodes:
        descendants = sorted(_bfs(out_adj, n))
        ancestors = sorted(_bfs(in_adj, n))
        transitive[n] = {"ancestors": ancestors, "descendants": descendants}

    combined = [{"from": e["from"], "to": e["to"]} for e in direct_edges + skip_edges]
    topo_order = _topo(chain_nodes, combined)

    return {
        "version": j.get("v"),
        "source": source,
        "edges": edges,
        "chain": {
            "nodes": chain_nodes,
            "directEdges": direct_edges,
            "skipEdges": skip_edges,
            "transitive": transitive,
            "topoOrder": topo_order,
            "isDAG": bool(topo_order) or not chain_nodes,
            "stats": {
                "nodeCount": len(chain_nodes),
                "directCount": len(direct_edges),
                "skipCount": len(skip_edges),
                "transitiveEdgeCount": sum(
                    len(t["descendants"]) for t in transitive.values()
                ) - len(direct_edges) - len(skip_edges),
            },
        },
    }
