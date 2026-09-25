import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatRisk(risk: number) {
  return risk.toFixed(1);
}

/**
 * docs/05-API-SPEC.md section 0 mandates timestamps as UTC with an explicit
 * offset. The live API serializes SQLite's naive datetimes without one
 * (`2010-08-14T21:47:03`, no `Z`), which JS's Date would otherwise parse as
 * local time. Treat any offset-less timestamp as UTC, per the documented
 * contract, rather than the browser's default.
 */
export function parseApiTimestamp(iso: string): Date {
  const hasOffset = /Z$|[+-]\d{2}:?\d{2}$/.test(iso);
  const withTime = iso.length === 10 ? `${iso}T00:00:00` : iso;
  return new Date(hasOffset ? withTime : `${withTime}Z`);
}

export function formatTime(iso: string) {
  const d = parseApiTimestamp(iso);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

export function formatDate(iso: string) {
  const d = parseApiTimestamp(iso);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
}

export function formatDateTime(iso: string) {
  return `${formatDate(iso)}, ${formatTime(iso)}`;
}
