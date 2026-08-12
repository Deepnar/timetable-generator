"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAllInstances } from "@/hooks/use-resources";
import { ProtectedShell } from "@/components/ProtectedShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorBanner } from "@/components/ui/error-banner";
import { EmptyState } from "@/components/ui/empty-state";
import { Layers } from "lucide-react";

const STATUS_TONE: Record<string, "success" | "warning" | "info" | "danger" | "neutral"> = {
  DRAFT: "neutral",
  SELECTED: "info",
  PUBLISHED: "success",
  ARCHIVED: "neutral",
};

export default function InstancesPage() {
  const router = useRouter();
  // list all instances, newest first — the whole college has 192 (one per class)
  const instances = useAllInstances({ limit: 1000 });

  return (
    <ProtectedShell>
      <div className="flex flex-col gap-5">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="display text-3xl text-ink">Instances</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {instances.data?.rows.length ?? "…"} timetables · one per class.
            </p>
          </div>
          <Button variant="outline" onClick={() => router.push("/generate")}>New generation</Button>
        </div>

        {instances.isError && <ErrorBanner message="Failed to load instances" onRetry={() => instances.refetch()} />}

        <div className="rounded-md border bg-surface">
          {instances.isLoading ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-12" />)}
            </div>
          ) : instances.data?.rows.length === 0 ? (
            <EmptyState
              icon={Layers}
              title="No instances yet"
              body="Run a generation to produce candidate timetables."
              action={<Button onClick={() => router.push("/generate")}>Generate</Button>}
            />
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-2 text-left eyebrow">Instance</th>
                  <th className="px-4 py-2 text-left eyebrow">Status</th>
                  <th className="px-4 py-2 text-left eyebrow">Score</th>
                  <th className="px-4 py-2 text-left eyebrow">Violations</th>
                  <th className="px-4 py-2 text-left eyebrow">Published</th>
                  <th className="px-4 py-2 text-right eyebrow">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {instances.data?.rows.map((inst) => (
                  <tr key={inst.id} className="hover:bg-muted/40">
                    <td className="px-4 py-3">
                      <p className="font-medium text-ink">{inst.class_label ?? `Instance #${inst.id}`}</p>
                      <p className="text-xs text-muted-foreground">#{inst.id} · instance {inst.instance_number}</p>
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={STATUS_TONE[inst.status] ?? "neutral"}>{inst.status}</Badge>
                    </td>
                    <td className="px-4 py-3 tabular-nums text-ink-soft">
                      {inst.soft_score != null ? inst.soft_score.toFixed(3) : "—"}
                    </td>
                    <td className="px-4 py-3 tabular-nums text-ink-soft">
                      {inst.hard_violations > 0 ? (
                        <span className="text-destructive">{inst.hard_violations}</span>
                      ) : (
                        <span className="text-success">0</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {inst.published_at ? new Date(inst.published_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button variant="link" size="sm" onClick={() => router.push(`/instances/compare?a=${inst.id}`)}>
                        Compare
                      </Button>
                      <Button variant="link" size="sm" onClick={() => router.push(`/instances/${inst.id}`)}>
                        View grid →
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </ProtectedShell>
  );
}
