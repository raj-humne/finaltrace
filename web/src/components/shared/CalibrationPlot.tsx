import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis, ReferenceLine } from "recharts";

interface Bin {
  confidence_range?: number[];
  n?: number;
  observed_precision?: number | null;
}

export function CalibrationPlot({ bins, ece }: { bins: Bin[]; ece?: number }) {
  const points = bins.map((b) => {
    const [lo = 0, hi = 0] = b.confidence_range ?? [];
    return { x: (lo + hi) / 2, y: b.observed_precision ?? 0, n: b.n ?? 0 };
  });

  return (
    <div>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid stroke="var(--color-gridline)" />
            <XAxis type="number" dataKey="x" domain={[0, 1]} tick={{ fontSize: 11, fill: "var(--color-ink-muted)" }} axisLine={{ stroke: "var(--color-gridline)" }} tickLine={false} name="Stated confidence" />
            <YAxis type="number" dataKey="y" domain={[0, 1]} tick={{ fontSize: 11, fill: "var(--color-ink-muted)" }} axisLine={false} tickLine={false} name="Observed precision" width={32} />
            <ZAxis type="number" dataKey="n" range={[40, 300]} name="n" />
            <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="var(--color-ink-muted)" strokeDasharray="4 4" />
            <Tooltip
              cursor={{ strokeDasharray: "3 3" }}
              contentStyle={{ background: "var(--color-surface-raised)", border: "1px solid var(--color-hairline)", fontSize: 12 }}
              formatter={(value, name) => [typeof value === "number" ? value.toFixed(2) : String(value), String(name)]}
            />
            <Scatter data={points} fill="var(--color-ember-400)" />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      {ece != null && <p className="mt-1 text-xs text-(--color-ink-muted)">Expected calibration error (ECE): {ece.toFixed(3)}</p>}
    </div>
  );
}
