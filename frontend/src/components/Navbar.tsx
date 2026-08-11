"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/rooms", label: "Rooms" },
  { href: "/faculty", label: "Faculty" },
  { href: "/groups", label: "Groups" },
  { href: "/subjects", label: "Subjects" },
];

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  hod: "Dept. Head",
  teacher: "Teacher",
  student: "Student",
};

export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { me, logout } = useAuth();

  return (
    <header className="sticky top-0 z-40 border-b border-accent-line bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/dashboard" className="flex items-baseline gap-2">
          <span className="display text-lg text-ink">Timetable</span>
        </Link>
        <nav className="flex items-center gap-1">
          {NAV_ITEMS.map((item) => {
            const active = pathname?.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-sm px-3 py-1.5 text-sm ${
                  active
                    ? "bg-canvas-deep font-medium text-ink"
                    : "text-ink-soft hover:bg-canvas-deep hover:text-ink"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
          {me && (
            <div className="ml-3 flex items-center gap-2 border-l border-accent-line pl-3">
              <div className="hidden text-right sm:block">
                <div className="text-sm font-medium leading-tight text-ink">{me.name}</div>
                <div className="eyebrow leading-tight">{ROLE_LABELS[me.role] ?? me.role}</div>
              </div>
              <button
                onClick={() => {
                  logout();
                  router.push("/login");
                }}
                className="rounded-sm px-2 py-1.5 text-sm text-ink-faint hover:bg-canvas-deep hover:text-ink"
                title="Sign out"
              >
                Sign out
              </button>
            </div>
          )}
        </nav>
      </div>
    </header>
  );
}
