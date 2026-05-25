import { useMemo, useState } from "react";
import { toast } from "sonner";
import { useStudio } from "./store";
import { encodeState } from "./codec";
import {
  Download, Copy, Check, Link2, Code2, Terminal, Sparkles, FileJson, Eye,
} from "lucide-react";

const API_BASE = process.env.REACT_APP_BACKEND_URL || "";

export default function StudioExportPanel() {
  const { source, groups, edges, chainNodes, chainEdges } = useStudio();
  const [copied, setCopied] = useState("");
  const [tab, setTab] = useState("url"); // 'url' | 'lovable' | 'js' | 'curl' | 'json'
  const [showPreview, setShowPreview] = useState(false);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  const token = useMemo(
    () => encodeState({ source, groups, edges, chainNodes, chainEdges }),
    [source, groups, edges, chainNodes, chainEdges]
  );
  const resolveUrl = `${API_BASE}/api/studio/resolve?d=${token}`;

  const copy = async (key, value) => {
    await navigator.clipboard.writeText(value);
    setCopied(key);
    setTimeout(() => setCopied(""), 1400);
    toast.success("Copied");
  };

  const downloadJson = async () => {
    setBusy(true);
    try {
      const res = await fetch(resolveUrl);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `delaybridge-chain-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
      toast.success("Downloaded resolved chain JSON");
    } catch (e) {
      toast.error(`Download failed: ${e.message}`);
    } finally { setBusy(false); }
  };

  const fetchPreview = async () => {
    setBusy(true);
    try {
      const res = await fetch(resolveUrl);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setPreview(data);
      setShowPreview(true);
    } catch (e) {
      toast.error(`Preview failed: ${e.message}`);
    } finally { setBusy(false); }
  };

  const lovableSnippet = `// DelayBridge — dependency chain resolver
// Drop this into your Lovable / React app
const RESOLVE = ${JSON.stringify(resolveUrl)};

export async function loadDependencyChain() {
  const res = await fetch(RESOLVE);
  if (!res.ok) throw new Error("Resolver " + res.status);
  return res.json();
  // returns {
  //   source: { url, headers, rowIds } | null,
  //   chain: {
  //     nodes:        [columnId, ...],
  //     directEdges:  [{ from, to, label }],
  //     skipEdges:    [{ from, to, label }],
  //     transitive:   { columnId: { ancestors:[], descendants:[] } },
  //     topoOrder:    [columnId, ...],
  //     stats: { nodeCount, directCount, skipCount, transitiveEdgeCount }
  //   }
  // }
}`;

  const jsSnippet = `fetch(${JSON.stringify(resolveUrl)})
  .then(r => r.json())
  .then(({ chain }) => {
    console.log("topo order:", chain.topoOrder);
    console.log("direct:", chain.directEdges);
    console.log("transitive:", chain.transitive);
  });`;

  const curlSnippet = `curl -s "${resolveUrl}" | jq .`;

  return (
    <div className="db-card p-4 flex flex-col gap-3 overflow-y-auto"
         data-testid="chain-export-panel"
         style={{ width: 360 }}>
      <div className="flex items-center gap-2">
        <Sparkles className="w-4 h-4 db-accent" />
        <div className="text-sm font-semibold">Export to frontend</div>
      </div>
      <div className="text-[11px] mono" style={{ color: "var(--db-muted)" }}>
        Hand the resolved chain (with transitive closure) to any external frontend —
        Lovable, Bubble, plain React — via one stateless GET. No auth, no server-side state,
        no DB. The token IS the logic.
      </div>

      {chainNodes.length === 0 && (
        <div className="text-[11px] mono p-3 db-card"
             style={{ color: "var(--db-muted)", background: "rgba(255,255,255,0.02)" }}>
          Add at least one chain node to enable the export.
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-3 gap-1.5 text-[10px] mono">
        <SmallStat label="nodes" value={chainNodes.length} />
        <SmallStat label="direct" value={chainEdges.filter((e) => e.kind === "direct").length} />
        <SmallStat label="skip" value={chainEdges.filter((e) => e.kind === "skip").length} />
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        <button
          data-testid="chain-export-download"
          onClick={downloadJson}
          disabled={busy || !chainNodes.length}
          className="db-btn justify-center text-[11px]">
          <Download className="w-3 h-3" /> Download JSON
        </button>
        <button
          data-testid="chain-export-preview"
          onClick={fetchPreview}
          disabled={busy || !chainNodes.length}
          className="db-btn db-btn-ghost justify-center text-[11px]">
          <Eye className="w-3 h-3" /> Preview resolved
        </button>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1" data-testid="chain-export-tabs">
        <TabBtn id="url"     icon={Link2}     label="URL"     active={tab === "url"}     onClick={() => setTab("url")} />
        <TabBtn id="lovable" icon={Sparkles}  label="Lovable" active={tab === "lovable"} onClick={() => setTab("lovable")} />
        <TabBtn id="js"      icon={Code2}     label="JS"      active={tab === "js"}      onClick={() => setTab("js")} />
        <TabBtn id="curl"    icon={Terminal}  label="cURL"    active={tab === "curl"}    onClick={() => setTab("curl")} />
        <TabBtn id="json"    icon={FileJson}  label="Schema"  active={tab === "json"}    onClick={() => setTab("json")} />
      </div>

      {tab === "url" && (
        <SnippetBlock testid="export-snippet-url" copied={copied === "url"}
                      onCopy={() => copy("url", resolveUrl)} content={resolveUrl}
                      hint="GET this URL from any frontend — returns the resolved chain JSON." />
      )}
      {tab === "lovable" && (
        <SnippetBlock testid="export-snippet-lovable" copied={copied === "lovable"}
                      onCopy={() => copy("lovable", lovableSnippet)} content={lovableSnippet}
                      hint="Paste into Lovable as a utility module — call loadDependencyChain() from any component." />
      )}
      {tab === "js" && (
        <SnippetBlock testid="export-snippet-js" copied={copied === "js"}
                      onCopy={() => copy("js", jsSnippet)} content={jsSnippet}
                      hint="Vanilla fetch — drop into the browser console." />
      )}
      {tab === "curl" && (
        <SnippetBlock testid="export-snippet-curl" copied={copied === "curl"}
                      onCopy={() => copy("curl", curlSnippet)} content={curlSnippet}
                      hint="Pipe through `jq` for pretty-printed JSON." />
      )}
      {tab === "json" && (
        <SnippetBlock testid="export-snippet-schema" copied={copied === "schema"}
                      onCopy={() => copy("schema", SCHEMA_DOC)} content={SCHEMA_DOC}
                      hint="The response schema returned by GET /api/studio/resolve." />
      )}

      {/* Preview modal */}
      {showPreview && preview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4"
             style={{ background: "rgba(7,7,14,0.7)", backdropFilter: "blur(6px)" }}
             onClick={() => setShowPreview(false)}
             data-testid="chain-export-preview-modal">
          <div className="db-card p-5 w-full max-w-3xl max-h-[80vh] overflow-hidden flex flex-col"
               onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2 mb-2">
              <Eye className="w-4 h-4 db-accent" />
              <div className="text-sm font-semibold">Resolved chain — server response</div>
              <div className="flex-1"></div>
              <button onClick={() => copy("preview", JSON.stringify(preview, null, 2))}
                      className="db-btn db-btn-ghost py-1 px-2 text-xs">
                {copied === "preview" ? <Check className="w-3 h-3 db-success" /> : <Copy className="w-3 h-3" />}
                {copied === "preview" ? "Copied" : "Copy"}
              </button>
              <button onClick={() => setShowPreview(false)}
                      className="db-btn db-btn-ghost py-1 px-2 text-xs">Close</button>
            </div>
            <pre className="db-code flex-1 overflow-auto text-[11px]"
                 data-testid="chain-export-preview-body">
              {JSON.stringify(preview, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

function TabBtn({ icon: Icon, label, active, onClick, id }) {
  return (
    <button
      data-testid={`chain-export-tab-${id}`}
      onClick={onClick}
      className="db-btn db-btn-ghost py-1 px-2 text-[10px] flex-1 justify-center"
      style={active
        ? { borderColor: "rgba(0,170,255,0.5)", background: "rgba(0,170,255,0.08)", color: "#6cd0ff" }
        : {}}>
      <Icon className="w-3 h-3" /> {label}
    </button>
  );
}

function SnippetBlock({ content, hint, onCopy, copied, testid }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="text-[10px] mono" style={{ color: "var(--db-muted)" }}>{hint}</div>
      <div className="relative">
        <pre className="db-code overflow-x-auto text-[10px] max-h-[200px]"
             data-testid={testid}>
          {content}
        </pre>
        <button
          onClick={onCopy}
          className="db-btn db-btn-ghost absolute top-1.5 right-1.5 py-0.5 px-1.5 text-[10px]"
          data-testid={`${testid}-copy`}>
          {copied ? <Check className="w-3 h-3 db-success" /> : <Copy className="w-3 h-3" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}

function SmallStat({ label, value }) {
  return (
    <div className="db-card p-2">
      <div className="text-[9px] mono uppercase tracking-wider"
           style={{ color: "var(--db-muted)" }}>{label}</div>
      <div className="text-xs db-tabular-num mono mt-0.5">{value}</div>
    </div>
  );
}

const SCHEMA_DOC = `GET /api/studio/resolve?d=<base64url-token>
→ 200 OK
{
  "version": 2,
  "source": {
    "url":     "https://script.google.com/.../exec",
    "headers": ["Col A", "Col B", ...],
    "rowIds":  ["r0", "r1", ...]
  } | null,
  "edges": [   // row/col/group edges (cardinality variant)
    { "id", "from": [...refs], "to": [...refs],
      "cardinality": "1:1" | "1:N" | "N:1" | "N:N",
      "label": "", "fanIn": false }
  ],
  "chain": {
    "nodes":       ["Col A", "Col B", ...],
    "directEdges": [{ "from", "to", "label" }],
    "skipEdges":   [{ "from", "to", "label" }],
    "transitive":  {
      "Col A": { "ancestors": [...], "descendants": [...] }
    },
    "topoOrder":   ["Col A", "Col B", ...],
    "isDAG":       true,
    "stats": {
      "nodeCount", "directCount", "skipCount", "transitiveEdgeCount"
    }
  }
}`;
