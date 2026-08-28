# FPLGuru — Master Build Plan

> **What this is:** The top-level roadmap. It locks the architecture decisions the PRD left open, defines the repo layout, and decomposes the product into a sequence of **independently shippable sub-plans**. Each sub-plan gets its own detailed TDD document (see `docs/plans/`). Only the Foundation sub-plan is fully detailed today: [`2026-08-27-foundation.md`](2026-08-27-foundation.md).

**Goal:** Ship the PRD's FPL tracking + predictive-analytics platform as a web dashboard + PWA, built on one primary language stack to keep the ML engine and the API in the same runtime.

> ### ⚠️ SCOPE OVERRIDE (2026-08-27): no payments, no tiers
> The owner has decided the product is **free with no Free/Pro tiers**. This supersedes all "Pro-gated", "$3.99/mo", "freemium", trial, and Stripe language anywhere in this document and the PRD:
> - **P1g (Subscriptions/Stripe) — DROPPED.** No `subscriptions` table, no tier-gate middleware, no webhooks.
> - **P4c (Annual Billing) — DROPPED.** (A referral mechanic could still be built as growth-only if wanted.)
> - Every feature marked "Pro" is just a feature, available to everyone. Horizon selectors expose the full 1–10 range to all users. Alert message caps become a user-configurable setting (default: uncapped).
> - **P1a-auth** (accounts) is now *optional* — only for cross-device sync / saved preferences, and blocks nothing.
> - Milestones M2/M3 drop their "Stripe in test mode" / "flip Stripe to live" criteria.
> Remaining sub-plans after this override: **8** (F + all of Phase 1 + **P1i** design system + **P2h/P2i/P2e/P2a** done; P1g + P4c dropped). **Decided:** xG source → PitchAPI; LLM → Google Gemini + `$5/mo` cap; **UI is now a dark design system + sidebar app shell** (P1i). **Telegram (P2g) deferred.** **P2b (Advanced xP) unblocked** (P1c ✓ + P2a ✓). Also unblocked: P2d optimizer, P2f H2H.

**Source of truth:** `PRD.md` (the document this plan is derived from). Section references below (`§5.3` etc.) point at that PRD.

---

## 1. Locked Architecture Decisions

The PRD offered choices; this section resolves each one so sub-plans don't re-litigate. Rationale is one line; if a decision is wrong, change it here and propagate.

| Area | Decision | Rationale |
|---|---|---|
| Backend language | **Python 3.12** everywhere (API + workers + ML) | The xP engine (§5) is the differentiator and is Python. One language = shared feature code, shared model types, no serialization boundary between "predict" and "serve". |
| API framework | **FastAPI** + Uvicorn | Async, Pydantic models double as API schema and DB DTOs, shares runtime with `packages/ml`. |
| Frontend | **Next.js 15 (App Router)** + TypeScript + Tailwind, deployed as an installable **PWA** (same codebase, §4.2) | PRD's stated choice; SSR for dashboard SEO/TTFB. |
| Client ↔ server live updates | **SSE** (Server-Sent Events) for live scores, with polling fallback; Redis pub/sub between the poller worker and the API's SSE endpoint | One-way, proxy-friendly, simpler than WebSockets for a score ticker. |
| Database | **PostgreSQL 16** (primary) + **Redis 7** (cache, live data, rate-limit counters, Celery broker, SSE fan-out) | PRD's stated choice. |
| ORM / migrations | **SQLAlchemy 2.0** (async) + **Alembic** | Standard, plays well with FastAPI + Pydantic. |
| Feature store | **Plain Postgres tables**, versioned rows (`feature_set_version`, `model_version`), never mutated in place | PRD §6.1 says "start simple; don't over-engineer". Feast only if scale demands it later. |
| Task queue + scheduling | **Celery** (worker) + **Celery Beat** (cron-style GW-cadence jobs), Redis broker | Python-native; Beat covers the deadline/results cadence in §6.2. Prefect/Dagster deferred until the ML DAG is complex enough to need it. |
| Auth | **Auth.js (NextAuth v5)** with Postgres adapter, Email + Google OAuth | PRD: "avoid building auth from scratch"; vendor-neutral, no per-MAU cost. |
| Payments | **Stripe Billing** — one product, $3.99/mo price, 7-day trial. Annual price is a flag (§8, open question). | PRD's stated choice. |
| Push channels | **web-push (VAPID)** for PWA (Phase 1); **python-telegram-bot** (Phase 2); **WhatsApp via 360dialog BSP** (Phase 3) | Matches phased delivery; WhatsApp needs Meta verification lead time (§10.2). |
| Hosting | **Vercel** (web) + **Fly.io** (api, worker, Postgres, Redis) | PRD-suggested shape; Fly gives us managed Postgres/Redis + container jobs in one place. |
| Package management | **`venv` + `pip`** with editable installs of `packages/*` and `services/*` (one root `requirements-dev.txt`); **pnpm** workspace (via `corepack`) for `apps/web` | Originally `uv`, but the dev machine has **Smart App Control ON**, which blocks `uv`'s (and other unsigned) binaries. Tools are invoked as `python -m <tool>`; `ruff` runs in CI only. Revisit `uv` if the environment changes. |
| Local dev infra | **Docker Compose** (Postgres + Redis only); api/worker/web run on host | Fast iteration; no need to containerize app code for local work. |
| CI | **GitHub Actions** — lint + typecheck + tests on every PR, against a service-container Postgres/Redis | — |
| Error/analytics/infra obs | **Sentry** + **PostHog** + Fly metrics/Grafana | PRD §6.1. |

