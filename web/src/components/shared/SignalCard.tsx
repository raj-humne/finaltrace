import { cn } from "@/lib/utils";
import type { components } from "@/lib/api/types.gen";

type Signal = components["schemas"]["SignalDetailOut"];
type AttributionItem = components["schemas"]["AttributionItemOut"];

export function SignalCard({
  signal,
  attribution,
  risk,
  selected,
  onSelect,
}: {
  signal: Signal;
  attribution: AttributionItem | undefined;
  risk: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const pts = attribution?.delta ?? Math.round((signal.contribution ?? 0) * 20 * 10) / 10;
  const withoutSignal = attribution?.risk_without ?? Math.max(0, risk - pts);
  // `detail` is a free-form record (engine-specific per rule); Track A has
  // not populated feature/observed/threshold/z_self on every signal yet, so
  // treat each key as possibly absent rather than assuming the richer shape.
  const detail = (signal.detail ?? {}) as Record<string, unknown>;
  const asDisplay = (v: unknown): string | number | undefined =>
    typeof v === "number" || typeof v === "string" ? v : undefined;
  const feature = asDisplay(detail.feature);
  const observed = asDisplay(detail.observed);
  const threshold = asDisplay(detail.threshold);
  const zSelf = asDisplay(detail.z_self);
  return (
    <button
      onClick={onSelect}
      className={cn(
        "w-full border-b border-(--color-hairline) px-4 py-3 text-left last:border-b-0",
        selected ? "bg-(--color-surface)" : "hover:bg-(--color-surface)/60"
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <span className="text-xs font-medium uppercase tracking-wide text-(--color-ink-muted)">{signal.category}</span>
          <p className="text-sm">{signal.phrase}</p>
          {(observed != null || threshold != null) && (
            <p className="mt-0.5 font-mono-tab text-xs text-(--color-ink-muted)">
              {feature} · observed {observed} · threshold {threshold}
              {zSelf != null ? ` · z ${zSelf}` : ""}
            </p>
          )}
        </div>
        <span className="shrink-0 font-mono-tab text-sm text-(--color-ember-500)">
          +{pts.toFixed(1)}
        </span>
      </div>
      <p className="mt-1.5 text-sm text-(--color-ink-secondary)">
        Without this signal, risk would be {withoutSignal.toFixed(1)}.
        {attribution?.in_minimal_set && <span className="ml-1 text-(--color-ink)">✓ minimal set</span>}
      </p>
    </button>
  );
}
