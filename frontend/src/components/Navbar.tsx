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

export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { logout } = useAuth();

  return (
    <header className="border-b border-accent-line bg-white/90 backdrop-blur sticky top-0 z-40">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/dashboard" className="flex items-baseline gap-2">
          <span className="display text-lg text-ink">Timetable</span>
          <span className="eyebrow hidden sm:inline">Admin</span>
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
                    ? "text-ink font-medium bg-canvas-deep"
                    : "text-ink-soft hover:text-ink hover:bg-canvas-deep"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
          <button
            onClick={() => {
              logout();
              router.push("/login");
            }}
            className="ml-2 rounded-sm px-3 py-1.5 text-sm text-ink-faint hover:text-ink hover:bg-canvas-deep"
          >
            Sign out
          </button>
        </nav>
      </div>
    </header>
  );
}
