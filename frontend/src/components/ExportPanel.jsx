import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  ComposedChart, Area, Line, Legend,
} from "recharts";
import { PUBLIC_BASE } from "../api";
import { safeCopy } from "../lib/clipboard";
import {
  Copy, ChevronLeft, ExternalLink, Code2, Link as LinkIcon, RefreshCw,
  Check, Globe, FileJson, LayoutDashboard, Sparkles, Send, ShieldCheck, Table2, TrendingUp, AlertTriangle,
  FileText, Lightbulb, Activity, Bell, Plus, Trash2, SlidersHorizontal,
} from "lucide-react";

const SLICE_ENDPOINTS = [
  { key: "full", label: "Full analysis JSON", path: "" },
  { key: "dashboard", label: "Data dashboard", path: "/dashboard" },
  { key: "pivot", label: "Pivot / segmentation", path: "/pivot" },
  { key: "whatif", label: "What-if simulation", path: "/whatif" },
  { key: "forecast", label: "Forecast", path: "/forecast" },
  { key: "trends", label: "Trends", path: "/trends" },
  { key: "anomalies", label: "Anomaly detection", path: "/anomalies" },
  { key: "digest", label: "Auto-digest", path: "/digest" },
  { key: "recommendations", label: "Recommendations", path: "/recommendations" },
  { key: "quality", label: "Data-quality audit", path: "/quality" },
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
  return ["link", "dashboard", "digest", "pivot", "whatif", "forecast", "trends", "anomalies", "recommendations", "quality", "alerts", "copilot", "preview", "snippets"];
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
              {t === "link" ? "Slice URLs" : t === "dashboard" ? "Dashboard" : t === "digest" ? "Digest" : t === "pivot" ? "Pivot" : t === "whatif" ? "What-if" : t === "forecast" ? "Forecast" : t === "trends" ? "Trends" : t === "anomalies" ? "Anomalies" : t === "recommendations" ? "Recommendations" : t === "quality" ? "Data quality" : t === "alerts" ? "Alerts" : t === "copilot" ? "Copilot" : t === "preview" ? "Live preview" : "Code snippets"}
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

        {tab === "copilot" && (
          <CopilotView baseUrl={baseUrl} />
        )}

        {tab === "digest" && (
          <DigestView baseUrl={baseUrl} />
        )}

        {tab === "alerts" && (
          <AlertsView baseUrl={baseUrl} />
        )}

        {tab === "trends" && (
          <TrendsView baseUrl={baseUrl} />
        )}

        {tab === "recommendations" && (
          <RecommendationsView baseUrl={baseUrl} />
        )}

        {tab === "anomalies" && (
          <AnomaliesView baseUrl={baseUrl} />
        )}

        {tab === "forecast" && (
          <ForecastView baseUrl={baseUrl} />
        )}

        {tab === "whatif" && (
          <WhatIfView baseUrl={baseUrl} />
        )}

        {tab === "pivot" && (
          <PivotView baseUrl={baseUrl} />
        )}

        {tab === "quality" && (
          <QualityView baseUrl={baseUrl} />
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

function CopilotView({ baseUrl }) {
  const [q, setQ] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [msgs, setMsgs] = useState([]); // {role, text}
  const [loading, setLoading] = useState(false);

  const SUGGESTIONS = [
    "Summarize this dataset in 3 bullet points",
    "Which category has the highest total?",
    "What columns are numeric and what are their totals?",
    "Are there any data-quality issues I should know about?",
  ];

  const ask = async (text) => {
    const question = (text ?? q).trim();
    if (!question || loading) return;
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setQ("");
    setLoading(true);
    try {
      const r = await fetch(`${baseUrl}/copilot`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question, session_id: sessionId }),
      });
      const j = await r.json();
      if (j.session_id) setSessionId(j.session_id);
      setMsgs((m) => [...m, { role: "assistant", text: j.answer || j.message || "(no answer)" }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", text: `Error: ${e.message}` }]);
    } finally { setLoading(false); }
  };

  return (
    <div className="space-y-4" data-testid="copilot-tab">
      <div className="text-[11px] mono uppercase tracking-wider flex items-center gap-2"
           style={{ color: "var(--db-muted)" }}>
        <Sparkles className="w-3.5 h-3.5 db-accent" /> Ask anything about this sheet — answers are computed from exact aggregates.
      </div>

      {msgs.length === 0 && (
        <div className="flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => ask(s)} className="db-chip db-chip-blue" style={{ cursor: "pointer" }}>
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="db-card p-4 space-y-3 max-h-[420px] overflow-auto">
        {msgs.length === 0 && (
          <div className="text-sm" style={{ color: "var(--db-muted)" }}>
            Tip: the copilot uses server-computed sums/counts, so totals are exact — not guessed from a sample.
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <div className={`inline-block px-3 py-2 rounded-lg text-sm whitespace-pre-wrap ${m.role === "user" ? "db-chip-blue" : ""}`}
                 style={m.role === "assistant" ? { background: "var(--db-card-2, rgba(255,255,255,0.04))" } : {}}>
              {m.text}
            </div>
          </div>
        ))}
        {loading && <div className="text-sm mono" style={{ color: "var(--db-muted)" }}>Thinking…</div>}
      </div>

      <div className="db-link-row">
        <input
          data-testid="copilot-input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") ask(); }}
          placeholder="Ask about totals, breakdowns, outliers, trends…"
        />
        <button onClick={() => ask()} disabled={loading} className="db-btn">
          <Send className="w-3.5 h-3.5" /> Ask
        </button>
      </div>
      <div className="text-[11px] mono" style={{ color: "var(--db-muted)" }}>
        Needs an ANTHROPIC_API_KEY set on the server. POST to <span className="db-accent">{baseUrl}/copilot</span> with {"{ message }"}.
      </div>
    </div>
  );
}

