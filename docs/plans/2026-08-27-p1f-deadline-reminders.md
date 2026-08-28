# P1f — Deadline Reminders — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** Fire an alert-feed reminder a configurable number of minutes before each gameweek deadline (24h / 2h / 1h / 30m presets plus user-chosen offsets).

**Architecture:** A new pure generator `deadline_reminder_alerts` in `fplguru-alerts`; `score_alert` gains a `deadline` base weight + a "tight" bump. `linked_teams.reminder_offsets` (JSON list of minutes, default `[1440, 120, 60, 30]`) drives it. The existing `generate_alerts` worker task calls the generator for the gameweek whose deadline is next in the future, per linked team. The `PATCH /entries/{id}/settings` route accepts `reminder_offsets`; a new `GET /entries/{id}/settings` lets the web load current values. The `/alerts` page gets a small offsets editor.

**Tech Stack:** SQLAlchemy + Alembic (`0006`), `fplguru-alerts`, Celery, FastAPI, Next.js 16.

---

## Project context (read once)

Same monorepo / SAC toolchain / TDD / commit conventions as the P1e plan
([`docs/plans/2026-08-27-p1e-alerts-engine.md`](2026-08-27-p1e-alerts-engine.md)) — re-read its
"Project context" block. Branch: **`feature/p1f-deadline-reminders`** off `main`.

Key facts specific to P1f:
- `fplguru_alerts` (`packages/alerts/src/fplguru_alerts/__init__.py`) exports `score_alert`,
  `availability_alerts`, `dgw_bgw_alerts`. `score_alert(alert, *, in_xi, is_captain, before_deadline)`;
  `_BASE = {"availability": 60, "bgw": 45, "dgw": 40}`.
- Worker `_generate_alerts` (`services/worker/src/fplguru_worker/tasks.py`) already: loads the
  `is_current` Gameweek, computes `before_deadline`, iterates `LinkedTeam` rows, builds `picks`,
  calls the generators, `_upsert_alerts`, then applies the per-GW `alert_cap` suppression pass.
- `Alert` columns: `linked_team_id, gameweek_id, type, dedup_key, player_id, priority, title,
  body, payload, suppressed, seen_at`. Unique `(linked_team_id, dedup_key)`.
- API: `PATCH /entries/{entry_id}/settings` currently accepts `_SettingsBody(alert_cap: int | None)`
  and returns `{fpl_entry_id, alert_cap}`. `_linked_or_404(db, entry_id)` helper. Mutating routes
  use `await db.commit()` (the session autobegins on the first read — do **not** use `db.begin()`).
- Web: `apps/web/src/lib/api.ts` has `updateEntrySettings(base, entryId, alertCap)`. `/alerts`
  page is `apps/web/src/app/alerts/AlertFeed.tsx` (client).
- **Baseline:** repo-root `python -m pytest -q` → **126 passed**; web `vitest run` → **7 passed**.

---

## Task 1: `reminder_offsets` column + `0006` migration

**Files:** `packages/core/src/fplguru_core/models.py`, `packages/core/tests/test_alert_model.py`, `alembic/versions/0006_reminder_offsets.py`.

- [ ] **Step 1: failing test** — append to `packages/core/tests/test_alert_model.py`:
```python
def test_linked_team_has_reminder_offsets_default():
    col = LinkedTeam.__table__.c.reminder_offsets
    assert col.nullable is False
```

- [ ] **Step 2: model** — in `class LinkedTeam`, after `alert_cap`:
```python
    reminder_offsets: Mapped[list] = mapped_column(
        JSON, default=lambda: [1440, 120, 60, 30],
        server_default='[1440, 120, 60, 30]',
    )
```
(`JSON` is already imported in `models.py`.)

