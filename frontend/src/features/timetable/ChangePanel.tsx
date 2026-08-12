"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Settings2, UserCheck, DoorOpen, ArrowLeftRight, CalendarClock,
  Loader2, Save, Undo2, Users,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { apiPost, apiDelete } from "@/lib/api";
import { useOverrides, useAvailableFaculty, useRooms } from "@/hooks/use-resources";
import type { GridSession } from "./TimetableGrid";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

const TYPE_LABELS: Record<string, string> = {
  TEACHER_COVER: "Teacher cover",
  ROOM_CHANGE: "Room change",
  SWAP: "Swap lectures",
  TEMP: "Temporary window",
  CUSTOM: "Custom",
};

const TYPE_TONE: Record<string, "info" | "warning" | "success" | "danger" | "neutral"> = {
  TEACHER_COVER: "info",
  ROOM_CHANGE: "warning",
  SWAP: "success",
  TEMP: "danger",
  CUSTOM: "neutral",
};

export interface ChangeCellState {
  session: GridSession;
  x: number;
  y: number;
}

/** Change-mode editor anchored to a clicked cell on a PUBLISHED timetable. */
export function ChangeEditor({
  instanceId,
  cell,
  sessions,
  onDone,
}: {
  instanceId: number;
  cell: ChangeCellState;
  sessions: GridSession[];
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const session = cell.session;

  const [type, setType] = useState("TEACHER_COVER");
  const [newFacultyId, setNewFacultyId] = useState("");
  const [newRoomId, setNewRoomId] = useState("");
  const [swapWith, setSwapWith] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  const roomsQ = useRooms({ limit: 1000 });

  const candidates = useAvailableFaculty(
    instanceId,
    type === "TEACHER_COVER"
      ? { day_of_week: session.day, slot_number: session.startSlot, exclude_slot_id: session.slotId }
      : null,
  );

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["instance", instanceId, "overrides"] });
    qc.invalidateQueries({ queryKey: ["instance", instanceId, "available-faculty"] });
  };

  async function save() {
    setSaving(true);
    try {
      const body: Record<string, unknown> = {
        slot_id: session.slotId,
        override_type: type,
        reason: reason || null,
      };
      if (type === "TEACHER_COVER") {
        if (!newFacultyId) { toast.error("Pick a covering teacher"); setSaving(false); return; }
        body.new_faculty_id = Number(newFacultyId);
      } else if (type === "ROOM_CHANGE") {
        if (!newRoomId) { toast.error("Pick a room"); setSaving(false); return; }
        body.new_room_id = Number(newRoomId);
      } else if (type === "SWAP") {
        if (!swapWith) { toast.error("Pick the lecture to swap with"); setSaving(false); return; }
        body.swap_with_slot_id = Number(swapWith);
      } else if (type === "TEMP") {
        if (dateFrom) body.date_from = dateFrom;
        if (dateTo) body.date_to = dateTo;
        if (!newFacultyId && !newRoomId && !dateFrom) {
          toast.error("Give the temporary change a teacher, room, or date window");
          setSaving(false); return;
        }
        if (newFacultyId) body.new_faculty_id = Number(newFacultyId);
        if (newRoomId) body.new_room_id = Number(newRoomId);
      }

      await apiPost(`/api/v1/instances/${instanceId}/overrides`, body);
      toast.success("Change applied");
      invalidate();
      onDone();
    } catch (e) {
      const detail = (e as { detail?: { message?: string; violations?: string[] } })?.detail;
      if (detail?.violations?.length) {
        toast.error(detail.violations[0]);
      } else {
        toast.error(e instanceof Error ? e.message : "Change failed");
      }
    } finally {
      setSaving(false);
    }
  }

  const candidateNames = useMemo(() => new Map((candidates.data ?? []).map((c) => [c.id, c])), [candidates.data]);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="font-mono text-xs font-semibold text-primary">{session.subjectCode ?? "—"}</p>
        <p className="text-sm font-medium text-ink">{session.subjectName ?? "—"}</p>
        <p className="text-xs text-muted-foreground">
          {DAY_NAMES[session.day] ?? `Day ${session.day}`} · slot {session.startSlot}
          {session.roomCode ? ` · ${session.roomCode}` : ""}
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label>Change type</Label>
        <Select value={type} onValueChange={setType}>
          <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
          <SelectContent>
            {Object.entries(TYPE_LABELS).map(([v, l]) => (
              <SelectItem key={v} value={v}>{l}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {type === "TEACHER_COVER" && (
        <div className="flex flex-col gap-1.5">
          <Label>Covering teacher</Label>
          <Select value={newFacultyId} onValueChange={setNewFacultyId}>
            <SelectTrigger className="h-8"><SelectValue placeholder="Available teachers…" /></SelectTrigger>
            <SelectContent>
              {candidates.data?.length === 0 && <div className="px-2 py-1 text-xs text-muted-foreground">No teachers free at this time.</div>}
              {(candidates.data ?? []).map((f) => (
                <SelectItem key={f.id} value={String(f.id)}>{f.name} · {f.department}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="flex items-center gap-1 text-xs text-muted-foreground">
            <Users className="h-3 w-3" /> Only teachers free at this day/slot are listed.
          </p>
        </div>
      )}

      {type === "ROOM_CHANGE" && (
        <div className="flex flex-col gap-1.5">
          <Label>New room</Label>
          <Select value={newRoomId} onValueChange={setNewRoomId}>
            <SelectTrigger className="h-8"><SelectValue placeholder="Pick a room…" /></SelectTrigger>
            <SelectContent>
              {(roomsQ.data?.rows ?? []).map((r) => (
                <SelectItem key={r.id} value={String(r.id)}>{r.room_code} · {r.room_type} · {r.capacity}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {type === "SWAP" && (
        <div className="flex flex-col gap-1.5">
          <Label>Swap with slot</Label>
          <Select value={swapWith} onValueChange={setSwapWith}>
            <SelectTrigger className="h-8"><SelectValue placeholder="Pick another lecture…" /></SelectTrigger>
            <SelectContent>
              {sessions
                .filter((s) => s.slotId !== session.slotId)
                .map((s) => (
                  <SelectItem key={s.slotId} value={String(s.slotId)}>
                    {DAY_NAMES[s.day] ?? `Day ${s.day}`} slot {s.startSlot} · {s.subjectCode ?? "—"}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">Validation checks both resulting positions before saving.</p>
        </div>
      )}

      {type === "TEMP" && (
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="df">From</Label>
            <Input id="df" type="date" className="h-8" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dt">To</Label>
            <Input id="dt" type="date" className="h-8" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <div className="col-span-2 flex flex-col gap-1.5">
            <Label>Temporary teacher (optional)</Label>
            <Select value={newFacultyId} onValueChange={setNewFacultyId}>
              <SelectTrigger className="h-8"><SelectValue placeholder="Available teachers…" /></SelectTrigger>
              <SelectContent>
                {(candidates.data ?? []).map((f) => (
                  <SelectItem key={f.id} value={String(f.id)}>{f.name} · {f.department}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="col-span-2 flex flex-col gap-1.5">
            <Label>Temporary room (optional)</Label>
            <Select value={newRoomId} onValueChange={setNewRoomId}>
              <SelectTrigger className="h-8"><SelectValue placeholder="Pick a room…" /></SelectTrigger>
              <SelectContent>
                {(roomsQ.data?.rows ?? []).map((r) => (
                  <SelectItem key={r.id} value={String(r.id)}>{r.room_code} · {r.room_type}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="reason">Reason</Label>
        <Input id="reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. teacher resigned mid-year" />
      </div>

      <Button onClick={save} disabled={saving} className="w-full">
        {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
        {saving ? "Applying…" : "Apply change"}
      </Button>
    </div>
  );
}

/** The change list for an instance (active changes with revert). */
export function ChangeList({ instanceId }: { instanceId: number }) {
  const qc = useQueryClient();
  const overrides = useOverrides(instanceId, false);
  const [reverting, setReverting] = useState<number | null>(null);

  async function revert(id: number) {
    setReverting(id);
    try {
      await apiDelete(`/api/v1/instances/${instanceId}/overrides/${id}`);
      toast.success("Change reverted");
      qc.invalidateQueries({ queryKey: ["instance", instanceId, "overrides"] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Revert failed");
    } finally {
      setReverting(null);
    }
  }

  const rows = overrides.data ?? [];
  if (rows.length === 0) {
    return (
      <div className="flex flex-col items-center gap-1 py-6 text-center">
        <Settings2 className="h-8 w-8 text-muted-foreground" />
        <p className="text-sm font-medium text-ink">No changes yet</p>
        <p className="text-xs text-muted-foreground">Click a cell in change mode to record a mid-year change.</p>
      </div>
    );
  }

  return (
    <ul className="divide-y divide-border">
      {rows.map((o) => (
        <li key={o.id} className="py-2.5">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Badge variant={TYPE_TONE[o.override_type] ?? "neutral"}>{TYPE_LABELS[o.override_type] ?? o.override_type}</Badge>
                {o.date_from && (
                  <span className="text-xs text-muted-foreground">
                    {o.date_from}{o.date_to ? ` → ${o.date_to}` : " → ongoing"}
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm text-ink">
                {o.override_type === "TEACHER_COVER" && (
                  <><UserCheck className="mr-1 inline h-3.5 w-3.5 text-muted-foreground" />{o.old_faculty_name ?? "—"} → {o.new_faculty_name ?? "—"}</>
                )}
                {o.override_type === "ROOM_CHANGE" && (
                  <><DoorOpen className="mr-1 inline h-3.5 w-3.5 text-muted-foreground" />{o.old_room_code ?? "—"} → {o.new_room_code ?? "—"}</>
                )}
                {o.override_type === "SWAP" && (
                  <><ArrowLeftRight className="mr-1 inline h-3.5 w-3.5 text-muted-foreground" />swapped with {DAY_NAMES[o.slot_day ?? 0]} slot {o.slot_number}</>
                )}
                {o.override_type === "TEMP" && (
                  <><CalendarClock className="mr-1 inline h-3.5 w-3.5 text-muted-foreground" />{o.new_faculty_name ?? o.new_room_code ?? "temporary change"}</>
                )}
              </p>
              {o.subject_code && (
                <p className="text-xs text-muted-foreground">{o.subject_code} · {o.subject_name}</p>
              )}
              {o.reason && <p className="mt-0.5 text-xs text-ink-soft">“{o.reason}”</p>}
            </div>
            <Button variant="ghost" size="sm" className="shrink-0 text-muted-foreground" disabled={reverting === o.id} onClick={() => revert(o.id)}>
              {reverting === o.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Undo2 className="h-3.5 w-3.5" />}
              Revert
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}
