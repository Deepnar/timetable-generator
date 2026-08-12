"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, Download, Pencil, CheckCircle2, X, Wrench } from "lucide-react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { apiPost } from "@/lib/api";
import { useAllInstances } from "@/hooks/use-resources";
import { useGridSessions } from "@/features/timetable/use-grid-sessions";
import { TimetableGrid, type GridSession } from "@/features/timetable/TimetableGrid";
import { SlotEditor } from "@/features/timetable/SlotEditor";
import { ChangeEditor, ChangeList } from "@/features/timetable/ChangePanel";
import { ProtectedShell } from "@/components/ProtectedShell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Badge } from "@/components/ui/badge";

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

  // The instance id IS the path segment; find its metadata via the lookup.
  const all = useAllInstances({ limit: 200 });
  const instance = all.data?.rows.find((i) => i.id === instanceId);

  const { sessions, isLoading, isError, error, refetch, totalSlots, slotCount, slotTime } = useGridSessions(instanceId);

  const [editing, setEditing] = useState<GridSession | null>(null);
  const [anchor, setAnchor] = useState<{ x: number; y: number } | null>(null);
  const [changeMode, setChangeMode] = useState(false);
  const [changing, setChanging] = useState<{ session: GridSession; x: number; y: number } | null>(null);

  const days = Array.from({ length: 6 }, (_, i) => i); // Mon-Sat default

  const editable = instance?.status === "DRAFT" || instance?.status === "SELECTED";
  const changeable = instance?.status === "PUBLISHED";

  function openEditor(session: GridSession, event: React.MouseEvent<HTMLButtonElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    if (changeable && changeMode) {
      setChanging({ session, x: rect.left, y: rect.bottom });
      return;
    }
    setEditing(session);
    setAnchor({ x: rect.left, y: rect.bottom });
  }

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
              <p className="mt-0.5 text-sm text-muted-foreground">
                {totalSlots} scheduled slots{instance ? ` · ${instance.status}` : ""}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => exportInstance("pdf")}>
              <Download className="mr-1 h-4 w-4" /> PDF
            </Button>
            <Button variant="outline" onClick={() => exportInstance("csv")}>CSV</Button>
            <Button variant="outline" onClick={() => exportInstance("ical")}>iCal</Button>
            <Button variant="outline" onClick={() => router.push(`/instances/compare?a=${instanceId}`)}>
              Compare
            </Button>
            {changeable && (
              <Button variant={changeMode ? "default" : "outline"} onClick={() => setChangeMode((v) => !v)}>
                <Wrench className="mr-1 h-4 w-4" /> {changeMode ? "Change mode on" : "Change mode"}
              </Button>
            )}
            <Button variant="outline" onClick={selectInstance}>
              <Pencil className="mr-1 h-4 w-4" /> Select
            </Button>
            <Button onClick={publishInstance}>
              <CheckCircle2 className="mr-1 h-4 w-4" /> Publish
            </Button>
          </div>
        </div>

        {isError && <ErrorBanner message={error instanceof Error ? error.message : "Failed to load"} onRetry={() => refetch()} />}
        {changeable && (
          <div className="rounded-md border border-warning/40 bg-warning/5 px-4 py-2.5 text-sm text-warning">
            This timetable is published. Use <span className="font-semibold">Change mode</span> to record mid-year changes
            (teacher covers, room changes, swaps, temporary windows) without touching the base slots.
          </div>
        )}

        <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
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
                slotTime={slotTime}
                readOnly={!editable && !(changeable && changeMode)}
                onCellClick={(s, e) => openEditor(s, e)}
              />
            )}
          </div>

          {changeable && (
            <div className="rounded-md border bg-surface shadow-sm">
              <div className="border-b px-4 py-3">
                <div className="flex items-center justify-between">
                  <h2 className="display text-lg text-ink">Mid-year changes</h2>
                  <Badge variant="warning">{changeMode ? "Change mode active" : "Read-only"}</Badge>
                </div>
              </div>
              <div className="px-4 pb-4">
                <ChangeList instanceId={instanceId} />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Slot override editor (DRAFT/SELECTED). */}
      {editing && editable && anchor && (
        <div
          className="fixed z-50 w-80 rounded-md border bg-surface p-4 shadow-lg"
          style={{ left: Math.min(anchor.x, Math.max(8, window.innerWidth - 340)), top: Math.min(anchor.y + 6, window.innerHeight - 460) }}
        >
          <div className="mb-2 flex items-start justify-between">
            <p className="eyebrow">Edit slot</p>
            <Button variant="ghost" size="icon" className="-mr-2 -mt-1 h-6 w-6" onClick={() => setEditing(null)}>
              <X className="h-4 w-4" />
            </Button>
          </div>
          <SlotEditor
            key={editing.slotId}
            instanceId={instanceId}
            session={editing}
            days={days}
            slotCount={slotCount}
            onSaved={() => { setEditing(null); qc.invalidateQueries(); }}
          />
        </div>
      )}

      {/* Mid-year change editor (PUBLISHED). */}
      {changing && changeable && (
        <div
          className="fixed z-50 w-80 rounded-md border bg-surface p-4 shadow-lg"
          style={{ left: Math.min(changing.x, Math.max(8, window.innerWidth - 340)), top: Math.min(changing.y + 6, window.innerHeight - 560) }}
        >
          <div className="mb-2 flex items-start justify-between">
            <p className="eyebrow">Apply change</p>
            <Button variant="ghost" size="icon" className="-mr-2 -mt-1 h-6 w-6" onClick={() => setChanging(null)}>
              <X className="h-4 w-4" />
            </Button>
          </div>
          <ChangeEditor
            key={changing.session.slotId}
            instanceId={instanceId}
            cell={changing}
            sessions={sessions}
            onDone={() => setChanging(null)}
          />
        </div>
      )}
    </ProtectedShell>
  );
}
