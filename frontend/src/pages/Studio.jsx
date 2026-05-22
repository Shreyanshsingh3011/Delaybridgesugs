import { useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr } from "../api";
import { useStudio } from "../studio/store";
import { buildShareUrl, readHashState, clearHash } from "../studio/codec";
import Palette from "../studio/Palette";
import Graph from "../studio/Graph";
import EdgeList from "../studio/EdgeList";
import ColumnDependencyWizard from "../studio/ColumnDependencyWizard";
import {
  ChevronLeft, Link2, Loader2, Workflow, Copy, Check, RefreshCw,
  Share2, X, Eye, Wand2, Hand,
} from "lucide-react";

export default function Studio() {
  const nav = useNavigate();
  const {
    source, edges, groups, setSource, loadFromShare, resetAll,
  } = useStudio();

  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [authoringMode, setAuthoringMode] = useState("wizard"); // 'wizard' | 'generic'

  // Restore from URL fragment on mount
  useEffect(() => {
    const decoded = readHashState();
    if (decoded) {
      loadFromShare(decoded);
      setUrl(decoded.source?.url || "");
      toast.success("Shared dependency map loaded");
      clearHash();
    }
    // eslint-disable-next-line
  }, []);

  const shareUrl = useMemo(
    () => buildShareUrl({ source, groups, edges }),
    [source, groups, edges]
  );

  const fetchUrl = async () => {
    if (!url.trim()) { toast.error("Paste an Apps Script JSON endpoint first."); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/studio/fetch", { url: url.trim() });
      setSource({
        url: url.trim(),
        headers: data.headers || [],
        rowIds: data.rowIds || [],
        fetchedAt: new Date().toISOString(),
      });
      toast.success(`Materialised ${data.rowCount} rows × ${data.headers.length} columns`);
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || e.message);
    } finally { setBusy(false); }
  };

  const copyShare = async () => {
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true); setTimeout(() => setCopied(false), 1400);
    toast.success("Share link copied — the link IS the logic");
  };

  return (
    <div className="min-h-screen flex flex-col" data-testid="studio-page"
         style={{ background: "#07070e" }}>
      {/* TopBar */}
      <header className="px-5 py-3 border-b db-divider sticky top-0 z-30 flex items-center gap-3"
              style={{ background: "rgba(7,7,14,0.85)", backdropFilter: "blur(12px)" }}>
        <button onClick={() => nav("/")} data-testid="studio-back-button"
                className="db-btn db-btn-ghost py-1 px-2 text-xs">
          <ChevronLeft className="w-3.5 h-3.5" /> Back
        </button>
        <Workflow className="w-4 h-4 db-accent" />
        <div>
          <div className="text-sm font-semibold">Dependency Resolver</div>
          <div className="text-[10px] mono uppercase tracking-widest"
               style={{ color: "var(--db-muted)" }}>
            fetch → pick → commit → share
          </div>
        </div>
        <div className="flex-1"></div>

        {source && (
          <div className="text-[11px] mono hidden md:flex items-center gap-2"
               style={{ color: "var(--db-muted)" }}
               data-testid="studio-source-badge">
            <span className="db-dot on"></span>
            {source.rowIds.length} rows · {source.headers.length} cols
          </div>
        )}

        <button data-testid="studio-reset-button" onClick={() => { if (confirm("Reset everything?")) resetAll(); }}
                className="db-btn db-btn-ghost py-1 px-2 text-xs">
          <RefreshCw className="w-3.5 h-3.5" /> Reset
        </button>
        <button data-testid="studio-share-button" onClick={() => setShareOpen(true)}
                className="db-btn">
          <Share2 className="w-3.5 h-3.5" /> Share link
        </button>
      </header>

      {/* URL connector */}
      <div className="px-5 py-3 border-b db-divider"
           data-testid="studio-source-bar">
        <div className="flex items-center gap-2 flex-wrap">
          <Link2 className="w-3.5 h-3.5 db-accent" />
          <span className="text-[11px] mono uppercase tracking-wider"
                style={{ color: "var(--db-muted)" }}>apps script json endpoint</span>
          <input
            data-testid="studio-url-input"
            className="db-input flex-1 min-w-[300px] text-xs"
            placeholder="https://script.google.com/macros/s/AKfycb…/exec"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && fetchUrl()}
          />
          <button data-testid="studio-fetch-button" onClick={fetchUrl}
                  disabled={busy || !url.trim()}
                  className="db-btn">
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Workflow className="w-3.5 h-3.5" />}
            {busy ? "Fetching…" : "Fetch architecture data"}
          </button>
        </div>
        <div className="text-[10px] mono mt-1.5"
             style={{ color: "var(--db-muted)" }}>
          HARD FILTER: only row-indices and column-labels are persisted. Cell-level scalar values are discarded server-side.
        </div>
      </div>

      {/* Main 3-panel layout */}
      <main className="flex-1 flex gap-3 p-3 min-h-0">
        <div className="flex flex-col gap-2" style={{ width: 360 }}>
          <div className="flex gap-1" data-testid="authoring-mode-switch">
            <button
              data-testid="mode-wizard"
              onClick={() => setAuthoringMode("wizard")}
              className="db-btn db-btn-ghost py-1.5 px-2 text-[11px] flex-1 justify-center"
              style={authoringMode === "wizard"
                ? { borderColor: "rgba(0,170,255,0.5)", background: "rgba(0,170,255,0.08)", color: "#e7e8ee" }
                : {}}>
              <Wand2 className="w-3 h-3" /> Column wizard
            </button>
            <button
              data-testid="mode-generic"
              onClick={() => setAuthoringMode("generic")}
              className="db-btn db-btn-ghost py-1.5 px-2 text-[11px] flex-1 justify-center"
              style={authoringMode === "generic"
                ? { borderColor: "rgba(0,170,255,0.5)", background: "rgba(0,170,255,0.08)", color: "#e7e8ee" }
                : {}}>
              <Hand className="w-3 h-3" /> Generic builder
            </button>
          </div>
          {authoringMode === "wizard" ? <ColumnDependencyWizard /> : <Palette />}
        </div>
        <Graph />
        <EdgeList />
      </main>

      {/* Share modal */}
      {shareOpen && (
        <div className="fixed inset-0 z-40 flex items-center justify-center px-4"
             style={{ background: "rgba(7,7,14,0.6)", backdropFilter: "blur(6px)" }}
             onClick={() => setShareOpen(false)}
             data-testid="studio-share-modal">
          <div className="db-card p-6 w-full max-w-2xl"
               onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2 mb-3">
              <Share2 className="w-4 h-4 db-accent" />
              <div className="text-lg font-semibold">Shareable dependency link</div>
              <div className="flex-1"></div>
              <button onClick={() => setShareOpen(false)}
                      className="db-btn db-btn-ghost py-1 px-2 text-xs">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="text-xs mb-3" style={{ color: "var(--db-muted)" }}>
              No server persistence — the link itself encodes the full graph (source URL,
              groups, edges, cardinality metadata) as Base64URL of minified JSON. Round-trip
              fidelity is guaranteed.
            </div>
            <div className="db-link-row" data-testid="studio-share-url-row">
              <Link2 className="w-3.5 h-3.5 db-accent flex-shrink-0" />
              <input data-testid="studio-share-url" readOnly value={shareUrl} />
              <button data-testid="studio-copy-share" onClick={copyShare}
                      className="db-btn db-btn-ghost">
                {copied ? <Check className="w-3.5 h-3.5 db-success" /> : <Copy className="w-3.5 h-3.5" />}
                {copied ? "Copied" : "Copy"}
              </button>
              <a href={shareUrl} target="_blank" rel="noreferrer"
                 data-testid="studio-open-share"
                 className="db-btn db-btn-ghost">
                <Eye className="w-3.5 h-3.5" /> Open
              </a>
            </div>
            <div className="grid grid-cols-3 gap-3 mt-4">
              <Stat label="Encoded length" value={`${shareUrl.length} chars`} />
              <Stat label="Edges" value={edges.length} />
              <Stat label="Groups" value={groups.length} />
            </div>
            <details className="mt-3">
              <summary className="text-[11px] mono uppercase tracking-wider cursor-pointer"
                       style={{ color: "var(--db-muted)" }}>raw payload</summary>
              <pre className="db-code mt-2 max-h-[180px] overflow-auto"
                   data-testid="studio-share-payload">
                {JSON.stringify({ source, groups, edges }, null, 2)}
              </pre>
            </details>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="db-card p-3">
      <div className="text-[10px] mono uppercase tracking-wider"
           style={{ color: "var(--db-muted)" }}>{label}</div>
      <div className="text-sm db-tabular-num mono mt-1">{value}</div>
    </div>
  );
}
