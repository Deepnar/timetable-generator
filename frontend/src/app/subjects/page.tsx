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
          { key: "name", label: "Name", render: (s) => <span className="font-medium">{s.name}</span> },
          { key: "subject_code", label: "Code" },
          { key: "department", label: "Department" },
          { key: "semester", label: "Sem" },
          { key: "hours_per_week", label: "Hrs/week" },
          { key: "requires_lab", label: "Lab", render: (s) => (s.requires_lab ? "Yes" : "No") },
        ]}
        fields={FIELDS}
        filters={[
          { name: "department", label: "Department" },
          { name: "semester", label: "Semester" },
        ]}
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
