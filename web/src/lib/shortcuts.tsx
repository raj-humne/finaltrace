import { createContext, useContext, useEffect, useRef, type ReactNode } from "react";

export interface ListShortcutTarget {
  count: number;
  getSelectedIndex: () => number;
  onMove: (delta: number) => void;
  onOpen: () => void;
}

interface ShortcutRegistry {
  list: ListShortcutTarget | null;
  createAction: (() => void) | null;
}

const ShortcutRegistryContext = createContext<{ current: ShortcutRegistry } | null>(null);

/** Holds the currently-active list/create targets so the one global keydown
 * handler in AppShell can act on whatever page is mounted, without every
 * page needing to know about every other page. */
export function ShortcutRegistryProvider({ children }: { children: ReactNode }) {
  const registry = useRef<ShortcutRegistry>({ list: null, createAction: null }).current;
  return <ShortcutRegistryContext.Provider value={{ current: registry }}>{children}</ShortcutRegistryContext.Provider>;
}

export function useShortcutRegistry() {
  const ctx = useContext(ShortcutRegistryContext);
  if (!ctx) throw new Error("useShortcutRegistry must be used within ShortcutRegistryProvider");
  return ctx.current;
}

/** A page with a navigable list (e.g. the triage queue) registers itself
 * here so j/k/Enter/i work on it. Unregisters on unmount or when the target
 * identity changes. */
export function useListShortcuts(target: ListShortcutTarget | null) {
  const registry = useShortcutRegistry();
  useEffect(() => {
    registry.list = target;
    return () => {
      if (registry.list === target) registry.list = null;
    };
  }, [registry, target]);
}

/** A page registers whatever "create/comment" means for it (e.g. focusing
 * the verdict note field) so `c` can trigger it. */
export function useCreateShortcut(action: (() => void) | null) {
  const registry = useShortcutRegistry();
  useEffect(() => {
    registry.createAction = action;
    return () => {
      if (registry.createAction === action) registry.createAction = null;
    };
  }, [registry, action]);
}

export function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  if (el.isContentEditable) return true;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}
