import { useId, useMemo } from "react";
import { STAGE_NAMES, STAGE_RAMP, EMBER_STEPS } from "@/lib/design";
import { formatTime, formatDate } from "@/lib/utils";

export interface ChainSpineEventPin {
  ts: string;
  label: string;
  stage: number;
}

export interface ChainSpineCampaignPoint {
  date: string;
  stage: number;
  risk: number;
  headline: string;
  incidentId: string;
}

interface ChainSpineProps {
  size: "sm" | "lg" | "campaign";
  /** Stage indices (0-5) that were actually reached this incident/campaign. */
  activeStages: number[];
  events?: ChainSpineEventPin[];
  campaignPoints?: ChainSpineCampaignPoint[];
  onSelectCampaignPoint?: (incidentId: string) => void;
  className?: string;
}

const STAGE_COUNT = STAGE_NAMES.length;

/**
 * The kill-chain spine — the product's visual signature. ~120 lines of
 * hand-written SVG, deliberately not a chart library (docs/06 section 5.1, 11).
 * A six-stage horizontal rail: filled + joined where the chain advanced,
 * hollow where it did not.
 */
export function ChainSpine({ size, activeStages, events = [], campaignPoints, onSelectCampaignPoint, className }: ChainSpineProps) {
  const gradientId = useId();
  const glowId = useId();
  const activeSet = useMemo(() => new Set(activeStages), [activeStages]);
  const maxActive = activeStages.length ? Math.max(...activeStages) : -1;
  const minActive = activeStages.length ? Math.min(...activeStages) : STAGE_COUNT;
  const isCampaign = size === "campaign" && !!campaignPoints && campaignPoints.length > 0;

  const isSm = size === "sm";
  const width = isSm ? 96 : 800;
  const padX = isSm ? 4 : 24;
  const step = (width - padX * 2) / (STAGE_COUNT - 1);
  const stageX = (i: number) => padX + step * i;
  const dotR = isSm ? 3 : 6;
  const leadColor = maxActive >= 3 ? EMBER_STEPS[3] : STAGE_RAMP.dark;

  // Events sharing a stage AND a label (e.g. a 45-file burst macro citing
  // every file it touched as evidence) collapse into one "label ×45" pin
  // spanning first→last time, instead of 45 near-identical rows stacked
  // into an unreadable column — seen for real on the live-demo's
  // file_copy_burst scenario. Genuinely distinct labels at the same stage
  // still get their own row, stacked as before.
  const pinRows = useMemo(() => {
    if (isSm) return { rows: [], maxDepth: 0 };
    const groups = new Map<string, { ev: ChainSpineEventPin; count: number; lastTs: string }>();
    const order: string[] = [];
    for (const ev of events) {
      const key = `${ev.stage}::${ev.label}`;
      const existing = groups.get(key);
      if (existing) {
        existing.count += 1;
        if (ev.ts > existing.lastTs) existing.lastTs = ev.ts;
        if (ev.ts < existing.ev.ts) existing.ev = { ...existing.ev, ts: ev.ts };
      } else {
        groups.set(key, { ev, count: 1, lastTs: ev.ts });
        order.push(key);
      }
    }
    const counts = new Map<number, number>();
    const rows = order.map((key) => {
      const g = groups.get(key)!;
      const xKey = Math.max(0, Math.min(STAGE_COUNT - 1, g.ev.stage));
      const row = counts.get(xKey) ?? 0;
      counts.set(xKey, row + 1);
      const label = g.count > 1 ? `${g.ev.label} ×${g.count}` : g.ev.label;
      return { ev: { ...g.ev, label }, x: stageX(xKey), row, lastTs: g.count > 1 ? g.lastTs : undefined };
    });
    const maxDepth = counts.size ? Math.max(...counts.values()) : 0;
    return { rows, maxDepth };
  }, [events, isSm, stageX]);

  const pinRowHeight = 28;
  const height = isSm ? 20 : Math.max(88, 56 + pinRows.maxDepth * pinRowHeight);
  const railY = isSm ? height / 2 : 40;

  if (isCampaign) {
    return <CampaignSpine points={campaignPoints!} onSelect={onSelectCampaignPoint} className={className} />;
  }

  return (
    <div className={className}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height={height}
        role="img"
        aria-label={`Kill-chain progression through ${STAGE_NAMES.filter((_, i) => activeSet.has(i)).join(", ") || "no stages"}`}
        preserveAspectRatio={isSm ? "xMinYMid meet" : "none"}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={STAGE_RAMP.light} />
            <stop offset="100%" stopColor={leadColor} />
          </linearGradient>
          <filter id={glowId} x="-120%" y="-120%" width="340%" height="340%">
            <feGaussianBlur stdDeviation={isSm ? 1.5 : 3} result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {!isSm &&
          STAGE_NAMES.map((name, i) => (
            <text
              key={name}
              x={stageX(i)}
              y={14}
              textAnchor={i === 0 ? "start" : i === STAGE_COUNT - 1 ? "end" : "middle"}
              fontSize="10.5"
              letterSpacing="0.04em"
              className="fill-(--color-ink-muted)"
              style={{ fontFamily: "var(--font-interface)", fontWeight: 500 }}
            >
              {name}
            </text>
          ))}

        {Array.from({ length: STAGE_COUNT - 1 }, (_, i) => {
          const advanced = activeSet.has(i) && activeSet.has(i + 1) && i >= minActive && i + 1 <= maxActive;
          const traversed = i >= minActive && i + 1 <= maxActive;
          return (
            <line
              key={`seg-${i}`}
              x1={stageX(i)}
              y1={railY}
              x2={stageX(i + 1)}
              y2={railY}
              stroke={advanced || traversed ? `url(#${gradientId})` : "currentColor"}
              strokeOpacity={advanced || traversed ? 0.95 : 0.28}
              strokeWidth={advanced ? (isSm ? 3 : 5) : 1.25}
              strokeLinecap="round"
            >
              {!isSm && (
                <title>
                  {advanced
                    ? `${STAGE_NAMES[i]} → ${STAGE_NAMES[i + 1]}: this incident advanced the kill chain across this step`
                    : `${STAGE_NAMES[i]} → ${STAGE_NAMES[i + 1]}: not reached in this incident`}
                </title>
              )}
            </line>
          );
        })}

        {STAGE_NAMES.map((name, i) => {
          const active = activeSet.has(i);
          const isLead = active && i === maxActive;
          return (
            <circle
              key={`dot-${i}`}
              cx={stageX(i)}
              cy={railY}
              r={active ? dotR : dotR * 0.6}
              fill={active ? (isLead ? leadColor : STAGE_RAMP.dark) : "var(--color-surface)"}
              stroke={active ? (isLead ? leadColor : STAGE_RAMP.dark) : "currentColor"}
              strokeOpacity={active ? 1 : 0.4}
              strokeWidth={1.25}
              filter={isLead ? `url(#${glowId})` : undefined}
            >
              {!isSm && (
                <title>
                  {name}
                  {active ? (isLead ? " — furthest stage this incident reached" : " — reached") : " — not reached"}
                </title>
              )}
            </circle>
          );
        })}

        {!isSm &&
          pinRows.rows.map(({ ev, x, row, lastTs }, i) => {
            const pinY = railY + 20 + row * pinRowHeight;
            const anchor = x <= padX + 4 ? "start" : x >= width - padX - 4 ? "end" : "middle";
            return (
              <g key={`${ev.ts}-${i}`}>
                <line x1={x} y1={railY + dotR} x2={x} y2={pinY - 16} stroke="currentColor" strokeOpacity={0.35} strokeWidth={1} />
                <text x={x} y={pinY} textAnchor={anchor} fontSize="10" className="fill-(--color-ink-secondary)" style={{ fontFamily: "var(--font-mono)" }}>
                  {lastTs ? `${formatTime(ev.ts)}–${formatTime(lastTs)}` : formatTime(ev.ts)}
                </text>
                <text x={x} y={pinY + 13} textAnchor={anchor} fontSize="10" className="fill-(--color-ink)">
                  {ev.label}
                </text>
              </g>
            );
          })}
      </svg>
    </div>
  );
}

