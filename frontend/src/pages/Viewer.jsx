import { useEffect, useMemo, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { LayoutDashboard, Sparkles, Send, RefreshCw, Link as LinkIcon } from "lucide-react";
import { PUBLIC_BASE } from "../api";

const CHART_COLORS = ["#00aaff", "#7c5cff", "#ff8a3d", "#23c48e", "#ff5d5d", "#f7c948", "#36c5f0", "#a78bfa"];

function parseToken(input) {
  if (!input) return "";
  const s = input.trim();
  const m = s.match(/\/public\/([^/?#\s]+)/);
  if (m) return m[1];
  // raw token (strip any trailing slice path)
  return s.split(/[/?#\s]/)[0];
}

export default function Viewer() {
  const initial = useMemo(() => {
    const p = new URLSearchParams(window.location.search);
    return p.get("link") || p.get("token") || "";
  }, []);
  const [input, setInput] = useState(initial);
  const [token, setToken] = useState(parseToken(initial));
  const [dash, setDash] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sheetIdx, setSheetIdx] = useState(0);

  const baseUrl = token ? `${PUBLIC_BASE}/${token}` : null;

  const load = async (tok) => {
    const t = tok ?? token;
    if (!t) return;
    setLoading(true); setErr(null); setDash(null); setSheetIdx(0);
    try {
      const r = await fetch(`${PUBLIC_BASE}/${t}/dashboard`);
      const j = await r.json();
      if (j.enabled === false) { setErr(j.message || "Dashboard not enabled for this link."); }
      else setDash(j);
    } catch (e) { setErr(e.message); } finally { setLoading(false); }
  };

  useEffect(() => { if (token) load(token); /* eslint-disable-next-line */ }, []);

  const submit = () => {
    const t = parseToken(input);
    setToken(t);
    const url = new URL(window.location);
    url.searchParams.set("token", t);
    window.history.replaceState({}, "", url);
    load(t);
  };

  const sheets = dash?.sheets || [];
  const sheet = sheets[sheetIdx];

  return (
    <div style={{ minHeight: "100vh", background: "#07070e", color: "#e7e8ee" }}>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "28px 20px" }}>
        <div className="flex items-center gap-2 mb-1">
          <LayoutDashboard className="w-5 h-5" style={{ color: "#00aaff" }} />
          <h1 className="text-lg font-semibold">Dynamic dashboard viewer</h1>
        </div>
        <p className="text-sm mb-4" style={{ color: "#8a8aa3" }}>
          Paste any public export link (or token). The dashboard renders live and the copilot answers about the selected sheet.
        </p>

        <div className="db-link-row" style={{ marginBottom: 18 }}>
          <LinkIcon className="w-4 h-4" style={{ color: "#8a8aa3" }} />
          <input
            data-testid="viewer-link-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
            placeholder="https://…/api/public/<token>/dashboard  or  <token>"
            style={{ flex: 1 }}
          />
          <button onClick={submit} className="db-btn">Load</button>
          {token && <button onClick={() => load()} className="db-btn db-btn-ghost"><RefreshCw className="w-3.5 h-3.5" /></button>}
        </div>

        {loading && <div className="text-sm mono" style={{ color: "#8a8aa3" }}>Loading dashboard…</div>}
        {err && <div className="db-card p-4 text-sm" style={{ color: "#ff8a8a" }}>{err}</div>}

        {!loading && dash && <AnalysisSections analysis={dash.analysis} />}

        {!loading && dash && sheets.length > 0 && (
          <>
            <div className="flex items-center gap-2 mb-4 flex-wrap">
              <span className="text-[11px] mono uppercase tracking-wider" style={{ color: "#8a8aa3" }}>{dash.project || "Export"} ·</span>
              {sheets.map((s, i) => (
                <button key={s.label || i} onClick={() => setSheetIdx(i)}
                        className={`db-btn ${i === sheetIdx ? "" : "db-btn-ghost"}`}>
                  {s.label || `Sheet ${i + 1}`}
                </button>
              ))}
            </div>

            {sheet && (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                  {(sheet.kpis || []).map((k, i) => (
                    <div key={i} className="db-card p-4">
                      <div className="text-[10px] mono uppercase tracking-wider" style={{ color: "#8a8aa3" }}>{k.label}</div>
                      <div className="db-tabular-num mono text-2xl mt-1">{typeof k.value === "number" ? k.value.toLocaleString() : k.value}</div>
                    </div>
                  ))}
                </div>

                {(sheet.charts || []).length > 0 && (
                  <div className="grid md:grid-cols-2 gap-4 mb-4">
                    {sheet.charts.map((c, i) => (
                      <div key={i} className="db-card p-4">
                        <div className="text-sm font-medium mb-3">{c.title}</div>
                        <ResponsiveContainer width="100%" height={220}>
                          <BarChart data={c.data} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                            <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={50} />
                            <YAxis tick={{ fontSize: 11 }} width={44} />
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

                <div className="db-card p-0 overflow-auto max-h-[420px] mb-6">
                  <table className="w-full text-sm">
                    <thead><tr>
                      {(sheet.columns || []).map((col) => (
                        <th key={col.name} className="text-left px-3 py-2 sticky top-0"
                            style={{ background: "#0d1117", color: "#8a8aa3", fontWeight: 600 }}>
                          {col.name}<span className="ml-1 text-[9px] mono opacity-60">{col.type}</span>
                        </th>
                      ))}
                    </tr></thead>
                    <tbody>
                      {(sheet.rows || []).slice(0, 100).map((row, ri) => (
                        <tr key={ri} style={{ borderTop: "1px solid #1c1c2e" }}>
                          {(sheet.columns || []).map((col) => (
                            <td key={col.name} className="px-3 py-1.5 whitespace-nowrap">{String(row[col.name] ?? "")}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <ViewerCopilot baseUrl={baseUrl} sheetLabel={sheet.label} />
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function AnalysisSections({ analysis }) {
  if (!analysis) return null;
  const { summary, totals, status_breakdown, flags, mode_badge } = analysis;
  const hasAny = summary || totals || status_breakdown || (flags && flags.length >= 0);
  if (!hasAny) return null;
  const card = { background: "rgba(255,255,255,0.04)", border: "1px solid #1c1c2e", borderRadius: 12, padding: 16 };
  return (
    <div style={{ marginBottom: 18 }}>
      {mode_badge && (
        <div className="text-[11px] mono uppercase tracking-wider" style={{ color: "#00aaff", marginBottom: 8 }}>{mode_badge}</div>
      )}
      {summary && <div style={{ ...card, marginBottom: 12 }}><div className="text-sm">{summary}</div></div>}
      {totals && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(120px,1fr))", gap: 12, marginBottom: 12 }}>
          {Object.entries(totals).map(([k, v]) => (
            <div key={k} style={card}>
              <div className="text-[10px] mono uppercase tracking-wider" style={{ color: "#8a8aa3" }}>{k.replace(/_/g, " ")}</div>
              <div className="db-tabular-num mono text-xl mt-1">{typeof v === "number" ? v.toLocaleString() : String(v)}</div>
            </div>
          ))}
        </div>
      )}
      {status_breakdown && Object.keys(status_breakdown).length > 0 && (
        <div style={{ ...card, marginBottom: 12 }}>
          <div className="text-sm font-medium mb-2">Status breakdown</div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(status_breakdown).map(([k, v]) => (
              <span key={k} className="db-chip db-chip-grey">{k}: {v}</span>
            ))}
          </div>
        </div>
      )}
      {flags && flags.length > 0 && (
        <div style={{ ...card, marginBottom: 12 }}>
          <div className="text-sm font-medium mb-2">Flags ({flags.length})</div>
          <div className="space-y-1">
            {flags.slice(0, 20).map((f, i) => (
              <div key={i} className="text-[12px] mono">{f.message || f.title || JSON.stringify(f)}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ViewerCopilot({ baseUrl, sheetLabel }) {
  const [q, setQ] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [loading, setLoading] = useState(false);

  // reset thread when the selected sheet changes
  useEffect(() => { setMsgs([]); setSessionId(null); }, [sheetLabel, baseUrl]);

  const ask = async (text) => {
    const question = (text ?? q).trim();
    if (!question || loading) return;
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setQ(""); setLoading(true);
    try {
      const r = await fetch(`${baseUrl}/copilot?sheet=${encodeURIComponent(sheetLabel || "")}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question, session_id: sessionId }),
      });
      const j = await r.json();
      if (j.session_id) setSessionId(j.session_id);
      setMsgs((m) => [...m, { role: "assistant", text: j.answer || j.message || "(no answer)" }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", text: `Error: ${e.message}` }]);
    } finally { setLoading(false); }
  };

  const SUGGESTIONS = [
    `Summarize the ${sheetLabel || "sheet"} in 3 points`,
    "Which category has the highest total?",
    "Any data-quality issues?",
  ];

  return (
    <div className="db-card p-4">
      <div className="flex items-center gap-2 mb-3">
        <Sparkles className="w-4 h-4" style={{ color: "#00aaff" }} />
        <div className="text-sm font-semibold">Copilot</div>
        <span className="text-[11px] mono" style={{ color: "#8a8aa3" }}>answers about “{sheetLabel}”</span>
      </div>
      {msgs.length === 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => ask(s)} className="db-btn db-btn-ghost" style={{ fontSize: 12 }}>{s}</button>
          ))}
        </div>
      )}
      <div className="space-y-2 mb-3" style={{ maxHeight: 320, overflow: "auto" }}>
        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <div className="inline-block px-3 py-2 rounded-lg text-sm whitespace-pre-wrap"
                 style={m.role === "user" ? { background: "#13233a" } : { background: "rgba(255,255,255,0.04)" }}>
              {m.text}
            </div>
          </div>
        ))}
        {loading && <div className="text-sm mono" style={{ color: "#8a8aa3" }}>Thinking…</div>}
      </div>
      <div className="db-link-row">
        <input value={q} onChange={(e) => setQ(e.target.value)}
               onKeyDown={(e) => { if (e.key === "Enter") ask(); }}
               placeholder={`Ask about ${sheetLabel || "this sheet"}…`} style={{ flex: 1 }} />
        <button onClick={() => ask()} disabled={loading} className="db-btn"><Send className="w-3.5 h-3.5" /> Ask</button>
      </div>
    </div>
  );
}
