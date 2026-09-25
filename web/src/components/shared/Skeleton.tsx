import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("st-skeleton", className)} aria-hidden />;
}

export function IncidentRowSkeleton() {
  return (
    <div className="grid grid-cols-[auto_auto_1fr] items-start gap-x-4 gap-y-1.5 border-b border-(--color-hairline) px-4 py-3">
      <div className="flex w-28 flex-col gap-2">
        <Skeleton className="h-3.5 w-16" />
        <Skeleton className="h-6 w-10" />
      </div>
      <Skeleton className="h-1.5 w-24" />
      <div className="flex flex-col gap-2">
        <Skeleton className="h-3.5 w-48" />
        <Skeleton className="h-3.5 w-72" />
        <Skeleton className="h-3 w-40" />
      </div>
    </div>
  );
}

export function TableRowSkeleton({ cols = 5 }: { cols?: number }) {
  return (
    <tr className="border-b border-(--color-hairline) last:border-b-0">
      {Array.from({ length: cols }, (_, i) => (
        <td key={i} className="px-4 py-3">
          <Skeleton className="h-3.5 w-full max-w-24" />
        </td>
      ))}
    </tr>
  );
}
