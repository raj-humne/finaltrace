import { useEffect, useLayoutEffect, useMemo, useRef, useState, useCallback } from "react";
import ForceGraph2D, { type NodeObject, type LinkObject, type ForceGraphMethods } from "react-force-graph-2d";
import { SOURCE_SHAPES, emberForRisk, type EventSource } from "@/lib/design";
import { cn, parseApiTimestamp } from "@/lib/utils";
import type { components } from "@/lib/api/types.gen";

type NodeDatum = components["schemas"]["GraphNodeOut"];
type LinkDatum = components["schemas"]["GraphEdgeOut"];
type FGNode = NodeObject<NodeDatum>;
type FGLink = LinkObject<NodeDatum, LinkDatum>;

interface CorrelationGraphProps {
  nodes: NodeDatum[];
  edges: LinkDatum[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  overDense?: boolean;
}

function endpointId(end: FGLink["source"]): string | undefined {
  if (end == null) return undefined;
  return typeof end === "object" ? String((end as FGNode).id) : String(end);
}

function drawShape(ctx: CanvasRenderingContext2D, shape: string, x: number, y: number, r: number) {
  ctx.beginPath();
  switch (shape) {
    case "diamond":
      ctx.moveTo(x, y - r);
      ctx.lineTo(x + r, y);
      ctx.lineTo(x, y + r);
      ctx.lineTo(x - r, y);
      ctx.closePath();
      break;
    case "square":
      ctx.rect(x - r * 0.85, y - r * 0.85, r * 1.7, r * 1.7);
      break;
    case "triangle":
      ctx.moveTo(x, y - r);
      ctx.lineTo(x + r * 0.95, y + r * 0.75);
      ctx.lineTo(x - r * 0.95, y + r * 0.75);
      ctx.closePath();
      break;
    case "hexagon": {
      for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 3) * i - Math.PI / 2;
        const px = x + r * Math.cos(angle);
        const py = y + r * Math.sin(angle);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.closePath();
      break;
    }
    default:
      ctx.arc(x, y, r, 0, 2 * Math.PI);
  }
}

