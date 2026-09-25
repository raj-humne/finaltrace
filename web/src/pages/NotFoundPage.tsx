import { Link } from "react-router-dom";
import { usePageTitle } from "@/hooks/usePageTitle";

export function NotFoundPage() {
  usePageTitle("Page not found");
  return (
    <div className="flex flex-col items-center gap-3 py-24 text-center">
      <span className="font-mono-tab text-sm text-(--color-ink-muted)">404</span>
      <h1 className="text-2xl font-semibold tracking-tight">Page not found</h1>
      <p className="max-w-md text-sm text-(--color-ink-secondary)">
        There's no page at this address. It may have moved, or the link may be wrong.
      </p>
      <Link to="/incidents" className="mt-2 rounded-md bg-(--color-accent) px-4 py-2 text-sm font-medium text-(--color-accent-ink) hover:opacity-90">
        Back to the triage queue
      </Link>
    </div>
  );
}
