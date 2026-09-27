import { useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { ScoreMeter } from "./ScoreMeter";
import { SOURCE_LABELS, type EventSource } from "@/lib/design";
import { cn, formatTime, parseApiTimestamp } from "@/lib/utils";
import type { components } from "@/lib/api/types.gen";

type GraphNode = components["schemas"]["GraphNodeOut"];

const STEP_MS = 900;

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

/**
 * User-started, scrubbable replay of an incident's events in chronological
 * order, with the risk score climbing as signal-bearing events pass (docs/06
 * section 7.3, FR-7.3). The one piece of non-trivial motion in the incident
 * page — auto-advance is opt-in via Play and never starts itself, and is
 * unavailable under prefers-reduced-motion (docs/06 section 8).
 */
export function TimelineReplay({ nodes, finalRisk }: { nodes: GraphNode[]; finalRisk: number }) {
  const reducedMotion = usePrefersReducedMotion();
  const sorted = useMemo(
    () =>
      nodes
        .filter((n): n is GraphNode & { ts: string } => !!n.ts)
        .slice()
        .sort((a, b) => parseApiTimestamp(a.ts).getTime() - parseApiTimestamp(b.ts).getTime()),
    [nodes]
  );

  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!playing) return;
    timerRef.current = setInterval(() => {
      setIndex((i) => {
        if (i >= sorted.length - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, STEP_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [playing, sorted.length]);

  if (sorted.length === 0) {
    return <p className="text-sm text-(--color-ink-muted)">No events available to replay.</p>;
  }

  const current = sorted[index];
  const runningRisk = Math.min(
    finalRisk,
    sorted.slice(0, index + 1).reduce((sum, n) => sum + (n.has_signal ? (n.risk_contribution ?? 0) : 0), 0)
  );

  function step(delta: number) {
    setPlaying(false);
    setIndex((i) => Math.max(0, Math.min(sorted.length - 1, i + delta)));
  }

  return (
    <div className="flex flex-col gap-3">
      <ScoreMeter label="Risk so far" value={runningRisk} threshold={finalRisk} thresholdLabel={`final risk ${finalRisk.toFixed(1)}`} />

      <div className="flex items-center gap-3">
        {reducedMotion ? (
          <span className="text-xs text-(--color-ink-muted)">Reduced motion: use the step controls</span>
        ) : (
          <button
            onClick={() => setPlaying((p) => !p)}
            aria-label={playing ? "Pause replay" : "Play replay"}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-(--color-accent) text-(--color-accent-ink)"
          >
            {playing ? <Pause className="h-3.5 w-3.5" aria-hidden /> : <Play className="h-3.5 w-3.5" aria-hidden />}
          </button>
        )}
        <button onClick={() => step(-1)} aria-label="Previous event" disabled={index === 0} className="text-(--color-ink-muted) hover:text-(--color-ink) disabled:opacity-30">
          <SkipBack className="h-4 w-4" aria-hidden />
        </button>
        <input
          type="range"
          min={0}
          max={sorted.length - 1}
          value={index}
          onChange={(e) => {
            setPlaying(false);
            setIndex(Number(e.target.value));
          }}
          aria-label="Timeline position"
          aria-valuetext={`${formatTime(current.ts!)}, event ${index + 1} of ${sorted.length}`}
          className="h-1.5 flex-1 accent-(--color-accent)"
        />
        <button onClick={() => step(1)} aria-label="Next event" disabled={index === sorted.length - 1} className="text-(--color-ink-muted) hover:text-(--color-ink) disabled:opacity-30">
          <SkipForward className="h-4 w-4" aria-hidden />
        </button>
      </div>

      <div className={cn("rounded-md border border-(--color-hairline) p-3", current.has_signal ? "bg-(--color-accent)/5" : "bg-(--color-surface)")}>
        <div className="flex items-baseline justify-between gap-3">
          <span className="font-mono-tab text-sm text-(--color-ink-secondary)">{formatTime(current.ts!)}</span>
          <span className="text-xs text-(--color-ink-muted)">
            event {index + 1} of {sorted.length}
          </span>
        </div>
        <p className="mt-0.5 text-sm text-(--color-ink)">{current.label ?? current.action}</p>
        <p className="mt-0.5 text-xs text-(--color-ink-muted)">
          {SOURCE_LABELS[(current.source as EventSource) ?? "file"] ?? current.source}
          {current.pc_id ? ` · ${current.pc_id}` : ""}
          {current.has_signal && current.risk_contribution ? ` · +${current.risk_contribution.toFixed(1)} risk` : ""}
        </p>
      </div>
    </div>
  );
}
