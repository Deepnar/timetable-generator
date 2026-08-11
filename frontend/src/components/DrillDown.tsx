"use client";

import { ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** One clickable branch (e.g. "LAB" or "Sem 3"). value = filter value, count = X-Total-Count. */
export interface FacetOption {
  value: string;
  label: string;
  count?: number;
}

interface FacetTilesProps {
  options: FacetOption[];
  active: string | null;
  onSelect: (value: string | null) => void;
  /** Fixed grid columns (e.g. grid-cols-5) so short labels line up. */
  className?: string;
}

/** Level-1 category row: big count-bearing tiles (the "root branches"). */
export function FacetTiles({ options, active, onSelect, className }: FacetTilesProps) {
  return (
    <div className={cn("grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5", className)}>
      {options.map((opt) => {
        const isActive = active === opt.value;
        return (
          <button
            key={opt.value}
            onClick={() => onSelect(isActive ? null : opt.value)}
            className={cn(
              "flex flex-col items-start gap-1 rounded-md border p-4 text-left shadow-sm transition-all",
              isActive
                ? "border-primary bg-primary text-primary-foreground shadow-md"
                : "border-border bg-surface text-ink hover:shadow-md",
            )}
          >
            <span className="text-2xl font-medium tabular-nums">{opt.count ?? "…"}</span>
            <span className={cn("text-sm font-medium", isActive ? "text-primary-foreground/80" : "text-ink-soft")}>
              {opt.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}

interface FacetSectionProps {
  label: string;
  options: FacetOption[];
  active: string | null;
  onSelect: (value: string | null) => void;
  /** The true filtered branch total, shown on the "All" row (NOT the sum of
   * bucket counts — overlapping buckets like capacity ranges double-count). */
  allCount?: number;
}

/** A facet rail section (e.g. Building, Department). 'All' clears the facet. */
export function FacetSection({ label, options, active, onSelect, allCount }: FacetSectionProps) {
  return (
    <div>
      <p className="eyebrow mb-1.5 px-2">{label}</p>
      <ul className="space-y-0.5">
        <li>
          <button
            onClick={() => onSelect(null)}
            className={cn(
              "flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm transition-colors",
              active === null ? "bg-accent font-medium text-accent-foreground" : "text-ink-soft hover:bg-muted hover:text-ink",
            )}
          >
            <span>All {label.toLowerCase()}</span>
            {allCount != null && (
              <span className="tabular-nums text-muted-foreground">{allCount}</span>
            )}
          </button>
        </li>
        {options.map((opt) => {
          const isActive = active === opt.value;
          return (
            <li key={opt.value}>
              <button
                onClick={() => onSelect(isActive ? null : opt.value)}
                className={cn(
                  "flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm transition-colors",
                  isActive ? "bg-accent font-medium text-accent-foreground" : "text-ink-soft hover:bg-muted hover:text-ink",
                )}
              >
                <span className="truncate">{opt.label}</span>
                <span className="ml-2 shrink-0 tabular-nums text-muted-foreground">{opt.count ?? "…"}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export interface Crumb {
  label: string;
  /** Removing this crumb clears this filter level and everything below it. */
  clearLevel: () => void;
}

/** Drill path: Rooms > Lab > Main, with climb-back-one-level controls. */
export function Breadcrumbs({ crumbs, onClearAll }: { crumbs: Crumb[]; onClearAll: () => void }) {
  if (crumbs.length === 0) return null;
  return (
    <nav className="flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
      {crumbs.map((crumb, i) => {
        const isLast = i === crumbs.length - 1;
        return (
          <span key={i} className="flex items-center gap-1">
            <button
              onClick={crumb.clearLevel}
              className={cn(
                "rounded px-1 py-0.5 hover:bg-muted hover:text-ink",
                isLast && "font-medium text-ink",
              )}
            >
              {crumb.label}
            </button>
            {!isLast && <ChevronRight className="h-3.5 w-3.5" />}
          </span>
        );
      })}
      <Button variant="ghost" size="sm" onClick={onClearAll} className="ml-1 h-6 text-xs text-muted-foreground hover:text-ink">
        Clear all
      </Button>
    </nav>
  );
}