### Cross-cutting non-functional requirements (PRD §7) — every sub-plan owns its slice

- **Performance:** dashboard TTFB < 500ms cached, live updates to client within 5–10s. Enforced via SSR + Redis caching (F, P1b) and checked in Playwright perf assertions per feature plan.
- **Scalability:** Friday/Saturday deadline + 3pm-kickoff spikes. Stateless api/worker containers, Redis-backed rate limits and SSE fan-out, autoscale on Fly.
- **Reliability:** graceful degradation when the FPL API is down — serve last-known state + "data as of X" (built in F: `data_sync_log` + `/status`; consumed by every read path).
- **Security:** no FPL credentials stored (public Team ID only); OWASP baseline on the account/payment system (P1a, P1g); secrets in Fly/Vercel env, never in repo.
- **Privacy:** GDPR/CCPA — data-export + delete-account endpoints and a cookie/consent policy land in P1a; PostHog configured EU-region + IP anonymization.
- **Accessibility:** WCAG 2.1 AA — axe-core check wired into the web CI job in F; each feature plan includes keyboard-nav + contrast acceptance criteria.

### Testing stack (applies to every sub-plan)

- **Python:** `pytest`, `pytest-asyncio`, `httpx.AsyncClient` for API tests, `respx` to mock the FPL API, `factory-boy` for fixtures, a real Postgres via Compose for integration tests (no SQLite — we use Postgres-specific types).
- **Web:** `vitest` + `@testing-library/react` for units, `playwright` for e2e (deadline-time flows, install prompt, live ticker).
- **TDD is mandatory** (superpowers:test-driven-development). Every task below is "write failing test → see it fail → minimal impl → see it pass → commit".

---

## 2. Repo Layout

```
fplguru/
  apps/
    web/                     # Next.js 15 App Router, Tailwind, PWA (manifest + SW)
  services/
    api/                     # FastAPI app: REST + SSE. Thin — delegates to packages/*
    worker/                  # Celery app: ingestion, alert generation, model jobs, Beat schedule
  packages/
    core/                    # SQLAlchemy models, async DB session, Alembic env, Pydantic schemas, settings (pydantic-settings), logging
    fpl_client/              # Typed async client for fantasy.premierleague.com/api/* + response models + retry/backoff/caching
    ml/                      # xP engine: feature builders, Basic + Advanced models, backtest harness, calibration, aggregation
    ingest/                  # Source-specific ingesters (FPL bootstrap/fixtures/live, Understat, historical CSV) — pure functions: fetch -> normalized rows
  alembic/                   # migration versions (env.py imports packages/core metadata)
  infra/
    docker-compose.yml       # postgres:16, redis:7
    Dockerfile.api
    Dockerfile.worker
  docs/
    plans/                   # this file + per-sub-plan detailed plans
  .github/workflows/ci.yml
  pyproject.toml             # root config only (pytest, ruff); no project deps
  requirements-dev.txt       # editable installs of packages/* + services/* + test deps
  pnpm-workspace.yaml        # apps/*
  README.md
```

