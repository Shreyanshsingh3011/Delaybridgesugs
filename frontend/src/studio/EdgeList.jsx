import { useStudio } from "./store";
import { ArrowRight, Trash2 } from "lucide-react";

const CARDINALITIES = ["1:1", "1:N", "N:1", "N:N"];
const COLOR = { row: "db-chip-blue", col: "db-chip-orange", group: "db-chip-purple" };

export default function EdgeList() {
  const { edges, deleteEdge, updateEdgeLabel, updateEdgeCardinality, groups } = useStudio();
  const nameOfGroup = (id) => groups.find((g) => g.id === id)?.name || id;

  return (
    <div className="db-card p-4 flex flex-col" data-testid="edge-list" style={{ width: 380 }}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-[11px] mono uppercase tracking-wider"
             style={{ color: "var(--db-muted)" }}>
          authored edges ({edges.length})
        </div>
      </div>
      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {edges.length === 0 && (
          <div className="text-[11px] mono p-2" style={{ color: "var(--db-muted)" }}>
            No edges authored yet. Build one in the palette below.
          </div>
        )}
        {edges.map((e) => (
          <div key={e.id}
               data-testid={`edge-row-${e.id}`}
               className="db-card p-2.5"
               style={{
                 background: e.fanIn ? "rgba(0,170,255,0.05)" : "rgba(255,255,255,0.015)",
                 borderColor: e.fanIn ? "rgba(0,170,255,0.35)" : undefined,
               }}>
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className="db-chip db-chip-blue text-[10px]">{e.cardinality}</span>
              {e.fanIn && (
                <span className="db-chip db-chip-orange text-[10px]"
                      data-testid={`edge-fanin-${e.id}`}>FAN-IN</span>
              )}
              <span className="flex-1"></span>
              <select
                data-testid={`edge-card-${e.id}`}
                className="db-input text-[10px] py-0.5 px-2"
                value={e.cardinality}
                onChange={(ev) => updateEdgeCardinality(e.id, ev.target.value)}
              >
                {CARDINALITIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <button data-testid={`edge-delete-${e.id}`} onClick={() => deleteEdge(e.id)}
                      className="db-btn db-btn-ghost py-0.5 px-1.5 text-[10px]">
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
            {e.fanIn ? (
              <div className="text-[10px] mono">
                <div className="flex flex-wrap items-center gap-1 mb-1">
                  <span style={{ color: "var(--db-muted)" }}>source:</span>
                  <span className="db-chip db-chip-orange text-[10px]">{e.to[0]?.i}</span>
                </div>
                <div className="flex flex-wrap items-center gap-1">
                  <span style={{ color: "var(--db-muted)" }}>
                    dependsOn[{e.from.length}]:
                  </span>
                  {e.from.slice(0, 8).map((r, i) => (
                    <span key={i} className="db-chip db-chip-blue text-[10px]">{r.i}</span>
                  ))}
                  {e.from.length > 8 && (
                    <span className="db-chip db-chip-grey text-[10px]">
                      +{e.from.length - 8}
                    </span>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-1 text-[10px] mono">
                <Side refs={e.from} nameOfGroup={nameOfGroup} />
                <ArrowRight className="w-3 h-3 db-accent flex-shrink-0" />
                <Side refs={e.to} nameOfGroup={nameOfGroup} />
              </div>
            )}
            <input
              data-testid={`edge-label-${e.id}`}
              className="db-input text-[10px] mt-2"
              placeholder="(optional label)"
              value={e.label || ""}
              onChange={(ev) => updateEdgeLabel(e.id, ev.target.value)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

function Side({ refs, nameOfGroup }) {
  const display = refs.slice(0, 6);
  return (
    <div className="flex flex-wrap gap-1 items-center">
      {display.map((r, i) => (
        <span key={i} className={`db-chip ${COLOR[r.t]} text-[10px]`}>
          {r.t === "group" ? nameOfGroup(r.i) : r.i}
        </span>
      ))}
      {refs.length > display.length && (
        <span className="db-chip db-chip-grey text-[10px]">+{refs.length - display.length}</span>
      )}
    </div>
  );
}
