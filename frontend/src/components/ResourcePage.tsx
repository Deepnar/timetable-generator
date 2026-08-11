"use client";

import { useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { type ColumnDef, type SortingState } from "@tanstack/react-table";
import { Plus, Trash2, Search } from "lucide-react";
import { toast } from "sonner";
import { apiPost, apiPut, apiDelete, type ListParams } from "@/lib/api";
import { useFacetCounts } from "@/hooks/use-resources";
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
import { Breadcrumbs, FacetSection, FacetTiles, type FacetOption } from "@/components/DrillDown";
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

/** A facet dimension in the drill-down. name = URL query param key. */
export interface DrillFacet {
  name: string;
  label: string;
  values: string[];
  labels?: Record<string, string>; // display overrides (e.g. "SEMINAR_HALL" -> "Seminar hall")
}

interface DrillDownProps {
  /** Level-1 category tiles (e.g. room_type). */
  tile?: DrillFacet;
  /** Deeper facet rail sections (e.g. building, capacity). */
  rail?: DrillFacet[];
}

interface ResourcePageProps<T extends { id: number }> {
  title: string;
  endpoint: string; // e.g. "/api/v1/rooms"
  query: (params: ListParams) => UseQueryResult<{ rows: T[]; total: number }>;
  columns: ColumnDef<T, unknown>[];
  fields: FieldConfig[];
  createPayload: () => Record<string, unknown>;
  toPayload: (form: Record<string, unknown>) => Record<string, unknown>;
  toForm: (row: T) => Record<string, unknown>;
  summary?: (rows: T[]) => { label: string; value: string | number }[];
  drilldown?: DrillDownProps;
  singular?: string;
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
    return <Checkbox checked={Boolean(value)} onCheckedChange={(v) => onChange(v)} />;
  }
  if (field.type === "switch") {
    return <Switch checked={Boolean(value)} onCheckedChange={(v) => onChange(v)} />;
  }
  if (field.type === "select") {
    return (
      <Select value={String(value ?? "")} onValueChange={(v) => onChange(v)}>
        <SelectTrigger><SelectValue placeholder="Select…" /></SelectTrigger>
        <SelectContent>
          {(field.options ?? []).map((opt) => <SelectItem key={opt} value={opt}>{opt}</SelectItem>)}
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
  createPayload,
  toPayload,
  toForm,
  summary,
  drilldown,
  singular,
}: ResourcePageProps<T>) {
  const noun = singular ?? singularize(title);
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: [endpoint.split("/").pop()] });

  // URL-driven drill state (shareable + back-button)
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const page = Number(searchParams.get("skip") ?? 0);
  const pageSize = Number(searchParams.get("limit") ?? 25);
  const search = searchParams.get("q") ?? "";
  const [sorting, setSorting] = useState<SortingState>([]);
  const [debouncedSearch, setDebouncedSearch] = useState(search);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // The set of active drill facets read from the URL.
  const activeFacets = useMemo(() => {
    const out: Record<string, string> = {};
    if (drilldown?.tile) {
      const v = searchParams.get(drilldown.tile.name);
      if (v) out[drilldown.tile.name] = v;
    }
    for (const f of drilldown?.rail ?? []) {
      const v = searchParams.get(f.name);
      if (v) out[f.name] = v;
    }
    return out;
  }, [searchParams, drilldown]);

  function setFacet(name: string, value: string | null) {
    const next = new URLSearchParams(searchParams.toString());
    if (value === null || value === "") next.delete(name);
    else next.set(name, value);
    next.delete("skip"); // reset pagination on drill
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }

  // all drill facets except the one passed — used so a facet's counts show
  // the total within the current branch (excluding its own selection)
  function activeExcept(name: string): ListParams {
    const out: ListParams = {};
    for (const [k, v] of Object.entries(activeFacets)) if (k !== name) out[k] = v;
    return out;
  }

  const params = useMemo<ListParams>(() => {
    const p: ListParams = { skip: page, limit: pageSize };
    if (debouncedSearch) p.search = debouncedSearch;
    if (sorting.length) p.sort = `${sorting[0].id}:${sorting[0].desc ? "desc" : "asc"}`;
    for (const [k, v] of Object.entries(activeFacets)) p[k] = v;
    return p;
  }, [page, pageSize, debouncedSearch, sorting, activeFacets]);

  const { data, isLoading, isError, error, refetch } = query(params);
  const rows = data?.rows ?? [];
  const total = data?.total ?? 0;

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
    [columns],
  );

  // Facet counts (parallel X-Total-Count probes)
  const labelFor = (f: DrillFacet, value: string) => f.labels?.[value] ?? value.replaceAll("_", " ");

  const tileCounts = useFacetCounts<T>(
    endpoint,
    drilldown?.tile?.name ?? "",
    drilldown?.tile?.values ?? [],
    activeExcept(drilldown?.tile?.name ?? ""),
  );
  // One hook per rail facet (fixed count, safe). Each probes its values.
  const rail0 = useFacetCounts<T>(endpoint, drilldown?.rail?.[0]?.name ?? "", drilldown?.rail?.[0]?.values ?? [], activeExcept(drilldown?.rail?.[0]?.name ?? ""));
  const rail1 = useFacetCounts<T>(endpoint, drilldown?.rail?.[1]?.name ?? "", drilldown?.rail?.[1]?.values ?? [], activeExcept(drilldown?.rail?.[1]?.name ?? ""));
  const railCounts = [
    drilldown?.rail?.[0] ? { facet: drilldown.rail[0], results: rail0 } : null,
    drilldown?.rail?.[1] ? { facet: drilldown.rail[1], results: rail1 } : null,
  ].filter((x): x is { facet: DrillFacet; results: ReturnType<typeof useFacetCounts<T>> } => x != null);

  const tileOptions: FacetOption[] = (drilldown?.tile?.values ?? []).map((v, i) => ({
    value: v,
    label: labelFor(drilldown!.tile!, v),
    count: tileCounts[i]?.data?.total,
  }));

  // debounce search into the URL
  const [debounceTimer, setDebounceTimer] = useState<ReturnType<typeof setTimeout> | null>(null);
  function onSearchChange(v: string) {
    setDebouncedSearch(v);
    if (debounceTimer) clearTimeout(debounceTimer);
    setDebounceTimer(setTimeout(() => {
      const next = new URLSearchParams(searchParams.toString());
      if (v) next.set("q", v);
      else next.delete("q");
      next.delete("skip");
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    }, 300));
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

  // Breadcrumb path from active facets (in order: tile first, then rail).
  const crumbs = [
    drilldown?.tile && activeFacets[drilldown.tile.name]
      ? { label: labelFor(drilldown.tile, activeFacets[drilldown.tile.name]), clearLevel: () => setFacet(drilldown.tile!.name, null) }
      : null,
    ...(drilldown?.rail ?? []).map((f) =>
      activeFacets[f.name] ? { label: labelFor(f, activeFacets[f.name]), clearLevel: () => setFacet(f.name, null) } : null,
    ),
  ].filter(Boolean) as { label: string; clearLevel: () => void }[];

  const hasDrill = (drilldown?.tile ?? drilldown?.rail?.length) != null;

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

      {drilldown?.tile && (
        <div className="mb-5">
          <FacetTiles options={tileOptions} active={activeFacets[drilldown.tile.name] ?? null} onSelect={(v) => setFacet(drilldown.tile!.name, v)} />
        </div>
      )}

      <div className="mb-4 flex items-center gap-3 rounded-md bg-surface p-3 shadow-sm">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-8"
            placeholder={`Search ${title.toLowerCase()}…`}
            value={debouncedSearch}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        </div>
      </div>

      <Breadcrumbs crumbs={crumbs} onClearAll={() => {
        const next = new URLSearchParams(searchParams.toString());
        if (drilldown?.tile) next.delete(drilldown.tile.name);
        for (const f of drilldown?.rail ?? []) next.delete(f.name);
        next.delete("skip");
        router.replace(`${pathname}?${next.toString()}`, { scroll: false });
      }} />

      <div className="mt-4 flex gap-6">
        {hasDrill && (
          <div className="hidden w-48 shrink-0 flex-col gap-6 lg:flex">
            {railCounts.map(({ facet, results }) => (
              <FacetSection
                key={facet.name}
                label={facet.label}
                options={facet.values.map((v, i) => ({ value: v, label: labelFor(facet, v), count: results[i]?.data?.total }))}
                active={activeFacets[facet.name] ?? null}
                onSelect={(v) => setFacet(facet.name, v)}
                allCount={total}
              />
            ))}
          </div>
        )}

        <div className="min-w-0 flex-1">
          {isError && (
            <div className="mb-4">
              <ErrorBanner message={error instanceof Error ? error.message : "Failed to load"} onRetry={() => refetch()} />
            </div>
          )}

          <DataTable
            columns={columnsWithActions}
            rows={rows}
            totalCount={total}
            page={Math.floor(page / pageSize)}
            pageSize={pageSize}
            onPageChange={(p) => {
              const next = new URLSearchParams(searchParams.toString());
              next.set("skip", String(p * pageSize));
              router.replace(`${pathname}?${next.toString()}`, { scroll: false });
            }}
            onPageSizeChange={(s) => {
              const next = new URLSearchParams(searchParams.toString());
              next.set("limit", String(s));
              next.delete("skip");
              router.replace(`${pathname}?${next.toString()}`, { scroll: false });
            }}
            sorting={sorting}
            onSortingChange={setSorting}
            loading={isLoading}
            emptyNode={
              <EmptyState
                icon={undefined}
                title={`No ${title.toLowerCase()} found`}
                body={Object.keys(activeFacets).length ? "Try clearing a filter or two." : "Add one to get started."}
                action={<Button onClick={openCreate}>Add {noun}</Button>}
              />
            }
          />
        </div>
      </div>

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
