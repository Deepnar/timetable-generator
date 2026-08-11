"use client";

import { ResourceTable, type FieldConfig } from "@/components/ResourceTable";
import { ProtectedShell } from "@/components/ProtectedShell";
import type { Subject } from "@/lib/types";

const FIELDS: FieldConfig[] = [
  { name: "name", label: "Name", type: "text", required: true },
  { name: "subject_code", label: "Subject code", type: "text", required: true },
  { name: "department", label: "Department", type: "text", required: true },
  { name: "semester", label: "Semester", type: "number", required: true, min: 1 },
  { name: "hours_per_week", label: "Hours / week", type: "number", required: true, min: 0 },
  { name: "requires_lab", label: "Requires lab", type: "checkbox" },
];

export default function SubjectsPage() {
  return (
    <ProtectedShell>
      <ResourceTable<Subject>
        title="Subjects"
        endpoint="/api/v1/subjects"
        columns={[
          { key: "name", label: "Name", render: (s) => <span className="font-medium text-ink">{s.name}</span> },
          { key: "subject_code", label: "Code", render: (s) => <span className="text-ink-faint">{s.subject_code}</span> },
          { key: "department", label: "Department", render: (s) => (
            <span className="inline-block rounded-full bg-canvas-deep px-2 py-0.5 text-xs font-medium text-ink-soft">
              {s.department}
            </span>
          )},
          { key: "semester", label: "Sem", render: (s) => <span className="tabular-nums">{s.semester}</span> },
          { key: "hours_per_week", label: "Hrs/week", render: (s) => <span className="tabular-nums">{s.hours_per_week}</span> },
          { key: "requires_lab", label: "Lab", render: (s) => (
            s.requires_lab
              ? <span className="inline-block rounded-full bg-violet-100 px-2.5 py-0.5 text-xs font-medium text-violet-800">Lab</span>
              : <span className="text-ink-faint">—</span>
          )},
        ]}
        fields={FIELDS}
        filters={[
          { name: "department", label: "Department" },
          { name: "semester", label: "Semester" },
        ]}
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
          name: "",
          subject_code: "",
          department: "",
          semester: 1,
          hours_per_week: 3,
          requires_lab: false,
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
          name: subject.name,
          subject_code: subject.subject_code,
          department: subject.department,
          semester: subject.semester,
          hours_per_week: subject.hours_per_week,
          requires_lab: subject.requires_lab,
        })}
      />
    </ProtectedShell>
  );
}
