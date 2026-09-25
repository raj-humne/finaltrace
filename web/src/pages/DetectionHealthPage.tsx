import { useMemo } from "react";
import { useDetectionHealth, useRuleStatsFor, useRules } from "@/hooks/useDetection";
import { CalibrationPlot } from "@/components/shared/CalibrationPlot";
import { LANES, type TriageLane } from "@/lib/design";
import { cn } from "@/lib/utils";

export function DetectionHealthPage() {
  const { data: health } = useDetectionHealth();
  const { data: rules } = useRules();
  const ruleIds = useMemo(() => (rules?.items ?? []).map((r) => r.rule_id!).filter(Boolean), [rules]);
  const statsQueries = useRuleStatsFor(ruleIds);

  const rows = useMemo(() => {
    return ruleIds
      .map((id, i) => {
        const stats = statsQueries[i]?.data;
        const rule = rules?.items?.find((r) => r.rule_id === id);
        if (!stats) return null;
        return { id, name: rule?.name ?? id, ...stats };
      })
      .filter((r): r is NonNullable<typeof r> => r !== null)
      .sort((a, b) => Math.abs(b.weight_drift ?? 0) - Math.abs(a.weight_drift ?? 0));
  }, [ruleIds, statsQueries, rules]);

  const laneMix = health?.lane_mix ?? {};
  const laneTotal = Object.values(laneMix).reduce((s, n) => s + (n ?? 0), 0) || 1;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Detection health</h1>
        <p className="mt-1 text-sm text-(--color-ink-secondary)">
          {health?.window?.from} – {health?.window?.to}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <section className="rounded-lg border border-(--color-hairline) bg-(--color-surface-raised) p-4">
          <h2 className="text-sm font-medium text-(--color-ink-secondary)">Alert volume</h2>
          <p className="mt-2 font-mono-tab text-2xl">{health?.alert_volume?.per_1k_users_per_day?.toFixed(2)}</p>
          <p className="text-xs text-(--color-ink-muted)">incidents / 1,000 users / day</p>
          <p className="mt-2 text-xs text-(--color-ink-muted)">
            {health?.compression?.signals_per_incident_mean?.toFixed(1)} signals and {health?.compression?.events_per_incident_mean?.toFixed(0)} events per incident on average
          </p>
        </section>

        <section className="rounded-lg border border-(--color-hairline) bg-(--color-surface-raised) p-4 md:col-span-2">
          <h2 className="mb-2 text-sm font-medium text-(--color-ink-secondary)">Lane mix</h2>
          <div className="flex h-4 overflow-hidden rounded-full">
            {(Object.keys(LANES) as TriageLane[]).map((lane) => {
              const count = laneMix[lane] ?? 0;
              const pct = (count / laneTotal) * 100;
              if (pct === 0) return null;
              return <div key={lane} title={`${LANES[lane].word}: ${count}`} style={{ width: `${pct}%`, backgroundColor: LANES[lane].hex }} className="mr-0.5 last:mr-0" />;
            })}
          </div>
          <div className="mt-2 flex flex-wrap gap-4 text-xs text-(--color-ink-secondary)">
            {(Object.keys(LANES) as TriageLane[]).map((lane) => (
              <span key={lane} className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: LANES[lane].hex }} />
                {LANES[lane].word} {laneMix[lane] ?? 0}
              </span>
            ))}
          </div>
        </section>
      </div>

      <section className="rounded-lg border border-(--color-hairline) bg-(--color-surface-raised) p-4">
        <h2 className="mb-2 text-sm font-medium text-(--color-ink-secondary)">Calibration</h2>
        <p className="mb-2 text-xs text-(--color-ink-muted)">Stated confidence against observed precision, with the diagonal drawn.</p>
        {health?.calibration && <CalibrationPlot bins={health.calibration.bins ?? []} ece={health.calibration.ece} />}
      </section>

      {health?.warnings && health.warnings.length > 0 && (
        <div className="rounded-lg border border-(--color-status-monitor)/40 bg-(--color-surface-raised) p-4 text-sm text-(--color-ink-secondary)">
          {health.warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
        </div>
      )}

      <section className="overflow-hidden rounded-lg border border-(--color-hairline) bg-(--color-surface-raised)">
        <h2 className="border-b border-(--color-hairline) px-4 py-3 text-sm font-medium text-(--color-ink-secondary)">Rules, sorted by weight drift</h2>
        <table className="w-full text-sm">
          <thead className="border-b border-(--color-hairline) text-left text-xs text-(--color-ink-muted)">
            <tr>
              <th className="px-4 py-2 font-medium">Rule</th>
              <th className="px-4 py-2 font-medium">Fires</th>
              <th className="px-4 py-2 font-medium">Reviewed</th>
              <th className="px-4 py-2 font-medium">Observed precision</th>
              <th className="px-4 py-2 font-medium">Configured weight</th>
              <th className="px-4 py-2 font-medium">Measured log-odds</th>
              <th className="px-4 py-2 font-medium">Drift</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-(--color-hairline) last:border-b-0">
                <td className="px-4 py-2">
                  <span className="font-medium">{r.name}</span>
                  <span className="ml-2 font-mono-tab text-xs text-(--color-ink-muted)">{r.id}</span>
                </td>
                <td className="px-4 py-2 font-mono-tab">{r.fire_count}</td>
                <td className="px-4 py-2 font-mono-tab">{r.reviewed}</td>
                <td className="px-4 py-2 font-mono-tab">{r.observed_precision?.toFixed(2)}</td>
                <td className="px-4 py-2 font-mono-tab">{r.configured_weight?.toFixed(2)}</td>
                <td className="px-4 py-2 font-mono-tab">{r.measured_log_odds?.toFixed(2)}</td>
                <td
                  className={cn(
                    "px-4 py-2 font-mono-tab",
                    r.recommendation !== "within_tolerance" && "text-(--color-status-review)"
                  )}
                >
                  {r.recommendation !== "within_tolerance" && "⚠ "}
                  {r.weight_drift?.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
