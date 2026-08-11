"use client";

import { useMemo, useState } from "react";
import { useQueryClient, useQueries } from "@tanstack/react-query";
import { Plus, Save, Trash2, Sparkles, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { apiList, apiPost, apiPut, apiDelete } from "@/lib/api";
import { useSubjects, useGroups, useFaculty } from "@/hooks/use-resources";
import type { SubjectAssignment } from "@/lib/types";
import { ProtectedShell } from "@/components/ProtectedShell";
import { Avatar, AvatarFallback, initialsFor } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorBanner } from "@/components/ui/error-banner";
import { EmptyState } from "@/components/ui/empty-state";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

interface CellRef {
  subjectId: number;
  groupId: number;
  x: number;
  y: number;
}

export default function AssignmentsPage() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["assignments"] });

  // Departments are derived from the group list (capped at 200 rows: 192 groups).
  const groupsQ = useGroups({ limit: 200 });
  const departments = useMemo(() => {
    const set = new Set<string>();
    for (const g of groupsQ.data?.rows ?? []) if (g.department) set.add(g.department);
    return Array.from(set).sort();
  }, [groupsQ.data]);

  const [dept, setDept] = useState("");
  const [sem, setSem] = useState("1");

  const subjectsQ = useSubjects({ department: dept, semester: Number(sem), limit: 200 });
  const facultyQ = useFaculty({ department: dept, limit: 200 });

  // Groups in scope = this department + semester.
  const matrixGroups = useMemo(
    () => (groupsQ.data?.rows ?? []).filter((g) => g.department === dept && g.semester === Number(sem)),
    [groupsQ.data, dept, sem],
  );

  // One assignments query per in-scope group (bounded: ≤6 rows each).
  const groupAssign = useQueries({
    queries: matrixGroups.map((g) => ({
      queryKey: ["assignments", { group_id: g.id }] as const,
      queryFn: () => apiList<SubjectAssignment>("/api/v1/assignments", { group_id: g.id, limit: 200 }),
    })),
  });

  const assignments = useMemo(() => {
    const map = new Map<string, SubjectAssignment>();
    for (const q of groupAssign) {
      for (const a of q.data?.rows ?? []) map.set(`${a.subject_id}:${a.group_id}`, a);
    }
    return map;
  }, [groupAssign]);

  const subjects = useMemo(
    () => (subjectsQ.data?.rows ?? []).slice().sort((a, b) => a.subject_code.localeCompare(b.subject_code)),
    [subjectsQ.data],
  );
  const faculty = useMemo(() => facultyQ.data?.rows ?? [], [facultyQ.data]);

  const [editing, setEditing] = useState<CellRef | null>(null);
  const [editFaculty, setEditFaculty] = useState("");
  const [editHours, setEditHours] = useState(3);
  const [saving, setSaving] = useState(false);
  const [filling, setFilling] = useState(false);

  const isLoading = groupsQ.isLoading || subjectsQ.isLoading || groupAssign.some((q) => q.isLoading);
  const isError = groupsQ.isError || subjectsQ.isError || groupAssign.some((q) => q.isError);

  const semesters = Array.from({ length: 8 }, (_, i) => String(i + 1));

  function openCell(subjectId: number, groupId: number, event: React.MouseEvent<HTMLButtonElement>) {
    const a = assignments.get(`${subjectId}:${groupId}`);
    const rect = event.currentTarget.getBoundingClientRect();
    setEditing({ subjectId, groupId, x: rect.left, y: rect.bottom });
    setEditFaculty(a?.faculty_id ? String(a.faculty_id) : "");
    setEditHours(a?.weekly_hours ?? 3);
  }

  async function saveCell() {
    if (!editing) return;
    setSaving(true);
    const existing = assignments.get(`${editing.subjectId}:${editing.groupId}`);
    try {
      if (existing) {
        await apiPut(`/api/v1/assignments/${existing.id}`, {
          faculty_id: editFaculty ? Number(editFaculty) : null,
          weekly_hours: editHours,
        });
        toast.success("Assignment updated");
      } else {
        await apiPost("/api/v1/assignments", {
          subject_id: editing.subjectId,
          group_id: editing.groupId,
          faculty_id: editFaculty ? Number(editFaculty) : null,
          weekly_hours: editHours,
        });
        toast.success("Assignment created");
      }
      setEditing(null);
      invalidate();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function deleteCell() {
    if (!editing) return;
    const existing = assignments.get(`${editing.subjectId}:${editing.groupId}`);
    if (!existing) return;
    setSaving(true);
    try {
      await apiDelete(`/api/v1/assignments/${existing.id}`);
      toast.success("Assignment removed");
      setEditing(null);
      invalidate();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setSaving(false);
    }
  }

  /** Assign the least-loaded in-department faculty to every empty cell. */
  async function autoFill() {
    if (!subjects.length || !matrixGroups.length) return;
    setFilling(true);
    const load = new Map<number, number>();
    for (const a of assignments.values()) {
      if (a.faculty_id) load.set(a.faculty_id, (load.get(a.faculty_id) ?? 0) + a.weekly_hours);
    }
    let created = 0;
    try {
      for (const subject of subjects) {
        for (const group of matrixGroups) {
          if (assignments.has(`${subject.id}:${group.id}`)) continue;
          // Least-loaded faculty in the department; skip anyone at 20h/week.
          let pick: { id: number; load: number } | null = null;
          for (const f of faculty) {
            const l = load.get(f.id) ?? 0;
            if (l >= 20) continue;
            if (!pick || l < pick.load) pick = { id: f.id, load: l };
          }
          if (!pick) continue;
          await apiPost("/api/v1/assignments", {
            subject_id: subject.id,
            group_id: group.id,
            faculty_id: pick.id,
            weekly_hours: subject.hours_per_week,
          });
          load.set(pick.id, pick.load + subject.hours_per_week);
          created += 1;
        }
      }
      toast.success(`Auto-filled ${created} assignment${created === 1 ? "" : "s"}`);
      invalidate();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Auto-fill failed");
    } finally {
      setFilling(false);
    }
  }

  const covered = subjects.map((s) => {
    const count = matrixGroups.filter((g) => assignments.has(`${s.id}:${g.id}`)).length;
    return { subject: s, count, total: matrixGroups.length };
  });
  const totalAssigned = assignments.size;

  return (
    <ProtectedShell>
      <div className="flex flex-col gap-5">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="display text-3xl text-ink">Assignments</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Who teaches which subject to which division. {totalAssigned} assignments in view.
            </p>
          </div>
          <Button variant="outline" onClick={autoFill} disabled={filling || !subjects.length || !matrixGroups.length}>
            {filling ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            {filling ? "Filling…" : "Auto-fill unassigned"}
          </Button>
        </div>

        {/* Scope picker */}
        <div className="flex flex-wrap items-end gap-4 rounded-md border bg-surface p-4 shadow-sm">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dept">Department</Label>
            <Select value={dept} onValueChange={setDept}>
              <SelectTrigger id="dept" className="w-72"><SelectValue placeholder="Select a department…" /></SelectTrigger>
              <SelectContent>
                {departments.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sem">Semester</Label>
            <Select value={sem} onValueChange={setSem}>
              <SelectTrigger id="sem" className="w-28"><SelectValue /></SelectTrigger>
              <SelectContent>
                {semesters.map((s) => <SelectItem key={s} value={s}>Sem {s}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>

        {isError && <ErrorBanner message="Failed to load assignments" />}

        {isLoading ? (
          <div className="space-y-2"><Skeleton className="h-64 w-full" /></div>
        ) : !dept ? (
          <EmptyState
            icon={Plus}
            title="Pick a department"
            body="Select a department and semester to see the subject × group matrix."
          />
        ) : (
          <div className="overflow-x-auto rounded-md border bg-surface shadow-sm">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="sticky left-0 z-10 bg-muted/50 px-4 py-2 text-left eyebrow">Subject</th>
                  {matrixGroups.map((g) => (
                    <th key={g.id} className="px-4 py-2 text-center eyebrow">
                      {g.name} <span className="ml-1 font-normal text-muted-foreground">({g.strength})</span>
                    </th>
                  ))}
                  <th className="px-4 py-2 text-center eyebrow">Coverage</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {covered.map(({ subject, count, total }) => (
                  <tr key={subject.id} className="hover:bg-muted/30">
                    <td className="sticky left-0 z-10 bg-surface px-4 py-3">
                      <p className="font-mono text-xs font-semibold text-primary">{subject.subject_code}</p>
                      <p className="max-w-56 truncate font-medium text-ink">{subject.name}</p>
                      <p className="text-xs text-muted-foreground">{subject.hours_per_week}h/wk</p>
                    </td>
                    {matrixGroups.map((g) => {
                      const a = assignments.get(`${subject.id}:${g.id}`);
                      const f = a?.faculty_id != null ? faculty.find((x) => x.id === a.faculty_id) : undefined;
                      return (
                        <td key={g.id} className="px-2 py-2 text-center">
                          <button
                            type="button"
                            onClick={(e) => openCell(subject.id, g.id, e)}
                            className={cn(
                              "flex w-full items-center justify-center gap-2 rounded-md border px-2 py-2 text-left transition-colors",
                              a
                                ? "border-border bg-surface hover:shadow-sm"
                                : "border-dashed border-border text-muted-foreground hover:border-ink-soft",
                            )}
                          >
                            {a ? (
                              <>
                                <Avatar className="h-6 w-6">
                                  <AvatarFallback>{initialsFor(f?.name ?? "?")}</AvatarFallback>
                                </Avatar>
                                <span className="min-w-0 flex-1">
                                  <span className="block truncate text-xs font-medium text-ink">{f?.name ?? "—"}</span>
                                </span>
                                <Badge variant="neutral" className="shrink-0">{a.weekly_hours}h</Badge>
                              </>
                            ) : (
                              <span className="flex items-center gap-1 text-xs">
                                <Plus className="h-3 w-3" /> Assign
                              </span>
                            )}
                          </button>
                        </td>
                      );
                    })}
                    <td className="px-4 py-3 text-center">
                      <Badge variant={count === total && total > 0 ? "success" : count > 0 ? "warning" : "neutral"}>
                        {count}/{total}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Cell editor (anchored to the clicked cell) */}
      {editing && (
        <div
          className="fixed z-50 w-80 rounded-md border bg-surface p-4 shadow-lg"
          style={{ left: Math.min(editing.x, Math.max(8, window.innerWidth - 340)), top: Math.min(editing.y + 6, window.innerHeight - 380) }}
        >
          <div className="mb-2 flex items-start justify-between">
            <p className="eyebrow">Edit assignment</p>
            <Button variant="ghost" size="icon" className="-mr-2 -mt-1 h-6 w-6" onClick={() => setEditing(null)}>
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Faculty</Label>
              <Select value={editFaculty} onValueChange={setEditFaculty}>
                <SelectTrigger className="h-8"><SelectValue placeholder="Unassigned" /></SelectTrigger>
                <SelectContent>
                  {faculty.map((f) => (
                    <SelectItem key={f.id} value={String(f.id)}>{f.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="hours">Weekly hours</Label>
              <Input id="hours" type="number" min={1} max={40} value={editHours} onChange={(e) => setEditHours(Number(e.target.value))} />
            </div>
            <div className="flex gap-2">
              {assignments.has(`${editing.subjectId}:${editing.groupId}`) && (
                <Button variant="outline" className="text-destructive" onClick={deleteCell} disabled={saving}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}
              <Button onClick={saveCell} disabled={saving} className="flex-1">
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                {saving ? "Saving…" : "Save"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </ProtectedShell>
  );
}
