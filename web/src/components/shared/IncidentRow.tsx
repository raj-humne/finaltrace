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
      className="grid grid-cols-[auto_auto_1fr] items-start gap-x-4 gap-y-1.5 border-b border-(--color-hairline) px-4 py-3 hover:bg-(--color-surface)"
    >
      <div className="flex w-28 flex-col gap-1.5">
        <LaneChip lane={(item.triage_lane as TriageLane) ?? "MONITOR"} />
        <span className="font-mono-tab text-xl" style={{ color: emberForRisk(risk) }}>
          {risk.toFixed(0)}
        </span>
      </div>
      <div className="w-32 pt-0.5">
        <ConfidenceMeter value={item.confidence ?? 0} compact />
      </div>
      <div className="min-w-0">
        <div className="flex items-baseline justify-between gap-4">
          <span className="truncate text-sm font-medium">
            {item.user_name} <span className="font-normal text-(--color-ink-muted)">· {item.department}</span>
          </span>
          <ChainSpine size="sm" activeStages={item.killchain_stages ?? []} className="w-24 shrink-0" />
        </div>
        <p className="mt-0.5 truncate text-sm text-(--color-ink-secondary)">{item.headline}</p>
        <div className="mt-1 flex items-center gap-3 text-xs text-(--color-ink-muted)">
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
