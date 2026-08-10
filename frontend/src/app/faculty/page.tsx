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

export default function FacultyPage() {
  return (
    <ProtectedShell>
      <ResourceTable<Faculty>
        title="Faculty"
        endpoint="/api/v1/faculty"
        columns={[
          { key: "name", label: "Name", render: (f) => <span className="font-medium">{f.name}</span> },
          { key: "email", label: "Email" },
          { key: "department", label: "Department" },
          { key: "max_hours_per_week", label: "Hrs/week" },
          { key: "max_hours_per_day", label: "Hrs/day" },
        ]}
        fields={FIELDS}
        filters={[{ name: "department", label: "Department" }]}
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
