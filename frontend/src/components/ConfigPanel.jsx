import { useMemo } from "react";
import { ChevronLeft, ChevronRight, Play, Save, Activity, Zap } from "lucide-react";

const FIELD_GROUPS = [
  {
    name: "Overview",
    icon: Activity,
    fields: [
      { key: "summary", label: "Summary text", hint: "Short human-readable summary line" },
      { key: "totals", label: "Totals", hint: "rows, delayed, blocked, completed, at_risk" },
      { key: "risk_score", label: "Risk score", hint: "0–100 composite risk indicator" },
      { key: "status_breakdown", label: "Status breakdown", hint: "Counts per status" },
      { key: "sheets", label: "Sheets metadata", hint: "Labels, colors, last_fetched" },
    ],
  },
  {
    name: "Delay analysis",
    icon: Zap,
    fields: [
      { key: "top_delay_reasons", label: "Top delay reasons", hint: "Most frequent reason classes" },
      { key: "correlation_matrix", label: "Reason correlation matrix", hint: "Reason × reason co-occurrence heatmap" },
      { key: "dependency_chains", label: "Dependency chains", hint: "Chains, critical path, at-risk activities" },
      { key: "person_ranking", label: "Person ranking", hint: "Top delaying people with reason mix" },
      { key: "department_ranking", label: "Department ranking", hint: "Delays grouped by stage/dept" },
      { key: "timeline_correlation", label: "Timeline correlation", hint: "Delays by week + month" },
      { key: "tat_performance", label: "TAT performance (single-sheet)", hint: "Planned vs actual; null when 2+ sheets" },
    ],
  },
  {
    name: "Variance (multi-sheet)",
    icon: Activity,
    fields: [
      { key: "variance", label: "Variance analysis", hint: "Rows, conflicts, outliers, reliability, consensus, correlations", multiOnly: true },
    ],
  },
  {
    name: "Flags",
    icon: Zap,
    fields: [
      { key: "flags", label: "Flags array", hint: "Auto-generated delay + variance flags with downstream people" },
    ],
  },
  {
    name: "Dynamic dashboard & AI",
    icon: Activity,
    fields: [
      { key: "data_dashboard", label: "Sheet data dashboard", hint: "Auto KPIs, charts & a data table built from your raw sheet rows" },
      { key: "copilot", label: "Sheet copilot (AI Q&A)", hint: "Ask questions in plain language; answered from exact aggregates of your sheet" },
      { key: "data_quality", label: "Data-quality audit", hint: "Missing values, duplicates, casing issues, subtotal rows, type mismatches + score" },
      { key: "pivot", label: "Pivot & segmentation", hint: "Group any dimension by sum/avg/count of any measure (excludes total rows)" },
    ],
  },
];

