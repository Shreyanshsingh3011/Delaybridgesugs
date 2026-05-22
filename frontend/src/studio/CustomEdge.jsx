import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath } from "reactflow";

const CARD_COLOR = {
  "1:1": "#00aaff",
  "1:N": "#5bd9a8",
  "N:1": "#ffb265",
  "N:N": "#c7a5ff",
};

export default function DependencyEdge(props) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition,
          data, label, selected, markerEnd } = props;
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, borderRadius: 14,
  });
  const card = data?.cardinality || "1:1";
  const color = CARD_COLOR[card] || "#00aaff";
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
        }}
      />
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
            display: "flex", gap: 6, alignItems: "center",
          }}
          className="nodrag nopan"
        >
          <strong>{card}</strong>
          {label && <span style={{ opacity: 0.85 }}>· {label}</span>}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
