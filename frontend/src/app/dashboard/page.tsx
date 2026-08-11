"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiList } from "@/lib/api";
import type { Generation, Room, Faculty, StudentGroup, Subject } from "@/lib/types";
import { ProtectedShell } from "@/components/ProtectedShell";

const STATUS_STYLES: Record<string, string> = {
  PENDING: "bg-amber-50 text-amber-800",
  RUNNING: "bg-sky-50 text-sky-800",
  COMPLETED: "bg-emerald-50 text-emerald-800",
  FAILED: "bg-red-50 text-red-800",
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
          <div>
            <h1 className="display text-3xl text-ink">Dashboard</h1>
            <p className="mt-1 text-sm text-ink-faint">Overview of schedulable resources and recent runs.</p>
          </div>
        </div>

        {error && (
          <div className="rounded-sm border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {statCards.map((card) => (
            <Link
              key={card.label}
              href={card.href}
              className="rounded-sm bg-white p-5 shadow-card transition hover:shadow-lift"
            >
              <div className="text-3xl font-medium text-ink">{card.value}</div>
              <div className="mt-1 eyebrow">{card.label}</div>
            </Link>
          ))}
        </div>

        <div className="rounded-sm bg-white p-6 shadow-card">
          <h2 className="display mb-4 text-lg text-ink">Recent generation runs</h2>
          {runs.length === 0 ? (
            <p className="text-sm text-ink-faint">No runs yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-accent-line text-left">
                  <th className="pb-2 pr-4 eyebrow font-medium">#</th>
                  <th className="pb-2 pr-4 eyebrow font-medium">Year</th>
                  <th className="pb-2 pr-4 eyebrow font-medium">Type</th>
                  <th className="pb-2 pr-4 eyebrow font-medium">Instances</th>
                  <th className="pb-2 pr-4 eyebrow font-medium">Status</th>
                  <th className="pb-2 eyebrow font-medium">Triggered</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-accent-line">
                {runs.map((run) => (
                  <tr key={run.id}>
                    <td className="py-2 pr-4 text-ink">{run.id}</td>
                    <td className="py-2 pr-4 text-ink">{run.academic_year}</td>
                    <td className="py-2 pr-4 text-ink">{run.timetable_type}</td>
                    <td className="py-2 pr-4 text-ink">
                      {run.instances_produced}/{run.instances_requested}
                    </td>
                    <td className="py-2 pr-4">
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[run.generation_status] ?? "bg-canvas-deep text-ink-soft"}`}
                      >
                        {run.generation_status}
                      </span>
                    </td>
                    <td className="py-2 text-ink-soft">
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
