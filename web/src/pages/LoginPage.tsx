import { useState, type FormEvent } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/state/auth";
import { cn } from "@/lib/utils";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(username, password);
      const to = (location.state as { from?: string } | null)?.from ?? "/incidents";
      navigate(to, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-(--color-page) px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">SentinelTrace</h1>
          <p className="mt-1 text-sm text-(--color-ink-secondary)">Behavioural threat detection &amp; incident correlation</p>
        </div>
        <form onSubmit={onSubmit} className="flex flex-col gap-4 rounded-lg border border-(--color-hairline) bg-(--color-surface-raised) p-6">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="username" className="text-sm text-(--color-ink-secondary)">
              Analyst id
            </label>
            <input
              id="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="rounded-md border border-(--color-hairline) bg-(--color-surface) px-3 py-2 text-sm outline-none focus-visible:border-(--color-source-logon)"
              placeholder="priya.s"
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-sm text-(--color-ink-secondary)">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rounded-md border border-(--color-hairline) bg-(--color-surface) px-3 py-2 text-sm outline-none focus-visible:border-(--color-source-logon)"
              required
            />
          </div>
          {error && <p className="text-sm text-(--color-status-auto-flag)">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className={cn(
              "mt-2 rounded-md bg-(--color-ink) px-3 py-2 text-sm font-medium text-(--color-page) transition-opacity",
              submitting && "opacity-60"
            )}
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>
          <p className="text-center text-xs text-(--color-ink-muted)">Demo credentials: priya.s / analyst-demo-pw</p>
        </form>
      </div>
    </div>
  );
}
