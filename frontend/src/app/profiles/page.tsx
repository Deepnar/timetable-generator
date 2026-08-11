"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Settings2, Archive, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { apiDelete, apiPost } from "@/lib/api";
import { useProfiles } from "@/hooks/use-resources";
import type { Profile } from "@/lib/types";
import { ProtectedShell } from "@/components/ProtectedShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorBanner } from "@/components/ui/error-banner";
import { EmptyState } from "@/components/ui/empty-state";
import { Separator } from "@/components/ui/separator";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

const SCOPE_LABELS: Record<string, string> = {
  DEPARTMENT: "Department",
  YEAR: "Year",
  DIVISION: "Division",
  EVENT: "Event",
  EXAM: "Exam",
  CUSTOM: "Custom",
};

const SCOPE_TONE: Record<string, "neutral" | "info" | "success" | "warning" | "danger"> = {
  DEPARTMENT: "neutral",
  YEAR: "info",
  DIVISION: "success",
  EVENT: "warning",
  EXAM: "danger",
};

export default function ProfilesPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const profiles = useProfiles({ limit: 200 });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["profiles"] });

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    name: "", description: "", scope_type: "DIVISION",
    academic_year: "2026-27", semester: "1", department: "",
  });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      apiPost<Profile>("/api/v1/profiles", {
        name: form.name,
        description: form.description || null,
        scope_type: form.scope_type,
        academic_year: form.academic_year,
        semester: form.semester ? Number(form.semester) : null,
        department: form.department || null,
      }),
    onSuccess: (p) => {
      toast.success("Profile created");
      setOpen(false);
      invalidate();
      router.push(`/profiles/${p.id}`);
    },
    onError: (e) => setFormError(e instanceof Error ? e.message : "Create failed"),
  });

  async function archive(id: number) {
    try {
      await apiDelete(`/api/v1/profiles/${id}`);
      toast.success("Profile archived");
      invalidate();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Archive failed");
    }
  }

  const rows = profiles.data?.rows ?? [];

  return (
    <ProtectedShell>
      <div className="flex flex-col gap-5">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="display text-3xl text-ink">Profiles</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Named presets: resources + constraints + parameters, ready to generate.
            </p>
          </div>
          <Button onClick={() => { setFormError(null); setOpen(true); }}>
            <Plus className="mr-1 h-4 w-4" /> New profile
          </Button>
        </div>

        {profiles.isError && <ErrorBanner message="Failed to load profiles" onRetry={() => profiles.refetch()} />}

        {profiles.isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-40" />)}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            icon={Settings2}
            title="No profiles yet"
            body="Create a profile to bundle the resources, constraints, and parameters a timetable run needs."
            action={<Button onClick={() => setOpen(true)}>New profile</Button>}
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {rows.map((p) => (
              <div
                key={p.id}
                className="flex cursor-pointer flex-col justify-between rounded-md border bg-surface p-5 shadow-sm transition-shadow hover:shadow-md"
                onClick={() => router.push(`/profiles/${p.id}`)}
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <h2 className="display text-lg text-ink">{p.name}</h2>
                    <div className="flex shrink-0 gap-1">
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground" onClick={(e) => e.stopPropagation()}>
                            <Archive className="h-4 w-4" />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Archive this profile?</AlertDialogTitle>
                            <AlertDialogDescription>
                              The profile is disabled and hidden from generation pickers. Existing runs keep their data.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel onClick={(e) => e.stopPropagation()}>Cancel</AlertDialogCancel>
                            <AlertDialogAction onClick={(e) => { e.stopPropagation(); archive(p.id); }}>Archive</AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <Badge variant={SCOPE_TONE[p.scope_type] ?? "neutral"}>{SCOPE_LABELS[p.scope_type] ?? p.scope_type}</Badge>
                    {p.semester && <Badge variant="neutral">Sem {p.semester}</Badge>}
                    {p.department && <Badge variant="neutral">{p.department}</Badge>}
                  </div>
                  {p.description && <p className="mt-3 line-clamp-2 text-sm text-muted-foreground">{p.description}</p>}
                </div>
                <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
                  <span>{p.academic_year}</span>
                  <span className="flex items-center gap-1 text-primary">
                    Configure <Settings2 className="h-3 w-3" />
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create drawer */}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent>
          <form
            onSubmit={(e) => { e.preventDefault(); setSaving(true); create.mutate(); }}
            className="flex h-full flex-col"
          >
            <SheetHeader>
              <SheetTitle>New profile</SheetTitle>
              <SheetDescription>Bundle resources, constraints, and parameters.</SheetDescription>
            </SheetHeader>
            <div className="mt-4 flex flex-1 flex-col gap-4">
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="text-sm font-medium text-ink">Name *</span>
                <Input required value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="e.g. Computer Engineering — Sem 3" />
              </label>
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="text-sm font-medium text-ink">Scope *</span>
                <Select value={form.scope_type} onValueChange={(v) => setForm((f) => ({ ...f, scope_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(SCOPE_LABELS).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                  </SelectContent>
                </Select>
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="text-sm font-medium text-ink">Academic year *</span>
                  <Input required value={form.academic_year} onChange={(e) => setForm((f) => ({ ...f, academic_year: e.target.value }))} placeholder="2026-27" />
                </label>
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="text-sm font-medium text-ink">Semester</span>
                  <Input type="number" min={1} max={8} value={form.semester} onChange={(e) => setForm((f) => ({ ...f, semester: e.target.value }))} />
                </label>
              </div>
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="text-sm font-medium text-ink">Department</span>
                <Input value={form.department} onChange={(e) => setForm((f) => ({ ...f, department: e.target.value }))} placeholder="e.g. Computer Engineering" />
              </label>
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="text-sm font-medium text-ink">Description</span>
                <Input value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
              </label>
              {formError && (
                <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{formError}</div>
              )}
            </div>
            <Separator className="my-4" />
            <SheetFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
              <Button type="submit" disabled={saving}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                {saving ? "Creating…" : "Create"}
              </Button>
            </SheetFooter>
          </form>
        </SheetContent>
      </Sheet>
    </ProtectedShell>
  );
}
