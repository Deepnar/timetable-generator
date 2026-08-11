# Frontend Technical Architecture & Implementation Blueprint

Next.js 14 (App Router) + TypeScript + Tailwind CSS 3.4 — the full-stack
timetable product's admin UI. This is the authoritative build blueprint derived
from the qwen3.8-max design review (`frontend-design-plan.md` was the strategy;
this file is the implementation contract). Every page, component, and query is
mapped so coding can start immediately.

> Conventions: all paths under `frontend/src/`. Import alias `@/*` → `src/*`.
> One `"use client"` boundary at the page/feature level; leaf components are
> client components. All data fetching goes through TanStack Query; no raw
> `fetch` in components (only in `lib/api.ts`).

---

## 1. Dependency set (add to `frontend/package.json`)

```jsonc
// dependencies
"@radix-ui/react-dialog": "1.1.2",
"@radix-ui/react-dropdown-menu": "2.1.2",
"@radix-ui/react-popover": "1.1.2",
"@radix-ui/react-select": "2.1.2",
"@radix-ui/react-slot": "1.1.1",
"@radix-ui/react-switch": "1.1.1",
"@radix-ui/react-tabs": "1.1.1",
"@tanstack/react-query": "^5.59.0",
"@tanstack/react-table": "^8.20.5",
"class-variance-authority": "0.7.0",
"clsx": "2.1.1",
"lucide-react": "^0.454.0",
"recharts": "^2.13.3",
"sonner": "^1.5.0",
"tailwind-merge": "2.5.4",
"tailwindcss-animate": "1.0.7"

// devDependencies
"@types/node": "20.x",        // (already present)
"@types/react": "18.x",       // (already present)
```

Radix is the primitive layer; shadcn/ui components are **hand-authored** into
`src/components/ui/` following the shadcn convention (CVA + `cn()`), NOT pulled
via `npx shadcn init` (keeps the repo self-contained and the theme custom).

---

## 2. Design tokens (Tailwind)

`tailwind.config.ts` — replace the current tokens with the blueprint palette.
Radix variables are mapped to CSS custom properties in `globals.css`; Tailwind
classes (`bg-surface`, `text-ink`, `ring-accent`) reference them.

```ts
// tailwind.config.ts
import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

const config: Config = {
  darkMode: ["class"],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas:  "#F5F3EF",
        surface: "#FFFFFF",
        ink:     "#1C1917",
        "ink-soft": "#57534E",
        "ink-faint": "#8A8682",
        border:  "#E7E5E4",
        input:   "#E7E5E4",
        ring:    "rgba(67, 56, 202, 0.35)",
        background: "var(--background)",
        foreground: "var(--foreground)",
        primary:   "#4338CA",
        "primary-foreground": "#FFFFFF",
        "primary-hover": "#3730A3",
        secondary: "#57534E",
        "secondary-foreground": "#FFFFFF",
        muted:     "#F1F0EE",
        "muted-foreground": "#8A8682",
        accent:    "#EEF0FB",            // indigo 8% tint
        "accent-foreground": "#4338CA",
        destructive: "#B91C1C",
        "destructive-foreground": "#FFFFFF",
        success:   "#15803D",
        warning:   "#B45309",
        info:      "#0369A1",
        chart: ["#4338CA","#0E7490","#15803D","#B45309","#C2410C","#BE185D","#6D28D9","#64748B"],
      },
      fontFamily: {
        display: ['"Fraunces"', "Georgia", "serif"],
        sans:    ['"Inter"', "-apple-system", "sans-serif"],
        mono:    ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      borderRadius: {
        sm: "6px", md: "10px", lg: "14px", full: "9999px",
      },
      boxShadow: {
        sm: "0 1px 2px rgba(28,25,23,0.06)",
        md: "0 4px 12px rgba(28,25,23,0.08)",
        lg: "0 16px 40px rgba(28,25,23,0.16)",
      },
    },
  },
  plugins: [animate],
};
export default config;
```

`src/app/globals.css` — import the three Google fonts, define Radix CSS vars,
and the shadcn base layer:

