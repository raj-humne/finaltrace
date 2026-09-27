import { useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useIncident, useIncidentGraph } from "@/hooks/useIncidents";
import { useCampaign } from "@/hooks/useCampaign";
import { ChainSpine } from "@/components/shared/ChainSpine";
import { ScoreMeter } from "@/components/shared/ScoreMeter";
import { LaneChip } from "@/components/shared/LaneChip";
import type { TriageLane } from "@/lib/design";
import { CorrelationGraph } from "@/components/shared/CorrelationGraph";
import { SignalCard } from "@/components/shared/SignalCard";
import { MitigationPanel } from "@/components/shared/MitigationPanel";
import { VerificationPanel } from "@/components/shared/VerificationPanel";
import { FeedbackDialog } from "@/components/shared/FeedbackDialog";
import { VerdictForm } from "@/components/shared/VerdictForm";
import { AskAssistant } from "@/components/shared/AskAssistant";
import { ErrorState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/shared/Skeleton";
import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { usePageTitle } from "@/hooks/usePageTitle";
import { formatDate, formatTime } from "@/lib/utils";

export function IncidentPage() {
  const { incidentId } = useParams<{ incidentId: string }>();
  const { data: incident, isLoading, isError } = useIncident(incidentId);
  const { data: graph } = useIncidentGraph(incidentId);
  const { data: campaign } = useCampaign(incident?.campaign?.campaign_id);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const startedAt = useRef(Date.now()).current;
  usePageTitle(incident?.narrative?.headline ?? incidentId);

  const activeStages = useMemo(
    () => [...new Set((incident?.signals ?? []).map((s) => s.stage).filter((s): s is number => s != null))].sort((a, b) => a - b),
    [incident]
  );

  // The graph endpoint doesn't populate node.stage yet (Track A gap — see
  // api/routers/incidents.py's GraphNodeOut, stage is always null). Signals
  // carry the real kill-chain stage per rule, so back-fill node stage from
  // whichever signal's evidence_event_ids covers that node.
  const stageByEventId = useMemo(() => {
    const map = new Map<string, number>();
    for (const s of incident?.signals ?? []) {
      for (const eid of s.evidence_event_ids ?? []) {
        if (s.stage != null) map.set(eid, s.stage);
      }
    }
    return map;
  }, [incident]);

  const enrichedGraphNodes = useMemo(
    () => (graph?.nodes ?? []).map((n) => ({ ...n, stage: n.id != null ? (stageByEventId.get(n.id) ?? n.stage) : n.stage })),
    [graph, stageByEventId]
  );

  const eventPins = useMemo(
    () =>
      enrichedGraphNodes
        .filter((n) => n.has_signal)
        .map((n) => ({ ts: n.ts!, label: n.label ?? n.action ?? "", stage: n.stage ?? 0 })),
    [enrichedGraphNodes]
  );

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-2">
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-7 w-2/3" />
          <Skeleton className="h-4 w-1/3" />
        </div>
        <div className="divide-y divide-(--color-hairline) rounded-lg border border-(--color-hairline) bg-(--color-surface-raised)">
          <div className="flex items-start gap-8 p-4">
            <Skeleton className="h-5 w-24" />
            <Skeleton className="h-10 flex-1" />
            <Skeleton className="h-10 flex-1" />
          </div>
          <div className="p-4">
            <Skeleton className="h-24 w-full max-w-[68ch]" />
          </div>
          <div className="p-4">
            <Skeleton className="h-24 w-full" />
          </div>
        </div>
      </div>
    );
  }
  if (isError || !incident) return <ErrorState title="Could not load this incident." />;

  const risk = incident.score?.risk ?? 0;
  const confidence = incident.score?.confidence ?? 0;
  // `window` is a free-form record (Pydantic dict[str, Any] mixing datetime and float fields).
  const windowStart = typeof incident.window?.start === "string" ? incident.window.start : undefined;
  const windowEnd = typeof incident.window?.end === "string" ? incident.window.end : undefined;
  const windowDurationMin = typeof incident.window?.duration_min === "number" ? incident.window.duration_min : undefined;
  const attributionBySignal = new Map((incident.attribution?.items ?? []).map((a) => [String(a.signal_id), a]));
  const selectedSignal = selectedId
    ? (incident.signals ?? []).find((s) => (s.evidence_event_ids ?? []).includes(selectedId) || String(s.signal_id) === selectedId)
    : undefined;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: "Queue", to: "/incidents" }, { label: incident.incident_id! }]} />
        <div className="mt-2 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{incident.narrative?.headline}</h1>
            {incident.user?.user_id && (
              <p className="mt-1 text-sm text-(--color-ink-secondary)">
                <Link to={`/users/${incident.user.user_id}`} className="text-(--color-accent) hover:underline">
                  View {incident.user.name ?? incident.user.user_id}&rsquo;s profile
                </Link>
              </p>
            )}
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2">
            <span className="font-mono-tab text-xs text-(--color-ink-muted)">{incident.incident_id}</span>
            <FeedbackDialog incidentId={incident.incident_id!} disabled={incident.disposition === "false_positive"} />
          </div>
        </div>
      </div>

      {/* One continuous document frame, hairline-divided — not a stack of
          identical cards. Only the correlation graph and evidence list get
          their own visual weight below because they're genuinely instruments
          and a set, not prose (docs/06 section 5.2). */}
      <div className="divide-y divide-(--color-hairline) rounded-lg border border-(--color-hairline) bg-(--color-surface-raised)">
        <div className="flex items-start gap-8 p-4">
          <LaneChip lane={(incident.score?.triage_lane as TriageLane) ?? "MONITOR"} className="mt-1 shrink-0" />
          <ScoreMeter label="Risk" value={risk} threshold={incident.attribution?.alert_threshold ?? 40} thresholdLabel={`alert at ${incident.attribution?.alert_threshold ?? 40}`} className="flex-1" />
          <ScoreMeter
            label="Confidence"
            value={confidence}
            max={1}
            threshold={0.65}
            thresholdLabel="auto-flag at 0.65"
            format={(v) => v.toFixed(2)}
            tone="neutral"
            className="flex-1"
          />
        </div>

        {incident.narrative?.summary && (
          <div className="p-4">
            <p className="font-narrative max-w-[68ch] text-lg leading-[1.55] text-(--color-ink)">{incident.narrative.summary}</p>
          </div>
        )}

        <div className="p-4">
          <h2 className="text-sm font-medium text-(--color-ink-secondary)">The chain</h2>
          <p className="mt-1 mb-4 text-sm text-(--color-ink-secondary)">
            <strong className="text-(--color-ink)">Filled</strong> = reached · <strong className="text-(--color-ink)">hollow</strong> = not reached · glowing dot = furthest stage.
          </p>
          <ChainSpine size="lg" activeStages={activeStages} events={eventPins} />
          {windowStart && windowEnd && (
            <p className="mt-2 text-xs text-(--color-ink-muted)">
              {formatDate(windowStart)}, {formatTime(windowStart)}-{formatTime(windowEnd)} · {windowDurationMin?.toFixed(1)} min
            </p>
          )}
        </div>

        {campaign && (
          <div className="p-4">
            <div className="mb-4 flex items-baseline justify-between">
              <h2 className="text-sm font-medium text-(--color-ink-secondary)">
                Campaign {campaign.campaign_id} spans {Math.round((new Date(campaign.last_seen!).getTime() - new Date(campaign.first_seen!).getTime()) / 86400000)} days
              </h2>
              <span className="font-mono-tab text-sm text-(--color-ember-500)">campaign risk {campaign.campaign_risk?.toFixed(1)}</span>
            </div>
            <ChainSpine
              size="campaign"
              activeStages={[]}
              campaignPoints={(campaign.stage_progression ?? []).map((p) => ({
                date: p.date!,
                stage: p.stage ?? 0,
                risk: p.risk ?? 0,
                headline: p.headline ?? "",
                incidentId: p.incident_id!,
              }))}
            />
            {campaign.narrative && <p className="font-narrative mt-4 max-w-[68ch] text-base leading-[1.55]">{campaign.narrative}</p>}
          </div>
        )}

        {graph && (
          <div className="p-4">
            <h2 className="mb-2 text-sm font-medium text-(--color-ink-secondary)">Correlation graph</h2>
            <CorrelationGraph nodes={enrichedGraphNodes} edges={graph.edges ?? []} selectedId={selectedId} onSelect={setSelectedId} overDense={graph.over_dense} />
          </div>
        )}

        <div>
          <div className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
            <h2 className="text-sm font-medium text-(--color-ink-secondary)">Evidence</h2>
            <span className="text-xs text-(--color-ink-muted)">{incident.attribution?.note}</span>
          </div>
          <div className="divide-y divide-(--color-hairline) border-t border-(--color-hairline)">
            {(incident.signals ?? [])
              .slice()
              .sort((a, b) => (attributionBySignal.get(String(b.signal_id))?.delta ?? 0) - (attributionBySignal.get(String(a.signal_id))?.delta ?? 0))
              .map((s) => (
                <SignalCard
                  key={s.signal_id}
                  signal={s}
                  attribution={attributionBySignal.get(String(s.signal_id))}
                  risk={risk}
                  selected={selectedId != null && ((s.evidence_event_ids ?? []).includes(selectedId) || selectedSignal?.signal_id === s.signal_id)}
                  onSelect={() => setSelectedId((s.evidence_event_ids ?? [])[0] ?? String(s.signal_id))}
                />
              ))}
          </div>
          {incident.attribution?.minimal_sufficient_set && (
            <p className="border-t border-(--color-hairline) px-4 py-3 text-sm text-(--color-ink-secondary)">
              {incident.attribution.minimal_sufficient_set.length} of these {incident.signals?.length ?? 0} signals are enough on their own to clear the threshold.
            </p>
          )}
        </div>

        <MitigationPanel mitigations={incident.mitigations ?? []} />

        {incident.score?.triage_lane === "AUTO_FLAG" && (
          <div className="p-4">
            <VerificationPanel incidentId={incident.incident_id!} />
          </div>
        )}

        <div className="p-4">
          <AskAssistant incidentId={incident.incident_id!} />
        </div>

        <div className="p-4">
          <h2 className="mb-3 text-sm font-medium text-(--color-ink-secondary)">Record a verdict</h2>
          <VerdictForm incidentId={incident.incident_id!} userId={incident.user?.user_id ?? ""} closed={incident.status === "closed"} startedAt={startedAt} />
        </div>
      </div>
    </div>
  );
}
