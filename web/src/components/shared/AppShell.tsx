import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useAuth } from "@/state/auth";
import { CommandPalette } from "./CommandPalette";
import { ShortcutRegistryProvider, isTypingTarget, useShortcutRegistry } from "@/lib/shortcuts";

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
  return (
    <ShortcutRegistryProvider>
      <AppShellInner>{children}</AppShellInner>
    </ShortcutRegistryProvider>
  );
}

function AppShellInner({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const registry = useShortcutRegistry();
  const [theme, setTheme] = useState<"dark" | "light">(initialTheme);
  const [paletteOpen, setPaletteOpen] = useState(false);

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
        return;
      }
      // The command palette's own Escape handler and the "no-op while
      // typing" rule below already cover its search input; nothing extra
      // needed here to keep j/k/etc. from firing while it's open.
      if (paletteOpen || e.metaKey || e.ctrlKey || e.altKey || isTypingTarget(e.target)) return;

      const key = e.key.toLowerCase();
      if (key === "j" || key === "k") {
        const list = registry.list;
        if (!list || list.count === 0) return;
        e.preventDefault();
        list.onMove(key === "j" ? 1 : -1);
      } else if (key === "enter" || key === "i") {
        const list = registry.list;
        if (!list || list.count === 0) return;
        e.preventDefault();
        list.onOpen();
      } else if (key === "c") {
        if (!registry.createAction) return;
        e.preventDefault();
        registry.createAction();
      } else if (key === "b") {
        e.preventDefault();
        navigate(-1);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paletteOpen, navigate, registry]);

  return (
    <div className="min-h-screen bg-(--color-page)">
      <header className="sticky top-0 z-20 border-b border-(--color-hairline) bg-(--color-page)/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2 sm:h-14 sm:flex-nowrap sm:py-0">
          <span className="shrink-0 text-sm font-semibold tracking-tight">SentinelTrace</span>
          <nav className="order-3 flex w-full items-center gap-4 overflow-x-auto whitespace-nowrap sm:order-none sm:h-full sm:w-auto sm:gap-5 sm:overflow-visible">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "relative flex h-full shrink-0 items-center py-1.5 text-sm text-(--color-ink-secondary) transition-colors hover:text-(--color-ink) sm:py-0",
                    isActive && "font-medium text-(--color-ink) sm:after:absolute sm:after:inset-x-0 sm:after:bottom-0 sm:after:h-0.5 sm:after:bg-(--color-accent) sm:after:content-['']"
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-3">
            <button
              onClick={() => setPaletteOpen(true)}
              aria-label="Open command palette"
              className="hidden rounded-md border border-(--color-hairline) px-2 py-1 text-xs text-(--color-ink-muted) sm:block"
            >
              &#8984;K
            </button>
            <button
              aria-label="Toggle theme"
              onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
              className="rounded-md border border-(--color-hairline) px-2 py-1 text-xs text-(--color-ink-secondary)"
            >
              {theme === "dark" ? "Dark" : "Light"}
            </button>
            {user && (
              <div className="flex items-center gap-2 text-xs text-(--color-ink-secondary)">
                <span className="hidden md:inline">{user.display_name}</span>
                <button onClick={() => logout().then(() => navigate("/login"))} className="text-(--color-ink-muted) underline-offset-2 hover:underline">
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1400px] px-4 py-6">{children}</main>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
