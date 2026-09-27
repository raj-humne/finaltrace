import { useState, type FormEvent } from "react";
import { usePageTitle } from "@/hooks/usePageTitle";
import { api } from "@/lib/api/client";
import { cn, formatDateTime } from "@/lib/utils";
import type { components } from "@/lib/api/types.gen";

type VerifyTokenResponse = components["schemas"]["VerifyTokenResponse"];

/**
 * Deliberately NOT behind <Protected> (see App.tsx) - the entire point of a
 * verification token is that someone with no SentinelTrace account (HR, an
 * auditor, a judge) can confirm a flagged report is genuine and unaltered.
 * Calls the real POST /verify-token endpoint, which itself requires no auth
 * (api/routers/verification.py) - this page is a thin UI over that, nothing
 * about verification happens client-side.
 */
export function VerifyTokenPage() {
  usePageTitle("Verify a report");
  const [token, setToken] = useState("");
  const [result, setResult] = useState<VerifyTokenResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token.trim()) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    let data, apiError;
    try {
      ({ data, error: apiError } = await api.POST("/api/v1/verify-token", {
        body: { token: token.trim() },
      }));
    } catch {
      setSubmitting(false);
      setError("Could not reach the server. Check your connection and try again.");
      return;
    }
    setSubmitting(false);
    if (apiError) {
      const detail =
        typeof apiError === "object" && apiError !== null
          ? (apiError as { detail?: string }).detail
          : typeof apiError === "string"
            ? apiError
            : undefined;
      setError(detail || "This token could not be verified.");
      return;
    }
    setResult(data);
  }

  return (
    <div className="flex min-h-screen items-start justify-center bg-(--color-page) px-4 py-16">
      <div className="w-full max-w-lg">
        <h1 className="text-xl font-semibold text-(--color-ink)">Verify a SentinelTrace report</h1>
        <p className="mt-2 text-sm text-(--color-ink-secondary)">
          Paste a verification token to confirm it was genuinely issued by SentinelTrace and has not
          been altered. No account needed. Each token can be checked exactly once.
        </p>

        <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-3">
          <textarea
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Paste the token here"
            rows={4}
            aria-label="Verification token"
            className="w-full rounded-md border border-(--color-hairline) bg-(--color-surface) p-3 font-mono-tab text-xs text-(--color-ink) outline-none focus-visible:border-(--color-accent)"
          />
          <button
            type="submit"
            disabled={submitting || !token.trim()}
            className={cn(
              "rounded-md px-4 py-2 text-sm font-medium",
              "bg-(--color-accent) text-(--color-accent-ink) disabled:opacity-50",
            )}
          >
            {submitting ? "Checking…" : "Verify"}
          </button>
        </form>

        {error && (
          <div
            role="alert"
            className="mt-4 rounded-md border border-(--color-status-auto-flag) bg-(--color-surface) p-4"
          >
            <p className="text-sm font-medium text-(--color-status-auto-flag)">Not verified</p>
            <p className="mt-1 text-sm text-(--color-ink-secondary)">{error}</p>
          </div>
        )}

        {result && (
          <div
            role="status"
            className="mt-4 flex flex-col gap-4 rounded-md border border-(--color-ember-400) bg-(--color-surface) p-4"
          >
            <div>
              <p className="text-sm font-medium text-(--color-ember-400)">Genuine — verified</p>
              <p className="mt-1 text-xs text-(--color-ink-muted)">
                {result.user_id} · {formatDateTime(result.window_start)}–{formatDateTime(result.window_end)}
              </p>
            </div>

            {/* What the user actually did, not just a score — the same
                narrative and evidence bullets the analyst dashboard shows,
                re-read from the incident this token points to. */}
            {result.headline && <p className="text-base font-medium text-(--color-ink)">{result.headline}</p>}
            {result.summary && <p className="text-sm leading-relaxed text-(--color-ink-secondary)">{result.summary}</p>}
            {result.evidence.length > 0 && (
              <ul className="flex flex-col gap-1.5 border-t border-(--color-hairline) pt-3 text-sm text-(--color-ink)">
                {result.evidence.map((line, i) => (
                  <li key={i} className="flex gap-2">
                    <span aria-hidden className="text-(--color-ink-muted)">
                      &bull;
                    </span>
                    {line}
                  </li>
                ))}
              </ul>
            )}

            <dl className="grid grid-cols-2 gap-y-2 border-t border-(--color-hairline) pt-3 text-sm">
              <dt className="text-(--color-ink-muted)">Incident</dt>
              <dd className="font-mono-tab text-(--color-ink)">{result.incident_id}</dd>
              <dt className="text-(--color-ink-muted)">Risk</dt>
              <dd className="text-(--color-ink)">{result.risk.toFixed(1)}</dd>
              <dt className="text-(--color-ink-muted)">Confidence</dt>
              <dd className="text-(--color-ink)">{result.confidence.toFixed(2)}</dd>
              <dt className="text-(--color-ink-muted)">Lane</dt>
              <dd className="text-(--color-ink)">{result.triage_lane}</dd>
              <dt className="text-(--color-ink-muted)">Issued by</dt>
              <dd className="text-(--color-ink)">{result.issued_by}</dd>
              <dt className="text-(--color-ink-muted)">Issued at</dt>
              <dd className="text-(--color-ink)">{formatDateTime(result.issued_at)}</dd>
            </dl>
            <p className="text-xs text-(--color-ink-muted)">
              This token has now been consumed and cannot verify this report again.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
