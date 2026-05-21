// Client-side analytics — mirrors backend logic for instant feedback.
export function analyzeGraph(nodes, edges) {
  const ids = new Set(nodes.map((n) => n.id));
  const adj = new Map();
  const rev = new Map();
  for (const n of nodes) { adj.set(n.id, []); rev.set(n.id, []); }
  for (const e of edges) {
    if (ids.has(e.source) && ids.has(e.target)) {
      adj.get(e.source).push(e.target);
      rev.get(e.target).push(e.source);
    }
  }
  const inDeg = {}, outDeg = {};
  for (const id of ids) { inDeg[id] = rev.get(id).length; outDeg[id] = adj.get(id).length; }

  const orphans = [...ids].filter((id) => inDeg[id] === 0 && outDeg[id] === 0);
  const roots = [...ids].filter((id) => inDeg[id] === 0 && outDeg[id] > 0);
  const sinks = [...ids].filter((id) => outDeg[id] === 0 && inDeg[id] > 0);

  // Cycle detection via DFS
  const color = new Map();
  for (const id of ids) color.set(id, 0);
  const cycles = [];
  const stack = [];
  function dfs(u) {
    color.set(u, 1);
    stack.push(u);
    for (const v of adj.get(u) || []) {
      const c = color.get(v) ?? 0;
      if (c === 0) dfs(v);
      else if (c === 1) {
        const i = stack.indexOf(v);
        if (i >= 0) cycles.push(stack.slice(i).concat(v));
      }
    }
    stack.pop();
    color.set(u, 2);
  }
  for (const id of ids) if (color.get(id) === 0) dfs(id);

  const uniqCycles = [];
  const seen = new Set();
  for (const c of cycles) {
    const k = [...new Set(c)].sort().join("|");
    if (!seen.has(k) && c.length > 1) { seen.add(k); uniqCycles.push(c); }
  }

  // Topo
  const indeg = { ...inDeg };
  const q = [...ids].filter((id) => indeg[id] === 0);
  const topo = [];
  while (q.length) {
    const u = q.shift();
    topo.push(u);
    for (const v of adj.get(u) || []) {
      indeg[v]--;
      if (indeg[v] === 0) q.push(v);
    }
  }
  const isDag = topo.length === ids.size && uniqCycles.length === 0;

  const deg = [...ids].map((id) => ({
    id, in: inDeg[id], out: outDeg[id], total: inDeg[id] + outDeg[id],
  }));
  deg.sort((a, b) => b.total - a.total);
  const bottlenecks = deg.filter((d) => d.total >= 4).slice(0, 5);
  const highCoupling = deg.filter((d) => d.total > 6);

  const pairCount = new Map();
  for (const e of edges) {
    const k = `${e.source}->${e.target}`;
    pairCount.set(k, (pairCount.get(k) || 0) + 1);
  }
  const redundant = [...pairCount.entries()]
    .filter(([, c]) => c > 1)
    .map(([k, c]) => { const [s, t] = k.split("->"); return { source: s, target: t, count: c }; });

  const broken = edges.filter((e) => !ids.has(e.source) || !ids.has(e.target));

  const catOf = (id) => {
    const n = nodes.find((x) => x.id === id);
    return ((n?.data?.category) || "").toLowerCase();
  };
  const badPatterns = [];
  for (const e of edges) {
    const s = catOf(e.source), t = catOf(e.target);
    if ((s.includes("ui") || s.includes("frontend")) && (t.includes("database") || t.includes("db"))) {
      badPatterns.push({ source: e.source, target: e.target, issue: "Frontend/UI directly accessing Database" });
    }
  }

  const n = Math.max(1, ids.size);
  const cyclePenalty = Math.min(40, uniqCycles.length * 15);
  const orphanPenalty = Math.min(20, orphans.length * 4);
  const couplingPenalty = Math.min(20, highCoupling.length * 5);
  const patternPenalty = Math.min(20, badPatterns.length * 5);
  const redundantPenalty = Math.min(10, redundant.length * 3);
  const health = Math.max(0, 100 - cyclePenalty - orphanPenalty - couplingPenalty - patternPenalty - redundantPenalty);

  const avgDeg = deg.reduce((a, d) => a + d.total, 0) / n;
  const dependencyScore = Math.min(100, Math.round(avgDeg * 15));
  const complexity = Math.min(100, Math.round(edges.length * 1.5 + ids.size * 0.8 + uniqCycles.length * 10 + highCoupling.length * 5));

  const insights = [];
  const nameOf = (id) => {
    const n = nodes.find((x) => x.id === id);
    return n?.data?.name || id;
  };
  if (uniqCycles.length) insights.push({ severity: "danger", text: `Circular dependency detected in ${uniqCycles.length} cycle(s). Break the loop or extract a shared service.` });
  if (orphans.length) insights.push({ severity: "warning", text: `${orphans.length} orphan node(s) — connect them or remove if unused.` });
  if (bottlenecks.length) {
    const b = bottlenecks[0];
    insights.push({ severity: "warning", text: `"${nameOf(b.id)}" is a critical bottleneck — ${b.in} in / ${b.out} out.` });
  }
  if (highCoupling.length) insights.push({ severity: "warning", text: `${highCoupling.length} node(s) show excessive coupling (>6 connections).` });
  if (redundant.length) insights.push({ severity: "info", text: `${redundant.length} redundant edge(s) found.` });
  for (const bp of badPatterns) insights.push({ severity: "danger", text: `"${nameOf(bp.source)}" → "${nameOf(bp.target)}" — ${bp.issue}.` });
  if (isDag && ids.size > 3 && insights.length === 0)
    insights.push({ severity: "success", text: `Clean directed-acyclic architecture with ${ids.size} nodes and ${edges.length} edges.` });
  if (!insights.length) insights.push({ severity: "info", text: "No issues detected yet — add more nodes or edges to map your architecture." });

  return {
    nodes: ids.size, edges: edges.length,
    inDeg, outDeg, orphans, roots, sinks, cycles: uniqCycles,
    bottlenecks, highCoupling, redundant, broken, badPatterns,
    isDag, topo: isDag ? topo : null,
    scores: { health, dependency: dependencyScore, complexity },
    insights,
  };
}
