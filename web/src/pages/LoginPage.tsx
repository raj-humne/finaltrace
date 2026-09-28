import { useState, useEffect, type FormEvent } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import gsap from "gsap";
import { useAuth } from "@/state/auth";
import { cn } from "@/lib/utils";
import { KillChainHero } from "@/components/shared/KillChainHero";
import { LoopProgression } from "@/components/shared/LoopProgression";
import { usePageTitle } from "@/hooks/usePageTitle";
import KineticGrid from "@/components/ui/kinetic-grid";
import { useGsap3DTilt } from "@/hooks/useGsap3DTilt";
import { ThemeSelect, type ThemeSelectOption } from "@/components/ui/ThemeSelect";

const ROLE_OPTIONS: ThemeSelectOption[] = [
  { value: "analyst", label: "SOC Analyst" },
  { value: "detection_engineer", label: "Detection Engineer" },
];

export function LoginPage() {
  usePageTitle("Sign in");
  useGsap3DTilt();
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [tab, setTab] = useState<"signin" | "signup">("signin");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("analyst");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [hoveredChar, setHoveredChar] = useState<number | null>(null);

  // Staggered character entrance from down to up
  useEffect(() => {
    const chars = document.querySelectorAll(".hero-char");
    if (!chars.length) return;

    gsap.fromTo(
      chars,
      {
        y: "125%",
        opacity: 0,
      },
      {
        y: "0%",
        opacity: 1,
        duration: 0.75,
        stagger: 0.04,
        ease: "power3.out",
        overwrite: "auto",
        clearProps: "transform",
      }
    );
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(username, password);
      const to = (location.state as { from?: string } | null)?.from ?? "/incidents";
      navigate(to, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <KineticGrid className="bg-[#0F0F0F] text-[#FBFBFB]">
      <div className="flex min-h-screen flex-col justify-between">
        {/* Main Content Area: Left Hero & Right Form Card */}
        <main className="flex-1 flex flex-col lg:flex-row items-center justify-between px-6 sm:px-12 lg:px-20 py-8 lg:py-12 gap-10 lg:gap-16 max-w-7xl mx-auto w-full">
          {/* Left Column: Big Title, Subtitle, 6-Dot Loop Diagram */}
          <div className="flex-1 flex flex-col items-start justify-center max-w-2xl">
            <h1 className="inline-block select-none font-akira text-6xl sm:text-7xl lg:text-8xl xl:text-[5.5rem] font-extrabold tracking-wider leading-[0.92]">
              <span className="block text-[#FBFBFB] overflow-hidden pb-1">
                {"SENTINEL".split("").map((char, idx) => (
                  <span
                    key={idx}
                    className="hero-char inline-block will-change-transform"
                  >
                    {char}
                  </span>
                ))}
              </span>
              <span className="flex justify-between w-full overflow-hidden pb-1">
                {["T", "R", "A", "C", "E"].map((char, idx) => (
                  <span
                    key={idx}
                    className="inline-block overflow-hidden py-1 px-1.5 cursor-pointer"
                    onMouseEnter={() => setHoveredChar(idx)}
                    onMouseLeave={() => setHoveredChar(null)}
                  >
                    <span
                      className={cn(
                        "hero-char trace-letter will-change-transform",
                        hoveredChar === idx && "trace-letter-active"
                      )}
                    >
                      {char}
                    </span>
                  </span>
                ))}
              </span>
            </h1>
            <p className="mt-6 font-mont font-light text-xs sm:text-[13px] tracking-[0.2em] uppercase text-[#BCABAE] leading-relaxed">
              Behavioural threat detection &amp; incident correlation
            </p>

            {/* 6 Connected Dots Diagram matching wireframe */}
            <div className="mt-9 w-full max-w-[450px]">
              <LoopProgression />
            </div>
          </div>

          {/* Right Column: Sign In / Sign Up Glassmorphic Card */}
          <div className="w-full max-w-[26rem] shrink-0">
            <div className="glass-container tilt-card rounded-2xl p-8">
              {/* Tab Selector: Sign in vs Sign up (auth tag removed) */}
              <div className="flex items-center justify-center border-b border-white/10 pb-4 mb-6">
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => { setTab("signin"); setError(null); }}
                    className={cn(
                      "px-4 py-1.5 text-xs font-semibold rounded-md transition-all font-mont tracking-wider",
                      tab === "signin"
                        ? "bg-[#BCABAE] text-[#0F0F0F] shadow-sm"
                        : "text-[#BCABAE] hover:text-[#FBFBFB] hover:bg-white/[0.08]"
                    )}
                  >
                    SIGN IN
                  </button>
                  <button
                    type="button"
                    onClick={() => { setTab("signup"); setError(null); }}
                    className={cn(
                      "px-4 py-1.5 text-xs font-semibold rounded-md transition-all font-mont tracking-wider",
                      tab === "signup"
                        ? "bg-[#BCABAE] text-[#0F0F0F] shadow-sm"
                        : "text-[#BCABAE] hover:text-[#FBFBFB] hover:bg-white/[0.08]"
                    )}
                  >
                    SIGN UP
                  </button>
                </div>
              </div>

              {/* Card Header: Akira font heading & center-aligned subheading */}
              <div className="text-center">
                <h2 className="font-akira text-base sm:text-lg font-bold tracking-wider text-[#FBFBFB]">
                  {tab === "signin" ? "WELCOME BACK" : "CREATE AN ACCOUNT"}
                </h2>
                <p className="mt-2 text-xs text-[#BCABAE]/80">
                  {tab === "signin"
                    ? "Use your analyst or detection-engineer credentials."
                    : "Join the SOC threat detection team."}
                </p>
              </div>

              <form onSubmit={onSubmit} className="mt-5 flex flex-col gap-3.5">
                {tab === "signup" && (
                  <div className="flex flex-col gap-1">
                    <label htmlFor="name" className="text-xs font-medium text-[#BCABAE]">
                      Full Name
                    </label>
                    <input
                      id="name"
                      autoComplete="name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      className="rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-[#FBFBFB] outline-none transition-colors placeholder:text-[#716969] focus-visible:border-[#BCABAE] focus-visible:bg-black/60"
                      placeholder="Alex Turner"
                      required
                    />
                  </div>
                )}

                <div className="flex flex-col gap-1">
                  <label htmlFor="username" className="text-xs font-medium text-[#BCABAE]">
                    Analyst id
                  </label>
                  <input
                    id="username"
                    autoComplete="username"
                    spellCheck={false}
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-[#FBFBFB] outline-none transition-colors placeholder:text-[#716969] focus-visible:border-[#BCABAE] focus-visible:bg-black/60"
                    placeholder="priya.s"
                    required
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <label htmlFor="password" className="text-xs font-medium text-[#BCABAE]">
                    Password
                  </label>
                  <input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-[#FBFBFB] outline-none transition-colors placeholder:text-[#716969] focus-visible:border-[#BCABAE] focus-visible:bg-black/60"
                    required
                  />
                </div>

                {tab === "signup" && (
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-medium text-[#BCABAE]">
                      Role
                    </label>
                    <ThemeSelect
                      value={role}
                      onValueChange={setRole}
                      options={ROLE_OPTIONS}
                      triggerClassName="w-full bg-black/40 border-white/10 py-2"
                    />
                  </div>
                )}

                {error && (
                  <p role="alert" aria-live="polite" className="text-xs text-[#d03b3b]">
                    {error}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={submitting}
                  className={cn(
                    "mt-2 rounded-md bg-[#BCABAE] px-3 py-2.5 text-sm font-semibold text-[#0F0F0F] transition-opacity hover:opacity-90 shadow-md",
                    submitting && "opacity-60"
                  )}
                >
                  {submitting ? "Processing…" : tab === "signin" ? "Sign in" : "Create Account"}
                </button>
              </form>

              <p className="mt-5 text-center text-xs text-[#BCABAE]/70">
                Demo: <span className="text-[#FBFBFB] font-mono">priya.s</span> / <span className="text-[#FBFBFB] font-mono">analyst-demo-pw</span>
              </p>
            </div>
          </div>
        </main>

        {/* Horizontal 6 Connected Points in the Bottom */}
        <footer className="w-full shrink-0 bg-transparent px-6 py-4">
          <div className="mx-auto max-w-6xl">
            <KillChainHero />
          </div>
        </footer>
      </div>
    </KineticGrid>
  );
}
