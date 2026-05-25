import { useMemo, useState, useEffect, useCallback } from "react";
import ReactFlow, {
  Background, Controls, MiniMap, MarkerType,
  ReactFlowProvider, useReactFlow,
} from "reactflow";
import "reactflow/dist/style.css";
import { toast } from "sonner";
import {
  Columns3, Plus, Search, Trash2, GitFork, GitMerge, X, Check,
  AlertCircle, Network, ArrowRight, FastForward, ChevronRight,
} from "lucide-react";
import { useStudio } from "./store";
import { autoLayout } from "./autolayout";
import { nodeInspection, computeRewire, topoSort } from "./chainGraph";

const KIND_COLOR = { direct: "#00aaff", skip: "#c7a5ff" };

// ---- Chain node renderer ----
import { memo } from "react";
import { Handle, Position } from "reactflow";

const ChainNode = memo(function ChainNode({ data, selected, id }) {
  return (
    <div
      data-testid={`chain-node-${id}`}
      onClick={data.onClick}
      style={{
        background: "linear-gradient(180deg, #0e0e1a 0%, #14142a 100%)",
        border: `1px solid ${selected ? "#ffb265" : "#1f1f3a"}`,
        boxShadow: selected
          ? "0 0 0 2px rgba(255,178,101,0.4), 0 6px 24px rgba(255,178,101,0.25)"
          : "0 4px 14px rgba(0,0,0,0.35)",
        borderRadius: 12,
        minWidth: 160, maxWidth: 220,
        padding: "8px 10px",
        fontFamily: "IBM Plex Mono, monospace",
        color: "#e7e8ee",
        cursor: "pointer",
      }}
    >
      <Handle type="target" position={Position.Left}
              style={{ background: "#ffb265", width: 8, height: 8 }} />
      <Handle type="source" position={Position.Right}
              style={{ background: "#ffb265", width: 8, height: 8 }} />
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{
          width: 22, height: 22, borderRadius: 6,
          background: "rgba(255,178,101,0.18)",
          border: "1px solid rgba(255,178,101,0.45)",
          display: "flex", alignItems: "center", justifyContent: "center",
          color: "#ffb265", flexShrink: 0,
        }}>
          <Columns3 size={12} />
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{
            fontSize: 11, fontWeight: 600,
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>{data.label}</div>
          <div style={{
            fontSize: 9, color: "#8a8aa3",
            textTransform: "uppercase", letterSpacing: "0.06em",
          }}>
            COL · in {data.inDeg} · out {data.outDeg}
          </div>
        </div>
      </div>
    </div>
  );
});

const nodeTypes = { chainNode: ChainNode };

// ---- visual edge ----
import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath } from "reactflow";
function ChainEdgeView(props) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition,
          data, label, selected, markerEnd } = props;
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, borderRadius: 14,
  });
  const kind = data?.kind || "direct";
  const color = KIND_COLOR[kind] || "#00aaff";
  const dashed = kind === "skip";
  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: color,
          strokeWidth: selected ? 2.6 : 1.8,
          strokeDasharray: dashed ? "6 5" : "none",
          opacity: selected ? 1 : 0.9,
        }}
      />
      <EdgeLabelRenderer>
        <div
          data-testid={`chain-edge-label-${id}`}
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            background: "#0e0e1a",
            border: `1px solid ${color}66`,
            color,
            padding: "2px 8px",
            borderRadius: 999,
            fontFamily: "IBM Plex Mono, monospace",
            fontSize: 10,
            letterSpacing: "0.04em",
            pointerEvents: "all",
            textTransform: "uppercase",
            display: "flex", gap: 6, alignItems: "center",
          }}
          className="nodrag nopan"
        >
          <strong>{kind}</strong>
          {label && <span style={{ opacity: 0.85 }}>· {label}</span>}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
const edgeTypes = { chainEdge: ChainEdgeView };

