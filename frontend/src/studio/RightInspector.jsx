import { useMemo } from "react";
import { useStudio } from "./store";
import { analyzeGraph } from "./analytics";
import {
  Info, AlertTriangle, AlertOctagon, CheckCircle2, Trash2, Copy,
  ArrowRightLeft, GitBranch, Activity, Network, Brain,
} from "lucide-react";

const SEV_CFG = {
  danger:  { color: "#ff8a8a", border: "rgba(255,68,68,0.35)", bg: "rgba(255,68,68,0.08)", Icon: AlertOctagon },
  warning: { color: "#ffb265", border: "rgba(255,136,0,0.35)", bg: "rgba(255,136,0,0.08)", Icon: AlertTriangle },
  info:    { color: "#6cd0ff", border: "rgba(0,170,255,0.35)", bg: "rgba(0,170,255,0.08)", Icon: Info },
  success: { color: "#5bd9a8", border: "rgba(0,204,136,0.35)", bg: "rgba(0,204,136,0.08)", Icon: CheckCircle2 },
};

const PRIORITIES = ["Low", "Normal", "High", "Critical"];

export default function RightInspector() {
  const {
    nodes, edges, selectedId, updateNode, removeNode, duplicateNode,
    updateEdge, removeEdge, DEPENDENCY_TYPES, CATEGORIES,
  } = useStudio();

  const analysis = useMemo(() => analyzeGraph(nodes, edges), [nodes, edges]);

  const selectedNode = nodes.find((n) => n.id === selectedId);
  const incoming = edges.filter((e) => e.target === selectedId);
  const outgoing = edges.filter((e) => e.source === selectedId);
  const nameOf = (id) => nodes.find((n) => n.id === id)?.data?.name || id;

  return (
    <div className="db-card p-4 h-full overflow-y-auto" data-testid="studio-right-inspector"
         style={{ width: 340 }}>
      {/* Scores */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        <ScoreBox label="Health" value={analysis.scores.health}
                  color={analysis.scores.health >= 70 ? "#5bd9a8" : analysis.scores.health >= 40 ? "#ffb265" : "#ff8a8a"} />
        <ScoreBox label="Deps" value={analysis.scores.dependency} color="#6cd0ff" />
        <ScoreBox label="Complex" value={analysis.scores.complexity}
                  color={analysis.scores.complexity >= 70 ? "#ff8a8a" : analysis.scores.complexity >= 40 ? "#ffb265" : "#5bd9a8"} />
      </div>

      {/* AI insights */}
      <Section icon={Brain} title="AI insights">
        <div className="space-y-1.5">
          {analysis.insights.map((it, i) => {
            const c = SEV_CFG[it.severity] || SEV_CFG.info;
            const I = c.Icon;
            return (
              <div key={i}
                   data-testid={`studio-insight-${it.severity}`}
                   style={{
                     border: `1px solid ${c.border}`,
                     background: c.bg,
                     borderRadius: 8, padding: "8px 10px",
                     display: "flex", gap: 8,
                     fontSize: 12, color: c.color,
                   }}>
                <I className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                <div>{it.text}</div>
              </div>
            );
          })}
        </div>
      </Section>

      {/* Analytics summary */}
      <Section icon={Activity} title="Dependency analytics">
        <Row label="Nodes" value={analysis.nodes} />
        <Row label="Edges" value={analysis.edges} />
        <Row label="Roots" value={analysis.roots.length} />
        <Row label="Sinks" value={analysis.sinks.length} />
        <Row label="Orphans" value={analysis.orphans.length}
             warn={analysis.orphans.length > 0} />
        <Row label="Cycles" value={analysis.cycles.length}
             warn={analysis.cycles.length > 0} danger={analysis.cycles.length > 0} />
        <Row label="Bottlenecks" value={analysis.bottlenecks.length}
             warn={analysis.bottlenecks.length > 0} />
        <Row label="High coupling" value={analysis.highCoupling.length}
             warn={analysis.highCoupling.length > 0} />
        <Row label="Redundant edges" value={analysis.redundant.length} />
        <Row label="Acyclic (DAG)" value={analysis.isDag ? "yes" : "no"}
             warn={!analysis.isDag && analysis.nodes > 0} />
      </Section>

      {/* Node inspector */}
      {selectedNode ? (
        <Section icon={Network} title="Selected node">
          <input
            data-testid="studio-node-name-input"
            className="db-input text-sm font-semibold mb-2"
            value={selectedNode.data?.name || ""}
            onChange={(e) => updateNode(selectedNode.id, { name: e.target.value })}
          />
          <FieldLabel>Category</FieldLabel>
          <select className="db-input text-xs mb-2"
                  value={selectedNode.data?.category || "Service"}
                  onChange={(e) => updateNode(selectedNode.id, { category: e.target.value })}>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <div className="grid grid-cols-2 gap-2 mb-2">
            <div>
              <FieldLabel>Type</FieldLabel>
              <input className="db-input text-xs"
                     value={selectedNode.data?.type || ""}
                     onChange={(e) => updateNode(selectedNode.id, { type: e.target.value })} />
            </div>
            <div>
              <FieldLabel>Status</FieldLabel>
              <input className="db-input text-xs"
                     value={selectedNode.data?.status || ""}
                     onChange={(e) => updateNode(selectedNode.id, { status: e.target.value })} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 mb-2">
            <div>
              <FieldLabel>Stage</FieldLabel>
              <input className="db-input text-xs"
                     value={selectedNode.data?.stage ?? ""}
                     onChange={(e) => updateNode(selectedNode.id, { stage: e.target.value })} />
            </div>
            <div>
              <FieldLabel>Tags (comma)</FieldLabel>
              <input className="db-input text-xs"
                     value={(selectedNode.data?.tags || []).join(", ")}
                     onChange={(e) => updateNode(selectedNode.id, {
                       tags: e.target.value.split(",").map((t) => t.trim()).filter(Boolean),
                     })} />
            </div>
          </div>
          <FieldLabel>Notes</FieldLabel>
          <textarea className="db-input text-xs"
                    rows={3}
                    value={selectedNode.data?.notes || ""}
                    onChange={(e) => updateNode(selectedNode.id, { notes: e.target.value })} />

          {/* Connections */}
          <div className="mt-3 grid grid-cols-2 gap-3">
            <ConnList title={`Incoming (${incoming.length})`} edges={incoming}
                      nameOf={nameOf} side="source" />
            <ConnList title={`Outgoing (${outgoing.length})`} edges={outgoing}
                      nameOf={nameOf} side="target" />
          </div>

          <div className="flex items-center gap-2 mt-3">
            <button data-testid="studio-duplicate-node" onClick={() => duplicateNode(selectedNode.id)}
                    className="db-btn db-btn-ghost text-xs">
              <Copy className="w-3 h-3" /> Duplicate
            </button>
            <button data-testid="studio-delete-node" onClick={() => removeNode(selectedNode.id)}
                    className="db-btn db-btn-ghost text-xs">
              <Trash2 className="w-3 h-3" /> Delete
            </button>
          </div>
        </Section>
      ) : (
        <Section icon={GitBranch} title="Edges">
          <div className="text-[11px] mono mb-2" style={{ color: "var(--db-muted)" }}>
            Select a node to edit. Click an edge below to edit it.
          </div>
          <div className="space-y-1 max-h-[260px] overflow-y-auto">
            {edges.length === 0 && (
              <div className="text-[11px] mono" style={{ color: "var(--db-muted)" }}>
                no edges yet · drag from one node handle to another
              </div>
            )}
            {edges.slice(0, 50).map((e) => (
              <EdgeRow key={e.id} e={e} nameOf={nameOf}
                       onChange={(patch) => updateEdge(e.id, patch)}
                       onDelete={() => removeEdge(e.id)}
                       DEPENDENCY_TYPES={DEPENDENCY_TYPES}
                       PRIORITIES={PRIORITIES} />
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}

function ScoreBox({ label, value, color }) {
  return (
    <div style={{
      border: `1px solid ${color}55`,
      background: `${color}11`,
      borderRadius: 10, padding: "8px 10px",
    }}>
      <div className="text-[10px] mono uppercase tracking-wider"
           style={{ color: "var(--db-muted)" }}>{label}</div>
      <div className="text-2xl db-tabular-num mono" style={{ color }}>{value}</div>
    </div>
  );
}

function Section({ icon: Icon, title, children }) {
  return (
    <div className="mb-4 pt-3 border-t db-divider first:border-t-0 first:pt-0">
      <div className="flex items-center gap-2 mb-2">
        <Icon className="w-3.5 h-3.5 db-accent" />
        <div className="text-xs mono uppercase tracking-wider"
             style={{ color: "var(--db-muted)" }}>{title}</div>
      </div>
      {children}
    </div>
  );
}

function Row({ label, value, warn, danger }) {
  const color = danger ? "#ff8a8a" : warn ? "#ffb265" : undefined;
  return (
    <div className="flex items-center justify-between text-xs py-1">
      <span style={{ color: "var(--db-muted)" }}>{label}</span>
      <span className="db-tabular-num mono" style={{ color }}>{value}</span>
    </div>
  );
}

function FieldLabel({ children }) {
  return (
    <div className="text-[10px] mono uppercase tracking-wider mb-1"
         style={{ color: "var(--db-muted)" }}>
      {children}
    </div>
  );
}

function ConnList({ title, edges, nameOf, side }) {
  return (
    <div>
      <FieldLabel>{title}</FieldLabel>
      <div className="space-y-1 max-h-[140px] overflow-y-auto">
        {edges.length === 0 && (
          <div className="text-[10px] mono" style={{ color: "var(--db-muted)" }}>—</div>
        )}
        {edges.map((e) => (
          <div key={e.id} className="text-[11px] mono flex items-center gap-1.5">
            <ArrowRightLeft className="w-3 h-3 db-accent" />
            <span className="truncate">{nameOf(side === "source" ? e.source : e.target)}</span>
            <span className="db-chip db-chip-grey text-[9px]">{e.data?.type || "Required"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function EdgeRow({ e, nameOf, onChange, onDelete, DEPENDENCY_TYPES, PRIORITIES }) {
  return (
    <div className="text-[11px] mono p-2 rounded border db-divider hover:bg-white/[0.02]"
         data-testid={`studio-edge-row-${e.id}`}
         style={{ background: "rgba(255,255,255,0.015)" }}>
      <div className="flex items-center gap-1 mb-1 truncate">
        <span className="truncate">{nameOf(e.source)}</span>
        <span className="db-accent">→</span>
        <span className="truncate">{nameOf(e.target)}</span>
        <div className="flex-1"></div>
        <button onClick={onDelete} className="text-[10px] db-danger hover:underline">remove</button>
      </div>
      <div className="grid grid-cols-2 gap-1">
        <select className="db-input text-[10px] py-1"
                value={e.data?.type || "Required"}
                onChange={(ev) => onChange({ label: ev.target.value, data: { type: ev.target.value } })}>
          {DEPENDENCY_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select className="db-input text-[10px] py-1"
                value={e.data?.priority || "Normal"}
                onChange={(ev) => onChange({ data: { priority: ev.target.value } })}>
          {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </div>
    </div>
  );
}
