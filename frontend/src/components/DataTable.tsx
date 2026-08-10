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
      <div className="overflow-x-auto rounded border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  className="px-4 py-2 text-left font-medium text-slate-600"
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {loading ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-8 text-center text-slate-400">
                  Loading…
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-8 text-center text-slate-400">
                  No rows.
                </td>
              </tr>
            ) : (
              rows.map((row, i) => (
                <tr key={i} className="hover:bg-slate-50">
                  {columns.map((col) => (
                    <td key={col.key} className="px-4 py-2 text-slate-700">
                      {col.render ? col.render(row) : String((row as Record<string, unknown>)[col.key] ?? "")}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex items-center justify-between text-sm text-slate-500">
        <div className="flex items-center gap-2">
          <span>Rows per page</span>
          <select
            className="rounded border border-slate-300 px-1 py-0.5"
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
            className="rounded border border-slate-300 px-2 py-0.5 disabled:opacity-40"
            disabled={page <= 1}
          >
            «
          </button>
          <button
            onClick={() => onSkipChange(Math.min((page + 1) * limit - limit, (pages - 1) * limit))}
            className="rounded border border-slate-300 px-2 py-0.5 disabled:opacity-40"
            disabled={page >= pages}
          >
            »
          </button>
        </div>
      </div>
    </div>
  );
}