**Boundary rules:**
- `services/api` and `services/worker` contain **no business logic** beyond request/response wiring and task orchestration. Logic lives in `packages/*` so it's unit-testable without HTTP or Celery.
- `packages/core` is the only place that imports SQLAlchemy models. Everything else takes/returns Pydantic schemas or plain dataclasses.
- `packages/ingest` functions never touch the DB — they return normalized rows; the caller (a worker task) persists them. This makes ingest logic testable with recorded fixtures.
- `packages/ml` never makes network calls and never touches the DB — it takes a feature DataFrame in, returns predictions out.

---

## 3. Sub-Plan Decomposition

Each sub-plan produces **working, testable software on its own** and has its own `docs/plans/<date>-<name>.md`. Ordering respects the dependency graph in §4.

### Phase 1 — Foundation & MVP

| # | Sub-plan | Delivers (acceptance) | Depends on | PRD refs |
|---|---|---|---|---|
| **F** | **Foundation** (repo/infra + FPL data pipeline) — *detailed today* | `docker compose up` + venv boots api & worker; CI green; Postgres populated with teams/players/fixtures/gameweeks from the live FPL API; refresh job runs on a schedule; API serves `/health` and `/gameweeks`. | — | §6.1, §6.2, §6.3, §5.6, §7 (degradation) |
| **P1a** ✅ | Team Linking & Dashboard Shell — *done* ([`2026-08-27-p1a-team-dashboard.md`](2026-08-27-p1a-team-dashboard.md)) | Enter manager ID → `linked_teams` / `entry_gw_history` / `entry_picks` (`0003`); `sync_entry` in the shared `fplguru-entrysync` pkg + `sync-linked-teams` Beat task; `POST /link/{id}`, `GET /entries/{id}` (squad + per-pick xP), `GET /entries/{id}/history`; Next.js nav shell + link form (entry id in `localStorage`) + squad page. **Auth deferred to sub-plan P1a-auth** (blocked on OAuth creds / email transport) — P1a is entry-id-keyed, no accounts. Chips + mini-league IDs also deferred (P2h owns leaderboards). | F | §4.1, §4.8 |
| **P1b** ✅ | Live Scores & GW Live tool — *done* ([`2026-08-27-p1b-live-scores.md`](2026-08-27-p1b-live-scores.md), branch `feature/p1b-live-scores`) | `player_gw_live` + `fixtures` match-state columns (`0004`); `fplguru-live` pkg (`project_bonus` rank-position tie rule + `build_live_rows`); `poll_live` Beat task polls `event/{gw}/live` only while a fixture is in play, projects 3/2/1 bonus per fixture from BPS, upserts one row per (player, current-GW); `GET /gameweeks/current/live` snapshot + `GET /gameweeks/current/live/stream` (hand-rolled SSE, re-reads DB every `live_stream_poll_seconds`); Next.js `/live` board (fixtures strip + ranked table) subscribing over `EventSource` with a 15s polling fallback + my-players filter. End-to-end latency ≈ `live_poll_seconds` (60s, settable) + FPL's own lag. | F | §4.10 (GW Live), §7 |
| **P1c** ✅ | Basic xP Engine v1 — *done* ([`2026-08-27-p1c-basic-xp-engine.md`](2026-08-27-p1c-basic-xp-engine.md), branch `feature/basic-xp`) | `player_gw_predictions` populated by a per-position closed-form ridge model (no scikit-learn), FPL-only leak-safe features, horizons 1–5 + widening band + position-mean cold start; `player_gw_stats` ingest (`event/{gw}/live`); walk-forward backtest → [`docs/xp-backtest/2026-08-27.md`](../xp-backtest/2026-08-27.md) (all 4 positions beat baseline); worker `compute_xp` on Beat; `GET /xp` + `GET /players/{id}/xp`. Component `x_*` fields deferred to P2b. | F | §5.1, §5.2 (Basic), §5.4, §5.5, §5.7 |
| **P1d** ✅ | FDR Table — *done* ([`2026-08-27-p1d-fdr-table.md`](2026-08-27-p1d-fdr-table.md), branch `feature/p1d-fdr`) | `fplguru-fdr` pkg: platform FDR per team from FPL strength tier blended with recent goals-for/against form (`att_fdr`/`def_fdr` split, band 1–5); `GET /fdr?horizon=&start_gw=` (horizon 1–10, all users, no tier gate); Next.js `/fdr` colour-coded grid, easiest-first, horizon selector persisted to `localStorage` (`prefs.ts`). xG-for/against + clean-sheet-probability columns deferred to P2a (Understat, blocked). | F | §4.6 |
| **P1e** ✅ | Alerts Engine + Priority Ranking — *done* ([`2026-08-27-p1e-alerts-engine.md`](2026-08-27-p1e-alerts-engine.md), branch `feature/p1e-alerts`) | [Priority-ranking design doc](../design/2026-08-27-alert-priority-ranking.md); `fplguru-alerts` pkg (`score_alert` + `availability_alerts` + `dgw_bgw_alerts`); `alerts` table + `linked_teams.alert_cap` (`0005`); `generate_alerts` Beat task (30 min) with per-GW cap application; `GET /entries/{id}/alerts`, `POST .../alerts/seen`, `PATCH .../settings`; Next.js `/alerts` feed + nav unseen badge. **No tier / no "upgrade" message** — `alert_cap` is a nullable per-team int (default uncapped). Deferred: `price_change` / `fdr_shift` generators (need snapshots), **Web Push delivery → P1h** (owns VAPID + subscriptions; alert rows are already push-shaped). | F, P1a | §4.3, §3 |
| **P1f** ✅ | Deadline Reminders — *done* ([`2026-08-27-p1f-deadline-reminders.md`](2026-08-27-p1f-deadline-reminders.md), branch `feature/p1f-deadline-reminders`) | `deadline_reminder_alerts` generator + `deadline` score weight (base 55, +15 when ≤60 min out); `linked_teams.reminder_offsets` JSON (`0006`, default `[1440,120,60,30]`); wired into `generate_alerts` for the nearest-future-deadline gameweek per team; `GET` + `PATCH /entries/{id}/settings` (offsets sanitised: positive, ≤4320 min, ≤7 entries); presets + free-text editor on `/alerts`. Fires through the same feed + nav badge as P1e (Web Push still P1h). | P1e | §4.4 |
| ~~**P1g**~~ | ~~Subscriptions (Stripe) scaffold~~ — **DROPPED** (scope override: no payments) | — | — | — |
| **P1h** ✅ | PWA — *done* ([`2026-08-27-p1h-pwa.md`](2026-08-27-p1h-pwa.md), branch `feature/p1h-pwa`) | Icons + `public/sw.js` (precache shell, network-first API with last-known-data fallback, `push` / `notificationclick` handlers); `PwaSetup` install-prompt island; `push_subscriptions` (`0007`) + `alerts.pushed_at`; `fplguru-push` targeting pkg; `deliver_push` Beat task (60s) sending the visible alert feed as Web Push — `pywebpush` is **optional / deploy-image-only** (SAC blocks its native tree locally), a logged no-op without a VAPID key; `GET /push/vapid-public-key` + `POST`/`DELETE /entries/{id}/push/subscribe`; `/alerts` push opt-in. Background Sync API queue deferred. **Phase 1 complete.** | P1a | §4.2 |
| **P1i** ✅ | Design System & App Shell — *done* ([`2026-08-28-p1i-design-system.md`](2026-08-28-p1i-design-system.md), branch `feature/p1i-design-system`) | Dark token system (Tailwind v4 `@theme`, violet/green identity, light override); hand-written shadcn-style primitives (`src/components/ui`: Button/Card/Badge/Table/Tabs/Input/Select/Skeleton/Sheet); responsive `AppShell` (sidebar + topbar + mobile drawer + theme toggle via `next-themes`); shared components (`PageHeader`/`StatTile`/`DataTable` sortable/`Delta`/`EmptyState`/`Chart` via `recharts`); a real landing page; **all 8 pages restyled** onto it; skeleton loaders + empty states. + `fix(api): CORS` so the browser can call the API. Deferred: player comparison, full chart pages, motion, a real logo mark. | P1a | — |

