import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { PUBLIC_BASE } from "../api";
import { safeCopy } from "../lib/clipboard";
import {
  Copy, ChevronLeft, ExternalLink, Code2, Link as LinkIcon, RefreshCw,
  Check, Globe, FileJson, LayoutDashboard,
} from "lucide-react";

const SLICE_ENDPOINTS = [
  { key: "full", label: "Full analysis JSON", path: "" },
  { key: "dashboard", label: "Data dashboard", path: "/dashboard" },
  { key: "flags", label: "Flags only", path: "/flags" },
  { key: "variances", label: "Variances only", path: "/variances" },
  { key: "correlations", label: "Correlations", path: "/correlations" },
  { key: "dependencies", label: "Dependency chains", path: "/dependencies" },
  { key: "status", label: "Sheet status", path: "/status" },
  { key: "alerts", label: "Alerts log", path: "/alerts" },
  { key: "chat-suggestions", label: "Chat suggestions", path: "/chat/suggestions" },
];

const CHART_COLORS = ["#00aaff", "#7c5cff", "#ff8a3d", "#23c48e", "#ff5d5d", "#f7c948", "#36c5f0", "#a78bfa"];

function tabs() {
  return ["link", "dashboard", "preview", "snippets"];
}

export default function ExportPanel({ sessionMeta, exportFields, onBack }) {
  const token = sessionMeta.public_token;
  const baseUrl = `${PUBLIC_BASE}/${token}`;
  const fieldsQuery = exportFields.length ? `?fields=${exportFields.join(",")}` : "";
  const composedUrl = `${baseUrl}/export${fieldsQuery}`;

  const [preview, setPreview] = useState(null);
  const [previewErr, setPreviewErr] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [copiedKey, setCopiedKey] = useState(null);
  const [tab, setTab] = useState("link");
  const [dash, setDash] = useState(null);
  const [dashErr, setDashErr] = useState(null);
  const [dashLoading, setDashLoading] = useState(false);

  const fetchDashboard = async () => {
    setDashLoading(true);
    setDashErr(null);
    try {
      const r = await fetch(`${baseUrl}/dashboard`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setDash(j);
    } catch (e) {
      setDashErr(e.message);
    } finally { setDashLoading(false); }
  };

  useEffect(() => { if (tab === "dashboard" && !dash && !dashLoading) fetchDashboard(); /* eslint-disable-next-line */ }, [tab]);

  const fetchPreview = async () => {
    setPreviewLoading(true);
    setPreviewErr(null);
    try {
      const r = await fetch(composedUrl);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setPreview(j);
    } catch (e) {
      setPreviewErr(e.message);
    } finally { setPreviewLoading(false); }
  };

  useEffect(() => { fetchPreview(); /* eslint-disable-next-line */ }, [composedUrl]);

  const copy = async (url, key) => {
    const r = await safeCopy(url);
    if (!r.ok) {
      toast.error("Clipboard blocked — long-press the field to copy manually");
      return;
    }
    setCopiedKey(key);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopiedKey(null), 1500);
  };

  const lovableSnippet = useMemo(() => `// Lovable / any React app
const r = await fetch("${composedUrl}");
const data = await r.json();
console.log(data);`, [composedUrl]);

  const appsScriptSnippet = useMemo(() => `// Google Apps Script
function getDelayBridgeData() {
  const r = UrlFetchApp.fetch("${composedUrl}");
  const d = JSON.parse(r.getContentText());
  Logger.log(d.summary);
  return d;
}`, [composedUrl]);

  const curlSnippet = useMemo(() => `curl -sS "${composedUrl}" | jq`, [composedUrl]);

  const previewJson = useMemo(() => {
    if (!preview) return "";
    return JSON.stringify(preview, null, 2);
  }, [preview]);

  return (
    <div className="space-y-6" data-testid="export-panel">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Globe className="w-5 h-5 db-accent" /> Your public export link
          </h2>
          <p className="text-sm mt-1" style={{ color: "var(--db-muted)" }}>
            Anyone with this URL can read the analysis JSON. Use it in Lovable, Apps Script,
            or any HTTP client. Token can be rotated by deleting + recreating the project.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button data-testid="refresh-preview-button" onClick={fetchPreview}
                  className="db-btn db-btn-ghost">
            <RefreshCw className="w-4 h-4" /> Re-test
          </button>
        </div>
      </div>

      {/* Main composed link */}
      <div className="db-card p-6" data-testid="primary-link-card">
        <div className="text-[11px] mono uppercase tracking-wider mb-2"
             style={{ color: "var(--db-muted)" }}>
          composed export URL · {exportFields.length} fields
        </div>
        <div className="db-link-row" data-testid="primary-link-row">
          <LinkIcon className="w-4 h-4 db-accent flex-shrink-0" />
          <input data-testid="primary-link-input" readOnly value={composedUrl} />
          <button data-testid="copy-primary-link-button" onClick={() => copy(composedUrl, "primary")}
                  className="db-btn db-btn-ghost">
            {copiedKey === "primary" ? <Check className="w-3.5 h-3.5 db-success" /> : <Copy className="w-3.5 h-3.5" />}
            {copiedKey === "primary" ? "Copied" : "Copy"}
          </button>
          <a data-testid="open-primary-link" href={composedUrl} target="_blank" rel="noreferrer"
             className="db-btn db-btn-ghost">
            <ExternalLink className="w-3.5 h-3.5" /> Open
          </a>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-2 mt-5 mb-3">
          {tabs().map((t) => (
            <button key={t} onClick={() => setTab(t)}
                    data-testid={`export-tab-${t}`}
                    className={`db-step ${tab === t ? "active" : ""}`}>
              {t === "link" ? "Slice URLs" : t === "dashboard" ? "Dashboard" : t === "preview" ? "Live preview" : "Code snippets"}
            </button>
          ))}
        </div>

        {tab === "link" && (
          <div className="space-y-2" data-testid="slice-urls-list">
            {SLICE_ENDPOINTS.map((s) => {
              const url = `${baseUrl}${s.path}`;
              return (
                <div key={s.key} className="db-link-row" data-testid={`slice-row-${s.key}`}>
                  <span className="db-chip db-chip-grey min-w-[100px] justify-center">{s.key}</span>
                  <input readOnly value={url} />
                  <button data-testid={`copy-slice-${s.key}`} onClick={() => copy(url, s.key)}
                          className="db-btn db-btn-ghost">
                    {copiedKey === s.key ? <Check className="w-3.5 h-3.5 db-success" /> : <Copy className="w-3.5 h-3.5" />}
                  </button>
                  <a href={url} target="_blank" rel="noreferrer"
                     className="db-btn db-btn-ghost"><ExternalLink className="w-3.5 h-3.5" /></a>
                </div>
              );
            })}
          </div>
        )}

        {tab === "dashboard" && (
          <DashboardView data={dash} loading={dashLoading} err={dashErr} onRefresh={fetchDashboard} />
        )}

        {tab === "preview" && (
          <div data-testid="preview-tab">
            {previewLoading && <div className="text-sm mono" style={{ color: "var(--db-muted)" }}>Loading…</div>}
            {previewErr && <div className="db-danger text-sm mono">Error: {previewErr}</div>}
            {!previewLoading && !previewErr && preview && (
              <>
                <div className="text-[11px] mono uppercase tracking-wider mb-2"
                     style={{ color: "var(--db-muted)" }}>
                  response · {Object.keys(preview).length} top-level keys · {Math.round(previewJson.length / 1024)}KB
                </div>
                <pre className="db-code max-h-[480px] overflow-auto"
                     data-testid="preview-json">{previewJson.slice(0, 50000)}{previewJson.length > 50000 ? "\n... [truncated]" : ""}</pre>
              </>
            )}
          </div>
        )}

        {tab === "snippets" && (
          <div className="space-y-4" data-testid="snippets-tab">
            <Snippet label="Lovable / fetch" icon={Code2} code={lovableSnippet}
                     onCopy={() => copy(lovableSnippet, "snip-lovable")}
                     copied={copiedKey === "snip-lovable"} />
            <Snippet label="Google Apps Script" icon={FileJson} code={appsScriptSnippet}
                     onCopy={() => copy(appsScriptSnippet, "snip-apps")}
                     copied={copiedKey === "snip-apps"} />
            <Snippet label="cURL" icon={Code2} code={curlSnippet}
                     onCopy={() => copy(curlSnippet, "snip-curl")}
                     copied={copiedKey === "snip-curl"} />
          </div>
        )}
      </div>

      {/* Token info */}
      <div className="db-card p-5 grid md:grid-cols-3 gap-4">
        <div>
          <div className="text-[10px] mono uppercase tracking-wider"
               style={{ color: "var(--db-muted)" }}>Project name</div>
          <div className="text-sm font-medium mt-1">{sessionMeta.name}</div>
        </div>
        <div>
          <div className="text-[10px] mono uppercase tracking-wider"
               style={{ color: "var(--db-muted)" }}>Public token</div>
          <div className="text-sm mono mt-1 break-all">{token}</div>
        </div>
        <div>
          <div className="text-[10px] mono uppercase tracking-wider"
               style={{ color: "var(--db-muted)" }}>Connected sheets</div>
          <div className="text-sm mt-1 flex flex-wrap gap-2">
            {sessionMeta.sheets.map((s) => (
              <span key={s.label} className={`db-chip db-chip-${s.color}`}>
                {s.label} · {s.rows} rows
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between gap-4 pt-2">
        <button data-testid="back-to-configure-button" onClick={onBack} className="db-btn db-btn-ghost">
          <ChevronLeft className="w-4 h-4" /> Configure
        </button>
        <div className="text-xs mono" style={{ color: "var(--db-muted)" }}>
          Paste this URL into Lovable → fetch() and you’re done.
        </div>
      </div>
    </div>
  );
}

function DashboardView({ data, loading, err, onRefresh }) {
  if (loading) return <div className="text-sm mono" style={{ color: "var(--db-muted)" }}>Loading dashboard…</div>;
  if (err) return <div className="db-danger text-sm mono">Error: {err}</div>;
  if (!data) return null;
  if (data.enabled === false) {
    return (
      <div className="db-card p-5 text-sm" style={{ color: "var(--db-muted)" }}>
        The data dashboard isn’t enabled for this export. Go back to Configure and turn on
        <span className="db-accent"> Sheet data dashboard</span>.
      </div>
    );
  }
  const sheets = data.sheets || [];
  if (!sheets.length) {
    return <div className="db-card p-5 text-sm" style={{ color: "var(--db-muted)" }}>No connected sheets to visualize yet.</div>;
  }
  return (
    <div className="space-y-8" data-testid="dashboard-tab">
      <div className="flex items-center justify-between">
        <div className="text-[11px] mono uppercase tracking-wider flex items-center gap-2"
             style={{ color: "var(--db-muted)" }}>
          <LayoutDashboard className="w-3.5 h-3.5 db-accent" /> {data.project || "Dashboard"} · {sheets.length} sheet(s)
        </div>
        <button onClick={onRefresh} className="db-btn db-btn-ghost"><RefreshCw className="w-3.5 h-3.5" /> Refresh</button>
      </div>

      {sheets.map((s) => (
        <div key={s.label} className="space-y-4">
          <div className="flex items-center gap-2">
            <span className={`db-chip db-chip-${s.color || "blue"}`}>{s.label}</span>
            <span className="text-sm font-medium">{s.name}</span>
            <span className="text-[11px] mono" style={{ color: "var(--db-muted)" }}>{s.row_count} rows</span>
          </div>

          {/* KPI cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {(s.kpis || []).map((k, i) => (
              <div key={i} className="db-card p-4">
                <div className="text-[10px] mono uppercase tracking-wider" style={{ color: "var(--db-muted)" }}>{k.label}</div>
                <div className="db-tabular-num mono text-2xl mt-1">{typeof k.value === "number" ? k.value.toLocaleString() : k.value}</div>
              </div>
            ))}
          </div>

          {/* Charts */}
          {(s.charts || []).length > 0 && (
            <div className="grid md:grid-cols-2 gap-4">
              {s.charts.map((c, i) => (
                <div key={i} className="db-card p-4">
                  <div className="text-sm font-medium mb-3">{c.title}</div>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={c.data} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                      <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={50} />
                      <YAxis tick={{ fontSize: 11 }} width={40} />
                      <Tooltip />
                      <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                        {c.data.map((_, idx) => <Cell key={idx} fill={CHART_COLORS[idx % CHART_COLORS.length]} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ))}
            </div>
          )}

          {/* Data table */}
          <div className="db-card p-0 overflow-auto max-h-[420px]">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  {(s.columns || []).map((col) => (
                    <th key={col.name} className="text-left px-3 py-2 sticky top-0"
                        style={{ background: "var(--db-bg, #0d1117)", color: "var(--db-muted)", fontWeight: 600 }}>
                      {col.name}
                      <span className="ml-1 text-[9px] mono opacity-60">{col.type}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(s.rows || []).slice(0, 100).map((row, ri) => (
                  <tr key={ri} className="border-t" style={{ borderColor: "var(--db-border, #222)" }}>
                    {(s.columns || []).map((col) => (
                      <td key={col.name} className="px-3 py-1.5 whitespace-nowrap">{String(row[col.name] ?? "")}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {s.truncated && (
            <div className="text-[11px] mono" style={{ color: "var(--db-muted)" }}>
              Showing first rows · full data available via the /dashboard endpoint.
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function Snippet({ label, icon: Icon, code, onCopy, copied }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-3.5 h-3.5 db-accent" />
        <div className="text-xs mono uppercase tracking-wider"
             style={{ color: "var(--db-muted)" }}>{label}</div>
        <div className="flex-1"></div>
        <button data-testid={`copy-${label.toLowerCase().replace(/\s+/g,'-')}`}
                onClick={onCopy} className="db-btn db-btn-ghost">
          {copied ? <Check className="w-3.5 h-3.5 db-success" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="db-code">{code}</pre>
    </div>
  );
}
