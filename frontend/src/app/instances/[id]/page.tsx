"use client";

import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Download, Pencil, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { apiPost } from "@/lib/api";
import { useGridSessions } from "@/features/timetable/use-grid-sessions";
import { TimetableGrid } from "@/features/timetable/TimetableGrid";
import { ProtectedShell } from "@/components/ProtectedShell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorBanner } from "@/components/ui/error-banner";

const STATUS_TONE: Record<string, "success" | "warning" | "info" | "danger" | "neutral"> = {
  DRAFT: "neutral",
  SELECTED: "info",
  PUBLISHED: "success",
  ARCHIVED: "neutral",
};

export default function InstanceViewerPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const instanceId = Number(params.id);
  const qc = useQueryClient();

  // The instance id IS the path segment; find its generation via the lookup.
  const { sessions, isLoading, isError, error, refetch, totalSlots } = useGridSessions(instanceId);

  const days = Array.from({ length: 6 }, (_, i) => i); // Mon-Sat default
  const slotCount = 8;

  async function selectInstance() {
    try {
      await apiPost(`/api/v1/instances/${instanceId}/select`);
      toast.success("Instance selected");
      qc.invalidateQueries();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Select failed");
    }
  }
  async function publishInstance() {
    try {
      await apiPost(`/api/v1/instances/${instanceId}/publish`);
      toast.success("Published — previous instance archived");
      qc.invalidateQueries();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Publish failed");
    }
  }
  async function exportInstance(ext: string) {
    try {
      const token = typeof window !== "undefined" ? window.localStorage.getItem("timetable_token") : null;
      const res = await fetch(`http://localhost:8000/api/v1/export/instances/${instanceId}/${ext}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(res.statusText);
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `instance-${instanceId}.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    }
  }

  return (
    <ProtectedShell>
      <div className="flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" onClick={() => router.push("/instances")}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div>
              <h1 className="display text-3xl text-ink">Instance #{instanceId}</h1>
              <p className="mt-0.5 text-sm text-muted-foreground">{totalSlots} scheduled slots</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => exportInstance("pdf")}>
              <Download className="mr-1 h-4 w-4" /> PDF
            </Button>
            <Button variant="outline" onClick={() => exportInstance("csv")}>CSV</Button>
            <Button variant="outline" onClick={() => exportInstance("ical")}>iCal</Button>
            <Button variant="outline" onClick={selectInstance}>
              <Pencil className="mr-1 h-4 w-4" /> Select
            </Button>
            <Button onClick={publishInstance}>
              <CheckCircle2 className="mr-1 h-4 w-4" /> Publish
            </Button>
          </div>
        </div>

        {isError && <ErrorBanner message={error instanceof Error ? error.message : "Failed to load"} onRetry={() => refetch()} />}

        <div className="rounded-md border bg-surface p-4 shadow-sm">
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-12" />)}
            </div>
          ) : (
            <TimetableGrid
              sessions={sessions}
              days={days}
              slotCount={slotCount}
              readOnly
            />
          )}
        </div>
      </div>
    </ProtectedShell>
  );
}
