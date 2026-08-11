"use client";

import { useMemo } from "react";import { FlaskConical } from "lucide-react";
import { cn } from "@/lib/utils";
import { chartColor } from "@/lib/chart-colors";

/** One placed session. */
export interface GridSession {
  key: string;
  slotId: number;
  subjectId: number | null;
  facultyId?: number;
  roomId?: number;
  groupId?: number;
  subjectCode?: string;
  subjectName?: string;
  facultyName?: string;
  roomCode?: string;
  groupName?: string;
  day: number; // 0..6
  startSlot: number; // 1-based
  duration: number; // block_length
  sessionType?: string;
  warnings?: string[];
  isManualOverride?: boolean;
}

/** Per-cell diff marker used by compare mode. Keyed by `${day}:${startSlot}`. */
export type GridCellMarker = "added" | "removed" | "changed";

export interface TimetableGridProps {
  sessions: GridSession[];
  /** 0-indexed days actually used, e.g. [0,1,2,3,4]. */
  days: number[];
  dayLabels?: (day: number) => string;
  slotCount: number;
  /** Time label for a slot, e.g. "09:00". */
  slotTime?: (slot: number) => string;
  density?: "comfortable" | "compact";
  readOnly?: boolean;
  onCellClick?: (session: GridSession, event: React.MouseEvent<HTMLButtonElement>) => void;
  /** Forward the scroll container so compare can sync two grids. */
  scrollRef?: React.Ref<HTMLDivElement>;
  /** Diff markers keyed by `${day}:${startSlot}`. */
  markers?: Record<string, GridCellMarker>;
  /** Scroll listener forwarded to the container (compare scroll sync). */
  onScroll?: (e: React.UIEvent<HTMLDivElement>) => void;
}

const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export function TimetableGrid({
  sessions,
  days,
  slotCount,
  dayLabels = (d) => DAY_NAMES[d] ?? `Day ${d}`,
  slotTime = (s) => `${String(8 + Math.floor((s - 1) / 2)).padStart(2, "0")}:${(s - 1) % 2 ? "30" : "00"}`,
  density = "comfortable",
  readOnly = false,
  onCellClick,
  scrollRef,
  markers,
  onScroll,
}: TimetableGridProps) {
  // index sessions by (day, startSlot) for O(1) lookup; skip spans of blocks
  const byDaySlot = useMemo(() => {
    const map = new Map<string, GridSession>();
    for (const s of sessions) {
      // only index the START slot; the span covers the rest
      map.set(`${s.day}:${s.startSlot}`, s);
    }
    return map;
  }, [sessions]);

  const rowHeight = density === "compact" ? 44 : 64;

  const cells: React.ReactNode[] = [];
  for (const day of days) {
    for (let slot = 1; slot <= slotCount; slot++) {
      const session = byDaySlot.get(`${day}:${slot}`);
      // skip slots covered by a block that started earlier
      const coveredByEarlier = Array.from({ length: slot - 1 }, (_, k) => slot - 1 - k).some((s) => {
        const prev = byDaySlot.get(`${day}:${s}`);
        return prev && prev.startSlot + prev.duration - 1 >= slot;
      });
      if (coveredByEarlier) continue;

      const marker = session ? markers?.[`${day}:${slot}`] : undefined;

      cells.push(
        <div
          key={`${day}:${slot}`}
          className="border-t border-l border-border first:border-l-0"
          style={{ gridColumn: day + 2, gridRow: slot + 1 }}
        >
          {session ? (
            <GridCell session={session} density={density} readOnly={readOnly} marker={marker} onClick={(e) => onCellClick?.(session, e)} />
          ) : null}
        </div>,
      );
    }
  }

  return (
    <div className="overflow-x-auto" ref={scrollRef} onScroll={onScroll}>
      <div
        className="grid min-w-[820px]"
        style={{
          gridTemplateColumns: `56px repeat(${days.length}, minmax(150px, 1fr))`,
          gridTemplateRows: `36px repeat(${slotCount}, ${rowHeight}px)`,
        }}
      >
        {/* corner */}
        <div className="sticky left-0 z-20 bg-muted" style={{ gridColumn: 1, gridRow: 1 }} />
        {/* day headers */}
        {days.map((day, i) => (
          <div
            key={day}
            data-day={day}
            className="sticky top-0 z-10 flex items-center justify-center bg-muted px-2 text-xs font-medium uppercase tracking-wide text-ink-soft"
            style={{ gridColumn: i + 2, gridRow: 1 }}
          >
            {dayLabels(day)}
          </div>
        ))}
        {/* slot gutter */}
        {Array.from({ length: slotCount }, (_, k) => k + 1).map((slot) => (
          <div
            key={slot}
            data-slot={slot}
            className="sticky left-0 z-10 flex items-start justify-end bg-muted pr-2 font-mono text-[11px] text-ink-faint"
            style={{ gridColumn: 1, gridRow: slot + 1 }}
          >
            {slotTime(slot)}
          </div>
        ))}
        {cells}
      </div>
    </div>
  );
}

function GridCell({ session, density, readOnly, marker, onClick }: {
  session: GridSession;
  density: "comfortable" | "compact";
  readOnly: boolean;
  marker?: GridCellMarker;
  onClick: (e: React.MouseEvent<HTMLButtonElement>) => void;
}) {
  const color = chartColor(session.subjectId ?? 0);
  const isLab = session.sessionType === "LAB";
  return (
    <button
      type="button"
      onClick={readOnly ? undefined : onClick}
      className={cn(
        "flex h-full w-full flex-col justify-center gap-0.5 overflow-hidden rounded-r-sm border-l-[3px] bg-surface px-2 text-left",
        !readOnly && "cursor-pointer transition-shadow hover:shadow-md",
        marker === "added" && "border-l-ink ring-2 ring-dashed ring-primary/70 ring-inset",
        marker === "removed" && "opacity-60 ring-2 ring-dashed ring-danger/70 ring-inset",
        marker === "changed" && "ring-2 ring-warning/80 ring-inset",
      )}
      style={{ borderLeftColor: color }}
    >
      <div className="flex items-center gap-1 font-mono text-xs font-semibold" style={{ color }}>
        {session.subjectCode ?? "—"}
        {isLab && <FlaskConical className="h-3 w-3" />}
      </div>
      {density === "comfortable" && session.subjectName && (
        <div className="truncate text-[13px] font-medium text-ink">{session.subjectName}</div>
      )}
      <div className="flex items-center gap-1 text-xs text-ink-soft">
        {session.facultyName && <span className="truncate">{session.facultyName}</span>}
        {session.roomCode && <span className="shrink-0 font-mono text-muted-foreground">{session.roomCode}</span>}
      </div>
      {session.groupName && density === "comfortable" && (
        <div className="truncate text-[11px] text-muted-foreground">{session.groupName}</div>
      )}
    </button>
  );
}
