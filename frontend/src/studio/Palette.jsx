import { useMemo, useState } from "react";
import { useStudio, refKey, refsEq } from "./store";
import {
  Rows3, Columns3, Layers, Search, CheckSquare, Square, Plus,
  ArrowDownToLine, ArrowUpFromLine, Trash2, ArrowRightLeft, GitCommit,
} from "lucide-react";

const KIND_LABEL = { row: "row", col: "col", group: "group" };

export default function Palette() {
  const {
    source, groups, paletteTab, paletteSearch, paletteSelection,
    sourceSelection, targetSelection,
    setPaletteTab, setPaletteSearch, togglePaletteItem,
    selectAllPalette, clearPaletteSelection,
    setSelectionWholeRow, setSelectionWholeCol,
    saveSelectionAsGroup, deleteGroup, renameGroup,
    setSourceFromSelection, setTargetFromSelection, swapEnds, clearBuilder,
    commitEdge,
  } = useStudio();

  const [groupName, setGroupName] = useState("");
  const [edgeLabel, setEdgeLabel] = useState("");

  const items = useMemo(() => {
    if (!source && paletteTab !== "groups") return [];
    if (paletteTab === "rows") {
      return (source.rowIds || []).map((id) => ({ t: "row", i: id, label: id }));
    }
    if (paletteTab === "cols") {
      return (source.headers || []).map((h) => ({ t: "col", i: h, label: h }));
    }
    return groups.map((g) => ({
      t: "group", i: g.id, label: g.name,
      kindOf: g.kind, count: g.members.length, group: g,
    }));
  }, [source, paletteTab, groups]);

  const filtered = useMemo(() => {
    const q = paletteSearch.trim().toLowerCase();
    if (!q) return items;
    return items.filter((it) => String(it.label).toLowerCase().includes(q));
  }, [items, paletteSearch]);

  const isSelected = (ref) => paletteSelection.some((r) => refsEq(r, ref));

  const inferCard = (a, b) =>
    `${a.length > 1 ? "N" : "1"}:${b.length > 1 ? "N" : "1"}`;

  return (
    <div className="db-card p-4 flex flex-col h-full" data-testid="studio-palette"
         style={{ width: 360 }}>
      {/* Tabs */}
      <div className="flex gap-1 mb-3">
        <TabBtn active={paletteTab === "rows"} onClick={() => setPaletteTab("rows")}
                icon={Rows3} testid="palette-tab-rows" label={`Rows${source ? ` (${source.rowIds.length})` : ""}`} />
        <TabBtn active={paletteTab === "cols"} onClick={() => setPaletteTab("cols")}
                icon={Columns3} testid="palette-tab-cols" label={`Cols${source ? ` (${source.headers.length})` : ""}`} />
        <TabBtn active={paletteTab === "groups"} onClick={() => setPaletteTab("groups")}
                icon={Layers} testid="palette-tab-groups" label={`Groups (${groups.length})`} />
      </div>

      {/* Search */}
      <div className="relative mb-2">
        <Search className="w-3 h-3 absolute left-3 top-3" style={{ color: "var(--db-muted)" }} />
        <input
          data-testid="palette-search-input"
          className="db-input text-xs pl-8"
          placeholder={paletteTab === "groups" ? "Search groups…" : `Search ${paletteTab}…`}
          value={paletteSearch}
          onChange={(e) => setPaletteSearch(e.target.value)}
        />
      </div>

      {/* Bulk actions */}
      <div className="flex items-center gap-1 mb-2 flex-wrap">
        <button data-testid="palette-select-all" onClick={() => selectAllPalette(filtered)}
                disabled={!filtered.length}
                className="db-btn db-btn-ghost py-1 px-2 text-[10px]">
          <CheckSquare className="w-3 h-3" /> All
        </button>
        <button data-testid="palette-clear" onClick={clearPaletteSelection}
                disabled={!paletteSelection.length}
                className="db-btn db-btn-ghost py-1 px-2 text-[10px]">
          <Square className="w-3 h-3" /> Clear
        </button>
        {source && paletteTab === "rows" && (
          <button data-testid="palette-whole-row" onClick={setSelectionWholeRow}
                  className="db-btn db-btn-ghost py-1 px-2 text-[10px]">whole-row band</button>
        )}
        {source && paletteTab === "cols" && (
          <button data-testid="palette-whole-col" onClick={setSelectionWholeCol}
                  className="db-btn db-btn-ghost py-1 px-2 text-[10px]">whole-col band</button>
        )}
        <span className="ml-auto text-[10px] mono"
              style={{ color: "var(--db-muted)" }}>
          {paletteSelection.length} selected
        </span>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto db-card p-1 mb-3"
           style={{ minHeight: 160 }}
           data-testid="palette-list">
        {!source && paletteTab !== "groups" && (
          <div className="text-[11px] mono p-3" style={{ color: "var(--db-muted)" }}>
            Fetch an Apps Script URL to materialise rows & columns.
          </div>
        )}
        {source && filtered.length === 0 && (
          <div className="text-[11px] mono p-3" style={{ color: "var(--db-muted)" }}>
            no matches
          </div>
        )}
        {filtered.map((it) => {
          const sel = isSelected(it);
          return (
            <div key={refKey(it)}
                 onClick={() => togglePaletteItem({ t: it.t, i: it.i })}
                 data-testid={`palette-item-${it.t}-${it.i}`}
                 className="flex items-center gap-2 py-1 px-2 rounded cursor-pointer hover:bg-white/5 transition"
                 style={sel ? { background: "rgba(0,170,255,0.10)" } : {}}>
              <span className="w-3.5 h-3.5 flex items-center justify-center">
                {sel ? <CheckSquare className="w-3.5 h-3.5 db-accent" />
                     : <Square className="w-3.5 h-3.5" style={{ color: "var(--db-muted)" }} />}
              </span>
              <span className={`db-chip ${it.t === "row" ? "db-chip-blue" : it.t === "col" ? "db-chip-orange" : "db-chip-purple"}`}>
                {it.t === "group" ? KIND_LABEL[it.kindOf] : KIND_LABEL[it.t]}
              </span>
              <span className="text-xs mono truncate flex-1">{it.label}</span>
              {it.t === "group" && (
                <>
                  <span className="text-[10px] mono" style={{ color: "var(--db-muted)" }}>
                    {it.count}
                  </span>
                  <button onClick={(e) => { e.stopPropagation(); const n = prompt("Rename group", it.label); if (n) renameGroup(it.i, n); }}
                          className="text-[10px] db-accent hover:underline">rename</button>
                  <button onClick={(e) => { e.stopPropagation(); if (confirm("Delete group?")) deleteGroup(it.i); }}
                          className="text-[10px] db-danger hover:underline">remove</button>
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* Group create */}
      {paletteTab !== "groups" && paletteSelection.length > 0 && (
        <div className="flex items-center gap-2 mb-3" data-testid="palette-group-bar">
          <input className="db-input text-xs" placeholder="group name…"
                 data-testid="palette-group-name"
                 value={groupName} onChange={(e) => setGroupName(e.target.value)} />
          <button data-testid="palette-save-group"
                  className="db-btn"
                  onClick={() => { saveSelectionAsGroup(groupName.trim()); setGroupName(""); }}>
            <Plus className="w-3.5 h-3.5" /> Group
          </button>
        </div>
      )}

      {/* Builder */}
      <div className="db-card p-3" data-testid="edge-builder">
        <div className="text-[11px] mono uppercase tracking-wider mb-2"
             style={{ color: "var(--db-muted)" }}>edge builder</div>

        <div className="flex items-center gap-2 mb-2">
          <button data-testid="builder-set-source" onClick={setSourceFromSelection}
                  disabled={!paletteSelection.length}
                  className="db-btn db-btn-ghost py-1.5 px-2 text-[11px] flex-1 justify-center">
            <ArrowUpFromLine className="w-3 h-3" /> Set as source
          </button>
          <button data-testid="builder-set-target" onClick={setTargetFromSelection}
                  disabled={!paletteSelection.length}
                  className="db-btn db-btn-ghost py-1.5 px-2 text-[11px] flex-1 justify-center">
            <ArrowDownToLine className="w-3 h-3" /> Set as target
          </button>
        </div>

        <SelectionPills label="SOURCE" refs={sourceSelection} testid="builder-source-pills" />
        <SelectionPills label="TARGET" refs={targetSelection} testid="builder-target-pills" />

        {(sourceSelection.length > 0 && targetSelection.length > 0) && (
          <>
            <div className="flex items-center justify-center mt-1 mb-2 text-[10px] mono"
                 style={{ color: "var(--db-muted)" }}>
              cardinality
              <span className="ml-2 db-chip db-chip-blue text-[11px]"
                    data-testid="builder-cardinality">
                {inferCard(sourceSelection, targetSelection)}
              </span>
            </div>
            <input className="db-input text-xs mb-2"
                   placeholder="(optional) edge label"
                   data-testid="builder-edge-label"
                   value={edgeLabel} onChange={(e) => setEdgeLabel(e.target.value)} />
            <div className="flex gap-2">
              <button data-testid="builder-swap" onClick={swapEnds}
                      className="db-btn db-btn-ghost py-1 px-2 text-[11px]">
                <ArrowRightLeft className="w-3 h-3" /> Swap
              </button>
              <button data-testid="builder-clear" onClick={clearBuilder}
                      className="db-btn db-btn-ghost py-1 px-2 text-[11px]">
                <Trash2 className="w-3 h-3" /> Clear
              </button>
              <button data-testid="builder-commit" onClick={() => { commitEdge(edgeLabel.trim()); setEdgeLabel(""); }}
                      className="db-btn flex-1 justify-center">
                <GitCommit className="w-3.5 h-3.5" /> Commit edge
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function TabBtn({ active, onClick, icon: Icon, label, testid }) {
  return (
    <button onClick={onClick}
            data-testid={testid}
            className="db-btn db-btn-ghost py-1.5 px-2.5 text-[11px] flex-1 justify-center"
            style={active ? { borderColor: "rgba(0,170,255,0.5)", background: "rgba(0,170,255,0.08)", color: "#e7e8ee" } : {}}>
      <Icon className="w-3 h-3" /> {label}
    </button>
  );
}

function SelectionPills({ label, refs, testid }) {
  return (
    <div className="mb-2" data-testid={testid}>
      <div className="text-[10px] mono uppercase tracking-wider mb-1"
           style={{ color: "var(--db-muted)" }}>{label} ({refs.length})</div>
      {refs.length === 0 ? (
        <div className="text-[10px] mono" style={{ color: "var(--db-muted)" }}>— empty —</div>
      ) : (
        <div className="flex flex-wrap gap-1 max-h-[60px] overflow-y-auto">
          {refs.slice(0, 24).map((r, i) => (
            <span key={i}
                  className={`db-chip text-[10px] ${r.t === "row" ? "db-chip-blue" : r.t === "col" ? "db-chip-orange" : "db-chip-purple"}`}>
              {r.t} · {r.i}
            </span>
          ))}
          {refs.length > 24 && (
            <span className="db-chip db-chip-grey text-[10px]">+{refs.length - 24} more</span>
          )}
        </div>
      )}
    </div>
  );
}
