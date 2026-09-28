import { useCallback, useRef, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useIncidents } from "@/hooks/useIncidents";
import { IncidentRow } from "@/components/shared/IncidentRow";
import { EmptyState, ErrorState } from "@/components/shared/EmptyState";
import { IncidentRowSkeleton, Skeleton } from "@/components/shared/Skeleton";
import { usePageTitle } from "@/hooks/usePageTitle";
import { LANES, type TriageLane } from "@/lib/design";
import { cn } from "@/lib/utils";
import { SplitHeading } from "@/components/shared/SplitHeading";
import { ThemeSelect, type ThemeSelectOption } from "@/components/ui/ThemeSelect";

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
  const sortField = sort.replace(/^-/, "") as "risk" | "confidence" | "window_start";
  const items = (data?.items ?? [])
    .filter((i) => !department || i.department === department)
    .slice()
    .sort((a, b) =>
      sortField === "window_start"
        ? new Date(b.window.start).getTime() - new Date(a.window.start).getTime()
        : (b[sortField] ?? 0) - (a[sortField] ?? 0)
    );
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

  const departments = useMemo(
    () => [...new Set((data?.items ?? []).map((i) => i.department).filter(Boolean))] as string[],
    [data?.items]
  );

  const laneOptions: ThemeSelectOption[] = useMemo(
    () =>
      LANE_FILTERS.map((l) => ({
        value: l,
        label: l === "ALL" ? "All lanes" : LANES[l].word,
        badgeDotColor:
          l === "ALL"
            ? undefined
            : LANES[l].hex.startsWith("#")
            ? LANES[l].hex
            : "#716969",
      })),
    []
  );

  const stageOptions: ThemeSelectOption[] = useMemo(
    () =>
      STAGE_FILTERS.map((s) => ({
        value: s.value !== undefined ? String(s.value) : "",
        label: s.label,
      })),
    []
  );

  const departmentOptions: ThemeSelectOption[] = useMemo(
    () => [
      { value: "", label: "All departments" },
      ...departments.map((d) => ({ value: d, label: d })),
    ],
    [departments]
  );

  const sortOptions: ThemeSelectOption[] = useMemo(
    () => [
      { value: "-risk", label: "Risk" },
      { value: "-confidence", label: "Confidence" },
      { value: "-window_start", label: "Most recent" },
    ],
    []
  );

  return (
    <div className="flex flex-col gap-6">
      {/* Centered Page Header: Akira Heading & Mont Subheading */}
      <div className="flex flex-col items-center justify-center text-center pt-2 pb-2">
        <SplitHeading text="TRIAGE QUEUE" />
        <p className="mt-3 font-mont font-light text-xs sm:text-[13px] tracking-[0.2em] uppercase text-[#BCABAE]">
          {facets ? (
            <>
              {facets.lane?.AUTO_FLAG ?? 0} auto-flagged · {facets.lane?.ANALYST_REVIEW ?? 0} awaiting review · {facets.lane?.MONITOR ?? 0} monitored
            </>
          ) : (
            <Skeleton inline className="h-4 w-72 mx-auto" />
          )}
        </p>
      </div>

      {/* Glassmorphic Container for Filters and Incident Table */}
      <div className="glass-container rounded-2xl overflow-hidden">
        {/* Filter Bar with Animated Theme Dropdowns */}
        <div className="flex flex-wrap items-center gap-3 border-b border-white/[0.12] px-5 py-3.5 bg-white/[0.03] backdrop-blur-xl">
          <ThemeSelect
            ariaLabel="Filter by lane"
            value={lane}
            onValueChange={(val) => updateParam("lane", val === "ALL" ? undefined : val)}
            options={laneOptions}
          />
          <ThemeSelect
            ariaLabel="Filter by maximum kill-chain stage"
            value={stageMax !== undefined ? String(stageMax) : ""}
            onValueChange={(val) => updateParam("stage_max", val || undefined)}
            options={stageOptions}
          />
          <ThemeSelect
            ariaLabel="Filter by department"
            value={department}
            onValueChange={(val) => updateParam("department", val || undefined)}
            options={departmentOptions}
          />
          <div className="ml-auto flex items-center gap-2 text-sm text-[#BCABAE]">
            <span id="queue-sort-label" className="text-xs uppercase tracking-wider font-mont font-medium text-[#BCABAE]/80">Sort:</span>
            <ThemeSelect
              ariaLabel="Sort incidents"
              value={sort}
              onValueChange={(val) => updateParam("sort", val === "-risk" ? undefined : val)}
              options={sortOptions}
            />
          </div>
        </div>

        {/* Incidents Table / Virtualized Rows */}
        <div className="bg-transparent">
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
                      <IncidentRow item={item} />
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
