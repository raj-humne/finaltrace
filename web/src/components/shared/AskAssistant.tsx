import { useState, type FormEvent } from "react";
import { useAskIncident } from "@/hooks/useAskIncident";
import { cn } from "@/lib/utils";

interface Turn {
  question: string;
  answer?: string;
  error?: string;
}

/**
 * Grounded Q&A over one incident's already-computed evidence. Deliberately
 * NOT the authoritative record - that stays the deterministic narrative
 * above (ADR 0004). This is the "optional v2 gloss" that ADR explicitly
 * names as the safe next step: answers can only cite what's already stored
 * for this incident, and the boundary is stated on every answer, not just
 * once at the top.
 */
export function AskAssistant({ incidentId }: { incidentId: string }) {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const mutation = useAskIncident(incidentId);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || mutation.isPending) return;
    setQuestion("");
    try {
      const result = await mutation.mutateAsync(q);
      setTurns((t) => [...t, { question: q, answer: result?.answer }]);
    } catch {
      setTurns((t) => [
        ...t,
        { question: q, error: "The assistant isn't available right now (it may not be configured on this server)." },
      ]);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-medium text-(--color-ink-secondary)">Ask about this incident</h2>
        <span className="rounded-full border border-(--color-hairline) px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-(--color-ink-muted)">
          AI assistant &middot; not the audited record
        </span>
      </div>

      {turns.length > 0 && (
        <div className="flex flex-col gap-3">
          {turns.map((t, i) => (
            <div key={i} className="flex flex-col gap-1.5 rounded-md border border-(--color-hairline) bg-(--color-surface) p-3">
              <p className="text-sm font-medium text-(--color-ink)">{t.question}</p>
              {t.answer && <p className="text-sm leading-relaxed text-(--color-ink-secondary)">{t.answer}</p>}
              {t.error && (
                <p role="alert" className="text-sm text-(--color-status-auto-flag)">
                  {t.error}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      <form onSubmit={onSubmit} className="flex gap-2">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. why is the confidence lower than the risk?"
          aria-label="Ask a question about this incident"
          className="flex-1 rounded-md border border-(--color-hairline) bg-(--color-surface) px-3 py-2 text-sm outline-none focus-visible:border-(--color-accent)"
        />
        <button
          type="submit"
          disabled={!question.trim() || mutation.isPending}
          className={cn(
            "shrink-0 rounded-md bg-(--color-accent) px-4 py-2 text-sm font-medium text-(--color-accent-ink)",
            (!question.trim() || mutation.isPending) && "opacity-50"
          )}
        >
          {mutation.isPending ? "Asking…" : "Ask"}
        </button>
      </form>
      <p className="text-xs text-(--color-ink-muted)">Uses only this incident's evidence — not a recommendation.</p>
    </div>
  );
}
