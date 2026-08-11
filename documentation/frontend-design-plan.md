# Frontend Design Plan (qwen3.8-max)

> **The complete, verbatim design plan produced by qwen3.8-max over the current
> screenshots. This is the product strategy — do not replace it.** Library
> integration and implementation notes requested by the user are appended in
> the section at the bottom, merged in — not substituted.

## Current state critique

**What's working:**
- Consistent editorial identity: serif display headings ('Overview', 'Rooms', 'Groups') on a warm gray canvas with white cards is a genuine differentiator versus generic admin dashboards.
- A repeatable resource-page pattern (serif title + 'N records' + summary chip row + filter card + table + single black CTA) makes Rooms/Faculty/Groups/Subjects instantly learnable.
- Badge vocabulary already differentiates entities: light-blue pills for CLASSROOM/DIVISION, purple 'Lab' pill, gray department pills, and initial avatars on faculty rows.
- Clear action hierarchy: one near-black primary button per page ('+ Add room') and consistent Edit/Delete row actions.
- Dashboard leads with real data (200 rooms / 200 faculty / 192 groups / 200 subjects) and breakdown bars, and the topbar identity block ('admin / ADMIN') is a seed for role-aware UI.

**What's weak:**
- Unstyled native controls read as prototype-grade: default OS `<select>` in the rooms filter and Add-room modal, and native checkboxes stacked centered above their labels inside the modal.
- No brand accent exists: primary buttons, active nav pill, and all chart bars are near-black/gray, so nothing guides the eye and the dashboard bar charts are monochrome with no legend or color meaning.
- Top navigation holds only 5 links and already fills the bar; there is no home for Generation, Instances, Profiles, Constraints, Assignments, Exports, Settings or Users, so the IA cannot scale to the real product.
- Data tables are thin relative to the backend: no search, no column sorting, no visible pagination despite '25 records' and X-Total-Count paging API, no CSV import/export UI, no row hover/zebra, and tall ~52px rows waste vertical space.
- States are missing: 'Recent generation runs' empty state is a bare 'No runs yet.' text line; no skeletons, no error banners, no field-level validation beyond red asterisks; login is a barren centered card on an empty canvas.
- Dashboard cards have large dead zones (the 'Rooms by type' card is half empty below three bars) and stat cards carry no icon, trend or link, so the page informs but never directs.
- The Add-room modal layout is unbalanced: centered checkbox group, centered Cancel/Save buttons, and a 2-column grid that collapses awkwardly.

**Verdict:** Keep the editorial-light soul (paper canvas + serif display) because it is the product's only differentiator, but the execution is wireframe-grade: native form controls, a grayscale palette with no accent, missing empty/loading/error states, a 5-item top nav that cannot scale, and the complete absence of the scheduling screens (grid viewer, generation, profiles). Rebuild the body around the existing soul: design tokens with one confident accent, a styled component kit, sidebar IA, dense server-driven tables, and the missing timetable centerpiece.

## Design language

- **Keep editorial-light**: yes.
- **Typography**: display = Fraunces (Google Fonts, opsz 9-144, weights 500/600), fallback Georgia/Times New Roman serif; body = Inter (400/500/600), fallback system sans; mono = JetBrains Mono (500) for codes, slot labels, times.
- **Size scale**: 12px captions/eyebrows/table headers · 13px table body · 14px UI base · 16px lead · 20px card titles (serif) · 28px page titles (serif) · 36px stat numerals · 44px login/display (serif).
- **Colors**: canvas `#F5F3EF` · surface `#FFFFFF` · ink `#1C1917` · inkSoft `#57534E` · accent `#4338CA` (hover `#3730A3`) · success `#15803D` · danger `#B91C1C` · warning `#B45309` · info `#0369A1` · chart `["#4338CA","#0E7490","#15803D","#B45309","#C2410C","#BE185D","#6D28D9","#64748B"]`.
- **Radius/shadow**: 6px inputs/buttons/badges · 10px cards/tables · 14px modals/drawers · 999px pills/avatars. Shadows: sm `0 1px 2px rgba(28,25,23,0.06)`, md `0 4px 12px rgba(28,25,23,0.08)`, lg `0 16px 40px rgba(28,25,23,0.16)`.
- **States**: hover = row bg `#F5F3EF` / cards shadow-sm→md / nav accent tint `rgba(67,56,202,0.08)`; focus = 2px ring `rgba(67,56,202,0.35)` + border accent; disabled = opacity .45; empty = 40px icon in `#EEF2FF` circle + serif title + one action; loading = layout-mirroring skeletons (stone-200, animate-pulse); error = `#FEF2F2` banner + `#FECACA` border + Retry, field errors 12px `#B91C1C`.

