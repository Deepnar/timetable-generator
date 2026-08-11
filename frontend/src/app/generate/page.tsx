"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Play, RefreshCw, CalendarDays } from "lucide-react";
import { toast } from "sonner";
import { apiPost } from "@/lib/api";
import { useGenerationStatus, useGenerations, useProfiles } from "@/hooks/use-resources";
import type { Generation } from "@/lib/types";
import { ProtectedShell } from "@/components/ProtectedShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorBanner } from "@/components/ui/error-banner";
import { EmptyState } from "@/components/ui/empty-state";

const STATUS_TONE: Record<string, "success" | "warning" | "info" | "danger" | "neutral"> = {
  PENDING: "warning",
  RUNNING: "info",
  COMPLETED: "success",
  FAILED: "danger",
};

function RunCard({ id }: { id: number }) {
  const { data: run } = useGenerationStatus(id);
  const router = useRouter();
  if (!run) return <Skeleton className="h-20" />;
  return (
    <div className="flex items-center justify-between rounded-md border bg-surface p-4 shadow-sm">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-ink">Run #{run.id}</span>
          <Badge variant={STATUS_TONE[run.generation_status] ?? "neutral"}>{run.generation_status}</Badge>
        </div>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {run.academic_year} · {run.timetable_type} · {run.algorithm_used}
          {run.instances_produced > 0 && ` · ${run.instances_produced}/${run.instances_requested} instances`}
          {run.run_duration_ms != null && ` · ${(run.run_duration_ms / 1000).toFixed(1)}s`}
        </p>
        {run.generation_status === "COMPLETED" && (
          <Button variant="link" size="sm" className="h-6 px-0 text-primary" onClick={() => router.push(`/instances/${run.id}`)}>
            View instances →
          </Button>
        )}
        {run.generation_status === "FAILED" && run.error_log && (
          <p className="mt-1 text-xs text-destructive">{run.error_log.slice(0, 120)}</p>
        )}
        {run.placement_warning && (
          <p className="mt-1 text-xs text-warning">{run.placement_warning}</p>
        )}
      </div>
      {(run.generation_status === "PENDING" || run.generation_status === "RUNNING") && (
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      )}
    </div>
  );
}

export default function GeneratePage() {
  const router = useRouter();
  const qc = useQueryClient();
  const profiles = useProfiles({ limit: 200 });
  const generations = useGenerations({ limit: 20 });

  const [profileId, setProfileId] = useState("");
  const [timetableType, setTimetableType] = useState("CLASS");
  const [algorithm, setAlgorithm] = useState("GREEDY");
  const [instances, setInstances] = useState(3);

  const generate = useMutation<Generation>({
    mutationFn: () =>
      apiPost<Generation>("/api/v1/generate", {
        profile_id: Number(profileId),
        timetable_type: timetableType,
        academic_year: "2026-27",
        instances_requested: instances,
        algorithm,
      }),
    onSuccess: async (gen) => {
      toast.success(`Generation started (run #${gen.id})`);
      await qc.invalidateQueries({ queryKey: ["generations"] });
      router.push(`/generate?run=${gen.id}`);
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : "Generation failed"),
  });

  const canSubmit = profileId !== "" && !generate.isPending;

  return (
    <ProtectedShell>
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Form */}
        <div className="rounded-md border bg-surface p-6 shadow-sm">
          <h1 className="display text-3xl text-ink">New generation</h1>
          <p className="mt-1 text-sm text-muted-foreground">Pick a profile and run the solver.</p>

          {profiles.isError && (
            <div className="mt-4">
              <ErrorBanner message="Failed to load profiles" onRetry={() => profiles.refetch()} />
            </div>
          )}

          <form
            className="mt-6 flex flex-col gap-5"
            onSubmit={(e) => { e.preventDefault(); if (canSubmit) generate.mutate(); }}
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="profile">Profile</Label>
              <Select value={profileId} onValueChange={setProfileId}>
                <SelectTrigger id="profile" className="w-full">
                  <SelectValue placeholder="Select a profile…" />
                </SelectTrigger>
                <SelectContent>
                  {profiles.data?.rows.map((p) => (
                    <SelectItem key={p.id} value={String(p.id)}>
                      {p.name} {p.semester ? `· Sem ${p.semester}` : ""} · {p.department ?? p.scope_type}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="type">Timetable type</Label>
              <Select value={timetableType} onValueChange={setTimetableType}>
                <SelectTrigger id="type" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {["CLASS", "EXAM", "EVENT", "CUSTOM"].map((t) => (
                    <SelectItem key={t} value={t}>{t}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="algo">Solver</Label>
              <Select value={algorithm} onValueChange={setAlgorithm}>
                <SelectTrigger id="algo" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="GREEDY">Greedy (fast preview)</SelectItem>
                  <SelectItem value="OR_TOOLS">OR-Tools CP-SAT</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="instances">Instances</Label>
              <Input
                id="instances"
                type="number"
                min={1}
                max={5}
                value={instances}
                onChange={(e) => setInstances(Number(e.target.value))}
              />
            </div>

            <Button type="submit" disabled={!canSubmit} className="w-full">
              {generate.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {generate.isPending ? "Generating…" : "Generate"}
            </Button>
          </form>
        </div>

        {/* Runs */}
        <div className="rounded-md border bg-surface p-6 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="display text-lg text-ink">Recent runs</h2>
            <Button variant="ghost" size="sm" onClick={() => generations.refetch()}>
              <RefreshCw className="mr-1 h-3.5 w-3.5" /> Refresh
            </Button>
          </div>
          {generations.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20" />)}
            </div>
          ) : generations.data?.rows.length === 0 ? (
            <EmptyState
              icon={CalendarDays}
              title="No runs yet"
              body="Configure a profile and generate your first timetable."
            />
          ) : (
            <div className="flex flex-col gap-2">
              {generations.data?.rows.map((run) => (
                <RunCard key={run.id} id={run.id} />
              ))}
            </div>
          )}
        </div>
      </div>
    </ProtectedShell>
  );
}
