import { create } from "zustand";
import { wouldCreateCycle, computeRewire } from "./chainGraph";

const uid = (p = "x") =>
  `${p}-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e6).toString(36)}`;

const refEq = (a, b) => a.t === b.t && a.i === b.i;
const dedupRefs = (refs) => {
  const out = [];
  for (const r of refs) if (!out.some((x) => refEq(x, r))) out.push(r);
  return out;
};

const inferCard = (from, to) => {
  const s = from.length > 1 ? "N" : "1";
  const t = to.length > 1 ? "N" : "1";
  return `${s}:${t}`;
};

export const useStudio = create((set, get) => ({
  // --- ingested source (structure only)
  source: null,          // { url, headers, rowIds, fetchedAt }

  // --- authored state
  groups: [],            // [{ id, name, kind:'row'|'col', members:[rowId|colLabel] }]
  edges: [],             // [{ id, from:Ref[], to:Ref[], cardinality, label }]

  // --- palette / picker
  paletteTab: "rows",    // 'rows' | 'cols' | 'groups'
  paletteSearch: "",
  paletteSelection: [],  // array of Refs

  // --- builder
  sourceSelection: [],
  targetSelection: [],

  // --- Column Dependency Chains (DAG over columnId namespace)
  //  chainNodes: [columnId, ...]
  //  chainEdges: [{ id, from:columnId, to:columnId, kind:'direct'|'skip', label }]
  //  Transitive edges are NEVER stored — derived in chainGraph.js
  chainNodes: [],
  chainEdges: [],
  chainSelected: null, // columnId of inspected node

  // ---- bootstrapping
  loadFromShare: (decoded) =>
    set({
      source: decoded.source || null,
      groups: decoded.groups || [],
      edges: decoded.edges || [],
      chainNodes: decoded.chainNodes || [],
      chainEdges: decoded.chainEdges || [],
      paletteSelection: [],
      sourceSelection: [],
      targetSelection: [],
      chainSelected: null,
    }),

  setSource: (src) =>
    set({
      source: src,
      // Resetting groups/edges would lose work — keep them; share-link is portable.
    }),

  resetAll: () =>
    set({
      source: null, groups: [], edges: [],
      chainNodes: [], chainEdges: [], chainSelected: null,
      paletteSelection: [], sourceSelection: [], targetSelection: [],
      paletteTab: "rows", paletteSearch: "",
    }),

  // ---- chain operations
  addChainNode: (columnId) =>
    set((s) => {
      if (!columnId) return {};
      if (s.chainNodes.includes(columnId)) return {};
      return { chainNodes: [...s.chainNodes, columnId] };
    }),

  addChainNodes: (columnIds) =>
    set((s) => {
      const fresh = columnIds.filter((c) => c && !s.chainNodes.includes(c));
      if (!fresh.length) return {};
      return { chainNodes: [...s.chainNodes, ...fresh] };
    }),

  selectChainNode: (columnId) => set({ chainSelected: columnId || null }),

  // Add a direct/skip edge. Returns { ok, reason } via callback pattern.
  commitChainEdge: (from, to, kind, label) => {
    const s = get();
    if (!from || !to || from === to) return { ok: false, reason: "self_loop" };
    if (!s.chainNodes.includes(from) || !s.chainNodes.includes(to))
      return { ok: false, reason: "missing_node" };
    if (kind !== "direct" && kind !== "skip")
      return { ok: false, reason: "bad_kind" };
    if (s.chainEdges.some((e) => e.from === from && e.to === to && e.kind === kind))
      return { ok: false, reason: "duplicate" };
    if (wouldCreateCycle(s.chainNodes, s.chainEdges, from, to))
      return { ok: false, reason: "cycle" };
    const e = { id: uid("ce"), from, to, kind, label: label || "" };
    set({ chainEdges: [...s.chainEdges, e] });
    return { ok: true };
  },

  deleteChainEdge: (id) =>
    set((s) => ({ chainEdges: s.chainEdges.filter((e) => e.id !== id) })),

  updateChainEdgeLabel: (id, label) =>
    set((s) => ({
      chainEdges: s.chainEdges.map((e) => (e.id === id ? { ...e, label } : e)),
    })),

  // Delete a chain node. mode = 'disconnect' (drop incident edges) or 'rewire'
  // ('rewire' first inserts P×S direct edges, then drops incident edges).
  deleteChainNode: (columnId, mode = "disconnect") =>
    set((s) => {
      if (!s.chainNodes.includes(columnId)) return {};
      let edges = s.chainEdges;
      if (mode === "rewire") {
        const { news } = computeRewire(s.chainNodes, edges, columnId);
        for (const n of news) {
          if (!edges.some((e) => e.from === n.from && e.to === n.to && e.kind === "direct")) {
            edges = [...edges, { id: uid("ce"), from: n.from, to: n.to, kind: "direct", label: "" }];
          }
        }
      }
      edges = edges.filter((e) => e.from !== columnId && e.to !== columnId);
      return {
        chainNodes: s.chainNodes.filter((n) => n !== columnId),
        chainEdges: edges,
        chainSelected: s.chainSelected === columnId ? null : s.chainSelected,
      };
    }),

  resetChains: () =>
    set({ chainNodes: [], chainEdges: [], chainSelected: null }),

  // ---- palette
  setPaletteTab: (t) => set({ paletteTab: t, paletteSelection: [], paletteSearch: "" }),
  setPaletteSearch: (q) => set({ paletteSearch: q }),
  togglePaletteItem: (ref) =>
    set((s) => {
      const exists = s.paletteSelection.some((r) => refEq(r, ref));
      return {
        paletteSelection: exists
          ? s.paletteSelection.filter((r) => !refEq(r, ref))
          : [...s.paletteSelection, ref],
      };
    }),
  selectAllPalette: (refs) => set({ paletteSelection: refs }),
  clearPaletteSelection: () => set({ paletteSelection: [] }),

  // ---- groups
  saveSelectionAsGroup: (name) =>
    set((s) => {
      const sel = s.paletteSelection;
      if (!sel.length) return {};
      // Only allow uniform kind (row or col), and only single-kind items.
      const kinds = new Set(sel.map((r) => r.t));
      if (kinds.size > 1 || !["row", "col"].some((k) => kinds.has(k))) return {};
      const kind = sel[0].t;
      const grp = {
        id: uid("g"),
        name: name || `Group ${s.groups.length + 1}`,
        kind,
        members: sel.map((r) => r.i),
      };
      return { groups: [...s.groups, grp], paletteSelection: [] };
    }),
  renameGroup: (id, name) =>
    set((s) => ({ groups: s.groups.map((g) => (g.id === id ? { ...g, name } : g)) })),
  deleteGroup: (id) =>
    set((s) => {
      // Remove the group itself + any edges that referenced it
      const refMatches = (r) => !(r.t === "group" && r.i === id);
      const edges = s.edges
        .map((e) => ({
          ...e,
          from: e.from.filter(refMatches),
          to: e.to.filter(refMatches),
        }))
        .filter((e) => e.from.length && e.to.length);
      return { groups: s.groups.filter((g) => g.id !== id), edges };
    }),

  // ---- builder
  setSourceFromSelection: () =>
    set((s) => ({ sourceSelection: dedupRefs(s.paletteSelection) })),
  setTargetFromSelection: () =>
    set((s) => ({ targetSelection: dedupRefs(s.paletteSelection) })),
  setSelectionWholeRow: () =>
    set((s) =>
      s.source ? { paletteSelection: s.source.rowIds.map((i) => ({ t: "row", i })) } : {}
    ),
  setSelectionWholeCol: () =>
    set((s) =>
      s.source ? { paletteSelection: s.source.headers.map((i) => ({ t: "col", i })) } : {}
    ),
  swapEnds: () =>
    set((s) => ({ sourceSelection: s.targetSelection, targetSelection: s.sourceSelection })),
  clearBuilder: () => set({ sourceSelection: [], targetSelection: [] }),

  commitEdge: (label) =>
    set((s) => {
      const from = dedupRefs(s.sourceSelection);
      const to = dedupRefs(s.targetSelection);
      if (!from.length || !to.length) return {};
      const card = inferCard(from, to);
      const edge = { id: uid("e"), from, to, cardinality: card, label: label || "" };
      return { edges: [...s.edges, edge], sourceSelection: [], targetSelection: [] };
    }),

  // Atomic column-on-column dependency set: child depends on [parents...]
  // Stored as ONE edge with from=parents, to=[child]. No pairwise decomposition.
  commitColumnDependency: (child, parents, label) =>
    set((s) => {
      if (!child || !parents || !parents.length) return {};
      const childRef = { t: "col", i: child };
      const parentRefs = dedupRefs(
        parents.filter((p) => p && p !== child).map((p) => ({ t: "col", i: p }))
      );
      if (!parentRefs.length) return {};
      const card = `${parentRefs.length > 1 ? "N" : "1"}:1`;
      const edge = {
        id: uid("e"),
        from: parentRefs,
        to: [childRef],
        cardinality: card,
        label: label || "",
        fanIn: true,
      };
      return { edges: [...s.edges, edge] };
    }),

  deleteEdge: (id) =>
    set((s) => ({ edges: s.edges.filter((e) => e.id !== id) })),
  updateEdgeLabel: (id, label) =>
    set((s) => ({ edges: s.edges.map((e) => (e.id === id ? { ...e, label } : e)) })),
  updateEdgeCardinality: (id, card) =>
    set((s) => ({ edges: s.edges.map((e) => (e.id === id ? { ...e, cardinality: card } : e)) })),
}));

export const refKey = (r) => `${r.t}:${r.i}`;
export const refsEq = refEq;