## Information architecture & navigation

- **Nav model**: sidebar (240px, 68px icon rail below 1024px).
- **Groups**: Overview (Dashboard) · Scheduling (Generation, Instances, Assignments) · Resources (Rooms, Faculty, Groups, Subjects) · Configuration (Profiles, Constraints, Settings, Users) · Output (Exports) · My space (My Schedule teacher / My Timetable student).
- **Role navs**: admin = everything; hod = no Constraints/Settings/Users; teacher = My Schedule + Exports; student = My Timetable + Exports.

## Page-by-page design

1. `/login` — split screen: left 45% ink brand panel (paper serif wordmark, one-line promise, faint 6×4 slot-grid motif in accent tint); right centered 400px form card. Loading = spinner + disabled inputs; 401 = ErrorBanner; role-based redirect (admin/hod→/dashboard, teacher→/my-schedule, student→/my-timetable); optional 'Use demo account' chip.
2. `/dashboard` — 12-col grid: 4 StatCards (icon + link + optional delta); 3 colored ChartCards (Recharts); bottom row RunsList (8 cols) + QuickActions (4 cols). Zero-run state = 3-step setup checklist card. Skeleton stat cards/chart bars. Error banner with Retry. HOD variant scopes to department.
3. `/rooms` — Header + Toolbar (search, type select, CSV import, CSV export, Add) + DataTable + Pagination. Same shell reused for faculty/groups/subjects. Filtered-empty 'No rooms match' + Clear filters; true-empty 'Add your first room' + Import CSV. Edit opens a right-side drawer with styled select + amenity switches. Delete = ConfirmDialog + undo toast.
4. `/faculty` — Avatar column (deterministic hue), styled department Select filter, hours columns. Row click opens drawer in edit mode.
5. `/groups` — type/dept/sem filters (combined → one server query), type badge, strength right-aligned mono numerals.
6. `/subjects` — dept select, sem select, lab toggle; code in mono; Lab purple pill; requires_lab switch in drawer.
7. `/assignments` (NEW) — matrix: rows = subjects grouped by semester, columns = groups; cell = faculty avatar + weekly-hours chip; CellPopover to assign/edit; coverage chips; unsaved-changes bar; auto-suggest bulk fill.
8. `/profiles` (NEW) — card grid: name, scope, resource counts, constraint count, last-run status pill; duplicate/archive menu.
9. `/profiles/[id]` (NEW) — header inline-editable name + Tabs (Resources | Parameters | Constraints | Runs) + shuttle pickers + param fields by type + constraint rows with switch + soft weight slider + DirtyBar + dry-run check.
10. `/constraints` (NEW) — reference catalog table: name, HARD/SOFT badge, description, parameter schema; 'Configure in profile' jump.
11. `/generate` (NEW) — two panes: left form (profile picker + coverage preview, solver radio, instance count stepper, background switch, time limit); right live Runs list. Submit spinner; async polls 2s; 422 form banner; FAILED card surfaces error_log; completion toast deep-links to instances.
12. `/instances` (NEW) — table: id, run, score bar, hard-violations, lifecycle pill (DRAFT/SELECTED/PUBLISHED/ARCHIVED), actions View/Compare/Export/Select/Publish. Compare after two selections; publish confirm notes archiving.
13. `/instances/[id]` (NEW) — header + perspective Select (Group/Faculty/Room) + TimetableGrid + right rail (violations + legend) + export menu + slot override popover (edit mode only).
14. `/instances/compare` (NEW) — summary bar (score/violation/moved deltas) + two synced grids + DiffList with click-to-scroll.
15. `/exports` (NEW) — left builder (scope + format cards PDF/CSV/iCal + iCal week range); right download history.
16. `/settings` (NEW) — section cards: institution info, feature flags (Switch), tunables (typed key/value), danger zone.
17. `/users` (NEW) — table + Invite; role change, deactivate; invite gated by SMTP flag.
18. `/my-schedule` (teacher, NEW) — header + Today card + TimetableGrid (faculty perspective, read-only) + export iCal/PDF. Empty = 'not published yet' + contact-admin link.
19. `/my-timetable` (student, NEW) — header + TimetableGrid (group perspective, read-only) + legend + exports.

## Component system

AppShell (sidebar+topbar) · DataTable (server-driven, 44px rows, sticky header) · FilterBar (search + styled selects + clear) · Field kit (TextInput, Select, Switch, NumberStepper, Checkbox) · ResourceFormDrawer (right 440px) · Badge/StatusPill (token-driven tones) · StatCard (icon + link + delta) · HBarChart (colored, legend) · EmptyState · Skeletons (table/card/grid) · ErrorBanner/toast (Sonner) · ConfirmDialog · CsvImportModal · TimetableGrid · SlotPopover · Tabs · Avatar (deterministic hue).

