import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import ReactFlow, {
  Background, Controls, MiniMap, ReactFlowProvider, MarkerType,
} from "reactflow";
import "reactflow/dist/style.css";
import { toast } from "sonner";
import { PUBLIC_BASE, formatErr } from "../api";
import { useStudio } from "../studio/store";
import CustomNode from "../studio/CustomNode";
import DependencyEdge from "../studio/CustomEdge";
import RightInspector from "../studio/RightInspector";
import TopBar from "../studio/TopBar";
import { Workflow, ExternalLink, Lock } from "lucide-react";

const nodeTypes = { custom: CustomNode };
const edgeTypes = { dependency: DependencyEdge };
const defaultEdgeOptions = {
  type: "dependency", animated: true,
  markerEnd: { type: MarkerType.ArrowClosed, color: "#00aaff" },
};

function SharedInner() {
  const { token } = useParams();
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [meta, setMeta] = useState(null);
  const {
    nodes, edges, onNodesChange, onEdgesChange, onConnect, select, setMap,
  } = useStudio();

  useEffect(() => {
    (async () => {
      setLoading(true); setErr(null);
      try {
        const url = `${PUBLIC_BASE.replace('/public','/studio/public')}/${token}`;
        const r = await fetch(url);
        if (!r.ok) {
          const j = await r.json().catch(() => ({}));
          throw new Error(formatErr(j.detail) || `HTTP ${r.status}`);
        }
        const data = await r.json();
        setMap({
          id: data.id, title: data.title,
          share_token: token, share_mode: data.share_mode,
          nodes: data.nodes || [], edges: data.edges || [],
        });
        setMeta(data);
      } catch (e) {
        setErr(e.message); toast.error(e.message);
      } finally { setLoading(false); }
    })();
    // eslint-disable-next-line
  }, [token]);

  const readonly = meta && meta.share_mode !== "editable";

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center"
           style={{ background: "#07070e" }}>
        <div className="text-sm mono" style={{ color: "#8a8aa3" }}>loading shared map…</div>
      </div>
    );
  }
  if (err) {
    return (
      <div className="min-h-screen flex items-center justify-center px-6"
           style={{ background: "#07070e" }}>
        <div className="db-card p-8 text-center max-w-md">
          <Lock className="w-8 h-8 mx-auto mb-3 db-warning" />
          <div className="text-lg font-semibold mb-2">Can't open this map</div>
          <div className="text-sm mono mb-4" style={{ color: "#8a8aa3" }}>{err}</div>
          <a href="/" className="db-btn">
            <ExternalLink className="w-3.5 h-3.5" /> Back to DelayBridge
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col" data-testid="shared-map-page"
         style={{ background: "#07070e" }}>
      <TopBar mapId={meta?.id} isShared readonly={readonly}
              onBack={null} />
      <div className="px-5 py-2 text-[11px] mono border-b db-divider"
           style={{ color: "#8a8aa3", background: "rgba(255,255,255,0.02)" }}
           data-testid="shared-banner">
        <Workflow className="inline w-3 h-3 mr-1 db-accent" />
        shared by {meta?.owner_email || "—"} · {readonly ? "read-only view" : "collaborative editing"}
      </div>
      <div className="flex-1 flex min-h-0">
        <div className="flex-1 min-w-0 relative" data-testid="shared-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={readonly ? undefined : onNodesChange}
            onEdgesChange={readonly ? undefined : onEdgesChange}
            onConnect={readonly ? undefined : onConnect}
            onNodeClick={(_, n) => select(n.id)}
            onPaneClick={() => select(null)}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            defaultEdgeOptions={defaultEdgeOptions}
            nodesDraggable={!readonly}
            nodesConnectable={!readonly}
            elementsSelectable
            fitView minZoom={0.1} maxZoom={3}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={24} size={1} color="#1f1f3a" />
            <Controls position="bottom-left"
                      style={{ background: "#0e0e1a", border: "1px solid #1f1f3a" }} />
            <MiniMap pannable zoomable
                     style={{ background: "#0e0e1a", border: "1px solid #1f1f3a" }}
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

export default function SharedMap() {
  return (
    <ReactFlowProvider>
      <SharedInner />
    </ReactFlowProvider>
  );
}
