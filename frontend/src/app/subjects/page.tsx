"use client";

import type { ColumnDef } from "@tanstack/react-table";
import { ResourcePage, type FieldConfig } from "@/components/ResourcePage";
import { ProtectedShell } from "@/components/ProtectedShell";
import { Badge } from "@/components/ui/badge";
import { useSubjects } from "@/hooks/use-resources";
import type { Subject } from "@/lib/types";

const FIELDS: FieldConfig[] = [
  { name: "name", label: "Name", type: "text", required: true },
  { name: "subject_code", label: "Subject code", type: "text", required: true },
  { name: "department", label: "Department", type: "text", required: true },
  { name: "semester", label: "Semester", type: "number", required: true, min: 1 },
  { name: "hours_per_week", label: "Hours / week", type: "number", required: true, min: 0 },
  { name: "requires_lab", label: "Requires lab", type: "switch" },
];

const columns: ColumnDef<Subject, unknown>[] = [
  {
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => <span className="font-medium text-ink">{row.original.name}</span>,
  },
  {
    accessorKey: "subject_code",
    header: "Code",
    cell: ({ row }) => <span className="font-mono text-xs text-muted-foreground">{row.original.subject_code}</span>,
  },
  {
    accessorKey: "department",
    header: "Department",
    cell: ({ row }) => <Badge variant="neutral">{row.original.department}</Badge>,
  },
  {
    accessorKey: "semester",
    header: "Sem",
    meta: { align: "right" },
    cell: ({ row }) => <span className="tabular-nums">{row.original.semester}</span>,
  },
  {
    accessorKey: "hours_per_week",
    header: "Hrs/week",
    meta: { align: "right" },
    cell: ({ row }) => <span className="tabular-nums">{row.original.hours_per_week}</span>,
  },
  {
    accessorKey: "requires_lab",
    header: "Lab",
    cell: ({ row }) =>
      row.original.requires_lab ? (
        <Badge variant="success">Lab</Badge>
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
  },
];

export default function SubjectsPage() {
  return (
    <ProtectedShell>
      <ResourcePage<Subject>
        title="Subjects"
        endpoint="/api/v1/subjects"
        query={useSubjects}
        columns={columns}
        fields={FIELDS}
        drilldown={{
          tile: { name: "semester", label: "Semester", values: ["1", "2", "3", "4", "5", "6", "7", "8"], labels: { "1": "Sem 1", "2": "Sem 2", "3": "Sem 3", "4": "Sem 4", "5": "Sem 5", "6": "Sem 6", "7": "Sem 7", "8": "Sem 8" } },
          rail: [
            { name: "department", label: "Department", values: ["Computer Engineering", "Information Technology", "Mechanical Engineering", "Civil Engineering", "Electronics & Telecommunication", "Electronics Engineering", "Electrical Engineering", "Chemical Engineering", "Instrumentation Engineering", "Artificial Intelligence & Data Science", "Artificial Intelligence & ML", "Computer Science & Business Systems"] },
            { name: "requires_lab", label: "Lab", values: ["true", "false"], labels: { "true": "Lab", "false": "Theory" } },
          ],
        }}
        summary={(rows) => {
          const byDept = new Map<string, number>();
          const labs = rows.filter((s) => s.requires_lab).length;
          const totalHrs = rows.reduce((a, s) => a + s.hours_per_week, 0);
          for (const s of rows) byDept.set(s.department, (byDept.get(s.department) ?? 0) + 1);
          return [
            { label: "Subjects", value: rows.length },
            { label: "Lab-based", value: labs },
            { label: "Hours/week", value: totalHrs },
            ...Array.from(byDept.entries()).slice(0, 2).map(([k, v]) => ({ label: k, value: v })),
          ];
        }}
        createPayload={() => ({
          name: "", subject_code: "", department: "", semester: 1, hours_per_week: 3, requires_lab: false,
        })}
        toPayload={(form) => ({
          name: String(form.name ?? ""),
          subject_code: String(form.subject_code ?? ""),
          department: String(form.department ?? ""),
          semester: Number(form.semester ?? 1),
          hours_per_week: Number(form.hours_per_week ?? 3),
          requires_lab: Boolean(form.requires_lab),
        })}
        toForm={(subject) => ({
          name: subject.name, subject_code: subject.subject_code, department: subject.department,
          semester: subject.semester, hours_per_week: subject.hours_per_week, requires_lab: subject.requires_lab,
        })}
      />
    </ProtectedShell>
  );
}
