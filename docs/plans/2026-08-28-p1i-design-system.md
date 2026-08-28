# P1i — Design System & App Shell — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Frontend-heavy — gates are `pnpm --filter web build` (typecheck) + `pnpm --filter web test` (unchanged api-client tests) + a browser check per page. Steps use `- [ ]` checkboxes.

**Goal:** Turn the plain functional web pages into a modern, professional, dark FPL-analytics UI — a design-token system, a component kit (shadcn-style, hand-written, SAC-safe), a responsive app shell with a sidebar, shared feature components + charts, a real landing page, and a restyle of all 8 existing pages. Same *genre* as wassupfpl.com; FPLGuru's own identity.

**Architecture:** Tailwind v4 `@theme` tokens in `globals.css` (dark-first, with a light override). Hand-written primitives in `apps/web/src/components/ui/` (Button, Card, Badge, Table, Tabs, Input, Select, Skeleton, Separator, Tooltip, DropdownMenu, Sheet) built on Radix primitives + `cva` + `cn()`. `recharts` for charts (pure SVG, no native deps). `AppShell` (sidebar + topbar, responsive) replaces the `<nav>` in `layout.tsx`. Shared feature components (`PageHeader`, `StatTile`, `DataTable`, `EmptyState`, `Chart`) in `src/components/`. No API/backend changes.

**Tech Stack:** Next 16 / React 19 / Tailwind v4 (already set up), Radix UI, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `next-themes`, `recharts`, `tw-animate-css`. All pure JS — nothing SAC would block.

---

## Project context (read once)

- Monorepo `D:\AntiGravity\FPLGuru`; web app at `apps/web` (pnpm workspace). Branch: **`feature/p1i-design-system`** off `main`.
- Current web: Tailwind v4 (`@import "tailwindcss"` + `@theme inline` in `src/app/globals.css`; PostCSS via `@tailwindcss/postcss`; **no `tailwind.config`**). `src/app/*` pages + `src/lib/*` (api clients, `entry.ts`, `prefs.ts`, `push.ts`). Nav is a `<nav>` in `src/app/layout.tsx`. Pages: `/` (link form), `/squad`, `/fdr`, `/live`, `/alerts`, `/leagues` + `/leagues/[id]`, `/tools`, `/captain`. Each is a server `page.tsx` rendering a `"use client"` child.
- `NEXT_PUBLIC_API_BASE` default `http://localhost:8000`. API has CORS `*` (added). To view: API on :8000 (`python -m uvicorn fplguru_api.main:app --port 8000`), web on :3000 (`pnpm --filter web dev` from `apps/web` or `./node_modules/.bin/next dev`). DB is populated (20 teams / 616 players / 380 fixtures / 2465 predictions).
- Web checks from `apps/web`: `./node_modules/.bin/next build` (typecheck + prod build), `./node_modules/.bin/vitest run` (10 files / 19 tests — **must stay green**; they only test `src/lib/api*.test.ts`).
- Commits: `git add -A -- ':!docs'` for code tasks. Author `Anil Kujur <anilkuj@gmail.com>` + `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`. Do not push except the PR.
- Verify each restyled page in the in-app browser (`navigate` + `get_page_text` / screenshot) against the running servers.

---

## Design tokens (the identity)

Dark-first. FPLGuru palette: **deep navy/ink** surfaces, **electric violet** primary, **spring green** positive accent, amber/red for warnings. Define as CSS vars on `:root` (dark values) + a `:root.light` / `[data-theme="light"]` override.

| Token | Dark value | Use |
|---|---|---|
| `--bg` | `#0b0e14` | app background |
| `--surface` | `#12161f` | cards, sidebar |
| `--surface-2` | `#1a1f2b` | raised / hover |
| `--border` | `#232a37` | hairlines |
| `--fg` | `#e7ebf3` | primary text |
| `--fg-muted` | `#9aa4b6` | secondary text |
| `--primary` | `#7c5cff` | brand, active nav, primary buttons |
| `--primary-fg` | `#ffffff` | on primary |
| `--positive` | `#37e0a0` | ▲ deltas, good FDR |
| `--warning` | `#f5b849` | doubtful, BGW |
| `--danger` | `#ff5c72` | ▼ deltas, injuries, hard FDR |
| `--ring` | `#7c5cff` | focus ring |
| radius | `--radius: 0.75rem` | cards; `calc(var(--radius) - 4px)` for controls |
| FDR ramp | `#1f8a53 → #3fae5f → #d8a13a → #e07f3a → #d0445a` | difficulty 1→5 cells |
| chart series | `--primary`, `--positive`, `#5cc8ff`, `--warning` | recharts |

