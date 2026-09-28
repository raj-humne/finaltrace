import { STAGE_NAMES } from "@/lib/design";

export function KillChainHero() {
  const width = 1100;
  const height = 36;
  const padX = 70;
  const y = 18;
  const step = (width - padX * 2) / (STAGE_NAMES.length - 1);
  const xFor = (i: number) => padX + step * i;
  const pathD = `M ${xFor(0)} ${y} L ${xFor(STAGE_NAMES.length - 1)} ${y}`;
  const totalDuration = "4.2s";

  // Pre-calculated animation timings for the 6 dots across 4.2s
  // 6 dots at: 0%, 20%, 40%, 60%, 80%, 100%
  const dotTimings = [
    { start: 0, peak: 0.05, end: 0.14 },
    { start: 0.16, peak: 0.20, end: 0.28 },
    { start: 0.36, peak: 0.40, end: 0.48 },
    { start: 0.56, peak: 0.60, end: 0.68 },
    { start: 0.76, peak: 0.80, end: 0.88 },
    { start: 0.92, peak: 0.96, end: 1.0 },
  ];

  return (
    <div className="relative w-full overflow-hidden bg-transparent py-1">
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          width="100%"
          height="100%"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="Connected detection chain dots"
          className="relative min-w-[760px] max-h-10 w-full select-none bg-transparent"
        >
          <defs>
            {/* Pure white glow filter */}
            <filter id="cleanWhiteGlow" x="-60%" y="-60%" width="220%" height="220%">
              <feGaussianBlur in="SourceGraphic" stdDeviation="2.5" result="blur1" />
              <feGaussianBlur in="SourceGraphic" stdDeviation="5" result="blur2" />
              <feMerge>
                <feMergeNode in="blur2" />
                <feMergeNode in="blur1" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Clean minimal rail connection line */}
          <path
            d={pathD}
            fill="none"
            stroke="rgba(113, 105, 105, 0.4)"
            strokeWidth={1.8}
            strokeLinecap="round"
          />

          {/* Static dots (6 connected nodes) */}
          {STAGE_NAMES.map((_, i) => {
            const cx = xFor(i);
            const cy = y;
            const timing = dotTimings[i];

            return (
              <g key={i}>
                {/* Expanding ring ripple when the traveling light reaches this dot */}
                <circle
                  cx={cx}
                  cy={cy}
                  r={5}
                  fill="none"
                  stroke="#FFFFFF"
                  strokeWidth={1.5}
                  opacity={0}
                >
                  <animate
                    attributeName="r"
                    values="5; 16; 16"
                    keyTimes={`0; ${timing.peak}; 1`}
                    dur={totalDuration}
                    repeatCount="indefinite"
                  />
                  <animate
                    attributeName="opacity"
                    values={`0; ${timing.start > 0 ? "0;" : ""} 0.85; 0; 0`}
                    keyTimes={
                      timing.start > 0
                        ? `0; ${timing.start}; ${timing.peak}; ${timing.end}; 1`
                        : `0; ${timing.peak}; ${timing.end}; 1`
                    }
                    dur={totalDuration}
                    repeatCount="indefinite"
                  />
                </circle>

                {/* Base dot element that illuminates bright white when light passes through */}
                <circle
                  cx={cx}
                  cy={cy}
                  r={5}
                  fill="#0F0F0F"
                  stroke="#716969"
                  strokeWidth={2}
                  className="transition-colors duration-200"
                >
                  <animate
                    attributeName="fill"
                    values={
                      timing.start > 0
                        ? `#0F0F0F; #0F0F0F; #FFFFFF; #0F0F0F; #0F0F0F`
                        : `#FFFFFF; #0F0F0F; #0F0F0F; #0F0F0F`
                    }
                    keyTimes={
                      timing.start > 0
                        ? `0; ${timing.start}; ${timing.peak}; ${timing.end}; 1`
                        : `0; ${timing.end}; 0.95; 1`
                    }
                    dur={totalDuration}
                    repeatCount="indefinite"
                  />
                  <animate
                    attributeName="stroke"
                    values={
                      timing.start > 0
                        ? `#716969; #716969; #FFFFFF; #716969; #716969`
                        : `#FFFFFF; #716969; #716969; #716969`
                    }
                    keyTimes={
                      timing.start > 0
                        ? `0; ${timing.start}; ${timing.peak}; ${timing.end}; 1`
                        : `0; ${timing.end}; 0.95; 1`
                    }
                    dur={totalDuration}
                    repeatCount="indefinite"
                  />
                </circle>
              </g>
            );
          })}

          {/* Traveling Glowing White Light Dot (Clean, transparent, no colored aura or line behind it) */}
          <g>
            <animateMotion
              path={pathD}
              dur={totalDuration}
              repeatCount="indefinite"
              calcMode="linear"
            />
            {/* Opacity control: fade in at start, fade out cleanly at end */}
            <animate
              attributeName="opacity"
              values="0; 1; 1; 1; 0; 0"
              keyTimes="0; 0.04; 0.92; 0.98; 0.99; 1"
              dur={totalDuration}
              repeatCount="indefinite"
            />

            {/* Glowing white light halo */}
            <circle
              r={9}
              fill="#FFFFFF"
              opacity={0.8}
              filter="url(#cleanWhiteGlow)"
            />

            {/* Core white light dot */}
            <circle r={5} fill="#FFFFFF" />
          </g>
        </svg>
      </div>
    </div>
  );
}