## Key user journeys

1. **Admin: profile → published timetable** — sign in → new profile (shuttle resources, set params, toggle constraints + soft weights) → fix assignment coverage → generate (OR-Tools, 3 instances, background) → poll to COMPLETED → compare two → select winner → publish (confirm archives previous) → export PDF per group + iCal per faculty.
2. **Teacher: weekly schedule → iCal** — sign in → /my-schedule (faculty perspective grid, Today card) → click cell (read-only detail) → compact density → export iCal (room as location). Empty = 'not published yet' + contact link.

## Timetable grid (centerpiece)

- **Rendering**: pure CSS grid in overflow-x container: `grid-template-columns 64px repeat(days, minmax(150px,1fr))`; 36px sticky day header + sticky slot gutter with mono times; sessions placed by gridColumn/gridRow with row spans; free cells faint dashed only in edit mode.
- **Cell content**: line 1 subject code (mono, colored by subject hue) + flask icon when lab; line 2 subject name; line 3 faculty avatar + name + room code mono; group chip when perspective ≠ group; warning triangle + 2px danger ring for issues.
- **Color coding**: deterministic hash of subjectId into the 8-color palette; cell bg = hue at 8% over white, 3px solid left border in hue, code text at 700-level hue; legend chips above; same mapping in compare, exports, teacher/student views.
- **Density**: Comfortable 64px rows / Compact 44px (code only), persisted.
- **Blocks**: sessions carry start_slot + duration; labs span rows with '2h LAB' tag; lunch = separator row, not a slot.
- **Compare**: `/instances/compare?a=&b=`; two grids synced scroll + identical color map; only-one accent dashed outline; changed = warning ring; DiffList of moves with click-to-scroll; deltas summary.
- **Slot override**: edit mode only (DRAFT/SELECTED); click cell → popover (day/slot/room/faculty); debounced revalidate; Save disabled until clean; optimistic commit + Undo toast; PUBLISHED view-only with banner.
- **Navigation**: perspective select re-pivots; prev/next instance arrows; keyboard arrows move focus, Enter opens popover; 'today' column tinted on /my-schedule.

## Build order (5 phases, each demoable)

1. **Design system + shell + existing pages** — /login, /dashboard, /rooms, /faculty, /groups, /subjects rebuilt (sidebar IA, tokens, styled selects, dense sortable/paginated tables, colored charts, real states). A before/after that reads 'product'.
2. **Scheduling core (read path)** — /generate, /instances, /instances/[id] (grid), /exports. First end-to-end demo without curl.
3. **Configuration surfaces** — /profiles, /profiles/[id], /constraints, /assignments.
4. **Editing & comparison** — /instances/compare + slot override.
5. **Roles & administration** — /my-schedule, /my-timetable, /users, /settings.

## Top priorities

1. Build the TimetableGrid + instance viewer (/instances/[id]) — the money screen, currently absent.
2. One design-system pass over the existing five pages (styled controls, accent, sidebar, dense tables, real states) — this alone removes the 'not professional' impression.
3. Wire the generation loop UI (generate → instances → publish) for a curl-free end-to-end demo.
4. Role-scoped teacher/student views for the other buyer personas.

---

# ═══════════════════════════════════════════════════════════
# LIBRARY INTEGRATION & IMPLEMENTATION NOTES (user additions — MERGED IN)
# ═══════════════════════════════════════════════════════════

These are the implementation-level requirements added by the user on top of
the qwen strategy above. They refine HOW each piece is built on the
Next.js 14 (App Router) + Tailwind CSS 3.4 stack. The design intent above is
unchanged; this section is the build contract.

## 1. UI library & primitives

- **shadcn/ui (Radix primitives)** for ALL form controls, modals, popovers,
  select dropdowns, hover cards, command menus — replacing native HTML
  inputs. Hand-authored into `frontend/src/components/ui/` following the
  shadcn convention (CVA + `cn()` = `clsx` + `tailwind-merge`), NOT pulled via
  `npx shadcn init`, so the repo stays self-contained and the theme stays
  custom. Radix packages: dialog, dropdown-menu, popover, select, slot,
  switch, tabs, avatar, tooltip, separator, checkbox, command.
- **lucide-react** for all icons (Plus, Search, Download, Upload, Pencil,
  Trash2, Play, Check, X, ChevronDown, CalendarDays, Users, GraduationCap,
  DoorOpen, FileDown, AlertTriangle, Loader2, Undo2, ...).

## 2. Data handling & tables

