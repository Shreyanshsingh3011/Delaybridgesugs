import { useState, useMemo } from "react";
import { useStudio } from "./store";
import {
  Columns3, ChevronRight, GitMerge, Plus, X, Search, Wand2, Check,
} from "lucide-react";

export default function ColumnDependencyWizard() {
  const { source, commitColumnDependency, edges } = useStudio();
  const [child, setChild] = useState("");
  const [parents, setParents] = useState([]);
  const [label, setLabel] = useState("");
  const [query, setQuery] = useState("");

  const cols = source?.headers || [];
  const filteredParents = useMemo(() => {
    const q = query.trim().toLowerCase();
    return cols
      .filter((c) => c !== child)
      .filter((c) => !q || c.toLowerCase().includes(q));
  }, [cols, child, query]);

  const isParentSelected = (c) => parents.includes(c);
  const toggleParent = (c) =>
    setParents((p) => (p.includes(c) ? p.filter((x) => x !== c) : [...p, c]));
  const selectAll = () =>
    setParents([...new Set([...parents, ...filteredParents])]);
  const clearParents = () => setParents([]);
  const reset = () => { setChild(""); setParents([]); setLabel(""); setQuery(""); };

  const onCommit = () => {
    if (!child || !parents.length) return;
    commitColumnDependency(child, parents, label.trim());
    reset();
  };

  // Existing fan-in summary for the chosen child
  const existing = useMemo(() => {
    if (!child) return [];
    const out = [];
    for (const e of edges) {
      const isFanInToChild =
        e.to.length === 1 &&
        e.to[0].t === "col" &&
        e.to[0].i === child &&
        e.from.every((r) => r.t === "col");
      if (isFanInToChild) {
        out.push({ id: e.id, parents: e.from.map((r) => r.i), cardinality: e.cardinality });
      }
    }
    return out;
  }, [child, edges]);

  return (
    <div className="db-card p-4 flex flex-col gap-3" data-testid="col-dep-wizard"
         style={{ width: 360 }}>
      <div className="flex items-center gap-2">
        <Wand2 className="w-4 h-4 db-accent" />
        <div className="text-sm font-semibold">Column dependency wizard</div>
      </div>
      <div className="text-[11px] mono" style={{ color: "var(--db-muted)" }}>
        Pick the dependent column, then click every column it depends on.
        Committed as one atomic fan-in edge — no pairwise decomposition.
      </div>

      {!source && (
        <div className="text-[11px] mono p-3 db-card"
             style={{ color: "var(--db-muted)", background: "rgba(255,255,255,0.02)" }}>
          Fetch an Apps Script URL first to materialise columns.
        </div>
      )}

      {source && (
        <>
          {/* Step 1 — child */}
          <div>
            <div className="text-[10px] mono uppercase tracking-wider mb-1"
                 style={{ color: "var(--db-muted)" }}>
              step 1 · dependent column (the child)
            </div>
            <select
              data-testid="wizard-child-select"
              className="db-input text-xs"
              value={child}
              onChange={(e) => { setChild(e.target.value); setParents([]); }}
            >
              <option value="">— select column —</option>
              {cols.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            {child && (
              <div className="mt-2 flex items-center gap-2">
                <span className="db-chip db-chip-orange">
                  <Columns3 className="w-3 h-3" /> {child}
                </span>
                <span className="text-[10px] mono"
                      style={{ color: "var(--db-muted)" }}>← will depend on…</span>
              </div>
            )}
          </div>

          {/* Step 2 — parents */}
          {child && (
            <div>
              <div className="flex items-center justify-between mb-1">
                <div className="text-[10px] mono uppercase tracking-wider"
                     style={{ color: "var(--db-muted)" }}>
                  step 2 · click parent columns ({parents.length} selected)
                </div>
                <div className="flex gap-1">
                  <button data-testid="wizard-all" onClick={selectAll}
                          className="db-btn db-btn-ghost py-0.5 px-1.5 text-[10px]">
                    All
                  </button>
                  <button data-testid="wizard-clear" onClick={clearParents}
                          className="db-btn db-btn-ghost py-0.5 px-1.5 text-[10px]">
                    Clear
                  </button>
                </div>
              </div>
              <div className="relative mb-2">
                <Search className="w-3 h-3 absolute left-3 top-3"
                        style={{ color: "var(--db-muted)" }} />
                <input
                  data-testid="wizard-search"
                  className="db-input text-xs pl-8"
                  placeholder="search columns…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              <div className="flex flex-wrap gap-1.5 max-h-[180px] overflow-y-auto db-card p-2"
                   style={{ background: "rgba(255,255,255,0.015)" }}
                   data-testid="wizard-parent-pool">
                {filteredParents.length === 0 && (
                  <div className="text-[10px] mono"
                       style={{ color: "var(--db-muted)" }}>no other columns</div>
                )}
                {filteredParents.map((c) => {
                  const sel = isParentSelected(c);
                  return (
                    <button
                      key={c}
                      data-testid={`wizard-col-${c}`}
                      onClick={() => toggleParent(c)}
                      className="db-chip text-[11px] cursor-pointer transition"
                      style={
                        sel
                          ? { background: "rgba(0,170,255,0.15)",
                              border: "1px solid rgba(0,170,255,0.5)",
                              color: "#6cd0ff" }
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
            </div>
          )}

          {/* Step 3 — commit */}
          {child && parents.length > 0 && (
            <div className="db-card p-3" style={{ background: "rgba(0,170,255,0.04)" }}
                 data-testid="wizard-preview">
              <div className="text-[10px] mono uppercase tracking-wider mb-2"
                   style={{ color: "var(--db-muted)" }}>
                step 3 · preview & commit
              </div>
              <div className="text-[11px] mono flex flex-wrap items-center gap-1.5 mb-2">
                <span className="db-chip db-chip-orange">{child}</span>
                <ChevronRight className="w-3 h-3 db-accent" />
                <span style={{ color: "var(--db-muted)" }}>dependsOn[{parents.length}]:</span>
                {parents.slice(0, 8).map((p) => (
                  <span key={p} className="db-chip db-chip-blue text-[10px]">
                    <Plus className="w-3 h-3" /> {p}
                  </span>
                ))}
                {parents.length > 8 && (
                  <span className="db-chip db-chip-grey text-[10px]">
                    +{parents.length - 8} more
                  </span>
                )}
              </div>
              <div className="flex items-center justify-between gap-2 mb-2">
                <span className="text-[10px] mono"
                      style={{ color: "var(--db-muted)" }}>
                  cardinality
                </span>
                <span className="db-chip db-chip-orange text-[11px]"
                      data-testid="wizard-cardinality">
                  {parents.length > 1 ? "N:1" : "1:1"}
                </span>
              </div>
              <input
                data-testid="wizard-label"
                className="db-input text-xs mb-2"
                placeholder="(optional) edge label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
              />
              <div className="flex gap-2">
                <button data-testid="wizard-reset" onClick={reset}
                        className="db-btn db-btn-ghost py-1.5 px-2 text-[11px]">
                  <X className="w-3 h-3" /> Reset
                </button>
                <button data-testid="wizard-commit" onClick={onCommit}
                        className="db-btn flex-1 justify-center">
                  <GitMerge className="w-3.5 h-3.5" />
                  Commit fan-in ({parents.length})
                </button>
              </div>
            </div>
          )}

          {/* Existing dependencies for the selected child */}
          {child && existing.length > 0 && (
            <div>
              <div className="text-[10px] mono uppercase tracking-wider mb-1"
                   style={{ color: "var(--db-muted)" }}>
                existing fan-in edges into {child} ({existing.length})
              </div>
              <div className="space-y-1.5" data-testid="wizard-existing-list">
                {existing.map((e) => (
                  <div key={e.id}
                       className="db-card p-2 text-[10px] mono"
                       style={{ background: "rgba(255,255,255,0.015)" }}>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="db-chip db-chip-blue">{e.cardinality}</span>
                      <span style={{ color: "var(--db-muted)" }}>
                        ← {e.parents.length} parents:
                      </span>
                      {e.parents.slice(0, 5).map((p) => (
                        <span key={p} className="db-chip db-chip-orange text-[10px]">{p}</span>
                      ))}
                      {e.parents.length > 5 && (
                        <span className="db-chip db-chip-grey text-[10px]">
                          +{e.parents.length - 5}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
