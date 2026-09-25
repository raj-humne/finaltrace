import { useEffect, useRef, useState } from "react";
import { STAGE_NAMES, STAGE_RAMP, EMBER_STEPS } from "@/lib/design";

const STAGE_COPY: Record<(typeof STAGE_NAMES)[number], string> = {
  CONTEXT: "A logon, three hours late",
  RECON: "A download from an unfamiliar domain",
  STAGING: "Removable media, first time in months",
  COLLECTION: "Forty-seven files, one session",
  EXFILTRATION: "One upload, off the network",
  EVASION: "Nothing left to flag — alone",
};

/**
 * The kill-chain spine, reused as the login screen's hero. Every action in
 * the list reads as routine on its own; the connecting line is the thing
 * SentinelTrace actually sells. This is the same visual device as
 * ChainSpine (docs/06 section 2) rendered large and once, at rest — the
 * one page-load moment allowed outside the working screens.
 */
export function KillChainHero() {
  const railRef = useRef<SVGPathElement>(null);
  const [ready, setReady] = useState(false);
  const [pulse, setPulse] = useState(false);

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setReady(true);
    if (!reduced) {
      const t = setTimeout(() => setPulse(true), 450);
      return () => clearTimeout(t);
    }
  }, []);

  const width = 380;
  const height = 520;
  const padY = 46;
  const x = 46;
  const step = (height - padY * 2) / (STAGE_NAMES.length - 1);
  const yFor = (i: number) => padY + step * i;
  const pathD = STAGE_NAMES.map((_, i) => `${i === 0 ? "M" : "L"} ${x} ${yFor(i)}`).join(" ");

  return (
    <div className="relative h-full w-full overflow-hidden bg-[#0E1315]">
      <div
        className="pointer-events-none absolute -right-24 top-1/3 h-72 w-72 rounded-full opacity-25 blur-3xl"
        style={{ background: `radial-gradient(circle, ${EMBER_STEPS[3]}, transparent 70%)` }}
        aria-hidden
      />
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height="100%"
        preserveAspectRatio="xMidYMid slice"
        role="img"
        aria-label="Kill-chain progression: context, recon, staging, collection, exfiltration, evasion"
        className="relative"
      >
        <path
          d={pathD}
          fill="none"
          stroke="rgba(242,245,246,0.14)"
          strokeWidth={2}
          strokeLinecap="round"
        />
        <path
          ref={railRef}
          d={pathD}
          fill="none"
          stroke={STAGE_RAMP.dark}
          strokeWidth={2.5}
          strokeLinecap="round"
          pathLength={100}
          strokeDasharray={100}
          strokeDashoffset={ready ? 0 : 100}
          style={{ transition: ready ? "stroke-dashoffset 1.8s cubic-bezier(0.22, 1, 0.36, 1)" : "none" }}
        />

        {STAGE_NAMES.map((name, i) => {
          const isLast = i === STAGE_NAMES.length - 1;
          const cy = yFor(i);
          return (
            <g key={name} style={{ opacity: ready ? 1 : 0, transition: `opacity 0.5s ease ${0.15 + i * 0.12}s` }}>
              <circle
                cx={x}
                cy={cy}
                r={isLast ? 6.5 : 5}
                fill={isLast ? EMBER_STEPS[3] : "#0E1315"}
                stroke={isLast ? EMBER_STEPS[3] : STAGE_RAMP.dark}
                strokeWidth={2}
              />
              {isLast && (
                <circle cx={x} cy={cy} r={6.5} fill="none" stroke={EMBER_STEPS[3]} strokeWidth={2} opacity={pulse ? 0 : 0.9}>
                  {pulse && (
                    <animate attributeName="r" from="6.5" to="18" dur="1.6s" begin="0s" fill="freeze" />
                  )}
                  {pulse && <animate attributeName="opacity" from="0.9" to="0" dur="1.6s" begin="0s" fill="freeze" />}
                </circle>
              )}
              <text x={x + 20} y={cy - 6} fontSize="13" fontFamily="Archivo, sans-serif" fontWeight={600} letterSpacing="0.01em" fill="#F2F5F6">
                {name.charAt(0) + name.slice(1).toLowerCase()}
              </text>
              <text x={x + 20} y={cy + 12} fontSize="12" fontFamily="'Source Serif 4', serif" fontStyle="italic" fill="rgba(242,245,246,0.62)">
                {STAGE_COPY[name]}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
