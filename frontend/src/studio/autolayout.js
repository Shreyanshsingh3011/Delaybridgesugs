import dagre from "dagre";

export function autoLayout(nodes, edges, direction = "LR") {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 60, ranksep: 90, edgesep: 30 });

  const NW = 220, NH = 110;
  for (const n of nodes) {
    g.setNode(n.id, { width: NW, height: NH });
  }
  for (const e of edges) {
    g.setEdge(e.source, e.target);
  }
  dagre.layout(g);
  return nodes.map((n) => {
    const pos = g.node(n.id);
    if (!pos) return n;
    return {
      ...n,
      position: { x: pos.x - NW / 2, y: pos.y - NH / 2 },
      targetPosition: direction === "LR" ? "left" : "top",
      sourcePosition: direction === "LR" ? "right" : "bottom",
    };
  });
}

export function forceLayout(nodes, edges, iterations = 100) {
  // Lightweight force layout — repulsion + spring on edges.
  const pos = new Map();
  nodes.forEach((n, i) => {
    pos.set(n.id, {
      x: n.position?.x ?? 200 + (i % 6) * 180,
      y: n.position?.y ?? 200 + Math.floor(i / 6) * 140,
    });
  });
  const k = 180;
  for (let it = 0; it < iterations; it++) {
    const f = new Map();
    nodes.forEach((n) => f.set(n.id, { x: 0, y: 0 }));
    // Repulsion
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = pos.get(nodes[i].id), b = pos.get(nodes[j].id);
        const dx = a.x - b.x, dy = a.y - b.y;
        const d2 = Math.max(dx * dx + dy * dy, 1);
        const r = (k * k) / d2;
        const fa = f.get(nodes[i].id), fb = f.get(nodes[j].id);
        fa.x += dx * r * 0.02; fa.y += dy * r * 0.02;
        fb.x -= dx * r * 0.02; fb.y -= dy * r * 0.02;
      }
    }
    // Spring
    for (const e of edges) {
      const a = pos.get(e.source), b = pos.get(e.target);
      if (!a || !b) continue;
      const dx = b.x - a.x, dy = b.y - a.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const force = (d - k) * 0.05;
      const fx = (dx / d) * force, fy = (dy / d) * force;
      const fa = f.get(e.source), fb = f.get(e.target);
      fa.x += fx; fa.y += fy;
      fb.x -= fx; fb.y -= fy;
    }
    // Apply
    const t = 1 - it / iterations;
    for (const n of nodes) {
      const p = pos.get(n.id), ff = f.get(n.id);
      p.x += Math.max(Math.min(ff.x * t, 30), -30);
      p.y += Math.max(Math.min(ff.y * t, 30), -30);
    }
  }
  return nodes.map((n) => ({ ...n, position: pos.get(n.id) }));
}
