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
  /** Lab batch this session belongs to (parallel practicals), 1-based. */
  batchNumber?: number;
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
  /** If set, render an explicit full-width break/lunch row after this slot
   * (e.g. 4 = lunch after the 4th slot), so the 1h lunch is visible instead of
   * looking like a 2-hour gap in the times. */
  breakAfterSlot?: number;
  breakLabel?: string;
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
  breakAfterSlot,
  breakLabel = "LUNCH BREAK",
}: TimetableGridProps) {
  // index sessions by (day, startSlot); a cell may hold several parallel
  // batches (same time, distinct rooms) — keep them all.
  const byDaySlot = useMemo(() => {
    const map = new Map<string, GridSession[]>();
    for (const s of sessions) {
      const key = `${s.day}:${s.startSlot}`;
      const arr = map.get(key) ?? [];
      arr.push(s);
      map.set(key, arr);
    }
    return map;
  }, [sessions]);

  const rowHeight = density === "compact" ? 52 : 76;
  // A break row (1h) is inserted after breakAfterSlot; slots after it shift down.
  const breakSlot = breakAfterSlot ?? 0;
  const breakRow = breakSlot > 0 ? breakSlot + 1 : 0;
  const totalRows = breakRow ? slotCount + 1 : slotCount;
  const rowFor = (slot: number) => (breakRow && slot > breakSlot ? slot + 1 : slot);

  const cells: React.ReactNode[] = [];
  for (const day of days) {
    for (let slot = 1; slot <= slotCount; slot++) {
      const slotSessions = byDaySlot.get(`${day}:${slot}`) ?? [];
      // skip slots covered by a block that started earlier
      const coveredByEarlier = Array.from({ length: slot - 1 }, (_, k) => slot - 1 - k).some((s) => {
        const prev = byDaySlot.get(`${day}:${s}`);
        return prev?.some((p) => p.startSlot + p.duration - 1 >= slot);
      });
      if (coveredByEarlier) continue;

      const cellSessions = slotSessions.filter(
        (s) => s.startSlot + s.duration - 1 >= slot,
      );
      const marker = cellSessions.length ? markers?.[`${day}:${slot}`] : undefined;

      cells.push(
        <div
          key={`${day}:${slot}`}
          className="border-t border-l border-border first:border-l-0"
          style={{ gridColumn: day + 2, gridRow: rowFor(slot) + 1 }}
        >
          {cellSessions.length ? (
            <CellStack
              sessions={cellSessions}
              density={density}
              readOnly={readOnly}
              marker={marker}
              onClick={(s, e) => onCellClick?.(s, e)}
            />
          ) : null}
        </div>,
      );
    }
  }

  return (
    <div className="overflow-x-auto" ref={scrollRef} onScroll={onScroll}>
      <div
        className="grid min-w-[980px]"
        style={{
          gridTemplateColumns: `64px repeat(${days.length}, minmax(170px, 1fr))`,
          gridTemplateRows: `38px repeat(${totalRows}, ${rowHeight}px)`,
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
            style={{ gridColumn: 1, gridRow: rowFor(slot) + 1 }}
          >
            {slotTime(slot)}
          </div>
        ))}
        {/* break / lunch row */}
        {breakRow > 0 && (
          <div
            className="col-span-full flex items-center justify-center border-t border-border bg-muted/60 text-[11px] font-semibold uppercase tracking-[0.18em] text-ink-soft"
            style={{ gridColumn: `1 / span ${days.length + 1}`, gridRow: breakRow + 1 }}
          >
            {breakLabel}
          </div>
        )}
        {cells}
      </div>
    </div>
  );
}

function CellStack({ sessions, density, readOnly, marker, onClick }: {
  sessions: GridSession[];
  density: "comfortable" | "compact";
  readOnly: boolean;
  marker?: GridCellMarker;
  onClick: (s: GridSession, e: React.MouseEvent<HTMLButtonElement>) => void;
}) {
  // Parallel practicals stack several batches in one time window. A single
  // session renders full-height; multiple sessions share the cell vertically.
  if (sessions.length === 1) {
    return (
      <GridCell session={sessions[0]} density={density} readOnly={readOnly} marker={marker} onClick={(e) => onClick(sessions[0], e)} />
    );
  }
  // Several parallel batches share the window — let them scroll vertically so
  // every batch stays readable instead of squishing into overlapping text.
  const scrollable = sessions.length >= 3;
  return (
    <div className={cn(
      "flex h-full w-full flex-col gap-px overflow-hidden",
      scrollable && "overflow-y-auto",
    )}>
      {sessions.map((s) => (
        <GridCell
          key={s.key}
          session={s}
          density={density}
          readOnly={readOnly}
          marker={marker}
          compact
          onClick={(e) => onClick(s, e)}
        />
      ))}
    </div>
  );
}

function GridCell({ session, density, readOnly, marker, onClick, compact = false }: {
  session: GridSession;
  density: "comfortable" | "compact";
  readOnly: boolean;
  marker?: GridCellMarker;
  onClick: (e: React.MouseEvent<HTMLButtonElement>) => void;
  compact?: boolean;
}) {
  const color = chartColor(session.subjectId ?? 0);
  const isLab = session.sessionType === "LAB";
  const isOnline = !session.roomId && session.sessionType === "ACTIVITY";
  return (
    <button
      type="button"
      onClick={readOnly ? undefined : onClick}
      className={cn(
        "flex min-h-0 w-full flex-col justify-center gap-0.5 overflow-hidden rounded-r-sm border-l-[3px] bg-surface px-2 text-left",
        compact && "flex-[1]",
        !readOnly && "cursor-pointer transition-shadow hover:shadow-md",
        marker === "added" && "border-l-ink ring-2 ring-dashed ring-primary/70 ring-inset",
        marker === "removed" && "opacity-60 ring-2 ring-dashed ring-danger/70 ring-inset",
        marker === "changed" && "ring-2 ring-warning/80 ring-inset",
      )}
      style={{ borderLeftColor: color }}
    >
      <div className="flex items-center gap-1 font-mono text-xs font-semibold" style={{ color }}>
        {session.subjectCode ?? "—"}
        {session.batchNumber != null && <span className="rounded bg-ink/10 px-1">B{session.batchNumber}</span>}
        {isLab && <FlaskConical className="h-3 w-3" />}
        {isOnline && <span className="text-[10px] uppercase tracking-wide text-primary">online</span>}
      </div>
      {density === "comfortable" && !compact && session.subjectName && (
        <div className="truncate text-[13px] font-medium text-ink">{session.subjectName}</div>
      )}
      <div className="flex items-center gap-1 text-xs text-ink-soft">
        {session.facultyName && <span className="truncate">{session.facultyName}</span>}
        {session.roomCode && <span className="shrink-0 font-mono text-muted-foreground">{session.roomCode}</span>}
      </div>
      {session.groupName && density === "comfortable" && !compact && (
        <div className="truncate text-[11px] text-muted-foreground">{session.groupName}</div>
      )}
    </button>
  );
}
