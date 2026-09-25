import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatDate } from "@/lib/utils";

interface Point {
  date: string;
  risk: number;
  p50: number;
  p90: number;
}

export function RiskTrendChart({ points }: { points: Point[] }) {
  const withBand = points.map((p) => ({ ...p, bandDelta: Math.max(0, p.p90 - p.p50) }));
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={withBand} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--color-gridline)" vertical={false} />
          <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fontSize: 11, fill: "var(--color-ink-muted)" }} axisLine={{ stroke: "var(--color-gridline)" }} tickLine={false} minTickGap={40} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: "var(--color-ink-muted)" }} axisLine={false} tickLine={false} width={28} />
          <Tooltip
            labelFormatter={(v) => formatDate(String(v))}
            contentStyle={{ background: "var(--color-surface-raised)", border: "1px solid var(--color-hairline)", fontSize: 12 }}
          />
          <Area dataKey="p50" stackId="band" stroke="none" fill="transparent" isAnimationActive={false} />
          <Area dataKey="bandDelta" stackId="band" stroke="none" fill="var(--color-ink-muted)" fillOpacity={0.12} isAnimationActive={false} />
          <Line dataKey="risk" stroke="var(--color-ember-500)" strokeWidth={2} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="mt-1 text-xs text-(--color-ink-muted)">Shaded band: cohort p50–p90 for the same dates.</p>
    </div>
  );
}
