"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Loader2, CheckCircle2, AlertTriangle, Save } from "lucide-react";
import { apiPost } from "@/lib/api";
import { useRooms, useFaculty, useSlotOverride } from "@/hooks/use-resources";
import type { GridSession } from "./TimetableGrid";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export interface SlotPopoverProps {
  instanceId: number;
  session: GridSession;
  /** 0-indexed days the grid shows. */
  days: number[];
  slotCount: number;
  slotTime?: (slot: number) => string;
  onSaved: () => void;
}

/**
 * Edit drawer content for one slot. Lets the admin move a session to another
 * day/slot/room/faculty, dry-runs the constraint checker (debounced), and only
 * enables Save once the move is clean.
 */
export function SlotEditor({
  instanceId,
  session,
  days,
  slotCount,
  slotTime = (s) => `${String(8 + Math.floor((s - 1) / 2)).padStart(2, "0")}:${(s - 1) % 2 ? "30" : "00"}`,
  onSaved,
}: SlotPopoverProps) {
  const roomsQ = useRooms({ limit: 200 });
  const facultyQ = useFaculty({ limit: 200 });

  const [day, setDay] = useState(session.day);
  const [slot, setSlot] = useState(session.startSlot);
  const [roomId, setRoomId] = useState<string>("");
  const [facultyId, setFacultyId] = useState<string>("");
  const [reason, setReason] = useState("");
  const [violations, setViolations] = useState<string[] | null>(null);
  const [checking, setChecking] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const override = useSlotOverride(instanceId);

  // The proposed state. Day/slot/room/faculty; subject/group stay fixed.
  const proposed = useMemo(
    () => ({
      day_of_week: day,
      slot_number: slot,
      room_id: roomId ? Number(roomId) : undefined,
      faculty_id: facultyId ? Number(facultyId) : undefined,
    }),
    [day, slot, roomId, facultyId],
  );

  const isDirty =
    day !== session.day ||
    slot !== session.startSlot ||
    (roomId !== "" && Number(roomId) !== session.roomId) ||
    (facultyId !== "" && Number(facultyId) !== session.facultyId);

  // Debounced dry-run of the checker against the current proposed state.
  useEffect(() => {
    if (!isDirty) {
      setViolations(null);
      return;
    }
    setChecking(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        const res = await apiPost<{ violations: string[] }>(
          `/api/v1/instances/${instanceId}/slots/${session.slotId}/revalidate`,
          proposed,
        );
        setViolations(res.violations ?? []);
      } catch (e) {
        setViolations([e instanceof Error ? e.message : "Revalidation failed"]);
      } finally {
        setChecking(false);
      }
    }, 450);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [proposed, isDirty, instanceId, session.slotId]);

  async function save() {
    try {
      await override.mutateAsync({
        slotId: session.slotId,
        payload: {
          day_of_week: day,
          slot_number: slot,
          ...(roomId ? { room_id: Number(roomId) } : {}),
          ...(facultyId ? { faculty_id: Number(facultyId) } : {}),
          override_reason: reason || "Manual override",
        },
      });
      toast.success("Slot updated");
      onSaved();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed");
      // Surface any checker violations from the 409 detail if present.
      const detail = (e as { detail?: { violations?: string[] } })?.detail;
      if (detail?.violations) setViolations(detail.violations);
    }
  }

  const clean = violations != null && violations.length === 0;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="font-mono text-xs font-semibold text-primary">{session.subjectCode ?? "—"}</p>
        {session.subjectName && <p className="text-sm font-medium text-ink">{session.subjectName}</p>}
        <p className="text-xs text-muted-foreground">
          {session.groupName ?? "—"} · {session.facultyName ?? "—"}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5">
          <Label>Day</Label>
          <Select value={String(day)} onValueChange={(v) => setDay(Number(v))}>
            <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
            <SelectContent>
              {days.map((d) => (
                <SelectItem key={d} value={String(d)}>{DAY_NAMES[d] ?? `Day ${d}`}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Slot</Label>
          <Select value={String(slot)} onValueChange={(v) => setSlot(Number(v))}>
            <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
            <SelectContent>
              {Array.from({ length: slotCount }, (_, k) => k + 1).map((s) => (
                <SelectItem key={s} value={String(s)}>{s} · {slotTime(s)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Room</Label>
          <Select value={roomId} onValueChange={setRoomId}>
            <SelectTrigger className="h-8"><SelectValue placeholder={session.roomCode ?? "Unchanged"} /></SelectTrigger>
            <SelectContent>
              {roomsQ.data?.rows.map((r) => (
                <SelectItem key={r.id} value={String(r.id)}>{r.room_code} · {r.capacity}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Faculty</Label>
          <Select value={facultyId} onValueChange={setFacultyId}>
            <SelectTrigger className="h-8"><SelectValue placeholder={session.facultyName ?? "Unchanged"} /></SelectTrigger>
            <SelectContent>
              {facultyQ.data?.rows.map((f) => (
                <SelectItem key={f.id} value={String(f.id)}>{f.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="reason">Reason</Label>
        <Input id="reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. swapped with teacher B" />
      </div>

      {/* Revalidate status */}
      <div className="flex min-h-8 items-center gap-2 text-sm">
        {checking ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            <span className="text-muted-foreground">Checking conflicts…</span>
          </>
        ) : violations === null ? (
          <span className="text-muted-foreground">No changes yet.</span>
        ) : clean ? (
          <>
            <CheckCircle2 className="h-4 w-4 text-success" />
            <span className="text-success">No conflicts</span>
          </>
        ) : (
          <>
            <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" />
            <span className="text-destructive">
              {violations.length} conflict{violations.length === 1 ? "" : "s"}:
            </span>
          </>
        )}
      </div>
      {!checking && violations && violations.length > 0 && (
        <ul className="max-h-24 space-y-1 overflow-y-auto rounded-md bg-destructive/5 p-2 text-xs text-destructive">
          {violations.map((v, i) => <li key={i}>· {v}</li>)}
        </ul>
      )}

      <Button onClick={save} disabled={!isDirty || !clean || override.isPending} className="w-full">
        {override.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
        {override.isPending ? "Saving…" : "Save override"}
      </Button>
    </div>
  );
}
