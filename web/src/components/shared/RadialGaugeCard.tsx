import { RadialBar, RadialBarChart, PolarAngleAxis } from "recharts";

interface RadialGaugeCardProps {
  title: string;
  subtitle: string;
  value: number;
  target: number;
  valueLabel: string;
  captionLabel: string;
  breakdown: { label: string; value: string; pct: number }[];
}

/** Matches the "Estimated Revenue" gauge card shape, with real numbers: precision against the PRD's documented auto-flag target (docs/01 section 7.1), not a fabricated revenue goal. */
export function RadialGaugeCard({ title, subtitle, value, target, valueLabel, captionLabel, breakdown }: RadialGaugeCardProps) {
  const pct = Math.max(0, Math.min(100, (value / target) * 100));
  const data = [{ name: title, value: pct, fill: "#4F46E5" }];

  return (
    <div className="flex flex-col rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>
        </div>
      </div>

      <div className="relative mx-auto mt-2 h-[150px] w-[260px]">
        <RadialBarChart width={260} height={150} cx="50%" cy="100%" innerRadius={90} outerRadius={130} barSize={14} data={data} startAngle={180} endAngle={0}>
          <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
          <RadialBar dataKey="value" cornerRadius={7} background={{ fill: "#E5E7EB" }} isAnimationActive={false} />
        </RadialBarChart>
        <div className="absolute inset-x-0 bottom-0 flex flex-col items-center">
          <span className="text-2xl font-semibold text-slate-900">{valueLabel}</span>
          <span className="text-xs text-slate-500">{captionLabel}</span>
        </div>
      </div>

      <div className="mt-2 divide-y divide-slate-100 border-t border-slate-100">
        {breakdown.map((b) => (
          <div key={b.label} className="flex items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <p className="text-sm text-slate-500">{b.label}</p>
              <p className="text-sm font-semibold text-slate-900">{b.value}</p>
            </div>
            <div className="flex flex-1 items-center gap-2">
              <div className="h-1.5 flex-1 rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-indigo-600" style={{ width: `${Math.max(0, Math.min(100, b.pct))}%` }} />
              </div>
              <span className="w-9 shrink-0 text-right text-xs text-slate-500">{Math.round(b.pct)}%</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
