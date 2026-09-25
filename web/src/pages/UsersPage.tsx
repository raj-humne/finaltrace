import { useState } from "react";
import { Link } from "react-router-dom";
import { useUsers } from "@/hooks/useUsers";
import { emberForRisk } from "@/lib/design";
import { ErrorState } from "@/components/shared/EmptyState";

export function UsersPage() {
  const [q, setQ] = useState("");
  const { data, isLoading, isError } = useUsers({ q: q || undefined, limit: 200 });
  // The live API always returns user_id order and ignores `sort` (Track B,
  // see api/routers/users.py), so sort by current risk client-side.
  const items = (data?.items ?? []).slice().sort((a, b) => (b.current_risk ?? 0) - (a.current_risk ?? 0));

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
        <p className="mt-1 text-sm text-(--color-ink-secondary)">{data?.total ?? "…"} monitored</p>
      </div>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search by name or id…"
        className="w-72 rounded-md border border-(--color-hairline) bg-(--color-surface) px-3 py-2 text-sm outline-none focus-visible:border-(--color-source-logon)"
      />
      {isError && <ErrorState title="Could not load the user directory." />}
      {!isError && (
        <div className="overflow-hidden rounded-lg border border-(--color-hairline) bg-(--color-surface-raised)">
          <table className="w-full text-sm">
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
              {items.map((u) => (
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
                  <td className="px-4 py-2 text-(--color-ink-secondary)">{u.trend}</td>
                  <td className="px-4 py-2 font-mono-tab">{u.open_incidents}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {isLoading && <p className="px-4 py-3 text-sm text-(--color-ink-muted)">Loading…</p>}
        </div>
      )}
    </div>
  );
}
