import { useMemo, useCallback, useEffect } from "react";
import ReactFlow, {
  Background, Controls, MiniMap, MarkerType, ReactFlowProvider, useReactFlow,
} from "reactflow";
import "reactflow/dist/style.css";
import { useStudio } from "./store";
import CustomNode from "./CustomNode";
import DependencyEdge from "./CustomEdge";
import { autoLayout } from "./autolayout";

const nodeTypes = { studioNode: CustomNode };
const edgeTypes = { depEdge: DependencyEdge };

const cardColor = {
  "1:1": "#00aaff", "1:N": "#5bd9a8", "N:1": "#ffb265", "N:N": "#c7a5ff",
};

function buildGraph(edges, groups) {
  // Collect every unique ref referenced by any authored edge
  const refMap = new Map();
  const groupById = new Map(groups.map((g) => [g.id, g]));
  for (const e of edges) {
    for (const r of [...e.from, ...e.to]) {
      const key = `${r.t}:${r.i}`;
      if (!refMap.has(key)) {
        const isGroup = r.t === "group";
        const g = isGroup ? groupById.get(r.i) : null;
        refMap.set(key, {
          id: key,
          kind: r.t,
          label: isGroup ? (g?.name || r.i) : r.i,
          memberCount: isGroup ? (g?.members?.length || 0) : 0,
        });
      }
    }
  }
  const nodes = [...refMap.values()].map((n) => ({
    id: n.id,
    type: "studioNode",
    position: { x: 0, y: 0 },
    data: { label: n.label, kind: n.kind, memberCount: n.memberCount },
  }));

  // Expand each authored edge into N×M visual arrows sharing the same id-prefix.
  const flowEdges = [];
  for (const e of edges) {
    const color = cardColor[e.cardinality] || "#00aaff";
    for (const a of e.from) {
      for (const b of e.to) {
        const src = `${a.t}:${a.i}`;
        const tgt = `${b.t}:${b.i}`;
        if (src === tgt) continue;
        flowEdges.push({
          id: `${e.id}::${src}->${tgt}`,
          source: src, target: tgt,
          type: "depEdge",
          animated: true,
          markerEnd: { type: MarkerType.ArrowClosed, color },
          label: e.label || "",
          data: { cardinality: e.cardinality, label: e.label || "", edgeId: e.id },
        });
      }
    }
  }
  return { nodes, edges: flowEdges };
}

function GraphInner() {
  const { edges, groups } = useStudio();
  const rf = useReactFlow();

  const { nodes, edges: flowEdges } = useMemo(
    () => buildGraph(edges, groups),
    [edges, groups]
  );

  // Auto-layout whenever the topology changes
  const laidOut = useMemo(
    () => (nodes.length ? autoLayout(nodes, flowEdges, "LR") : []),
    [nodes, flowEdges]
  );

  useEffect(() => {
    const t = setTimeout(() => rf.fitView({ padding: 0.2, duration: 300 }), 80);
    return () => clearTimeout(t);
  }, [laidOut.length, flowEdges.length, rf]);

  const minimapColor = useCallback((n) => {
    if (n.data?.kind === "row") return "#00aaff";
    if (n.data?.kind === "col") return "#ffb265";
    return "#c7a5ff";
  }, []);

  return (
    <div className="db-card flex-1 min-w-0 relative overflow-hidden"
         data-testid="studio-graph"
         style={{ minHeight: 360 }}>
      <ReactFlow
        nodes={laidOut}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodesConnectable={false}
        nodesDraggable
        elementsSelectable
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
                 nodeColor={minimapColor}
                 maskColor="rgba(7,7,14,0.6)" />
      </ReactFlow>

      {nodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="text-center">
            <div className="text-sm" style={{ color: "var(--db-muted)" }}>
              No edges yet
            </div>
            <div className="text-[11px] mono mt-1" style={{ color: "var(--db-muted)" }}>
              Pick source + target in the palette, then Commit edge.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Graph() {
  return (
    <ReactFlowProvider>
      <GraphInner />
    </ReactFlowProvider>
  );
}
