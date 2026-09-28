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
    <div className={cn("glass-card rounded-xl p-5", className)}>
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/[0.08] text-[#BCABAE]">
          <Icon className="h-4 w-4" aria-hidden />
        </span>
        <span className="text-sm font-medium text-[#BCABAE]">{label}</span>
      </div>
      <p className="mt-4 text-[1.75rem] font-bold leading-none tracking-tight text-[#FBFBFB]">{value}</p>
      {delta && (
        <div className="mt-3 flex items-center gap-2 text-xs">
          <span className={cn("rounded-full px-2 py-0.5 font-medium", positive ? "bg-emerald-950/60 text-emerald-400 border border-emerald-800/40" : "bg-rose-950/60 text-rose-400 border border-rose-800/40")}>
            {positive ? "+" : ""}
            {delta.pct.toFixed(1)}%
          </span>
          <span className="text-[#BCABAE]/70">{delta.caption}</span>
        </div>
      )}
    </div>
  );
}