// ---- Inner graph component ----
function ChainGraphInner({ onNodeClick }) {
  const { chainNodes, chainEdges, chainSelected } = useStudio();
  const rf = useReactFlow();

  // Compute in/out degree per node (over direct+skip combined).
  const degrees = useMemo(() => {
    const m = new Map();
    for (const n of chainNodes) m.set(n, { inDeg: 0, outDeg: 0 });
    for (const e of chainEdges) {
      const f = m.get(e.from); const t = m.get(e.to);
      if (f) f.outDeg += 1;
      if (t) t.inDeg += 1;
    }
    return m;
  }, [chainNodes, chainEdges]);

  const rfNodes = useMemo(
    () => chainNodes.map((cid) => ({
      id: cid,
      type: "chainNode",
      position: { x: 0, y: 0 },
      selected: cid === chainSelected,
      data: {
        label: cid,
        inDeg: degrees.get(cid)?.inDeg || 0,
        outDeg: degrees.get(cid)?.outDeg || 0,
        onClick: () => onNodeClick(cid),
      },
    })),
    [chainNodes, chainSelected, degrees, onNodeClick]
  );

  const rfEdges = useMemo(
    () => chainEdges.map((e) => ({
      id: e.id,
      source: e.from,
      target: e.to,
      type: "chainEdge",
      animated: e.kind === "direct",
      markerEnd: { type: MarkerType.ArrowClosed, color: KIND_COLOR[e.kind] || "#00aaff" },
      label: e.label || "",
      data: { kind: e.kind, label: e.label || "" },
    })),
    [chainEdges]
  );

  const laidOut = useMemo(
    () => (rfNodes.length ? autoLayout(rfNodes, rfEdges, "LR") : []),
    [rfNodes, rfEdges]
  );

  useEffect(() => {
    const t = setTimeout(() => rf.fitView({ padding: 0.2, duration: 300 }), 80);
    return () => clearTimeout(t);
  }, [laidOut.length, rfEdges.length, rf]);

  const onNodeClickRf = useCallback((_, n) => onNodeClick(n.id), [onNodeClick]);

  return (
    <div className="db-card flex-1 min-w-0 relative overflow-hidden"
         data-testid="chain-graph"
         style={{ minHeight: 360 }}>
      <ReactFlow
        nodes={laidOut}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodesConnectable={false}
        nodesDraggable
        elementsSelectable
        onNodeClick={onNodeClickRf}
        fitView
        minZoom={0.1}
        maxZoom={2.5}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={24} size={1} color="#1f1f3a" />
        <Controls position="bottom-left"
                  style={{ background: "#0e0e1a", border: "1px solid #1f1f3a" }} />
        <MiniMap pannable zoomable
                 style={{ background: "#0e0e1a", border: "1px solid #1f1f3a" }}
                 nodeColor={() => "#ffb265"}
                 maskColor="rgba(7,7,14,0.6)" />
      </ReactFlow>

      {chainNodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="text-center">
            <div className="text-sm" style={{ color: "var(--db-muted)" }}>
              No chain nodes yet
            </div>
            <div className="text-[11px] mono mt-1" style={{ color: "var(--db-muted)" }}>
              Add columns from the left panel, then commit direct or skip edges.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---- Authoring side panel (left): node picker + edge builder ----
function ChainAuthoring() {
  const {
    source, chainNodes, chainEdges,
    addChainNodes, commitChainEdge,
  } = useStudio();
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState([]);
  const [edgeFrom, setEdgeFrom] = useState("");
  const [edgeTo, setEdgeTo] = useState("");
  const [edgeKind, setEdgeKind] = useState("direct");
  const [edgeLabel, setEdgeLabel] = useState("");

  const cols = source?.headers || [];
  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    return cols
      .filter((c) => !chainNodes.includes(c))
      .filter((c) => !s || c.toLowerCase().includes(s));
  }, [cols, chainNodes, q]);

  const togglePick = (c) =>
    setPicked((p) => (p.includes(c) ? p.filter((x) => x !== c) : [...p, c]));

  const addPicked = () => {
    if (!picked.length) return;
    addChainNodes(picked);
    toast.success(`Added ${picked.length} column${picked.length > 1 ? "s" : ""} to chain`);
    setPicked([]);
  };

  const commit = () => {
    if (!edgeFrom || !edgeTo) { toast.error("Pick a source and a target column."); return; }
    const r = commitChainEdge(edgeFrom, edgeTo, edgeKind, edgeLabel.trim());
    if (!r.ok) {
      const reasonMap = {
        self_loop: "An edge cannot start and end on the same node.",
        missing_node: "Both nodes must be in the chain first.",
        bad_kind: "Edge kind must be direct or skip.",
        duplicate: "That edge already exists.",
        cycle: "Rejected: this edge would create a cycle (target already reaches source).",
      };
      toast.error(reasonMap[r.reason] || "Edge rejected.");
      return;
    }
    toast.success(`${edgeKind === "direct" ? "Direct" : "Skip"} edge committed: ${edgeFrom} → ${edgeTo}`);
    setEdgeLabel("");
  };

  return (
    <div className="db-card p-4 flex flex-col gap-3" data-testid="chain-authoring"
         style={{ width: 360 }}>
      <div className="flex items-center gap-2">
        <Network className="w-4 h-4 db-accent" />
        <div className="text-sm font-semibold">Column chain authoring</div>
      </div>
      <div className="text-[11px] mono" style={{ color: "var(--db-muted)" }}>
        Build a DAG over columnIds. Only direct + skip edges are stored — transitive paths
        are derived and never drawn.
      </div>

      {!source && (
        <div className="text-[11px] mono p-3 db-card"
             style={{ color: "var(--db-muted)", background: "rgba(255,255,255,0.02)" }}>
          Fetch an Apps Script URL first to materialise columns.
        </div>
      )}

      {source && (
        <>
          {/* Step 1 — add columns to chain */}
          <div>
            <div className="text-[10px] mono uppercase tracking-wider mb-1"
                 style={{ color: "var(--db-muted)" }}>
              step 1 · add columns to the chain ({chainNodes.length} in chain)
            </div>
            <div className="relative mb-2">
              <Search className="w-3 h-3 absolute left-3 top-3"
                      style={{ color: "var(--db-muted)" }} />
              <input
                data-testid="chain-search"
                className="db-input text-xs pl-8"
                placeholder="search columns to add…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </div>
            <div className="flex flex-wrap gap-1.5 max-h-[140px] overflow-y-auto db-card p-2"
                 style={{ background: "rgba(255,255,255,0.015)" }}
                 data-testid="chain-pool">
              {filtered.length === 0 && (
                <div className="text-[10px] mono"
                     style={{ color: "var(--db-muted)" }}>
                  {chainNodes.length === cols.length
                    ? "all columns are already in the chain"
                    : "no matching columns"}
                </div>
              )}
              {filtered.map((c) => {
                const sel = picked.includes(c);
                return (
                  <button
                    key={c}
                    data-testid={`chain-pick-${c}`}
                    onClick={() => togglePick(c)}
                    className="db-chip text-[11px] cursor-pointer transition"
                    style={
                      sel
                        ? { background: "rgba(255,178,101,0.15)",
                            border: "1px solid rgba(255,178,101,0.5)",
                            color: "#ffb265" }
                        : { background: "rgba(255,255,255,0.04)",
                            border: "1px solid var(--db-border)",
                            color: "var(--db-text)" }
                    }
                  >
                    {sel && <Check className="w-3 h-3" />} {c}
                  </button>
                );
              })}
            </div>
            {picked.length > 0 && (
              <button
                data-testid="chain-add-picked"
                onClick={addPicked}
                className="db-btn mt-2 w-full justify-center text-[11px]">
                <Plus className="w-3 h-3" /> Add {picked.length} to chain
              </button>
            )}
          </div>

          {/* Step 2 — author an edge */}
          {chainNodes.length >= 2 && (
            <div className="db-card p-3" style={{ background: "rgba(0,170,255,0.04)" }}
                 data-testid="chain-edge-builder">
              <div className="text-[10px] mono uppercase tracking-wider mb-2"
                   style={{ color: "var(--db-muted)" }}>
                step 2 · author an edge
              </div>

              <div className="text-[10px] mono mb-1" style={{ color: "var(--db-muted)" }}>from</div>
              <select
                data-testid="chain-edge-from"
                className="db-input text-xs mb-2"
                value={edgeFrom}
                onChange={(e) => setEdgeFrom(e.target.value)}
              >
                <option value="">— source column —</option>
                {chainNodes.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>

              <div className="text-[10px] mono mb-1" style={{ color: "var(--db-muted)" }}>to</div>
              <select
                data-testid="chain-edge-to"
                className="db-input text-xs mb-2"
                value={edgeTo}
                onChange={(e) => setEdgeTo(e.target.value)}
              >
                <option value="">— target column —</option>
                {chainNodes.filter((c) => c !== edgeFrom).map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>

              <div className="flex gap-1 mb-2">
                <button
                  data-testid="chain-kind-direct"
                  onClick={() => setEdgeKind("direct")}
                  className="db-btn db-btn-ghost py-1.5 px-2 text-[11px] flex-1 justify-center"
                  style={edgeKind === "direct"
                    ? { borderColor: "rgba(0,170,255,0.5)", background: "rgba(0,170,255,0.08)", color: "#6cd0ff" }
                    : {}}>
                  <ArrowRight className="w-3 h-3" /> Direct
                </button>
                <button
                  data-testid="chain-kind-skip"
                  onClick={() => setEdgeKind("skip")}
                  className="db-btn db-btn-ghost py-1.5 px-2 text-[11px] flex-1 justify-center"
                  style={edgeKind === "skip"
                    ? { borderColor: "rgba(199,165,255,0.5)", background: "rgba(199,165,255,0.08)", color: "#d9bfff" }
                    : {}}>
                  <FastForward className="w-3 h-3" /> Skip
                </button>
              </div>

              <input
                data-testid="chain-edge-label"
                className="db-input text-xs mb-2"
                placeholder="(optional) edge label"
                value={edgeLabel}
                onChange={(e) => setEdgeLabel(e.target.value)}
              />

              <button
                data-testid="chain-commit-edge"
                onClick={commit}
                className="db-btn w-full justify-center"
                disabled={!edgeFrom || !edgeTo}>
                {edgeKind === "direct" ? <GitMerge className="w-3.5 h-3.5" /> : <GitFork className="w-3.5 h-3.5" />}
                Commit {edgeKind} edge
              </button>
            </div>
          )}

          {/* Stats */}
          <div className="grid grid-cols-3 gap-1.5 text-[10px] mono">
            <Stat label="nodes" value={chainNodes.length} testid="chain-stat-nodes" />
            <Stat label="direct" value={chainEdges.filter((e) => e.kind === "direct").length} testid="chain-stat-direct" />
            <Stat label="skip" value={chainEdges.filter((e) => e.kind === "skip").length} testid="chain-stat-skip" />
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, testid }) {
  return (
    <div className="db-card p-2" data-testid={testid}>
      <div className="text-[9px] mono uppercase tracking-wider"
           style={{ color: "var(--db-muted)" }}>{label}</div>
      <div className="text-xs db-tabular-num mono mt-0.5">{value}</div>
    </div>
  );
}

// ---- Right side panel: node inspector ----
function ChainInspector() {
  const {
    chainNodes, chainEdges, chainSelected, selectChainNode,
    deleteChainEdge, deleteChainNode,
  } = useStudio();
  const [confirmDelete, setConfirmDelete] = useState(null); // columnId

  const insp = useMemo(() => {
    if (!chainSelected) return null;
    return nodeInspection(chainNodes, chainEdges, chainSelected);
  }, [chainSelected, chainNodes, chainEdges]);

  const incidentEdges = useMemo(() => {
    if (!chainSelected) return [];
    return chainEdges.filter((e) => e.from === chainSelected || e.to === chainSelected);
  }, [chainEdges, chainSelected]);

  const topo = useMemo(
    () => topoSort(chainNodes, chainEdges) || [],
    [chainNodes, chainEdges]
  );

  const rewirePreview = useMemo(() => {
    if (!confirmDelete) return null;
    return computeRewire(chainNodes, chainEdges, confirmDelete);
  }, [confirmDelete, chainNodes, chainEdges]);

  return (
    <div className="db-card p-4 flex flex-col gap-3 overflow-y-auto"
         data-testid="chain-inspector"
         style={{ width: 360 }}>
      <div className="flex items-center gap-2">
        <Columns3 className="w-4 h-4" style={{ color: "#ffb265" }} />
        <div className="text-sm font-semibold">Node inspector</div>
      </div>

      {!chainSelected && (
        <div className="text-[11px] mono p-3 db-card"
             style={{ color: "var(--db-muted)", background: "rgba(255,255,255,0.02)" }}>
          Click a node on the graph to inspect its direct and transitive relationships.
        </div>
      )}

      {chainSelected && insp && (
        <>
          <div className="flex items-center gap-2">
            <span className="db-chip db-chip-orange text-[11px]"
                  data-testid="chain-selected-label">
              {chainSelected}
            </span>
            <button
              data-testid="chain-deselect"
              onClick={() => selectChainNode(null)}
              className="db-btn db-btn-ghost py-0.5 px-1.5 text-[10px]">
              <X className="w-3 h-3" /> deselect
            </button>
          </div>

          <Section title="direct predecessors" testid="sect-direct-in"
                   items={insp.directIn} color="#00aaff" />
          <Section title="direct successors" testid="sect-direct-out"
                   items={insp.directOut} color="#00aaff" />
          <Section title="skip edges (ancestor → here)" testid="sect-skip-in"
                   items={insp.skipIn} color="#c7a5ff" />
          <Section title="skip edges (here → descendant)" testid="sect-skip-out"
                   items={insp.skipOut} color="#c7a5ff" />
          <Section title="transitive ancestors" testid="sect-transitive-anc"
                   items={insp.transitiveAnc} color="#8a8aa3" muted />
          <Section title="transitive descendants" testid="sect-transitive-desc"
                   items={insp.transitiveDesc} color="#8a8aa3" muted />

          {/* Incident edges with delete */}
          {incidentEdges.length > 0 && (
            <div>
              <div className="text-[10px] mono uppercase tracking-wider mb-1"
                   style={{ color: "var(--db-muted)" }}>
                incident edges ({incidentEdges.length})
              </div>
              <div className="space-y-1" data-testid="chain-incident-edges">
                {incidentEdges.map((e) => (
                  <div key={e.id}
                       className="db-card p-2 flex items-center justify-between text-[10px] mono"
                       style={{ background: "rgba(255,255,255,0.015)" }}>
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="db-chip"
                            style={{
                              background: `${KIND_COLOR[e.kind]}22`,
                              border: `1px solid ${KIND_COLOR[e.kind]}55`,
                              color: KIND_COLOR[e.kind],
                            }}>{e.kind}</span>
                      <span className="truncate">{e.from}</span>
                      <ChevronRight className="w-3 h-3 db-accent" />
                      <span className="truncate">{e.to}</span>
                    </div>
                    <button
                      data-testid={`chain-del-edge-${e.id}`}
                      onClick={() => { deleteChainEdge(e.id); toast.success("Edge deleted"); }}
                      className="db-btn db-btn-ghost py-0.5 px-1">
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Delete-node action */}
          <button
            data-testid="chain-delete-node"
            onClick={() => setConfirmDelete(chainSelected)}
            className="db-btn db-btn-ghost text-[11px] justify-center"
            style={{ color: "#ff7a99", borderColor: "rgba(255,122,153,0.35)" }}>
            <Trash2 className="w-3 h-3" /> Delete node…
          </button>
        </>
      )}

      {/* Topological order (whole chain) */}
      {chainNodes.length > 0 && (
        <div>
          <div className="text-[10px] mono uppercase tracking-wider mb-1"
               style={{ color: "var(--db-muted)" }}>
            topological order
          </div>
          <div className="flex flex-wrap gap-1" data-testid="chain-topo">
            {topo.length === 0 && (
              <span className="text-[10px] mono" style={{ color: "#ff7a99" }}>
                <AlertCircle className="w-3 h-3 inline" /> cyclic — should never happen
              </span>
            )}
            {topo.map((c, i) => (
              <span key={c} className="db-chip text-[10px]"
                    style={{ background: "rgba(255,255,255,0.04)",
                             border: "1px solid var(--db-border)" }}>
                <span style={{ color: "var(--db-muted)" }}>{i + 1}.</span> {c}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Delete-node confirm modal */}
      {confirmDelete && rewirePreview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4"
             style={{ background: "rgba(7,7,14,0.7)", backdropFilter: "blur(6px)" }}
             onClick={() => setConfirmDelete(null)}
             data-testid="chain-delete-modal">
          <div className="db-card p-5 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2 mb-2">
              <AlertCircle className="w-4 h-4" style={{ color: "#ff7a99" }} />
              <div className="text-sm font-semibold">Delete {confirmDelete}</div>
            </div>
            <div className="text-xs mb-3" style={{ color: "var(--db-muted)" }}>
              This node has{" "}
              <strong>{rewirePreview.preds.length}</strong> direct predecessor{rewirePreview.preds.length === 1 ? "" : "s"} and{" "}
              <strong>{rewirePreview.succs.length}</strong> direct successor{rewirePreview.succs.length === 1 ? "" : "s"}.
              Choose how to handle them:
            </div>
            <div className="space-y-2">
              <button
                data-testid="chain-delete-disconnect"
                onClick={() => {
                  deleteChainNode(confirmDelete, "disconnect");
                  toast.success(`${confirmDelete} disconnected`);
                  setConfirmDelete(null);
                }}
                className="db-btn db-btn-ghost w-full justify-start py-2 px-3 text-xs text-left">
                <div>
                  <div className="font-semibold">Disconnect</div>
                  <div className="text-[10px] mt-0.5" style={{ color: "var(--db-muted)" }}>
                    Drop all incident edges. Predecessors lose connection to successors.
                  </div>
                </div>
              </button>
              <button
                data-testid="chain-delete-rewire"
                onClick={() => {
                  deleteChainNode(confirmDelete, "rewire");
                  toast.success(`${confirmDelete} rewired — ${rewirePreview.news.length} new direct edge${rewirePreview.news.length === 1 ? "" : "s"}`);
                  setConfirmDelete(null);
                }}
                className="db-btn w-full justify-start py-2 px-3 text-xs text-left">
                <div>
                  <div className="font-semibold">Rewire ({rewirePreview.news.length} new edge{rewirePreview.news.length === 1 ? "" : "s"})</div>
                  <div className="text-[10px] mt-0.5" style={{ opacity: 0.85 }}>
                    Create a direct edge from each predecessor to each successor (P×S),
                    preserving reachability.
                  </div>
                </div>
              </button>
              <button
                data-testid="chain-delete-cancel"
                onClick={() => setConfirmDelete(null)}
                className="db-btn db-btn-ghost w-full justify-center text-[11px]">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Section({ title, items, color, muted, testid }) {
  return (
    <div data-testid={testid}>
      <div className="text-[10px] mono uppercase tracking-wider mb-1"
           style={{ color: "var(--db-muted)" }}>
        {title} ({items.length})
      </div>
      <div className="flex flex-wrap gap-1">
        {items.length === 0 && (
          <span className="text-[10px] mono" style={{ color: "var(--db-muted)" }}>—</span>
        )}
        {items.map((c) => (
          <span key={c} className="db-chip text-[10px]"
                style={{
                  background: muted ? "rgba(255,255,255,0.02)" : `${color}1a`,
                  border: `1px solid ${muted ? "var(--db-border)" : color + "55"}`,
                  color: muted ? "var(--db-muted)" : color,
                  fontStyle: muted ? "italic" : "normal",
                }}>
            {c}
          </span>
        ))}
      </div>
    </div>
  );
}

// ---- Outer wrapper ----
export default function ColumnChainStudio() {
  const { selectChainNode } = useStudio();
  const onNodeClick = useCallback((cid) => selectChainNode(cid), [selectChainNode]);

  return (
    <div className="flex-1 flex gap-3 min-h-0" data-testid="column-chain-studio">
      <ChainAuthoring />
      <ReactFlowProvider>
        <ChainGraphInner onNodeClick={onNodeClick} />
      </ReactFlowProvider>
      <ChainInspector />
    </div>
  );
}