function CampaignSpine({ points, onSelect, className }: { points: ChainSpineCampaignPoint[]; onSelect?: (id: string) => void; className?: string }) {
  const gradientId = useId();
  const glowId = useId();
  const width = 800;
  const height = 120;
  const padX = 32;
  const padTop = 44;
  const t0 = new Date(points[0].date).getTime();
  const t1 = new Date(points[points.length - 1].date).getTime();
  const span = Math.max(1, t1 - t0);
  const x = (d: string) => padX + ((new Date(d).getTime() - t0) / span) * (width - padX * 2);
  const railY = height - 20;
  const yForStage = (stage: number) => railY - (stage / (STAGE_NAMES.length - 1)) * (railY - padTop);
  const lastPoint = points[points.length - 1];
  const leadColor = lastPoint.stage >= 3 ? EMBER_STEPS[3] : STAGE_RAMP.dark;

  // With many incidents in a campaign, labeling every point prints the same
  // stage name over and over, crammed close enough in time to overlap into
  // an unreadable blob (seen for real: 13 points, mostly "STAGING", packed
  // into 800px). Label only where the story actually changes — the first
  // point, the last, and every stage transition — and stagger those labels
  // onto a second tier whenever two of them still land too close together.
  const MIN_LABEL_GAP = 54;
  const placements = points.reduce<{ rows: { show: boolean; tier: number }[]; lastLabelX: number; lastTier: number }>(
    (acc, p, i) => {
      const isTransition = i === 0 || i === points.length - 1 || p.stage !== points[i - 1].stage;
      if (!isTransition) {
        acc.rows.push({ show: false, tier: 0 });
        return acc;
      }
      const px = x(p.date);
      const tier = px - acc.lastLabelX < MIN_LABEL_GAP ? (acc.lastTier === 0 ? 1 : 0) : 0;
      acc.rows.push({ show: true, tier });
      acc.lastLabelX = px;
      acc.lastTier = tier;
      return acc;
    },
    { rows: [], lastLabelX: -Infinity, lastTier: 0 }
  ).rows;

  return (
    <div className={className}>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img" aria-label="Campaign kill-chain progression over time">
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={STAGE_RAMP.light} />
            <stop offset="100%" stopColor={leadColor} />
          </linearGradient>
          <filter id={glowId} x="-150%" y="-150%" width="400%" height="400%">
            <feGaussianBlur stdDeviation={4} result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <line x1={padX} y1={railY} x2={width - padX} y2={railY} stroke="currentColor" strokeOpacity={0.25} strokeWidth={1} />
        {points.map((p, i) => {
          if (i === 0) return null;
          const prev = points[i - 1];
          return (
            <line
              key={`c-seg-${i}`}
              x1={x(prev.date)}
              y1={yForStage(prev.stage)}
              x2={x(p.date)}
              y2={yForStage(p.stage)}
              stroke={`url(#${gradientId})`}
              strokeOpacity={0.9}
              strokeWidth={3}
              strokeLinecap="round"
            />
          );
        })}
        {points.map((p, i) => {
          const isLast = p.incidentId === lastPoint.incidentId;
          const { show, tier } = placements[i];
          return (
            <g
              key={p.incidentId}
              tabIndex={0}
              role="button"
              aria-label={`${formatDate(p.date)}: ${p.headline}, ${STAGE_NAMES[p.stage]}, risk ${p.risk}`}
              onClick={() => onSelect?.(p.incidentId)}
              className="cursor-pointer outline-none"
            >
              <title>{`${formatDate(p.date)} — ${STAGE_NAMES[p.stage]} — ${p.headline} (risk ${p.risk.toFixed(1)})`}</title>
              <circle
                cx={x(p.date)}
                cy={yForStage(p.stage)}
                r={isLast ? 8 : show ? 6 : 4}
                fill={isLast ? leadColor : STAGE_RAMP.dark}
                fillOpacity={show || isLast ? 1 : 0.55}
                stroke="var(--color-surface)"
                strokeWidth={2}
                filter={isLast ? `url(#${glowId})` : undefined}
              />
              {show && (
                <>
                  <text
                    x={x(p.date)}
                    y={yForStage(p.stage) - 14 - tier * 11}
                    textAnchor="middle"
                    fontSize="10"
                    className="fill-(--color-ink-secondary)"
                    style={{ fontFamily: "var(--font-mono)" }}
                  >
                    {formatDate(p.date)}
                  </text>
                  <text x={x(p.date)} y={railY + 16 + tier * 11} textAnchor="middle" fontSize="10" className="fill-(--color-ink)">
                    {STAGE_NAMES[p.stage]}
                  </text>
                </>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