function AlertsView({ baseUrl }) {
  const [rules, setRules] = useState([]);
  const [log, setLog] = useState([]);
  const [tested, setTested] = useState(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);

  const refresh = async () => {
    try {
      const [rr, lr] = await Promise.all([
        fetch(`${baseUrl}/alerts/rules`).then((r) => r.json()),
        fetch(`${baseUrl}/alerts`).then((r) => r.json()),
      ]);
      setRules(rr.rules || []);
      setLog(lr.alerts || lr.history || lr || []);
    } catch (e) { /* ignore */ }
  };
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [baseUrl]);

  const update = (i, k, v) => setRules((rs) => rs.map((r, idx) => idx === i ? { ...r, [k]: v } : r));
  const add = () => setRules((rs) => [...rs, { label: "", metric: "total_rows", op: "lt", threshold: 0, webhook_url: "" }]);
  const remove = (i) => setRules((rs) => rs.filter((_, idx) => idx !== i));

  const save = async () => {
    setSaving(true); setMsg(null);
    try {
      await fetch(`${baseUrl}/alerts/rules`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rules }),
      });
      setMsg("Saved.");
    } catch (e) { setMsg("Save failed: " + e.message); } finally { setSaving(false); }
  };
  const test = async () => {
    setMsg(null);
    try {
      const r = await fetch(`${baseUrl}/alerts/test`, { method: "POST" });
      setTested(await r.json());
      refresh();
    } catch (e) { setMsg("Test failed: " + e.message); }
  };

  return (
    <div className="space-y-4" data-testid="alerts-tab">
      <div className="text-[11px] mono uppercase tracking-wider flex items-center gap-2" style={{ color: "var(--db-muted)" }}>
        <Bell className="w-3.5 h-3.5 db-accent" /> Rules run on the daily snapshot and fire webhooks when triggered.
      </div>

      <div className="space-y-2">
        {rules.map((r, i) => (
          <div key={i} className="db-card p-3 flex flex-wrap items-end gap-2">
            <Field label="Label"><input className="db-select" style={{ width: 120 }} value={r.label || ""} onChange={(e) => update(i, "label", e.target.value)} placeholder="optional" /></Field>
            <Field label="Metric">
              <input className="db-select" style={{ width: 130 }} list="metric-opts" value={r.metric} onChange={(e) => update(i, "metric", e.target.value)} />
              <datalist id="metric-opts"><option value="total_rows" /><option value="quality" /><option value="anomalies" /></datalist>
            </Field>
            <Field label="Condition">
              <select className="db-select" value={r.op} onChange={(e) => update(i, "op", e.target.value)}>
                <option value="lt">drops below</option><option value="gt">rises above</option><option value="change_pct">changes ≥ % </option>
              </select>
            </Field>
            <Field label="Value"><input type="number" className="db-select" style={{ width: 90 }} value={r.threshold} onChange={(e) => update(i, "threshold", e.target.value)} /></Field>
            <Field label="Webhook URL (optional)"><input className="db-select" style={{ width: 220 }} value={r.webhook_url || ""} onChange={(e) => update(i, "webhook_url", e.target.value)} placeholder="https://…" /></Field>
            <button onClick={() => remove(i)} className="db-btn db-btn-ghost"><Trash2 className="w-3.5 h-3.5" /></button>
          </div>
        ))}
        {rules.length === 0 && <div className="text-sm" style={{ color: "var(--db-muted)" }}>No rules yet. Add one below.</div>}
      </div>

      <div className="flex items-center gap-2">
        <button onClick={add} className="db-btn db-btn-ghost"><Plus className="w-3.5 h-3.5" /> Add rule</button>
        <button onClick={save} disabled={saving} className="db-btn"><Check className="w-3.5 h-3.5" /> {saving ? "Saving…" : "Save rules"}</button>
        <button onClick={test} className="db-btn db-btn-ghost"><Bell className="w-3.5 h-3.5" /> Test now</button>
        {msg && <span className="text-xs mono" style={{ color: "var(--db-muted)" }}>{msg}</span>}
      </div>

      {tested && (
        <div className="db-card p-4">
          <div className="text-sm font-medium mb-2">Test result · {tested.count} triggered</div>
          <div className="text-[12px] mono mb-2" style={{ color: "var(--db-muted)" }}>
            current: rows {tested.current?.total_rows}, quality {tested.current?.quality ?? "—"}, anomalies {tested.current?.anomalies}
          </div>
          {(tested.triggered || []).map((t, i) => (
            <div key={i} className="db-chip db-chip-grey mr-2 mb-1">{t.message}</div>
          ))}
          {(tested.triggered || []).length === 0 && <div className="text-sm db-success">No rules triggered.</div>}
        </div>
      )}

      {log.length > 0 && (
        <div className="db-card p-4">
          <div className="text-sm font-medium mb-2">Recent alerts</div>
          <div className="space-y-1 max-h-[200px] overflow-auto">
            {log.slice(0, 30).map((a, i) => (
              <div key={i} className="text-[12px] mono flex gap-2">
                <span style={{ color: "var(--db-muted)" }}>{(a.created_at || "").slice(0, 16).replace("T", " ")}</span>
                <span>{a.message || a.metric}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TrendsView({ baseUrl }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    (async () => {
      setLoading(true); setErr(null);
      try { const r = await fetch(`${baseUrl}/trends`); setData(await r.json()); }
      catch (e) { setErr(e.message); } finally { setLoading(false); }
    })();
  }, [baseUrl]);
  if (loading) return <div className="text-sm mono" style={{ color: "var(--db-muted)" }}>Loading trends…</div>;
  if (err) return <div className="db-danger text-sm mono">Error: {err}</div>;
  if (!data) return null;
  if (data.enabled === false) return <div className="db-card p-5 text-sm" style={{ color: "var(--db-muted)" }}>
    Trends isn’t enabled. Enable <span className="db-accent">Trends</span> in Configure.
  </div>;

  const series = data.series || [];
  return (
    <div className="space-y-4" data-testid="trends-tab">
      <div className="text-[11px] mono uppercase tracking-wider flex items-center gap-2" style={{ color: "var(--db-muted)" }}>
        <Activity className="w-3.5 h-3.5 db-accent" /> {data.snapshot_count} snapshot(s) captured
      </div>

      {!data.ready && (
        <div className="db-card p-5 text-sm" style={{ color: "var(--db-muted)" }}>{data.message}</div>
      )}

      {data.changes && data.changes.length > 0 && (
        <div className="db-card p-4">
          <div className="text-sm font-medium mb-2">What changed since the last snapshot</div>
          <div className="flex flex-wrap gap-2">
            {data.changes.map((c, i) => (
              <span key={i} className={`db-chip ${c.delta > 0 ? "db-chip-green" : "db-chip-grey"}`}>{c.text}</span>
            ))}
          </div>
        </div>
      )}

      {series.length >= 2 && (
        <div className="db-card p-4">
          <div className="text-sm font-medium mb-3">Rows & quality over time</div>
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={series} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} />
              <YAxis yAxisId="l" tick={{ fontSize: 11 }} width={48} />
              <YAxis yAxisId="r" orientation="right" domain={[0, 100]} tick={{ fontSize: 11 }} width={36} />
              <Tooltip />
              <Legend />
              <Line yAxisId="l" dataKey="total_rows" stroke="#00aaff" strokeWidth={2} dot name="Rows" />
              <Line yAxisId="r" dataKey="quality" stroke="#23c48e" strokeWidth={2} strokeDasharray="5 4" dot name="Quality" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="db-card p-0 overflow-auto max-h-[260px]">
        <table className="w-full text-sm">
          <thead><tr>
            {["Date", "Rows", "Quality", "Anomalies"].map((h) => (
              <th key={h} className="text-left px-3 py-2" style={{ color: "var(--db-muted)" }}>{h}</th>
            ))}
          </tr></thead>
          <tbody>
            {series.map((s, i) => (
              <tr key={i} className="border-t" style={{ borderColor: "var(--db-border, #222)" }}>
                <td className="px-3 py-1.5">{s.date}</td>
                <td className="px-3 py-1.5 db-tabular-num mono">{s.total_rows.toLocaleString()}</td>
                <td className="px-3 py-1.5 db-tabular-num mono">{s.quality ?? "—"}</td>
                <td className="px-3 py-1.5 db-tabular-num mono">{s.anomalies}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DigestView({ baseUrl }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    (async () => {
      setLoading(true); setErr(null);
      try { const r = await fetch(`${baseUrl}/digest`); setData(await r.json()); }
      catch (e) { setErr(e.message); } finally { setLoading(false); }
    })();
  }, [baseUrl]);
  if (loading) return <div className="text-sm mono" style={{ color: "var(--db-muted)" }}>Summarizing…</div>;
  if (err) return <div className="db-danger text-sm mono">Error: {err}</div>;
  if (!data) return null;
  if (data.enabled === false) return <div className="db-card p-5 text-sm" style={{ color: "var(--db-muted)" }}>
    Digest isn’t enabled. Enable <span className="db-accent">Auto-digest</span> in Configure.
  </div>;
  return (
    <div className="space-y-4" data-testid="digest-tab">
      <div className="db-card p-5">
        <div className="flex items-center gap-2 mb-2">
          <FileText className="w-4 h-4 db-accent" />
          <div className="text-sm font-semibold">Executive summary</div>
          <span className="db-chip db-chip-grey ml-auto">{data.generated_by === "ai" ? "AI-written" : "computed"}</span>
        </div>
        <p className="text-sm leading-relaxed">{data.summary}</p>
      </div>
      {(data.sheets || []).map((s) => (
        <div key={s.label} className="db-card p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="db-chip db-chip-blue">{s.label}</span>
            <span className="text-sm font-medium">{s.name}</span>
          </div>
          <ul className="text-sm space-y-1" style={{ listStyle: "disc", paddingLeft: 18 }}>
            {(s.highlights || []).map((h, i) => <li key={i}>{h}</li>)}
          </ul>
        </div>
      ))}
    </div>
  );
}

function RecommendationsView({ baseUrl }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    (async () => {
      setLoading(true); setErr(null);
      try { const r = await fetch(`${baseUrl}/recommendations`); setData(await r.json()); }
      catch (e) { setErr(e.message); } finally { setLoading(false); }
    })();
  }, [baseUrl]);
  if (loading) return <div className="text-sm mono" style={{ color: "var(--db-muted)" }}>Analyzing…</div>;
  if (err) return <div className="db-danger text-sm mono">Error: {err}</div>;
  if (!data) return null;
  if (data.enabled === false) return <div className="db-card p-5 text-sm" style={{ color: "var(--db-muted)" }}>
    Recommendations isn’t enabled. Enable <span className="db-accent">Recommendations</span> in Configure.
  </div>;
  const recs = data.recommendations || [];
  const sevColor = (s) => s === "high" ? "db-danger" : s === "medium" ? "db-warning" : "db-success";
  return (
    <div className="space-y-3" data-testid="recommendations-tab">
      {recs.length === 0 && <div className="db-card p-5 text-sm" style={{ color: "var(--db-muted)" }}>No recommendations — data looks clean.</div>}
      {recs.map((r, i) => (
        <div key={i} className="db-card p-4 flex items-start gap-3">
          <Lightbulb className={`w-4 h-4 mt-0.5 ${sevColor(r.severity)}`} />
          <div>
            <div className="text-sm font-medium">{r.title} <span className={`db-chip db-chip-grey ml-1`} style={{ fontSize: 10 }}>{r.severity}</span></div>
            <div className="text-[13px]" style={{ color: "var(--db-muted)" }}>{r.detail}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function AnomaliesView({ baseUrl }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sensitivity, setSensitivity] = useState("medium");
  const [column, setColumn] = useState("");

  const load = async (params = {}) => {
    setLoading(true); setErr(null);
    const qs = new URLSearchParams();
    qs.set("sensitivity", params.sensitivity ?? sensitivity);
    const c = params.column ?? column;
    if (c) qs.set("column", c);
    try {
      const r = await fetch(`${baseUrl}/anomalies?${qs.toString()}`);
      setData(await r.json());
    } catch (e) { setErr(e.message); } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  if (data && data.enabled === false) {
    return <div className="db-card p-5 text-sm" style={{ color: "var(--db-muted)" }}>
      Anomaly module isn’t enabled. Enable <span className="db-accent">Anomaly detection</span> in Configure.
    </div>;
  }
  const anomalies = data?.anomalies || [];
  return (
    <div className="space-y-4" data-testid="anomalies-tab">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Column">
          <select className="db-select" value={column} onChange={(e) => { setColumn(e.target.value); load({ column: e.target.value }); }}>
            <option value="">All numeric</option>
            {(data?.available_columns || []).map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </Field>
        <Field label="Sensitivity">
          <select className="db-select" value={sensitivity} onChange={(e) => { setSensitivity(e.target.value); load({ sensitivity: e.target.value }); }}>
            <option value="low">Low (only extreme)</option>
            <option value="medium">Medium</option>
            <option value="high">High (more flags)</option>
          </select>
        </Field>
        <div className="text-[11px] mono ml-auto" style={{ color: "var(--db-muted)" }}>
          <AlertTriangle className="w-3.5 h-3.5 inline db-warning" /> {data?.count ?? 0} anomalies
        </div>
      </div>

      {loading && <div className="text-sm mono" style={{ color: "var(--db-muted)" }}>Scanning…</div>}
      {err && <div className="db-danger text-sm mono">Error: {err}</div>}

      {!loading && anomalies.length === 0 && (
        <div className="db-card p-5 text-sm" style={{ color: "var(--db-muted)" }}>No anomalies at this sensitivity.</div>
      )}
      {!loading && anomalies.length > 0 && (
        <div className="db-card p-0 overflow-auto max-h-[420px]">
          <table className="w-full text-sm">
            <thead><tr>
              {["Row", "Column", "Value", "Score", ""].map((h) => (
                <th key={h} className="text-left px-3 py-2" style={{ color: "var(--db-muted)" }}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {anomalies.map((a, i) => (
                <tr key={i} className="border-t" style={{ borderColor: "var(--db-border, #222)" }}>
                  <td className="px-3 py-1.5 max-w-[280px] truncate" title={a.label}>{a.label}</td>
                  <td className="px-3 py-1.5"><span className="db-chip db-chip-grey">{a.column}</span></td>
                  <td className="px-3 py-1.5 db-tabular-num mono">{Number(a.value).toLocaleString()}</td>
                  <td className="px-3 py-1.5 db-tabular-num mono">{a.score}</td>
                  <td className="px-3 py-1.5">
                    <span className={a.direction === "high" ? "db-danger" : "db-warning"}>{a.direction === "high" ? "▲ high" : "▼ low"}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ForecastView({ baseUrl }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const [periods, setPeriods] = useState(6);
  const [measure, setMeasure] = useState("");
  const [gran, setGran] = useState("");

  const load = async (params = {}) => {
    setLoading(true); setErr(null);
    const qs = new URLSearchParams();
    qs.set("periods", params.periods ?? periods);
    const m = params.measure ?? measure;
    const g = params.gran ?? gran;
    if (m) qs.set("measure", m);
    if (g) qs.set("granularity", g);
    try {
      const r = await fetch(`${baseUrl}/forecast?${qs.toString()}`);
      const j = await r.json();
      setData(j);
      if (j.measure_col && j.measure_col !== "(row count)") setMeasure(j.measure_col);
      if (j.granularity) setGran(j.granularity);
    } catch (e) { setErr(e.message); } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  if (data && data.enabled === false) {
    return <div className="db-card p-5 text-sm" style={{ color: "var(--db-muted)" }}>
      Forecast module isn’t enabled. Enable <span className="db-accent">Forecast</span> in Configure.
    </div>;
  }
  if (data && data.ready === false) {
    return (
      <div className="db-card p-5 text-sm space-y-2" style={{ color: "var(--db-muted)" }}>
        <div className="db-warning">{data.message}</div>
        <div>Detected date columns: {(data.available_dates || []).join(", ") || "none"} · numeric measures: {(data.available_measures || []).join(", ") || "none"}.</div>
        <div>Connect a sheet that has a date/timestamp column to use forecasting.</div>
      </div>
    );
  }

  const chartData = data ? [
    ...(data.history || []).map((h) => ({ period: h.period, actual: h.value })),
    ...(data.forecast || []).map((f) => ({ period: f.period, p50: f.p50, band95: [f.p95_low, f.p95_high], band80: [f.p80_low, f.p80_high] })),
  ] : [];

  return (
    <div className="space-y-4" data-testid="forecast-tab">
      <div className="flex flex-wrap items-end gap-3">
        {data?.available_measures?.length > 0 && (
          <Field label="Measure">
            <select className="db-select" value={measure} onChange={(e) => { setMeasure(e.target.value); load({ measure: e.target.value }); }}>
              {data.available_measures.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </Field>
        )}
        <Field label="Granularity">
          <select className="db-select" value={gran} onChange={(e) => { setGran(e.target.value); load({ gran: e.target.value }); }}>
            <option value="day">Daily</option><option value="week">Weekly</option><option value="month">Monthly</option>
          </select>
        </Field>
        <Field label="Periods ahead">
          <select className="db-select" value={periods} onChange={(e) => { setPeriods(Number(e.target.value)); load({ periods: e.target.value }); }}>
            {[3, 6, 12, 18, 24].map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </Field>
      </div>

      {loading && <div className="text-sm mono" style={{ color: "var(--db-muted)" }}>Forecasting…</div>}
      {err && <div className="db-danger text-sm mono">Error: {err}</div>}

      {!loading && data?.ready && (
        <>
          <div className="db-card p-4">
            <div className="text-sm font-medium mb-1">
              {data.measure_col} over time · {data.granularity} · trend {data.trend_per_period >= 0 ? "+" : ""}{data.trend_per_period}/period
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
                <XAxis dataKey="period" tick={{ fontSize: 10 }} interval="preserveStartEnd" angle={-20} textAnchor="end" height={50} />
                <YAxis tick={{ fontSize: 11 }} width={48} />
                <Tooltip />
                <Legend />
                <Area dataKey="band95" stroke="none" fill="#7c5cff" fillOpacity={0.12} name="P95 band" />
                <Area dataKey="band80" stroke="none" fill="#00aaff" fillOpacity={0.18} name="P80 band" />
                <Line dataKey="actual" stroke="#23c48e" strokeWidth={2} dot={false} name="Actual" />
                <Line dataKey="p50" stroke="#00aaff" strokeWidth={2} strokeDasharray="5 4" dot={false} name="Forecast (P50)" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="db-card p-0 overflow-auto max-h-[280px]">
            <table className="w-full text-sm">
              <thead><tr>
                {["Period", "P50", "P80 low", "P80 high", "P95 low", "P95 high"].map((h) => (
                  <th key={h} className="text-right px-3 py-2 first:text-left" style={{ color: "var(--db-muted)" }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {(data.forecast || []).map((f, i) => (
                  <tr key={i} className="border-t" style={{ borderColor: "var(--db-border, #222)" }}>
                    <td className="px-3 py-1.5">{f.period}</td>
                    <td className="px-3 py-1.5 text-right db-tabular-num mono">{f.p50.toLocaleString()}</td>
                    <td className="px-3 py-1.5 text-right db-tabular-num mono" style={{ color: "var(--db-muted)" }}>{f.p80_low.toLocaleString()}</td>
                    <td className="px-3 py-1.5 text-right db-tabular-num mono" style={{ color: "var(--db-muted)" }}>{f.p80_high.toLocaleString()}</td>
                    <td className="px-3 py-1.5 text-right db-tabular-num mono" style={{ color: "var(--db-muted)" }}>{f.p95_low.toLocaleString()}</td>
                    <td className="px-3 py-1.5 text-right db-tabular-num mono" style={{ color: "var(--db-muted)" }}>{f.p95_high.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function WhatIfView({ baseUrl }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dimension, setDimension] = useState("");
  const [measure, setMeasure] = useState("");
  const [globalPct, setGlobalPct] = useState(0);
  const [adj, setAdj] = useState({}); // key -> pct

  const load = async (params = {}) => {
    setLoading(true); setErr(null);
    const qs = new URLSearchParams();
    const d = params.dimension ?? dimension;
    const m = params.measure ?? measure;
    if (d) qs.set("dimension", d);
    if (m) qs.set("measure", m);
    try {
      const r = await fetch(`${baseUrl}/whatif?${qs.toString()}`);
      const j = await r.json();
      setData(j);
      if (j.dimension) setDimension(j.dimension);
      if (j.measure) setMeasure(j.measure);
      setAdj({});
    } catch (e) { setErr(e.message); } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  if (data && data.enabled === false) return <div className="db-card p-5 text-sm" style={{ color: "var(--db-muted)" }}>
    What-if isn’t enabled. Enable <span className="db-accent">What-if simulation</span> in Configure.
  </div>;
  if (data && data.error) return <div className="db-card p-5 text-sm db-warning">{data.error}</div>;

  const baseline = data?.baseline || [];
  const scenario = baseline.map((b) => {
    const pct = (Number(adj[b.key]) || 0) + Number(globalPct || 0);
    return { key: b.key, base: b.value, value: Math.round(b.value * (1 + pct / 100) * 100) / 100 };
  });
  const baseTotal = baseline.reduce((a, b) => a + b.value, 0);
  const scenTotal = scenario.reduce((a, b) => a + b.value, 0);
  const delta = scenTotal - baseTotal;
  const deltaPct = baseTotal ? (delta / baseTotal) * 100 : 0;
  const chart = scenario.slice(0, 12).map((s) => ({ key: s.key, baseline: s.base, scenario: s.value }));

  return (
    <div className="space-y-4" data-testid="whatif-tab">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Group by">
          <select className="db-select" value={dimension} onChange={(e) => { setDimension(e.target.value); load({ dimension: e.target.value }); }}>
            {(data?.available_dimensions || []).map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </Field>
        <Field label="Measure">
          <select className="db-select" value={measure} onChange={(e) => { setMeasure(e.target.value); load({ measure: e.target.value }); }}>
            {(data?.available_measures || []).map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </Field>
        <Field label="Global adjust %">
          <input type="number" className="db-select" style={{ width: 100 }} value={globalPct} onChange={(e) => setGlobalPct(e.target.value)} />
        </Field>
        <button onClick={() => { setAdj({}); setGlobalPct(0); }} className="db-btn db-btn-ghost">Reset</button>
      </div>

      {loading && <div className="text-sm mono" style={{ color: "var(--db-muted)" }}>Loading…</div>}
      {err && <div className="db-danger text-sm mono">Error: {err}</div>}

      {!loading && baseline.length > 0 && (
        <>
          <div className="grid grid-cols-3 gap-3">
            <Metric label={`Baseline ${data.measure}`} value={Math.round(baseTotal)} />
            <Metric label="Scenario" value={Math.round(scenTotal)} />
            <div className="db-card p-3">
              <div className="text-[10px] mono uppercase tracking-wider" style={{ color: "var(--db-muted)" }}>Change</div>
              <div className={`db-tabular-num mono text-xl mt-1 ${delta >= 0 ? "db-success" : "db-danger"}`}>
                {delta >= 0 ? "+" : ""}{Math.round(delta).toLocaleString()} ({deltaPct >= 0 ? "+" : ""}{deltaPct.toFixed(1)}%)
              </div>
            </div>
          </div>

          <div className="db-card p-4">
            <div className="text-sm font-medium mb-3 flex items-center gap-2"><SlidersHorizontal className="w-4 h-4 db-accent" /> Baseline vs scenario</div>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={chart} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                <XAxis dataKey="key" tick={{ fontSize: 10 }} interval={0} angle={-25} textAnchor="end" height={56} />
                <YAxis tick={{ fontSize: 11 }} width={48} />
                <Tooltip /><Legend />
                <Bar dataKey="baseline" fill="#3a3f4b" radius={[3, 3, 0, 0]} />
                <Bar dataKey="scenario" fill="#00aaff" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="db-card p-0 overflow-auto max-h-[320px]">
            <table className="w-full text-sm">
              <thead><tr>
                {[data.dimension, "Baseline", "Adjust %", "Scenario"].map((h) => (
                  <th key={h} className="text-left px-3 py-2" style={{ color: "var(--db-muted)" }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {scenario.map((s, i) => (
                  <tr key={i} className="border-t" style={{ borderColor: "var(--db-border, #222)" }}>
                    <td className="px-3 py-1.5">{s.key}</td>
                    <td className="px-3 py-1.5 db-tabular-num mono">{s.base.toLocaleString()}</td>
                    <td className="px-3 py-1.5">
                      <input type="number" className="db-select" style={{ width: 80 }}
                             value={adj[s.key] ?? ""} placeholder="0"
                             onChange={(e) => setAdj((a) => ({ ...a, [s.key]: e.target.value }))} />
                    </td>
                    <td className="px-3 py-1.5 db-tabular-num mono db-accent">{s.value.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function PivotView({ baseUrl }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dimension, setDimension] = useState("");
  const [measure, setMeasure] = useState("");
  const [agg, setAgg] = useState("sum");
  const [includeTotals, setIncludeTotals] = useState(false);

  const load = async (params = {}) => {
    setLoading(true); setErr(null);
    const qs = new URLSearchParams();
    const d = params.dimension ?? dimension;
    const m = params.measure ?? measure;
    const a = params.agg ?? agg;
    const it = params.includeTotals ?? includeTotals;
    if (d) qs.set("dimension", d);
    if (m && a !== "count") qs.set("measure", m);
    qs.set("agg", a);
    qs.set("include_totals", it ? "true" : "false");
    try {
      const r = await fetch(`${baseUrl}/pivot?${qs.toString()}`);
      const j = await r.json();
      setData(j);
      if (j.dimension) setDimension(j.dimension);
      if (j.measure) setMeasure(j.measure);
    } catch (e) { setErr(e.message); } finally { setLoading(false); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
  if (data && data.enabled === false) {
    return <div className="db-card p-5 text-sm" style={{ color: "var(--db-muted)" }}>
      Pivot module isn’t enabled. Enable <span className="db-accent">Pivot & segmentation</span> in Configure.
    </div>;
  }

  const dims = data?.available_dimensions || [];
  const measures = data?.available_measures || [];
  const rows = data?.data || [];

  return (
    <div className="space-y-4" data-testid="pivot-tab">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Group by">
          <select className="db-select" value={dimension}
                  onChange={(e) => { setDimension(e.target.value); load({ dimension: e.target.value }); }}>
            {dims.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </Field>
        <Field label="Aggregate">
          <select className="db-select" value={agg}
                  onChange={(e) => { setAgg(e.target.value); load({ agg: e.target.value }); }}>
            <option value="sum">Sum</option>
            <option value="avg">Average</option>
            <option value="count">Count</option>
          </select>
        </Field>
        {agg !== "count" && (
          <Field label="Measure">
            <select className="db-select" value={measure}
                    onChange={(e) => { setMeasure(e.target.value); load({ measure: e.target.value }); }}>
              {measures.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </Field>
        )}
        <label className="db-toggle-row" style={{ cursor: "pointer" }}>
          <span className="text-xs">Include total rows</span>
          <input type="checkbox" className="accent-[#00aaff] w-4 h-4 ml-2" checked={includeTotals}
                 onChange={(e) => { setIncludeTotals(e.target.checked); load({ includeTotals: e.target.checked }); }} />
        </label>
      </div>

      {loading && <div className="text-sm mono" style={{ color: "var(--db-muted)" }}>Computing…</div>}
      {err && <div className="db-danger text-sm mono">Error: {err}</div>}

      {!loading && rows.length > 0 && (
        <>
          <div className="db-card p-4">
            <div className="text-sm font-medium mb-3">
              {agg === "count" ? "Count" : `${agg} of ${data.measure}`} by {data.dimension}
              {data.total != null && <span className="text-[11px] mono ml-2" style={{ color: "var(--db-muted)" }}>total: {data.total.toLocaleString()}</span>}
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={rows.slice(0, 20)} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                <XAxis dataKey="key" tick={{ fontSize: 11 }} interval={0} angle={-25} textAnchor="end" height={60} />
                <YAxis tick={{ fontSize: 11 }} width={48} />
                <Tooltip />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {rows.slice(0, 20).map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="db-card p-0 overflow-auto max-h-[320px]">
            <table className="w-full text-sm">
              <thead><tr>
                <th className="text-left px-3 py-2" style={{ color: "var(--db-muted)" }}>{data.dimension}</th>
                <th className="text-right px-3 py-2" style={{ color: "var(--db-muted)" }}>{agg === "count" ? "count" : data.measure}</th>
                <th className="text-right px-3 py-2" style={{ color: "var(--db-muted)" }}>rows</th>
              </tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className="border-t" style={{ borderColor: "var(--db-border, #222)" }}>
                    <td className="px-3 py-1.5">{r.key}</td>
                    <td className="px-3 py-1.5 text-right db-tabular-num mono">{Number(r.value).toLocaleString()}</td>
                    <td className="px-3 py-1.5 text-right db-tabular-num mono" style={{ color: "var(--db-muted)" }}>{r.rows}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function QualityView({ baseUrl }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true); setErr(null);
      try {
        const r = await fetch(`${baseUrl}/quality`);
        setData(await r.json());
      } catch (e) { setErr(e.message); } finally { setLoading(false); }
    })();
  }, [baseUrl]);

  if (loading) return <div className="text-sm mono" style={{ color: "var(--db-muted)" }}>Auditing…</div>;
  if (err) return <div className="db-danger text-sm mono">Error: {err}</div>;
  if (!data) return null;
  if (data.enabled === false) {
    return <div className="db-card p-5 text-sm" style={{ color: "var(--db-muted)" }}>
      Data-quality module isn’t enabled. Enable <span className="db-accent">Data-quality audit</span> in Configure.
    </div>;
  }
  return (
    <div className="space-y-6" data-testid="quality-tab">
      {(data.sheets || []).map((s) => {
        const i = s.issues || {};
        const scoreColor = s.score >= 80 ? "db-success" : s.score >= 50 ? "db-warning" : "db-danger";
        return (
          <div key={s.label} className="space-y-3">
            <div className="flex items-center gap-3">
              <span className="db-chip db-chip-blue">{s.label}</span>
              <span className="text-sm font-medium">{s.name}</span>
              <span className={`db-tabular-num mono text-2xl ml-auto ${scoreColor}`}>{s.score}<span className="text-xs">/100</span></span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Metric label="Rows" value={s.row_count} />
              <Metric label="Duplicate rows" value={i.duplicate_rows} warn={i.duplicate_rows > 0} />
              <Metric label="Total/subtotal rows" value={i.total_subtotal_rows} warn={i.total_subtotal_rows > 0} />
              <Metric label="Cols w/ missing" value={(i.missing || []).length} warn={(i.missing || []).length > 0} />
            </div>
            {(i.inconsistent_categories || []).length > 0 && (
              <div className="db-card p-4">
                <div className="text-sm font-medium mb-2 db-warning">Inconsistent category values</div>
                {i.inconsistent_categories.map((c) => (
                  <div key={c.column} className="text-[12px] mono mb-1">
                    <span className="db-accent">{c.column}</span>: {c.groups.map((g) => g.variants.join(" / ")).join("  ·  ")}
                  </div>
                ))}
              </div>
            )}
            {(i.missing || []).length > 0 && (
              <div className="db-card p-4">
                <div className="text-sm font-medium mb-2">Missing values</div>
                <div className="flex flex-wrap gap-2">
                  {i.missing.map((m) => (
                    <span key={m.column} className="db-chip db-chip-grey">{m.column}: {m.missing} ({m.pct}%)</span>
                  ))}
                </div>
              </div>
            )}
            {(i.type_mismatches || []).length > 0 && (
              <div className="db-card p-4">
                <div className="text-sm font-medium mb-2 db-warning">Non-numeric values in numeric columns</div>
                <div className="flex flex-wrap gap-2">
                  {i.type_mismatches.map((t) => (
                    <span key={t.column} className="db-chip db-chip-grey">{t.column}: {t.non_numeric}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <div className="text-[10px] mono uppercase tracking-wider mb-1" style={{ color: "var(--db-muted)" }}>{label}</div>
      {children}
    </div>
  );
}

function Metric({ label, value, warn }) {
  return (
    <div className="db-card p-3">
      <div className="text-[10px] mono uppercase tracking-wider" style={{ color: "var(--db-muted)" }}>{label}</div>
      <div className={`db-tabular-num mono text-xl mt-1 ${warn ? "db-warning" : ""}`}>{typeof value === "number" ? value.toLocaleString() : value}</div>
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
