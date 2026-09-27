import { useState } from "react";
import { useIssueVerificationToken } from "@/hooks/useVerificationToken";
import { cn } from "@/lib/utils";

/**
 * Only rendered for an AUTO_FLAG incident (checked by the caller,
 * IncidentPage.tsx) — issuing a token for anything else is rejected by the
 * backend with 403 (api/verification.py's IncidentNotFlagged), matching the
 * brief: a token proves a RAISED report is genuine, not every incident.
 */
export function VerificationPanel({ incidentId }: { incidentId: string }) {
  const mutation = useIssueVerificationToken(incidentId);
  const [copied, setCopied] = useState(false);

  async function copyToken(token: string) {
    try {
      await navigator.clipboard.writeText(token);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard permission denied — the token is still shown in the
      // textarea below, so selecting it by hand always works as a fallback.
    }
  }

  return (
    <div className="rounded-md border border-(--color-hairline) bg-(--color-surface) p-4">
      <h3 className="text-sm font-medium text-(--color-ink)">Verification token</h3>
      <p className="mt-1 text-sm text-(--color-ink-secondary)">
        Prove this report is genuine to anyone — no SentinelTrace account needed. Single-use: once
        checked, the same token cannot verify a report a second time.
      </p>

      {!mutation.data && (
        <button
          type="button"
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className={cn(
            "mt-3 rounded-md px-3 py-2 text-sm font-medium",
            "bg-(--color-accent) text-(--color-accent-ink) disabled:opacity-50",
          )}
        >
          {mutation.isPending ? "Issuing…" : "Issue a verification token"}
        </button>
      )}

      {mutation.isError && (
        <p role="alert" className="mt-2 text-sm text-(--color-status-auto-flag)">
          Could not issue a token — this incident may no longer be AUTO_FLAG.
        </p>
      )}

      {mutation.data && (
        <div className="mt-3 flex flex-col gap-2">
          <textarea
            readOnly
            value={mutation.data.token}
            rows={3}
            aria-label="Verification token"
            className="w-full rounded-md border border-(--color-hairline) bg-(--color-surface-raised) p-2 font-mono-tab text-xs text-(--color-ink)"
            onFocus={(e) => e.currentTarget.select()}
          />
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => copyToken(mutation.data!.token)}
              className="rounded-md border border-(--color-hairline) px-3 py-1.5 text-sm text-(--color-ink)"
            >
              {copied ? "Copied" : "Copy token"}
            </button>
            <a
              href="/verify"
              target="_blank"
              rel="noreferrer"
              className="text-sm text-(--color-accent) underline"
            >
              Open the verify page →
            </a>
            <button
              type="button"
              onClick={() => mutation.mutate()}
              className="text-sm text-(--color-ink-muted) underline"
            >
              issue another
            </button>
          </div>
          <p className="text-xs text-(--color-ink-muted)">
            Issued {new Date(mutation.data.issued_at).toLocaleString()}. {mutation.data.note}
          </p>
        </div>
      )}
    </div>
  );
}
