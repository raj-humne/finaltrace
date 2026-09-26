import { useState, type ReactNode } from "react";
import { Table2, LineChart } from "lucide-react";

/**
 * Every chart needs a "view as table" affordance so the same data is
 * readable without interpreting a visualization (docs/06 sections 9, 11).
 */
export function ChartViewToggle({ chart, table, label }: { chart: ReactNode; table: ReactNode; label: string }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const isTable = view === "table";
  return (
    <div>
      <div className="mb-1 flex justify-end">
        <button
          onClick={() => setView(isTable ? "chart" : "table")}
          aria-pressed={isTable}
          className="flex items-center gap-1.5 rounded-md border border-(--color-hairline) px-2 py-1 text-xs text-(--color-ink-muted) hover:text-(--color-ink)"
        >
          {isTable ? <LineChart className="h-3.5 w-3.5" aria-hidden /> : <Table2 className="h-3.5 w-3.5" aria-hidden />}
          {isTable ? "View as chart" : "View as table"}
        </button>
      </div>
      <div role="img" aria-label={label} hidden={isTable}>
        {chart}
      </div>
      {isTable && table}
    </div>
  );
}