```css
@import url("https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap");
@tailwind base; @tailwind components; @tailwind utilities;

:root {
  --background: #F5F3EF; --foreground: #1C1917;
  --card: #FFFFFF; --card-foreground: #1C1917;
  --primary: #4338CA; --primary-foreground: #FFFFFF;
  --secondary: #57534E; --secondary-foreground: #FFFFFF;
  --muted: #F1F0EE; --muted-foreground: #8A8682;
  --accent: #EEF0FB; --accent-foreground: #4338CA;
  --destructive: #B91C1C; --destructive-foreground: #FFFFFF;
  --border: #E7E5E4; --input: #E7E5E4; --ring: rgba(67,56,202,0.35);
  --radius: 0.625rem;
}
* { @apply border-border; }
body { @apply bg-background text-foreground font-sans antialiased; }
/* editorial display headings */
.display { @apply font-display tracking-tight; }
.eyebrow { @apply text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground; }
```

---

## 3. Data layer

### 3.1 API client (`src/lib/api.ts`, extend existing)

Add typed helpers TanStack Query calls:

```ts
// apiFetch already exists (attaches Bearer, X-Total-Count, 401→/login).
export interface ListParams {
  skip?: number; limit?: number;
  [filter: string]: string | number | undefined;
}
export async function apiList<T>(path: string, params: ListParams = {}): Promise<{ rows: T[]; total: number }> {
  // unchanged signature — already returns { rows, total } with X-Total-Count.
}
```

### 3.2 Query provider (`src/app/providers.tsx`)

```tsx
"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { useState } from "react";
export function Providers({ children }: { children: React.ReactNode }) {
  const [qc] = useState(() => new QueryClient({
    defaultOptions: { queries: { staleTime: 15_000, retry: 1 } },
  }));
  return (
    <QueryClientProvider client={qc}>
      {children}
      <Toaster position="bottom-right" richColors closeButton />
    </QueryClientProvider>
  );
}
```

Mount in `src/app/layout.tsx` (server component) inside `AuthProvider`.

### 3.3 Query hooks (`src/hooks/use-resources.ts`)

```ts
"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiList, apiPost, apiPut, apiDelete } from "@/lib/api";
import type { Room, Faculty, StudentGroup, Subject, Generation, Instance, Slot, Me } from "@/lib/types";

export const qk = {
  rooms: (p) => ["rooms", p] as const,
  faculty: (p) => ["faculty", p] as const,
  groups: (p) => ["groups", p] as const,
  subjects: (p) => ["subjects", p] as const,
  generations: (p) => ["generations", p] as const,
  instances: (p) => ["instances", p] as const,
  instanceSlots: (id) => ["instance", id, "slots"] as const,
  me: () => ["me"] as const,
};

export function useRooms(params) { return useQuery({ queryKey: qk.rooms(params), queryFn: () => apiList<Room>("/api/v1/rooms", params) }); }
export function useFaculty(params) { return useQuery({ queryKey: qk.faculty(params), queryFn: () => apiList<Faculty>("/api/v1/faculty", params) }); }
export function useGroups(params) { return useQuery({ queryKey: qk.groups(params), queryFn: () => apiList<StudentGroup>("/api/v1/groups", params) }); }
export function useSubjects(params) { return useQuery({ queryKey: qk.subjects(params), queryFn: () => apiList<Subject>("/api/v1/subjects", params) }); }
export function useGenerations(params) { return useQuery({ queryKey: qk.generations(params), queryFn: () => apiList<Generation>("/api/v1/generate", params) }); }
export function useGenerationStatus(id) {
  return useQuery({ queryKey: ["generation", id, "status"], queryFn: () => apiGet<Generation>(`/api/v1/generate/${id}/status`), refetchInterval: (q) => {
    const s = q.state.data?.generation_status;
    return s === "PENDING" || s === "RUNNING" ? 2000 : false;   // poll async runs
  }});
}
export function useInstances(generationId) { return useQuery({ queryKey: qk.instances({generationId}), queryFn: () => apiList<Instance>(`/api/v1/instances/${generationId}`) }); }
export function useInstanceSlots(instanceId) { return useQuery({ queryKey: qk.instanceSlots(instanceId), queryFn: () => apiGet<Slot[]>(`/api/v1/instances/${instanceId}/slots`) }); }
export function useMe() { return useQuery({ queryKey: qk.me(), queryFn: () => apiGet<Me>("/auth/me") }); }

// Optimistic mutation: slot override (see §7.5)
export function useSlotOverride(instanceId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slotId, payload }) => apiPut(`/api/v1/instances/${instanceId}/slots/${slotId}`, payload),
    onMutate: async ({ slotId, payload }) => {
      await qc.cancelQueries({ queryKey: qk.instanceSlots(instanceId) });
      const prev = qc.getQueryData(qk.instanceSlots(instanceId));
      qc.setQueryData(qk.instanceSlots(instanceId), (old) =>
        old?.map((s) => (s.id === slotId ? { ...s, ...payload } : s)));
      return { prev };
    },
    onError: (_e, _v, ctx) => qc.setQueryData(qk.instanceSlots(instanceId), ctx.prev),
    onSettled: () => qc.invalidateQueries({ queryKey: qk.instanceSlots(instanceId) }),
  });
}
```

