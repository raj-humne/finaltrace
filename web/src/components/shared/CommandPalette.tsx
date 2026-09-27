import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

const ROUTES = [
  { to: "/incidents", label: "Go to queue" },
  { to: "/users", label: "Go to users" },
  { to: "/detection/health", label: "Go to detection health" },
];

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const returnFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) {
      setQuery("");
      return;
    }
    returnFocusRef.current = document.activeElement as HTMLElement | null;
    return () => returnFocusRef.current?.focus?.();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const filtered = ROUTES.filter((r) => r.label.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 pt-32" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="w-full max-w-md rounded-lg border border-(--color-hairline) bg-(--color-surface-raised) shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          autoFocus
          aria-label="Search commands"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Jump to…"
          className="w-full border-b border-(--color-hairline) bg-transparent px-4 py-3 text-sm outline-none"
        />
        <ul className="max-h-64 overflow-auto p-1">
          {filtered.map((r) => (
            <li key={r.to}>
              <button
                onClick={() => {
                  navigate(r.to);
                  onClose();
                }}
                className="w-full rounded-md px-3 py-2 text-left text-sm hover:bg-(--color-surface)"
              >
                {r.label}
              </button>
            </li>
          ))}
          {filtered.length === 0 && <li className="px-3 py-2 text-sm text-(--color-ink-muted)">No matches</li>}
        </ul>
      </div>
    </div>
  );
}