- [ ] **Step 3: migration `alembic/versions/0006_reminder_offsets.py`** (`revision = '0006'`, `down_revision = '0005'`; header style from `0003_entry_tables.py`):
```python
def upgrade() -> None:
    op.add_column(
        'linked_teams',
        sa.Column('reminder_offsets', sa.JSON(), nullable=False,
                  server_default='[1440, 120, 60, 30]'),
    )


def downgrade() -> None:
    op.drop_column('linked_teams', 'reminder_offsets')
```

- [ ] **Step 4:** `python -m alembic upgrade head` → ok. `python -m alembic check` → `No new upgrade operations detected.` (If drift on the default: the model `server_default` string must byte-match the migration's — keep both exactly `'[1440, 120, 60, 30]'`.)

- [ ] **Step 5:** `python -m pytest packages/core -q` → pass. `python -m pytest -q -W error` → **127 passed**. `ruff` clean, `alembic check` clean.
  `feat(core): linked_teams.reminder_offsets (0006)`

---

## Task 2: `deadline_reminder_alerts` generator + `score_alert` deadline weight

**Files:** `packages/alerts/src/fplguru_alerts/__init__.py`, `packages/alerts/tests/test_alerts.py`.

- [ ] **Step 1: failing test** — append to `packages/alerts/tests/test_alerts.py`:
```python
from datetime import UTC, datetime, timedelta

from fplguru_alerts import deadline_reminder_alerts


def test_score_deadline_tight_pre_deadline():
    a = {"type": "deadline", "payload": {"minutes_left": 25}}
    assert score_alert(a, in_xi=False, is_captain=False, before_deadline=True) == 55 + 15 + 10


def test_score_deadline_far():
    a = {"type": "deadline", "payload": {"minutes_left": 800}}
    assert score_alert(a, in_xi=False, is_captain=False, before_deadline=True) == 55 + 10


def test_deadline_reminder_fires_for_offsets_already_inside_window():
    now = datetime(2026, 8, 30, 10, 40, tzinfo=UTC)
    deadline = datetime(2026, 8, 30, 11, 0, tzinfo=UTC)  # 20 min away
    out = {a["dedup_key"]: a for a in deadline_reminder_alerts(
        deadline, now, [1440, 120, 60, 30], gameweek_id=4)}
    # only offsets whose window contains "now" (>= 20 min): 1440, 120, 60, 30
    assert set(out) == {"deadline:4:1440", "deadline:4:120", "deadline:4:60", "deadline:4:30"}
    assert out["deadline:4:30"]["type"] == "deadline"
    assert out["deadline:4:30"]["payload"]["minutes_left"] == 20
    assert out["deadline:4:30"]["gameweek_id"] == 4
    assert "20 min" in out["deadline:4:30"]["body"] or "20 minutes" in out["deadline:4:30"]["body"]


def test_deadline_reminder_excludes_past_and_too_early():
    now = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    deadline = datetime(2026, 8, 30, 11, 0, tzinfo=UTC)  # 180 min away
    out = {a["dedup_key"] for a in deadline_reminder_alerts(
        deadline, now, [1440, 120, 30], gameweek_id=4)}
    assert out == {"deadline:4:1440"}          # 120 and 30 windows not reached yet


def test_deadline_reminder_none_after_deadline():
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    deadline = datetime(2026, 8, 30, 11, 0, tzinfo=UTC)
    assert deadline_reminder_alerts(deadline, now, [1440, 30], gameweek_id=4) == []
```

- [ ] **Step 2: implement** — in `packages/alerts/src/fplguru_alerts/__init__.py`:
  - add `"deadline": 55` to `_BASE`.
  - in `score_alert`, after the hard-out block, add:
    ```python
    if alert["type"] == "deadline" and alert.get("payload", {}).get("minutes_left", 1e9) <= 60:
        score += 15
    ```
  - add to `__all__`: `"deadline_reminder_alerts"`.
  - add the generator:
    ```python
    def _humanize(minutes: int) -> str:
        if minutes >= 1440:
            d = round(minutes / 1440)
            return f"{d} day{'s' if d != 1 else ''}"
        if minutes >= 120:
            return f"{round(minutes / 60)} hours"
        if minutes >= 60:
            return "1 hour"
        return f"{minutes} min"


    def deadline_reminder_alerts(deadline, now, offsets, *, gameweek_id):
        minutes_left = (deadline - now).total_seconds() / 60.0
        if minutes_left < 0:
            return []
        out = []
        for offset in sorted({int(o) for o in offsets}):
            if minutes_left <= offset:
                out.append({
                    "type": "deadline",
                    "dedup_key": f"deadline:{gameweek_id}:{offset}",
                    "gameweek_id": gameweek_id,
                    "player_id": None,
                    "title": f"GW{gameweek_id} deadline in ~{_humanize(int(round(minutes_left)))}",
                    "body": (
                        f"The GW{gameweek_id} deadline is in about "
                        f"{int(round(minutes_left))} min — set your team."
                    ),
                    "payload": {"offset": offset, "minutes_left": int(round(minutes_left))},
                })
        return out
    ```
  Note: `deadline`/`now` are timezone-aware `datetime`; `offsets` is a list of ints (minutes).

- [ ] **Step 3:** `python -m pytest packages/alerts -q` → **11 passed** (6 + 5). `python -m pytest -q -W error` → **132 passed** (127 + 5). `ruff` clean.
  `feat(alerts): deadline_reminder_alerts generator + deadline score weight`

---

## Task 3: wire into the `generate_alerts` worker task

**Files:** `services/worker/src/fplguru_worker/tasks.py`, `services/worker/tests/test_generate_alerts.py`.

- [ ] **Step 1a: update the two existing exact-set assertions** in `services/worker/tests/test_generate_alerts.py`. `_seed` sets the GW9 deadline 1 day out, so the `1440`-minute reminder now also fires:
  - `test_generate_alerts_creates_ranked_rows`: change the expected set to
    `{"avail:2:i:0", "avail:3:a:75", "dgw:10:9", "bgw:11:9", "deadline:9:1440"}` and add
    `assert rows["deadline:9:1440"].priority == 55 + 10` (far-out, pre-deadline, no tight bump).
  - `test_generate_alerts_is_idempotent`: change `assert n == 4` to `assert n == 5`.
  - `test_generate_alerts_applies_cap` uses `alert_cap=2`; with 5 alerts now, the two visible are
    still the top two by priority: `avail:2:i:0` (100) and `dgw:10:9` (75) — unchanged. The
    suppressed set becomes `{"avail:3:a:75", "bgw:11:9", "deadline:9:1440"}` (priorities 70 / 70 /
    65). Update that assertion.

- [ ] **Step 1b: failing test** — append to `services/worker/tests/test_generate_alerts.py`:
```python
async def test_generate_alerts_emits_deadline_reminders(db_session):
    await _seed(db_session)  # GW9 is_current, deadline ~1 day out
    # move GW9 deadline to 25 minutes from now so the 30 + 120 + 1440 windows fire
    from fplguru_core.models import Gameweek as _GW
    gw = (await db_session.execute(select(_GW).where(_GW.id == 9))).scalar_one()
    gw.deadline_time = datetime.now(UTC) + timedelta(minutes=25)
    await db_session.commit()

    await tasks._generate_alerts()

    keys = {a.dedup_key for a in (await db_session.execute(select(Alert))).scalars()}
    assert {"deadline:9:30", "deadline:9:120", "deadline:9:1440"} <= keys
    row = (await db_session.execute(
        select(Alert).where(Alert.dedup_key == "deadline:9:30")
    )).scalar_one()
    assert row.type == "deadline"
    assert row.priority == 55 + 15 + 10          # tight + pre-deadline
    assert row.linked_team_id == 1
```
(The default `_seed` `LinkedTeam` has `reminder_offsets` defaulting to `[1440, 120, 60, 30]` via the column server default — but ORM-inserted rows need the Python-side `default`, which the model provides. Confirm `_seed` does not pass `reminder_offsets`; it should not.)

- [ ] **Step 2: implement** — in `_generate_alerts`, extend the `fplguru_alerts` import to include `deadline_reminder_alerts`. After the `is_current` gw lookup / `before_deadline` line, add a lookup for the next-deadline gameweek:
```python
            now = datetime.now(UTC)
            next_dl_gw = (await session.execute(
                select(Gameweek).where(Gameweek.deadline_time > now)
                .order_by(Gameweek.deadline_time).limit(1)
            )).scalar_one_or_none()
```
Then inside the `for lt in teams:` loop, after `generated = availability_alerts(...)` / the dgw-bgw block, add:
```python
                if next_dl_gw is not None:
                    generated += deadline_reminder_alerts(
                        next_dl_gw.deadline_time, now,
                        lt.reminder_offsets or [],
                        gameweek_id=next_dl_gw.id,
                    )
```
The existing `for a in generated:` scoring loop already handles `player_id is None` alerts
(sets `in_xi`/`is_cap` via `_team_flag` on `payload["player_names"]`, which is absent for
deadline alerts → both `False`). `score_alert` picks up `type == "deadline"` and the
`minutes_left` bump. The per-GW cap pass groups by `Alert.gameweek_id`; deadline alerts carry
`next_dl_gw.id` which may differ from the `is_current` gw — that is fine, they are capped within
their own gameweek group. **Adjust the cap pass** to iterate every distinct `gameweek_id` present
for the team, not just `gw.id`:
```python
                team_gw_ids = {r["gameweek_id"] for r in rows} | {gw.id}
                for gwid in team_gw_ids:
                    ranked = (await session.execute(
                        select(Alert).where(
                            Alert.linked_team_id == lt.id, Alert.gameweek_id == gwid
                        ).order_by(Alert.priority.desc(), Alert.id)
                    )).scalars().all()
                    for i, row in enumerate(ranked):
                        row.suppressed = lt.alert_cap is not None and i >= lt.alert_cap
```
(replace the single-`gw.id` cap block with this.)

- [ ] **Step 3:** `python -m pytest services/worker/tests/test_generate_alerts.py -q` → **4 passed**. `python -m pytest -q -W error` → **133 passed** (132 + 1). `ruff` clean, `alembic check` clean.
  `feat(worker): deadline reminders in generate_alerts (nearest-future-deadline GW)`

---

## Task 4: settings API — `reminder_offsets`

**Files:** `services/api/src/fplguru_api/main.py`, `services/api/tests/test_alerts_api.py`.

- [ ] **Step 1: failing test** — append to `services/api/tests/test_alerts_api.py`:
```python
async def test_get_settings_returns_defaults(client, db_session):
    await _seed(db_session)
    body = (await client.get("/entries/555/settings")).json()
    assert body["alert_cap"] is None
    assert body["reminder_offsets"] == [1440, 120, 60, 30]


async def test_patch_settings_reminder_offsets(client, db_session):
    await _seed(db_session)
    r = await client.patch("/entries/555/settings",
                           json={"reminder_offsets": [180, 45, 45, 0, -3]})
    # sanitised: deduped, positives only, sorted desc, capped at 7
    assert r.json()["reminder_offsets"] == [180, 45]
    # alert_cap untouched when omitted
    assert r.json()["alert_cap"] is None
```

- [ ] **Step 2: implement** — in `main.py`:
  - `_SettingsBody` gains `reminder_offsets: list[int] | None = None`.
  - add a sanitiser:
    ```python
    def _clean_offsets(raw: list[int]) -> list[int]:
        vals = sorted({int(o) for o in raw if 0 < int(o) <= 4320}, reverse=True)
        return vals[:7]
    ```
  - `patch_entry_settings`: only assign each field when its body value is not `None`
    (so a patch of just `reminder_offsets` doesn't wipe `alert_cap` and vice-versa — note
    `alert_cap: None` in the body is indistinguishable from "omitted" with this shape, which
    matches today's behaviour where sending `{"alert_cap": null}` clears it; keep that, and
    guard `reminder_offsets` with `is not None`):
    ```python
    @app.patch("/entries/{entry_id}/settings")
    async def patch_entry_settings(entry_id: int, body: _SettingsBody,
                                   db: AsyncSession = Depends(get_db)) -> dict:
        lt = await _linked_or_404(db, entry_id)
        lt.alert_cap = body.alert_cap
        if body.reminder_offsets is not None:
            lt.reminder_offsets = _clean_offsets(body.reminder_offsets)
        out = {"fpl_entry_id": lt.fpl_entry_id, "alert_cap": body.alert_cap,
               "reminder_offsets": lt.reminder_offsets}
        await db.commit()
        return out
    ```
  - add the GET:
    ```python
    @app.get("/entries/{entry_id}/settings")
    async def get_entry_settings(entry_id: int,
                                 db: AsyncSession = Depends(get_db)) -> dict:
        lt = await _linked_or_404(db, entry_id)
        return {"fpl_entry_id": lt.fpl_entry_id, "alert_cap": lt.alert_cap,
                "reminder_offsets": lt.reminder_offsets}
    ```

- [ ] **Step 3:** `python -m pytest services/api/tests/test_alerts_api.py -q` → **8 passed** (6 + 2). `python -m pytest -q -W error` → **135 passed** (133 + 2). `ruff` clean.
  `feat(api): GET/PATCH entry settings — reminder_offsets`

---

## Task 5: web — reminder-offsets editor

**Files:** `apps/web/src/lib/api.ts`, `apps/web/src/lib/api.alerts.test.ts`, `apps/web/src/app/alerts/AlertFeed.tsx`.

- [ ] **Step 1: failing test** — append to `apps/web/src/lib/api.alerts.test.ts`:
```ts
import { getEntrySettings, updateEntrySettings } from "./api";

describe("entry settings api", () => {
  it("getEntrySettings reads current values", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ alert_cap: null, reminder_offsets: [120, 30] }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;
    const r = await getEntrySettings("http://api.test", 7);
    expect(r.reminder_offsets).toEqual([120, 30]);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/entries/7/settings");
  });

  it("updateEntrySettings sends both fields", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ alert_cap: 5, reminder_offsets: [60] }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;
    await updateEntrySettings("http://api.test", 7, { alertCap: 5, reminderOffsets: [60] });
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ alert_cap: 5, reminder_offsets: [60] });
  });
});
```

- [ ] **Step 2: implement** — in `apps/web/src/lib/api.ts`, **replace** the current `updateEntrySettings` with an options-object form and add `getEntrySettings`:
```ts
export type EntrySettings = { alert_cap: number | null; reminder_offsets: number[] };

export function getEntrySettings(base: string, entryId: number) {
  return fetch(`${base}/entries/${entryId}/settings`, { cache: "no-store" }).then(
    asJson<EntrySettings & { fpl_entry_id: number }>,
  );
}

export function updateEntrySettings(
  base: string,
  entryId: number,
  opts: { alertCap?: number | null; reminderOffsets?: number[] },
) {
  const body: Record<string, unknown> = { alert_cap: opts.alertCap ?? null };
  if (opts.reminderOffsets !== undefined) body.reminder_offsets = opts.reminderOffsets;
  return fetch(`${base}/entries/${entryId}/settings`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  }).then(asJson<EntrySettings & { fpl_entry_id: number }>);
}
```

- [ ] **Step 3:** update `apps/web/src/app/alerts/AlertFeed.tsx`:
  - the existing "Save" for the cap now calls `updateEntrySettings(API, entryId, { alertCap: cap === "" ? null : Number(cap) }).then(load)`.
  - add an offsets `<input>` (comma-separated minutes) initialised from `getEntrySettings` on mount, plus preset quick-buttons (1440 / 120 / 60 / 30) that toggle membership, and a Save that calls `updateEntrySettings(API, entryId, { alertCap: <current>, reminderOffsets: <parsed> }).then(load)`. Parse: `text.split(",").map(s => Number(s.trim())).filter(n => Number.isFinite(n) && n > 0)`.
  Keep it compact — one row under the existing controls.

- [ ] **Step 4:** `./node_modules/.bin/vitest run` → **9 passed** (7 + 2). `./node_modules/.bin/next build` → success.
  `feat(web): reminder-offsets editor on the alerts page`

---

## Task 6: docs

**Files:** `README.md`, `docs/plans/2026-08-27-fplguru-master-build-plan.md`, `docs/RESUME-foundation.md`.

- [ ] **Step 1: `README.md`** — in the Alerts section, note deadline reminders + `reminder_offsets`; add `GET /entries/{id}/settings` to the endpoint list.
- [ ] **Step 2: master plan** — mark **P1f** ✅ (branch `feature/p1f-deadline-reminders`): `deadline_reminder_alerts` generator + `deadline` score weight; `linked_teams.reminder_offsets` (`0006`, default `[1440,120,60,30]`); wired into `generate_alerts` for the nearest-future-deadline GW; `GET`/`PATCH /entries/{id}/settings`; offsets editor on `/alerts`. Decrement remaining count (14 → 13).
- [ ] **Step 3: `docs/RESUME-foundation.md`** — top status line + a `## P1f` section (task table + commits) + update "Remaining unblocked Phase-1 path" to just `P1h (PWA)`.
- [ ] **Step 4: full verification** — `pytest -q -W error` → **135 passed**; `ruff` clean; `alembic check` clean; web `vitest run` → 9 passed; `next build` → success.
- [ ] **Step 5:** `docs: P1f Deadline Reminders complete`

---

## Self-Review

**Spec coverage (master §3 P1f / PRD §4.4):**
- 24h / 2h / 1h / 30m presets → default `reminder_offsets = [1440, 120, 60, 30]` ✓
- up to 3 user custom offsets → `_clean_offsets` allows any positive minutes ≤ 4320, capped at 7 total (presets + customs) ✓
- fires through P1e's channels → alerts land in the same `alerts` table / feed / nav badge; Web Push still deferred to P1h for all alert types ✓

**Type/name consistency:**
- `deadline_reminder_alerts(deadline, now, offsets, *, gameweek_id) -> list[dict]` — Task 2 def == Task 3 call ✓
- generator dict keys map to `Alert` columns exactly as the other generators do (Task 3 reuses the existing `rows` build + scoring loop) ✓
- `score_alert` `type == "deadline"` branch + `_BASE["deadline"]` — Task 2 ✓
- `reminder_offsets`: model `JSON` list, migration `sa.JSON()` `server_default='[1440, 120, 60, 30]'`, `_SettingsBody.reminder_offsets`, `_clean_offsets`, web `EntrySettings.reminder_offsets`, `getEntrySettings` / `updateEntrySettings` ✓
- **Breaking web API change:** `updateEntrySettings` signature changes from `(base, id, alertCap)` to `(base, id, {alertCap, reminderOffsets})`. Only caller is `AlertFeed.tsx` (updated in Task 5) and `api.alerts.test.ts` (updated in Task 5). Grep confirms no other callers.

**Migration drift:** `0006` adds one non-null JSON column with a server default; Task 1 Step 4 runs `alembic check`; no new table so `test_expected_tables_registered` is untouched.

**Placeholder scan:** none.

---

## Execution Handoff

Branch `feature/p1f-deadline-reminders` off `main`. Subagent-driven, order 1 → 6. Task 2 (generator + score) and Task 3 (worker wiring + cap-pass change) get a full review; Tasks 1, 4, 5 spec-check; Task 6 spec-check. After Task 6: whole-branch review, PR → `main`, watch CI, squash-merge.
