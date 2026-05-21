import { useState } from "react";
import { toast } from "sonner";
import { api, formatErr } from "../api";
import { useStudio } from "./store";
import {
  Link2, Loader2, Plus, Search, Filter, Sparkles, Workflow,
} from "lucide-react";

const TEMPLATES = [
  { name: "Frontend → Auth API → Database",
    nodes: [
      { name: "Frontend", category: "UI" },
      { name: "Auth API", category: "API" },
      { name: "Database", category: "Database" },
    ],
    edges: [[0, 1], [1, 2]] },
  { name: "Event-driven Pipeline",
    nodes: [
      { name: "Producer", category: "Service" },
      { name: "Queue", category: "Queue" },
      { name: "Worker", category: "Worker" },
      { name: "Storage", category: "Storage" },
    ],
    edges: [[0, 1], [1, 2], [2, 3]] },
  { name: "Microservices Trio",
    nodes: [
      { name: "Gateway", category: "API" },
      { name: "Users", category: "Service" },
      { name: "Orders", category: "Service" },
      { name: "Payments", category: "Service" },
      { name: "Postgres", category: "Database" },
    ],
    edges: [[0, 1], [0, 2], [0, 3], [1, 4], [2, 4], [3, 4]] },
];

export default function LeftSidebar() {
  const {
    sourceUrl, nodes, importRecords, addNode, CATEGORIES, DEPENDENCY_TYPES,
    filterCategory, filterType, searchTerm, setFilter,
  } = useStudio();
  const [url, setUrl] = useState(sourceUrl || "");
  const [busy, setBusy] = useState(false);

  const fetchData = async () => {
    if (!url.trim()) { toast.error("Paste an Apps Script URL."); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/studio/fetch", { url: url.trim() });
      importRecords(data.rows || []);
      toast.success(`Imported ${data.rows.length} node(s)`);
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || e.message);
    } finally { setBusy(false); }
  };

  const insertTemplate = (tpl) => {
    const base = Date.now();
    const created = tpl.nodes.map((n, i) => ({
      ...n, id: `tpl-${base}-${i}`,
      position: { x: 120 + i * 220, y: 200 + (i % 2) * 80 },
    }));
    created.forEach((c) => addNode(c));
    // edges will need to be added after nodes — use timeout? We can read store but addNode is async via set.
    setTimeout(() => {
      const store = useStudio.getState();
      const lookup = {};
      created.forEach((c, i) => { lookup[i] = c.id; });
      const newEdges = tpl.edges.map(([a, b], i) => ({
        id: `tpl-e-${base}-${i}`,
        source: lookup[a], target: lookup[b],
        type: "dependency", animated: true,
        data: { type: "Required" }, label: "Required",
      }));
      useStudio.setState({ edges: [...store.edges, ...newEdges], dirty: true });
    }, 50);
    toast.success(`Inserted template: ${tpl.name}`);
  };

  return (
    <div className="db-card p-4 h-full overflow-y-auto" data-testid="studio-left-sidebar"
         style={{ width: 280 }}>
      {/* API connector */}
      <div className="mb-5">
        <div className="flex items-center gap-2 mb-2">
          <Link2 className="w-3.5 h-3.5 db-accent" />
          <div className="text-xs mono uppercase tracking-wider"
               style={{ color: "var(--db-muted)" }}>data source</div>
        </div>
        <input
          data-testid="studio-source-url-input"
          className="db-input text-xs"
          placeholder="Apps Script JSON Endpoint"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <button
          data-testid="studio-fetch-button"
          onClick={fetchData}
          disabled={busy || !url.trim()}
          className="db-btn w-full justify-center mt-2"
        >
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Workflow className="w-3.5 h-3.5" />}
          {busy ? "Fetching…" : "Fetch architecture data"}
        </button>
        <div className="text-[10px] mono mt-2" style={{ color: "var(--db-muted)" }}>
          Records become draggable graph nodes automatically.
        </div>
      </div>

      {/* Node library */}
      <div className="mb-5">
        <div className="flex items-center gap-2 mb-2">
          <Plus className="w-3.5 h-3.5 db-accent" />
          <div className="text-xs mono uppercase tracking-wider"
               style={{ color: "var(--db-muted)" }}>add manual node</div>
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          {CATEGORIES.map((c) => (
            <button
              key={c}
              data-testid={`studio-add-${c}-button`}
              onClick={() => addNode({ name: c, category: c, type: c })}
              className="db-btn db-btn-ghost text-[11px] py-1.5 px-2"
              title={`Add ${c} node`}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      {/* Templates */}
      <div className="mb-5">
        <div className="flex items-center gap-2 mb-2">
          <Sparkles className="w-3.5 h-3.5 db-accent" />
          <div className="text-xs mono uppercase tracking-wider"
               style={{ color: "var(--db-muted)" }}>templates</div>
        </div>
        <div className="space-y-1.5">
          {TEMPLATES.map((t) => (
            <button
              key={t.name}
              data-testid={`studio-template-${t.name.split(' ')[0]}`}
              onClick={() => insertTemplate(t)}
              className="db-btn db-btn-ghost w-full text-left text-[11px] py-2 px-3"
            >
              <div>{t.name}</div>
              <div className="text-[10px] mono mt-0.5"
                   style={{ color: "var(--db-muted)" }}>
                {t.nodes.length} nodes · {t.edges.length} edges
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Filters */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <Filter className="w-3.5 h-3.5 db-accent" />
          <div className="text-xs mono uppercase tracking-wider"
               style={{ color: "var(--db-muted)" }}>search & filter</div>
        </div>
        <div className="relative mb-2">
          <Search className="w-3 h-3 absolute left-3 top-3" style={{ color: "var(--db-muted)" }} />
          <input
            data-testid="studio-search-input"
            className="db-input text-xs pl-8"
            placeholder="Search nodes…"
            value={searchTerm}
            onChange={(e) => setFilter("searchTerm", e.target.value)}
          />
        </div>
        <select
          data-testid="studio-filter-category"
          className="db-input text-xs mb-2"
          value={filterCategory}
          onChange={(e) => setFilter("filterCategory", e.target.value)}
        >
          <option value="">All categories</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select
          data-testid="studio-filter-type"
          className="db-input text-xs"
          value={filterType}
          onChange={(e) => setFilter("filterType", e.target.value)}
        >
          <option value="">All dependency types</option>
          {DEPENDENCY_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <div className="text-[10px] mono mt-2"
             style={{ color: "var(--db-muted)" }}>
          {nodes.length} node{nodes.length === 1 ? "" : "s"} in graph
        </div>
      </div>
    </div>
  );
}
