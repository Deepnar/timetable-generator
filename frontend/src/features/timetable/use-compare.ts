"use client";

import { useMemo, useRef } from "react";
import type { RefObject } from "react";
import { useGridSessions } from "./use-grid-sessions";
import type { GridSession, GridCellMarker } from "./TimetableGrid";

/** One differing cell in the compare view. */
export interface DiffEntry {
  day: number;
  slot: number;
  type: "added" | "removed" | "changed";
  a?: GridSession;
  b?: GridSession;
}

const cellKey = (s: GridSession) => `${s.day}:${s.startSlot}`;

/** Session identity ignores position/room so moves can be recognised. */
const identity = (s: GridSession) =>
  `${s.subjectId}|${s.facultyName ?? ""}|${s.groupName ?? ""}`;

export function useCompare(aId: number | undefined, bId: number | undefined) {
  const a = useGridSessions(aId);
  const b = useGridSessions(bId);

  const gridARef = useRef<HTMLDivElement | null>(null);
  const gridBRef = useRef<HTMLDivElement | null>(null);
  const syncing = useRef(false);

  /** Mirror horizontal/vertical scroll between the two grids. */
  function syncScroll(from: RefObject<HTMLDivElement | null>, to: RefObject<HTMLDivElement | null>) {
    return () => {
      if (syncing.current || !from.current || !to.current) return;
      syncing.current = true;
      to.current.scrollLeft = from.current.scrollLeft;
      to.current.scrollTop = from.current.scrollTop;
      syncing.current = false;
    };
  }

  /** Bring the given day/slot column into view in both grids. */
  function scrollTo(day: number, slot: number) {
    const from = gridARef.current;
    if (!from) return;
    const header = from.querySelector(`[data-day="${day}"]`);
    const gutter = from.querySelector(`[data-slot="${slot}"]`);
    let left = 0;
    let top = 0;
    if (header && from) {
      const hr = header.getBoundingClientRect();
      const cr = from.getBoundingClientRect();
      left = from.scrollLeft + (hr.left - cr.left);
    }
    if (gutter && from) {
      const gr = gutter.getBoundingClientRect();
      const cr = from.getBoundingClientRect();
      top = from.scrollTop + (gr.top - cr.top);
    }
    for (const ref of [gridARef, gridBRef]) {
      if (ref.current) {
        ref.current.scrollTo({ left, top, behavior: "smooth" });
      }
    }
  }

  const diff = useMemo(() => {
    const aSessions = a.sessions;
    const bSessions = b.sessions;
    const aMap = new Map(aSessions.map((s) => [cellKey(s), s]));
    const bMap = new Map(bSessions.map((s) => [cellKey(s), s]));
    const keys = new Set([...aMap.keys(), ...bMap.keys()]);

    const entries: DiffEntry[] = [];
    const markersA: Record<string, GridCellMarker> = {};
    const markersB: Record<string, GridCellMarker> = {};
    let added = 0;
    let removed = 0;
    let changed = 0;

    for (const key of keys) {
      const a = aMap.get(key);
      const b = bMap.get(key);
      if (a && b) {
        if (identity(a) !== identity(b) || a.roomCode !== b.roomCode) {
          changed += 1;
          markersA[key] = "changed";
          markersB[key] = "changed";
          entries.push({ day: a.day, slot: a.startSlot, type: "changed", a, b });
        }
      } else if (b) {
        added += 1;
        markersB[key] = "added";
        entries.push({ day: b.day, slot: b.startSlot, type: "added", b });
      } else if (a) {
        removed += 1;
        markersA[key] = "removed";
        entries.push({ day: a.day, slot: a.startSlot, type: "removed", a });
      }
    }

    // Moved sessions: the same identity sitting at a different position in B.
    const bByIdentity = new Map(bSessions.map((s) => [identity(s), s]));
    let moved = 0;
    for (const s of aSessions) {
      const other = bByIdentity.get(identity(s));
      if (other && cellKey(s) !== cellKey(other)) moved += 1;
    }

    entries.sort((x, y) => x.day - y.day || x.slot - y.slot);

    return {
      entries,
      markersA,
      markersB,
      summary: { added, removed, changed, moved },
    };
  }, [a.sessions, b.sessions]);

  const isLoading = a.isLoading || b.isLoading;
  const isError = a.isError || b.isError;
  const error = a.error ?? b.error;

  return {
    a,
    b,
    diff,
    gridARef,
    gridBRef,
    syncScroll,
    scrollTo,
    isLoading,
    isError,
    error,
  };
}