### Phase 2 — Core Differentiators

| # | Sub-plan | Delivers | Depends on | PRD refs |
|---|---|---|---|---|
| **P2a** ✅ | xG/xA Ingestion (PitchAPI) — *done* ([`2026-08-27-p2a-pitchapi-xg.md`](2026-08-27-p2a-pitchapi-xg.md), branch `feature/p2a-pitchapi-xg`) | `fplguru-pitch` client (`X-API-KEY`, `Retry-After`) + `fplguru-pitchmatch` pure matcher/normalizer; `pitch_team_map` / `pitch_player_map` (auto surname+initial+team) / `player_xg` (`0011`); `sync_xg` Beat task (daily) resolves finished fixtures → PitchAPI matches → per-player xG (shot sums) + xag + minutes, upserts `player_xg`, seeds id maps, parks unmatched; `PitchApiError`/shape errors → `DataSyncLog` (surfaced on `/status`); `GET /players/{id}/xg` + `GET /xg-snapshot` (the deferred P2i tool) + `/tools` xG tab; `scripts/pitch_probe.py|pitch_map.py|backfill_xg.py`. **Response shapes are from the published docs — `pitch_probe.py` must confirm them before the first real sync.** No key → task is a no-op. **Unblocks P2b (Advanced xP).** Deferred: team-xG rollups, shot-level storage, ops alerting, scheduled backfill. | F | §5.3, §5.6, §10.1 |
| **P2b** | Advanced xP Engine | LightGBM ensemble, one model per position group, full multi-GW iterative rollout (compounding rotation + fixture swings), quantile-regression floor/ceiling bands, isotonic calibration, SHAP contributions surfaced. | P1c, P2a | §5.2 (Advanced), §5.4, §5.5 |
| **P2c** | LLM Explanation Layer | Turns Advanced model output + top SHAP features into plain-English rationale. **LLM provider decided → Google Gemini** (reuse `fplguru-llm` + the `llm_calls` budget ledger + `generate_within_budget` from P2e). | P2b | §5.4, §5.2 |
| **P2d** | Optimize My Team | Suggested transfers in/out, captain/vice, bench order, chip-timing window flags; horizon selector (1–5 all, 10 Pro); persisted preference. Basic algo (Free) vs advanced xP + rationale (Pro). | P1c (Free), P2b/P2c (Pro), P1g | §4.5 |
| **P2e** ✅ | AI Captain Recommendations — *done* ([`2026-08-27-p2e-ai-captain.md`](2026-08-27-p2e-ai-captain.md), branch `feature/p2e-ai-captain`) | **First LLM feature.** `fplguru-llm` (async **Gemini REST** client, no SDK) + `fplguru-captain` (pure ranking); `llm_calls` budget ledger + `captain_rationale` cache (`0010`); `services/api/llm.py::generate_within_budget` enforces `FPLGURU_LLM_MONTHLY_USD_CAP`; `GET /entries/{id}/captain?horizon=` → constrained (your XI) + unconstrained picks by Basic xP + a Gemini rationale (cached per player-GW, templated fallback when unset/over-budget); Next.js `/captain` page. **No tier gate** (2026-08-27 pivot) — cost bounded by the cap. Ranks on Basic xP; SHAP-driven rationale is a P2b/P2c follow-up. | P1c (~~P2b, P2c, P1g~~) | §4.11 |
| **P2f** | H2H Match Helper | Opponent squad profiling, squad-vs-squad view, strategy suggestion. Pro-gated. | P1a, P2b, P1g | §4.12 |
| **P2g** | Telegram Bot + Pull Commands | `/myteam` `/fdr` `/captain` `/live`; Free 2/day, Pro unlimited; alert push channel. | P1e, P1a | §4.9, §4.3 |
| **P2h** ✅ | Community Leaderboard — *done* ([`2026-08-27-p2h-community-leaderboard.md`](2026-08-27-p2h-community-leaderboard.md), branch `feature/p2h-leaderboard`) | `sync_entry` captures classic mini-leagues → `linked_team_leagues`; `sync_league_standings` Beat task (2h) refreshes each tracked league's top slice → `league_standings` (`0008`); `GET /entries/{id}/leagues` (rank + weekly delta), `GET /leagues/{id}/standings`, `GET /leagues/{id}/search?q=`, `GET /entries/{id}/rank-history`; Next.js `/leagues` board + `/leagues/[id]` standings/search + SVG rank sparkline. "Global" = the Overall league (314); a bespoke global top-N crawl + standings pagination + H2H leagues are follow-ups. | P1a | §4.8 |
| **P2i** ✅ | Free Tools Suite — *done* ([`2026-08-27-p2i-free-tools.md`](2026-08-27-p2i-free-tools.md), branch `feature/p2i-free-tools`) | `fplguru-tools` pkg (`trends`, `template_xi`, `template_diff`, `gw_calendar`, `pick_overpowered_xi`); `players` gains transfer/price/form cols (`0009`); `GET /trends`, `/template`, `/entries/{id}/template-diff`, `/calendar?from_gw=&to_gw=`, `/overpowered?horizon=`; Next.js `/tools` tabbed hub. **FDR/xG/CS Snapshot deferred to P2a.** Budget + max-3-per-club constraints on the XI pickers are follow-ups. | F, P1c, ~~P2a~~ | §4.10 |