---

## 4. shadcn/ui component kit (`src/components/ui/`)

Hand-authored, CVA + `cn()`. `cn` util: `clsx` + `tailwind-merge`.

`utils.ts`:
```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)); }
```

Required kit (each one file, standard shadcn anatomy):

| File | Radix basis | Purpose |
|---|---|---|
| `button.tsx` | Radix Slot | Variants: `default` (primary indigo), `secondary` (ink), `outline`, `ghost`, `destructive`, `link`; sizes sm/default/lg/icon. |
| `input.tsx`, `textarea.tsx` | — | 6px radius, 1px border, focus ring. |
| `select.tsx` | Radix Select | Replaces native `<select>` everywhere (filters, forms, perspective). |
| `checkbox.tsx` | Radix Checkbox | Styled checkbox (amenities, multi-select). |
| `switch.tsx` | Radix Switch | Boolean flags (requires_lab, feature toggles, amenities). |
| `dialog.tsx` | Radix Dialog | Modal + ConfirmDialog (delete/publish). |
| `sheet.tsx` | Radix Dialog (side) | ResourceFormDrawer (right 440px) for create/edit. |
| `popover.tsx` | Radix Popover | CellPopover (assignment cell, slot override), info popovers. |
| `dropdown-menu.tsx` | Radix DropdownMenu | Row actions, profile menu, export menu. |
| `tabs.tsx` | Radix Tabs | Profile builder tabs, viewer rails. |
| `badge.tsx` | — | Tones: neutral/info/success/warning/danger/accent; 10% tint + 700 text. |
| `command.tsx` | Radix Dialog | Global search / command palette (optional, later). |
| `avatar.tsx` | Radix Avatar | Deterministic-hue initials. |
| `skeleton.tsx` | — | Layout-mirroring loading bars. |
| `tooltip.tsx` | Radix Tooltip | Hover detail (cells, icons). |
| `separator.tsx` | Radix Separator | Hairline dividers. |

Icons: **lucide-react** everywhere (`Plus, Search, Download, Upload, Pencil, Trash2, Play, Check, X, ChevronDown, CalendarDays, Users, GraduationCap, DoorOpen, FileDown, AlertTriangle, Loader2, Undo2`).

---

## 5. App shell (sidebar + topbar)

`src/components/layout/app-shell.tsx` + `sidebar.tsx` + `topbar.tsx`.

- **Sidebar**: 240px, collapsible to 68px icon rail below 1024px. Groups from
  the design plan §IA. Active item: `bg-accent text-accent-foreground` + 3px
  left accent bar. Group labels: `eyebrow` in `text-muted-foreground`.
- **Role filtering**: read `useMe()`; a `navFor(role)` returns the visible
  groups. Teacher → only My Schedule + Exports; student → only My Timetable +
  Exports.
- **Topbar**: sticky, serif wordmark, global search (later), user chip
  (avatar + name + role badge from `useMe()`), sign-out.

`ProtectedShell` currently wraps each page with `Navbar`; replace with:
```tsx
export function ProtectedShell({ children }) {
  const { isAuthenticated } = useAuth();
  // redirect to /login if !isAuthenticated (existing logic)
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <Topbar />
        <main className="mx-auto w-full max-w-7xl px-6 py-6">{children}</main>
      </div>
    </div>
  );
}
```

---

## 6. Resource list shell (Rooms / Faculty / Groups / Subjects)

One reusable feature: `src/features/resources/resource-page.tsx`.

```tsx
interface ResourceConfig<T> {
  title: string;
  query: (params) => Query;              // useRooms etc.
  columns: ColumnDef<T>[];               // TanStack Table
  filterFields: FilterField[];           // search + selects
  drawer: { fields: FieldConfig[]; toPayload; toForm };
  summary: (rows: T[]) => Chip[];        // existing summary chips
}
```

