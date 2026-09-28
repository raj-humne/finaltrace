import { useMemo } from "react";
import { Activity, Calendar, Download, Layers3, RefreshCw, ShieldAlert, ShieldCheck } from "lucide-react";
import { useDetectionHealth, useRuleStatsFor, useRules } from "@/hooks/useDetection";
import { useIncidents } from "@/hooks/useIncidents";
import { CalibrationPlot } from "@/components/shared/CalibrationPlot";
import { KpiCard } from "@/components/shared/KpiCard";
import { RadialGaugeCard } from "@/components/shared/RadialGaugeCard";
import { AlertVolumeChart, type AlertVolumePoint } from "@/components/shared/AlertVolumeChart";
import { LANES, type TriageLane } from "@/lib/design";
import { cn, formatDate } from "@/lib/utils";
import { usePageTitle } from "@/hooks/usePageTitle";
import { SplitHeading } from "@/components/shared/SplitHeading";

// Auto-flag precision target from docs/01-PRD.md section 7.1 ("Auto-flag
// precision >= 0.75") — the gauge measures against a documented product
// target, not an invented business goal.
const AUTO_FLAG_PRECISION_TARGET = 75;

function downloadCsv(filename: string, rows: Record<string, unknown>[]) {
  if (rows.length === 0) return;
  const headers = Object.keys(rows[0]);
  const csv = [headers.join(","), ...rows.map((r) => headers.map((h) => JSON.stringify(r[h] ?? "")).join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function DetectionHealthPage() {
  usePageTitle("Detection health");
  const { data: health, refetch: refetchHealth, isFetching: fetchingHealth } = useDetectionHealth();
  const { data: rules, refetch: refetchRules } = useRules();
  const ruleIds = useMemo(() => (rules ?? []).map((r) => r.id!).filter(Boolean), [rules]);
  const statsQueries = useRuleStatsFor(ruleIds);
  const { data: openIncidents, refetch: refetchOpen } = useIncidents({ status: "open", limit: 1 });
  const { data: allIncidents, refetch: refetchAll } = useIncidents({ limit: 500 });

  const rows = useMemo(() => {
    return ruleIds
      .map((id, i) => {
        const stats = statsQueries[i]?.data;
        const rule = rules?.find((r) => r.id === id);
        if (!stats) return null;
        return { id, name: rule?.name ?? id, ...stats };
      })
      .filter((r): r is NonNullable<typeof r> => r !== null)
      .sort((a, b) => Math.abs(b.weight_drift ?? 0) - Math.abs(a.weight_drift ?? 0));
  }, [ruleIds, statsQueries, rules]);

  const rulesWithReviews = rows.filter((r) => r.reviewed > 0);
  const weightedPrecision = useMemo(() => {
    const totalDecided = rulesWithReviews.reduce((s, r) => s + r.confirmed + r.benign, 0);
    if (totalDecided === 0) return null;
    const totalConfirmed = rulesWithReviews.reduce((s, r) => s + r.confirmed, 0);
    return (totalConfirmed / totalDecided) * 100;
  }, [rulesWithReviews]);

  const withinToleranceCount = rows.filter((r) => r.recommendation === "within_tolerance").length;
  const scoredRuleCount = rows.filter((r) => r.recommendation !== "insufficient_data").length;

  const { dailyPoints, firstHalfCount, secondHalfCount } = useMemo(() => {
    const from = health?.window?.from;
    const to = health?.window?.to;
    if (!from || !to || !allIncidents?.items) return { dailyPoints: [] as AlertVolumePoint[], firstHalfCount: 0, secondHalfCount: 0 };
    const start = new Date(`${from}T00:00:00Z`);
    const end = new Date(`${to}T00:00:00Z`);
    const dayMs = 86400000;
    const days = Math.max(1, Math.round((end.getTime() - start.getTime()) / dayMs) + 1);
    const counts = new Map<string, number>();
    for (let i = 0; i < days; i++) {
      const d = new Date(start.getTime() + i * dayMs).toISOString().slice(0, 10);
      counts.set(d, 0);
    }
    for (const inc of allIncidents.items) {
      const d = inc.window?.start?.slice(0, 10);
      if (d && counts.has(d)) counts.set(d, (counts.get(d) ?? 0) + 1);
    }
    const points = [...counts.entries()].map(([date, count]) => ({ date, count }));
    const mid = Math.floor(points.length / 2);
    const firstHalf = points.slice(0, mid).reduce((s, p) => s + p.count, 0);
    const secondHalf = points.slice(mid).reduce((s, p) => s + p.count, 0);
    return { dailyPoints: points, firstHalfCount: firstHalf, secondHalfCount: secondHalf };
  }, [health, allIncidents]);

  const volumeChangePct = firstHalfCount > 0 ? ((secondHalfCount - firstHalfCount) / firstHalfCount) * 100 : null;

  const laneMix = health?.lane_mix ?? {};
  const laneTotal = Object.values(laneMix).reduce((s, n) => s + (n ?? 0), 0) || 1;

  function onRefresh() {
    refetchHealth();
    refetchRules();
    refetchOpen();
    refetchAll();
  }

  function onExport() {
    downloadCsv(
      "sentineltrace-rules.csv",
      rows.map((r) => ({
        rule_id: r.id,
        name: r.name,
        fire_count: r.fire_count,
        reviewed: r.reviewed,
        observed_precision: r.observed_precision,
        configured_weight: r.configured_weight,
        measured_log_odds: r.measured_log_odds,
        weight_drift: r.weight_drift,
        recommendation: r.recommendation,
      }))
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Centered Page Header: Akira Heading & Mont Subheading (matching Queue design, no icon) */}
      <div className="flex flex-col items-center justify-center text-center pt-2 pb-2">
        <SplitHeading text="DETECTION HEALTH" />
        <p className="mt-3 font-mont font-light text-xs sm:text-[13px] tracking-[0.2em] uppercase text-[#BCABAE]">
          {health?.window?.from && health?.window?.to ? (
            <>Window {formatDate(health.window.from)} – {formatDate(health.window.to)} · System Health &amp; Calibration</>
          ) : (
            "System Health & Calibration Metrics"
          )}
        </p>
      </div>

      <div className="glass-container rounded-2xl p-6">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.08] pb-4 mb-5">
          <div className="font-mont text-xs tracking-wider uppercase text-[#BCABAE]/80 font-medium">
            Telemetry &amp; Rule Performance
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onRefresh}
              aria-label="Refresh"
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-white/15 bg-white/[0.06] backdrop-blur-md text-[#BCABAE] hover:text-[#FBFBFB] hover:border-white/30 transition-colors"
            >
              <RefreshCw className={cn("h-4 w-4", fetchingHealth && "animate-spin")} aria-hidden />
            </button>
            <span className="flex h-9 items-center gap-2 rounded-lg border border-white/15 bg-white/[0.06] backdrop-blur-md px-3 text-sm text-[#BCABAE]">
              <Calendar className="h-4 w-4 text-[#BCABAE]/70" aria-hidden />
              {health?.window?.from && formatDate(health.window.from)} - {health?.window?.to && formatDate(health.window.to)}
            </span>
            <button
              onClick={onExport}
              className="btn-cta flex h-9 items-center gap-2 rounded-lg bg-[#BCABAE] px-3.5 text-sm font-semibold text-[#0F0F0F] transition-all hover:bg-[#d8c7ca] shadow-md"
            >
              <Download className="h-4 w-4" aria-hidden />
              Export
            </button>
          </div>
        </div>

      <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard icon={ShieldAlert} label="Open incidents" value={String(openIncidents?.total ?? 0)} />
        <KpiCard icon={ShieldCheck} label="Auto-flag precision" value={weightedPrecision != null ? `${weightedPrecision.toFixed(0)}%` : "n/a"} />
        <KpiCard icon={Layers3} label="Signals / incident" value={health?.compression?.signals_per_incident_mean?.toFixed(1) ?? "n/a"} />
        <KpiCard icon={Activity} label="Calibration error" value={health?.calibration?.ece?.toFixed(3) ?? "n/a"} />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-[1.6fr_1fr]">
        <AlertVolumeChart points={dailyPoints} total={allIncidents?.total ?? 0} changePct={volumeChangePct} />
        <RadialGaugeCard
          title="Auto-flag precision"
          subtitle="Against the documented product target"
          value={weightedPrecision ?? 0}
          target={AUTO_FLAG_PRECISION_TARGET}
          valueLabel={weightedPrecision != null ? `${weightedPrecision.toFixed(0)}%` : "n/a"}
          captionLabel={`of ${AUTO_FLAG_PRECISION_TARGET}% target`}
          breakdown={[
            { label: "Rules reviewed", value: `${rulesWithReviews.length} / ${rows.length}`, pct: rows.length ? (rulesWithReviews.length / rows.length) * 100 : 0 },
            { label: "Within tolerance", value: `${withinToleranceCount} / ${scoredRuleCount}`, pct: scoredRuleCount ? (withinToleranceCount / scoredRuleCount) * 100 : 0 },
          ]}
        />
      </div>

      <div className="glass-card mt-4 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-[#FBFBFB]">Lane mix</h2>
        <div className="mt-3 flex h-3 overflow-hidden rounded-full bg-white/10">
          {(Object.keys(LANES) as TriageLane[]).map((lane) => {
            const count = laneMix[lane] ?? 0;
            const pct = (count / laneTotal) * 100;
            if (pct === 0) return null;
            return <div key={lane} title={`${LANES[lane].word}: ${count}`} style={{ width: `${pct}%`, backgroundColor: LANES[lane].hex }} className="mr-0.5 last:mr-0" />;
          })}
        </div>
        <div className="mt-3 flex flex-wrap gap-4 text-xs text-[#BCABAE]">
          {(Object.keys(LANES) as TriageLane[]).map((lane) => (
            <span key={lane} className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: LANES[lane].hex }} />
              {LANES[lane].word} {laneMix[lane] ?? 0}
            </span>
          ))}
        </div>
      </div>

      <div className="glass-card mt-4 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-[#FBFBFB]">Calibration</h2>
        <p className="mb-2 text-xs text-[#BCABAE]/80">Stated confidence against observed precision, with the diagonal drawn.</p>
        {health?.calibration && <CalibrationPlot bins={health.calibration.bins ?? []} ece={health.calibration.ece} />}
      </div>

      {health?.warnings && health.warnings.length > 0 && (
        <div className="mt-4 rounded-xl border border-amber-500/30 bg-amber-950/40 p-4 text-sm text-amber-200 backdrop-blur-md">
          {health.warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
        </div>
      )}

      <div className="glass-card mt-4 overflow-hidden rounded-xl">
        <h2 className="border-b border-white/10 px-5 py-3 text-sm font-semibold text-[#FBFBFB]">Rules, sorted by weight drift</h2>
        <table className="w-full text-sm">
          <thead className="border-b border-white/10 text-left text-xs text-[#BCABAE]">
            <tr>
              <th className="px-5 py-2 font-medium">Rule</th>
              <th className="px-5 py-2 font-medium">Fires</th>
              <th className="px-5 py-2 font-medium">Reviewed</th>
              <th className="px-5 py-2 font-medium">Observed precision</th>
              <th className="px-5 py-2 font-medium">Configured weight</th>
              <th className="px-5 py-2 font-medium">Measured log-odds</th>
              <th className="px-5 py-2 font-medium">Drift</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-white/[0.06] hover:bg-white/[0.04] transition-colors last:border-b-0">
                <td className="px-5 py-2.5">
                  <span className="font-medium text-[#FBFBFB]">{r.name}</span>
                  <span className="ml-2 font-mono-tab text-xs text-[#BCABAE]/60">{r.id}</span>
                </td>
                <td className="px-5 py-2.5 font-mono-tab text-[#FBFBFB]">{r.fire_count}</td>
                <td className="px-5 py-2.5 font-mono-tab text-[#FBFBFB]">{r.reviewed}</td>
                <td className="px-5 py-2.5 font-mono-tab text-[#FBFBFB]">{r.observed_precision?.toFixed(2)}</td>
                <td className="px-5 py-2.5 font-mono-tab text-[#FBFBFB]">{r.configured_weight?.toFixed(2)}</td>
                <td className="px-5 py-2.5 font-mono-tab text-[#FBFBFB]">{r.measured_log_odds?.toFixed(2)}</td>
                <td
                  className={cn(
                    "px-5 py-2.5 font-mono-tab",
                    r.recommendation === "review_weight" && "text-rose-400 font-medium",
                    r.recommendation === "insufficient_data" && "text-[#BCABAE]/60",
                    r.recommendation === "within_tolerance" && "text-[#FBFBFB]"
                  )}
                >
                  {r.recommendation === "review_weight" && "⚠ "}
                  {r.weight_drift != null ? r.weight_drift.toFixed(2) : "insufficient data"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  </div>
);
}
