import { useState } from "react";
import { toast } from "sonner";
import { useReactFlow } from "reactflow";
import { toPng, toSvg } from "html-to-image";
import { api, formatErr, PUBLIC_BASE } from "../api";
import { useStudio } from "./store";
import { autoLayout, forceLayout } from "./autolayout";
import {
  Save, Share2, Download, Sparkles, ZoomIn, ZoomOut, Maximize2,
  Workflow, ChevronLeft, Globe2, Lock, Eye, Edit3, ArrowDownToLine,
  Copy, Check,
} from "lucide-react";

export default function TopBar({ mapId, onBack, isShared, readonly }) {
  const rf = useReactFlow();
  const {
    title, setTitle, nodes, edges, dirty, shareToken, shareMode, clearDirty,
    setNodes,
  } = useStudio();
  const [busy, setBusy] = useState(false);
  const [showShare, setShowShare] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const [copied, setCopied] = useState(false);

  const onSave = async () => {
    if (!mapId) return;
    setBusy(true);
    try {
      if (isShared) {
        await fetch(`${PUBLIC_BASE.replace('/public','/studio/public')}/${shareToken}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, nodes, edges }),
        }).then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); });
      } else {
        await api.put(`/studio/maps/${mapId}`, { title, nodes, edges });
      }
      clearDirty();
      toast.success("Map saved");
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || e.message);
    } finally { setBusy(false); }
  };

  const onAutoArrange = (dir) => {
    const next = dir === "force" ? forceLayout(nodes, edges) : autoLayout(nodes, edges, dir);
    setNodes(next);
    setTimeout(() => rf.fitView({ padding: 0.2, duration: 400 }), 100);
    toast.success(`Auto-arranged · ${dir}`);
  };

  const findElement = () => document.querySelector(".react-flow__viewport")?.parentElement?.parentElement;

  const exportPng = async () => {
    const el = findElement();
    if (!el) return;
    rf.fitView({ padding: 0.1 });
    setTimeout(async () => {
      try {
        const url = await toPng(el, { pixelRatio: 2, backgroundColor: "#07070e" });
        downloadDataUrl(url, `${(title || "map").replace(/\s+/g, "-")}.png`);
        toast.success("PNG exported");
      } catch (e) { toast.error(e.message); }
    }, 200);
  };
  const exportSvg = async () => {
    const el = findElement();
    if (!el) return;
    rf.fitView({ padding: 0.1 });
    setTimeout(async () => {
      try {
        const url = await toSvg(el, { backgroundColor: "#07070e" });
        downloadDataUrl(url, `${(title || "map").replace(/\s+/g, "-")}.svg`);
        toast.success("SVG exported");
      } catch (e) { toast.error(e.message); }
    }, 200);
  };
  const exportJson = () => {
    const data = JSON.stringify({ title, nodes, edges,
      metadata: { exported_at: new Date().toISOString() } }, null, 2);
    const blob = new Blob([data], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    downloadDataUrl(url, `${(title || "map").replace(/\s+/g, "-")}.json`);
    setTimeout(() => URL.revokeObjectURL(url), 500);
    toast.success("JSON exported");
  };

  const setShareMode = async (mode) => {
    if (!mapId) return;
    try {
      const { data } = await api.post(`/studio/maps/${mapId}/share`, { mode });
      useStudio.setState({ shareMode: data.share_mode, shareToken: data.share_token });
      toast.success(`Share mode: ${mode}`);
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || e.message);
    }
  };

  const shareUrl = shareToken
    ? `${window.location.origin}/studio/share/${shareToken}`
    : "";

  const copyShare = async () => {
    if (!shareUrl) return;
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true); setTimeout(() => setCopied(false), 1400);
    toast.success("Share link copied");
  };

  return (
    <div className="flex items-center gap-3 px-5 py-3 border-b db-divider sticky top-0 z-30"
         style={{ background: "rgba(7,7,14,0.85)", backdropFilter: "blur(12px)" }}
         data-testid="studio-topbar">
      {onBack && (
        <button onClick={onBack} className="db-btn db-btn-ghost py-1 px-2 text-xs"
                data-testid="studio-back-button">
          <ChevronLeft className="w-3.5 h-3.5" /> Back
        </button>
      )}
      <Workflow className="w-4 h-4 db-accent" />
      <input
        data-testid="studio-title-input"
        className="bg-transparent border-0 outline-none text-base font-semibold flex-1 min-w-[160px] max-w-[400px]"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        readOnly={readonly}
      />
      <span className="text-[10px] mono uppercase tracking-wider"
            style={{ color: dirty ? "#ffb265" : "var(--db-muted)" }}>
        {readonly ? "read-only" : dirty ? "unsaved" : "saved"}
      </span>

      <div className="flex-1"></div>

      <button onClick={() => rf.zoomIn()} className="db-btn db-btn-ghost py-1 px-2 text-xs"
              title="Zoom in" data-testid="studio-zoom-in"><ZoomIn className="w-3.5 h-3.5" /></button>
      <button onClick={() => rf.zoomOut()} className="db-btn db-btn-ghost py-1 px-2 text-xs"
              title="Zoom out" data-testid="studio-zoom-out"><ZoomOut className="w-3.5 h-3.5" /></button>
      <button onClick={() => rf.fitView({ padding: 0.2 })}
              className="db-btn db-btn-ghost py-1 px-2 text-xs"
              title="Fit" data-testid="studio-fit"><Maximize2 className="w-3.5 h-3.5" /></button>

      <div className="border-l db-divider h-6 mx-1"></div>

      <div className="relative">
        <button onClick={() => setShowShare((s) => !s)}
                className="db-btn db-btn-ghost py-1 px-2 text-xs"
                data-testid="studio-arrange-button">
          <Sparkles className="w-3.5 h-3.5" /> Auto-arrange
        </button>
        {showShare && false && null}
      </div>
      <button onClick={() => onAutoArrange("LR")}
              className="db-btn db-btn-ghost py-1 px-2 text-xs"
              data-testid="studio-arrange-lr">LR</button>
      <button onClick={() => onAutoArrange("TB")}
              className="db-btn db-btn-ghost py-1 px-2 text-xs"
              data-testid="studio-arrange-tb">TB</button>
      <button onClick={() => onAutoArrange("force")}
              className="db-btn db-btn-ghost py-1 px-2 text-xs"
              data-testid="studio-arrange-force">Force</button>

      <div className="border-l db-divider h-6 mx-1"></div>

      <div className="relative">
        <button
          onClick={() => setShowExport((s) => !s)}
          className="db-btn db-btn-ghost py-1 px-2 text-xs"
          data-testid="studio-export-button"
        >
          <Download className="w-3.5 h-3.5" /> Export
        </button>
        {showExport && (
          <div className="absolute right-0 top-full mt-1 db-card p-1 z-50 w-32"
               data-testid="studio-export-menu">
            <button data-testid="studio-export-png" onClick={() => { setShowExport(false); exportPng(); }}
                    className="w-full text-left text-xs py-1.5 px-2 hover:bg-white/5 rounded">PNG</button>
            <button data-testid="studio-export-svg" onClick={() => { setShowExport(false); exportSvg(); }}
                    className="w-full text-left text-xs py-1.5 px-2 hover:bg-white/5 rounded">SVG</button>
            <button data-testid="studio-export-json" onClick={() => { setShowExport(false); exportJson(); }}
                    className="w-full text-left text-xs py-1.5 px-2 hover:bg-white/5 rounded">JSON</button>
          </div>
        )}
      </div>

      {!isShared && (
        <div className="relative">
          <button onClick={() => setShowShare((s) => !s)}
                  className="db-btn db-btn-ghost py-1 px-2 text-xs"
                  data-testid="studio-share-button">
            <Share2 className="w-3.5 h-3.5" /> Share
          </button>
          {showShare && (
            <div className="absolute right-0 top-full mt-2 db-card p-3 z-50 w-80"
                 data-testid="studio-share-panel">
              <div className="text-xs mono uppercase tracking-wider mb-2"
                   style={{ color: "var(--db-muted)" }}>share mode</div>
              <div className="grid grid-cols-2 gap-1.5 mb-3">
                <ModeButton active={shareMode === "private"} onClick={() => setShareMode("private")}
                            icon={Lock} label="Private" testid="studio-share-private" />
                <ModeButton active={shareMode === "public"} onClick={() => setShareMode("public")}
                            icon={Globe2} label="Public" testid="studio-share-public" />
                <ModeButton active={shareMode === "readonly"} onClick={() => setShareMode("readonly")}
                            icon={Eye} label="Read-only" testid="studio-share-readonly" />
                <ModeButton active={shareMode === "editable"} onClick={() => setShareMode("editable")}
                            icon={Edit3} label="Editable" testid="studio-share-editable" />
              </div>
              {shareMode !== "private" && shareUrl && (
                <>
                  <div className="text-xs mono uppercase tracking-wider mb-1"
                       style={{ color: "var(--db-muted)" }}>shareable url</div>
                  <div className="db-link-row" data-testid="studio-share-url-row">
                    <input readOnly value={shareUrl} />
                    <button onClick={copyShare}
                            data-testid="studio-copy-share"
                            className="db-btn db-btn-ghost py-1 px-2 text-xs">
                      {copied ? <Check className="w-3 h-3 db-success" /> : <Copy className="w-3 h-3" />}
                    </button>
                  </div>
                </>
              )}
              {shareMode === "private" && (
                <div className="text-[11px] mono" style={{ color: "var(--db-muted)" }}>
                  Map is private. Switch to Public / Read-only / Editable to share.
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {!readonly && (
        <button onClick={onSave} disabled={busy} className="db-btn"
                data-testid="studio-save-button">
          {busy ? <ArrowDownToLine className="w-3.5 h-3.5 animate-pulse" /> : <Save className="w-3.5 h-3.5" />}
          {busy ? "Saving…" : "Save"}
        </button>
      )}
    </div>
  );
}

function ModeButton({ active, onClick, icon: Icon, label, testid }) {
  return (
    <button
      data-testid={testid}
      onClick={onClick}
      className="db-btn db-btn-ghost py-1.5 px-2 text-xs justify-center"
      style={active ? { borderColor: "rgba(0,170,255,0.6)", background: "rgba(0,170,255,0.08)" } : {}}
    >
      <Icon className="w-3 h-3" /> {label}
    </button>
  );
}

function downloadDataUrl(url, filename) {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}
