import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Inbox } from "lucide-react";
import { useIncidents } from "@/hooks/useIncidents";
import { IncidentRow } from "@/components/shared/IncidentRow";
import { EmptyState, ErrorState } from "@/components/shared/EmptyState";
import { IncidentRowSkeleton, Skeleton } from "@/components/shared/Skeleton";
import { usePageTitle } from "@/hooks/usePageTitle";
import { useListShortcuts } from "@/lib/shortcuts";
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
  usePageTitle("Triage queue");
  // Filters live in the URL, not component state, so a filtered view
  // survives a refresh and can be shared or bookmarked as-is.
  const [searchParams, setSearchParams] = useSearchParams();
  const lane = (searchParams.get("lane") as TriageLane | null) ?? "ALL";
  const stageMax = searchParams.get("stage_max") ? Number(searchParams.get("stage_max")) : undefined;
  const department = searchParams.get("department") ?? "";
  const sort = searchParams.get("sort") ?? "-risk";

  const updateParam = useCallback(
    (key: string, value: string | undefined) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (!value) next.delete(key);
          else next.set(key, value);
          return next;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  const { data, isLoading, isError } = useIncidents({
    lane: lane === "ALL" ? undefined : lane,
    stage_max: stageMax,
    limit: 500,
  });

  // The live API always returns risk-desc and ignores `sort` (Track B, see
  // api/routers/incidents.py), so honour the sort choice client-side.
  const sortField = sort.replace(/^-/, "") as "risk" | "confidence";
  const items = (data?.items ?? [])
    .filter((i) => !department || i.department === department)
    .slice()
    .sort((a, b) => (b[sortField] ?? 0) - (a[sortField] ?? 0));
  const facets = data?.facets;

  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    // 92px fits the desktop single-row layout, but IncidentRow stacks into
    // 3 lines on mobile — real height varies by viewport, so measure each
    // row instead of trusting one fixed estimate (a fixed height here
    // silently overlapped rows on narrow screens).
    estimateSize: () => 92,
    overscan: 10,
  });

  const departments = [...new Set((data?.items ?? []).map((i) => i.department).filter(Boolean))] as string[];

  const navigate = useNavigate();
  const [selectedIndex, setSelectedIndex] = useState(0);
  useEffect(() => {
    setSelectedIndex((i) => Math.min(i, Math.max(0, items.length - 1)));
  }, [items.length]);
  useEffect(() => {
    virtualizer.scrollToIndex(selectedIndex, { align: "auto" });
  }, [selectedIndex, virtualizer]);
  useListShortcuts(
    items.length > 0
      ? {
          count: items.length,
          getSelectedIndex: () => selectedIndex,
          onMove: (delta) => setSelectedIndex((i) => Math.max(0, Math.min(items.length - 1, i + delta))),
          onOpen: () => {
            const item = items[selectedIndex];
            if (item) navigate(`/incidents/${item.incident_id}`);
          },
        }
      : null
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-(--color-accent)/10">
          <Inbox className="h-4.5 w-4.5 text-(--color-accent)" aria-hidden />
        </span>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Triage queue</h1>
          <p className="text-sm text-(--color-ink-secondary)">
            {facets ? (
              <>
                {facets.lane?.AUTO_FLAG ?? 0} auto-flagged · {facets.lane?.ANALYST_REVIEW ?? 0} awaiting review · {facets.lane?.MONITOR ?? 0} monitored
              </>
            ) : (
              <Skeleton inline className="h-4 w-72" />
            )}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-(--color-hairline) bg-(--color-surface) px-3 py-2">
        <select
          aria-label="Filter by lane"
          value={lane}
          onChange={(e) => updateParam("lane", e.target.value === "ALL" ? undefined : e.target.value)}
          className="rounded-md border border-(--color-hairline) bg-(--color-surface-raised) px-2 py-1.5 text-sm"
        >
          {LANE_FILTERS.map((l) => (
            <option key={l} value={l}>
              {l === "ALL" ? "All lanes" : LANES[l].word}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by maximum kill-chain stage"
          value={stageMax ?? ""}
          onChange={(e) => updateParam("stage_max", e.target.value || undefined)}
          className="rounded-md border border-(--color-hairline) bg-(--color-surface-raised) px-2 py-1.5 text-sm"
        >
          {STAGE_FILTERS.map((s) => (
            <option key={s.label} value={s.value ?? ""}>
              {s.label}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by department"
          value={department}
          onChange={(e) => updateParam("department", e.target.value || undefined)}
          className="rounded-md border border-(--color-hairline) bg-(--color-surface-raised) px-2 py-1.5 text-sm"
        >
          <option value="">All departments</option>
          {departments.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
        <div className="ml-auto flex items-center gap-2 text-sm text-(--color-ink-secondary)">
          <span id="queue-sort-label">Sort:</span>
          <select aria-labelledby="queue-sort-label" value={sort} onChange={(e) => updateParam("sort", e.target.value === "-risk" ? undefined : e.target.value)} className="rounded-md border border-(--color-hairline) bg-(--color-surface-raised) px-2 py-1.5">
            <option value="-risk">Risk</option>
            <option value="-confidence">Confidence</option>
          </select>
        </div>
      </div>

      <div className="rounded-xl border border-(--color-hairline) bg-(--color-surface-raised)">
        {isError && <ErrorState title="Could not load the triage queue." />}
        {!isError && isLoading && (
          <div>
            {Array.from({ length: 8 }, (_, i) => (
              <IncidentRowSkeleton key={i} />
            ))}
          </div>
        )}
        {!isError && !isLoading && items.length === 0 && (
          <EmptyState title={`No open incidents in this window. ${data?.total ?? 0} user-days were scored and stayed below the alert threshold.`} />
        )}
        {!isError && items.length > 0 && (
          <div ref={parentRef} className={cn("overflow-auto")} style={{ height: "70vh" }}>
            <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
              {virtualizer.getVirtualItems().map((virtualRow) => {
                const item = items[virtualRow.index];
                return (
                  <div
                    key={item.incident_id}
                    ref={virtualizer.measureElement}
                    data-index={virtualRow.index}
                    style={{ position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${virtualRow.start}px)` }}
                  >
                    <IncidentRow item={item} selected={virtualRow.index === selectedIndex} />
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
