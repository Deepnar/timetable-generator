"use client";

import { useMemo, useState } from "react";
import {
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import { type ColumnDef, type SortingState } from "@tanstack/react-table";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { apiPost, apiPut, apiDelete, type ListParams } from "@/lib/api";
import { DataTable } from "@/components/ui/data-table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { ErrorBanner } from "@/components/ui/error-banner";
import { EmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/utils";

export interface FieldConfig {
  name: string;
  label: string;
  type: "text" | "number" | "select" | "checkbox" | "switch" | "textarea";
  required?: boolean;
  options?: string[];
  placeholder?: string;
  min?: number;
}

interface FilterConfig {
  name: string;
  label: string;
  options?: string[];
}

interface ResourcePageProps<T extends { id: number }> {
  title: string;
  endpoint: string; // e.g. "/api/v1/rooms"
  query: (params: ListParams) => UseQueryResult<{ rows: T[]; total: number }>;
  columns: ColumnDef<T, unknown>[];
  fields: FieldConfig[];
  filters?: FilterConfig[];
  createPayload: () => Record<string, unknown>;
  toPayload: (form: Record<string, unknown>) => Record<string, unknown>;
  toForm: (row: T) => Record<string, unknown>;
  summary?: (rows: T[]) => { label: string; value: string | number }[];
  singular?: string; // display noun, default = title lowercased
}

function singularize(title: string): string {
  const lower = title.toLowerCase();
  if (lower.endsWith("ies")) return lower.slice(0, -3) + "y";
  if (lower.endsWith("s") && !lower.endsWith("ss")) return lower.slice(0, -1);
  return lower;
}

function FieldInput({ field, value, onChange }: {
  field: FieldConfig; value: unknown; onChange: (v: unknown) => void;
}) {
  if (field.type === "checkbox") {
    return (
      <Checkbox checked={Boolean(value)} onCheckedChange={(v) => onChange(v)} />
    );
  }
  if (field.type === "switch") {
    return <Switch checked={Boolean(value)} onCheckedChange={(v) => onChange(v)} />;
  }
  if (field.type === "select") {
    return (
      <Select value={String(value ?? "")} onValueChange={(v) => onChange(v)}>
        <SelectTrigger>
          <SelectValue placeholder="Select…" />
        </SelectTrigger>
        <SelectContent>
          {(field.options ?? []).map((opt) => (
            <SelectItem key={opt} value={opt}>{opt}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }
  if (field.type === "textarea") {
    return (
      <textarea
        className="flex min-h-20 w-full rounded-md border border-input bg-surface px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        placeholder={field.placeholder}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  return (
    <Input
      type={field.type === "number" ? "number" : "text"}
      placeholder={field.placeholder}
      min={field.min}
      value={String(value ?? "")}
      onChange={(e) => onChange(field.type === "number" ? Number(e.target.value) : e.target.value)}
    />
  );
}

export function ResourcePage<T extends { id: number }>({
  title,
  endpoint,
  query,
  columns,
  fields,
  filters = [],
  createPayload,
  toPayload,
  toForm,
  summary,
  singular,
}: ResourcePageProps<T>) {
  const noun = singular ?? singularize(title);
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: [endpoint.split("/").pop()] });

  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [search, setSearch] = useState("");
  const [filtersNow, setFiltersNow] = useState<Record<string, string>>({});
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const params = useMemo<ListParams>(() => {
    const p: ListParams = { skip: page * pageSize, limit: pageSize };
    if (debouncedSearch) p.search = debouncedSearch;
    if (sorting.length) p.sort = `${sorting[0].id}:${sorting[0].desc ? "desc" : "asc"}`;
    for (const [k, v] of Object.entries(filtersNow)) if (v) p[k] = v;
    return p;
  }, [page, pageSize, debouncedSearch, sorting, filtersNow]);

  const { data, isLoading, isError, error, refetch } = query(params);
  const rows = data?.rows ?? [];
  const total = data?.total ?? 0;

  // Auto-append an actions column (Edit + Delete) driven by this component's state.
  const columnsWithActions: ColumnDef<T, unknown>[] = useMemo(
    () => [
      ...columns,
      {
        id: "actions",
        header: () => <span className="sr-only">Actions</span>,
        meta: { align: "right" },
        cell: ({ row }) => <ActionCell onEdit={() => openEdit(row.original)} onDelete={() => remove(row.original)} />,
      },
    ],
    [columns], // openEdit/remove are stable closures below
  );

  // debounce search
  const [debounceTimer, setDebounceTimer] = useState<ReturnType<typeof setTimeout> | null>(null);
  function onSearchChange(v: string) {
    setSearch(v);
    if (debounceTimer) clearTimeout(debounceTimer);
    setDebounceTimer(setTimeout(() => { setDebouncedSearch(v); setPage(0); }, 300));
  }

  function openCreate() {
    setEditingId(null);
    setForm(createPayload());
    setFormError(null);
    setDrawerOpen(true);
  }
  function openEdit(row: T) {
    setEditingId(row.id);
    setForm(toForm(row));
    setFormError(null);
    setDrawerOpen(true);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      const payload = toPayload(form);
      if (editingId === null) {
        await apiPost(endpoint, payload);
        toast.success(`${title} created`);
      } else {
        await apiPut(`${endpoint}/${editingId}`, payload);
        toast.success(`${title} updated`);
      }
      setDrawerOpen(false);
      invalidate();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function remove(row: T) {
    try {
      await apiDelete(`${endpoint}/${row.id}`);
      toast.success(`${noun} deleted`);
      invalidate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <div>
      <div className="mb-5 flex items-end justify-between">
        <div>
          <h1 className="display text-3xl text-ink">{title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{total} record{total === 1 ? "" : "s"}</p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="mr-1 h-4 w-4" /> Add {noun}
        </Button>
      </div>

      {summary && rows.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {summary(rows).map((s) => (
            <div key={s.label} className="flex items-baseline gap-2 rounded-md bg-surface px-4 py-2 shadow-sm">
              <span className="text-lg font-medium tabular-nums text-ink">{s.value}</span>
              <span className="eyebrow">{s.label}</span>
            </div>
          ))}
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3 rounded-md bg-surface p-3 shadow-sm">
        <Input
          className="max-w-xs"
          placeholder={`Search ${title.toLowerCase()}…`}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        {filters.map((f) => (
          <Select
            key={f.name}
            value={filtersNow[f.name] ?? "all"}
            onValueChange={(v) => {
              const next = { ...filtersNow };
              if (v === "all") delete next[f.name];
              else next[f.name] = v;
              setFiltersNow(next);
              setPage(0);
            }}
          >
            <SelectTrigger className="w-44">
              <SelectValue placeholder={f.label} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All {f.label.toLowerCase()}</SelectItem>
              {(f.options ?? []).map((opt) => (
                <SelectItem key={opt} value={opt}>{opt}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        ))}
      </div>

      {isError && (
        <div className="mb-4">
          <ErrorBanner message={error instanceof Error ? error.message : "Failed to load"} onRetry={() => refetch()} />
        </div>
      )}

      <DataTable
        columns={columnsWithActions}
        rows={rows}
        totalCount={total}
        page={page}
        pageSize={pageSize}
        onPageChange={setPage}
        onPageSizeChange={(s) => { setPageSize(s); setPage(0); }}
        sorting={sorting}
        onSortingChange={setSorting}
        loading={isLoading}
        emptyNode={
          <EmptyState
            icon={undefined}
            title={`No ${title.toLowerCase()} yet`}
            body="Add one to get started."
            action={<Button onClick={openCreate}>Add {noun}</Button>}
          />
        }
      />

      {/* Create / edit drawer */}
      <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
        <SheetContent>
          <form onSubmit={save}>
            <SheetHeader>
              <SheetTitle>{editingId === null ? `Add ${noun}` : `Edit ${noun}`}</SheetTitle>
              <SheetDescription>Fill in the details below.</SheetDescription>
            </SheetHeader>
            <div className="mt-4 grid grid-cols-1 gap-4">
              {fields.map((field) => (
                <label key={field.name} className={cn("flex flex-col gap-1.5 text-sm", (field.type === "checkbox" || field.type === "switch") && "flex-row items-center justify-between gap-2")}>
                  <span className="text-sm font-medium text-ink">
                    {field.label}
                    {field.required && <span className="ml-0.5 text-destructive">*</span>}
                  </span>
                  <FieldInput field={field} value={form[field.name]} onChange={(v) => setForm((prev) => ({ ...prev, [field.name]: v }))} />
                </label>
              ))}
              {formError && (
                <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                  {formError}
                </div>
              )}
            </div>
            <Separator className="my-4" />
            <SheetFooter>
              <Button type="button" variant="outline" onClick={() => setDrawerOpen(false)}>Cancel</Button>
              <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
            </SheetFooter>
          </form>
        </SheetContent>
      </Sheet>
    </div>
  );
}

export function ActionCell({ onEdit, onDelete }: { onEdit: () => void; onDelete: () => void }) {
  return (
    <div className="flex justify-end gap-1">
      <Button variant="outline" size="sm" onClick={onEdit}>Edit</Button>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive">
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this record?</AlertDialogTitle>
            <AlertDialogDescription>This cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={onDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
