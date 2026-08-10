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
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/dashboard" className="text-lg font-semibold text-slate-800">
          Timetable Admin
        </Link>
        <nav className="flex items-center gap-1">
          {NAV_ITEMS.map((item) => {
            const active = pathname?.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded px-3 py-1.5 text-sm ${
                  active
                    ? "bg-slate-800 text-white"
                    : "text-slate-600 hover:bg-slate-100"
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
            className="ml-2 rounded px-3 py-1.5 text-sm text-slate-500 hover:bg-slate-100"
          >
            Sign out
          </button>
        </nav>
      </div>
    </header>
  );
}
