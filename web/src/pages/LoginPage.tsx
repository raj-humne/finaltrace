import { useRef, useState, type FormEvent, type MouseEvent } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/state/auth";
import { cn } from "@/lib/utils";
import { KillChainHero } from "@/components/shared/KillChainHero";
import { usePageTitle } from "@/hooks/usePageTitle";

const TILT_ENABLED =
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: no-preference)").matches &&
  window.matchMedia("(pointer: fine)").matches;

export function LoginPage() {
  usePageTitle("Sign in");
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const heroRef = useRef<HTMLDivElement>(null);
  const [tilt, setTilt] = useState({ x: 0, y: 0 });

  function onHeroMouseMove(e: MouseEvent<HTMLDivElement>) {
    if (!TILT_ENABLED || !heroRef.current) return;
    const rect = heroRef.current.getBoundingClientRect();
    const px = (e.clientX - rect.left) / rect.width - 0.5;
    const py = (e.clientY - rect.top) / rect.height - 0.5;
    setTilt({ x: py * -3.5, y: px * 5 });
  }

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
    <div className="flex min-h-screen bg-(--color-page) lg:h-screen lg:overflow-hidden">
      <div
        ref={heroRef}
        onMouseMove={onHeroMouseMove}
        onMouseLeave={() => setTilt({ x: 0, y: 0 })}
        className="hidden w-[58%] shrink-0 bg-[#0E1315] lg:block"
        style={{ perspective: "1400px" }}
      >
        <div
          className="flex h-full w-full flex-col"
          style={{
            transform: `rotateX(${tilt.x}deg) rotateY(${tilt.y}deg) scale(1.02)`,
            transition: "transform 0.4s cubic-bezier(0.22, 1, 0.36, 1)",
            transformStyle: "preserve-3d",
          }}
        >
          <div className="shrink-0 px-12 pb-4 pt-12">
            <p className="text-lg font-semibold tracking-tight text-[#F2F5F6]">SentinelTrace</p>
            <p className="mt-1 max-w-[30ch] text-sm text-[rgba(242,245,246,0.62)]">
              Individually harmless actions. One progression.
            </p>
          </div>
          <div className="min-h-0 flex-1">
            <KillChainHero />
          </div>
        </div>
      </div>

      <div className="flex flex-1 items-center justify-center px-6">
        <div className="w-full max-w-[22rem]">
          <div className="mb-8 lg:hidden">
            <h1 className="text-2xl font-semibold tracking-tight">SentinelTrace</h1>
            <p className="mt-1 text-sm text-(--color-ink-secondary)">Behavioural threat detection &amp; incident correlation</p>
          </div>

          <h2 className="text-xl font-semibold tracking-tight">Sign in</h2>
          <p className="mt-1 text-sm text-(--color-ink-secondary)">Use your analyst or detection-engineer account.</p>

          <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="username" className="text-sm text-(--color-ink-secondary)">
                Analyst id
              </label>
              <input
                id="username"
                autoComplete="username"
                spellCheck={false}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="rounded-md border border-(--color-hairline) bg-(--color-surface) px-3 py-2.5 text-sm outline-none transition-colors focus-visible:border-(--color-accent)"
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
                className="rounded-md border border-(--color-hairline) bg-(--color-surface) px-3 py-2.5 text-sm outline-none transition-colors focus-visible:border-(--color-accent)"
                required
              />
            </div>
            {error && (
              <p role="alert" aria-live="polite" className="text-sm text-(--color-status-auto-flag)">
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={submitting}
              className={cn(
                "mt-2 rounded-md bg-(--color-accent) px-3 py-2.5 text-sm font-medium text-(--color-accent-ink) transition-opacity hover:opacity-90",
                submitting && "opacity-60"
              )}
            >
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <p className="mt-6 text-xs text-(--color-ink-muted)">Demo: priya.s / analyst-demo-pw</p>
        </div>
      </div>
    </div>
  );
}
