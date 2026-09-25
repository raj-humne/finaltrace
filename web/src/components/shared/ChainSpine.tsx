import { useMemo } from "react";
import { STAGE_NAMES, STAGE_RAMP } from "@/lib/design";
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
  const activeSet = useMemo(() => new Set(activeStages), [activeStages]);
  const maxActive = activeStages.length ? Math.max(...activeStages) : -1;
  const minActive = activeStages.length ? Math.min(...activeStages) : STAGE_COUNT;

  if (size === "campaign" && campaignPoints && campaignPoints.length > 0) {
    return <CampaignSpine points={campaignPoints} onSelect={onSelectCampaignPoint} className={className} />;
  }

  const isSm = size === "sm";
  const width = isSm ? 96 : 800;
  const height = isSm ? 20 : 88;
  const padX = isSm ? 4 : 24;
  const railY = isSm ? height / 2 : 40;
  const step = (width - padX * 2) / (STAGE_COUNT - 1);
  const stageX = (i: number) => padX + step * i;
  const dotR = isSm ? 3 : 6;

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
        {!isSm &&
          STAGE_NAMES.map((name, i) => (
            <text
              key={name}
              x={stageX(i)}
              y={14}
              textAnchor="middle"
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
              stroke={advanced || traversed ? STAGE_RAMP.dark : "currentColor"}
              strokeOpacity={advanced || traversed ? 0.85 : 0.28}
              strokeWidth={advanced ? (isSm ? 3 : 5) : 1.25}
              strokeLinecap="round"
            />
          );
        })}

        {STAGE_NAMES.map((_, i) => {
          const active = activeSet.has(i);
          return (
            <circle
              key={`dot-${i}`}
              cx={stageX(i)}
              cy={railY}
              r={active ? dotR : dotR * 0.6}
              fill={active ? STAGE_RAMP.dark : "var(--color-surface)"}
              stroke={active ? STAGE_RAMP.dark : "currentColor"}
              strokeOpacity={active ? 1 : 0.4}
              strokeWidth={1.25}
            />
          );
        })}

        {!isSm &&
          events.map((ev, i) => {
            const x = stageX(Math.max(0, Math.min(STAGE_COUNT - 1, ev.stage)));
            const pinY = railY + 14 + (i % 2) * 14;
            return (
              <g key={`${ev.ts}-${i}`}>
                <line x1={x} y1={railY + dotR} x2={x} y2={pinY - 6} stroke="currentColor" strokeOpacity={0.35} strokeWidth={1} />
                <text x={x} y={pinY} textAnchor="middle" fontSize="10" className="fill-(--color-ink-secondary)" style={{ fontFamily: "var(--font-mono)" }}>
                  {formatTime(ev.ts)}
                </text>
                <text x={x} y={pinY + 12} textAnchor="middle" fontSize="10" className="fill-(--color-ink)">
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

  return (
    <div className={className}>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img" aria-label="Campaign kill-chain progression over time">
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
              stroke={STAGE_RAMP.dark}
              strokeOpacity={0.8}
              strokeWidth={3}
              strokeLinecap="round"
            />
          );
        })}
        {points.map((p) => (
          <g key={p.incidentId} tabIndex={0} role="button" aria-label={`${formatDate(p.date)}: ${p.headline}, risk ${p.risk}`} onClick={() => onSelect?.(p.incidentId)} className="cursor-pointer outline-none">
            <circle cx={x(p.date)} cy={yForStage(p.stage)} r={7} fill={STAGE_RAMP.dark} stroke="var(--color-surface)" strokeWidth={2} />
            <text x={x(p.date)} y={yForStage(p.stage) - 12} textAnchor="middle" fontSize="10" className="fill-(--color-ink-secondary)" style={{ fontFamily: "var(--font-mono)" }}>
              {formatDate(p.date)}
            </text>
            <text x={x(p.date)} y={railY + 16} textAnchor="middle" fontSize="10" className="fill-(--color-ink)">
              {STAGE_NAMES[p.stage]}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
