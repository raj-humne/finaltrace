function fmtMinutes(m: number) {
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return `${String(h).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

/** The learned off-hours boundary, shown explicitly so an analyst can verify personalisation (docs/06 section 5.3). */
export function WorkingWindowBar({ startMin, endMin }: { startMin: number; endMin: number }) {
  const dayMin = 24 * 60;
  const leftPct = (startMin / dayMin) * 100;
  const widthPct = ((endMin - startMin) / dayMin) * 100;
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between text-sm">
        <span className="text-(--color-ink-secondary)">Working window, learned</span>
        <span className="font-mono-tab">
          {fmtMinutes(startMin)} - {fmtMinutes(endMin)}
        </span>
      </div>
      <div className="relative h-2.5 rounded-full bg-(--color-gridline)">
        <div className="absolute h-full rounded-full bg-(--color-accent)" style={{ left: `${leftPct}%`, width: `${widthPct}%` }} />
      </div>
    </div>
  );
}