Light override flips `--bg/#f7f8fb`, `--surface/#ffffff`, `--fg/#141821`, keeps `--primary`.

Font: keep Geist (already wired via `next/font`); set `--font-sans` to it; tighten headings (`font-semibold tracking-tight`).

---

## Task 1: tokens + deps + `cn()`

**Files:** `apps/web/package.json`, `apps/web/src/app/globals.css`, `apps/web/src/lib/utils.ts` (new), `apps/web/src/app/layout.tsx`.

- [ ] **Step 1: deps** — add to `apps/web/package.json` `dependencies` and `pnpm --filter web install`:
  `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `next-themes`, `recharts`,
  `@radix-ui/react-slot`, `@radix-ui/react-tabs`, `@radix-ui/react-select`,
  `@radix-ui/react-dropdown-menu`, `@radix-ui/react-tooltip`, `@radix-ui/react-separator`,
  `@radix-ui/react-dialog` (for the mobile Sheet); devDep `tw-animate-css`.

- [ ] **Step 2: `src/lib/utils.ts`**
```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 3: `src/app/globals.css`** — replace the whole file:
```css
@import "tailwindcss";
@import "tw-animate-css";

@custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));

:root {
  --bg: #0b0e14; --surface: #12161f; --surface-2: #1a1f2b; --border: #232a37;
  --fg: #e7ebf3; --fg-muted: #9aa4b6;
  --primary: #7c5cff; --primary-fg: #ffffff;
  --positive: #37e0a0; --warning: #f5b849; --danger: #ff5c72; --ring: #7c5cff;
  --radius: 0.75rem;
}
[data-theme="light"] {
  --bg: #f7f8fb; --surface: #ffffff; --surface-2: #f0f2f7; --border: #e4e7ee;
  --fg: #141821; --fg-muted: #5b6472;
}

@theme inline {
  --color-bg: var(--bg);
  --color-surface: var(--surface);
  --color-surface-2: var(--surface-2);
  --color-border: var(--border);
  --color-fg: var(--fg);
  --color-fg-muted: var(--fg-muted);
  --color-primary: var(--primary);
  --color-primary-fg: var(--primary-fg);
  --color-positive: var(--positive);
  --color-warning: var(--warning);
  --color-danger: var(--danger);
  --color-ring: var(--ring);
  --radius-lg: var(--radius);
  --radius-md: calc(var(--radius) - 4px);
  --radius-sm: calc(var(--radius) - 8px);
  --font-sans: var(--font-geist-sans);
}

* { border-color: var(--color-border); }
body {
  background: var(--color-bg);
  color: var(--color-fg);
  font-family: var(--font-sans), ui-sans-serif, system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
}
::selection { background: color-mix(in oklab, var(--primary) 30%, transparent); }
```

- [ ] **Step 4: `layout.tsx`** — keep the `Geist` font wiring; set `<html data-theme="dark" suppressHydrationWarning>`; body classes `min-h-dvh bg-bg text-fg`; render `<AppShell>{children}</AppShell>` (Task 3) instead of the `<nav>`; drop the inline `<nav>`, keep `metadata` + `viewport` (bump `themeColor` to `#0b0e14`). Import `NavAlerts` / `PwaSetup` usage moves into `AppShell`.

- [ ] **Step 5:** `./node_modules/.bin/next build` → success. Commit `feat(web): design tokens + deps + cn()`.

---

## Task 2: UI primitives (`src/components/ui/`)

Hand-write shadcn-style components (new-york flavour) — each a small file. Use `cn()`, `cva` for variants, Radix for behavior. Colours reference the tokens (`bg-surface`, `text-fg`, `border-border`, `bg-primary text-primary-fg`, `ring-ring`).

**Files (create each):** `button.tsx`, `card.tsx` (`Card/CardHeader/CardTitle/CardDescription/CardContent/CardFooter`), `badge.tsx` (`variant`: default/positive/warning/danger/outline), `table.tsx` (`Table/TableHeader/TableBody/TableRow/TableHead/TableCell` — sticky header, `hover:bg-surface-2`, zebra optional), `tabs.tsx` (Radix), `input.tsx`, `select.tsx` (Radix, styled), `skeleton.tsx` (`animate-pulse rounded-md bg-surface-2`), `separator.tsx` (Radix), `tooltip.tsx` (Radix), `dropdown-menu.tsx` (Radix), `sheet.tsx` (Radix Dialog — slide-in drawer for mobile nav), `scroll-area.tsx` (optional).

