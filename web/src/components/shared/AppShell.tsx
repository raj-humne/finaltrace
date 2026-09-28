import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useNavigate, useLocation } from "react-router-dom";
import LocomotiveScroll from "locomotive-scroll";
import "locomotive-scroll/locomotive-scroll.css";
import gsap from "gsap";
import { cn } from "@/lib/utils";
import { useAuth } from "@/state/auth";
import { CommandPalette } from "./CommandPalette";
import KineticGrid from "@/components/ui/kinetic-grid";
import { useGsap3DTilt } from "@/hooks/useGsap3DTilt";

const NAV = [
  { to: "/incidents", label: "Queue" },
  { to: "/users", label: "Users" },
  { to: "/detection/health", label: "Detection health" },
];

function initialTheme(): "dark" | "light" {
  try {
    // The app defaulted to dark before this redesign, so any browser that
    // already visited has "dark" saved from that old default — which would
    // silently defeat the new light-by-default choice forever. Force light
    // once per browser, then respect whatever the toggle is set to after.
    if (!localStorage.getItem("st-theme-v2")) {
      localStorage.setItem("st-theme-v2", "1");
      localStorage.setItem("st-theme", "light");
      return "light";
    }
    return (localStorage.getItem("st-theme") as "dark" | "light") ?? "light";
  } catch {
    return "light";
  }
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [theme, setTheme] = useState<"dark" | "light">(initialTheme);
  const [paletteOpen, setPaletteOpen] = useState(false);

  // Activate 3D perspective tilt across screen, headings, cards and text
  useGsap3DTilt();

  // Initialize Locomotive Scroll for buttery smooth scrolling
  useEffect(() => {
    let scroll: LocomotiveScroll | null = null;
    try {
      scroll = new LocomotiveScroll({
        lenisOptions: {
          smoothWheel: true,
          duration: 1.2,
          easing: (t: number) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
        },
      });
    } catch (e) {
      console.warn("LocomotiveScroll initialization failed", e);
    }
    return () => {
      scroll?.destroy();
    };
  }, []);

  // High-level GSAP tactile transitions on every CTA action / button
  useEffect(() => {
    const isInteractive = (el: HTMLElement | null): HTMLElement | null => {
      if (!el) return null;
      return el.closest("button, a[role='button'], .btn-cta, [data-cta]");
    };

    function onMouseOver(e: MouseEvent) {
      const target = isInteractive(e.target as HTMLElement);
      if (target) {
        gsap.to(target, {
          scale: 1.03,
          duration: 0.22,
          ease: "power2.out",
          overwrite: "auto",
        });
      }
    }

    function onMouseOut(e: MouseEvent) {
      const target = isInteractive(e.target as HTMLElement);
      if (target) {
        gsap.to(target, {
          scale: 1,
          duration: 0.25,
          ease: "power2.out",
          overwrite: "auto",
        });
      }
    }

    function onMouseDown(e: MouseEvent) {
      const target = isInteractive(e.target as HTMLElement);
      if (target) {
        gsap.to(target, {
          scale: 0.95,
          duration: 0.1,
          ease: "power1.in",
          overwrite: "auto",
        });
      }
    }

    function onMouseUp(e: MouseEvent) {
      const target = isInteractive(e.target as HTMLElement);
      if (target) {
        gsap.to(target, {
          scale: 1.03,
          duration: 0.22,
          ease: "elastic.out(1.2, 0.4)",
          overwrite: "auto",
        });
      }
    }

    document.addEventListener("mouseover", onMouseOver);
    document.addEventListener("mouseout", onMouseOut);
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("mouseup", onMouseUp);

    return () => {
      document.removeEventListener("mouseover", onMouseOver);
      document.removeEventListener("mouseout", onMouseOut);
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  // GSAP page entrance animation on route transition
  useEffect(() => {
    gsap.fromTo(
      "main > *",
      { opacity: 0, y: 12 },
      { opacity: 1, y: 0, duration: 0.4, ease: "power2.out" }
    );
  }, [location.pathname]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("st-theme", theme);
    } catch {
      // storage unavailable — theme still applies for this session
    }
  }, [theme]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <KineticGrid className="min-h-screen bg-[#0F0F0F] text-[#FBFBFB]">
      <header className="sticky top-0 z-20 bg-transparent">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between px-6 sm:h-16">
          {/* Left: Brand Logo */}
          <div className="flex shrink-0 items-center min-w-[200px]">
            <NavLink to="/incidents" className="flex items-center gap-2 select-none">
              <span className="text-base sm:text-lg font-bold tracking-tight text-(--color-ink)">
                SentinelTrace
              </span>
            </NavLink>
          </div>

          {/* Center: Nav links centered with larger font and wide spacing */}
          <nav className="flex flex-1 items-center justify-center gap-8 sm:gap-12 md:gap-14 lg:gap-16 h-full overflow-x-auto whitespace-nowrap">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "relative flex h-full shrink-0 items-center py-2 text-base sm:text-[17px] transition-colors",
                    isActive
                      ? "font-semibold text-(--color-ink) sm:after:absolute sm:after:inset-x-0 sm:after:bottom-0 sm:after:h-[2.5px] sm:after:bg-(--color-accent) sm:after:content-['']"
                      : "font-medium text-(--color-ink-secondary) hover:text-(--color-ink)"
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          {/* Right: Controls & User Profile */}
          <div className="flex shrink-0 items-center justify-end min-w-[200px] gap-2.5 sm:gap-3.5">
            <button
              onClick={() => setPaletteOpen(true)}
              aria-label="Open command palette"
              className="hidden rounded-md border border-(--color-hairline) px-2.5 py-1 text-xs text-(--color-ink-muted) sm:block hover:text-(--color-ink) transition-colors"
            >
              &#8984;K
            </button>
            <button
              aria-label="Toggle theme"
              onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
              className="rounded-md border border-(--color-hairline) px-2.5 py-1 text-xs text-(--color-ink-secondary) hover:text-(--color-ink) transition-colors"
            >
              {theme === "dark" ? "Dark" : "Light"}
            </button>
            {user && (
              <div className="flex items-center gap-2.5 text-xs text-(--color-ink-secondary)">
                <span className="hidden md:inline font-medium text-(--color-ink)">{user.display_name}</span>
                <button
                  onClick={() => logout().then(() => navigate("/login"))}
                  className="text-(--color-ink-muted) underline-offset-2 hover:underline hover:text-(--color-ink)"
                >
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1400px] px-4 py-6 relative z-10">{children}</main>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </KineticGrid>
  );
}
