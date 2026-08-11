"use client";

import Link from "next/link";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell,
} from "recharts";
import { ArrowRight, DoorOpen, Users, GraduationCap, BookOpen } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ROLE_LABELS, type Role } from "@/lib/roles";
import { useGenerations, useRooms, useSubjects, useGroups, useFaculty } from "@/hooks/use-resources";
import { chartColor } from "@/lib/chart-colors";
import { ProtectedShell } from "@/components/ProtectedShell";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorBanner } from "@/components/ui/error-banner";
import { EmptyState } from "@/components/ui/empty-state";
import { CalendarDays } from "lucide-react";

const STATUS_STYLES: Record<string, string> = {
  PENDING: "bg-amber-100 text-amber-800",
  RUNNING: "bg-sky-100 text-sky-800",
  COMPLETED: "bg-emerald-100 text-emerald-800",
  FAILED: "bg-red-100 text-red-800",
};

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border bg-surface p-5 shadow-sm">
      <h2 className="display mb-4 text-lg text-ink">{title}</h2>
      {children}
    </div>
  );
}

function HBars({ data }: { data: { label: string; value: number }[] }) {
  if (data.length === 0) return <p className="py-8 text-center text-sm text-muted-foreground">No data yet.</p>;
  return (
    <div className="h-52">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
          <CartesianGrid horizontal={false} stroke="#E7E5E4" strokeDasharray="3 3" />
          <XAxis type="number" tick={{ fontSize: 12 }} />
          <YAxis type="category" dataKey="label" width={130} interval={0} tick={{ fontSize: 12 }} />
          <Tooltip cursor={{ fill: "#F5F3EF" }} />
          <Bar dataKey="value" radius={[0, 3, 3, 0]}>
            {data.map((_, i) => <Cell key={i} fill={chartColor(i)} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function StatLink({ href, label, value, icon: Icon }: { href: string; label: string; value: number | string; icon: React.ElementType }) {
  return (
    <Link href={href} className="group rounded-md border bg-surface p-5 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-3xl font-medium tabular-nums text-ink">{value}</div>
          <div className="mt-1 eyebrow">{label}</div>
        </div>
        <Icon className="h-5 w-5 text-muted-foreground group-hover:text-primary" />
      </div>
    </Link>
  );
}

export default function DashboardPage() {
  const { me } = useAuth();
  const rooms = useRooms({ limit: 200 });
  const subjects = useSubjects({ limit: 200 });
  const groups = useGroups({ limit: 200 });
  const faculty = useFaculty({ limit: 200 });
  const generations = useGenerations({ limit: 10 });

  const error = rooms.error ?? subjects.error ?? groups.error ?? faculty.error ?? generations.error;
  const anyLoading = rooms.isLoading || subjects.isLoading || groups.isLoading || faculty.isLoading;

  const roomsByType = Object.entries(
    rooms.data?.rows.reduce<Record<string, number>>((acc, r) => {
      acc[r.room_type] = (acc[r.room_type] ?? 0) + 1;
      return acc;
    }, {}) ?? {},
  )
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([label, value]) => ({ label: label.replace("_", " "), value }));

  const subjectsBySem = Object.entries(
    subjects.data?.rows.reduce<Record<string, number>>((acc, s) => {
      const k = `Sem ${s.semester}`;
      acc[k] = (acc[k] ?? 0) + 1;
      return acc;
    }, {}) ?? {},
  )
    .sort((a, b) => a[0].localeCompare(b[0], undefined, { numeric: true }))
    .map(([label, value]) => ({ label, value }));

  const groupsByDept = Object.entries(
    groups.data?.rows.reduce<Record<string, number>>((acc, g) => {
      acc[g.department] = (acc[g.department] ?? 0) + 1;
      return acc;
    }, {}) ?? {},
  )
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([label, value]) => ({ label, value }));

  const runs = generations.data?.rows ?? [];

  return (
    <ProtectedShell>
      <div className="flex flex-col gap-6">
        <div>
          {me && <p className="eyebrow mb-1">{ROLE_LABELS[me.role as Role] ?? me.role} view</p>}
          <h1 className="display text-3xl text-ink">Overview</h1>
          <p className="mt-1 text-sm text-muted-foreground">Institution resources and recent generation runs.</p>
        </div>

        {error && <ErrorBanner message="Failed to load dashboard" onRetry={() => { rooms.refetch(); subjects.refetch(); groups.refetch(); generations.refetch(); }} />}

        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {anyLoading ? (
            Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)
          ) : (
            <>
            <StatLink href="/rooms" label="Rooms" value={rooms.data?.total ?? 0} icon={DoorOpen} />
            <StatLink href="/faculty" label="Faculty" value={faculty.data?.total ?? 0} icon={Users} />
            <StatLink href="/groups" label="Groups" value={groups.data?.total ?? 0} icon={GraduationCap} />
            <StatLink href="/subjects" label="Subjects" value={subjects.data?.total ?? 0} icon={BookOpen} />
            </>
          )}
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <ChartCard title="Rooms by type">
            {anyLoading ? <Skeleton className="h-52" /> : <HBars data={roomsByType} />}
          </ChartCard>
          <ChartCard title="Subjects by semester">
            {anyLoading ? <Skeleton className="h-52" /> : <HBars data={subjectsBySem} />}
          </ChartCard>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <ChartCard title="Groups by department">
            {anyLoading ? <Skeleton className="h-52" /> : <HBars data={groupsByDept} />}
          </ChartCard>

          <div className="rounded-md border bg-surface p-5 shadow-sm">
            <h2 className="display mb-4 text-lg text-ink">Recent generation runs</h2>
            {generations.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-8" />)}
              </div>
            ) : runs.length === 0 ? (
              <EmptyState
                icon={CalendarDays}
                title="No runs yet"
                body="Configure a profile and generate your first timetable."
              />
            ) : (
              <ul className="divide-y divide-border">
                {runs.map((run) => (
                  <li key={run.id} className="flex items-center justify-between py-2.5 text-sm">
                    <div className="min-w-0">
                      <span className="font-medium text-ink">Run #{run.id}</span>
                      <span className="ml-2 text-muted-foreground">
                        {run.academic_year} · {run.timetable_type}
                      </span>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <span className="text-muted-foreground">
                        {run.instances_produced}/{run.instances_requested} inst
                      </span>
                      <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[run.generation_status] ?? "bg-muted text-muted-foreground"}`}>
                        {run.generation_status}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <Link href="/generate" className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
              New generation <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </div>
    </ProtectedShell>
  );
}
