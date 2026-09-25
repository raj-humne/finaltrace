import type { ReactNode } from "react";

export function EmptyState({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center">
      <p className="max-w-md text-sm text-(--color-ink-secondary)">{title}</p>
      {action}
    </div>
  );
}

export function ErrorState({ title }: { title: string }) {
  return (
    <div className="flex flex-col items-center gap-2 py-16 text-center">
      <p className="max-w-md text-sm text-(--color-status-auto-flag)">{title}</p>
    </div>
  );
}
