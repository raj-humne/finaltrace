import { useEffect, useLayoutEffect, useMemo, useRef, useState, useCallback } from "react";
import ForceGraph2D, { type NodeObject, type LinkObject, type ForceGraphMethods } from "react-force-graph-2d";
import { SOURCE_SHAPES, SOURCE_LABELS, SOURCE_ORDER, EMBER_STEPS, emberForRisk, type EventSource } from "@/lib/design";
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

function endpointXY(end: FGLink["source"]): { x: number; y: number } | undefined {
  if (end == null || typeof end !== "object") return undefined;
  const n = end as FGNode;
  return n.x != null && n.y != null ? { x: n.x, y: n.y } : undefined;
}

const EDGE_TYPE_LABELS: Record<string, string> = {
  temporal: "next event in time",
  shared_pc: "same workstation",
  shared_file: "same file",
  stage_advance: "kill-chain stage advance",
};

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

  // "temporal" edges connect every pair of events that merely happened
  // close together in time - on a tight burst (e.g. 51 events in ~20
  // minutes) that's close to *every* pair, producing a solid black hairball
  // (a real incident here had 51 nodes and 1275 temporal edges - a complete
  // graph). shared_pc/shared_file only ever fire cross-user (lateral
  // movement, engine/correlate/graph.py), so a single-employee incident like
  // this one has *none* - dropping all temporal edges would leave a graph
  // with zero lines at all, which is worse than the hairball it replaced.
  //
  // Instead: keep only the temporal edges between events that are each
  // other's immediate next/previous event in time (a real edge from the
  // actual data, never fabricated) - a thin, readable "what happened right
  // after what" thread - plus every shared_pc/shared_file/stage_advance edge
  // (rare enough to always show in full, and the actual reason two events
  // were pulled into one incident beyond simple sequence).
  const { meaningfulEdges, temporalCount } = useMemo(() => {
    const nonTemporal = edges.filter((e) => e.type !== "temporal");
    const byTime = [...nodes].sort((a, b) => {
      const ta = a.ts ? parseApiTimestamp(a.ts).getTime() : 0;
      const tb = b.ts ? parseApiTimestamp(b.ts).getTime() : 0;
      return ta - tb;
    });
    const adjacentPairs = new Set<string>();
    for (let i = 0; i < byTime.length - 1; i++) {
      adjacentPairs.add(`${byTime[i].id}::${byTime[i + 1].id}`);
      adjacentPairs.add(`${byTime[i + 1].id}::${byTime[i].id}`);
    }
    const temporalSpine = edges.filter((e) => e.type === "temporal" && adjacentPairs.has(`${e.source}::${e.target}`));
    const meaningful = [...nonTemporal, ...temporalSpine];
    return { meaningfulEdges: meaningful, temporalCount: edges.length - meaningful.length };
  }, [edges, nodes]);

  const { graphData, tMin, tSpan } = useMemo(() => {
    const times = nodes.map((n) => (n.ts ? parseApiTimestamp(n.ts).getTime() : 0));
    const tMin = Math.min(...times);
    const tMax = Math.max(...times);
    const tSpan = Math.max(1, tMax - tMin);
    return {
      graphData: { nodes: nodes.map((n) => ({ ...n })) as FGNode[], links: meaningfulEdges.map((e) => ({ ...e })) as unknown as FGLink[] },
      tMin,
      tSpan,
    };
  }, [nodes, meaningfulEdges]);

  const activeId = hoverId ?? selectedId;
  const neighborIds = useMemo(() => {
    if (!activeId) return new Set<string>();
    const s = new Set<string>();
    for (const e of meaningfulEdges) {
      if (e.source === activeId) s.add(e.target!);
      if (e.target === activeId) s.add(e.source!);
    }
    return s;
  }, [activeId, meaningfulEdges]);

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
      <p className="text-sm text-(--color-ink-secondary)">
        Every dot is one real log event from this incident. Every line is a real, named reason two events were pulled together —
        hover a line or a dot to see exactly what it is. Switch <strong className="text-(--color-ink)">time</strong> to lay events
        out in the order they happened, or <strong className="text-(--color-ink)">force</strong> to cluster tightly-related events
        together instead.
      </p>
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
          {nodes.length} events · {meaningfulEdges.length} correlations shown
          {overDense ? " · over-dense (correlation bonus suppressed)" : ""}
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
            if (active) return "rgba(178, 100, 15, 0.9)";
            if (l.type === "stage_advance") return "rgba(222,127,28,0.85)";
            if (l.type === "shared_pc" || l.type === "shared_file") return "rgba(90,100,105,0.85)";
            return "rgba(120,130,135,0.35)"; // temporal spine - present, but deliberately faint
          }}
          linkWidth={(l: FGLink) => (l.type === "stage_advance" ? 2 : l.type === "temporal" ? 1 : 1.5)}
          linkLineDash={(l: FGLink) => (l.type === "shared_pc" || l.type === "shared_file" ? [3, 2] : null)}
          linkLabel={(l: FGLink) => `${EDGE_TYPE_LABELS[l.type ?? "temporal"] ?? l.type} · ${l.gap_label ?? ""}`}
          linkCanvasObjectMode={() => "after"}
          linkCanvasObject={(l: FGLink, ctx: CanvasRenderingContext2D) => {
            if (l.type === "temporal") return; // too many to label individually - hover shows the name instead
            const a = endpointXY(l.source);
            const b = endpointXY(l.target);
            if (!a || !b) return;
            const label = EDGE_TYPE_LABELS[l.type ?? ""] ?? l.type ?? "";
            ctx.font = "9px var(--font-interface, sans-serif)";
            ctx.textAlign = "center";
            ctx.textBaseline = "bottom";
            ctx.fillStyle = l.type === "stage_advance" ? "rgba(178, 100, 15, 0.95)" : "rgba(70,80,85,0.95)";
            ctx.fillText(label, (a.x + b.x) / 2, (a.y + b.y) / 2 - 3);
          }}
          nodeLabel={(n: FGNode) => `${SOURCE_LABELS[(n.source as EventSource) ?? "file"]} · ${n.action ?? ""}${n.has_signal ? " · flagged signal" : ""}`}
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
      <GraphLegend temporalCount={temporalCount} />
    </div>
  );
}

