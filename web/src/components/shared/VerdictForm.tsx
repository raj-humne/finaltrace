import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/state/auth";
import { useReviewIncident } from "@/hooks/useReviewIncident";
import { cn } from "@/lib/utils";

const VERDICT_TINT: Record<string, string> = {
  confirmed_threat: "var(--color-status-auto-flag)",
  benign: "var(--color-accent)",
  inconclusive: "var(--color-ink-muted)",
};

const VERDICTS = [
  { value: "confirmed_threat", label: "Confirmed threat" },
  { value: "benign", label: "Benign" },
  { value: "inconclusive", label: "Inconclusive" },
] as const;

export function VerdictForm({
  incidentId,
  userId,
  closed,
  startedAt,
}: {
  incidentId: string;
  userId: string;
  closed: boolean;
  startedAt: number;
}) {
  const { user } = useAuth();
  const [verdict, setVerdict] = useState<(typeof VERDICTS)[number]["value"] | null>(null);
  const [note, setNote] = useState("");
  const [proposeSuppression, setProposeSuppression] = useState(false);
  const [ruleId, setRuleId] = useState("");
  const mutation = useReviewIncident(incidentId);
  const [settled, setSettled] = useState(false);

  useEffect(() => {
    if (mutation.isSuccess) {
      const t = setTimeout(() => setSettled(true), 200);
      return () => clearTimeout(t);
    }
  }, [mutation.isSuccess]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!verdict || !user) return;
    await mutation.mutateAsync({
      verdict,
      note,
      analyst_id: user.username,
      time_to_triage_sec: Math.round((Date.now() - startedAt) / 1000),
      propose_suppression:
        verdict === "benign" && proposeSuppression && ruleId
          ? { scope: "user_rule", user_id: userId, rule_id: ruleId, expires_at: new Date(Date.now() + 1000 * 60 * 60 * 24 * 180).toISOString() }
          : null,
    });
  }

  if (closed && !mutation.isSuccess) {
    return <p className="text-sm text-(--color-ink-secondary)">This incident is closed. See the review above.</p>;
  }

  if (mutation.isSuccess) {
    const tint = (verdict && VERDICT_TINT[verdict]) ?? "var(--color-ink-muted)";
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex items-center gap-2.5 rounded-md py-1.5 pl-3 transition-colors duration-200"
        style={{
          borderLeft: `2px solid ${tint}`,
          backgroundColor: settled ? "transparent" : `color-mix(in srgb, ${tint} 12%, transparent)`,
        }}
      >
        <p className="text-sm text-(--color-ink-secondary)">Verdict saved.</p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3">
      <fieldset className="flex flex-wrap gap-4">
        <legend className="sr-only">Verdict</legend>
        {VERDICTS.map((v) => (
          <label key={v.value} className="flex items-center gap-2 text-sm">
            <input type="radio" name="verdict" value={v.value} checked={verdict === v.value} onChange={() => setVerdict(v.value)} />
            {v.label}
          </label>
        ))}
      </fieldset>
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="note"
        aria-label="Note"
        rows={2}
        className="rounded-md border border-(--color-hairline) bg-(--color-surface) px-3 py-2 text-sm outline-none focus-visible:border-(--color-accent)"
      />
      {verdict === "benign" && (
        <div className="flex flex-col gap-2 rounded-md border border-(--color-hairline) bg-(--color-surface) p-3">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={proposeSuppression} onChange={(e) => setProposeSuppression(e.target.checked)} />
            Propose a suppression for this user + rule
          </label>
          {proposeSuppression && (
            <>
              <input
                value={ruleId}
                onChange={(e) => setRuleId(e.target.value)}
                placeholder="rule_id, e.g. stage.usb_after_dormancy"
                aria-label="Rule ID to suppress"
                spellCheck={false}
                className="rounded-md border border-(--color-hairline) bg-(--color-surface-raised) px-2 py-1.5 text-sm"
              />
              <p className="text-xs text-(--color-ink-muted)">
                Created with status "proposed". A detection engineer must activate it. An analyst cannot silence a rule alone.
              </p>
            </>
          )}
        </div>
      )}
      {mutation.isError && (
        <p role="alert" aria-live="polite" className="text-sm text-(--color-status-auto-flag)">
          Could not save the verdict. Try again.
        </p>
      )}
      <div className="flex justify-end">
        <button
          type="submit"
          disabled={!verdict || mutation.isPending}
          className={cn("rounded-md bg-(--color-accent) px-4 py-2 text-sm font-medium text-(--color-accent-ink)", (!verdict || mutation.isPending) && "opacity-50")}
        >
          {mutation.isPending ? "Saving…" : "Save verdict"}
        </button>
      </div>
    </form>
  );
}
