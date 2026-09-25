import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface KpiCardProps {
  icon: LucideIcon;
  label: string;
  value: string;
  /** Only set when there's a real prior-period number to compare against — never fabricated. */
  delta?: { pct: number; caption: string };
  className?: string;
}

export function KpiCard({ icon: Icon, label, value, delta, className }: KpiCardProps) {
  const positive = (delta?.pct ?? 0) >= 0;
  return (
    <div className={cn("rounded-xl border border-slate-200 bg-white p-5", className)}>
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50">
          <Icon className="h-4 w-4 text-indigo-600" aria-hidden />
        </span>
        <span className="text-sm text-slate-500">{label}</span>
      </div>
      <p className="mt-4 text-[1.75rem] font-semibold leading-none tracking-tight text-slate-900">{value}</p>
      {delta && (
        <div className="mt-3 flex items-center gap-2 text-xs">
          <span className={cn("rounded-full px-2 py-0.5 font-medium", positive ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700")}>
            {positive ? "+" : ""}
            {delta.pct.toFixed(1)}%
          </span>
          <span className="text-slate-400">{delta.caption}</span>
        </div>
      )}
    </div>
  );
}
