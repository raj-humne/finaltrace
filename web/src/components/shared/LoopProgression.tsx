import { useEffect, useState } from "react";

interface NodeInfo {
  id: number;
  label: string;
  x: number;
  y: number;
}

export function LoopProgression() {
  const [pulseIndex, setPulseIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setPulseIndex((prev) => (prev + 1) % 6);
    }, 1800);
    return () => clearInterval(timer);
  }, []);

  // 6 nodes arranged in a 2x3 connected track:
  // Top:    1 (Context)   --> 2 (Recon)        --> 3 (Staging)
  //                                                    |
  // Bottom: 6 (Evasion)   <-- 5 (Exfiltration) <-- 4 (Collection)
  // 6 nodes arranged in a 2x3 connected track:
  // Top:    1 (Context)   --> 2 (Recon)        --> 3 (Staging)
  //                                                    |
  // Bottom: 6 (Evasion)   <-- 5 (Exfiltration) <-- 4 (Collection)
  const nodes: NodeInfo[] = [
    { id: 1, label: "Context", x: 50, y: 32 },
    { id: 2, label: "Recon", x: 210, y: 32 },
    { id: 3, label: "Staging", x: 370, y: 32 },
    { id: 4, label: "Collection", x: 370, y: 102 },
    { id: 5, label: "Exfiltration", x: 210, y: 102 },
    { id: 6, label: "Evasion", x: 50, y: 102 },
  ];

  // Path connecting 1 -> 2 -> 3 -> 4 -> 5 -> 6 (leaving left side between 1 Context and 6 Evasion open)
  const pathD = "M 50 32 L 370 32 L 370 102 L 50 102";

  return (
    <div className="w-full max-w-[450px] rounded-xl border border-white/10 bg-white/[0.04] p-5 backdrop-blur-xl shadow-[0_8px_32px_0_rgba(0,0,0,0.37)]">
      <div className="flex items-center justify-between mb-3">
        <span className="font-mont text-[11px] font-medium uppercase tracking-[0.18em] text-[#BCABAE]/90">
          Correlated Attack Chain
        </span>
      </div>
      <svg
        viewBox="0 0 420 135"
        className="w-full h-auto"
        role="img"
        aria-label="6 connected detection nodes track"
      >
        {/* Background track line */}
        <path
          d={pathD}
          fill="none"
          stroke="rgba(113, 105, 105, 0.4)"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Animated pulse rail */}
        <path
          d={pathD}
          fill="none"
          stroke="#BCABAE"
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeDasharray="60 200"
          className="animate-[dash_6s_linear_infinite]"
        />

        {/* Render 6 connected nodes */}
        {nodes.map((node, i) => {
          const isActive = pulseIndex === i;
          return (
            <g key={node.id}>
              {/* Outer glow ring for active node */}
              {isActive && (
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={12}
                  fill="none"
                  stroke="#FBFBFB"
                  strokeWidth={1.5}
                  opacity={0.6}
                  className="animate-ping"
                />
              )}
              {/* Node dot */}
              <circle
                cx={node.x}
                cy={node.y}
                r={isActive ? 6 : 4.5}
                fill={isActive ? "#FBFBFB" : "#0F0F0F"}
                stroke={isActive ? "#FBFBFB" : "#BCABAE"}
                strokeWidth={2}
                className="transition-all duration-300"
              />
              {/* Node label */}
              <text
                x={node.x}
                y={node.y > 60 ? node.y + 19 : node.y - 12}
                textAnchor="middle"
                fontSize="11"
                fontFamily="'Mont', sans-serif"
                fontWeight={isActive ? 700 : 300}
                fill={isActive ? "#FBFBFB" : "#BCABAE"}
                className="transition-colors duration-300 tracking-wider"
              >
                {node.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
