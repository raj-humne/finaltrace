import { Link } from "react-router-dom";
import { LaneChip } from "./LaneChip";
import { ConfidenceMeter } from "./ConfidenceMeter";
import { ChainSpine } from "./ChainSpine";
import { emberForRisk, type TriageLane } from "@/lib/design";
import { formatDate, formatDateTime } from "@/lib/utils";
import type { components } from "@/lib/api/types.gen";

type IncidentListItem = components["schemas"]["IncidentListItem"];

function contextLine(item: IncidentListItem): string {
  if (item.campaign_id) return "Part of a campaign";
  return item.status === "closed" ? "Reviewed" : "First incident";
}

export function IncidentRow({ item }: { item: IncidentListItem }) {
  const risk = item.risk ?? 0;
  return (
    <Link
      to={`/incidents/${item.incident_id}`}
      className="flex flex-col gap-2 border-b border-white/[0.08] px-5 py-3.5 hover:bg-white/[0.06] transition-colors sm:grid sm:grid-cols-[auto_auto_1fr] sm:items-start sm:gap-x-4 sm:gap-y-1.5"
    >
      <div className="flex items-center gap-3 sm:w-28 sm:flex-col sm:items-start sm:gap-1.5">
        <LaneChip lane={(item.triage_lane as TriageLane) ?? "MONITOR"} />
        <span className="font-mono-tab text-xl" style={{ color: emberForRisk(risk) }}>
          {risk.toFixed(0)}
        </span>
      </div>
      <div className="w-32 sm:pt-0.5">
        <ConfidenceMeter value={item.confidence ?? 0} compact />
      </div>
      <div className="min-w-0">
        <div className="flex items-baseline justify-between gap-4">
          <span className="truncate text-sm font-medium">
            {item.user_name} <span className="font-normal text-(--color-ink-muted)">· {item.department}</span>
          </span>
          <ChainSpine size="sm" activeStages={item.killchain_stages ?? []} className="hidden w-24 shrink-0 sm:block" />
        </div>
        <p className="mt-0.5 truncate text-sm text-(--color-ink-secondary)">{item.headline}</p>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-(--color-ink-muted)">
          <span className="font-mono-tab">{item.window?.start ? formatDateTime(item.window.start) : ""}</span>
          <span>{contextLine(item)}</span>
        </div>
      </div>
    </Link>
  );
}

export function formatQueueDate(iso: string) {
  return formatDate(iso);
}
