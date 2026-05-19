import { useState } from "react";
import { toast } from "sonner";
import { api, formatErr } from "../api";
import {
  RefreshCw, Plus, Trash2, Copy, ChevronRight, Check, X, Sparkles,
  HelpCircle, Database,
} from "lucide-react";

const APPS_SCRIPT_CODE = `function doGet(e) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const data = sheet.getDataRange().getValues();
  const headers = data[0];
  const rows = data.slice(1).map(row => {
    const obj = {};
    headers.forEach((h, i) => obj[h] = row[i]);
    return obj;
  });
  return ContentService
    .createTextOutput(JSON.stringify({ status: "ok", count: rows.length, data: rows }))
    .setMimeType(ContentService.MimeType.JSON);
}`;

const COLOR_MAP = {
  A: "blue", B: "orange", C: "purple", D: "green", E: "red",
};

export default function SheetsPanel({ sessionMeta, reload, onNext }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [showGuide, setShowGuide] = useState(sessionMeta.sheets.length === 0);
  const sessionId = sessionMeta.id;
  const sheets = sessionMeta.sheets || [];
  const usedLabels = new Set(sheets.map((s) => s.label));
  const nextLabel = ["A", "B", "C", "D", "E"].find((l) => !usedLabels.has(l));

  const addSheet = async () => {
    if (!url.trim()) return;
    setBusy(true);
    try {
      await api.post(`/sessions/${sessionId}/sheets`, { url: url.trim() });
      toast.success(`Sheet ${nextLabel} connected`);
      setUrl("");
      await reload();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || e.message);
    } finally { setBusy(false); }
  };

  const removeSheet = async (label) => {
    if (!confirm(`Remove sheet ${label}?`)) return;
    try {
      await api.delete(`/sessions/${sessionId}/sheets/${label}`);
      toast.success(`Sheet ${label} removed`);
      await reload();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || e.message);
    }
  };

  const refreshSheet = async (label) => {
    try {
      const { data } = await api.post(`/sessions/${sessionId}/sheets/${label}/refresh`);
      toast.success(`Sheet ${label} refreshed · ${data.rows} rows`);
      await reload();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || e.message);
    }
  };

  const loadDemo = async () => {
    setBusy(true);
    try {
      await api.post(`/sessions/${sessionId}/load-demo`);
      toast.success("Demo data loaded — 2 snapshots, 79 rows each");
      await reload();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || e.message);
    } finally { setBusy(false); }
  };

  const copyCode = async () => {
    await navigator.clipboard.writeText(APPS_SCRIPT_CODE);
    toast.success("Apps Script code copied");
  };

  return (
    <div className="space-y-6" data-testid="sheets-panel">
      {/* Header bar */}
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Connect Sheets</h2>
          <p className="text-sm mt-1" style={{ color: "var(--db-muted)" }}>
            Paste up to 5 Google Apps Script Web App URLs. When you add 2 or more,
            variance analysis activates automatically.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button data-testid="toggle-guide-button" onClick={() => setShowGuide((s) => !s)}
                  className="db-btn db-btn-ghost">
            <HelpCircle className="w-4 h-4" /> {showGuide ? "Hide" : "Show"} setup guide
          </button>
          <button data-testid="load-demo-button" onClick={loadDemo} disabled={busy}
                  className="db-btn db-btn-ghost">
            <Sparkles className="w-4 h-4" /> Load demo data
          </button>
        </div>
      </div>

      {/* Guide */}
      {showGuide && (
        <div className="db-card p-6 fade-in" data-testid="setup-guide">
          <div className="flex items-center gap-2 mb-3">
            <Database className="w-4 h-4 db-accent" />
            <div className="text-sm font-semibold">Publish your Google Sheet as an Apps Script Web App</div>
          </div>
          <ol className="text-sm space-y-1 mb-4" style={{ color: "var(--db-muted)" }}>
            <li>1 — Open your Google Sheet</li>
            <li>2 — Click <span className="mono db-accent">Extensions → Apps Script</span></li>
            <li>3 — Paste the code below and save</li>
            <li>4 — Click <span className="mono db-accent">Deploy → New Deployment</span></li>
            <li>5 — Type: <span className="mono">Web App</span> · Execute as: <span className="mono">Me</span> · Who has access: <span className="mono">Anyone</span></li>
            <li>6 — Click <span className="mono db-accent">Deploy</span> → copy the Web App URL</li>
            <li>7 — Paste that URL below</li>
          </ol>
          <div className="relative">
            <pre className="db-code">{APPS_SCRIPT_CODE}</pre>
            <button data-testid="copy-apps-script-button" onClick={copyCode}
                    className="db-btn db-btn-ghost absolute top-3 right-3">
              <Copy className="w-3.5 h-3.5" /> Copy code
            </button>
          </div>
        </div>
      )}

      {/* Add new sheet */}
      {nextLabel && (
        <div className="db-card p-5" data-testid="add-sheet-card">
          <div className="flex items-center gap-3 mb-3">
            <span className={`db-chip db-chip-${COLOR_MAP[nextLabel]}`}>Sheet {nextLabel}</span>
            <span className="text-xs mono" style={{ color: "var(--db-muted)" }}>
              {sheets.length === 0 ? "primary · required" : "additional · activates variance"}
            </span>
          </div>
          <div className="flex gap-3 flex-wrap">
            <input
              data-testid="apps-script-url-input"
              placeholder="https://script.google.com/macros/s/AKfycb…/exec"
              className="db-input flex-1 min-w-[300px]"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addSheet()}
            />
            <button data-testid="add-sheet-button" onClick={addSheet}
                    disabled={busy || !url.trim()} className="db-btn">
              <Plus className="w-4 h-4" /> {busy ? "Connecting…" : "Connect"}
            </button>
          </div>
        </div>
      )}

      {/* Connected sheets */}
      <div className="space-y-3">
        {sheets.map((s) => (
          <div key={s.label} className="db-card p-5" data-testid={`sheet-row-${s.label}`}>
            <div className="flex items-center gap-4 flex-wrap">
              <span className={`db-chip db-chip-${s.color || COLOR_MAP[s.label]}`}>Sheet {s.label}</span>
              <span className="db-dot on"></span>
              <div className="text-sm font-semibold">{s.name || `Sheet ${s.label}`}</div>
              <div className="db-tabular-num mono text-xs" style={{ color: "var(--db-muted)" }}>
                {s.rows} rows · {s.columns} columns
              </div>
              {s.last_fetched && (
                <div className="text-[11px] mono" style={{ color: "var(--db-muted)" }}>
                  fetched {new Date(s.last_fetched).toLocaleString()}
                </div>
              )}
              <div className="flex-1"></div>
              <button data-testid={`refresh-sheet-${s.label}`} onClick={() => refreshSheet(s.label)}
                      className="db-btn db-btn-ghost">
                <RefreshCw className="w-3.5 h-3.5" /> Refresh
              </button>
              <button data-testid={`remove-sheet-${s.label}`} onClick={() => removeSheet(s.label)}
                      className="db-btn db-btn-ghost">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Detected mapping summary */}
            {s.detected_mapping && Object.keys(s.detected_mapping).length > 0 && (
              <div className="mt-3 pt-3 border-t db-divider">
                <div className="text-[11px] mono uppercase tracking-wider mb-2"
                     style={{ color: "var(--db-muted)" }}>
                  detected columns
                </div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(s.detected_mapping).map(([std, src]) => (
                    <span key={std} className="db-chip db-chip-grey">
                      <span className="db-accent">{std}</span>
                      <ChevronRight className="w-3 h-3" />
                      <span>{src}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Data quality */}
            {s.data_quality && (
              <div className="mt-3 pt-3 border-t db-divider grid grid-cols-2 md:grid-cols-4 gap-3">
                <Stat label="Total rows" value={s.data_quality.total_rows} />
                <Stat label="Missing activity"
                      value={s.data_quality.missing_per_field?.activity ?? 0}
                      warn={(s.data_quality.missing_per_field?.activity ?? 0) > 0} />
                <Stat label="Missing reason"
                      value={s.data_quality.missing_per_field?.reason ?? 0}
                      muted />
                <Stat label="Invalid dates" value={s.data_quality.invalid_dates}
                      warn={s.data_quality.invalid_dates > 0} />
              </div>
            )}

            {/* Preview */}
            {s.preview && s.preview.length > 0 && (
              <details className="mt-3">
                <summary className="text-[11px] mono uppercase tracking-wider cursor-pointer"
                         style={{ color: "var(--db-muted)" }}>
                  preview · first {Math.min(5, s.preview.length)} rows
                </summary>
                <div className="overflow-x-auto mt-2">
                  <table className="text-[11px] mono w-full">
                    <thead>
                      <tr style={{ color: "var(--db-muted)" }}>
                        {Object.keys(s.preview[0]).slice(0, 6).map((k) => (
                          <th key={k} className="text-left py-1 pr-3 font-normal uppercase tracking-wider">
                            {k}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {s.preview.slice(0, 5).map((row, i) => (
                        <tr key={i} className="border-t db-divider">
                          {Object.keys(s.preview[0]).slice(0, 6).map((k) => (
                            <td key={k} className="py-1 pr-3 truncate max-w-[200px]">
                              {String(row[k] ?? "").slice(0, 60)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
          </div>
        ))}
      </div>

      {sheets.length === 0 && (
        <div className="db-card p-10 text-center" data-testid="empty-sheets-hint">
          <div className="text-sm mono mb-3" style={{ color: "var(--db-muted)" }}>
            No sheets yet — paste an Apps Script URL above or click <span className="db-accent">Load demo data</span> to explore the system.
          </div>
        </div>
      )}

      {/* Next */}
      <div className="flex items-center justify-between gap-4 pt-4">
        <div className="flex items-center gap-2">
          {sheets.length >= 2 ? (
            <span className="db-chip db-chip-green"><Check className="w-3 h-3" /> Variance enabled · {sheets.length} sheets</span>
          ) : sheets.length === 1 ? (
            <span className="db-chip db-chip-blue">Single sheet mode</span>
          ) : (
            <span className="db-chip db-chip-grey"><X className="w-3 h-3" /> No sheets connected</span>
          )}
        </div>
        <button data-testid="next-to-configure-button" disabled={sheets.length === 0}
                onClick={onNext} className="db-btn">
          Configure export <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

function Stat({ label, value, warn, muted }) {
  return (
    <div>
      <div className="text-[10px] mono uppercase tracking-wider"
           style={{ color: "var(--db-muted)" }}>{label}</div>
      <div className={`text-lg db-tabular-num mono ${
        warn ? "db-warning" : muted ? "" : ""
      }`}>{value}</div>
    </div>
  );
}
