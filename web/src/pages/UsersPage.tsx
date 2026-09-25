import { useState } from "react";
import { Link } from "react-router-dom";
import { Users as UsersIcon, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { useUsers } from "@/hooks/useUsers";
import { emberForRisk } from "@/lib/design";
import { ErrorState } from "@/components/shared/EmptyState";
import { TableRowSkeleton } from "@/components/shared/Skeleton";
import { usePageTitle } from "@/hooks/usePageTitle";

const TREND_ICON = { rising: TrendingUp, falling: TrendingDown } as const;

function TrendBadge({ trend }: { trend?: string }) {
  const Icon = TREND_ICON[trend as keyof typeof TREND_ICON] ?? Minus;
  const color = trend === "rising" ? "text-rose-600" : trend === "falling" ? "text-emerald-600" : "text-(--color-ink-muted)";
  return (
    <span className={`inline-flex items-center gap-1 ${color}`}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {trend ?? "stable"}
    </span>
  );
}

export function UsersPage() {
  usePageTitle("Users");
  const [q, setQ] = useState("");
  const { data, isLoading, isError } = useUsers({ q: q || undefined, limit: 200 });
  // The live API always returns user_id order and ignores `sort` (Track B,
  // see api/routers/users.py), so sort by current risk client-side.
  const items = (data?.items ?? []).slice().sort((a, b) => (b.current_risk ?? 0) - (a.current_risk ?? 0));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-(--color-accent)/10">
          <UsersIcon className="h-4.5 w-4.5 text-(--color-accent)" aria-hidden />
        </span>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
          <p className="text-sm text-(--color-ink-secondary)">{data?.total ?? "…"} monitored</p>
        </div>
      </div>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search by name or id…"
        aria-label="Search users by name or id"
        spellCheck={false}
        className="w-full rounded-md border border-(--color-hairline) bg-(--color-surface) px-3 py-2 text-sm outline-none focus-visible:border-(--color-accent) sm:w-72"
      />
      {isError && <ErrorState title="Could not load the user directory." />}
      {!isError && (
        <div className="overflow-x-auto rounded-xl border border-(--color-hairline) bg-(--color-surface-raised)">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="border-b border-(--color-hairline) text-left text-xs text-(--color-ink-muted)">
              <tr>
                <th className="px-4 py-2 font-medium">User</th>
                <th className="px-4 py-2 font-medium">Role</th>
                <th className="px-4 py-2 font-medium">Department</th>
                <th className="px-4 py-2 font-medium">Risk</th>
                <th className="px-4 py-2 font-medium">Trend</th>
                <th className="px-4 py-2 font-medium">Open</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && Array.from({ length: 6 }, (_, i) => <TableRowSkeleton key={i} cols={6} />)}
              {!isLoading &&
                items.map((u) => (
                  <tr key={u.user_id} className="border-b border-(--color-hairline) last:border-b-0 hover:bg-(--color-surface)">
                    <td className="px-4 py-2">
                      <Link to={`/users/${u.user_id}`} className="font-medium hover:underline">
                        {u.name}
                      </Link>
                      <span className="ml-2 font-mono-tab text-xs text-(--color-ink-muted)">{u.user_id}</span>
                    </td>
                    <td className="px-4 py-2 text-(--color-ink-secondary)">{u.role}</td>
                    <td className="px-4 py-2 text-(--color-ink-secondary)">{u.department}</td>
                    <td className="px-4 py-2 font-mono-tab" style={{ color: emberForRisk(u.current_risk ?? 0) }}>
                      {(u.current_risk ?? 0).toFixed(1)}
                    </td>
                    <td className="px-4 py-2">
                      <TrendBadge trend={u.trend} />
                    </td>
                    <td className="px-4 py-2 font-mono-tab">{u.open_incidents}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
