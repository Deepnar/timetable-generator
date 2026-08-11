"use client";

import { ResourceTable, type FieldConfig } from "@/components/ResourceTable";
import { ProtectedShell } from "@/components/ProtectedShell";
import type { StudentGroup } from "@/lib/types";

const GROUP_TYPES = ["DIVISION", "BATCH", "YEAR", "DEPARTMENT", "CUSTOM"];

const FIELDS: FieldConfig[] = [
  { name: "name", label: "Name", type: "text", required: true },
  { name: "group_type", label: "Group type", type: "select", options: GROUP_TYPES, required: true },
  { name: "department", label: "Department", type: "text", required: true },
  { name: "year", label: "Year", type: "number", min: 1 },
  { name: "semester", label: "Semester", type: "number", min: 1 },
  { name: "strength", label: "Strength", type: "number", required: true, min: 0 },
  { name: "incharge_email", label: "Incharge email", type: "text" },
];

const GROUP_STYLES: Record<string, string> = {
  DIVISION: "bg-sky-100 text-sky-800",
  BATCH: "bg-violet-100 text-violet-800",
  YEAR: "bg-amber-100 text-amber-800",
  DEPARTMENT: "bg-emerald-100 text-emerald-800",
  CUSTOM: "bg-canvas-deep text-ink-soft",
};

export default function GroupsPage() {
  return (
    <ProtectedShell>
      <ResourceTable<StudentGroup>
        title="Groups"
        endpoint="/api/v1/groups"
        columns={[
          { key: "name", label: "Name", render: (g) => <span className="font-medium text-ink">{g.name}</span> },
          { key: "group_type", label: "Type", render: (g) => (
            <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${GROUP_STYLES[g.group_type] ?? "bg-canvas-deep text-ink-soft"}`}>
              {g.group_type}
            </span>
          )},
          { key: "department", label: "Department", render: (g) => <span className="text-ink-soft">{g.department}</span> },
          { key: "year", label: "Year", render: (g) => g.year ?? "—" },
          { key: "semester", label: "Sem", render: (g) => g.semester ?? "—" },
          { key: "strength", label: "Strength", render: (g) => <span className="tabular-nums">{g.strength}</span> },
        ]}
        fields={FIELDS}
        filters={[
          { name: "group_type", label: "Group type", options: GROUP_TYPES },
          { name: "department", label: "Department" },
        ]}
        summary={(rows) => {
          const byType = new Map<string, number>();
          const totalStudents = rows.reduce((a, g) => a + (g.strength ?? 0), 0);
          for (const g of rows) byType.set(g.group_type, (byType.get(g.group_type) ?? 0) + 1);
          return [
            { label: "Groups", value: rows.length },
            { label: "Students", value: totalStudents },
                        ...Array.from(byType.entries()).map(([k, v]) => ({ label: k.toLowerCase(), value: v })),
          ];
        }}
        createPayload={() => ({
          name: "",
          group_type: "DIVISION",
          department: "",
          year: null,
          semester: null,
          strength: 60,
          incharge_email: "",
        })}
        toPayload={(form) => ({
          name: String(form.name ?? ""),
          group_type: String(form.group_type ?? "DIVISION"),
          department: String(form.department ?? ""),
          year: form.year !== "" && form.year !== null ? Number(form.year) : null,
          semester: form.semester !== "" && form.semester !== null ? Number(form.semester) : null,
          strength: Number(form.strength ?? 0),
          incharge_email: form.incharge_email ? String(form.incharge_email) : null,
        })}
        toForm={(group) => ({
          name: group.name,
          group_type: group.group_type,
          department: group.department,
          year: group.year ?? "",
          semester: group.semester ?? "",
          strength: group.strength,
          incharge_email: group.incharge_email ?? "",
        })}
      />
    </ProtectedShell>
  );
}