- [ ] **Step 1:** write all of the above with the standard shadcn implementations, swapping the default `bg-background/text-foreground/border-input` classes for FPLGuru tokens (`bg-bg`, `bg-surface`, `text-fg`, `text-fg-muted`, `border-border`, `focus-visible:ring-2 focus-visible:ring-ring`). `Button` variants: `default` (bg-primary), `secondary` (bg-surface-2), `outline` (border), `ghost`, `destructive` (bg-danger), `link`; sizes `sm/default/lg/icon`.
- [ ] **Step 2:** a barrel `src/components/ui/index.ts` re-exporting all.
- [ ] **Step 3:** `next build` → success (no page uses them yet — just compile). Commit `feat(web): UI primitive components`.

---

## Task 3: App shell (sidebar + topbar, responsive)

**Files:** `src/components/AppShell.tsx` (client), `src/components/ThemeToggle.tsx`, `src/components/nav-items.ts`; modify `layout.tsx` (done in Task 1 Step 4), delete `src/app/NavAlerts.tsx`'s standalone use (fold into shell) — keep the file but the shell renders the badge.

- [ ] **Step 1: `nav-items.ts`** — array of `{ href, label, icon }` (lucide): `/` Home, `/squad` Squad (Users), `/fdr` Fixtures (CalendarRange), `/live` Live (Radio), `/tools` Tools (Wrench), `/leagues` Leagues (Trophy), `/captain` Captain (Crown), `/alerts` Alerts (Bell).
- [ ] **Step 2: `AppShell.tsx`**
  - Desktop (`md+`): fixed left sidebar `w-60`, `bg-surface border-r`, logo block at top (`FPLGuru` wordmark, violet dot), nav list (`usePathname()` → active item gets `bg-primary/10 text-fg` + a left accent bar; others `text-fg-muted hover:text-fg hover:bg-surface-2`), Alerts item shows the unseen-count badge (reuse `getAlerts` + `getStoredEntryId`, poll 60s), footer with `ThemeToggle` + PWA install button.
  - Mobile (`<md`): sidebar hidden; a `Sheet` opened by a hamburger `Button` in the topbar.
  - Topbar (all sizes): `h-14 border-b bg-bg/80 backdrop-blur sticky top-0 z-20`, left = hamburger (mobile) + current page label (derive from pathname/nav-items), right = a small "Team #<id>" pill if `getStoredEntryId()` set (links to `/squad`) else a "Link team" `Button` linking `/`.
  - Content: `<main className="mx-auto w-full max-w-6xl px-4 py-6 md:px-8">{children}</main>`, sidebar offset via `md:pl-60`.
- [ ] **Step 3: `ThemeToggle.tsx`** — `next-themes` `useTheme`; a `Button size="icon" variant="ghost"` toggling `dark`/`light` (Sun/Moon lucide). Wrap the app in `<ThemeProvider attribute="data-theme" defaultTheme="dark">` — add a `providers.tsx` client component and render it in `layout.tsx` around `AppShell`.
- [ ] **Step 4:** `next build` → success. `vitest run` → still 19 passed. Browser: load `/` — shell renders, nav active states work, mobile drawer opens, theme toggles. Commit `feat(web): responsive app shell (sidebar + topbar + theme toggle)`.

---

## Task 4: shared feature components

**Files:** `src/components/PageHeader.tsx`, `StatTile.tsx`, `DataTable.tsx`, `EmptyState.tsx`, `Delta.tsx`, `Chart.tsx`.

- [ ] `PageHeader` — `{title, description?, actions?}` → `<h1 className="text-2xl font-semibold tracking-tight">` + muted description + right-aligned `actions` slot.
- [ ] `StatTile` — `{label, value, delta?, hint?}` in a `Card` — big `text-2xl font-semibold` value, muted label, `<Delta>` chip.
- [ ] `Delta` — `{value: number|null, invert?}` → `▲ n` (positive) / `▼ n` (danger) / `–` (muted), `invert` for rank (down = good).
- [ ] `DataTable<T>` — `{columns: {key, header, align?, sortable?, render?}[], rows, initialSort?}` — client sort on sortable columns (click header, ▲/▼ indicator), sticky header, `Table` primitives, `EmptyState` when `rows.length === 0`.
- [ ] `EmptyState` — `{icon?, title, hint?}` centered muted block.
- [ ] `Chart` — thin wrappers: `LineChartMini` (rank history — `recharts` `ResponsiveContainer`+`LineChart`, no axes, token stroke), `BarsMini` (FDR/xG). Theme colours via CSS vars passed as `stroke`/`fill` (`"var(--primary)"`).
- [ ] `next build` → success. Commit `feat(web): shared feature components (PageHeader/StatTile/DataTable/Chart)`.

