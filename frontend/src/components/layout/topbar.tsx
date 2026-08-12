"use client";

import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ROLE_LABELS, type Role } from "@/lib/roles";
import { Avatar, AvatarFallback, initialsFor } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { NotificationsBell } from "./NotificationsBell";

export function Topbar() {
  const { me, logout } = useAuth();
  const router = useRouter();

  return (
    <header className="sticky top-0 z-40 flex h-14 items-center justify-between border-b bg-surface/90 px-6 backdrop-blur">
      <div className="flex items-center gap-2 lg:hidden">
        <span className="display text-lg text-ink">Timetable</span>
      </div>
      <div className="ml-auto flex items-center gap-3">
        <NotificationsBell />
        {me && (
          <div className="flex items-center gap-2.5">
            <div className="hidden text-right sm:block">
              <div className="text-sm font-medium leading-tight text-ink">{me.name}</div>
              <div className="text-xs leading-tight text-muted-foreground">
                {ROLE_LABELS[me.role as Role] ?? me.role}
              </div>
            </div>
            <Avatar className="h-8 w-8">
              <AvatarFallback>{initialsFor(me.name)}</AvatarFallback>
            </Avatar>
          </div>
        )}
        <Button
          variant="ghost"
          size="icon"
          title="Sign out"
          onClick={() => {
            logout();
            router.push("/login");
          }}
        >
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
