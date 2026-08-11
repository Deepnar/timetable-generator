"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, GitCompareArrows, MoveRight } from "lucide-react";
import { useAllInstances } from "@/hooks/use-resources";
import { useCompare } from "@/features/timetable/use-compare";
import { TimetableGrid } from "@/features/timetable/TimetableGrid";
import { ProtectedShell } from "@/components/ProtectedShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorBanner } from "@/components/ui/error-banner";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const DIFF_TONE: Record<string, "success" | "info" | "danger" | "neutral"> = {
  added: "success",
  changed: "info",
  removed: "danger",
};

function slotTimeLabel(slot: number) {
  return `${String(8 + Math.floor((slot - 1) / 2)).padStart(2, "0")}:${(slot - 1) % 2 ? "30" : "00"}`;
}

function CompareInner() {
  const params = useSearchParams();
  const router = useRouter();
  const aId = Number(params.get("a")) || undefined;
  const bId = Number(params.get("b")) || undefined;

  const all = useAllInstances({ limit: 200 });
  const { a, b, diff, gridARef, gridBRef, syncScroll, scrollTo, isLoading, isError, error } =
    useCompare(aId, bId);

  const rows = all.data?.rows ?? [];
  const instA = rows.find((i) => i.id === aId);
  const instB = rows.find((i) => i.id === bId);

  const setPair = (side: "a" | "b", value: string) => {
    const next = new URLSearchParams(params.toString());
    next.set(side, value);
    router.replace(`/instances/compare?${next.toString()}`);
  };

  const days = Array.from({ length: 6 }, (_, i) => i);
  const slotCount = 8;

  if (!aId || !bId || !instA || !instB) {
    return (
      <div className="rounded-md border bg-surface p-10">
        <GitCompareArrows className="mx-auto h-10 w-10 text-muted-foreground" />
        <h2 className="mt-4 display text-center text-xl text-ink">Compare two instances</h2>
        <p className="mt-1 text-center text-sm text-muted-foreground">
          Pick an instance A and an instance B to see the differences.
        </p>
        <div className="mx-auto mt-6 grid max-w-md grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <p className="eyebrow">Instance A</p>
            <Select value={aId ? String(aId) : ""} onValueChange={(v) => setPair("a", v)}>
              <SelectTrigger><SelectValue placeholder="Select…" /></SelectTrigger>
              <SelectContent>
                {rows.map((i) => <SelectItem key={i.id} value={String(i.id)}>#{i.id} · {i.status}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <p className="eyebrow">Instance B</p>
            <Select value={bId ? String(bId) : ""} onValueChange={(v) => setPair("b", v)}>
              <SelectTrigger><SelectValue placeholder="Select…" /></SelectTrigger>
              <SelectContent>
                {rows.map((i) => <SelectItem key={i.id} value={String(i.id)}>#{i.id} · {i.status}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => router.push("/instances")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="display text-3xl text-ink">Compare instances</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Instance #{aId} vs instance #{bId}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Select value={aId ? String(aId) : ""} onValueChange={(v) => setPair("a", v)}>
            <SelectTrigger className="h-8 w-40"><SelectValue /></SelectTrigger>
            <SelectContent>
              {rows.map((i) => <SelectItem key={i.id} value={String(i.id)}>#{i.id} · {i.status}</SelectItem>)}
            </SelectContent>
          </Select>
          <MoveRight className="h-4 w-4 text-muted-foreground" />
          <Select value={bId ? String(bId) : ""} onValueChange={(v) => setPair("b", v)}>
            <SelectTrigger className="h-8 w-40"><SelectValue /></SelectTrigger>
            <SelectContent>
              {rows.map((i) => <SelectItem key={i.id} value={String(i.id)}>#{i.id} · {i.status}</SelectItem>)}
            </SelectContent>
          </Select>
          <Badge variant={instB?.status === "PUBLISHED" ? "success" : "neutral"}>{instB?.status}</Badge>
        </div>
      </div>

      {isError && <ErrorBanner message={error instanceof Error ? error.message : "Failed to load"} />}

      {/* Summary bar */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SummaryCard label="Soft score" value={instA && instB ? `${instA.soft_score?.toFixed(3) ?? "—"} → ${instB.soft_score?.toFixed(3) ?? "—"}` : "—"} />
        <SummaryCard label="Hard violations" value={instA && instB ? `${instA.hard_violations} → ${instB.hard_violations}` : "—"} />
        <SummaryCard label="Changed cells" value={String(diff.summary.changed)} />
        <SummaryCard label="Moved sessions" value={String(diff.summary.moved)} />
      </div>

      {/* Two synced grids */}
      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-80 w-full" />
          <Skeleton className="h-80 w-full" />
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          <div>
            <p className="eyebrow mb-2">Instance #{aId}</p>
            <div className="rounded-md border bg-surface p-4 shadow-sm">
              <TimetableGrid
                sessions={a.sessions}
                days={days}
                slotCount={slotCount}
                markers={diff.markersA}
                readOnly
                scrollRef={gridARef}
                onScroll={syncScroll(gridARef, gridBRef)}
              />
            </div>
          </div>
          <div>
            <p className="eyebrow mb-2">Instance #{bId}</p>
            <div className="rounded-md border bg-surface p-4 shadow-sm">
              <TimetableGrid
                sessions={b.sessions}
                days={days}
                slotCount={slotCount}
                markers={diff.markersB}
                readOnly
                scrollRef={gridBRef}
                onScroll={syncScroll(gridBRef, gridARef)}
              />
            </div>
          </div>
        </div>
      )}

      {/* Diff list */}
      <div className="rounded-md border bg-surface">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h2 className="display text-lg text-ink">Changes ({diff.entries.length})</h2>
          <p className="text-xs text-muted-foreground">
            {diff.summary.added} added · {diff.summary.removed} removed · {diff.summary.changed} changed · {diff.summary.moved} moved
          </p>
        </div>
        {diff.entries.length === 0 ? (
          <p className="p-6 text-sm text-muted-foreground">No differences — the two instances are identical.</p>
        ) : (
          <ul className="divide-y divide-border">
            {diff.entries.map((e, i) => (
              <li key={i}>
                <button
                  type="button"
                  onClick={() => scrollTo(e.day, e.slot)}
                  className="flex w-full items-start gap-3 px-4 py-2.5 text-left hover:bg-muted/50"
                >
                  <span className="mt-0.5 w-24 shrink-0 font-mono text-xs text-ink-soft">
                    {DAY_NAMES[e.day]} {slotTimeLabel(e.slot)}
                  </span>
                  <Badge variant={DIFF_TONE[e.type]}>{e.type}</Badge>
                  <span className="min-w-0 flex-1 text-sm text-ink-soft">
                    <CellLine session={e.type === "removed" ? e.a : e.b} />
                    {e.type === "changed" && e.a && e.b && (
                      <span className="block text-xs text-muted-foreground">
                        was {e.a.subjectCode ?? "—"} in {DAY_NAMES[e.a.day]} {slotTimeLabel(e.a.startSlot)}
                        {e.a.roomCode ? ` · ${e.a.roomCode}` : ""}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-surface p-4 shadow-sm">
      <p className="eyebrow">{label}</p>
      <p className="mt-1 text-sm font-medium text-ink">{value}</p>
    </div>
  );
}

function CellLine({ session }: { session?: { subjectCode?: string; subjectName?: string; facultyName?: string; roomCode?: string } }) {
  if (!session) return <span className="text-muted-foreground">empty</span>;
  return (
    <>
      <span className="font-medium text-ink">{session.subjectCode ?? "—"}</span>
      {session.subjectName && <span className="ml-1 text-muted-foreground">{session.subjectName}</span>}
      <span className="block text-xs text-muted-foreground">
        {session.facultyName ?? "—"}
        {session.roomCode ? ` · ${session.roomCode}` : ""}
      </span>
    </>
  );
}

export default function ComparePage() {
  return (
    <ProtectedShell>
      <Suspense fallback={<div className="p-8 text-sm text-muted-foreground">Loading compare…</div>}>
        <CompareInner />
      </Suspense>
    </ProtectedShell>
  );
}
