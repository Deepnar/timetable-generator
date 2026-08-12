"use client";

import { useMemo } from "react";
import { Download, CalendarCheck2, LogOut } from "lucide-react";
import { toast } from "sonner";
import { useQuery } from "@tanstack/react-query";
import { apiGet, getToken } from "@/lib/api";
import type { MyScheduleResponse, MyTodayResponse } from "@/lib/types";
import { useAuth } from "@/lib/auth";
import { TimetableGrid, type GridSession } from "@/features/timetable/TimetableGrid";
import { ProtectedShell } from "@/components/ProtectedShell";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorBanner } from "@/components/ui/error-banner";
import { EmptyState } from "@/components/ui/empty-state";
import { CalendarDays } from "lucide-react";

const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export default function MySchedulePage() {
  const { me, logout } = useAuth();

  const schedule = useQuery({
    queryKey: ["my", "schedule"],
    queryFn: () => apiGet<MyScheduleResponse>("/api/v1/my/schedule"),
  });
  const today = useQuery({
    queryKey: ["my", "today"],
    queryFn: () => apiGet<MyTodayResponse>("/api/v1/my/today"),
  });

  const days = Array.from({ length: 6 }, (_, i) => i);
  const slotCount = 8;

  const sessions = useMemo<GridSession[]>(
    () =>
      (schedule.data?.slots ?? []).map((s) => ({
        key: `${s.id}`,
        slotId: s.id,
        subjectId: null,
        subjectCode: s.subject_code ?? "—",
        subjectName: s.subject_name ?? undefined,
        roomCode: s.room_code ?? undefined,
        groupName: s.group_name ?? undefined,
        day: s.day_of_week ?? 0,
        startSlot: s.slot_number,
        duration: 1,
        sessionType: s.session_type,
        isManualOverride: s.is_manual_override,
      })),
    [schedule.data],
  );

  async function download(ext: string) {
    try {
      const token = getToken();
      const res = await fetch(`http://localhost:8000/api/v1/my/export/${ext}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(res.statusText);
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `my-schedule.${ext === "ical" ? "ics" : ext}`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Download started");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    }
  }

  const todaySlots = today.data?.slots ?? [];
  const todayDay = today.data?.day_of_week ?? 0;

  return (
    <ProtectedShell>
      <div className="flex flex-col gap-5">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="display text-3xl text-ink">My schedule</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {me?.name} · {schedule.data?.faculty?.department ?? "Teacher"} · published timetable
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => download("ical")}>
              <Download className="mr-1 h-4 w-4" /> iCal
            </Button>
            <Button variant="outline" onClick={() => download("pdf")}>
              <Download className="mr-1 h-4 w-4" /> PDF
            </Button>
            <Button variant="ghost" onClick={logout}>
              <LogOut className="mr-1 h-4 w-4" /> Sign out
            </Button>
          </div>
        </div>

        {(schedule.isError || today.isError) && (
          <ErrorBanner message="Failed to load your schedule" onRetry={() => { schedule.refetch(); today.refetch(); }} />
        )}

        {/* Today card */}
        <div className="rounded-md border bg-surface p-5 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="display text-lg text-ink">Today — {DAY_NAMES[todayDay] ?? "Unknown"}</h2>
            <CalendarCheck2 className="h-5 w-5 text-muted-foreground" />
          </div>
          {today.isLoading ? (
            <Skeleton className="h-16" />
          ) : todaySlots.length === 0 ? (
            <p className="text-sm text-muted-foreground">No classes today. Enjoy the free day!</p>
          ) : (
            <ul className="divide-y divide-border">
              {todaySlots.map((s) => (
                <li key={s.id} className="flex items-center justify-between py-2">
                  <div>
                    <p className="font-mono text-sm font-medium text-ink">{s.subject_code}</p>
                    <p className="text-xs text-muted-foreground">{s.subject_name}</p>
                  </div>
                  <div className="text-right text-sm text-ink-soft">
                    <p>{s.start_time}–{s.end_time}</p>
                    <p className="text-xs text-muted-foreground">
                      {s.group_name}{s.room_code ? ` · ${s.room_code}` : ""}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Weekly grid */}
        <div className="rounded-md border bg-surface p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="display text-lg text-ink">Weekly schedule</h2>
            <Badge variant="neutral">{sessions.length} sessions</Badge>
          </div>
          {schedule.isLoading ? (
            <div className="space-y-2">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-12" />)}</div>
          ) : schedule.data?.faculty == null ? (
            <EmptyState
              icon={CalendarDays}
              title="No timetable linked to your account"
              body="Your login email doesn't match a faculty record yet. Contact the admin to link it."
            />
          ) : sessions.length === 0 ? (
            <EmptyState
              icon={CalendarDays}
              title="Nothing published yet"
              body="The admin hasn't published a timetable for you. Check back after publishing."
            />
          ) : (
            <TimetableGrid sessions={sessions} days={days} slotCount={slotCount} readOnly />
          )}
        </div>
      </div>
    </ProtectedShell>
  );
}