---

## Task 5: landing page (`/`)

**Files:** `src/app/page.tsx`, `src/app/LinkTeamCard.tsx` (rework of the existing link form).

- [ ] Hero: headline ("Your FPL edge, in one place"), sub, primary CTA scrolls to / focuses the link-team card; secondary "Explore tools" → `/tools`.
- [ ] `LinkTeamCard` — `Card` with an `Input` for team ID + `Button`; on submit `setStoredEntryId` + `router.push("/squad")`; shows the current linked id if set with an "unlink" ghost button.
- [ ] Feature grid: 6 `Card`s (Fixtures / GW Live / Smart Alerts / AI Captain / Leaderboard / Free Tools) each with a lucide icon, one-line description, and a `Link` to the page. Style like wassupfpl's stacked feature cards but in a responsive `grid sm:grid-cols-2 lg:grid-cols-3`.
- [ ] A slim "what's inside" strip: small `StatTile`-ish counts if cheap (e.g. "20 teams · 616 players tracked") — optional, skip if it needs new API.
- [ ] `next build` + browser check. Commit `feat(web): landing page`.

---

## Task 6: restyle `/fdr`

- [ ] `FdrGrid.tsx` → `PageHeader` ("Fixture difficulty", description) with a horizon `Select` in `actions`. Body: a `Card` wrapping a horizontal-scroll table; team column sticky; each GW cell is a rounded chip `bg-[color]` from the FDR ramp (map `band` 1–5 → the 5 ramp colours, text auto-contrast) showing `OPP (H/A)`; `avg_fdr` column with a tiny `BarsMini`. `Skeleton` rows while loading; `EmptyState` if no data. Keep `getPref/setPref` horizon persistence.
- [ ] Browser check vs live data (MCI easiest). Commit `feat(web): restyle FDR`.

---

## Task 7: restyle `/tools`

- [ ] `ToolsHub.tsx` → `PageHeader` + shadcn `Tabs` (`Trends / Template / Calendar / Overpowered XI / xG`). Each panel in a `Card`:
  - **Trends**: 5 `Card`s in a grid, each a titled list of `web_name` + value `Badge`.
  - **Template**: formation badge + a position-grouped list; ownership as a muted right value.
  - **Calendar**: GW-range `Input`s; a `DataTable` (GW / DGW teams / BGW teams) with `Badge` chips.
  - **Overpowered XI**: formation + total-xP header; players as a `DataTable` (Pos / Player / xP), grouped visually by position.
  - **xG**: position `Select` + `DataTable` (Player / Pos / xG / xA / min), sortable; `EmptyState` "Add a PitchAPI key to populate".
- [ ] Browser check (Trends has real data). Commit `feat(web): restyle Tools`.

---

## Task 8: restyle `/live`

- [ ] `LiveBoard.tsx` → `PageHeader` ("GW Live") with a live dot + "updated …" in `actions`; "My players" toggle as a `Button variant={mineOnly?"default":"outline"} size="sm"`. Fixtures as a row of `Card`/`Badge` score chips (show `min'` / `FT`). Players as a `DataTable` (Player / Pos / Min / Pts / Bonus / BPS / Total) sortable, Total emphasised. Keep SSE + 15s fallback. `EmptyState` when no active GW.
- [ ] Commit `feat(web): restyle Live`.

---

## Task 9: restyle `/alerts`

- [ ] `AlertFeed.tsx` → `PageHeader` ("Alerts") with "Mark all read" `Button` in `actions`. Controls (`alert_cap`, reminder-offset presets + free text) inside a `Card` ("Settings"), presets as toggle `Button`s. Feed items as `Card`s with a left accent bar colour by `type` (availability=danger, bgw=warning, dgw=positive, deadline=primary), a lucide icon, title + body, priority as a muted `Badge`, `seen` → `opacity-60`. `PushToggle` becomes a `Button` in the header. `EmptyState` when empty.
- [ ] Commit `feat(web): restyle Alerts`.

---

## Task 10: restyle `/leagues` + `/leagues/[id]`