### Phase 3 — Content & Ecosystem

| # | Sub-plan | Delivers | Depends on | PRD refs |
|---|---|---|---|---|
| **P3a** | YouTube Summary Pipeline | Caption pull (YouTube Data API) → LLM paraphrased summary → structured output (picks/differentials/captain) tagged by creator. Free: curated list, 3/GW. Pro: own 5 channels, unlimited. Copyright-aware (paraphrase, never store/redistribute transcripts — §10.3). | P1g | §4.7 |
| **P3b** | Press Conference AI Extraction | Extract injury/team-news signals from presser transcripts/articles → daily in-app digest + optional Telegram push (Pro). | P2g | §4.13 |
| **P3c** | GW Strategy Consensus | Aggregate pundit/YouTuber/community sources into one pre-deadline consensus view (captain, differentials, transfer trends). All tiers (Free capped by 10-msg limit). | P3a, P1e | §4.14, §3 |
| **P3d** | WhatsApp Integration | 360dialog BSP, template message approval, mirror of Telegram commands + alert push. | P2g | §4.3, §10.2 |

### Phase 4 — Polish & Retention

| # | Sub-plan | Delivers | Depends on | PRD refs |
|---|---|---|---|---|
| **P4a** | Saved Optimization Plans | Up to 5 saved plans per Pro user. | P2d, P1g | §4.5, §3 |
| **P4b** | Model Transparency Page | Public "last GW xP vs actual" + rolling MAE/RMSE per position; A/B model-version switch. | P1c, P2b | §5.7 |
| ~~**P4c**~~ | ~~Annual Billing~~ — **DROPPED** (scope override). Referral/growth mechanic optional, standalone. | — | §9 |

