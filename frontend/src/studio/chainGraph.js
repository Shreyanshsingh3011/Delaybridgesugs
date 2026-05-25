// Pure graph algorithms for the Column Dependency Chaining subsystem.
// Operates on a graph (V, E) where:
//   V = set of columnIds (strings)
//   E = labelled directed edges, each with kind in {'direct','skip'}
// Transitive edges are NEVER stored — they are derived on demand from E.

// ---- adjacency builders ----
export function buildAdj(nodes, edges) {
  const out = new Map();
  const inn = new Map();
  for (const n of nodes) { out.set(n, new Set()); inn.set(n, new Set()); }
  for (const e of edges) {
    if (!out.has(e.from)) out.set(e.from, new Set());
    if (!inn.has(e.to))   inn.set(e.to, new Set());
    out.get(e.from).add(e.to);
    inn.get(e.to).add(e.from);
  }
  return { out, inn };
}

// ---- reachability index over (direct ∪ skip) ----
export function buildReach(nodes, edges) {
  const { out, inn } = buildAdj(nodes, edges);
  const desc = new Map();   // node -> Set(descendants)
  const anc  = new Map();   // node -> Set(ancestors)
  for (const n of nodes) {
    desc.set(n, bfs(out, n));
    anc.set(n,  bfs(inn, n));
  }
  return { out, inn, desc, anc };
}

function bfs(adj, start) {
  const visited = new Set();
  const q = [];
  for (const v of (adj.get(start) || [])) { visited.add(v); q.push(v); }
  while (q.length) {
    const cur = q.shift();
    for (const v of (adj.get(cur) || [])) {
      if (!visited.has(v)) { visited.add(v); q.push(v); }
    }
  }
  return visited;
}

// Would adding u -> v create a cycle in (V, E)? (E here is direct ∪ skip)
export function wouldCreateCycle(nodes, edges, u, v) {
  if (u === v) return true;
  // cycle iff v already reaches u
  const { desc } = buildReach(nodes, edges);
  return (desc.get(v) || new Set()).has(u);
}

// Direct adjacency: only kind==='direct'
export function buildDirectAdj(nodes, edges) {
  return buildAdj(nodes, edges.filter((e) => e.kind === "direct"));
}

// For a node n, in the FULL graph (direct+skip), return its descendants/ancestors.
// Direct = neighbours via 'direct' edges only.
// Transitive = reachable nodes minus direct neighbours minus self.
export function nodeInspection(nodes, edges, n) {
  const direct = edges.filter((e) => e.kind === "direct");
  const directOut = direct.filter((e) => e.from === n).map((e) => e.to);
  const directIn  = direct.filter((e) => e.to   === n).map((e) => e.from);
  const skip = edges.filter((e) => e.kind === "skip");
  const skipOut = skip.filter((e) => e.from === n).map((e) => e.to);
  const skipIn  = skip.filter((e) => e.to   === n).map((e) => e.from);

  const { desc, anc } = buildReach(nodes, edges);
  const allDesc = desc.get(n) || new Set();
  const allAnc  = anc.get(n)  || new Set();

  const directOutSet = new Set(directOut);
  const directInSet  = new Set(directIn);
  const skipOutSet   = new Set(skipOut);
  const skipInSet    = new Set(skipIn);

  const transitiveDesc = [...allDesc].filter(
    (x) => !directOutSet.has(x) && !skipOutSet.has(x) && x !== n
  );
  const transitiveAnc  = [...allAnc].filter(
    (x) => !directInSet.has(x) && !skipInSet.has(x) && x !== n
  );

  return {
    directOut, directIn, skipOut, skipIn,
    transitiveDesc, transitiveAnc,
  };
}

// Topological sort (Kahn) — returns null if cyclic.
export function topoSort(nodes, edges) {
  const { out, inn } = buildAdj(nodes, edges);
  const deg = new Map();
  for (const n of nodes) deg.set(n, (inn.get(n) || new Set()).size);
  const q = [...nodes].filter((n) => deg.get(n) === 0);
  const order = [];
  while (q.length) {
    const u = q.shift();
    order.push(u);
    for (const v of (out.get(u) || [])) {
      deg.set(v, deg.get(v) - 1);
      if (deg.get(v) === 0) q.push(v);
    }
  }
  return order.length === nodes.length ? order : null;
}

// Compute the rewire payload when deleting an intermediate node v.
// Returns the set of new DIRECT edges that should be inserted to preserve
// reachability (Cartesian product of direct predecessors × direct successors).
export function computeRewire(nodes, edges, v) {
  const direct = edges.filter((e) => e.kind === "direct");
  const preds = [...new Set(direct.filter((e) => e.to === v).map((e) => e.from))];
  const succs = [...new Set(direct.filter((e) => e.from === v).map((e) => e.to))];
  const news = [];
  for (const p of preds) {
    for (const s of succs) {
      if (p === s) continue;
      news.push({ from: p, to: s, kind: "direct" });
    }
  }
  return { preds, succs, news };
}

// Drop edges incident to a node.
export function withoutNode(nodes, edges, v) {
  const nextNodes = nodes.filter((n) => n !== v);
  const nextEdges = edges.filter((e) => e.from !== v && e.to !== v);
  return { nodes: nextNodes, edges: nextEdges };
}

// Insert an edge if it doesn't already exist with the same kind.
export function upsertEdge(edges, from, to, kind) {
  if (edges.some((e) => e.from === from && e.to === to && e.kind === kind)) {
    return edges;
  }
  return [...edges, { from, to, kind }];
}