### 6.1 Server-side table (`src/components/ui/data-table.tsx`)

TanStack Table v8 + server state (no `getPaginationRowModel`; state lives in
the query params):

```tsx
"use client";
import { useReactTable, getCoreRowModel, flexRender, type ColumnDef, type SortingState } from "@tanstack/react-table";
import { DataTablePagination } from "./data-table-pagination";

export function DataTable<T>({ columns, rows, totalCount, page, pageSize,
  onPageChange, onPageSizeChange, sorting, onSortingChange, loading, emptyNode }: Props) {
  const table = useReactTable({
    data: rows, columns,
    state: { sorting },
    onSortingChange,
    manualPagination: true, manualSorting: true,   // server-driven
    pageCount: Math.max(1, Math.ceil(totalCount / pageSize)),
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <div className="rounded-md border">
      <Table> {/* shadcn table: sticky header, 44px rows, hover:bg-muted */}
        <TableHeader>{table.getHeaderGroups().map(hg => (
          <TableRow key={hg.id}>{hg.headers.map(header => (
            <TableHead key={header.id} className={cn(header.column.columnDef.meta?.align === "right" && "text-right")}>
              {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
            </TableHead>))}
          </TableRow>))}</TableHeader>
        <TableBody>{loading ? <RowSkeleton cols={columns.length} rows={pageSize} />
          : rows.length === 0 ? <TableRow><TableCell colSpan={columns.length}>{emptyNode ?? "No rows."}</TableCell></TableRow>
          : table.getRowModel().rows.map(row => (
            <TableRow key={row.id} onClick={...} className="hover:bg-muted cursor-pointer">
              {row.getVisibleCells().map(cell => (
                <TableCell key={cell.id} className={...}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>))}
            </TableRow>))}</TableBody>
      </Table>
      <DataTablePagination total={totalCount} page={page} pageSize={pageSize}
        onPageChange={onPageChange} onPageSizeChange={onPageSizeChange} />
    </div>
  );
}
```

Sortable header helper: `Button variant="ghost"` with `ArrowUpDown` icon
toggling `sorting` `[{ id, desc }]` → appended to query params.

### 6.2 FilterBar

`search` input (300ms debounce), styled `Select`s per filter, active-count
chip, Clear button. All state → query params → `useXxx(params)` refetch.

### 6.3 ResourceFormDrawer (`sheet.tsx`)

Right 440px drawer. Fields rendered by the `field-kit` (§7.1); amenities as
`Switch` rows; `required` label + inline `error` under field; sticky footer
Cancel/Save; `busy` disables Save and shows spinner.

### 6.4 CSV import

`CsvImportModal` (`dialog.tsx`): drag-drop file → `POST /api/v1/import/{entity}`
(multipart) → preview + per-row errors; success toast + invalidate query.

---

## 7. TimetableGrid (the money screen)

### 7.1 Data model → grid

The backend returns flat `Slot[]`. Normalize once:

```ts
interface GridSession {
  key: string;                  // `${subjectId}-${facultyId}-${roomId}-${groupId}-${day}-${startSlot}`
  subjectId: number | null;
  subjectCode?: string;
  subjectName?: string;
  facultyId: number | null;
  facultyName?: string;
  roomId: number | null;
  roomCode?: string;
  groupId: number | null;
  groupName?: string;
  day: number;                  // 0..6
  startSlot: number;            // 1-based
  duration: number;             // block_length (labs span 2-3)
  sessionType: string;          // LECTURE | LAB | ...
  isManualOverride: boolean;
  warnings: string[];
}
```

`src/features/timetable/use-grid-sessions.ts` maps `Slot[]` → `GridSession[]`
and joins lookups (subjects/faculty/rooms/groups fetched alongside slots).

### 7.2 Component hierarchy

```
TimetableViewer (page: /instances/[id])
└─ TimetableGrid
   ├─ GridToolbar          — perspective Select, density toggle, legend, export menu
   ├─ GridHeaderRow        — sticky day headers (accent tint on "today")
   ├─ GridGutter           — sticky slot-time column (mono 09:00)
   ├─ GridBody             — pure CSS grid, row-spanning sessions
   │  └─ GridCell          — one session block OR empty cell
   │     └─ (edit mode) SlotPopover (Radix Popover) — override + revalidate
   └─ ViolationsPanel      — right rail: warnings + hard-violations list
```

### 7.3 Tailwind CSS Grid layout

