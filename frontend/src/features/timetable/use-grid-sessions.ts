"use client";

import { useMemo } from "react";
import { useInstanceSlots, useSubjects, useFaculty, useRooms, useGroups } from "@/hooks/use-resources";
import type { GridSession } from "./TimetableGrid";

/**
 * Maps a flat instance's Slot[] into grid sessions for the TimetableGrid,
 * joining subject/faculty/room/group lookups. Blocks (duration > 1) stay one
 * session that spans rows.
 */
export function useGridSessions(instanceId: number | undefined) {
  const slotsQ = useInstanceSlots(instanceId);
  const subjectsQ = useSubjects({ limit: 200 });
  const facultyQ = useFaculty({ limit: 200 });
  const roomsQ = useRooms({ limit: 200 });
  const groupsQ = useGroups({ limit: 200 });

  const sessions = useMemo<GridSession[]>(() => {
    const slots = slotsQ.data ?? [];
    const subjects = new Map(subjectsQ.data?.rows.map((s) => [s.id, s]) ?? []);
    const faculty = new Map(facultyQ.data?.rows.map((f) => [f.id, f]) ?? []);
    const rooms = new Map(roomsQ.data?.rows.map((r) => [r.id, r]) ?? []);
    const groups = new Map(groupsQ.data?.rows.map((g) => [g.id, g]) ?? []);

    return slots.map((sl) => {
      const subject = sl.subject_id != null ? subjects.get(sl.subject_id) : undefined;
      const fac = sl.faculty_id != null ? faculty.get(sl.faculty_id) : undefined;
      const room = sl.room_id != null ? rooms.get(sl.room_id) : undefined;
      const group = sl.student_group_id != null ? groups.get(sl.student_group_id) : undefined;
      return {
        key: `${sl.id}`,
        slotId: sl.id,
        subjectId: sl.subject_id,
        facultyId: sl.faculty_id ?? undefined,
        roomId: sl.room_id ?? undefined,
        groupId: sl.student_group_id ?? undefined,
        subjectCode: subject?.subject_code,
        subjectName: subject?.name,
        facultyName: fac?.name,
        roomCode: room?.room_code,
        groupName: group?.name,
        day: sl.day_of_week ?? 0,
        startSlot: sl.slot_number ?? 1,
        duration: 1, // contiguous blocks are stored per-slot; see grouping below
        sessionType: sl.session_type,
        isManualOverride: sl.is_manual_override,
      };
    });
  }, [slotsQ.data, subjectsQ.data, facultyQ.data, roomsQ.data, groupsQ.data]);

  // Merge consecutive same-session slots into blocks (labs spanning 2-3 slots).
  const grouped = useMemo<GridSession[]>(() => {
    const sorted = [...sessions].sort((a, b) => (a.day - b.day) || (a.startSlot - b.startSlot));
    const out: GridSession[] = [];
    let prev: GridSession | null = null;
    for (const s of sorted) {
      if (
        prev &&
        prev.day === s.day &&
        prev.startSlot + prev.duration === s.startSlot &&
        prev.subjectId === s.subjectId &&
        prev.facultyName === s.facultyName &&
        prev.roomCode === s.roomCode
      ) {
        prev.duration += 1;
      } else {
        prev = { ...s };
        out.push(prev);
      }
    }
    return out;
  }, [sessions]);

  return {
    sessions: grouped,
    isLoading: slotsQ.isLoading,
    isError: slotsQ.isError,
    error: slotsQ.error,
    refetch: slotsQ.refetch,
    totalSlots: slotsQ.data?.length ?? 0,
  };
}
