"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiList } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Generation, Room, Faculty, StudentGroup, Subject } from "@/lib/types";
import { ProtectedShell } from "@/components/ProtectedShell";

const STATUS_STYLES: Record<string, string> = {
  PENDING: "bg-amber-100 text-amber-800",
  RUNNING: "bg-sky-100 text-sky-800",
  COMPLETED: "bg-emerald-100 text-emerald-800",
  FAILED: "bg-red-100 text-red-800",
};

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  hod: "Department Head",
  teacher: "Teacher",
  student: "Student",
};

function HBar({ label, value, max, color = "bg-ink" }: { label: string; value: number; max: number; color?: string }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-40 shrink-0 truncate text-ink-soft">{label}</span>
      <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-canvas-deep">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 shrink-0 text-right tabular-nums text-ink">{value}</span>
    </div>
  );
}

export default function DashboardPage() {
  const { me } = useAuth();
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [runs, setRuns] = useState<Generation[]>([]);
  const [roomsByType, setRoomsByType] = useState<[string, number][]>([]);
  const [subjectsBySem, setSubjectsBySem] = useState<[string, number][]>([]);
  const [groupsByDept, setGroupsByDept] = useState<[string, number][]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [rooms, faculty, groups, subjects, generations] = await Promise.all([
          apiList<Room>("/api/v1/rooms/", { limit: 200 }),
          apiList<Faculty>("/api/v1/faculty/", { limit: 200 }),
          apiList<StudentGroup>("/api/v1/groups/", { limit: 200 }),
          apiList<Subject>("/api/v1/subjects/", { limit: 200 }),
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

        // charts
        const byType = new Map<string, number>();
        for (const r of rooms.rows) byType.set(r.room_type, (byType.get(r.room_type) ?? 0) + 1);
        setRoomsByType(Array.from(byType.entries()).sort((a, b) => b[1] - a[1]).slice(0, 6));

        const bySem = new Map<number, number>();
        for (const s of subjects.rows) bySem.set(s.semester, (bySem.get(s.semester) ?? 0) + 1);
        setSubjectsBySem(Array.from(bySem.entries()).sort((a, b) => a[0] - b[0]).map(([k, v]) => [`Sem ${k}`, v]));

        const byDept = new Map<string, number>();
        for (const g of groups.rows) byDept.set(g.department, (byDept.get(g.department) ?? 0) + 1);
        setGroupsByDept(Array.from(byDept.entries()).sort((a, b) => b[1] - a[1]).slice(0, 5));
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

  const maxRooms = Math.max(1, ...roomsByType.map(([, v]) => v));
  const maxSem = Math.max(1, ...subjectsBySem.map(([, v]) => v));
  const maxDept = Math.max(1, ...groupsByDept.map(([, v]) => v));
  const chartColors = ["bg-ink", "bg-stone-400", "bg-stone-300"];

  return (
    <ProtectedShell>
      <div className="flex flex-col gap-6">
        <div className="flex items-end justify-between">
          <div>
            {me && (
              <p className="eyebrow mb-1">
                {ROLE_LABELS[me.role] ?? me.role} view
              </p>
            )}
            <h1 className="display text-3xl text-ink">Overview</h1>
            <p className="mt-1 text-sm text-ink-faint">Institution resources and recent generation runs.</p>
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

        <div className="grid gap-6 lg:grid-cols-2">
          <section className="rounded-sm bg-white p-6 shadow-card">
            <h2 className="display mb-4 text-lg text-ink">Rooms by type</h2>
            {roomsByType.length === 0 ? (
              <p className="text-sm text-ink-faint">No rooms yet.</p>
            ) : (
              <div className="flex flex-col gap-3">
                {roomsByType.map(([label, value], i) => (
                  <HBar key={label} label={label} value={value} max={maxRooms}
                        color={chartColors[i % chartColors.length]} />
                ))}
              </div>
            )}
          </section>

          <section className="rounded-sm bg-white p-6 shadow-card">
            <h2 className="display mb-4 text-lg text-ink">Subjects by semester</h2>
            {subjectsBySem.length === 0 ? (
              <p className="text-sm text-ink-faint">No subjects yet.</p>
            ) : (
              <div className="flex flex-col gap-3">
                {subjectsBySem.map(([label, value], i) => (
                  <HBar key={label} label={label} value={value} max={maxSem}
                        color={chartColors[i % chartColors.length]} />
                ))}
              </div>
            )}
          </section>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <section className="rounded-sm bg-white p-6 shadow-card">
            <h2 className="display mb-4 text-lg text-ink">Groups by department</h2>
            {groupsByDept.length === 0 ? (
              <p className="text-sm text-ink-faint">No groups yet.</p>
            ) : (
              <div className="flex flex-col gap-3">
                {groupsByDept.map(([label, value], i) => (
                  <HBar key={label} label={label} value={value} max={maxDept}
                        color={chartColors[i % chartColors.length]} />
                ))}
              </div>
            )}
          </section>

          <section className="rounded-sm bg-white p-6 shadow-card">
            <h2 className="display mb-4 text-lg text-ink">Recent generation runs</h2>
            {runs.length === 0 ? (
              <p className="text-sm text-ink-faint">No runs yet.</p>
            ) : (
              <ul className="divide-y divide-accent-line">
                {runs.map((run) => (
                  <li key={run.id} className="flex items-center justify-between py-2.5 text-sm">
                    <div>
                      <span className="font-medium text-ink">Run #{run.id}</span>
                      <span className="ml-2 text-ink-faint">
                        {run.academic_year} · {run.timetable_type}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-ink-soft">
                        {run.instances_produced}/{run.instances_requested} inst
                      </span>
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[run.generation_status] ?? "bg-canvas-deep text-ink-soft"}`}
                      >
                        {run.generation_status}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </ProtectedShell>
  );
}
