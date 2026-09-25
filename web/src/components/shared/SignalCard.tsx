import { cn } from "@/lib/utils";
import type { components } from "@/lib/api/types.gen";

type Signal = components["schemas"]["Signal"];
type AttributionItem = components["schemas"]["AttributionItem"];

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
          {signal.detail && (signal.detail.observed != null || signal.detail.threshold != null) && (
            <p className="mt-0.5 font-mono-tab text-xs text-(--color-ink-muted)">
              {signal.detail.feature} · observed {signal.detail.observed} · threshold {signal.detail.threshold}
              {signal.detail.z_self != null ? ` · z ${signal.detail.z_self}` : ""}
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
