import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useAuth } from "@/state/auth";
import { CommandPalette } from "./CommandPalette";

const NAV = [
  { to: "/incidents", label: "Queue" },
  { to: "/users", label: "Users" },
  { to: "/detection/health", label: "Detection health" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [theme, setTheme] = useState<"dark" | "light">(() => (localStorage.getItem("st-theme") as "dark" | "light") ?? "dark");
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
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="min-h-screen bg-(--color-page)">
      <header className="sticky top-0 z-20 border-b border-(--color-hairline) bg-(--color-page)/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-6 px-4">
          <span className="text-sm font-semibold tracking-tight">SentinelTrace</span>
          <nav className="flex items-center gap-4">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn("text-sm text-(--color-ink-secondary) hover:text-(--color-ink)", isActive && "font-medium text-(--color-ink)")
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <button
              onClick={() => setPaletteOpen(true)}
              className="rounded-md border border-(--color-hairline) px-2 py-1 text-xs text-(--color-ink-muted)"
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
                <span>{user.name}</span>
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