---

## 4. Dependency Graph & Critical Path

```
F (Foundation)
├─> P1a Team Linking / Dashboard Shell
│   ├─> P1e Alerts ──> P1f Deadline Reminders
│   │              └─> P2g Telegram ──> P3b Pressers
│   │                              └─> P3d WhatsApp
│   ├─> P1g Stripe scaffold ──> (gates every Pro feature) ──> P4c Annual/Referral
│   ├─> P1h PWA
│   ├─> P1b Live Scores / GW Live
│   ├─> P2f H2H Helper
│   └─> P2h Leaderboard
├─> P1c Basic xP ──> P1d FDR ──> P2i Free Tools
│   └─> P2b Advanced xP (also needs P2a) ──> P2c LLM Rationale ──> P2d Optimizer ──> P4a Saved Plans
│                                        └─> P2e AI Captain
│                                        └─> P4b Transparency Page
└─> P2a Understat xG ──> P2b
P3a YouTube ──> P3c Consensus
```

**Critical path to a demoable differentiator:** `F → P1c (Basic xP) → P1d (FDR)`. Build these first and validate the model against history before investing in the Advanced engine — this de-risks the hardest part (PRD §11.3).

**Cross-cutting, build early:** `P1g (Stripe/tier gate)` — every Pro feature imports its gate decorator, so land the gate mechanism in Phase 1 even though most Pro features come later.

---

## 5. Phase Milestones & Exit Criteria

