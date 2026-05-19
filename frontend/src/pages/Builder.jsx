import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, setAuthHeader, formatErr } from "../api";
import { Workflow, LogOut, Plus, ChevronDown, FolderOpen, Trash2 } from "lucide-react";
import SheetsPanel from "../components/SheetsPanel";
import ConfigPanel from "../components/ConfigPanel";
import ExportPanel from "../components/ExportPanel";

const STEPS = [
  { key: "sheets", label: "1 · Connect Sheets" },
  { key: "configure", label: "2 · Configure Export" },
  { key: "export", label: "3 · Get Link" },
];

export default function Builder({ user, setUser }) {
  const nav = useNavigate();
  const [step, setStep] = useState("sheets");
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [sessionMeta, setSessionMeta] = useState(null);
  const [exportFields, setExportFields] = useState([]);
  const [analysisSummary, setAnalysisSummary] = useState(null);
  const [showSessionDropdown, setShowSessionDropdown] = useState(false);

  const loadSessions = useCallback(async () => {
    try {
      const { data } = await api.get("/sessions");
      setSessions(data);
      if (!sessionId && data.length > 0) {
        setSessionId(data[0].id);
      }
      if (!sessionId && data.length === 0) {
        const created = await api.post("/sessions", { name: "My First Project" });
        setSessions([created.data]);
        setSessionId(created.data.id);
      }
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || e.message);
    }
  }, [sessionId]);

  const loadSession = useCallback(async (sid) => {
    if (!sid) return;
    try {
      const { data } = await api.get(`/sessions/${sid}`);
      setSessionMeta(data);
      const cfg = await api.get(`/sessions/${sid}/export-config`);
      setExportFields(cfg.data.fields || []);
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || e.message);
    }
  }, []);

  useEffect(() => { loadSessions(); }, [loadSessions]);
  useEffect(() => { if (sessionId) loadSession(sessionId); }, [sessionId, loadSession]);

  const onCreateSession = async () => {
    const name = prompt("Project name?", "New Project");
    if (!name) return;
    try {
      const { data } = await api.post("/sessions", { name });
      setSessions([data, ...sessions]);
      setSessionId(data.id);
      setStep("sheets");
      toast.success(`Created project ${name}`);
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || e.message);
    }
  };

  const onDeleteSession = async () => {
    if (!sessionId) return;
    if (!confirm("Delete this project and all its sheets/analysis?")) return;
    try {
      await api.delete(`/sessions/${sessionId}`);
      toast.success("Project deleted");
      setSessionId(null);
      setSessionMeta(null);
      await loadSessions();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || e.message);
    }
  };

  const onLogout = async () => {
    try { await api.post("/auth/logout"); } catch {}
    setAuthHeader(null);
    setUser(null);
    nav("/login");
  };

  const sheetCount = sessionMeta?.sheets?.length || 0;
  const hasAnalysis = !!sessionMeta?.has_analysis;
  const isMulti = sheetCount >= 2;

  return (
    <div className="min-h-screen" data-testid="builder-page">
      {/* Header */}
      <header className="border-b db-divider sticky top-0 z-30"
              style={{ background: "rgba(7,7,14,0.85)", backdropFilter: "blur(12px)" }}>
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center gap-6">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center"
                 style={{ background: "rgba(0,170,255,0.1)", border: "1px solid rgba(0,170,255,0.4)" }}>
              <Workflow className="w-5 h-5" style={{ color: "#00aaff" }} />
            </div>
            <div>
              <div className="text-base font-semibold tracking-tight">DelayBridge</div>
              <div className="text-[10px] mono uppercase tracking-widest"
                   style={{ color: "var(--db-muted)" }}>
                connect → configure → export
              </div>
            </div>
          </div>

          {/* Project picker */}
          <div className="relative">
            <button
              data-testid="session-dropdown-button"
              onClick={() => setShowSessionDropdown((s) => !s)}
              className="db-btn-ghost db-btn"
            >
              <FolderOpen className="w-4 h-4" />
              <span className="mono">
                {sessions.find((s) => s.id === sessionId)?.name || "No project"}
              </span>
              <ChevronDown className="w-3.5 h-3.5" />
            </button>
            {showSessionDropdown && (
              <div className="absolute mt-2 w-72 db-card p-2 z-40" data-testid="session-dropdown">
                {sessions.map((s) => (
                  <button
                    key={s.id}
                    data-testid={`session-item-${s.id}`}
                    onClick={() => { setSessionId(s.id); setShowSessionDropdown(false); setStep("sheets"); }}
                    className={`w-full text-left p-2 rounded-md hover:bg-white/5 ${
                      s.id === sessionId ? "bg-white/[0.04]" : ""
                    }`}
                  >
                    <div className="text-sm">{s.name}</div>
                    <div className="text-[11px] mono" style={{ color: "var(--db-muted)" }}>
                      {s.sheet_count} sheets · {s.has_analysis ? "analysed" : "draft"}
                    </div>
                  </button>
                ))}
                <div className="border-t db-divider my-2"></div>
                <button data-testid="new-session-button" onClick={() => { setShowSessionDropdown(false); onCreateSession(); }}
                        className="w-full text-left p-2 rounded-md hover:bg-white/5 flex items-center gap-2">
                  <Plus className="w-4 h-4" /> <span className="text-sm">New project</span>
                </button>
              </div>
            )}
          </div>

          <div className="flex-1"></div>

          {/* Steps */}
          <div className="hidden md:flex items-center gap-2">
            {STEPS.map((s, i) => {
              const idx = STEPS.findIndex((x) => x.key === step);
              const cls = s.key === step ? "active" : i < idx ? "done" : "";
              return (
                <button
                  key={s.key}
                  data-testid={`step-${s.key}`}
                  onClick={() => setStep(s.key)}
                  className={`db-step ${cls}`}
                >
                  {s.label}
                </button>
              );
            })}
          </div>

          <div className="flex-1"></div>

          <div className="flex items-center gap-3">
            <button data-testid="delete-session-button" onClick={onDeleteSession}
                    className="db-btn db-btn-ghost" title="Delete project">
              <Trash2 className="w-4 h-4" />
            </button>
            <div className="text-xs mono hidden sm:block" style={{ color: "var(--db-muted)" }}>
              {user?.email}
            </div>
            <button data-testid="logout-button" onClick={onLogout} className="db-btn db-btn-ghost">
              <LogOut className="w-4 h-4" /> Logout
            </button>
          </div>
        </div>

        {/* Mobile steps */}
        <div className="md:hidden flex items-center gap-2 px-6 pb-4 overflow-x-auto">
          {STEPS.map((s, i) => {
            const idx = STEPS.findIndex((x) => x.key === step);
            const cls = s.key === step ? "active" : i < idx ? "done" : "";
            return (
              <button key={s.key} onClick={() => setStep(s.key)}
                      className={`db-step ${cls} flex-shrink-0`}>
                {s.label}
              </button>
            );
          })}
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 fade-in">
        {!sessionMeta && (
          <div className="db-card p-10 text-center">
            <div className="text-sm mono" style={{ color: "var(--db-muted)" }}>Loading project…</div>
          </div>
        )}

        {sessionMeta && step === "sheets" && (
          <SheetsPanel
            sessionMeta={sessionMeta}
            reload={() => loadSession(sessionId)}
            onNext={() => setStep("configure")}
          />
        )}

        {sessionMeta && step === "configure" && (
          <ConfigPanel
            sessionMeta={sessionMeta}
            exportFields={exportFields}
            setExportFields={setExportFields}
            isMulti={isMulti}
            hasAnalysis={hasAnalysis}
            onAnalyze={async () => {
              try {
                const { data } = await api.post(`/sessions/${sessionId}/analyze`);
                setAnalysisSummary(data);
                toast.success(`Analysis complete · ${data.flags_count} flags · risk ${data.risk_score}`);
                await loadSession(sessionId);
              } catch (e) {
                toast.error(formatErr(e.response?.data?.detail) || e.message);
              }
            }}
            onSaveFields={async (fields) => {
              try {
                await api.post(`/sessions/${sessionId}/export-config`, { fields });
                setExportFields(fields);
              } catch (e) {
                toast.error(formatErr(e.response?.data?.detail) || e.message);
              }
            }}
            onNext={() => setStep("export")}
            onBack={() => setStep("sheets")}
            analysisSummary={analysisSummary || sessionMeta.analysis_summary}
          />
        )}

        {sessionMeta && step === "export" && (
          <ExportPanel
            sessionMeta={sessionMeta}
            exportFields={exportFields}
            onBack={() => setStep("configure")}
          />
        )}
      </main>

      <footer className="max-w-7xl mx-auto px-6 py-10 text-center text-xs mono"
              style={{ color: "var(--db-muted)" }}>
        DelayBridge · backend-only intelligence layer · paste your links into Lovable, Apps Script, or any HTTP client
      </footer>
    </div>
  );
}
