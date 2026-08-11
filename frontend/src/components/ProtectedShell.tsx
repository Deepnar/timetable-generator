"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Sidebar } from "./layout/sidebar";
import { Topbar } from "./layout/topbar";

/**
 * Guards a protected page: redirects to /login until a token exists, then
 * renders the app shell (sidebar + topbar + content). Reads the caller's
 * role (via useAuth.me) so the sidebar is role-filtered.
 */
export function ProtectedShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { isAuthenticated, me } = useAuth();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setReady(true);
    if (!isAuthenticated) {
      router.replace("/login");
    }
  }, [isAuthenticated, router]);

  if (!ready || !isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        Checking session…
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar role={me?.role ?? "admin"} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="mx-auto w-full max-w-7xl px-6 py-6">{children}</main>
      </div>
    </div>
  );
}
