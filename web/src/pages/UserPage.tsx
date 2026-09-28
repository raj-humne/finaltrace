import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useUser, useUserRisk } from "@/hooks/useUsers";
import { useIncidents } from "@/hooks/useIncidents";
import { RiskTrendChart } from "@/components/shared/RiskTrendChart";
import { WorkingWindowBar } from "@/components/shared/WorkingWindowBar";
import { LaneChip } from "@/components/shared/LaneChip";
import { ErrorState } from "@/components/shared/EmptyState";
import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { usePageTitle } from "@/hooks/usePageTitle";
import { emberForRisk, type TriageLane } from "@/lib/design";
import { formatDate } from "@/lib/utils";

export function UserPage() {
  const { userId } = useParams<{ userId: string }>();
  const { data: user, isError } = useUser(userId);
  usePageTitle(user?.name ?? userId);
  const { data: risk } = useUserRisk(userId);
  const { data: incidents } = useIncidents({ user_id: userId, sort: "-risk", limit: 50 });

  const points = useMemo(() => {
    const bandByDate = new Map((risk?.peer_band ?? []).map((b) => [b.date, b]));
    return (risk?.series ?? []).map((s) => ({
      date: s.date!,
      risk: s.risk ?? 0,
      p50: bandByDate.get(s.date)?.p50 ?? 0,
      p90: bandByDate.get(s.date)?.p90 ?? 0,
    }));
  }, [risk]);

  if (isError || !user) return <ErrorState title="Could not load this user." />;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: "Users", to: "/users" }, { label: user.name ?? user.user_id! }]} />
        <div className="mt-2 flex items-baseline gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{user.name}</h1>
          <span className="font-mono-tab text-sm text-(--color-ink-muted)">{user.user_id}</span>
        </div>
        <p className="mt-1 text-sm text-(--color-ink-secondary)">
          {user.org?.role}, {user.org?.department} · reports to {user.org?.supervisor} · {user.org?.cohort_size} in cohort
          {user.departure_date && <> · departing {formatDate(user.departure_date)}</>}
        </p>
      </div>

      <section className="glass-card rounded-2xl p-5">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-(--color-ink-secondary)">Risk over time</h2>
          {risk?.summary && (
            <span className="text-xs text-(--color-ink-muted)">
              peak <span className="font-mono-tab" style={{ color: emberForRisk(risk.summary.peak_risk ?? 0) }}>{risk.summary.peak_risk?.toFixed(1)}</span> on{" "}
              {risk.summary.peak_date && formatDate(risk.summary.peak_date)}
            </span>
          )}
        </div>
        {points.length > 0 ? <RiskTrendChart points={points} /> : <p className="py-8 text-center text-sm text-(--color-ink-muted)">No scored days in this window.</p>}
      </section>

      <section className="glass-card rounded-2xl p-5">
        {user.baseline?.working_window?.start_min != null && user.baseline?.working_window?.end_min != null ? (
          <WorkingWindowBar startMin={user.baseline.working_window.start_min} endMin={user.baseline.working_window.end_min} />
        ) : (
          <p className="text-sm text-(--color-ink-muted)">
            This user has {user.baseline?.days_available ?? 0} days of history. Self-baseline rules are suppressed until 14; peer comparison is active.
          </p>
        )}
      </section>

      <section className="glass-card rounded-2xl overflow-hidden">
        <h2 className="border-b border-white/10 px-5 py-3.5 text-sm font-medium text-(--color-ink-secondary)">
          Incidents ({incidents?.total ?? 0})
        </h2>
        {(incidents?.items ?? []).map((inc) => (
          <Link key={inc.incident_id} to={`/incidents/${inc.incident_id}`} className="flex items-center gap-4 border-b border-(--color-hairline) px-4 py-3 last:border-b-0 hover:bg-(--color-surface)">
            <LaneChip lane={(inc.triage_lane as TriageLane) ?? "MONITOR"} className="w-32 shrink-0" />
            <span className="font-mono-tab text-sm" style={{ color: emberForRisk(inc.risk ?? 0) }}>
              {inc.risk?.toFixed(1)}
            </span>
            <span className="flex-1 truncate text-sm">{inc.headline}</span>
            <span className="shrink-0 text-xs text-(--color-ink-muted)">{inc.window?.start && formatDate(inc.window.start)}</span>
          </Link>
        ))}
        {(incidents?.items?.length ?? 0) === 0 && <p className="px-4 py-6 text-sm text-(--color-ink-muted)">No incidents for this user.</p>}
      </section>
    </div>
  );
}
