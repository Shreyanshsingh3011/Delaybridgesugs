import { useState, useEffect } from "react";
import { toast } from "sonner";
import { api, PUBLIC_BASE, formatErr } from "../api";
import { safeCopy } from "../lib/clipboard";
import axios from "axios";
import {
  RefreshCw, Plus, Trash2, Copy, ChevronRight, Check, X,
  HelpCircle, Database, ChevronDown, Loader2, Table2,
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
  const publicToken = sessionMeta.public_token;
  const sheets = sessionMeta.sheets || [];
  const sheetsByLabel = Object.fromEntries(sheets.map((s) => [s.label, s]));
  const [showGuide, setShowGuide] = useState(false);
  // { label, sheetType } when a sheet was just connected and awaits header config
  const [pendingConfig, setPendingConfig] = useState(null);

  // Track which empty slots are revealed (visible as an input card).
  // Sheet A is always visible. B-E become visible when user clicks "+ Add Sheet X"
  // OR automatically when the prior slot is filled.
  const [revealed, setRevealed] = useState(() => new Set(["A"]));

  // Auto-reveal next empty slot when prior slot becomes connected
  useEffect(() => {
    const next = new Set(revealed);
    for (let i = 0; i < LABEL_ORDER.length; i++) {
      const L = LABEL_ORDER[i];
      if (sheetsByLabel[L]) next.add(L);  // safe to keep
      // If the previous label is connected and current is empty, reveal current
      if (i > 0) {
        const prev = LABEL_ORDER[i - 1];
        if (sheetsByLabel[prev] && !sheetsByLabel[L]) {
          next.add(L);
        }
      }
    }
    if (next.size !== revealed.size) setRevealed(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sheets.length]);

  const refreshSheet = async (label) => {
    try {
      const { data } = await api.post(`/sessions/${sessionId}/sheets/${label}/refresh`);
      toast.success(`Sheet ${label} refreshed · ${data.rows} rows`);
      await reload();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || e.message);
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

  const connectSheet = async (label, url, sheetType) => {
    await api.post(`/sessions/${sessionId}/sheets`, { url: url.trim() });
    await reload();
    setPendingConfig({ label, sheetType: sheetType || null });
  };

  const copyCode = async () => {
    const r = await safeCopy(APPS_SCRIPT_CODE);
    if (r.ok) toast.success("Apps Script code copied");
    else toast.error("Copy blocked — select the code and copy manually");
  };

  const nextEmptyLabel = LABEL_ORDER.find((L) => !sheetsByLabel[L] && !revealed.has(L));
  const totalConnected = sheets.length;

  return (
    <div className="space-y-6" data-testid="sheets-panel">
      {/* Header */}
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Connect your sheets</h2>
          <p className="text-sm mt-1" style={{ color: "var(--db-muted)" }}>
            Paste a Google Apps Script Web App URL into each sheet slot. Add 2 or more to activate variance analysis.
          </p>
        </div>
        <button data-testid="toggle-guide-button" onClick={() => setShowGuide((s) => !s)}
                className="db-btn db-btn-ghost">
          <HelpCircle className="w-4 h-4" />
          {showGuide ? "Hide guide" : "How do I get an Apps Script URL?"}
        </button>
      </div>

      {/* Counter */}
      <div className="flex items-center gap-3">
        <span className="text-[11px] mono uppercase tracking-wider"
              style={{ color: "var(--db-muted)" }}>
          {totalConnected} of 5 connected
        </span>
        <div className="flex gap-1.5">
          {LABEL_ORDER.map((L) => (
            <span key={L} className={`db-chip ${sheetsByLabel[L] ? `db-chip-${COLOR_MAP[L]}` : "db-chip-grey"}`}>
              {sheetsByLabel[L] ? <Check className="w-3 h-3" /> : null}
              {L}
            </span>
          ))}
        </div>
      </div>

      {/* Per-slot cards */}
      <div className="space-y-4">
        {LABEL_ORDER.map((L, i) => {
          const sheet = sheetsByLabel[L];
          if (pendingConfig && pendingConfig.label === L && sheet) {
            return (
              <HeaderPickerCard
                key={L}
                sheet={sheet}
                token={publicToken}
                initialType={pendingConfig.sheetType}
                onSave={async () => {
                  setPendingConfig(null);
                  await reload();
                }}
                onSkip={() => setPendingConfig(null)}
              />
            );
          }
          if (sheet) {
            return (
              <ConnectedSheetCard
                key={L}
                s={sheet}
                onRefresh={() => refreshSheet(L)}
                onRemove={() => removeSheet(L)}
              />
            );
          }
          if (revealed.has(L)) {
            return (
              <SlotInputCard
                key={L}
                label={L}
                primary={L === "A"}
                onConnect={(url, sheetType) => connectSheet(L, url, sheetType)}
                onCancel={L === "A" ? null : () => {
                  const next = new Set(revealed);
                  next.delete(L);
                  setRevealed(next);
                }}
              />
            );
          }
          return null;
        })}

        {/* "+ Add Sheet X" button when there is an unrevealed slot */}
        {nextEmptyLabel && (
          <button
            data-testid={`reveal-sheet-${nextEmptyLabel}`}
            onClick={() => setRevealed(new Set([...revealed, nextEmptyLabel]))}
            className="w-full db-card p-4 text-left transition hover:bg-white/[0.02]"
            style={{ borderStyle: "dashed" }}
          >
            <div className="flex items-center gap-3">
              <Plus className="w-4 h-4 db-accent" />
              <span className={`db-chip db-chip-${COLOR_MAP[nextEmptyLabel]}`}>Sheet {nextEmptyLabel}</span>
              <span className="text-sm font-medium">Add another sheet</span>
              <span className="text-[11px] mono" style={{ color: "var(--db-muted)" }}>
                optional · {nextEmptyLabel === "B" ? "activates variance analysis" : "extends variance"}
              </span>
            </div>
          </button>
        )}
      </div>

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
            <li>7 — Paste it into the Sheet slot above</li>
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
          {totalConnected >= 2 ? (
            <span className="db-chip db-chip-green"><Check className="w-3 h-3" /> Variance enabled · {totalConnected} sheets</span>
          ) : totalConnected === 1 ? (
            <span className="db-chip db-chip-blue">Single sheet mode · add Sheet B for variance</span>
          ) : (
            <span className="db-chip db-chip-grey"><X className="w-3 h-3" /> No sheets connected</span>
          )}
        </div>
        <button data-testid="next-to-configure-button" disabled={totalConnected === 0}
                onClick={onNext} className="db-btn">
          Configure export <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

function SlotInputCard({ label, primary, onConnect, onCancel }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [sheetType, setSheetType] = useState("");
  const [sheetTypes, setSheetTypes] = useState([]);

  useEffect(() => {
    axios.get(`${PUBLIC_BASE}/sheet-types`)
      .then((r) => setSheetTypes(r.data.types || []))
      .catch(() => {});
  }, []);

  const submit = async () => {
    if (!url.trim()) {
      toast.error("Paste an Apps Script Web App URL first.");
      return;
    }
    setBusy(true);
    try {
      await onConnect(url, sheetType || null);
      setUrl("");
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || e.message);
    } finally { setBusy(false); }
  };

  return (
    <div className="db-card p-5" data-testid={`slot-card-${label}`}>
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <span className={`db-chip db-chip-${COLOR_MAP[label]}`}>Sheet {label}</span>
        <span className="text-sm font-semibold">
          {primary ? "Primary sheet" : `Additional sheet ${label}`}
        </span>
        <span className="text-[11px] mono" style={{ color: "var(--db-muted)" }}>
          {primary ? "required" : (label === "B" ? "activates variance" : "extends variance")}
        </span>
        <div className="flex-1"></div>
        {onCancel && (
          <button onClick={onCancel} data-testid={`cancel-slot-${label}`}
                  className="db-btn db-btn-ghost py-1 px-2 text-xs">
            <X className="w-3.5 h-3.5" /> Cancel
          </button>
        )}
      </div>
      <div className="flex gap-3 flex-wrap">
        <input
          data-testid={`url-input-${label}`}
          placeholder="https://script.google.com/macros/s/AKfycb…/exec"
          className="db-input flex-1 min-w-[260px]"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          disabled={busy}
        />
        {sheetTypes.length > 0 && (
          <select
            data-testid={`type-select-${label}`}
            className="db-input"
            value={sheetType}
            onChange={(e) => setSheetType(e.target.value)}
            disabled={busy}
            style={{ minWidth: 140 }}
          >
            <option value="">Generic</option>
            {sheetTypes.map((t) => (
              <option key={t.id} value={t.label}>{t.label}</option>
            ))}
          </select>
        )}
        <button data-testid={`connect-${label}-button`} onClick={submit}
                disabled={busy || !url.trim()} className="db-btn">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          {busy ? "Connecting…" : "Connect"}
        </button>
      </div>
    </div>
  );
}


function HeaderPickerCard({ sheet, token, initialType, onSave, onSkip }) {
  const [rawData, setRawData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedRow, setSelectedRow] = useState(null);
  const [dropEmpty, setDropEmpty] = useState(false);
  const [sheetType, setSheetType] = useState(initialType || "");
  const [sheetTypes, setSheetTypes] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([
      axios.get(`${PUBLIC_BASE}/${token}/raw-head?sheet=${sheet.label}&rows=12`),
      axios.get(`${PUBLIC_BASE}/sheet-types`),
    ]).then(([rawRes, typesRes]) => {
      const d = rawRes.data;
      setRawData(d);
      setSelectedRow(d.suggested_header_row ?? 0);
      if (!initialType && d.suggested_type) setSheetType(d.suggested_type);
      setSheetTypes(typesRes.data.types || []);
    }).catch(() => {
      toast.error("Could not load raw sheet data.");
    }).finally(() => setLoading(false));
  }, [token, sheet.label]);

  const previewHeaders = () => {
    if (!rawData || selectedRow == null) return [];
    const row = rawData.raw_rows[selectedRow] || [];
    return row.map((v, i) => {
      const s = String(v ?? "").trim();
      if (!s) return dropEmpty ? null : `Column ${i + 1}`;
      return s;
    }).filter(Boolean);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.post(`${PUBLIC_BASE}/${token}/header-mapping`, {
        sheet_label: sheet.label,
        header_row_index: selectedRow,
        drop_empty_named: dropEmpty,
        sheet_type: sheetType || null,
      });
      toast.success(`Header row saved for Sheet ${sheet.label}`);
      await onSave();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || e.message);
    } finally { setSaving(false); }
  };

  if (loading) {
    return (
      <div className="db-card p-5 fade-in" data-testid={`header-picker-${sheet.label}`}>
        <div className="flex items-center gap-3">
          <span className={`db-chip db-chip-${COLOR_MAP[sheet.label]}`}>Sheet {sheet.label}</span>
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-sm" style={{ color: "var(--db-muted)" }}>Loading raw data…</span>
        </div>
      </div>
    );
  }

  const headers = previewHeaders();

  return (
    <div className="db-card p-5 fade-in" data-testid={`header-picker-${sheet.label}`}>
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <span className={`db-chip db-chip-${COLOR_MAP[sheet.label]}`}>Sheet {sheet.label}</span>
        <Table2 className="w-4 h-4 db-accent" />
        <span className="text-sm font-semibold">Pick header row</span>
        <span className="text-[11px] mono" style={{ color: "var(--db-muted)" }}>
          click the row that contains column names
        </span>
        <div className="flex-1" />
        <button onClick={onSkip} className="db-btn db-btn-ghost py-1 px-2 text-xs">
          <X className="w-3.5 h-3.5" /> Skip
        </button>
      </div>

      {/* Type selector */}
      {sheetTypes.length > 0 && (
        <div className="flex items-center gap-3 mb-4">
          <span className="text-[11px] mono uppercase tracking-wider" style={{ color: "var(--db-muted)" }}>Sheet type</span>
          <select
            className="db-input"
            value={sheetType}
            onChange={(e) => setSheetType(e.target.value)}
            style={{ minWidth: 160 }}
          >
            <option value="">Generic</option>
            {sheetTypes.map((t) => (
              <option key={t.id} value={t.label}>{t.label}</option>
            ))}
          </select>
          {rawData?.suggested_type && (
            <span className="text-[11px] mono db-accent">suggested: {rawData.suggested_type}</span>
          )}
        </div>
      )}

      {/* Raw grid */}
      {rawData && rawData.raw_rows.length > 0 ? (
        <div className="overflow-x-auto mb-4">
          <table className="text-[11px] mono w-full">
            <tbody>
              {rawData.raw_rows.map((row, ri) => (
                <tr
                  key={ri}
                  onClick={() => setSelectedRow(ri)}
                  className={`cursor-pointer border-t db-divider transition-colors ${
                    selectedRow === ri
                      ? "bg-[var(--db-accent)]/10 outline outline-1 outline-[var(--db-accent)]"
                      : "hover:bg-white/[0.03]"
                  }`}
                >
                  <td className="py-1 pr-2 w-6 text-right" style={{ color: "var(--db-muted)" }}>
                    {selectedRow === ri
                      ? <Check className="w-3 h-3 db-accent inline" />
                      : <span>{ri}</span>}
                  </td>
                  {row.slice(0, 8).map((cell, ci) => (
                    <td key={ci} className="py-1 pr-3 truncate max-w-[160px]">
                      {String(cell ?? "").slice(0, 40) || <span style={{ color: "var(--db-muted)" }}>—</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-sm mb-4" style={{ color: "var(--db-muted)" }}>No rows available.</div>
      )}

      {/* Preview headers */}
      {headers.length > 0 && (
        <div className="mb-4">
          <div className="text-[11px] mono uppercase tracking-wider mb-2" style={{ color: "var(--db-muted)" }}>
            column names preview
          </div>
          <div className="flex flex-wrap gap-2">
            {headers.slice(0, 12).map((h, i) => (
              <span key={i} className="db-chip db-chip-grey">{h}</span>
            ))}
            {headers.length > 12 && (
              <span className="db-chip db-chip-grey">+{headers.length - 12} more</span>
            )}
          </div>
        </div>
      )}

      {/* Options */}
      <div className="flex items-center gap-4 mb-4">
        <label className="flex items-center gap-2 cursor-pointer text-xs">
          <input
            type="checkbox"
            checked={dropEmpty}
            onChange={(e) => setDropEmpty(e.target.checked)}
            className="rounded"
          />
          <span style={{ color: "var(--db-muted)" }}>Drop columns with blank header</span>
        </label>
      </div>

      {/* Actions */}
      <div className="flex gap-3">
        <button onClick={handleSave} disabled={saving || selectedRow == null} className="db-btn">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
          {saving ? "Saving…" : "Save header mapping"}
        </button>
        <button onClick={onSkip} className="db-btn db-btn-ghost">
          Use default
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
