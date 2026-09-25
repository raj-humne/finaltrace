// Fixed, validated design tokens from docs/06-FRONTEND-DESIGN.md section 4.
// Do not re-pick these colors — they were run through a colorblind-safety
// validator in both light and dark mode.

export type TriageLane = "AUTO_FLAG" | "ANALYST_REVIEW" | "MONITOR" | "SUPPRESSED";

export const LANES: Record<TriageLane, { word: string; hex: string; glyph: "filled-square" | "half-square" | "hollow-square" | "dash" }> = {
  AUTO_FLAG: { word: "Auto-flag", hex: "#d03b3b", glyph: "filled-square" },
  ANALYST_REVIEW: { word: "Review", hex: "#ec835a", glyph: "half-square" },
  MONITOR: { word: "Monitor", hex: "#fab219", glyph: "hollow-square" },
  SUPPRESSED: { word: "Suppressed", hex: "var(--color-ink-muted)", glyph: "dash" },
};

export type EventSource = "file" | "logon" | "email" | "device" | "http";

// Fixed slot order — never cycled, never reassigned.
export const SOURCE_ORDER: EventSource[] = ["file", "logon", "email", "device", "http"];

export const SOURCE_LABELS: Record<EventSource, string> = {
  file: "File",
  logon: "Logon",
  email: "Email",
  device: "Device",
  http: "HTTP",
};

// Shape encoding for the correlation graph (section 7.1) — source moves to
// shape because five hues cannot clear all-pairs CVD separation.
export const SOURCE_SHAPES: Record<EventSource, "circle" | "diamond" | "square" | "hexagon" | "triangle"> = {
  file: "circle",
  logon: "diamond",
  email: "square",
  device: "hexagon",
  http: "triangle",
};

export const EMBER_STEPS = ["#FDE4C8", "#F9C68B", "#F0A24E", "#DE7F1C", "#B9640F", "#8F4B0C", "#6A360A"];

/** Map a 0-100 risk value onto the ember sequential ramp (steps 300-600 are the validated ordinal range). */
export function emberForRisk(risk: number): string {
  const clamped = Math.max(0, Math.min(100, risk));
  const idx = Math.min(6, Math.floor((clamped / 100) * 7));
  return EMBER_STEPS[idx];
}

export const STAGE_NAMES = ["CONTEXT", "RECON", "STAGING", "COLLECTION", "EXFILTRATION", "EVASION"] as const;

export const STAGE_RAMP = { light: "#cde2fb", dark: "#184f95" };

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Interpolate along the stage ramp by position (0-5) — a signal's color then encodes *where in the chain it sits*, not decoration. */
export function stageColor(stage: number): string {
  const t = Math.max(0, Math.min(1, stage / (STAGE_NAMES.length - 1)));
  const [r1, g1, b1] = hexToRgb(STAGE_RAMP.light);
  const [r2, g2, b2] = hexToRgb(STAGE_RAMP.dark);
  const mix = (a: number, b: number) => Math.round(a + (b - a) * t);
  return `rgb(${mix(r1, r2)}, ${mix(g1, g2)}, ${mix(b1, b2)})`;
}
