"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { navFor } from "@/lib/roles";
import { cn } from "@/lib/utils";

export function Sidebar({ role }: { role: string }) {
  const pathname = usePathname();
  const groups = navFor(role);

  return (
    <aside className="hidden w-56 shrink-0 flex-col border-r bg-surface lg:flex">
      <div className="px-4 py-4">
        <Link href="/dashboard" className="display text-xl text-ink">
          Timetable
        </Link>
      </div>
      <nav className="flex-1 space-y-5 overflow-y-auto px-3 pb-6">
        {groups.map((group) => (
          <div key={group.group}>
            <p className="eyebrow px-2 pb-1.5">{group.group}</p>
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
                          ? "bg-accent font-medium text-accent-foreground"
                          : "text-ink-soft hover:bg-muted hover:text-ink",
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
    </aside>
  );
}
