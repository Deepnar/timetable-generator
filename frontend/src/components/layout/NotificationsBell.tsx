"use client";

import { useRouter } from "next/navigation";
import { Bell, CheckCheck } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { apiPost } from "@/lib/api";
import { useNotifications, useUnreadCount } from "@/hooks/use-resources";
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export function NotificationsBell() {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: count } = useUnreadCount();
  const notifications = useNotifications(true);
  const rows = notifications.data ?? [];

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["notifications"] });
  };

  async function readAll() {
    try {
      await apiPost("/api/v1/notifications/read-all");
      invalidate();
    } catch {
      // best-effort
    }
  }

  const unread = count?.unread ?? 0;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" title="Notifications" className="relative">
          <Bell className="h-4 w-4" />
          {unread > 0 && (
            <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-white">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <p className="eyebrow">Notifications</p>
          <Button variant="ghost" size="sm" className="h-6 gap-1 px-2 text-xs" onClick={readAll}>
            <CheckCheck className="h-3.5 w-3.5" /> Mark all read
          </Button>
        </div>
        {rows.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-muted-foreground">
            No unread notifications.
          </p>
        ) : (
          <ul className="max-h-80 overflow-y-auto divide-y divide-border">
            {rows.slice(0, 6).map((n) => (
              <li key={n.id} className="px-4 py-2.5">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium text-ink">{n.title}</p>
                  <span className="shrink-0 text-[11px] text-muted-foreground">{timeAgo(n.created_at)}</span>
                </div>
                {n.body && <p className="mt-0.5 text-xs text-muted-foreground">{n.body}</p>}
              </li>
            ))}
          </ul>
        )}
        <div className="border-t px-4 py-2">
          <Button variant="link" size="sm" className="h-6 px-0" onClick={() => router.push("/notifications")}>
            View all →
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
