import { useState, type FormEvent } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useIncidentFeedback } from "@/hooks/useIncidentFeedback";
import { cn } from "@/lib/utils";
import type { components } from "@/lib/api/types.gen";

type ReasonCode = components["schemas"]["FeedbackRequest"]["reason_code"];
type FeedbackResponse = components["schemas"]["FeedbackResponse"];

const REASON_CODES: { value: ReasonCode; label: string }[] = [
  { value: "approved_business_activity", label: "Approved business activity" },
  { value: "expected_off_hours_work", label: "Expected off-hours work" },
  { value: "known_usb_workflow", label: "Known USB workflow" },
  { value: "known_host_access", label: "Known host access" },
  { value: "expected_bulk_access", label: "Expected bulk access" },
  { value: "test_or_training", label: "Test or training activity" },
  { value: "other", label: "Other" },
];

const MAX_COMMENT_LENGTH = 500;

function SuccessSummary({ result }: { result: FeedbackResponse }) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-(--color-ink)">
        Marked as a false positive. The system will prioritize this pattern lower for this user going forward.
      </p>
      <div className="grid grid-cols-3 gap-3 rounded-md border border-(--color-hairline) bg-(--color-surface) p-3 text-sm">
        <div>
          <div className="text-xs text-(--color-ink-muted)">Original risk</div>
          <div className="font-mono-tab text-(--color-ink)">{result.score_impact.original_risk.toFixed(1)}</div>
        </div>
        <div>
          <div className="text-xs text-(--color-ink-muted)">Predicted similar risk</div>
          <div className="font-mono-tab text-(--color-ink)">{result.score_impact.predicted_similar_risk.toFixed(1)}</div>
        </div>
        <div>
          <div className="text-xs text-(--color-ink-muted)">Expected reduction</div>
          <div className="font-mono-tab text-(--color-accent)">-{result.score_impact.expected_reduction.toFixed(1)}</div>
        </div>
      </div>
      {(result.updated_baselines.length > 0 || result.updated_edges.length > 0) && (
        <div className="flex flex-col gap-2 text-xs text-(--color-ink-secondary)">
          {result.updated_baselines.length > 0 && (
            <p>
              Updated {result.updated_baselines.length} behavioral baseline{result.updated_baselines.length === 1 ? "" : "s"}:{" "}
              {result.updated_baselines.map((b) => b.feature_name).join(", ")}
            </p>
          )}
          {result.updated_edges.length > 0 && (
            <p>
              Decayed {result.updated_edges.length} correlation edge weight{result.updated_edges.length === 1 ? "" : "s"} for this user's
              chain.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Analyst Feedback Loop for False-Positive Reduction (Challenge 2). Reuses
 * @radix-ui/react-dialog (already installed, used nowhere else yet) rather
 * than adding a second dialog library. Distinct from VerdictForm's inline
 * review form: this is a deliberate, higher-friction modal confirmation,
 * because unlike an ordinary verdict it also mutates this user's future
 * scoring (behavioral baseline + correlation-edge weights), not just this
 * incident's status.
 */
export function FeedbackDialog({ incidentId, disabled }: { incidentId: string; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  const [reasonCode, setReasonCode] = useState<ReasonCode | "">("");
  const [comment, setComment] = useState("");
  const [applyToSimilar, setApplyToSimilar] = useState(true);
  const mutation = useIncidentFeedback(incidentId);

  function reset() {
    setReasonCode("");
    setComment("");
    setApplyToSimilar(true);
    mutation.reset();
  }

  function onOpenChange(next: boolean) {
    if (!next) reset();
    setOpen(next);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!reasonCode) return;
    await mutation.mutateAsync({
      verdict: "false_positive",
      reason_code: reasonCode,
      comment: comment.trim() || null,
      apply_to_similar: applyToSimilar,
    });
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Trigger asChild>
        <button
          type="button"
          disabled={disabled}
          className={cn(
            "rounded-md border border-(--color-hairline) px-3 py-1.5 text-sm font-medium text-(--color-ink-secondary) hover:text-(--color-ink)",
            disabled && "cursor-not-allowed opacity-50"
          )}
        >
          Mark as false positive
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-(--color-hairline) bg-(--color-surface-raised) p-5 shadow-xl focus:outline-none">
          <Dialog.Title className="text-base font-semibold text-(--color-ink)">Dismiss incident as false positive</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-(--color-ink-secondary)">
            Record why this incident's evidence is not a real threat. This closes the incident and, unless you opt out below, adjusts
            future scoring for this user's similar activity.
          </Dialog.Description>

          {mutation.isSuccess && mutation.data ? (
            <div className="mt-4 flex flex-col gap-4">
              <SuccessSummary result={mutation.data} />
              <div className="flex justify-end">
                <Dialog.Close asChild>
                  <button
                    type="button"
                    className="rounded-md bg-(--color-accent) px-4 py-2 text-sm font-medium text-(--color-accent-ink)"
                  >
                    Done
                  </button>
                </Dialog.Close>
              </div>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="mt-4 flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="feedback-reason-code" className="text-sm font-medium text-(--color-ink-secondary)">
                  Reason
                </label>
                <select
                  id="feedback-reason-code"
                  value={reasonCode}
                  onChange={(e) => setReasonCode(e.target.value as ReasonCode)}
                  required
                  className="rounded-md border border-(--color-hairline) bg-(--color-surface) px-3 py-2 text-sm text-(--color-ink) outline-none focus-visible:border-(--color-accent)"
                >
                  <option value="" disabled>
                    Select a reason&hellip;
                  </option>
                  {REASON_CODES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="feedback-comment" className="text-sm font-medium text-(--color-ink-secondary)">
                  Note <span className="font-normal text-(--color-ink-muted)">(optional)</span>
                </label>
                <textarea
                  id="feedback-comment"
                  value={comment}
                  onChange={(e) => setComment(e.target.value.slice(0, MAX_COMMENT_LENGTH))}
                  maxLength={MAX_COMMENT_LENGTH}
                  rows={3}
                  placeholder="Add context for other analysts…"
                  className="rounded-md border border-(--color-hairline) bg-(--color-surface) px-3 py-2 text-sm outline-none focus-visible:border-(--color-accent)"
                />
                <span className="self-end text-xs text-(--color-ink-muted)">
                  {comment.length}/{MAX_COMMENT_LENGTH}
                </span>
              </div>

              <label className="flex items-start gap-2 text-sm text-(--color-ink)">
                <input
                  type="checkbox"
                  checked={applyToSimilar}
                  onChange={(e) => setApplyToSimilar(e.target.checked)}
                  className="mt-0.5"
                />
                <span>Learn from this decision and reduce alerts for similar behavior by this user.</span>
              </label>

              {mutation.isError && (
                <p role="alert" aria-live="polite" className="text-sm text-(--color-status-auto-flag)">
                  {(() => {
                    const err = mutation.error;
                    const detail =
                      typeof err === "object" && err !== null
                        ? (err as { detail?: string }).detail
                        : typeof err === "string"
                          ? err
                          : undefined;
                    return detail || "Could not record this feedback. Try again.";
                  })()}
                </p>
              )}

              <div className="flex justify-end gap-2">
                <Dialog.Close asChild>
                  <button
                    type="button"
                    className="rounded-md border border-(--color-hairline) px-4 py-2 text-sm font-medium text-(--color-ink-secondary)"
                  >
                    Cancel
                  </button>
                </Dialog.Close>
                <button
                  type="submit"
                  disabled={!reasonCode || mutation.isPending}
                  className={cn(
                    "rounded-md bg-(--color-accent) px-4 py-2 text-sm font-medium text-(--color-accent-ink)",
                    (!reasonCode || mutation.isPending) && "opacity-50"
                  )}
                >
                  {mutation.isPending ? "Submitting…" : "Confirm false positive"}
                </button>
              </div>
            </form>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
