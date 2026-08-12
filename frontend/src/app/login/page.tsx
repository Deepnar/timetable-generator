"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { apiGet, apiPost } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { LoginResponse, Me } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Where each role lands after sign-in (design plan §2). */
const ROLE_HOME: Record<string, string> = {
  teacher: "/my-schedule",
  student: "/my-timetable",
  admin: "/dashboard",
  hod: "/dashboard",
};

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await apiPost<LoginResponse>("/auth/login", { email, password });
      login(res.access_token);
      toast.success("Signed in");
      // Resolve the role and redirect to that persona's home. /auth/me is
      // behind the global gate, so it only works with the fresh token.
      const me = await apiGet<Me>("/auth/me");
      router.replace(ROLE_HOME[me.role] ?? "/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* Brand panel */}
      <div className="hidden w-[45%] flex-col justify-between bg-ink p-10 lg:flex">
        <div>
          <span className="display text-3xl text-[#F5F3EF]">Timetable</span>
        </div>
        <div>
          <p className="display text-4xl leading-tight text-[#F5F3EF]">
            Plan, generate, and publish college timetables.
          </p>
          <p className="mt-4 max-w-md text-sm text-[#A8A29E]">
            Constraint-driven scheduling with greedy and OR-Tools solvers —
            rooms, faculty, groups, and subjects in one place.
          </p>
        </div>
        <p className="eyebrow text-[#A8A29E]">Institutional timetable management</p>
      </div>

      {/* Form panel */}
      <div className="flex flex-1 items-center justify-center bg-background px-4">
        <div className="w-full max-w-sm">
          <div className="mb-6 lg:hidden">
            <span className="display text-2xl text-ink">Timetable</span>
          </div>
          <h1 className="display text-2xl text-ink">Sign in</h1>
          <p className="mb-6 mt-1 text-sm text-muted-foreground">Sign in to manage timetables</p>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-sm font-medium text-ink">Email</span>
              <Input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-sm font-medium text-ink">Password</span>
              <Input
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {error && (
              <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            )}
            <Button type="submit" disabled={busy} className="w-full">
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
