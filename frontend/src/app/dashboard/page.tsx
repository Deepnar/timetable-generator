"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiList } from "@/lib/api";
import type { Generation, Room, Faculty, StudentGroup, Subject } from "@/lib/types";
import { ProtectedShell } from "@/components/ProtectedShell";

const STATUS_STYLES: Record<string, string> = {
  PENDING: "bg-amber-100 text-amber-700",
  RUNNING: "bg-blue-100 text-blue-700",
  COMPLETED: "bg-emerald-100 text-emerald-700",
  FAILED: "bg-red-100 text-red-700",
};

export default function DashboardPage() {
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [runs, setRuns] = useState<Generation[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [rooms, faculty, groups, subjects, generations] = await Promise.all([
          apiList<Room>("/api/v1/rooms/", { limit: 1 }),
          apiList<Faculty>("/api/v1/faculty/", { limit: 1 }),
          apiList<StudentGroup>("/api/v1/groups/", { limit: 1 }),
          apiList<Subject>("/api/v1/subjects/", { limit: 1 }),
          apiList<Generation>("/api/v1/generate/", { limit: 10 }),
        ]);
        if (cancelled) return;
        setCounts({
          rooms: rooms.total,
          faculty: faculty.total,
          groups: groups.total,
          subjects: subjects.total,
        });
        setRuns(generations.rows);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load dashboard");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const statCards = [
    { label: "Rooms", value: counts.rooms ?? "…", href: "/rooms" },
    { label: "Faculty", value: counts.faculty ?? "…", href: "/faculty" },
    { label: "Groups", value: counts.groups ?? "…", href: "/groups" },
    { label: "Subjects", value: counts.subjects ?? "…", href: "/subjects" },
  ];

  return (
    <ProtectedShell>
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">Dashboard</h1>
          <p className="text-sm text-slate-500">Overview of schedulable resources and recent runs.</p>
        </div>

        {error && (
          <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {statCards.map((card) => (
            <Link
              key={card.label}
              href={card.href}
              className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm transition hover:border-slate-300"
            >
              <div className="text-3xl font-semibold text-slate-800">{card.value}</div>
              <div className="mt-1 text-sm text-slate-500">{card.label}</div>
            </Link>
          ))}
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-3 text-lg font-semibold text-slate-800">Recent generation runs</h2>
          {runs.length === 0 ? (
            <p className="text-sm text-slate-500">No runs yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-slate-500">
                  <th className="pb-2 pr-4 font-medium">#</th>
                  <th className="pb-2 pr-4 font-medium">Year</th>
                  <th className="pb-2 pr-4 font-medium">Type</th>
                  <th className="pb-2 pr-4 font-medium">Instances</th>
                  <th className="pb-2 pr-4 font-medium">Status</th>
                  <th className="pb-2 font-medium">Triggered</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {runs.map((run) => (
                  <tr key={run.id}>
                    <td className="py-2 pr-4 text-slate-700">{run.id}</td>
                    <td className="py-2 pr-4 text-slate-700">{run.academic_year}</td>
                    <td className="py-2 pr-4 text-slate-700">{run.timetable_type}</td>
                    <td className="py-2 pr-4 text-slate-700">
                      {run.instances_produced}/{run.instances_requested}
                    </td>
                    <td className="py-2 pr-4">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[run.generation_status] ?? "bg-slate-100 text-slate-600"}`}
                      >
                        {run.generation_status}
                      </span>
                    </td>
                    <td className="py-2 text-slate-500">
                      {run.triggered_at ? new Date(run.triggered_at).toLocaleString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </ProtectedShell>
  );
}
