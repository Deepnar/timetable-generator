"use client";

import { ResourceTable, type FieldConfig } from "@/components/ResourceTable";
import { ProtectedShell } from "@/components/ProtectedShell";
import type { Faculty } from "@/lib/types";

const FIELDS: FieldConfig[] = [
  { name: "name", label: "Name", type: "text", required: true },
  { name: "email", label: "Email", type: "text", required: true },
  { name: "department", label: "Department", type: "text", required: true },
  { name: "max_hours_per_week", label: "Max hours / week", type: "number", min: 0 },
  { name: "max_hours_per_day", label: "Max hours / day", type: "number", min: 0 },
];

const INITIALS = (name: string) =>
  name.split(/\s+/).slice(0, 2).map((p) => p[0]).join("").toUpperCase();

export default function FacultyPage() {
  return (
    <ProtectedShell>
      <ResourceTable<Faculty>
        title="Faculty"
        endpoint="/api/v1/faculty"
        columns={[
          { key: "name", label: "Name", render: (f) => (
            <div className="flex items-center gap-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-canvas-deep text-xs font-medium text-ink-soft">
                {INITIALS(f.name)}
              </span>
              <span className="font-medium text-ink">{f.name}</span>
            </div>
          )},
          { key: "email", label: "Email", render: (f) => <span className="text-ink-soft">{f.email}</span> },
          { key: "department", label: "Department", render: (f) => (
            <span className="inline-block rounded-full bg-canvas-deep px-2 py-0.5 text-xs font-medium text-ink-soft">
              {f.department}
            </span>
          )},
          { key: "max_hours_per_week", label: "Hrs/week", render: (f) => <span className="tabular-nums">{f.max_hours_per_week}</span> },
          { key: "max_hours_per_day", label: "Hrs/day", render: (f) => <span className="tabular-nums">{f.max_hours_per_day}</span> },
        ]}
        fields={FIELDS}
        filters={[{ name: "department", label: "Department" }]}
        summary={(rows) => {
          const byDept = new Map<string, number>();
          for (const f of rows) byDept.set(f.department, (byDept.get(f.department) ?? 0) + 1);
          const totalHrs = rows.reduce((a, f) => a + f.max_hours_per_week, 0);
          return [
            { label: "Faculty", value: rows.length },
            { label: "Weekly capacity", value: totalHrs },
                        ...Array.from(byDept.entries()).slice(0, 3).map(([k, v]) => ({ label: k, value: v })),
          ];
        }}
        createPayload={() => ({
          name: "",
          email: "",
          department: "",
          max_hours_per_week: 20,
          max_hours_per_day: 5,
        })}
        toPayload={(form) => ({
          name: String(form.name ?? ""),
          email: String(form.email ?? ""),
          department: String(form.department ?? ""),
          max_hours_per_week: Number(form.max_hours_per_week ?? 20),
          max_hours_per_day: Number(form.max_hours_per_day ?? 5),
        })}
        toForm={(faculty) => ({
          name: faculty.name,
          email: faculty.email,
          department: faculty.department,
          max_hours_per_week: faculty.max_hours_per_week,
          max_hours_per_day: faculty.max_hours_per_day,
        })}
      />
    </ProtectedShell>
  );
}