Pure CSS grid — 8 slots × 6 days = 48 cells, no virtualization.

```tsx
// Container
<div className="overflow-x-auto">
  <div
    className="grid min-w-[900px]"
    style={{
      gridTemplateColumns: `64px repeat(${days.length}, minmax(150px, 1fr))`,
      gridTemplateRows: `36px repeat(${slotCount}, ${density === "comfortable" ? 64 : 44}px)`,
    }}
  >
    {/* header row */}
    <div className="grid sticky top-0 z-10 bg-surface" style={{ gridColumn: "1 / -1", display: "contents" }}>
      <div className="sticky left-0 z-20 ..." />               {/* corner */}
      {days.map(d => <div className="sticky top-0 ...">{label}</div>)}
    </div>
    {/* slot gutter + cells */}
    {slotNumbers.map(sn => (
      <Fragment key={sn}>
        <div className="sticky left-0 z-10 bg-surface mono text-xs" style={{ gridColumn: 1, gridRow: sn + 1 }}>
          09:00
        </div>
        {days.map(day => (
          <div key={`${day}-${sn}`} style={{ gridColumn: day + 2, gridRow: sn + 1 }}
               className="border-t border-l border-border">
            {sessionAt(day, sn) ? <GridCell session={...} /> : null}
          </div>
        ))}
      </Fragment>
    ))}
  </div>
</div>
```

### 7.4 Multi-slot block sessions (labs)

A session with `duration > 1` spans rows using explicit `gridRow` range. The
cell is placed at the START slot's (day, slot) and stretches over the
following rows:

```tsx
function GridCell({ session, density, perspective, colorMap, onSelect, readOnly }) {
  const color = colorMap[session.subjectId] ?? "neutral";
  return (
    <div
      className={cn(
        "group relative rounded-[6px] border-l-[3px] p-2",
        `bg-[${color.tint}] border-[${color.base}]`,   // see colorCoding
        density === "compact" && "p-1",
      )}
      style={{
        gridColumn: `${session.day + 2} / span 1`,
        gridRow: `${session.startSlot + 1} / span ${session.duration}`,
      }}
      onClick={readOnly ? undefined : () => onSelect(session)}
    >
      <div className="font-mono text-xs font-semibold" style={{ color: color.base }}>
        {session.subjectCode} {session.sessionType === "LAB" && <FlaskConical className="h-3 w-3 inline" />}
      </div>
      {density === "comfortable" && (
        <div className="text-[13px] font-medium text-ink truncate">{session.subjectName}</div>
      )}
      <div className="flex items-center gap-1 text-xs text-ink-soft">
        <Avatar name={session.facultyName} className="h-4 w-4 text-[9px]" />
        <span className="truncate">{session.facultyName}</span>
        <span className="font-mono text-muted-foreground">{session.roomCode}</span>
      </div>
      {session.warnings.length > 0 && <AlertTriangle className="absolute top-1 right-1 h-3.5 w-3.5 text-warning" />}
    </div>
  );
}
```

Row-spanning is achieved by `gridRow: start / span duration`. The grid's
`gridTemplateRows` provides the fixed row track; a 2-slot lab visually merges
two tracks. Because cells for the spanned rows are still rendered (empty),
the `sessionAt` helper must skip slots covered by an earlier start — build a
`Map<day, Map<slot, GridSession>>` and skip occupied spans when placing empty
cells.

### 7.5 Slot override + revalidation (edit mode)

`SlotPopover` (Radix Popover) anchored to the clicked cell:

```
Day Select        (Mon..Sat)
Slot Select       (1..slots_per_day)
Room Select       (filtered: capacity >= group strength, matches room_type)
Faculty Select    (from profile faculty)
[revalidate result]
   - pending: "Checking conflicts…" (Loader2 spin)
   - clean:   green "No conflicts"
   - errors:  danger list of violations
Save (disabled until clean)  → useSlotOverride optimistic mutation + toast
Undo (after commit)          → toast action re-applies previous values
```

Revalidation: `useQuery` keyed on the draft values
(`["slot-revalidate", instanceId, day, slot, roomId, facultyId]`) that calls
the backend checker if exposed; otherwise a client-side `ConstraintChecker`
port. If the backend has no public revalidate endpoint, add one:
`POST /api/v1/instances/{id}/slots/{slotId}/revalidate` returning
`{ ok: boolean, violations: string[] }` (wrap the existing
`_revalidate_slot` logic). **Confirm against `app/router/instances.py` before
phase 4.** PUBLISHED instances are view-only (`readOnly`) with a banner.

