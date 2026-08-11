"use client";

import { useCallback, useEffect, useState } from "react";
import { apiDelete, apiList, apiPost, apiPut } from "@/lib/api";
import { DataTable } from "./DataTable";
import { Modal } from "./Modal";

interface Column<T> {
  key: string;
  label: string;
  render?: (row: T) => React.ReactNode;
}

export interface FieldConfig {
  name: string;
  label: string;
  type: "text" | "number" | "select" | "checkbox" | "textarea";
  required?: boolean;
  options?: string[]; // for select
  placeholder?: string;
  min?: number;
}

interface FilterConfig {
  name: string;
  label: string;
  options?: string[]; // omitted = free-text input
}

interface ResourceTableProps<T extends { id: number }> {
  title: string;
  endpoint: string; // e.g. "/api/v1/rooms"
  columns: Column<T>[];
  fields: FieldConfig[];
  filters?: FilterConfig[];
  createPayload: () => Record<string, unknown>;
  toPayload: (form: Record<string, unknown>) => Record<string, unknown>;
  toForm: (row: T) => Record<string, unknown>;
}

function truthy(value: unknown): boolean {
  return value !== undefined && value !== null && value !== "";
}

/** Simple singularize: "Rooms" -> "room", "Subjects" -> "subject", and the
 * already-singular titles like "Faculty" / "Groups" pass through unchanged. */
function singular(title: string): string {
  const lower = title.toLowerCase();
  if (lower.endsWith("ies")) return lower.slice(0, -3) + "y";
  if (lower.endsWith("s") && !lower.endsWith("ss")) return lower.slice(0, -1);
  return lower;
}

function Input({ field, value, onChange }: { field: FieldConfig; value: unknown; onChange: (v: unknown) => void }) {
  const base = "field";
  if (field.type === "checkbox") {
    return (
      <input
        type="checkbox"
        className="h-4 w-4 rounded border-slate-300"
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
      />
    );
  }
  if (field.type === "select") {
    return (
      <select
        className={base}
        value={String(value ?? "")}
        required={field.required}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">— select —</option>
        {(field.options ?? []).map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    );
  }
  if (field.type === "textarea") {
    return (
      <textarea
        className={base}
        placeholder={field.placeholder}
        required={field.required}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  return (
    <input
      type={field.type === "number" ? "number" : "text"}
      className={base}
      placeholder={field.placeholder}
      required={field.required}
      min={field.min}
      value={String(value ?? "")}
      onChange={(e) => onChange(field.type === "number" ? Number(e.target.value) : e.target.value)}
    />
  );
}

/**
 * Server-paginated CRUD table for one resource. Handles the list fetch,
 * create/edit/delete calls, filters, and a modal form — the four resource
 * pages (rooms/faculty/groups/subjects) are just configs on top of this.
 */
export function ResourceTable<T extends { id: number }>({
  title,
  endpoint,
  columns,
  fields,
  filters = [],
  createPayload,
  toPayload,
  toForm,
}: ResourceTableProps<T>) {
  const [rows, setRows] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [limit, setLimit] = useState(25);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterValues, setFilterValues] = useState<Record<string, string>>({});

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(
    async (pageSkip: number, pageLimit: number, filtersNow: Record<string, string>) => {
      setLoading(true);
      setError(null);
      try {
        const { rows, total } = await apiList<T>(endpoint, {
          skip: pageSkip,
          limit: pageLimit,
          ...Object.fromEntries(
            Object.entries(filtersNow).filter(([, v]) => truthy(v)),
          ),
        });
        setRows(rows);
        setTotal(total);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        setLoading(false);
      }
    },
    [endpoint],
  );

  useEffect(() => {
    load(skip, limit, filterValues);
  }, [load, skip, limit, filterValues]);

  function openCreate() {
    setEditingId(null);
    setForm(createPayload());
    setFormError(null);
    setModalOpen(true);
  }

  function openEdit(row: T) {
    setEditingId(row.id);
    setForm(toForm(row));
    setFormError(null);
    setModalOpen(true);
  }

  async function save() {
    setSaving(true);
    setFormError(null);
    try {
      const payload = toPayload(form);
      if (editingId === null) {
        await apiPost(endpoint, payload);
      } else {
        await apiPut(`${endpoint}/${editingId}`, payload);
      }
      setModalOpen(false);
      await load(skip, limit, filterValues);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function remove(row: T) {
    if (!window.confirm(`Delete this ${singular(title)}? This cannot be undone.`)) {
      return;
    }
    try {
      await apiDelete(`${endpoint}/${row.id}`);
      await load(skip, limit, filterValues);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="display text-2xl text-ink">{title}</h1>
          <p className="mt-0.5 text-sm text-ink-faint">
            {total} record{total === 1 ? "" : "s"}
          </p>
        </div>
        <button onClick={openCreate} className="btn-primary">
          + Add {singular(title)}
        </button>
      </div>

      {filters.length > 0 && (
        <div className="mb-4 flex flex-wrap items-end gap-4 rounded-sm bg-white p-4 shadow-card">
          {filters.map((filter) => (
            <div key={filter.name} className="flex flex-col gap-1 text-sm">
              <label className="eyebrow font-medium">{filter.label}</label>
              {filter.options ? (
                <select
                  className="field w-auto"
                  value={filterValues[filter.name] ?? ""}
                  onChange={(e) => {
                    const next = { ...filterValues, [filter.name]: e.target.value };
                    setFilterValues(next);
                    setSkip(0);
                  }}
                >
                  <option value="">All</option>
                  {filter.options.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="field w-auto"
                  placeholder={`Filter by ${filter.label.toLowerCase()}…`}
                  value={filterValues[filter.name] ?? ""}
                  onChange={(e) => {
                    const next = { ...filterValues, [filter.name]: e.target.value };
                    setFilterValues(next);
                    setSkip(0);
                  }}
                />
              )}
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-sm border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <DataTable
        columns={[
          ...columns,
          {
            key: "actions",
            label: "",
            render: (row) => (
              <div className="flex gap-2">
                <button
                  onClick={() => openEdit(row)}
                  className="rounded-sm border border-accent-line px-2 py-1 text-xs text-ink hover:bg-canvas-deep"
                >
                  Edit
                </button>
                <button
                  onClick={() => remove(row)}
                  className="rounded-sm border border-red-200 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                >
                  Delete
                </button>
              </div>
            ),
          },
        ]}
        rows={rows}
        total={total}
        skip={skip}
        limit={limit}
        onLimitChange={setLimit}
        onSkipChange={setSkip}
        loading={loading}
      />

      {modalOpen && (
        <Modal title={editingId === null ? `Add ${singular(title)}` : `Edit ${singular(title)}`} onClose={() => setModalOpen(false)}>
          <form
            className="grid grid-cols-1 gap-x-4 gap-y-4 sm:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              save();
            }}
          >
            {fields.map((field) => (
              <label
                key={field.name}
                className={`flex flex-col gap-1 text-sm ${field.type === "checkbox" ? "sm:col-span-2 flex-row items-center gap-2" : ""}`}
              >
                <span className={`text-sm font-medium text-ink ${field.type === "checkbox" ? "order-2" : ""}`}>
                  {field.label}
                  {field.required && <span className="text-red-500"> *</span>}
                </span>
                <Input
                  field={field}
                  value={form[field.name]}
                  onChange={(value) => setForm((prev) => ({ ...prev, [field.name]: value }))}
                />
              </label>
            ))}
            {formError && (
              <div className="rounded-sm border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                {formError}
              </div>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="btn-ghost"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="btn-primary"
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