export default function ConfigPanel({
  sessionMeta, exportFields, setExportFields, isMulti, hasAnalysis,
  onAnalyze, onSaveFields, onNext, onBack, analysisSummary,
}) {
  const all = useMemo(() => FIELD_GROUPS.flatMap((g) => g.fields.map((f) => f.key)), []);
  const toggle = (key) => {
    const next = exportFields.includes(key)
      ? exportFields.filter((k) => k !== key)
      : [...exportFields, key];
    setExportFields(next);
  };
  const selectAll = () => { setExportFields(all); onSaveFields(all); };
  const clearAll = () => { setExportFields([]); onSaveFields([]); };
  const saveAndContinue = async () => { await onSaveFields(exportFields); onNext(); };

  return (
    <div className="space-y-6" data-testid="config-panel">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Configure your export</h2>
          <p className="text-sm mt-1" style={{ color: "var(--db-muted)" }}>
            Pick the fields you want exposed in your public link. Each toggle adds a key to the JSON.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button data-testid="select-all-button" onClick={selectAll} className="db-btn db-btn-ghost">
            Select all
          </button>
          <button data-testid="clear-all-button" onClick={clearAll} className="db-btn db-btn-ghost">
            Clear
          </button>
          <button data-testid="run-analysis-button" onClick={onAnalyze} className="db-btn">
            <Play className="w-4 h-4" /> Run analysis
          </button>
        </div>
      </div>

      {/* Analysis result summary */}
      {hasAnalysis && analysisSummary && (
        <div className="db-card p-5" data-testid="analysis-summary-card">
          <div className="text-[11px] mono uppercase tracking-wider mb-2"
               style={{ color: "var(--db-muted)" }}>
            latest analysis · {sessionMeta.sheets.length} sheets
          </div>
          <div className="text-sm">{analysisSummary.summary || analysisSummary}</div>
          {analysisSummary.risk_score != null && (
            <div className="mt-3 flex items-center gap-6 flex-wrap">
              <Stat big label="Risk score" value={analysisSummary.risk_score}
                    color={analysisSummary.risk_score >= 70 ? "danger"
                           : analysisSummary.risk_score >= 40 ? "warning" : "success"} />
              {analysisSummary.totals && (
                <>
                  <Stat label="Rows" value={analysisSummary.totals.rows} />
                  <Stat label="Delayed" value={analysisSummary.totals.delayed} color="warning" />
                  <Stat label="Blocked" value={analysisSummary.totals.blocked} color="danger" />
                  <Stat label="Completed" value={analysisSummary.totals.completed} color="success" />
                </>
              )}
              {analysisSummary.flags_count != null && (
                <Stat label="Flags" value={analysisSummary.flags_count} />
              )}
              {analysisSummary.mode && (
                <span className={`db-chip ${
                  analysisSummary.mode === "multi-sheet" ? "db-chip-green" : "db-chip-blue"
                }`}>
                  {analysisSummary.mode}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {!hasAnalysis && (
        <div className="db-card p-5" data-testid="no-analysis-hint">
          <div className="text-sm" style={{ color: "var(--db-muted)" }}>
            Click <span className="db-accent">Run analysis</span> first to compute results
            for the connected sheets. You can adjust the field selection here and re-run
            at any time.
          </div>
        </div>
      )}

      {/* Field groups */}
      <div className="grid md:grid-cols-2 gap-4">
        {FIELD_GROUPS.map((g) => (
          <div key={g.name} className="db-card p-5">
            <div className="flex items-center gap-2 mb-3">
              <g.icon className="w-4 h-4 db-accent" />
              <div className="text-sm font-semibold">{g.name}</div>
            </div>
            <div className="space-y-2">
              {g.fields.map((f) => {
                const checked = exportFields.includes(f.key);
                const disabled = f.multiOnly && !isMulti;
                return (
                  <label key={f.key}
                         data-testid={`field-toggle-${f.key}`}
                         className={`db-toggle-row ${checked ? "checked" : ""} ${disabled ? "opacity-40 pointer-events-none" : ""}`}>
                    <div>
                      <div className="text-sm font-medium">{f.label}</div>
                      <div className="text-[11px] mono" style={{ color: "var(--db-muted)" }}>
                        {f.hint}{disabled ? " · requires 2+ sheets" : ""}
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      className="accent-[#00aaff] w-4 h-4"
                      checked={checked}
                      disabled={disabled}
                      onChange={() => toggle(f.key)}
                    />
                  </label>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Selected fields tray */}
      <div className="db-card p-4">
        <div className="text-[11px] mono uppercase tracking-wider mb-2"
             style={{ color: "var(--db-muted)" }}>
          fields selected ({exportFields.length})
        </div>
        <div className="flex flex-wrap gap-2">
          {exportFields.length === 0 && (
            <span className="text-xs mono" style={{ color: "var(--db-muted)" }}>
              none — your export will return all standard fields
            </span>
          )}
          {exportFields.map((f) => (
            <span key={f} className="db-chip db-chip-blue">{f}</span>
          ))}
        </div>
      </div>

      {/* Nav */}
      <div className="flex items-center justify-between gap-4 pt-2">
        <button data-testid="back-to-sheets-button" onClick={onBack} className="db-btn db-btn-ghost">
          <ChevronLeft className="w-4 h-4" /> Sheets
        </button>
        <div className="flex items-center gap-3">
          <button data-testid="save-fields-button" onClick={() => onSaveFields(exportFields)}
                  className="db-btn db-btn-ghost">
            <Save className="w-4 h-4" /> Save selection
          </button>
          <button data-testid="next-to-export-button" disabled={!hasAnalysis}
                  onClick={saveAndContinue} className="db-btn">
            Get export link <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, big, color }) {
  const cls = color === "danger" ? "db-danger" : color === "warning" ? "db-warning" : color === "success" ? "db-success" : "";
  return (
    <div>
      <div className="text-[10px] mono uppercase tracking-wider"
           style={{ color: "var(--db-muted)" }}>{label}</div>
      <div className={`db-tabular-num mono ${big ? "text-3xl" : "text-lg"} ${cls}`}>{value}</div>
    </div>
  );
}
