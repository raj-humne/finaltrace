import { useState } from "react";
import { Link } from "react-router-dom";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { useUsers } from "@/hooks/useUsers";
import { emberForRisk } from "@/lib/design";
import { ErrorState } from "@/components/shared/EmptyState";
import { TableRowSkeleton } from "@/components/shared/Skeleton";
import { usePageTitle } from "@/hooks/usePageTitle";
import { SplitHeading } from "@/components/shared/SplitHeading";

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
    <div className="flex flex-col gap-6">
      {/* Centered Page Header: Akira Heading & Mont Subheading (matching Queue design, no icon) */}
      <div className="flex flex-col items-center justify-center text-center pt-2 pb-2">
        <SplitHeading text="USERS" />
        <p className="mt-3 font-mont font-light text-xs sm:text-[13px] tracking-[0.2em] uppercase text-[#BCABAE]">
          {data?.total != null ? `${data.total} monitored entities` : "Loading monitored directory…"}
        </p>
      </div>

      <div className="flex justify-center sm:justify-start">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search by name or id…"
          aria-label="Search users by name or id"
          spellCheck={false}
          className="w-full rounded-xl border border-white/15 bg-white/[0.06] backdrop-blur-md px-4 py-2.5 font-mont text-sm text-[#FBFBFB] placeholder:text-[#BCABAE]/60 outline-none transition-all focus:border-[#BCABAE] focus:ring-1 focus:ring-[#BCABAE] sm:w-80"
        />
      </div>
      {isError && <ErrorState title="Could not load the user directory." />}
      {!isError && (
        <div className="glass-container overflow-x-auto rounded-2xl">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="border-b border-white/10 text-left font-mont text-xs uppercase tracking-wider text-[#BCABAE]">
              <tr>
                <th className="px-5 py-3 font-semibold">User</th>
                <th className="px-5 py-3 font-semibold">Role</th>
                <th className="px-5 py-3 font-semibold">Department</th>
                <th className="px-5 py-3 font-semibold">Risk</th>
                <th className="px-5 py-3 font-semibold">Trend</th>
                <th className="px-5 py-3 font-semibold">Open</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.06] font-mont text-[#FBFBFB]">
              {isLoading && Array.from({ length: 6 }, (_, i) => <TableRowSkeleton key={i} cols={6} />)}
              {!isLoading &&
                items.map((u) => (
                  <tr key={u.user_id} className="transition-colors hover:bg-white/[0.04]">
                    <td className="px-5 py-3.5">
                      <Link to={`/users/${u.user_id}`} className="font-medium text-[#FBFBFB] transition-colors hover:text-[#BCABAE]">
                        {u.name}
                      </Link>
                      <span className="ml-2 font-mono-tab text-xs text-[#BCABAE]/70">{u.user_id}</span>
                    </td>
                    <td className="px-5 py-3.5 text-[#BCABAE]">{u.role}</td>
                    <td className="px-5 py-3.5 text-[#BCABAE]">{u.department}</td>
                    <td className="px-5 py-3.5 font-mono-tab font-semibold" style={{ color: emberForRisk(u.current_risk ?? 0) }}>
                      {(u.current_risk ?? 0).toFixed(1)}
                    </td>
                    <td className="px-5 py-3.5">
                      <TrendBadge trend={u.trend} />
                    </td>
                    <td className="px-5 py-3.5 font-mono-tab">{u.open_incidents}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
