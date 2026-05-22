import { memo } from "react";
import { Handle, Position } from "reactflow";
import { Rows3, Columns3, Layers, Hash } from "lucide-react";

const STYLE = {
  row:   { color: "#00aaff", icon: Rows3,    label: "ROW" },
  col:   { color: "#ffb265", icon: Columns3, label: "COL" },
  group: { color: "#c7a5ff", icon: Layers,   label: "GROUP" },
};

function StudioNode({ data, selected, id }) {
  const cfg = STYLE[data.kind] || STYLE.row;
  const Icon = cfg.icon;
  return (
    <div
      data-testid={`graph-node-${id}`}
      style={{
        background: "linear-gradient(180deg, #0e0e1a 0%, #14142a 100%)",
        border: `1px solid ${selected ? cfg.color : "#1f1f3a"}`,
        boxShadow: selected
          ? `0 0 0 2px ${cfg.color}55, 0 6px 24px ${cfg.color}33`
          : "0 4px 14px rgba(0,0,0,0.35)",
        borderRadius: 12,
        minWidth: 150,
        maxWidth: 220,
        padding: "8px 10px",
        fontFamily: "IBM Plex Mono, monospace",
        color: "#e7e8ee",
      }}
    >
      <Handle type="target" position={Position.Left}
              style={{ background: cfg.color, width: 8, height: 8 }} />
      <Handle type="source" position={Position.Right}
              style={{ background: cfg.color, width: 8, height: 8 }} />

      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div
          style={{
            width: 22, height: 22, borderRadius: 6,
            background: `${cfg.color}22`,
            border: `1px solid ${cfg.color}55`,
            display: "flex", alignItems: "center", justifyContent: "center",
            color: cfg.color, flexShrink: 0,
          }}
        >
          <Icon size={12} />
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{
            fontSize: 11, fontWeight: 600,
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>{data.label}</div>
          <div style={{
            fontSize: 9, color: "#8a8aa3",
            textTransform: "uppercase", letterSpacing: "0.06em",
          }}>
            {cfg.label}{data.memberCount ? ` · ${data.memberCount}` : ""}
          </div>
        </div>
        {data.kind === "group" && (
          <Hash size={11} style={{ color: "#8a8aa3" }} />
        )}
      </div>
    </div>
  );
}

export default memo(StudioNode);
