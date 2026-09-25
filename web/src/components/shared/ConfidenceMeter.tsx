const AUTO_FLAG_CONFIDENCE_THRESHOLD = 0.65;

export function ConfidenceMeter({ value, compact = false }: { value: number; compact?: boolean }) {
  const pct = Math.max(0, Math.min(100, value * 100));
  const thresholdPct = AUTO_FLAG_CONFIDENCE_THRESHOLD * 100;
  return (
    <div className="flex items-center gap-2">
      <div
        className="relative rounded-full bg-(--color-gridline)"
        style={{ width: compact ? 72 : 120, height: compact ? 6 : 8 }}
        role="meter"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={1}
        aria-label="Confidence"
      >
        <div className="h-full rounded-full bg-(--color-source-logon)" style={{ width: `${pct}%` }} />
        <div className="absolute top-1/2 h-2.5 w-0.5 -translate-y-1/2 bg-(--color-ink)" style={{ left: `${thresholdPct}%` }} aria-hidden />
      </div>
      <span className="font-mono-tab text-xs text-(--color-ink-secondary)">{value.toFixed(2)}</span>
    </div>
  );
}
