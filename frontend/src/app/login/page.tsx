"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiPost } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { LoginResponse } from "@/lib/types";

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
      // /auth is the only non-versioned path the client calls (DD-019).
      const res = await apiPost<LoginResponse>("/auth/login", { email, password });
      login(res.access_token);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="mb-1 text-xl font-semibold text-slate-800">Timetable Admin</h1>
        <p className="mb-6 text-sm text-slate-500">Sign in to manage timetables</p>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-600">Email</span>
            <input
              type="email"
              required
              autoComplete="email"
              className="rounded border border-slate-300 px-3 py-2 focus:border-slate-400 focus:outline-none"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-600">Password</span>
            <input
              type="password"
              required
              autoComplete="current-password"
              className="rounded border border-slate-300 px-3 py-2 focus:border-slate-400 focus:outline-none"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && (
            <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={busy}
            className="rounded bg-slate-800 px-4 py-2 font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
