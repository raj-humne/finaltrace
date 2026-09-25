import { cn, formatRisk } from "@/lib/utils";
import { emberForRisk } from "@/lib/design";

interface ScoreMeterProps {
  label: string;
  value: number;
  max?: number;
  threshold?: number;
  thresholdLabel?: string;
  format?: (v: number) => string;
  tone?: "ember" | "neutral";
  className?: string;
}

/** A horizontal meter with the threshold drawn on it as a tick — replaces the traffic-light gauge (docs/06 section 7.2). */
export function ScoreMeter({ label, value, max = 100, threshold, thresholdLabel, format, tone = "ember", className }: ScoreMeterProps) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const thresholdPct = threshold != null ? Math.max(0, Math.min(100, (threshold / max) * 100)) : null;
  const fillColor = tone === "ember" ? emberForRisk((value / max) * 100) : "var(--color-accent)";
  const displayValue = format ? format(value) : formatRisk(value);

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <div className="flex items-baseline justify-between">
        <span className="text-sm text-(--color-ink-secondary)">{label}</span>
        <span className="font-mono-tab text-lg" style={{ color: tone === "ember" ? fillColor : undefined }}>
          {displayValue}
        </span>
      </div>
      <div className="relative h-2.5 rounded-full bg-(--color-gridline)" role="meter" aria-valuenow={value} aria-valuemin={0} aria-valuemax={max} aria-label={label}>
        <div className="h-full rounded-full transition-[width]" style={{ width: `${pct}%`, backgroundColor: fillColor }} />
        {thresholdPct != null && (
          <div className="absolute top-1/2 h-3.5 w-0.5 -translate-y-1/2 bg-(--color-ink)" style={{ left: `${thresholdPct}%` }} aria-hidden />
        )}
      </div>
      {threshold != null && (
        <span className="text-xs text-(--color-ink-muted)">
          {thresholdLabel ?? `threshold at ${format ? format(threshold) : threshold}`}
        </span>
      )}
    </div>
  );
}