function ShapeSwatch({ shape }: { shape: "circle" | "diamond" | "square" | "hexagon" | "triangle" }) {
  return (
    <svg width={14} height={14} viewBox="0 0 14 14" aria-hidden className="shrink-0 fill-(--color-ink-secondary)">
      {shape === "circle" && <circle cx={7} cy={7} r={5} />}
      {shape === "diamond" && <polygon points="7,2 12,7 7,12 2,7" />}
      {shape === "square" && <rect x={2.5} y={2.5} width={9} height={9} />}
      {shape === "triangle" && <polygon points="7,2 11.75,10.75 2.25,10.75" />}
      {shape === "hexagon" && <polygon points="7,2 11.33,4.5 11.33,9.5 7,12 2.67,9.5 2.67,4.5" />}
    </svg>
  );
}

/** Spells out every visual encoding used above - shape, fill, size, and edge
 * style all carry real meaning, and none of it is discoverable by staring at
 * the canvas alone (docs/06 section 4.4's "never rely on the viewer to
 * infer an encoding" applies here as much as it does to color). */
function GraphLegend({ temporalCount }: { temporalCount: number }) {
  return (
    <div className="flex flex-col gap-3 rounded-md border border-(--color-hairline) bg-(--color-surface) p-3 text-xs text-(--color-ink-secondary)">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <span className="font-medium text-(--color-ink)">Shape = what kind of event</span>
        {SOURCE_ORDER.map((src) => (
          <span key={src} className="flex items-center gap-1.5">
            <ShapeSwatch shape={SOURCE_SHAPES[src]} />
            {SOURCE_LABELS[src]}
          </span>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <span className="font-medium text-(--color-ink)">Fill = how much this event drove the score</span>
        <span className="flex items-center gap-1.5">
          <span
            className="h-2.5 w-20 rounded-full"
            style={{ background: `linear-gradient(to right, ${EMBER_STEPS[0]}, ${EMBER_STEPS[EMBER_STEPS.length - 1]})` }}
          />
          low → high
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: "rgba(120,130,135,0.5)" }} />
          grey = surrounding context, not itself flagged
        </span>
        <span>Bigger dot = flagged as a signal · smaller dot = context only</span>
      </div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <span className="font-medium text-(--color-ink)">Lines = why events were grouped together (hover any line for its name)</span>
        <span className="flex items-center gap-1.5">
          <svg width={20} height={8} aria-hidden>
            <line x1={0} y1={4} x2={20} y2={4} stroke="rgba(222,127,28,0.9)" strokeWidth={2} />
          </svg>
          moved the kill chain forward a stage
        </span>
        <span className="flex items-center gap-1.5">
          <svg width={20} height={8} aria-hidden>
            <line x1={0} y1={4} x2={20} y2={4} stroke="rgba(90,100,105,0.85)" strokeWidth={1.5} strokeDasharray="3 2" />
          </svg>
          same workstation or same file
        </span>
        <span className="flex items-center gap-1.5">
          <svg width={20} height={8} aria-hidden>
            <line x1={0} y1={4} x2={20} y2={4} stroke="rgba(120,130,135,0.35)" strokeWidth={1} />
          </svg>
          led straight into the next event in time
        </span>
      </div>
      {temporalCount > 0 && (
        <p className="border-t border-(--color-hairline) pt-2 text-(--color-ink-muted)">
          {temporalCount} more "happened around the same time" links exist beyond the faint chronological thread shown above —
          left out because between them they'd connect nearly every event to every other one and just look like a solid block of
          lines, not because anything is being hidden from you.
        </p>
      )}
    </div>
  );
}
