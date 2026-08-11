"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { navFor } from "@/lib/roles";
import { cn } from "@/lib/utils";

export function Sidebar({ role }: { role: string }) {
  const pathname = usePathname();
  const groups = navFor(role);

  return (
    <aside className="hidden w-56 shrink-0 flex-col bg-ink-panel lg:flex">
      <div className="border-b border-ink-panel-border px-4 py-4">
        <Link href="/dashboard" className="display text-xl text-ink-panel-text">
          Timetable
        </Link>
      </div>
      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
        {groups.map((group) => (
          <div key={group.group}>
            <p className="px-2 pb-1.5 text-[11px] font-medium uppercase tracking-[0.14em] text-ink-panel-muted">
              {group.group}
            </p>
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const active =
                  item.path === "/dashboard"
                    ? pathname === "/dashboard"
                    : pathname?.startsWith(item.path);
                return (
                  <li key={item.path}>
                    <Link
                      href={item.path}
                      className={cn(
                        "block rounded-md px-2 py-1.5 text-sm transition-colors",
                        active
                          ? "bg-ink-panel-soft font-medium text-white"
                          : "text-ink-panel-text/80 hover:bg-ink-panel-soft hover:text-white",
                      )}
                    >
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
      <div className="border-t border-ink-panel-border px-4 py-3">
        <p className="eyebrow text-ink-panel-muted">Institutional timetable management</p>
      </div>
    </aside>
  );
}
