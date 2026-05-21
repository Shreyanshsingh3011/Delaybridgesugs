import { memo } from "react";
import { Handle, Position } from "reactflow";
import {
  Layers, Database, Cloud, Cpu, Globe, Boxes, Workflow,
  Lock, Server, MessageSquare, HardDrive, Sparkles,
} from "lucide-react";

const CAT_STYLE = {
  Application: { color: "#00aaff", icon: Layers },
  UI:          { color: "#00aaff", icon: Globe },
  Backend:     { color: "#a06bff", icon: Server },
  API:         { color: "#a06bff", icon: Workflow },
  Service:     { color: "#5bd9a8", icon: Boxes },
  Database:    { color: "#ffb265", icon: Database },
  Storage:     { color: "#ffb265", icon: HardDrive },
  Queue:       { color: "#ff8a8a", icon: MessageSquare },
  External:    { color: "#888aa3", icon: Cloud },
  AI:          { color: "#c7a5ff", icon: Sparkles },
  Auth:        { color: "#ff8a8a", icon: Lock },
  Worker:      { color: "#5bd9a8", icon: Cpu },
};

function CustomNode({ data, selected, id }) {
  const cat = data.category || "Service";
  const cfg = CAT_STYLE[cat] || CAT_STYLE.Service;
  const Icon = cfg.icon;
  const status = (data.status || "active").toLowerCase();
  const statusColor =
    status.includes("delay") || status.includes("error") ? "#ff4444"
    : status.includes("warn") ? "#ff8800"
    : status.includes("inactive") || status.includes("off") ? "#888aa3"
    : "#00cc88";

  return (
    <div
      style={{
        background: "linear-gradient(180deg, #0e0e1a 0%, #14142a 100%)",
        border: `1px solid ${selected ? cfg.color : "#1f1f3a"}`,
        boxShadow: selected
          ? `0 0 0 2px ${cfg.color}55, 0 6px 24px ${cfg.color}33`
          : "0 6px 16px rgba(0,0,0,0.35)",
        borderRadius: 14,
        minWidth: 210,
        maxWidth: 260,
        padding: "10px 12px",
        fontFamily: "IBM Plex Sans, sans-serif",
        color: "#e7e8ee",
        transition: "all .15s ease",
      }}
      data-testid={`studio-node-${id}`}
    >
      <Handle type="target" position={Position.Left}
              style={{ background: cfg.color, width: 9, height: 9 }} />
      <Handle type="source" position={Position.Right}
              style={{ background: cfg.color, width: 9, height: 9 }} />

      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div
          style={{
            width: 28, height: 28, borderRadius: 8,
            background: `${cfg.color}22`,
            border: `1px solid ${cfg.color}55`,
            display: "flex", alignItems: "center", justifyContent: "center",
            color: cfg.color,
          }}
        >
          <Icon size={15} />
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{
            fontSize: 13, fontWeight: 600, whiteSpace: "nowrap",
            overflow: "hidden", textOverflow: "ellipsis",
          }}>{data.name || id}</div>
          <div style={{
            fontSize: 10, fontFamily: "IBM Plex Mono, monospace",
            color: "#8a8aa3", textTransform: "uppercase", letterSpacing: "0.06em",
          }}>{cat}{data.type && data.type !== cat ? ` · ${data.type}` : ""}</div>
        </div>
        <div title={data.status}
             style={{ width: 8, height: 8, borderRadius: "50%", background: statusColor,
                      boxShadow: `0 0 8px ${statusColor}88` }} />
      </div>

      {(data.stage || (data.tags && data.tags.length > 0)) && (
        <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 4 }}>
          {data.stage && (
            <span style={{
              fontSize: 9, fontFamily: "IBM Plex Mono, monospace",
              padding: "2px 6px", borderRadius: 999,
              background: "rgba(255,255,255,0.05)",
              color: "#c9c9da", textTransform: "uppercase",
            }}>stage {data.stage}</span>
          )}
          {(data.tags || []).slice(0, 3).map((t, i) => (
            <span key={i} style={{
              fontSize: 9, fontFamily: "IBM Plex Mono, monospace",
              padding: "2px 6px", borderRadius: 999,
              background: `${cfg.color}15`, color: cfg.color,
            }}>{t}</span>
          ))}
        </div>
      )}
    </div>
  );
}

export default memo(CustomNode);
