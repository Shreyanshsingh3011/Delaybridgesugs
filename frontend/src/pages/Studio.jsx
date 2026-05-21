import { useEffect, useMemo, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import ReactFlow, {
  Background, Controls, MiniMap, ReactFlowProvider, MarkerType,
} from "reactflow";
import "reactflow/dist/style.css";
import { useStudio } from "../studio/store";
import { api, formatErr } from "../api";
import { toast } from "sonner";
import CustomNode from "../studio/CustomNode";
import DependencyEdge from "../studio/CustomEdge";
import LeftSidebar from "../studio/LeftSidebar";
import RightInspector from "../studio/RightInspector";
import TopBar from "../studio/TopBar";

const nodeTypes = { custom: CustomNode };
const edgeTypes = { dependency: DependencyEdge };
const defaultEdgeOptions = {
  type: "dependency", animated: true,
  markerEnd: { type: MarkerType.ArrowClosed, color: "#00aaff" },
};

function StudioInner() {
  const { mapId } = useParams();
  const nav = useNavigate();
  const {
    nodes, edges, onNodesChange, onEdgesChange, onConnect,
    select, setMap, filterCategory, filterType, searchTerm,
  } = useStudio();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        let id = mapId;
        if (!id) {
          // Find or create a default map
          const { data: list } = await api.get("/studio/maps");
          if (list.length > 0) {
            id = list[0].id;
          } else {
            const { data: created } = await api.post("/studio/maps", { title: "My Architecture Map" });
            id = created.id;
          }
          nav(`/studio/${id}`, { replace: true });
          return;
        }
        const { data } = await api.get(`/studio/maps/${id}`);
        if (!cancelled) setMap(data);
      } catch (e) {
        toast.error(formatErr(e.response?.data?.detail) || e.message);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line
  }, [mapId]);

  const visibleNodes = useMemo(() => {
    const term = (searchTerm || "").toLowerCase();
    return nodes.map((n) => {
      const matchesSearch = !term
        || (n.data?.name || "").toLowerCase().includes(term)
        || (n.data?.category || "").toLowerCase().includes(term);
      const matchesCat = !filterCategory || n.data?.category === filterCategory;
      return { ...n, hidden: !(matchesSearch && matchesCat) };
    });
  }, [nodes, searchTerm, filterCategory]);

  const visibleEdges = useMemo(() => {
    return edges.map((e) => ({
      ...e,
      hidden: filterType && (e.data?.type !== filterType),
    }));
  }, [edges, filterType]);

  const onNodeClick = useCallback((_, n) => select(n.id), [select]);
  const onPaneClick = useCallback(() => select(null), [select]);
  const minimapColor = useCallback((n) => {
    const cat = (n.data?.category || "").toLowerCase();
    if (cat.includes("database") || cat.includes("storage")) return "#ffb265";
    if (cat.includes("ui") || cat.includes("frontend")) return "#00aaff";
    if (cat.includes("queue")) return "#ff8a8a";
    if (cat.includes("ai")) return "#c7a5ff";
    return "#5bd9a8";
  }, []);

  return (
    <div className="h-screen flex flex-col" data-testid="studio-page" style={{ background: "#07070e" }}>
      <TopBar mapId={mapId} onBack={() => nav("/")} />
      <div className="flex-1 flex min-h-0">
        <div className="flex-shrink-0 p-3">
          <LeftSidebar />
        </div>
        <div className="flex-1 min-w-0 relative" data-testid="studio-canvas">
          <ReactFlow
            nodes={visibleNodes}
            edges={visibleEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            defaultEdgeOptions={defaultEdgeOptions}
            snapToGrid
            snapGrid={[16, 16]}
            fitView
            minZoom={0.1}
            maxZoom={3}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={24} size={1} color="#1f1f3a" />
            <Controls position="bottom-left"
                      style={{ background: "#0e0e1a", border: "1px solid #1f1f3a" }} />
            <MiniMap pannable zoomable
                     style={{ background: "#0e0e1a", border: "1px solid #1f1f3a" }}
                     nodeColor={minimapColor}
                     maskColor="rgba(7,7,14,0.6)" />
          </ReactFlow>
        </div>
        <div className="flex-shrink-0 p-3">
          <RightInspector />
        </div>
      </div>
    </div>
  );
}

export default function Studio() {
  return (
    <ReactFlowProvider>
      <StudioInner />
    </ReactFlowProvider>
  );
}
