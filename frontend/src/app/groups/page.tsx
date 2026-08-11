"use client";

import type { ColumnDef } from "@tanstack/react-table";
import { ResourcePage, type FieldConfig } from "@/components/ResourcePage";
import { ProtectedShell } from "@/components/ProtectedShell";
import { Badge } from "@/components/ui/badge";
import { useGroups } from "@/hooks/use-resources";
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

const GROUP_TONES: Record<string, "info" | "success" | "warning" | "neutral"> = {
  DIVISION: "info",
  BATCH: "success",
  YEAR: "warning",
  DEPARTMENT: "neutral",
  CUSTOM: "neutral",
};

const columns: ColumnDef<StudentGroup, unknown>[] = [
  {
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => <span className="font-medium text-ink">{row.original.name}</span>,
  },
  {
    accessorKey: "group_type",
    header: "Type",
    cell: ({ row }) => (
      <Badge variant={GROUP_TONES[row.original.group_type] ?? "neutral"}>{row.original.group_type}</Badge>
    ),
  },
  {
    accessorKey: "department",
    header: "Department",
    cell: ({ row }) => <span className="text-muted-foreground">{row.original.department}</span>,
  },
  {
    accessorKey: "year",
    header: "Year",
    cell: ({ row }) => row.original.year ?? "—",
  },
  {
    accessorKey: "semester",
    header: "Sem",
    cell: ({ row }) => row.original.semester ?? "—",
  },
  {
    accessorKey: "strength",
    header: "Strength",
    meta: { align: "right" },
    cell: ({ row }) => <span className="tabular-nums">{row.original.strength}</span>,
  },
];

export default function GroupsPage() {
  return (
    <ProtectedShell>
      <ResourcePage<StudentGroup>
        title="Groups"
        endpoint="/api/v1/groups"
        query={useGroups}
        columns={columns}
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
            ...Array.from(byType.entries()).map(([k, v]) => ({ label: `${k.toLowerCase()}s`, value: v })),
          ];
        }}
        createPayload={() => ({
          name: "", group_type: "DIVISION", department: "", year: null, semester: null,
          strength: 60, incharge_email: "",
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
          name: group.name, group_type: group.group_type, department: group.department,
          year: group.year ?? "", semester: group.semester ?? "",
          strength: group.strength, incharge_email: group.incharge_email ?? "",
        })}
      />
    </ProtectedShell>
  );
}