export function CorrelationGraph({ nodes, edges, selectedId, onSelect, overDense }: CorrelationGraphProps) {
  const [layout, setLayout] = useState<"temporal" | "force">("temporal");
  const [hoverId, setHoverId] = useState<string | null>(null);
  const fgRef = useRef<ForceGraphMethods<NodeDatum, LinkDatum> | undefined>(undefined);

  // react-force-graph-2d's own auto-sizing occasionally falls back to
  // window dimensions instead of the container's (observed: canvas sized to
  // the full viewport inside an h-80 box). Measuring the container directly
  // and passing explicit width/height sidesteps that entirely.
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setSize({ width: Math.round(width), height: Math.round(height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const { graphData, tMin, tSpan } = useMemo(() => {
    const times = nodes.map((n) => (n.ts ? parseApiTimestamp(n.ts).getTime() : 0));
    const tMin = Math.min(...times);
    const tMax = Math.max(...times);
    const tSpan = Math.max(1, tMax - tMin);
    return {
      graphData: { nodes: nodes.map((n) => ({ ...n })) as FGNode[], links: edges.map((e) => ({ ...e })) as unknown as FGLink[] },
      tMin,
      tSpan,
    };
  }, [nodes, edges]);

  const activeId = hoverId ?? selectedId;
  const neighborIds = useMemo(() => {
    if (!activeId) return new Set<string>();
    const s = new Set<string>();
    for (const e of edges) {
      if (e.source === activeId) s.add(e.target!);
      if (e.target === activeId) s.add(e.source!);
    }
    return s;
  }, [activeId, edges]);

  const pinTemporalPositions = useCallback(() => {
    const w = size.width || 800;
    const h = size.height || 320;
    graphData.nodes.forEach((n) => {
      const t = n.ts ? parseApiTimestamp(n.ts).getTime() : 0;
      n.fx = 24 + ((t - tMin) / tSpan) * Math.max(1, w - 48);
      n.fy = Math.min(h - 24, 32 + (n.stage ?? 0) * 22);
    });
  }, [graphData, tMin, tSpan, size.width, size.height]);

  // Bootstrap fixed positions once per dataset so the graph opens in
  // temporal mode without waiting on a user click or an engine-stop event
  // (calling d3ReheatSimulation from onEngineStop would just re-trigger
  // itself in a loop, since cooldownTicks is 0 in temporal mode). Fixed
  // positions are plain pixel coordinates, but the camera doesn't know to
  // frame them on its own — zoomToFit is required or the view stays at its
  // default centered-on-origin state and every node renders off-screen.
  useEffect(() => {
    if (layout !== "temporal" || !size.width) return;
    pinTemporalPositions();
    const t = setTimeout(() => fgRef.current?.zoomToFit(0, 24), 0);
    return () => clearTimeout(t);
  }, [graphData, layout, pinTemporalPositions, size.width]);

  const applyLayout = useCallback(
    (mode: "temporal" | "force") => {
      setLayout(mode);
      const fg = fgRef.current;
      if (!fg) return;
      if (mode === "temporal") {
        pinTemporalPositions();
        setTimeout(() => fg.zoomToFit(300, 24), 0);
      } else {
        graphData.nodes.forEach((n) => {
          n.fx = undefined;
          n.fy = undefined;
        });
        fg.d3ReheatSimulation();
        // Without this the camera stays framed on the previous (temporal)
        // layout's tight bounding box - the force simulation spreads nodes
        // out over its cooldownTicks, but nothing ever re-frames the view to
        // follow them, so only whatever corner they started in stays visible.
        // cooldownTicks is 100 in force mode; give it a beat to settle first.
        setTimeout(() => fg.zoomToFit(300, 24), 300);
      }
    },
    [graphData, pinTemporalPositions]
  );

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="flex gap-1 text-xs">
          <button
            onClick={() => applyLayout("temporal")}
            className={cn("rounded-md border px-2 py-1", layout === "temporal" ? "border-(--color-ink) bg-(--color-surface)" : "border-(--color-hairline) text-(--color-ink-muted)")}
          >
            time
          </button>
          <button
            onClick={() => applyLayout("force")}
            className={cn("rounded-md border px-2 py-1", layout === "force" ? "border-(--color-ink) bg-(--color-surface)" : "border-(--color-hairline) text-(--color-ink-muted)")}
          >
            force
          </button>
        </div>
        <span className="text-xs text-(--color-ink-muted)">
          {nodes.length} nodes{overDense ? " · over-dense (correlation bonus suppressed)" : ""}
        </span>
      </div>
      <div ref={containerRef} className="h-80 overflow-hidden rounded-md border border-(--color-hairline) bg-(--color-surface)">
        {size.width > 0 && (
          <ForceGraph2D<NodeDatum, LinkDatum>
          ref={fgRef}
          width={size.width}
          height={size.height}
          graphData={graphData}
          nodeId="id"
          cooldownTicks={layout === "temporal" ? 0 : 100}
          linkColor={(l: FGLink) => {
            const active = activeId && (endpointId(l.source) === activeId || endpointId(l.target) === activeId);
            return active ? "rgba(178, 100, 15, 0.9)" : "rgba(120,130,135,0.35)";
          }}
          linkWidth={(l: FGLink) => (l.type === "stage_advance" ? 2 : 1)}
          linkLineDash={(l: FGLink) => (l.type === "shared_pc" || l.type === "shared_file" ? [3, 2] : null)}
          onNodeClick={(n: FGNode) => {
            const id = n.id != null ? String(n.id) : null;
            onSelect(id === selectedId ? null : id);
          }}
          onNodeHover={(n: FGNode | null) => setHoverId(n?.id != null ? String(n.id) : null)}
          nodeCanvasObject={(node: FGNode, ctx: CanvasRenderingContext2D) => {
            const r = node.has_signal ? 6 : 3.5;
            const shape = SOURCE_SHAPES[(node.source as EventSource) ?? "file"];
            const fill = node.has_signal ? emberForRisk((node.risk_contribution ?? 0) * 5) : "rgba(120,130,135,0.5)";
            const id = node.id != null ? String(node.id) : "";
            const isActive = id === activeId;
            const isNeighbor = neighborIds.has(id);
            ctx.globalAlpha = activeId && !isActive && !isNeighbor ? 0.35 : 1;
            drawShape(ctx, shape, node.x ?? 0, node.y ?? 0, r);
            ctx.fillStyle = fill;
            ctx.fill();
            ctx.lineWidth = isActive ? 2 : 1;
            ctx.strokeStyle = isActive ? "#0B0F10" : "rgba(11,15,16,0.4)";
            ctx.stroke();
            ctx.globalAlpha = 1;
          }}
          />
        )}
      </div>
      <p className="text-xs text-(--color-ink-muted)">shape = source · fill = risk contribution · dashed edge = shared PC/file</p>
    </div>
  );
}