- [ ] `LeagueList.tsx` → `PageHeader` ("Leagues"); a "Overall rank trend" `Card` with `LineChartMini` (invert Y — lower rank higher); mini-leagues as `Card`s (name link, current rank big, `<Delta invert>` weekly) in a responsive grid.
- [ ] `StandingsView.tsx` → `PageHeader` (league name if we have it) with a search `Input` in `actions`; search hits as a small list above; standings as a sortable `DataTable` (# / Δ / Manager / Team / GW / Total). `RankSparkline` replaced by `LineChartMini`.
- [ ] Commit `feat(web): restyle Leagues`.

---

## Task 11: restyle `/captain` + `/squad`

- [ ] `CaptainView.tsx` → `PageHeader` ("AI Captain") + horizon `Select` in `actions`. Two `Card`s side by side ("From your XI" / "Anyone"), each a ranked list with rank `Badge`, `web_name` + `team_short` + `position` muted, `xp` right; the top pick highlighted (`ring-1 ring-primary/40`). Rationale in a `Card` with a `Crown` icon; `rationale_source==="template"` → a muted note.
- [ ] `/squad` (`SquadTable.tsx`) → `PageHeader` + a `DataTable` (Slot / Player / Pos / Price / xP / C·V) or position-grouped `Card`s; captain/vice as `Badge`s; "link your team" `EmptyState` when no id.
- [ ] Commit `feat(web): restyle Captain + Squad`.

---

## Task 12: polish + docs

- [ ] Mobile pass (375px) on every page — no horizontal body scroll; tables scroll inside their `Card`; sidebar → Sheet.
- [ ] Loading states: every page shows `Skeleton`/`LoadingRows` not a bare "Loading…".
- [ ] `apps/web/.gitignore` (or root) — ignore Next's auto-generated `apps/web/AGENTS.md` + `apps/web/CLAUDE.md`; `git rm --cached` them.
- [ ] Favicon / PWA: keep `manifest.json`; update `theme_color`/`background_color` to `#0b0e14`; regenerate `icon-192/512.png` via `scripts/gen_icons.py` with the new bg (`_BG=(11,14,20)`).
- [ ] `README.md` — refresh the `apps/web` line ("Next 16 App Router, dark design system, sidebar shell, recharts") and add a one-liner on running the UI.
- [ ] `docs/plans/2026-08-27-fplguru-master-build-plan.md` — add a **P1i ✅** row (Phase 1, design system) + note it. `docs/RESUME-foundation.md` — top line + a `## P1i` section.
- [ ] Final: `pnpm --filter web build` → success; `pnpm --filter web test` → 19 passed; `python -m pytest -q -W error` (repo root, unchanged) → still green; `python -m ruff check .` → clean.
- [ ] Commit `docs: P1i design system complete`.

---

## Self-Review

**Spec coverage:** dark token system (Task 1), component kit (Task 2), responsive sidebar shell + theme toggle (Task 3), shared components incl. charts (Task 4), landing page (Task 5), all 8 pages restyled onto it (Tasks 6–11), mobile + loading polish + docs (Task 12). "Same genre, own identity" → own violet/green palette + navy surfaces, sidebar layout (wassupfpl uses top-nav — we diverge intentionally), cards/charts/sortable tables like theirs.

**No backend changes** — every page keeps its existing `src/lib/api.ts` calls; only presentation changes. The 19 `vitest` api-client tests are untouched and must stay green. Python suite untouched.

**SAC:** every new dep is pure JS/TS (Radix, cva, clsx, tailwind-merge, lucide-react, next-themes, recharts, tw-animate-css) — no native `.node`. `pnpm install` may pull them; if any transitively ships a native binary that SAC blocks (unlikely for this set), pin around it as the repo already does for Python.

**Placeholder scan:** Task 2 says "standard shadcn implementations" rather than pasting ~12 component files — acceptable: these are well-known, and the token-swap rule is explicit. Tasks 6–11 specify *intent + component mapping* per page, not full TSX — acceptable for a visual restyle where the browser is the real check and the data contracts are unchanged.

---

## Execution Handoff

Branch `feature/p1i-design-system` off `main`. Subagent-driven, order 1 → 12. Tasks 1–4 (foundation) get a code-quality review; Tasks 5–11 are spec-check + a browser screenshot each; Task 12 spec-check. Keep the API (:8000) + web dev (:3000) servers up throughout for visual verification. After Task 12: whole-branch review, PR → `main`, watch CI, squash-merge.

### Deferred follow-ups
- Player comparison view, global search (wassupfpl has these).
- Real chart pages (xG trend per player, rank history full page).
- Motion polish (page transitions, number tickers).
- A proper icon/logo mark (current is a flat square).
