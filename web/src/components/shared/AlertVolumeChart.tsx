import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatDate } from "@/lib/utils";

export interface AlertVolumePoint {
  date: string;
  count: number;
}

export function AlertVolumeChart({ points, total, changePct }: { points: AlertVolumePoint[]; total: number; changePct: number | null }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Alert volume</p>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-2xl font-semibold text-slate-900">{total}</span>
            {changePct != null && (
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${changePct >= 0 ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>
                {changePct >= 0 ? "+" : ""}
                {changePct.toFixed(0)}%
              </span>
            )}
          </div>
        </div>
      </div>
      <div className="mt-4 h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="alertVolumeFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#4F46E5" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#4F46E5" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#EEF0F4" vertical={false} strokeDasharray="4 4" />
            <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fontSize: 11, fill: "#94A3B8" }} axisLine={{ stroke: "#E5E7EB" }} tickLine={false} minTickGap={32} />
            <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#94A3B8" }} axisLine={false} tickLine={false} width={24} />
            <Tooltip
              labelFormatter={(v) => formatDate(String(v))}
              formatter={(v) => [String(v), "Incidents"]}
              contentStyle={{ background: "#FFFFFF", border: "1px solid #E5E7EB", borderRadius: 8, fontSize: 12 }}
            />
            <Area type="monotone" dataKey="count" stroke="#4F46E5" strokeWidth={2} fill="url(#alertVolumeFill)" isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
