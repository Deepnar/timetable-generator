"use client";

import type { ColumnDef } from "@tanstack/react-table";
import { ResourcePage, type FieldConfig } from "@/components/ResourcePage";
import { ProtectedShell } from "@/components/ProtectedShell";
import { Avatar, AvatarFallback, initialsFor } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { useFaculty } from "@/hooks/use-resources";
import type { Faculty } from "@/lib/types";

const FIELDS: FieldConfig[] = [
  { name: "name", label: "Name", type: "text", required: true },
  { name: "email", label: "Email", type: "text", required: true },
  { name: "department", label: "Department", type: "text", required: true },
  { name: "max_hours_per_week", label: "Max hours / week", type: "number", min: 0 },
  { name: "max_hours_per_day", label: "Max hours / day", type: "number", min: 0 },
];

const columns: ColumnDef<Faculty, unknown>[] = [
  {
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => (
      <div className="flex items-center gap-3">
        <Avatar className="h-8 w-8">
          <AvatarFallback>{initialsFor(row.original.name)}</AvatarFallback>
        </Avatar>
        <span className="font-medium text-ink">{row.original.name}</span>
      </div>
    ),
  },
  {
    accessorKey: "email",
    header: "Email",
    cell: ({ row }) => <span className="text-muted-foreground">{row.original.email}</span>,
  },
  {
    accessorKey: "department",
    header: "Department",
    cell: ({ row }) => (
      <Badge variant="neutral">{row.original.department}</Badge>
    ),
  },
  {
    accessorKey: "max_hours_per_week",
    header: "Hrs/week",
    meta: { align: "right" },
    cell: ({ row }) => <span className="tabular-nums">{row.original.max_hours_per_week}</span>,
  },
  {
    accessorKey: "max_hours_per_day",
    header: "Hrs/day",
    meta: { align: "right" },
    cell: ({ row }) => <span className="tabular-nums">{row.original.max_hours_per_day}</span>,
  },
];

export default function FacultyPage() {
  return (
    <ProtectedShell>
      <ResourcePage<Faculty>
        title="Faculty"
        endpoint="/api/v1/faculty"
        query={useFaculty}
        columns={columns}
        fields={FIELDS}
        drilldown={{
          rail: [{ name: "department", label: "Department", values: ["Computer Engineering", "Information Technology", "Mechanical Engineering", "Civil Engineering", "Electronics & Telecommunication", "Electronics Engineering", "Electrical Engineering", "Chemical Engineering", "Instrumentation Engineering", "Artificial Intelligence & Data Science", "Artificial Intelligence & ML", "Computer Science & Business Systems"] }],
        }}
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
          name: "", email: "", department: "", max_hours_per_week: 20, max_hours_per_day: 5,
        })}
        toPayload={(form) => ({
          name: String(form.name ?? ""),
          email: String(form.email ?? ""),
          department: String(form.department ?? ""),
          max_hours_per_week: Number(form.max_hours_per_week ?? 20),
          max_hours_per_day: Number(form.max_hours_per_day ?? 5),
        })}
        toForm={(faculty) => ({
          name: faculty.name, email: faculty.email, department: faculty.department,
          max_hours_per_week: faculty.max_hours_per_week, max_hours_per_day: faculty.max_hours_per_day,
        })}
      />
    </ProtectedShell>
  );
}
