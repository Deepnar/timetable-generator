/** Shared chart palette (matches the design tokens §2). */
export const CHART_COLORS = [
  "#4338CA",
  "#0E7490",
  "#15803D",
  "#B45309",
  "#C2410C",
  "#BE185D",
  "#6D28D9",
  "#64748B",
] as const;

export function chartColor(index: number): string {
  return CHART_COLORS[Math.abs(index) % CHART_COLORS.length];
}
