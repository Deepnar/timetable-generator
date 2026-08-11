"use client";

interface Column<T> {
  key: string;
  label: string;
  render?: (row: T) => React.ReactNode;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  total: number;
  skip: number;
  limit: number;
  onLimitChange: (limit: number) => void;
  onSkipChange: (skip: number) => void;
  loading?: boolean;
}

/**
 * Generic paginated table driven by server-side skip/limit + X-Total-Count.
 * Callers own the data fetching; this only renders rows and paging controls.
 */
export function DataTable<T>({
  columns,
  rows,
  total,
  skip,
  limit,
  onLimitChange,
  onSkipChange,
  loading = false,
}: DataTableProps<T>) {
  const page = skip > 0 ? Math.floor(skip / limit) + 1 : 1;
  const pages = Math.max(1, Math.ceil(total / limit));

  return (
    <div>
      <div className="overflow-x-auto rounded-sm bg-white shadow-card">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-accent-line">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className="px-4 py-3 text-left eyebrow font-medium text-ink-faint"
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-accent-line">
            {loading ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-12 text-center text-ink-faint">
                  Loading…
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-12 text-center text-ink-faint">
                  No rows.
                </td>
              </tr>
            ) : (
              rows.map((row, i) => (
                <tr key={i} className="hover:bg-canvas-deep/60 transition-colors">
                  {columns.map((col) => (
                    <td key={col.key} className="px-4 py-3 text-ink">
                      {col.render ? col.render(row) : String((row as Record<string, unknown>)[col.key] ?? "")}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex items-center justify-between text-sm text-ink-faint">
        <div className="flex items-center gap-2">
          <span>Rows per page</span>
          <select
            className="rounded-sm border border-accent-line bg-white px-2 py-1 text-ink focus:border-ink focus:outline-none"
            value={limit}
            onChange={(e) => {
              onLimitChange(Number(e.target.value));
              onSkipChange(0);
            }}
          >
            {[10, 25, 50].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-3">
          <span>
            {total} row{total === 1 ? "" : "s"} · page {page}/{pages}
          </span>
          <button
            onClick={() => onSkipChange(0)}
            className="rounded-sm border border-accent-line bg-white px-2 py-1 text-ink disabled:opacity-40 hover:bg-canvas-deep"
            disabled={page <= 1}
          >
            «
          </button>
          <button
            onClick={() => onSkipChange(Math.min((page + 1) * limit - limit, (pages - 1) * limit))}
            className="rounded-sm border border-accent-line bg-white px-2 py-1 text-ink disabled:opacity-40 hover:bg-canvas-deep"
            disabled={page >= pages}
          >
            »
          </button>
        </div>
      </div>
    </div>
  );
}
