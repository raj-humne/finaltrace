import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartViewToggle } from "./ChartViewToggle";
import { formatDate } from "@/lib/utils";

interface Point {
  date: string;
  risk: number;
  p50: number;
  p90: number;
}

export function RiskTrendChart({ points }: { points: Point[] }) {
  const withBand = points.map((p) => ({ ...p, bandDelta: Math.max(0, p.p90 - p.p50) }));

  const chart = (
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
      <p className="mt-1 text-xs text-(--color-ink-muted)">Shaded band: cohort p50-p90 for the same dates.</p>
    </div>
  );

  const table = (
    <div className="max-h-64 overflow-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">Risk over time, with the cohort p50-p90 band for each date</caption>
        <thead className="border-b border-(--color-hairline) text-left text-xs text-(--color-ink-muted)">
          <tr>
            <th scope="col" className="py-1.5 pr-3 font-medium">
              Date
            </th>
            <th scope="col" className="py-1.5 pr-3 font-medium">
              Risk
            </th>
            <th scope="col" className="py-1.5 pr-3 font-medium">
              Cohort p50
            </th>
            <th scope="col" className="py-1.5 font-medium">
              Cohort p90
            </th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.date} className="border-b border-(--color-hairline) last:border-b-0">
              <td className="py-1.5 pr-3 font-mono-tab">{formatDate(p.date)}</td>
              <td className="py-1.5 pr-3 font-mono-tab">{p.risk.toFixed(1)}</td>
              <td className="py-1.5 pr-3 font-mono-tab text-(--color-ink-muted)">{p.p50.toFixed(1)}</td>
              <td className="py-1.5 font-mono-tab text-(--color-ink-muted)">{p.p90.toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return <ChartViewToggle label="Risk over time, with the cohort p50-p90 band" chart={chart} table={table} />;
}
