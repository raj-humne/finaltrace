import { useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useIncidents } from "@/hooks/useIncidents";
import { IncidentRow } from "@/components/shared/IncidentRow";
import { EmptyState, ErrorState } from "@/components/shared/EmptyState";
import { LANES, type TriageLane } from "@/lib/design";
import { cn } from "@/lib/utils";

const LANE_FILTERS: (TriageLane | "ALL")[] = ["ALL", "AUTO_FLAG", "ANALYST_REVIEW", "MONITOR", "SUPPRESSED"];
const STAGE_FILTERS = [
  { label: "Any stage", value: undefined },
  { label: "Through recon", value: 1 },
  { label: "Through staging", value: 2 },
  { label: "Through collection", value: 3 },
  { label: "Through exfil", value: 4 },
];

export function QueuePage() {
  const [lane, setLane] = useState<TriageLane | "ALL">("ALL");
  const [stageMax, setStageMax] = useState<number | undefined>(undefined);
  const [department, setDepartment] = useState<string>("");
  const [sort, setSort] = useState("-risk");

  const { data, isLoading, isError } = useIncidents({
    lane: lane === "ALL" ? undefined : lane,
    stage_max: stageMax,
    sort,
    limit: 500,
  });

  const items = (data?.items ?? []).filter((i) => !department || i.department === department);
  const facets = data?.facets;

  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 92,
    overscan: 10,
  });

  const departments = [...new Set((data?.items ?? []).map((i) => i.department).filter(Boolean))] as string[];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Triage queue</h1>
        <p className="mt-1 text-sm text-(--color-ink-secondary)">
          {facets ? (
            <>
              {facets.lane?.AUTO_FLAG ?? 0} auto-flagged · {facets.lane?.ANALYST_REVIEW ?? 0} awaiting review · {facets.lane?.MONITOR ?? 0} monitored
            </>
          ) : (
            "Loading counts…"
          )}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-(--color-hairline) bg-(--color-surface) px-3 py-2">
        <select value={lane} onChange={(e) => setLane(e.target.value as TriageLane | "ALL")} className="rounded-md border border-(--color-hairline) bg-(--color-surface-raised) px-2 py-1.5 text-sm">
          {LANE_FILTERS.map((l) => (
            <option key={l} value={l}>
              {l === "ALL" ? "All lanes" : LANES[l].word}
            </option>
          ))}
        </select>
        <select
          value={stageMax ?? ""}
          onChange={(e) => setStageMax(e.target.value ? Number(e.target.value) : undefined)}
          className="rounded-md border border-(--color-hairline) bg-(--color-surface-raised) px-2 py-1.5 text-sm"
        >
          {STAGE_FILTERS.map((s) => (
            <option key={s.label} value={s.value ?? ""}>
              {s.label}
            </option>
          ))}
        </select>
        <select value={department} onChange={(e) => setDepartment(e.target.value)} className="rounded-md border border-(--color-hairline) bg-(--color-surface-raised) px-2 py-1.5 text-sm">
          <option value="">All departments</option>
          {departments.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
        <div className="ml-auto flex items-center gap-2 text-sm text-(--color-ink-secondary)">
          <span>Sort:</span>
          <select value={sort} onChange={(e) => setSort(e.target.value)} className="rounded-md border border-(--color-hairline) bg-(--color-surface-raised) px-2 py-1.5">
            <option value="-risk">Risk</option>
            <option value="-confidence">Confidence</option>
          </select>
        </div>
      </div>

      <div className="rounded-lg border border-(--color-hairline) bg-(--color-surface-raised)">
        {isError && <ErrorState title="Could not load the triage queue." />}
        {!isError && !isLoading && items.length === 0 && (
          <EmptyState title={`No open incidents in this window. ${data?.total ?? 0} user-days were scored and stayed below the alert threshold.`} />
        )}
        {!isError && items.length > 0 && (
          <div ref={parentRef} className={cn("overflow-auto")} style={{ height: "70vh" }}>
            <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
              {virtualizer.getVirtualItems().map((virtualRow) => {
                const item = items[virtualRow.index];
                return (
                  <div key={item.incident_id} style={{ position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${virtualRow.start}px)` }}>
                    <IncidentRow item={item} />
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
