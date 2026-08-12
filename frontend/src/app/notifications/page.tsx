"use client";

import { Bell, CheckCheck } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { apiPost } from "@/lib/api";
import { useNotifications } from "@/hooks/use-resources";
import { ProtectedShell } from "@/components/ProtectedShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorBanner } from "@/components/ui/error-banner";
import { EmptyState } from "@/components/ui/empty-state";

const KIND_TONE: Record<string, "info" | "warning" | "success" | "neutral"> = {
  PUBLISH: "success",
  CHANGE: "warning",
};

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} hour${hrs === 1 ? "" : "s"} ago`;
  const days = Math.round(hrs / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

export default function NotificationsPage() {
  const qc = useQueryClient();
  const notifications = useNotifications(false);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["notifications"] });

  async function markRead(id: number) {
    try {
      await apiPost(`/api/v1/notifications/${id}/read`);
      invalidate();
    } catch {
      // best-effort
    }
  }
  async function readAll() {
    try {
      await apiPost("/api/v1/notifications/read-all");
      invalidate();
    } catch {
      // best-effort
    }
  }

  const rows = notifications.data ?? [];
  const unread = rows.filter((r) => !r.is_read).length;

  return (
    <ProtectedShell>
      <div className="flex flex-col gap-5">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="display text-3xl text-ink">Notifications</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {unread} unread · timetable publish and mid-year changes.
            </p>
          </div>
          <Button variant="outline" onClick={readAll} disabled={unread === 0}>
            <CheckCheck className="mr-1 h-4 w-4" /> Mark all read
          </Button>
        </div>

        {notifications.isError && <ErrorBanner message="Failed to load notifications" onRetry={() => notifications.refetch()} />}

        <div className="rounded-md border bg-surface shadow-sm">
          {notifications.isLoading ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16" />)}
            </div>
          ) : rows.length === 0 ? (
            <EmptyState
              icon={Bell}
              title="No notifications yet"
              body="You'll see a notification here when a timetable is published or a mid-year change is applied."
            />
          ) : (
            <ul className="divide-y divide-border">
              {rows.map((n) => (
                <li
                  key={n.id}
                  className={`flex items-start gap-3 px-4 py-3 ${n.is_read ? "" : "bg-primary/5"}`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-ink">{n.title}</span>
                      <Badge variant={KIND_TONE[n.kind] ?? "neutral"}>{n.kind}</Badge>
                      {!n.is_read && <span className="h-2 w-2 rounded-full bg-destructive" />}
                    </div>
                    {n.body && <p className="mt-0.5 text-sm text-muted-foreground">{n.body}</p>}
                    <p className="mt-0.5 text-xs text-muted-foreground">{timeAgo(n.created_at)}</p>
                  </div>
                  {!n.is_read && (
                    <Button variant="ghost" size="sm" className="shrink-0 text-xs" onClick={() => markRead(n.id)}>
                      Mark read
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </ProtectedShell>
  );
}