- **M1 — Foundation done:** `F` acceptance met. CI green. A cron-scheduled job keeps the DB in sync with FPL. Grafana shows job success. → *unblocks all Phase 1 parallel work.*
- **M2 — MVP live (private beta):** `P1a,b,d,e,f,g,h` shipped; `P1c` Basic xP serving predictions with a published backtest (MAE/RMSE per position). Dashboard installable as PWA. Stripe checkout works end-to-end in test mode. → *invite ~50 managers.*
- **M3 — Pro is worth paying for:** `P2a,b,c,d,e` shipped. Advanced xP beats Basic xP on backtest RMSE for ≥3 of 4 position groups. AI Captain + Optimizer live and gated. → *flip Stripe to live, open signups.*
- **M4 — Ecosystem:** `P2g,h,i` + `P3a,b,c` shipped. Telegram bot public. → *marketing push around content features.*
- **M5 — Retention:** `P4a,b,c` shipped. Transparency page public (trust differentiator). Annual plan live.

**Model-quality gate (blocks M3):** Advanced xP must demonstrably out-rank Basic xP. If it doesn't after two iterations, ship Basic as "the" model and re-scope Advanced — do not gate Pro revenue on an unproven model (PRD §10.4).

---

## 6. Data Sources — Procurement & Setup

| Source | Use | Access | Action needed before the sub-plan that needs it |
|---|---|---|---|
| Official FPL API (`fantasy.premierleague.com/api/`) | prices, ownership, fixtures, live points, bootstrap-static, manager/league data | Public, no key, unofficial (no SLA) | Build a resilient client with backoff + cached last-known state (in **F**). |
| `vaastav/Fantasy-Premier-League` (GitHub CSVs) | historical per-GW player data 2016-17 → present, for **backtraining & backtesting** the xP model | Public repo, CSV | Vendor a pinned snapshot into `packages/ingest` fixtures + a refresh script (in **F**, used by **P1c**). |
| Understat | player/team xG, xA, shots | Scrape (fragile, unofficial) | Decide in §7 open questions whether to accept scrape fragility or budget for Opta. Scraper + FPL-ID mapping is **P2a**. |
| YouTube Data API | captions for summary pipeline | API key, quota | Provision key + quota before **P3a**. Paraphrase-only summarization (§10.3). |
| UEFA / football-data fixture feed | midweek European fixture congestion feature | Free tiers exist | Wire into feature builder in **P2b** (optional for **P1c**). |
| Press conference transcripts / club news | injury signal extraction | Mixed (scrape + RSS) | Source list assembled in **P3b**. |

---

## 7. Open Questions (block planning of the named sub-plans)

1. **xG data budget (§10.1).** Understat scrape (free, fragile) vs licensed Opta/StatsBomb (accurate, expensive). **Blocks P2a/P2b scope.** Recommendation: start on Understat, isolate all xG access behind `packages/ingest/xg.py` so a provider swap is one module.
2. **Deadline reminders — does Pro get more than 3 custom offsets? (§4.4).** PRD flags this for stakeholders. **Blocks a gating detail in P1f.** Default assumption until answered: same for both tiers.
3. **Annual plan price/discount (§8).** **Blocks P4c.** Not urgent.
4. **Alert priority algorithm (§11.4).** Not external — but its design doc is the first deliverable inside **P1e** and must be reviewed before the engine is built.
5. **WhatsApp BSP choice + Meta business verification (§10.2).** Long lead time. **Start verification during Phase 2** so it's ready for **P3d**.
6. **LLM provider/'budget for rationale + summaries (§5.4, §4.7).** Per-request cost at scale for P2c/P3a/P3b. Pick a model + set a monthly cap before M3.

---

## 8. What Happens Next

The **Foundation** sub-plan is fully detailed in [`2026-08-27-foundation.md`](2026-08-27-foundation.md) — bite-sized TDD tasks, exact file paths, real code. Execute that first (it has no dependencies and no blocking open questions).

When Foundation is merged and M1 criteria are met, write the next detailed sub-plan. Suggested order: **P1c (Basic xP)** next — it's on the critical path and validating it early de-risks everything downstream — then P1a, then the rest of Phase 1 in dependency order.

Each sub-plan is written just-in-time (not all up front) so later plans benefit from what earlier ones taught us about the FPL data's quirks.
