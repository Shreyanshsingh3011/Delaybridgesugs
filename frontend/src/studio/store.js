import { create } from "zustand";

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

  // ---- bootstrapping
  loadFromShare: (decoded) =>
    set({
      source: decoded.source || null,
      groups: decoded.groups || [],
      edges: decoded.edges || [],
      paletteSelection: [],
      sourceSelection: [],
      targetSelection: [],
    }),

  setSource: (src) =>
    set({
      source: src,
      // Resetting groups/edges would lose work — keep them; share-link is portable.
    }),

  resetAll: () =>
    set({
      source: null, groups: [], edges: [],
      paletteSelection: [], sourceSelection: [], targetSelection: [],
      paletteTab: "rows", paletteSearch: "",
    }),

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

  deleteEdge: (id) =>
    set((s) => ({ edges: s.edges.filter((e) => e.id !== id) })),
  updateEdgeLabel: (id, label) =>
    set((s) => ({ edges: s.edges.map((e) => (e.id === id ? { ...e, label } : e)) })),
  updateEdgeCardinality: (id, card) =>
    set((s) => ({ edges: s.edges.map((e) => (e.id === id ? { ...e, cardinality: card } : e)) })),
}));

export const refKey = (r) => `${r.t}:${r.i}`;
export const refsEq = refEq;