### 7.6 Color coding

`src/features/timetable/color-map.ts`:

```ts
const PALETTE = ["#4338CA","#0E7490","#15803D","#B45309","#C2410C","#BE185D","#6D28D9","#64748B"];
export function colorFor(subjectId: number | null) {
  if (subjectId == null) return { base: "#8A8682", tint: "#F1F0EE" };
  const base = PALETTE[subjectId % PALETTE.length];
  return { base, tint: hexWithAlpha(base, 0.08) };   // base at 8% over white
}
```
Stable per subject across grid, compare, exports, teacher/student views.

### 7.7 Compare mode (`/instances/compare?a=&b=`)

Two `TimetableGrid`s, synced vertical scroll (a shared `scrollTop` ref), same
`colorMap`. `DiffList`: sessions present in only one → accent dashed outline;
changed (same subject, different slot/room) → warning ring. Summary bar shows
score + hard-violation deltas. Diff rows click → scroll both grids to the
cell.

---

## 8. Generation & instances flows

### 8.1 `/generate`

Two panes:
- **Left form** (`GenerateForm`): profile `Select` (with coverage preview from
  `GET /profiles/combinations` + `POST /profiles/combinations/{id}/resolve`),
  solver radio (Greedy/OR-Tools), instance count stepper 1-5, "Run in
  background" `Switch` (toggles async), time-limit field.
  Submit → `POST /api/v1/generate/`.
- **Right list** (`RunStatusCard`s): `useGenerations({ limit: 10 })`. Each card
  shows status pill; async runs use `useGenerationStatus(id)` (2s poll until
  COMPLETED/FAILED). COMPLETED → "View instances" link; FAILED → expandable
  `error_log`.

422/409 handling: mutation `onError` → `sonner.error` + form banner.

### 8.2 `/instances` + `/instances/[id]`

- `/instances`: DataTable (columns: id, run, score bar, hard-violations,
  lifecycle pill) with `?run=` filter; select-two rows → sticky CompareBar →
  `/instances/compare?a=&b=`; Publish via ConfirmDialog (warns about archiving
  the previous published instance of the same generation).
- `/instances/[id]`: `TimetableViewer` (§7). Header actions: Select, Publish,
  Export menu (PDF/CSV/iCal), Compare (pick a peer). Right rail:
  ViolationsPanel + legend.

---

## 9. Charts (Recharts) — dashboard

`src/features/dashboard/charts.tsx`:

```tsx
"use client";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip } from "recharts";
import { chartDataFrom } from "./data";

export function HBars({ title, data, unit }: { title: string; data: { label: string; value: number }[]; unit?: string }) {
  const colors = ["#4338CA","#0E7490","#15803D","#B45309","#C2410C","#BE185D","#6D28D9","#64748B"];
  return (
    <div className="rounded-md border bg-card p-5">
      <h2 className="display text-lg mb-4">{title}</h2>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
            <CartesianGrid horizontal={false} stroke="#E7E5E4" strokeDasharray="3 3" />
            <XAxis type="number" tick={{ fontSize: 12 }} />
            <YAxis type="category" dataKey="label" width={120} tick={{ fontSize: 12 }} />
            <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ fill: "#F5F3EF" }} />
            <Bar dataKey="value" radius={[0, 3, 3, 0]}>
              {data.map((_, i) => <Cell key={i} fill={colors[i % colors.length]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
```

Dashboard uses `useRooms/useSubjects/useGroups` (limit 200) and
`useGenerations`, computes the three breakdowns, and renders 3 `HBars` +
StatCards + RunsList. Role-aware: HOD variant scopes to their department.

---

## 10. Toasts (Sonner)

- Publish success → `toast.success("Published — previous instance archived")`
- Delete → `toast.success("Deleted", { action: { label: "Undo", onClick: undo } })`
- Slot override → `toast.success("Slot updated", { action: { label: "Undo", ... } })`
- Override rejected → `toast.error("Override rejected", { description: violations.join(" · ") })`
- Generation complete → `toast.success("Run #12 completed", { action: { label: "View instances", onClick: push } })`

---

## 11. Roles

`src/lib/roles.ts`:

