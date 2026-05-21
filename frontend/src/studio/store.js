import { create } from "zustand";
import { applyNodeChanges, applyEdgeChanges, addEdge } from "reactflow";

const NODE_CATEGORIES = [
  "Application", "Backend", "Database", "Service", "Queue", "External",
  "Storage", "AI", "Auth", "UI", "API", "Worker",
];

const DEPENDENCY_TYPES = [
  "Required", "Optional", "Direct", "Indirect", "Runtime", "Build-time",
  "API", "Database", "Event-driven", "Shared", "Sequential", "Blocking",
];

export const useStudio = create((set, get) => ({
  mapId: null,
  title: "Untitled Architecture Map",
  shareToken: null,
  shareMode: "private",
  sourceUrl: "",
  nodes: [],
  edges: [],
  selectedId: null,
  filterCategory: "",
  filterType: "",
  searchTerm: "",
  dirty: false,

  setMap: (m) => set({
    mapId: m.id,
    title: m.title || "Untitled Architecture Map",
    shareToken: m.share_token || null,
    shareMode: m.share_mode || "private",
    sourceUrl: m.source_url || "",
    nodes: m.nodes || [],
    edges: m.edges || [],
    dirty: false,
  }),

  setTitle: (t) => set({ title: t, dirty: true }),

  onNodesChange: (changes) =>
    set((s) => ({ nodes: applyNodeChanges(changes, s.nodes), dirty: true })),

  onEdgesChange: (changes) =>
    set((s) => ({ edges: applyEdgeChanges(changes, s.edges), dirty: true })),

  onConnect: (conn) =>
    set((s) => ({
      edges: addEdge(
        {
          ...conn,
          id: `e-${conn.source}-${conn.target}-${Date.now()}`,
          type: "dependency",
          animated: true,
          data: { type: "Required", priority: "Normal", note: "" },
          label: "Required",
        },
        s.edges
      ),
      dirty: true,
    })),

  setNodes: (nodes) => set({ nodes, dirty: true }),
  setEdges: (edges) => set({ edges, dirty: true }),

  addNode: (partial) =>
    set((s) => {
      const id = partial.id || `n-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
      const node = {
        id,
        type: "custom",
        position: partial.position || { x: 80 + Math.random() * 200, y: 80 + Math.random() * 200 },
        data: {
          name: partial.name || "New node",
          category: partial.category || "Service",
          type: partial.type || "Service",
          status: partial.status || "active",
          notes: "",
          stage: partial.stage || null,
          tags: partial.tags || [],
        },
      };
      return { nodes: [...s.nodes, node], dirty: true };
    }),

  importRecords: (rows) =>
    set((s) => {
      const usedIds = new Set(s.nodes.map((n) => n.id));
      const cols = 4;
      let added = 0;
      const newNodes = rows.map((r, i) => {
        const candidate = String(r.id ?? r.name ?? `imp-${Date.now()}-${i}`);
        let nid = candidate;
        let k = 1;
        while (usedIds.has(nid)) { nid = `${candidate}-${k++}`; }
        usedIds.add(nid);
        added++;
        return {
          id: nid,
          type: "custom",
          position: {
            x: 120 + (i % cols) * 260,
            y: 120 + Math.floor(i / cols) * 160,
          },
          data: {
            name: r.name || r.title || r.activity || `Node ${i + 1}`,
            category: r.category || r.stage || "Service",
            type: r.type || "Service",
            status: r.status || "active",
            notes: r.notes || r.description || "",
            stage: r.stage || null,
            tags: r.tags || [],
            raw: r,
          },
        };
      });
      return { nodes: [...s.nodes, ...newNodes], dirty: true };
    }),

  updateNode: (id, patch) =>
    set((s) => ({
      nodes: s.nodes.map((n) =>
        n.id === id ? { ...n, data: { ...n.data, ...patch } } : n
      ),
      dirty: true,
    })),

  removeNode: (id) =>
    set((s) => ({
      nodes: s.nodes.filter((n) => n.id !== id),
      edges: s.edges.filter((e) => e.source !== id && e.target !== id),
      selectedId: s.selectedId === id ? null : s.selectedId,
      dirty: true,
    })),

  duplicateNode: (id) =>
    set((s) => {
      const n = s.nodes.find((x) => x.id === id);
      if (!n) return {};
      const newId = `${n.id}-copy-${Date.now()}`;
      return {
        nodes: [
          ...s.nodes,
          { ...n, id: newId,
            position: { x: n.position.x + 40, y: n.position.y + 40 },
            data: { ...n.data, name: `${n.data.name} (copy)` } },
        ],
        dirty: true,
      };
    }),

  updateEdge: (id, patch) =>
    set((s) => ({
      edges: s.edges.map((e) =>
        e.id === id
          ? { ...e, ...patch, data: { ...e.data, ...(patch.data || {}) } }
          : e
      ),
      dirty: true,
    })),

  removeEdge: (id) =>
    set((s) => ({ edges: s.edges.filter((e) => e.id !== id), dirty: true })),

  select: (id) => set({ selectedId: id }),

  setFilter: (key, value) => set({ [key]: value }),
  clearDirty: () => set({ dirty: false }),

  CATEGORIES: NODE_CATEGORIES,
  DEPENDENCY_TYPES,
}));