- **TanStack Table v8 (`@tanstack/react-table`)** for all resource list views
  (Rooms, Faculty, Groups, Subjects) and every future list. Server-side
  pagination via `X-Total-Count` (manualPagination, pageCount from total);
  multi-column sorting (manualSorting, state in query params); column search
  filters via the FilterBar.
- **TanStack Query (`@tanstack/react-query`)** for all state management:
  queries per list, `refetchInterval` 2s for generation status polling, and
  optimistic updates for manual slot overrides (onMutate snapshot + rollback
  onError + invalidate onSettled). Provider in a client `Providers` wrapper
  mounted in `layout.tsx`.

## 3. Analytics & feedback

- **Recharts** for dashboard charts: custom tooltip component, responsive
  containers (`ResponsiveContainer`), the 8-color chart palette from the
  design tokens, rounded bars.
- **Sonner** for toasts: publish confirmations, undo actions (deletes, slot
  overrides), override error feedback, generation-complete deep links.
  `Toaster` mounted once in `Providers`.

## 4. TimetableGrid technical implementation

- **Component hierarchy**: `TimetableViewer` → `TimetableGrid` →
  { `GridToolbar`, `GridHeaderRow`, `GridGutter`, `GridBody` → `GridCell` →
  `SlotPopover` (edit mode) } + `ViolationsPanel`.
- **Normalization**: map flat backend `Slot[]` → `GridSession[]`
  (subjectId/facultyId/roomId/groupId, day, startSlot, duration, sessionType,
  warnings) joined with subject/faculty/room/group lookups.
- **CSS Grid layout**: `grid-template-columns: 64px repeat(days, minmax(150px,1fr))`
  and `grid-template-rows: 36px repeat(slotCount, 64|44px)`; sticky day
  header and sticky slot-time gutter; 8 slots × 6 days = 48 cells, no
  virtualization.
- **Row-spanning for labs**: a session with `duration > 1` uses
  `gridRow: start / span duration`, visually merging consecutive slot tracks;
  a `Map<day, Map<slot, GridSession>>` prevents empty cells from overwriting
  spanned rows. Lunch renders as a separator row, not a slot.
- **Popover override + revalidation**: Radix Popover anchored to the clicked
  cell; day/slot/room/faculty selects; a debounced revalidate query shows
  "No conflicts" (green) or the violation list (danger); Save stays disabled
  until clean; commit runs the optimistic `useSlotOverride` mutation + Undo
  toast. Backend needs `POST /api/v1/instances/{id}/slots/{slotId}/revalidate`
  (wrap `_revalidate_slot`) — confirm in `app/router/instances.py` before
  phase 4. PUBLISHED instances are `readOnly` with a banner.

## 5. Build contract mapping (phases)

| Phase | Deliverables | Demoable end-state |
|---|---|---|
| 1 | Deps; tokens; `ui/` kit; sidebar shell + role nav; TanStack DataTable + FilterBar + ResourceFormDrawer + CsvImportModal; rebuild /login, /dashboard (Recharts), /rooms, /faculty, /groups, /subjects; skeletons/empty/error/toasts | Same five screens rebuilt — reads 'product' |
| 2 | `TimetableGrid` + /generate + /instances + /instances/[id] + /exports | Real generation in the UI, browse the grid, no curl |
| 3 | /profiles, /profiles/[id], /constraints, /assignments | Profile + assignment matrix without JSON |
| 4 | /instances/compare + slot override + revalidation | Fix a placement, revalidate, republish, diff |
| 5 | /my-schedule, /my-timetable, /users, /settings | Teacher/student scoped logins; admin user/flag mgmt |

> **Shipped so far:** Phases 1, 2, 4 (compare + slot override + revalidation), and Phase 3's
> `/assignments` grid. Remaining Phase 3 items: `/profiles`, `/profiles/[id]`, `/constraints`.
> Phase 5 (role-scoped views + users/settings) is the final push.

## 6. Verification loop (per page)

Backend :8000 seeded · frontend dev :3001 · `node scripts/screenshot.mjs`
captures each page · vision review (qwen3.8-max or saved default) checks each
screenshot · fix flagged issues · re-shoot · `npm run build` type-checks ·
backend suite stays green.

## 7. Backend endpoints to confirm/add

- `POST /api/v1/instances/{id}/slots/{slotId}/revalidate` (phase 4).
- Teacher/student "my schedule": either server-side caller scoping on
  `GET /instances/{id}/slots` (RBAC read-scoping, DD-021 follow-up) or a
  dedicated `GET /my/schedule`; confirm `app/router/instances.py` first.
- Resource-level CSV export for the Exports hub if needed (phases 2/5).
