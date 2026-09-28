import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartViewToggle } from "./ChartViewToggle";
import { formatDate } from "@/lib/utils";

export interface AlertVolumePoint {
  date: string;
  count: number;
}

export function AlertVolumeChart({ points, total, changePct }: { points: AlertVolumePoint[]; total: number; changePct: number | null }) {
  const chart = (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="alertVolumeFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#BCABAE" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#BCABAE" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(113, 105, 105, 0.2)" vertical={false} strokeDasharray="4 4" />
          <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fontSize: 11, fill: "#BCABAE" }} axisLine={{ stroke: "rgba(255, 255, 255, 0.1)" }} tickLine={false} minTickGap={32} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#BCABAE" }} axisLine={false} tickLine={false} width={24} />
          <Tooltip labelFormatter={(v) => formatDate(String(v))} formatter={(v) => [String(v), "Incidents"]} contentStyle={{ background: "#1f2020", border: "1px solid rgba(255, 255, 255, 0.15)", borderRadius: 8, fontSize: 12, color: "#FBFBFB" }} />
          <Area type="monotone" dataKey="count" stroke="#BCABAE" strokeWidth={2} fill="url(#alertVolumeFill)" isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );

  const table = (
    <div className="max-h-64 overflow-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">Alert volume by date</caption>
        <thead className="border-b border-white/10 text-left text-xs text-[#BCABAE]">
          <tr>
            <th scope="col" className="py-1.5 pr-3 font-medium">
              Date
            </th>
            <th scope="col" className="py-1.5 font-medium">
              Incidents
            </th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.date} className="border-b border-white/[0.06] last:border-b-0">
              <td className="py-1.5 pr-3 font-mono-tab text-[#FBFBFB]">{formatDate(p.date)}</td>
              <td className="py-1.5 font-mono-tab text-[#FBFBFB]">{p.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="glass-card rounded-xl p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-[#BCABAE]">Alert volume</p>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-[#FBFBFB]">{total}</span>
            {changePct != null && (
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${changePct >= 0 ? "bg-emerald-950/60 text-emerald-400 border border-emerald-800/40" : "bg-rose-950/60 text-rose-400 border border-rose-800/40"}`}>
                {changePct >= 0 ? "+" : ""}
                {changePct.toFixed(0)}%
              </span>
            )}
          </div>
        </div>
      </div>
      <div className="mt-4">
        <ChartViewToggle label="Alert volume by date" chart={chart} table={table} />
      </div>
    </div>
  );
}
