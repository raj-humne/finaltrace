import { LANES, type TriageLane } from "@/lib/design";
import { cn } from "@/lib/utils";

const GLYPHS: Record<TriageLane, string> = {
  AUTO_FLAG: "■", // filled square
  ANALYST_REVIEW: "◧", // half square
  MONITOR: "□", // hollow square
  SUPPRESSED: "–", // dash
};

/** Glyph + word + color, never color alone (docs/06 section 4.4, 9). */
export function LaneChip({ lane, className }: { lane: TriageLane; className?: string }) {
  const cfg = LANES[lane];
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-sm font-medium", className)} style={{ color: cfg.hex }}>
      <span aria-hidden className="text-[0.85em]">
        {GLYPHS[lane]}
      </span>
      <span>{cfg.word}</span>
    </span>
  );
}
