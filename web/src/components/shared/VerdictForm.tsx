import { useState, type FormEvent } from "react";
import { useAuth } from "@/state/auth";
import { useReviewIncident } from "@/hooks/useReviewIncident";
import { cn } from "@/lib/utils";

const VERDICTS = [
  { value: "confirmed_threat", label: "Confirmed threat" },
  { value: "benign", label: "Benign" },
  { value: "inconclusive", label: "Inconclusive" },
] as const;

export function VerdictForm({ incidentId, closed, startedAt }: { incidentId: string; closed: boolean; startedAt: number }) {
  const { user } = useAuth();
  const [verdict, setVerdict] = useState<(typeof VERDICTS)[number]["value"] | null>(null);
  const [note, setNote] = useState("");
  const [proposeSuppression, setProposeSuppression] = useState(false);
  const [ruleId, setRuleId] = useState("");
  const mutation = useReviewIncident(incidentId);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!verdict || !user) return;
    await mutation.mutateAsync({
      verdict,
      note,
      analyst_id: user.analyst_id,
      time_to_triage_sec: Math.round((Date.now() - startedAt) / 1000),
      propose_suppression:
        verdict === "benign" && proposeSuppression && ruleId
          ? { scope: "user_rule", rule_id: ruleId, expires_at: new Date(Date.now() + 1000 * 60 * 60 * 24 * 180).toISOString() }
          : null,
    });
  }

  if (closed && !mutation.isSuccess) {
    return <p className="text-sm text-(--color-ink-secondary)">This incident is closed. See the review above.</p>;
  }

  if (mutation.isSuccess) {
    return <p className="text-sm text-(--color-ink-secondary)">Verdict saved.</p>;
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-4">
        {VERDICTS.map((v) => (
          <label key={v.value} className="flex items-center gap-2 text-sm">
            <input type="radio" name="verdict" value={v.value} checked={verdict === v.value} onChange={() => setVerdict(v.value)} />
            {v.label}
          </label>
        ))}
      </div>
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="note"
        rows={2}
        className="rounded-md border border-(--color-hairline) bg-(--color-surface) px-3 py-2 text-sm outline-none focus-visible:border-(--color-source-logon)"
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
                className="rounded-md border border-(--color-hairline) bg-(--color-surface-raised) px-2 py-1.5 text-sm"
              />
              <p className="text-xs text-(--color-ink-muted)">
                Created with status "proposed" — a detection engineer must activate it. An analyst cannot silence a rule alone.
              </p>
            </>
          )}
        </div>
      )}
      {mutation.isError && <p className="text-sm text-(--color-status-auto-flag)">Could not save the verdict. Try again.</p>}
      <div className="flex justify-end">
        <button
          type="submit"
          disabled={!verdict || mutation.isPending}
          className={cn("rounded-md bg-(--color-ink) px-4 py-2 text-sm font-medium text-(--color-page)", (!verdict || mutation.isPending) && "opacity-50")}
        >
          {mutation.isPending ? "Saving…" : "Save verdict"}
        </button>
      </div>
    </form>
  );
}
