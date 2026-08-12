"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { apiPost } from "@/lib/api";
import type { AdminResponse } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function RegisterPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiPost<AdminResponse>("/auth/register", { name, email, password });
      toast.success("Account created — sign in to continue");
      router.replace("/login");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
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
          <h1 className="display text-2xl text-ink">Create an account</h1>
          <p className="mb-6 mt-1 text-sm text-muted-foreground">Register to manage timetables</p>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-sm font-medium text-ink">Name</span>
              <Input
                type="text"
                required
                autoComplete="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
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
                autoComplete="new-password"
                minLength={6}
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
              {busy ? "Creating account…" : "Create account"}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link href="/login" className="font-medium text-primary underline">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
