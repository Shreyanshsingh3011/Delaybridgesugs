// Standalone Node test for chainGraph.js pure algorithms + codec round-trip.
// Run: node /app/frontend/src/studio/__tests__/chain_pure.test.mjs

import {
  buildAdj, buildReach, wouldCreateCycle, nodeInspection,
  topoSort, computeRewire, withoutNode, upsertEdge,
} from "../chainGraph.js";

let pass = 0, fail = 0;
const eq = (a, b, msg) => {
  const A = JSON.stringify(a), B = JSON.stringify(b);
  if (A === B) { pass++; console.log("PASS:", msg); }
  else { fail++; console.log("FAIL:", msg, "expected", B, "got", A); }
};
const ok = (cond, msg) => eq(!!cond, true, msg);

// --- Chain A->B->C (direct)
const nodes = ["A", "B", "C"];
const edges = [
  { id: "e1", from: "A", to: "B", kind: "direct" },
  { id: "e2", from: "B", to: "C", kind: "direct" },
];

// reach
const { desc, anc } = buildReach(nodes, edges);
eq([...desc.get("A")].sort(), ["B", "C"], "A descendants = {B,C}");
eq([...anc.get("C")].sort(), ["A", "B"], "C ancestors = {A,B}");

// cycle: adding C->A must be rejected
ok(wouldCreateCycle(nodes, edges, "C", "A"), "C->A would create cycle");
ok(!wouldCreateCycle(nodes, edges, "A", "C"), "A->C is fine (already reachable, not a cycle)");
ok(wouldCreateCycle(nodes, edges, "A", "A"), "self-loop A->A treated as cycle");

// inspection
const inspC = nodeInspection(nodes, edges, "C");
eq(inspC.directIn, ["B"], "C directIn = [B]");
eq(inspC.directOut, [], "C directOut = []");
eq(inspC.transitiveAnc.sort(), ["A"], "C transitiveAnc = [A]");

const inspA = nodeInspection(nodes, edges, "A");
eq(inspA.directOut, ["B"], "A directOut = [B]");
eq(inspA.transitiveDesc.sort(), ["C"], "A transitiveDesc = [C]");

// topo
eq(topoSort(nodes, edges), ["A", "B", "C"], "topo A,B,C");

// rewire B
const r = computeRewire(nodes, edges, "B");
eq(r.preds, ["A"], "rewire preds = [A]");
eq(r.succs, ["C"], "rewire succs = [C]");
eq(r.news, [{ from: "A", to: "C", kind: "direct" }], "rewire creates A->C");

// withoutNode
const wn = withoutNode(nodes, edges, "B");
eq(wn.nodes, ["A", "C"], "withoutNode removes B");
eq(wn.edges, [], "withoutNode drops incident edges");

// duplicate prevention via upsertEdge
const e1 = upsertEdge(edges, "A", "B", "direct");
eq(e1.length, edges.length, "upsertEdge duplicate not added");
const e2 = upsertEdge(edges, "A", "B", "skip"); // different kind allowed
eq(e2.length, edges.length + 1, "upsertEdge different kind added");

// --- Skip edges + transitive split
const nodes2 = ["A", "B", "C", "D"];
const edges2 = [
  { id: "e1", from: "A", to: "B", kind: "direct" },
  { id: "e2", from: "B", to: "C", kind: "direct" },
  { id: "e3", from: "C", to: "D", kind: "direct" },
  { id: "e4", from: "A", to: "D", kind: "skip" },
];
const inspA2 = nodeInspection(nodes2, edges2, "A");
eq(inspA2.directOut, ["B"], "A->B direct");
eq(inspA2.skipOut, ["D"], "A->D skip");
// transitiveDesc should exclude direct (B) and skip (D); only C remains
eq(inspA2.transitiveDesc.sort(), ["C"], "A transitiveDesc = [C] (B is direct, D is skip)");

// cycle with skip
ok(wouldCreateCycle(nodes2, edges2, "D", "A"), "D->A creates cycle via skip+direct");

// --- Rewire with multiple preds/succs
const nodes3 = ["P1", "P2", "B", "S1", "S2"];
const edges3 = [
  { id: "a", from: "P1", to: "B", kind: "direct" },
  { id: "b", from: "P2", to: "B", kind: "direct" },
  { id: "c", from: "B", to: "S1", kind: "direct" },
  { id: "d", from: "B", to: "S2", kind: "direct" },
];
const r3 = computeRewire(nodes3, edges3, "B");
eq(r3.news.length, 4, "rewire PxS = 2x2 = 4 new edges");

// --- Codec round-trip (simulate btoa/atob in Node)
globalThis.btoa = (s) => Buffer.from(s, "binary").toString("base64");
globalThis.atob = (s) => Buffer.from(s, "base64").toString("binary");
const { encodeState, decodeState } = await import("../codec.js");

const state = {
  source: { url: "u", headers: ["A", "B", "C"], rowIds: ["r1"] },
  groups: [], edges: [],
  chainNodes: ["A", "B", "C"],
  chainEdges: [
    { id: "x1", from: "A", to: "B", kind: "direct", label: "" },
    { id: "x2", from: "B", to: "C", kind: "direct", label: "" },
    { id: "x3", from: "A", to: "C", kind: "skip", label: "fast" },
  ],
};
const tok = encodeState(state);
const dec = decodeState(tok);
eq(dec.chainNodes, state.chainNodes, "round-trip chainNodes");
eq(dec.chainEdges.length, 3, "round-trip 3 chainEdges");
eq(dec.chainEdges[2].kind, "skip", "skip kind preserved");
eq(dec.chainEdges[0].kind, "direct", "direct kind preserved");
eq(dec.chainEdges[2].label, "fast", "edge label preserved");

// v1 backwards compat
const v1Payload = { v: 1, src: null, g: [], e: [] };
const v1Tok = globalThis.btoa(JSON.stringify(v1Payload)).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,"");
try {
  const dec1 = decodeState(v1Tok);
  eq(dec1.chainNodes, [], "v1 decode returns empty chainNodes");
  eq(dec1.chainEdges, [], "v1 decode returns empty chainEdges");
} catch (e) { fail++; console.log("FAIL: v1 backwards compat:", e.message); }

console.log(`\n=== ${pass} passed, ${fail} failed ===`);
process.exit(fail ? 1 : 0);
