import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath } from "reactflow";

const TYPE_COLOR = {
  Required: "#00aaff", Optional: "#888aa3", Direct: "#00aaff",
  Indirect: "#a06bff", Runtime: "#5bd9a8", "Build-time": "#ffb265",
  API: "#a06bff", Database: "#ffb265", "Event-driven": "#c7a5ff",
  Shared: "#5bd9a8", Sequential: "#00aaff", Blocking: "#ff4444",
};

export default function DependencyEdge(props) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition,
          data, label, selected, markerEnd } = props;
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, borderRadius: 14,
  });
  const t = (data?.type) || "Required";
  const color = TYPE_COLOR[t] || "#00aaff";
  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: color,
          strokeWidth: selected ? 2.4 : 1.6,
          opacity: selected ? 1 : 0.85,
          strokeDasharray: t === "Optional" ? "6 4" : undefined,
        }}
      />
      {(label || t) && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              background: "#0e0e1a",
              border: `1px solid ${color}66`,
              color,
              padding: "2px 8px",
              borderRadius: 999,
              fontFamily: "IBM Plex Mono, monospace",
              fontSize: 10,
              letterSpacing: "0.04em",
              pointerEvents: "all",
              textTransform: "uppercase",
            }}
            className="nodrag nopan"
          >
            {label || t}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
