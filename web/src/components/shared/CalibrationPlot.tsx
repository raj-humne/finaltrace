import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis, ReferenceLine } from "recharts";
import { ChartViewToggle } from "./ChartViewToggle";

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

  const chart = (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid stroke="#EEF0F4" />
          <XAxis type="number" dataKey="x" domain={[0, 1]} tick={{ fontSize: 11, fill: "#94A3B8" }} axisLine={{ stroke: "#E5E7EB" }} tickLine={false} name="Stated confidence" />
          <YAxis type="number" dataKey="y" domain={[0, 1]} tick={{ fontSize: 11, fill: "#94A3B8" }} axisLine={false} tickLine={false} name="Observed precision" width={32} />
          <ZAxis type="number" dataKey="n" range={[40, 300]} name="n" />
          <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="#CBD5E1" strokeDasharray="4 4" />
          <Tooltip cursor={{ strokeDasharray: "3 3" }} contentStyle={{ background: "#FFFFFF", border: "1px solid #E5E7EB", borderRadius: 8, fontSize: 12 }} formatter={(value, name) => [typeof value === "number" ? value.toFixed(2) : String(value), String(name)]} />
          <Scatter data={points} fill="#4F46E5" />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );

  const table = (
    <div className="max-h-64 overflow-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">Calibration bins: stated confidence range versus observed precision</caption>
        <thead className="border-b border-slate-200 text-left text-xs text-slate-400">
          <tr>
            <th scope="col" className="py-1.5 pr-3 font-medium">
              Confidence range
            </th>
            <th scope="col" className="py-1.5 pr-3 font-medium">
              n
            </th>
            <th scope="col" className="py-1.5 font-medium">
              Observed precision
            </th>
          </tr>
        </thead>
        <tbody>
          {bins.map((b, i) => {
            const [lo = 0, hi = 0] = b.confidence_range ?? [];
            return (
              <tr key={i} className="border-b border-slate-100 last:border-b-0">
                <td className="py-1.5 pr-3 font-mono-tab text-slate-700">
                  {lo.toFixed(2)}-{hi.toFixed(2)}
                </td>
                <td className="py-1.5 pr-3 font-mono-tab text-slate-700">{b.n ?? 0}</td>
                <td className="py-1.5 font-mono-tab text-slate-700">{b.observed_precision != null ? b.observed_precision.toFixed(2) : "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  return (
    <div>
      <ChartViewToggle label="Calibration: stated confidence versus observed precision" chart={chart} table={table} />
      {ece != null && <p className="mt-1 text-xs text-slate-500">Expected calibration error (ECE): {ece.toFixed(3)}</p>}
    </div>
  );
}
