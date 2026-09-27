import type { components } from "@/lib/api/types.gen";
import { cn } from "@/lib/utils";
import { ScoreMeter } from "@/components/shared/ScoreMeter";

type MitigationActionOut = components["schemas"]["MitigationActionOut"];

type MitigationOutcome = "TRIGGERED" | "FAILED" | "NOT_TRIGGERED";

// TRIGGERED reuses the AUTO_FLAG red (web/src/lib/design.ts's LANES) — an
// automated mitigation firing is, by construction, the same severity tier
// as an auto-flagged incident. FAILED reuses the review/amber tone: the
// pipeline still ran, it just couldn't reach the remediation service.
const GLYPHS: Record<MitigationOutcome, string> = { TRIGGERED: "■", FAILED: "◧", NOT_TRIGGERED: "□" };
const COLORS: Record<MitigationOutcome, string> = {
  TRIGGERED: "#d03b3b",
  FAILED: "#ec835a",
  NOT_TRIGGERED: "var(--color-ink-muted)",
};
const WORDS: Record<MitigationOutcome, string> = {
  TRIGGERED: "Triggered",
  FAILED: "Failed",
  NOT_TRIGGERED: "Not triggered",
};

/** Glyph + word + color, never color alone — same accessibility rule as LaneChip (docs/06 section 4.4, 9). */
function MitigationStatusChip({ outcome, className }: { outcome: MitigationOutcome; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-sm font-medium", className)} style={{ color: COLORS[outcome] }}>
      <span aria-hidden className="text-[0.85em]">
        {GLYPHS[outcome]}
      </span>
      <span>{WORDS[outcome]}</span>
    </span>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-(--color-ink-muted)">{label}</div>
      <div className="font-mono-tab text-(--color-ink)">{value}</div>
    </div>
  );
}

/**
 * Automated mitigation pipeline result for this incident (Challenge 1). At
 * most one MitigationAction ever exists per incident (unique constraint,
 * idempotent by design), so `mitigations` is either empty (threat weight
 * never exceeded the configured threshold — no automatic action, not an
 * error) or has exactly one entry.
 */
export function MitigationPanel({ mitigations }: { mitigations: MitigationActionOut[] }) {
  const action = mitigations[0];
  const outcome: MitigationOutcome = !action ? "NOT_TRIGGERED" : action.status === "SUCCESS" ? "TRIGGERED" : "FAILED";

  return (
    <div className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium text-(--color-ink-secondary)">Automated mitigation</h2>
        <MitigationStatusChip outcome={outcome} />
      </div>

      {action ? (
        <div className="flex flex-col gap-4">
          <ScoreMeter
            label="Threat weight"
            value={action.threat_weight}
            threshold={action.threshold}
            thresholdLabel={`mitigation threshold ${action.threshold}`}
            className="max-w-md"
          />
          <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
            <Field label="Action" value={`${action.action_type} ${action.target_type.toUpperCase()}`} />
            <Field label="Target" value={action.target_value ?? "—"} />
            <Field
              label="Webhook"
              value={action.status === "SUCCESS" ? `Success (${action.webhook_status_code ?? "—"})` : "Failed"}
            />
            <Field
              label="Isolation"
              value={action.isolation_status === "SIMULATED_ISOLATED" ? "Simulated — isolated" : "Not isolated"}
            />
          </div>
          {action.error_message && <p className="text-xs text-(--color-ember-500)">{action.error_message}</p>}
          <p className="text-xs text-(--color-ink-muted)">
            {action.reason}
            {action.created_at && <> · recorded {new Date(action.created_at).toLocaleString()}</>}
          </p>
        </div>
      ) : (
        <p className="text-sm text-(--color-ink-muted)">
          This incident's threat weight has not exceeded the configured mitigation threshold, so no automated action was taken.
        </p>
      )}
    </div>
  );
}
