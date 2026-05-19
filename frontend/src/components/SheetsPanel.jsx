import { useState } from "react";
import { toast } from "sonner";
import { api, formatErr } from "../api";
import {
  RefreshCw, Plus, Trash2, Copy, ChevronRight, Check, X,
  HelpCircle, Database, ChevronDown, Loader2, ListPlus,
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

const COLOR_MAP = { A: "blue", B: "orange", C: "purple", D: "green", E: "red" };
const LABEL_ORDER = ["A", "B", "C", "D", "E"];

export default function SheetsPanel({ sessionMeta, reload, onNext }) {
  const sessionId = sessionMeta.id;
  const sheets = sessionMeta.sheets || [];
  const usedLabels = new Set(sheets.map((s) => s.label));
  const freeLabels = LABEL_ORDER.filter((l) => !usedLabels.has(l));

  const [bulkText, setBulkText] = useState("");
  const [bulkBusy, setBulkBusy] = useState(false);
  const [lineStates, setLineStates] = useState({}); // {idx: 'pending'|'ok'|err}
  const [showGuide, setShowGuide] = useState(false);

  const connectOne = async (url) => {
    return api.post(`/sessions/${sessionId}/sheets`, { url: url.trim() });
  };

  const onBulkConnect = async () => {
    const lines = bulkText
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter((l) => l.length > 0);
    if (!lines.length) {
      toast.error("Paste one or more Apps Script URLs first.");
      return;
    }
    if (lines.length > freeLabels.length) {
      toast.error(`You can connect at most ${freeLabels.length} more sheet(s) in this project.`);
      return;
    }
    setBulkBusy(true);
    const fresh = {};
    lines.forEach((_, i) => { fresh[i] = "pending"; });
    setLineStates(fresh);

    // Connect sequentially so the backend assigns labels A, B, C…
    let okCount = 0;
    const errors = [];
    for (let i = 0; i < lines.length; i++) {
      try {
        await connectOne(lines[i]);
        setLineStates((s) => ({ ...s, [i]: "ok" }));
        okCount++;
      } catch (e) {
        const msg = formatErr(e.response?.data?.detail) || e.message;
        setLineStates((s) => ({ ...s, [i]: msg }));
        errors.push(`Line ${i + 1}: ${msg}`);
      }
    }
    setBulkBusy(false);
    if (okCount > 0) {
      toast.success(`Connected ${okCount} sheet(s)`);
      // Keep only failed lines in the textarea so user can fix them
      const failedLines = lines.filter((_, i) => lineStates[i] !== "ok" && fresh[i] !== "ok");
      // After loop, look at the local results map we built
      const remaining = [];
      lines.forEach((l, i) => {
        // anything other than "ok" stays
        // we rebuilt states inside loop; can't access easily — use closure variable
      });
      setBulkText(errors.length ? errors.map(() => "").join("\n") && lines.filter((_, i) => false).join("\n") : "");
      // Simpler: just clear if all ok, keep all if any failure
      if (errors.length === 0) {
        setBulkText("");
        setLineStates({});
      }
      await reload();
    }
    if (errors.length) {
      errors.forEach((e) => toast.error(e));
    }
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

  const copyCode = async () => {
    await navigator.clipboard.writeText(APPS_SCRIPT_CODE);
    toast.success("Apps Script code copied");
  };

  const lines = bulkText.split(/\r?\n/);

  return (
    <div className="space-y-6" data-testid="sheets-panel">
      {/* Header */}
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Connect your sheets</h2>
          <p className="text-sm mt-1" style={{ color: "var(--db-muted)" }}>
            Paste up to 5 Google Apps Script Web App URLs — one per line. Add 2 or more to activate variance analysis.
          </p>
        </div>
        <button data-testid="toggle-guide-button" onClick={() => setShowGuide((s) => !s)}
                className="db-btn db-btn-ghost">
          <HelpCircle className="w-4 h-4" />
          {showGuide ? "Hide" : "How do I get an Apps Script URL?"}
        </button>
      </div>

      {/* Connected sheets — compact summary first */}
      {sheets.length > 0 && (
        <div className="space-y-3" data-testid="connected-sheets-list">
          <div className="text-[11px] mono uppercase tracking-wider"
               style={{ color: "var(--db-muted)" }}>
            connected · {sheets.length} of 5
          </div>
          {sheets.map((s) => (
            <ConnectedSheetCard key={s.label} s={s}
                                onRefresh={() => refreshSheet(s.label)}
                                onRemove={() => removeSheet(s.label)} />
          ))}
        </div>
      )}

      {/* Bulk-add — primary input */}
      {freeLabels.length > 0 && (
        <div className="db-card p-5" data-testid="bulk-add-card">
          <div className="flex items-center gap-3 mb-3 flex-wrap">
            <ListPlus className="w-4 h-4 db-accent" />
            <div className="text-sm font-semibold">
              {sheets.length === 0 ? "Add your first sheets" : `Add up to ${freeLabels.length} more`}
            </div>
            <div className="flex gap-1.5">
              {freeLabels.map((l) => (
                <span key={l} className={`db-chip db-chip-${COLOR_MAP[l]}`}>{l}</span>
              ))}
            </div>
            <div className="flex-1"></div>
            <div className="text-[11px] mono" style={{ color: "var(--db-muted)" }}>
              one URL per line
            </div>
          </div>
          <textarea
            data-testid="bulk-url-textarea"
            placeholder={"https://script.google.com/macros/s/AKfycb-AAAA/exec\nhttps://script.google.com/macros/s/AKfycb-BBBB/exec\nhttps://script.google.com/macros/s/AKfycb-CCCC/exec"}
            className="db-input min-h-[140px] font-mono"
            style={{ fontFamily: "IBM Plex Mono, monospace", resize: "vertical" }}
            value={bulkText}
            onChange={(e) => setBulkText(e.target.value)}
          />

          {/* Per-line status */}
          {Object.keys(lineStates).length > 0 && (
            <div className="mt-3 space-y-1">
              {lines.filter((l) => l.trim()).map((line, i) => {
                const st = lineStates[i];
                return (
                  <div key={i} className="flex items-center gap-2 text-[11px] mono">
                    {st === "pending" && <Loader2 className="w-3 h-3 animate-spin db-accent" />}
                    {st === "ok" && <Check className="w-3 h-3 db-success" />}
                    {st && st !== "pending" && st !== "ok" && <X className="w-3 h-3 db-danger" />}
                    <span className="truncate max-w-[400px]" style={{ color: "var(--db-muted)" }}>
                      {line.slice(0, 80)}{line.length > 80 ? "…" : ""}
                    </span>
                    {st && st !== "pending" && st !== "ok" && (
                      <span className="db-danger">— {st}</span>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          <div className="flex items-center gap-3 mt-4 flex-wrap">
            <button
              data-testid="bulk-connect-button"
              onClick={onBulkConnect}
              disabled={bulkBusy || !bulkText.trim()}
              className="db-btn"
            >
              {bulkBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              {bulkBusy
                ? "Connecting…"
                : `Connect ${
                    bulkText.split(/\r?\n/).filter((l) => l.trim()).length || ""
                  } sheet${
                    bulkText.split(/\r?\n/).filter((l) => l.trim()).length === 1 ? "" : "s"
                  }`}
            </button>
            <button
              data-testid="clear-bulk-button"
              onClick={() => { setBulkText(""); setLineStates({}); }}
              disabled={bulkBusy || !bulkText.trim()}
              className="db-btn db-btn-ghost"
            >
              Clear
            </button>
          </div>
          <div className="text-[11px] mono mt-3" style={{ color: "var(--db-muted)" }}>
            Tip: each URL is a separately deployed Google Sheet. The first connected URL becomes Sheet A.
          </div>
        </div>
      )}

      {freeLabels.length === 0 && (
        <div className="db-card p-5" data-testid="max-sheets-notice">
          <div className="text-sm" style={{ color: "var(--db-muted)" }}>
            All 5 sheet slots used. Remove one to add a new URL.
          </div>
        </div>
      )}

      {/* Setup guide — collapsed by default */}
      {showGuide && (
        <div className="db-card p-6 fade-in" data-testid="setup-guide">
          <button onClick={() => setShowGuide(false)}
                  className="float-right db-btn db-btn-ghost py-1 px-2 text-xs">
            <ChevronDown className="w-3 h-3" /> Collapse
          </button>
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
            <li>7 — Paste the URL into the box above</li>
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

      {/* Next */}
      <div className="flex items-center justify-between gap-4 pt-2">
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

function ConnectedSheetCard({ s, onRefresh, onRemove }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="db-card p-4" data-testid={`sheet-row-${s.label}`}>
      <div className="flex items-center gap-3 flex-wrap">
        <span className={`db-chip db-chip-${s.color || COLOR_MAP[s.label]}`}>Sheet {s.label}</span>
        <span className="db-dot on"></span>
        <div className="text-sm font-semibold truncate max-w-[280px]">{s.name || `Sheet ${s.label}`}</div>
        <div className="db-tabular-num mono text-xs" style={{ color: "var(--db-muted)" }}>
          {s.rows} rows · {s.columns} cols
        </div>
        <div className="flex-1"></div>
        <button data-testid={`expand-sheet-${s.label}`}
                onClick={() => setExpanded((x) => !x)}
                className="db-btn db-btn-ghost py-1 px-2 text-xs">
          <ChevronDown className={`w-3.5 h-3.5 transition-transform ${expanded ? "rotate-180" : ""}`} />
          {expanded ? "Hide details" : "Details"}
        </button>
        <button data-testid={`refresh-sheet-${s.label}`} onClick={onRefresh}
                className="db-btn db-btn-ghost py-1 px-2 text-xs">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
        <button data-testid={`remove-sheet-${s.label}`} onClick={onRemove}
                className="db-btn db-btn-ghost py-1 px-2 text-xs">
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* URL line — always visible but small */}
      <div className="mt-2 text-[11px] mono break-all" style={{ color: "var(--db-muted)" }}>
        {s.url}
      </div>

      {expanded && (
        <div className="mt-3 pt-3 border-t db-divider fade-in">
          {s.last_fetched && (
            <div className="text-[11px] mono mb-2" style={{ color: "var(--db-muted)" }}>
              last fetched · {new Date(s.last_fetched).toLocaleString()}
            </div>
          )}
          {s.detected_mapping && Object.keys(s.detected_mapping).length > 0 && (
            <>
              <div className="text-[11px] mono uppercase tracking-wider mb-2"
                   style={{ color: "var(--db-muted)" }}>detected columns</div>
              <div className="flex flex-wrap gap-2 mb-3">
                {Object.entries(s.detected_mapping).map(([std, src]) => (
                  <span key={std} className="db-chip db-chip-grey">
                    <span className="db-accent">{std}</span>
                    <ChevronRight className="w-3 h-3" />
                    <span>{src}</span>
                  </span>
                ))}
              </div>
            </>
          )}
          {s.data_quality && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
              <Stat label="Total rows" value={s.data_quality.total_rows} />
              <Stat label="Missing activity"
                    value={s.data_quality.missing_per_field?.activity ?? 0}
                    warn={(s.data_quality.missing_per_field?.activity ?? 0) > 0} />
              <Stat label="Missing reason"
                    value={s.data_quality.missing_per_field?.reason ?? 0} muted />
              <Stat label="Invalid dates" value={s.data_quality.invalid_dates}
                    warn={s.data_quality.invalid_dates > 0} />
            </div>
          )}
          {s.preview && s.preview.length > 0 && (
            <div className="overflow-x-auto">
              <div className="text-[11px] mono uppercase tracking-wider mb-2"
                   style={{ color: "var(--db-muted)" }}>
                preview · first {Math.min(5, s.preview.length)} rows
              </div>
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
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, warn, muted }) {
  return (
    <div>
      <div className="text-[10px] mono uppercase tracking-wider"
           style={{ color: "var(--db-muted)" }}>{label}</div>
      <div className={`text-lg db-tabular-num mono ${warn ? "db-warning" : ""}`}>{value}</div>
    </div>
  );
}