```ts
export type Role = "admin" | "hod" | "teacher" | "student";
export const ROLE_LABELS: Record<Role, string> = {
  admin: "Admin", hod: "Department Head", teacher: "Teacher", student: "Student",
};
export const NAV: { group: string; items: { label: string; path: string; roles: Role[] }[] }[] = [
  { group: "Overview", items: [{ label: "Dashboard", path: "/dashboard", roles: ["admin","hod"] }] },
  { group: "Scheduling", items: [
    { label: "Generation", path: "/generate", roles: ["admin","hod"] },
    { label: "Instances", path: "/instances", roles: ["admin","hod"] },
    { label: "Assignments", path: "/assignments", roles: ["admin","hod"] },
  ]},
  { group: "Resources", items: [
    { label: "Rooms", path: "/rooms", roles: ["admin","hod"] },
    { label: "Faculty", path: "/faculty", roles: ["admin","hod"] },
    { label: "Groups", path: "/groups", roles: ["admin","hod"] },
    { label: "Subjects", path: "/subjects", roles: ["admin","hod"] },
  ]},
  { group: "Configuration", items: [
    { label: "Profiles", path: "/profiles", roles: ["admin","hod"] },
    { label: "Constraints", path: "/constraints", roles: ["admin"] },
    { label: "Settings", path: "/settings", roles: ["admin"] },
    { label: "Users", path: "/users", roles: ["admin"] },
  ]},
  { group: "Output", items: [{ label: "Exports", path: "/exports", roles: ["admin","hod","teacher","student"] }] },
  { group: "My space", items: [
    { label: "My Schedule", path: "/my-schedule", roles: ["teacher"] },
    { label: "My Timetable", path: "/my-timetable", roles: ["student"] },
  ]},
];
export const navFor = (role: Role) =>
  NAV.map(g => ({ ...g, items: g.items.filter(i => i.roles.includes(role)) }))
     .filter(g => g.items.length > 0);
```

Teacher `/my-schedule`: `useInstanceSlots` for the latest PUBLISHED instance
filtered to that faculty (backend: `GET /instances/{id}/slots?faculty_id=`
or a `/my-schedule` backend endpoint returning the caller's published slots —
**confirm the endpoint; add if missing**). Student `/my-timetable` analogous by
group.

---

## 12. Build order (phases)

Each phase ends demoable; commit per phase (repo standing rules).

| Phase | Deliverables | Demoable end-state |
|---|---|---|
| 1 | Deps install; design tokens; `ui/` kit; sidebar shell + role nav; DataTable/TanStack + FilterBar + ResourceFormDrawer + CsvImportModal; rebuild /login, /dashboard (Recharts), /rooms, /faculty, /groups, /subjects; skeletons/empty/error/toasts everywhere | The same five screens, rebuilt — a before/after that reads "product" |
| 2 | `TimetableGrid` + `/generate` + `/instances` + `/instances/[id]` + `/exports` | Trigger a real generation in the UI and browse the timetable grid with legend + exports — no curl |
| 3 | `/profiles`, `/profiles/[id]`, `/constraints`, `/assignments` | Build a profile + assignment matrix without JSON |
| 4 | `/instances/compare` + slot override + revalidation | Fix a placement in the grid, revalidate, republish, diff to a peer |
| 5 | `/my-schedule`, `/my-timetable`, `/users`, `/settings` | Teacher/student scoped logins; admin user/flag management |

---

## 13. Verification loop (mandatory per page)

1. Backend running on :8000, seeded (`uv run python -m scripts.seed_demo --wipe`).
2. Frontend dev on :3001 (`npm run dev -- -p 3001`).
3. `node scripts/screenshot.mjs` captures every page (real login).
4. Vision review (`vision-opencode-go-qwen3.8-max` or the saved default) checks
   each screenshot; fix flagged issues; re-shoot.
5. `npm run build` type-checks; backend suite stays green.

---

## 14. Backend endpoints to confirm/add during phases

- `POST /api/v1/instances/{id}/slots/{slotId}/revalidate` — wrap
  `_revalidate_slot` for the slot-override UI (phase 4). Not public today.
- Teacher/student "my schedule": either filter `GET /instances/{id}/slots` by
  caller identity server-side (RBAC read-scoping, DD-021 follow-up) or a
  dedicated `GET /my/schedule`. Confirm existing endpoints in
  `app/router/instances.py` first.
- CSV export for resource lists (`/export` exists for instances only) — add
  if the Exports hub needs resource-level CSV (phase 2/5).
