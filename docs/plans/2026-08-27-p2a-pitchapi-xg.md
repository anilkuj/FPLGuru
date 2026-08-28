# P2a — PitchAPI xG/xA Ingestion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** Ingest per-player expected-goals / expected-assists from **PitchAPI**, mapped to FPL player ids, into a `player_xg` table; expose a per-player series and an "xG snapshot" tool; log a fragility signal when PitchAPI rate-limits or changes shape. This unblocks the Advanced xP engine (P2b).

**Architecture:** A `fplguru-pitch` client wraps the PitchAPI REST endpoints (httpx + tenacity, `X-API-KEY`, honours `Retry-After`). A pure `fplguru-pitchmatch` package fuzzy-matches PitchAPI team + player names to FPL ids and normalizes a match's raw JSON into per-player xG rows. A worker task `sync_xg` walks finished FPL gameweeks, resolves each fixture to a PitchAPI match (date + mapped team ids), fetches shots + advanced-player stats, maps ids (lazily seeding `pitch_team_map`, auto-matching into `pitch_player_map`, parking the unmatched), and upserts `player_xg` keyed by `(player_id, fixture_id)`. The read API serves `GET /players/{id}/xg` and `GET /xg-snapshot`. Id-mapping fixes are a script, not an open HTTP endpoint (no auth system yet).

**Tech Stack:** httpx + tenacity, SQLAlchemy + Alembic (`0011`), Celery + Beat, FastAPI, Next.js 16, Vitest 4, `respx` for client/worker tests. All PitchAPI response shapes below are **from the published docs and must be verified against a live response** (`scripts/pitch_probe.py`) before the first real sync — the normalizers are written defensively for that reason.

---

## Project context (read once)

Same monorepo / SAC toolchain / TDD / commit conventions as the recent plans — re-read the
"Project context" block in [`docs/plans/2026-08-27-p1e-alerts-engine.md`](2026-08-27-p1e-alerts-engine.md).
Branch: **`feature/p2a-pitchapi-xg`** off `main`.

P2a-specific facts:
- **PitchAPI** — base `https://api.pitchapi.dev/v1` (`FPLGURU_PITCHAPI_BASE`), auth header
  `X-API-KEY` (`FPLGURU_PITCHAPI_KEY`; `pk_test_`/`pk_live_`). Endpoints & **assumed** shapes:
  - `GET /date/{YYYY-MM-DD}` →
    `{"data":{"date":"…","matches":[{"id":"m_…","league":{"id","name"},"home_team":{"id":"t_…","name"},"away_team":{"id","name"},"time_utc":"…Z","status":"finished","score_home":3,"score_away":1}]}}`
  - `GET /matches/{id}/shots` → `{"data":{"match_id":"m_…","shots":[{"player":{"id":"p_…","name":"E. Haaland"},"team_id":"t_…","minute":63,"expected_goals":0.24,"expected_goals_on_target":0.19,"is_goal":true}]}}`
    *(shape of `shots[]` not fully documented — parser tolerates missing keys; `pitch_probe.py` dumps a real one.)*
  - `GET /matches/{id}/advanced/players` →
    `{"data":{"match_id":"m_…","players":[{"player":{"id":"p_…","name":"E. Haaland","shirt_number":9},"team_id":"t_…","minutes_played":90,"possession_value":{"vaep_total":0.81},"passing":{"key_passes":2,"assists":0},"creation":{"xag":0.34,"chances_created":2}}]}}`
  - Errors: `{"error":{"code":"UNAUTHORIZED|RESOURCE_NOT_FOUND|RATE_LIMIT_EXCEEDED","message":"…"}}`;
    429 carries a `Retry-After` header (seconds).
  - No `/teams` listing — team ids/names come from `/date/{d}` match objects.
- `packages/fpl_client` / `packages/llm` show the house httpx + tenacity retry pattern.
- `Fixture(gameweek_id, kickoff_time, home_team_id, away_team_id, finished, started)`;
  `Team(id, name, short_name)`; `Gameweek(id, finished)`. `Player(id, web_name, first_name,
  second_name, team_id, position)`.
- Worker `tasks.py`: `_run_and_dispose`, `_record`, `_log_error`, `_upsert`, Beat in `app.py`
  (+ assertion in `services/worker/tests/test_beat_schedule.py`). `/status` `known` set in
  `services/api/main.py`.
- **Baseline:** repo-root `python -m pytest -q` → **179 passed**; web `vitest run` → **18 passed**.
  (Known intermittent local asyncpg flake on one worker DB test — re-run/isolate; CI Linux unaffected.)

---

## File Structure

| File | Responsibility |
|---|---|
| `packages/pitch/` (new pkg `fplguru-pitch`) | `PitchClient` (`matches_on`, `match_shots`, `match_advanced_players`), `PitchApiError`. |
| `packages/pitchmatch/` (new pkg `fplguru-pitchmatch`) | `match_teams`, `match_players`, `normalize_match_xg` — pure. |
| `packages/core/.../models.py` | `PitchTeamMap`, `PitchPlayerMap`, `PlayerXg`. |
| `packages/core/.../settings.py` | `pitchapi_key`, `pitchapi_base`. |
| `alembic/versions/0011_pitch_xg.py` | the three tables. |
| `services/worker/.../tasks.py` + `app.py` | `sync_xg` task + Beat entry + `/status` source. |
| `services/api/.../main.py` | `GET /players/{id}/xg`, `GET /xg-snapshot`. |
| `scripts/pitch_probe.py`, `scripts/pitch_map.py`, `scripts/backfill_xg.py` | ops helpers. |
| `apps/web/src/lib/api.ts`, `apps/web/src/app/tools/ToolsHub.tsx` | `getXgSnapshot` + an "xG" tab. |

---

## Task 1: `fplguru-pitch` — PitchAPI client

**Files:** `packages/pitch/pyproject.toml`, `packages/pitch/src/fplguru_pitch/__init__.py`, `packages/pitch/tests/test_pitch.py`; `requirements-dev.txt`, `pyproject.toml`.

- [ ] **Step 1: skeleton** like `packages/llm/pyproject.toml` → `name = "fplguru-pitch"`,
  `description = "Async PitchAPI (xG/xA) REST client."`, `dependencies = ["httpx>=0.27", "tenacity>=8.3"]`,
  `packages = ["src/fplguru_pitch"]`. Add `-e ./packages/pitch` to `requirements-dev.txt`;
  add `"fplguru_pitch"` to `known-first-party`. `pip install -r requirements-dev.txt`.

- [ ] **Step 2: failing test** — `packages/pitch/tests/test_pitch.py`:
```python
import httpx
import pytest
import respx

from fplguru_pitch import PitchApiError, PitchClient

BASE = "https://pitch.test/v1"


@respx.mock
async def test_matches_on_sends_key_header_and_returns_matches():
    route = respx.get(f"{BASE}/date/2025-11-09").mock(return_value=httpx.Response(200, json={
        "data": {"date": "2025-11-09", "matches": [{"id": "m_1", "status": "finished"}]}
    }))
    async with PitchClient("pk_test_x", base=BASE) as c:
        out = await c.matches_on("2025-11-09")
    assert out[0]["id"] == "m_1"
    assert route.calls.last.request.headers["x-api-key"] == "pk_test_x"


@respx.mock
async def test_match_advanced_players_and_shots():
    respx.get(f"{BASE}/matches/m_1/advanced/players").mock(return_value=httpx.Response(
        200, json={"data": {"players": [{"player": {"id": "p_9"}, "minutes_played": 90}]}}))
    respx.get(f"{BASE}/matches/m_1/shots").mock(return_value=httpx.Response(
        200, json={"data": {"shots": [{"player": {"id": "p_9"}, "expected_goals": 0.3}]}}))
    async with PitchClient("k", base=BASE) as c:
        adv = await c.match_advanced_players("m_1")
        shots = await c.match_shots("m_1")
    assert adv[0]["player"]["id"] == "p_9"
    assert shots[0]["expected_goals"] == 0.3


@respx.mock
async def test_404_raises_pitchapierror_not_retried():
    route = respx.get(f"{BASE}/matches/nope/shots").mock(return_value=httpx.Response(
        404, json={"error": {"code": "RESOURCE_NOT_FOUND", "message": "match not found"}}))
    async with PitchClient("k", base=BASE) as c:
        with pytest.raises(PitchApiError):
            await c.match_shots("nope")
    assert route.call_count == 1


@respx.mock
async def test_429_is_retried_then_raises():
    route = respx.get(f"{BASE}/date/2025-01-01").mock(return_value=httpx.Response(
        429, headers={"Retry-After": "0"},
        json={"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "slow down"}}))
    async with PitchClient("k", base=BASE) as c:
        with pytest.raises(PitchApiError):
            await c.matches_on("2025-01-01")
    assert route.call_count >= 2
```

- [ ] **Step 3: implement `packages/pitch/src/fplguru_pitch/__init__.py`**
```python
"""Async PitchAPI (xG/xA) REST client — no SDK."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
)

__all__ = ["PitchClient", "PitchApiError"]

logger = logging.getLogger("fplguru.pitch")
logger.addHandler(logging.NullHandler())

_DEFAULT_BASE = "https://api.pitchapi.dev/v1"
_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)


class PitchApiError(Exception):
    pass


class _Retryable(PitchApiError):
    """429 / 5xx — tenacity retries these; other PitchApiError does not."""


class PitchClient:
    def __init__(self, api_key: str, *, base: str = _DEFAULT_BASE,
                 http: httpx.AsyncClient | None = None) -> None:
        self._base = base.rstrip("/")
        self._http = http or httpx.AsyncClient(
            timeout=_TIMEOUT, headers={"X-API-KEY": api_key})
        self._owns_http = http is None

    async def __aenter__(self) -> PitchClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    @retry(
        stop=stop_after_attempt(4) | stop_after_delay(45),
        wait=wait_exponential(multiplier=0.5, max=10),
        retry=retry_if_exception_type((httpx.TransportError, _Retryable)),
        reraise=True,
    )
    async def _get(self, path: str) -> Any:
        resp = await self._http.get(f"{self._base}/{path}")
        if resp.status_code == 429:
            wait = resp.headers.get("Retry-After")
            if wait and wait.isdigit():
                await asyncio.sleep(min(int(wait), 10))
            raise _Retryable("pitch 429")
        if resp.status_code >= 500:
            raise _Retryable(f"pitch {resp.status_code}")
        if resp.status_code >= 400:
            raise PitchApiError(f"pitch {resp.status_code}: {resp.text[:200]}")
        try:
            return resp.json().get("data", {})
        except ValueError as exc:
            raise PitchApiError("pitch: non-JSON body") from exc

    async def matches_on(self, date: str) -> list[dict]:
        return list((await self._get(f"date/{date}")).get("matches", []))

    async def match_advanced_players(self, match_id: str) -> list[dict]:
        return list((await self._get(f"matches/{match_id}/advanced/players")).get("players", []))

    async def match_shots(self, match_id: str) -> list[dict]:
        return list((await self._get(f"matches/{match_id}/shots")).get("shots", []))
```

- [ ] **Step 4:** `python -m pytest packages/pitch -q` → **4 passed**. `python -m pytest -q -W error` → **183 passed**. `ruff` clean.
  `feat(pitch): fplguru-pitch — async PitchAPI client`

---

## Task 2: `fplguru-pitchmatch` — id matching + xG normalizer (pure)

**Files:** `packages/pitchmatch/pyproject.toml`, `packages/pitchmatch/src/fplguru_pitchmatch/__init__.py`, `packages/pitchmatch/tests/test_pitchmatch.py`; `requirements-dev.txt`, `pyproject.toml`.

- [ ] **Step 1: skeleton** (`name = "fplguru-pitchmatch"`, no deps, `packages = ["src/fplguru_pitchmatch"]`).
  Add to `requirements-dev.txt` + `known-first-party` (`"fplguru_pitchmatch"`). `pip install -r requirements-dev.txt`.

- [ ] **Step 2: failing test** — `packages/pitchmatch/tests/test_pitchmatch.py`:
```python
from fplguru_pitchmatch import match_players, match_teams, normalize_match_xg


def test_match_teams_by_normalized_name_and_alias():
    fpl = [{"id": 11, "name": "Man City", "short_name": "MCI"},
           {"id": 12, "name": "Nott'm Forest", "short_name": "NFO"}]
    pitch = [{"id": "t_a", "name": "Manchester City"},
             {"id": "t_b", "name": "Nottingham Forest"},
             {"id": "t_c", "name": "Unknown FC"}]
    got = match_teams(fpl, pitch)
    assert got == {"t_a": 11, "t_b": 12}          # t_c unmatched -> omitted


def test_match_players_uses_surname_initial_and_team():
    fpl = [
        {"id": 1, "web_name": "Haaland", "first_name": "Erling", "second_name": "Haaland",
         "team_id": 11},
        {"id": 2, "web_name": "B.Silva", "first_name": "Bernardo", "second_name": "Silva",
         "team_id": 11},
        {"id": 3, "web_name": "Silva", "first_name": "Thiago", "second_name": "Silva",
         "team_id": 12},
    ]
    pitch = [
        {"player": {"id": "p_h", "name": "E. Haaland"}, "team_id": "t_a"},
        {"player": {"id": "p_s", "name": "B. Silva"}, "team_id": "t_a"},
        {"player": {"id": "p_x", "name": "Zz Nobody"}, "team_id": "t_a"},
    ]
    team_map = {"t_a": 11}
    matched, unmatched = match_players(fpl, pitch, team_map)
    assert matched == {"p_h": 1, "p_s": 2}        # surname + initial + team
    assert [u["player"]["id"] for u in unmatched] == ["p_x"]


def test_normalize_match_xg_merges_shots_and_advanced():
    shots = [
        {"player": {"id": "p_h"}, "expected_goals": 0.3, "expected_goals_on_target": 0.2},
        {"player": {"id": "p_h"}, "expected_goals": 0.15},
        {"player": {"id": "p_s"}, "expected_goals": 0.05},
    ]
    adv = [
        {"player": {"id": "p_h"}, "minutes_played": 90,
         "possession_value": {"vaep_total": 0.8},
         "passing": {"key_passes": 1}, "creation": {"xag": 0.22, "chances_created": 2}},
        {"player": {"id": "p_s"}, "minutes_played": 78,
         "creation": {"xag": 0.4}},
    ]
    rows = {r["pitch_player_id"]: r for r in normalize_match_xg(shots, adv)}
    assert round(rows["p_h"]["xg"], 2) == 0.45
    assert round(rows["p_h"]["xg_ot"], 2) == 0.20
    assert rows["p_h"]["xag"] == 0.22
    assert rows["p_h"]["minutes"] == 90
    assert rows["p_h"]["key_passes"] == 1
    assert rows["p_h"]["vaep"] == 0.8
    assert rows["p_s"]["xg"] == 0.05 and rows["p_s"]["xag"] == 0.4 and rows["p_s"]["minutes"] == 78
```

- [ ] **Step 3: implement `packages/pitchmatch/src/fplguru_pitchmatch/__init__.py`**
```python
"""Pure PitchAPI <-> FPL identity matching + match xG normalization."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

__all__ = ["match_teams", "match_players", "normalize_match_xg"]

# PitchAPI full name -> FPL short name fragments that don't normalize cleanly
_TEAM_ALIASES = {
    "manchester city": "man city",
    "manchester united": "man utd",
    "manchester utd": "man utd",
    "newcastle united": "newcastle",
    "tottenham hotspur": "spurs",
    "tottenham": "spurs",
    "wolverhampton wanderers": "wolves",
    "nottingham forest": "nott m forest",
    "brighton hove albion": "brighton",
    "brighton and hove albion": "brighton",
    "west ham united": "west ham",
    "sheffield united": "sheffield utd",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).strip()


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def match_teams(fpl_teams: list[dict[str, Any]],
                pitch_teams: list[dict[str, Any]]) -> dict[str, int]:
    by_norm: dict[str, int] = {}
    for t in fpl_teams:
        by_norm[_squash(_norm(t["name"]))] = t["id"]
        by_norm[_squash(_norm(t["short_name"]))] = t["id"]
    out: dict[str, int] = {}
    for pt in pitch_teams:
        n = _squash(_norm(pt["name"]))
        n = _TEAM_ALIASES.get(n, n)
        if n in by_norm:
            out[pt["id"]] = by_norm[n]
            continue
        # last resort: token-subset (e.g. "everton" in "everton fc")
        hit = next((fid for key, fid in by_norm.items()
                    if key and (key in n or n in key)), None)
        if hit is not None:
            out[pt["id"]] = hit
    return out


def _pitch_last_first(name: str) -> tuple[str, str]:
    parts = _norm(name).split()
    if not parts:
        return "", ""
    last = parts[-1]
    first_initial = parts[0][0] if parts[0] else ""
    return last, first_initial


def match_players(fpl_players: list[dict[str, Any]], pitch_players: list[dict[str, Any]],
                  team_map: dict[str, int]) -> tuple[dict[str, int], list[dict]]:
    # index FPL players by (team_id, surname)
    idx: dict[tuple[int, str], list[dict]] = {}
    for p in fpl_players:
        surname = _norm(p["second_name"]).split()[-1] if p.get("second_name") else _norm(
            p["web_name"]).split()[-1]
        idx.setdefault((p["team_id"], surname), []).append(p)

    matched: dict[str, int] = {}
    unmatched: list[dict] = []
    for pp in pitch_players:
        pid = pp["player"]["id"]
        fpl_team = team_map.get(pp.get("team_id"))
        last, initial = _pitch_last_first(pp["player"].get("name", ""))
        cands = idx.get((fpl_team, last), []) if fpl_team is not None else []
        if len(cands) == 1:
            matched[pid] = cands[0]["id"]
        elif len(cands) > 1 and initial:
            narrowed = [c for c in cands if _norm(c["first_name"])[:1] == initial]
            if len(narrowed) == 1:
                matched[pid] = narrowed[0]["id"]
            else:
                unmatched.append(pp)
        else:
            unmatched.append(pp)
    return matched, unmatched


def _f(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def normalize_match_xg(shots: list[dict[str, Any]],
                       advanced: list[dict[str, Any]]) -> list[dict]:
    agg: dict[str, dict] = {}
    for s in shots:
        pid = (s.get("player") or {}).get("id")
        if not pid:
            continue
        r = agg.setdefault(pid, {"pitch_player_id": pid, "xg": 0.0, "xg_ot": 0.0,
                                 "xag": 0.0, "minutes": 0, "key_passes": 0,
                                 "chances_created": 0, "vaep": 0.0})
        r["xg"] += _f(s.get("expected_goals"))
        r["xg_ot"] += _f(s.get("expected_goals_on_target"))
    for a in advanced:
        pid = (a.get("player") or {}).get("id")
        if not pid:
            continue
        r = agg.setdefault(pid, {"pitch_player_id": pid, "xg": 0.0, "xg_ot": 0.0,
                                 "xag": 0.0, "minutes": 0, "key_passes": 0,
                                 "chances_created": 0, "vaep": 0.0})
        r["minutes"] = int(_f(a.get("minutes_played")))
        r["xag"] = _f((a.get("creation") or {}).get("xag"))
        r["chances_created"] = int(_f((a.get("creation") or {}).get("chances_created")))
        r["key_passes"] = int(_f((a.get("passing") or {}).get("key_passes")))
        r["vaep"] = _f((a.get("possession_value") or {}).get("vaep_total"))
    return list(agg.values())
```

- [ ] **Step 4:** `python -m pytest packages/pitchmatch -q` → **3 passed**. `python -m pytest -q -W error` → **186 passed**. `ruff` clean.
  `feat(pitchmatch): fplguru-pitchmatch — id matching + match xG normalizer`

---

## Task 3: models + `0011` migration + settings

**Files:** `packages/core/.../models.py`, `packages/core/.../settings.py`, `packages/core/tests/test_models.py`, `packages/core/tests/test_pitch_model.py` (new), `alembic/versions/0011_pitch_xg.py`.

- [ ] **Step 1: failing test** — `packages/core/tests/test_pitch_model.py`:
```python
from fplguru_core.models import Base, PitchPlayerMap, PitchTeamMap, PlayerXg


def test_pitch_tables_registered_with_keys():
    assert {"pitch_team_map", "pitch_player_map", "player_xg"} <= set(Base.metadata.tables)
    tm = {tuple(sorted(c.name for c in con.columns))
          for con in PitchTeamMap.__table__.constraints
          if con.__class__.__name__ == "UniqueConstraint"}
    assert ("pitch_team_id",) in tm
    pm = {tuple(sorted(c.name for c in con.columns))
          for con in PitchPlayerMap.__table__.constraints
          if con.__class__.__name__ == "UniqueConstraint"}
    assert ("pitch_player_id",) in pm
    xg = {tuple(sorted(c.name for c in con.columns))
          for con in PlayerXg.__table__.constraints
          if con.__class__.__name__ == "UniqueConstraint"}
    assert ("fixture_id", "player_id") in xg
```
Add `"pitch_team_map"`, `"pitch_player_map"`, `"player_xg"` to `test_models.py::test_expected_tables_registered`.

- [ ] **Step 2: settings** — add:
```python
    pitchapi_key: str = ""
    pitchapi_base: str = "https://api.pitchapi.dev/v1"
```

- [ ] **Step 3: models** — after the last model:
```python
class PitchTeamMap(_TimestampMixin, Base):
    __tablename__ = "pitch_team_map"
    __table_args__ = (UniqueConstraint("pitch_team_id", name="uq_pitch_team_map_pitch_team_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pitch_team_id: Mapped[str] = mapped_column(String(24))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    pitch_name: Mapped[str] = mapped_column(String(64), default="")


class PitchPlayerMap(_TimestampMixin, Base):
    __tablename__ = "pitch_player_map"
    __table_args__ = (
        UniqueConstraint("pitch_player_id", name="uq_pitch_player_map_pitch_player_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pitch_player_id: Mapped[str] = mapped_column(String(24))
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True, index=True)
    pitch_name: Mapped[str] = mapped_column(String(64), default="")
    method: Mapped[str] = mapped_column(String(12), default="auto")  # auto | manual | unmatched


class PlayerXg(_TimestampMixin, Base):
    """Per-player xG/xA for one fixture, from PitchAPI."""
    __tablename__ = "player_xg"
    __table_args__ = (
        UniqueConstraint("player_id", "fixture_id", name="uq_player_xg_player_id_fixture_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    xg: Mapped[float] = mapped_column(Float, default=0.0)
    xg_ot: Mapped[float] = mapped_column(Float, default=0.0)
    xag: Mapped[float] = mapped_column(Float, default=0.0)
    key_passes: Mapped[int] = mapped_column(Integer, default=0)
    chances_created: Mapped[int] = mapped_column(Integer, default=0)
    vaep: Mapped[float] = mapped_column(Float, default=0.0)
    pitch_match_id: Mapped[str] = mapped_column(String(24), default="")
```

- [ ] **Step 4: migration `alembic/versions/0011_pitch_xg.py`** — `revision='0011'`, `down_revision='0010'`;
  three `create_table` + their indexes, mirroring the style of `0008_leagues.py`. `pitch_team_map`
  FKs `teams`; `pitch_player_map.player_id` nullable FK `players`; `player_xg` FKs `players`,
  `fixtures`, `gameweeks`. UQ names exactly as in the models.

- [ ] **Step 5:** `python -m alembic upgrade head`; `python -m alembic check` → clean.
  `python -m pytest packages/core -q` → pass. `python -m pytest -q -W error` → **187 passed**.
  `ruff` clean. `feat(core): pitch_team_map + pitch_player_map + player_xg (0011)`

---

## Task 4: worker `sync_xg`

**Files:** `services/worker/.../tasks.py`, `services/worker/.../app.py`, `services/worker/tests/test_beat_schedule.py`, `services/api/src/fplguru_api/main.py` (add `"pitch_xg"` to `/status` `known`), `services/worker/tests/test_sync_xg.py` (new).

- [ ] **Step 1: failing test** — `services/worker/tests/test_sync_xg.py`:
```python
from datetime import UTC, datetime

from sqlalchemy import select

from fplguru_core.models import (
    Fixture, Gameweek, PitchPlayerMap, PitchTeamMap, Player, PlayerXg, Team,
)
from fplguru_worker import tasks


class _FakePitch:
    def __init__(self, key, base=None, http=None):
        pass
    async def matches_on(self, date):
        return [{"id": "m_1", "status": "finished", "time_utc": f"{date}T15:00:00Z",
                 "home_team": {"id": "t_h", "name": "Home FC"},
                 "away_team": {"id": "t_a", "name": "Away FC"}}]
    async def match_advanced_players(self, mid):
        return [{"player": {"id": "p_1", "name": "E. Home"}, "team_id": "t_h",
                 "minutes_played": 90, "creation": {"xag": 0.3}}]
    async def match_shots(self, mid):
        return [{"player": {"id": "p_1"}, "expected_goals": 0.4}]
    async def aclose(self):
        pass


async def _seed(db_session):
    db_session.add_all([Team(id=1, name="Home FC", short_name="HOM"),
                        Team(id=2, name="Away FC", short_name="AWY")])
    db_session.add(Gameweek(id=5, name="GW5", deadline_time=datetime(2025, 11, 8, tzinfo=UTC),
                            finished=True))
    await db_session.commit()
    db_session.add(Player(id=1, team_id=1, first_name="Erling", second_name="Home",
                          web_name="Home", position="FWD", now_cost=90, status="a"))
    db_session.add(Fixture(id=50, gameweek_id=5, home_team_id=1, away_team_id=2,
                           home_difficulty=3, away_difficulty=3, finished=True,
                           kickoff_time=datetime(2025, 11, 9, 15, 0, tzinfo=UTC)))
    await db_session.commit()


async def test_sync_xg_maps_ids_and_upserts_player_xg(db_session, monkeypatch):
    await _seed(db_session)
    monkeypatch.setattr(tasks, "PitchClient", _FakePitch)
    monkeypatch.setenv("FPLGURU_PITCHAPI_KEY", "pk_test_x")
    await tasks._sync_xg()

    xg = (await db_session.execute(select(PlayerXg))).scalars().all()
    assert len(xg) == 1
    assert xg[0].player_id == 1 and xg[0].fixture_id == 50 and xg[0].gameweek_id == 5
    assert round(xg[0].xg, 2) == 0.4 and xg[0].xag == 0.3 and xg[0].minutes == 90
    # id maps were seeded
    assert (await db_session.execute(select(PitchTeamMap))).scalars().first().team_id == 1
    assert (await db_session.execute(
        select(PitchPlayerMap).where(PitchPlayerMap.pitch_player_id == "p_1")
    )).scalar_one().player_id == 1

    await tasks._sync_xg()   # idempotent
    assert len((await db_session.execute(select(PlayerXg))).scalars().all()) == 1


async def test_sync_xg_noop_without_key(db_session, monkeypatch):
    await _seed(db_session)
    monkeypatch.delenv("FPLGURU_PITCHAPI_KEY", raising=False)
    await tasks._sync_xg()
    assert (await db_session.execute(select(PlayerXg))).first() is None
```

- [ ] **Step 2: implement in `tasks.py`**

Imports: `PitchTeamMap`, `PitchPlayerMap`, `PlayerXg` to `fplguru_core.models`; `from fplguru_pitch import PitchApiError, PitchClient`; `from fplguru_pitchmatch import match_players, match_teams, normalize_match_xg` (isort order). Add after `_sync_league_standings`:
```python
async def _sync_xg() -> None:
    started = datetime.now(UTC)
    key = get_settings().pitchapi_key
    if not key:
        async with get_sessionmaker()() as session, session.begin():
            await _record(session, "pitch_xg", "ok", started, "no pitchapi key")
        return
    try:
        async with get_sessionmaker()() as session:
            teams = {t.id: t for t in (await session.execute(select(Team))).scalars().all()}
            players = [
                {"id": p.id, "web_name": p.web_name, "first_name": p.first_name,
                 "second_name": p.second_name, "team_id": p.team_id}
                for p in (await session.execute(select(Player))).scalars().all()
            ]
            team_map = {m.pitch_team_id: m.team_id for m in
                        (await session.execute(select(PitchTeamMap))).scalars().all()}
            done_fixture_ids = set((await session.execute(
                select(PlayerXg.fixture_id).distinct()
            )).scalars().all())
            fixtures = [
                f for f in (await session.execute(
                    select(Fixture).join(Gameweek, Gameweek.id == Fixture.gameweek_id)
                    .where(Gameweek.finished.is_(True), Fixture.finished.is_(True),
                           Fixture.kickoff_time.is_not(None))
                )).scalars().all()
                if f.id not in done_fixture_ids
            ]

        client = PitchClient(key, base=get_settings().pitchapi_base)
        new_team_maps: dict[str, int] = {}
        new_player_maps: dict[str, tuple[int | None, str, str]] = {}
        pt_name: dict[str, str] = {}   # pitch_team_id -> name, accumulated across dates
        xg_rows: list[dict] = []
        try:
            by_date: dict[str, list] = {}
            for f in fixtures:
                by_date.setdefault(f.kickoff_time.date().isoformat(), []).append(f)
            for date, day_fixtures in by_date.items():
                matches = await client.matches_on(date)
                # resolve/extend the team map from this day's matches
                pitch_teams = []
                for m in matches:
                    for side in ("home_team", "away_team"):
                        if m.get(side):
                            pitch_teams.append(m[side])
                fresh = match_teams(
                    [{"id": t.id, "name": t.name, "short_name": t.short_name}
                     for t in teams.values()], pitch_teams)
                pt_name.update({pt["id"]: pt.get("name", "") for pt in pitch_teams})
                for ptid, fid in fresh.items():
                    if ptid not in team_map:
                        team_map[ptid] = fid
                        new_team_maps[ptid] = fid
                for f in day_fixtures:
                    match = next((
                        m for m in matches
                        if team_map.get((m.get("home_team") or {}).get("id")) == f.home_team_id
                        and team_map.get((m.get("away_team") or {}).get("id")) == f.away_team_id
                    ), None)
                    if match is None:
                        continue
                    adv = await client.match_advanced_players(match["id"])
                    shots = await client.match_shots(match["id"])
                    matched, unmatched = match_players(players, adv, team_map)
                    for pp in unmatched:
                        new_player_maps.setdefault(
                            pp["player"]["id"],
                            (None, pp["player"].get("name", ""), "unmatched"))
                    for ptid, fid in matched.items():
                        new_player_maps[ptid] = (fid, "", "auto")
                    for row in normalize_match_xg(shots, adv):
                        fpl_pid = matched.get(row["pitch_player_id"])
                        if fpl_pid is None:
                            continue
                        xg_rows.append({
                            "player_id": fpl_pid, "fixture_id": f.id,
                            "gameweek_id": f.gameweek_id, "pitch_match_id": match["id"],
                            **{k: row[k] for k in ("minutes", "xg", "xg_ot", "xag",
                                                   "key_passes", "chances_created", "vaep")},
                        })
        finally:
            await client.aclose()

        async with get_sessionmaker()() as session, session.begin():
            for ptid, fid in new_team_maps.items():
                session.add(PitchTeamMap(pitch_team_id=ptid, team_id=fid,
                                         pitch_name=pt_name.get(ptid, "")))
            existing_pm = set((await session.execute(
                select(PitchPlayerMap.pitch_player_id)
            )).scalars().all())
            for ptid, (fid, name, method) in new_player_maps.items():
                if ptid in existing_pm:
                    continue
                session.add(PitchPlayerMap(pitch_player_id=ptid, player_id=fid,
                                           pitch_name=name, method=method))
            await _upsert_xg(session, xg_rows)
            await _record(session, "pitch_xg", "ok", started,
                          f"{len(xg_rows)} rows / {len(fixtures)} fixtures")
        logger.info("xg synced: %d rows over %d fixtures", len(xg_rows), len(fixtures))
    except PitchApiError as exc:
        await _log_error("pitch_xg", started, exc)   # fragility signal: surfaces on /status
        raise
    except Exception as exc:
        await _log_error("pitch_xg", started, exc)
        raise


async def _upsert_xg(session, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(PlayerXg).values(rows)
    cols = {c: stmt.excluded[c] for c in rows[0] if c not in ("player_id", "fixture_id")}
    cols["updated_at"] = func.now()
    await session.execute(stmt.on_conflict_do_update(
        index_elements=["player_id", "fixture_id"], set_=cols))


@celery_app.task(name="sync_xg", bind=True, max_retries=2, default_retry_delay=300)
def sync_xg(self) -> None:
    try:
        asyncio.run(_run_and_dispose(_sync_xg))
    except Exception as exc:
        raise self.retry(exc=exc) from exc
```
(`new_team_maps` uses the `name` var — keep it or drop the unused local; the reviewer/ruff will
flag `name` if unused, so either store it on `PitchTeamMap.pitch_name` or remove it.)

- [ ] **Step 3: Beat + `/status`** — `app.py`: `"sync-xg": {"task": "sync_xg", "schedule": 86400.0}` (daily). `test_beat_schedule.py`: `assert sched["sync-xg"]["task"] == "sync_xg"`. `main.py` `/status`: `known = {..., "pitch_xg"}`.

- [ ] **Step 4:** `python -m pytest services/worker/tests/test_sync_xg.py services/worker/tests/test_beat_schedule.py -q` → **3 passed**. `python -m pytest -q -W error` → **190 passed**. `ruff` clean, `alembic check` clean.
  `feat(worker): sync_xg — PitchAPI xG ingestion + id-map seeding + fragility logging`

---

## Task 5: ops scripts

**Files:** create `scripts/pitch_probe.py`, `scripts/pitch_map.py`, `scripts/backfill_xg.py`.

- [ ] **Step 1: `scripts/pitch_probe.py`** — `python scripts/pitch_probe.py 2025-11-09` → prints
  `matches_on(date)` then, for the first match, the raw `match_advanced_players` + `match_shots`
  JSON (pretty). Purpose: **verify the assumed response shapes before trusting the normalizer.**
  Uses `PitchClient(get_settings().pitchapi_key, base=get_settings().pitchapi_base)`.

- [ ] **Step 2: `scripts/pitch_map.py`** — `python scripts/pitch_map.py p_7YtX4q 233` upserts a
  `PitchPlayerMap(pitch_player_id="p_7YtX4q", player_id=233, method="manual")` (overwriting an
  `unmatched`/`auto` row). `--list-unmatched` prints rows where `player_id IS NULL`.

- [ ] **Step 3: `scripts/backfill_xg.py`** — `python scripts/backfill_xg.py 2024-08-01 2025-05-25`
  loops dates in the range and calls the same per-date logic as `_sync_xg` (import a shared
  `_ingest_dates(dates: list[str])` helper factored out of `_sync_xg`, or just call
  `tasks._sync_xg()` after temporarily widening the fixture filter — simplest: add an optional
  `only_dates: set[str] | None` param to `_sync_xg` and have the script pass the range).
  Keep it minimal; no tests beyond `python -c "import scripts.backfill_xg"` style import checks
  are required, but `ruff` must pass on all three.

- [ ] **Step 4:** `python -m ruff check scripts/` → clean. `python -m pytest -q -W error` → **190 passed** (unchanged). Commit `chore: PitchAPI ops scripts (probe / map / backfill)`.

---

## Task 6: API — `GET /players/{id}/xg` + `GET /xg-snapshot`

**Files:** `services/api/src/fplguru_api/main.py`, `services/api/pyproject.toml`, `services/api/tests/test_xg_api.py` (new).

- [ ] **Step 1: deps** — add `"fplguru-pitchmatch"`? no — the API doesn't import it. **No dep change**
  (delete this step). `PlayerXg` comes from `fplguru-core`.

- [ ] **Step 2: failing test** — `services/api/tests/test_xg_api.py`:
```python
from datetime import UTC, datetime

from fplguru_core.models import Gameweek, Player, PlayerXg, Team


async def _seed(db_session):
    db_session.add(Team(id=1, name="A", short_name="A"))
    db_session.add_all([
        Gameweek(id=g, name=f"GW{g}", deadline_time=datetime(2025, 9, g, tzinfo=UTC),
                 finished=True)
        for g in (3, 4, 5)
    ])
    await db_session.commit()
    db_session.add_all([
        Player(id=1, team_id=1, first_name="a", second_name="b", web_name="Salah",
               position="MID", now_cost=130, status="a"),
        Player(id=2, team_id=1, first_name="c", second_name="d", web_name="Isak",
               position="FWD", now_cost=100, status="a"),
    ])
    await db_session.commit()
    db_session.add_all([
        PlayerXg(player_id=1, fixture_id=30, gameweek_id=3, minutes=90, xg=0.4, xag=0.2),
        PlayerXg(player_id=1, fixture_id=40, gameweek_id=4, minutes=90, xg=0.7, xag=0.1),
        PlayerXg(player_id=1, fixture_id=50, gameweek_id=5, minutes=80, xg=0.2, xag=0.5),
        PlayerXg(player_id=2, fixture_id=50, gameweek_id=5, minutes=90, xg=1.1, xag=0.0),
    ])
    await db_session.commit()


async def test_player_xg_series_recent_first(client, db_session):
    await _seed(db_session)
    body = (await client.get("/players/1/xg?last=2")).json()
    assert [r["gameweek_id"] for r in body["per_gw"]] == [5, 4]
    assert round(body["totals"]["xg"], 1) == 0.9        # 0.2 + 0.7
    assert body["web_name"] == "Salah"


async def test_xg_snapshot_ranks_by_xg_plus_xag(client, db_session):
    await _seed(db_session)
    body = (await client.get("/xg-snapshot?last=3")).json()
    # player 2: xg 1.1 + xag 0.0 = 1.1 ; player 1: xg 1.3 + xag 0.8 = 2.1
    assert [r["player_id"] for r in body["players"]] == [1, 2]
    assert body["players"][0]["xg"] == 1.3


async def test_xg_snapshot_position_filter(client, db_session):
    await _seed(db_session)
    body = (await client.get("/xg-snapshot?last=3&position=FWD")).json()
    assert [r["player_id"] for r in body["players"]] == [2]


async def test_player_xg_404_when_no_data(client, db_session):
    await _seed(db_session)
    assert (await client.get("/players/999/xg")).status_code == 404
```

- [ ] **Step 3: implement in `main.py`** — add `PlayerXg` to the models import. Then:
```python
def _xg_row(r: PlayerXg) -> dict:
    return {"gameweek_id": r.gameweek_id, "fixture_id": r.fixture_id, "minutes": r.minutes,
            "xg": r.xg, "xg_ot": r.xg_ot, "xag": r.xag, "key_passes": r.key_passes,
            "chances_created": r.chances_created, "vaep": r.vaep}


@app.get("/players/{player_id}/xg")
async def player_xg(player_id: int, last: int = Query(6, ge=1, le=38),
                    db: AsyncSession = Depends(get_db)) -> dict:
    player = (await db.execute(
        select(Player).where(Player.id == player_id))).scalar_one_or_none()
    rows = (await db.execute(
        select(PlayerXg).where(PlayerXg.player_id == player_id)
        .order_by(PlayerXg.gameweek_id.desc(), PlayerXg.fixture_id.desc())
        .limit(last)
    )).scalars().all()
    if player is None or not rows:
        raise HTTPException(status_code=404, detail="no xg for player")
    tot = {k: round(sum(getattr(r, k) for r in rows), 3)
           for k in ("xg", "xg_ot", "xag")}
    tot["minutes"] = sum(r.minutes for r in rows)
    return {"player_id": player.id, "web_name": player.web_name, "position": player.position,
            "totals": tot, "per_gw": [_xg_row(r) for r in rows]}


@app.get("/xg-snapshot")
async def xg_snapshot(last: int = Query(6, ge=1, le=15),
                      position: str | None = Query(None),
                      db: AsyncSession = Depends(get_db)) -> dict:
    max_gw = (await db.execute(select(func.max(PlayerXg.gameweek_id)))).scalar()
    if max_gw is None:
        return {"from_gw": None, "players": []}
    lo = max_gw - last + 1
    q = (
        select(Player, func.sum(PlayerXg.xg), func.sum(PlayerXg.xag),
               func.sum(PlayerXg.minutes))
        .join(PlayerXg, PlayerXg.player_id == Player.id)
        .where(PlayerXg.gameweek_id >= lo)
        .group_by(Player.id)
    )
    if position:
        q = q.where(Player.position == position)
    rows = (await db.execute(q)).all()
    players = sorted(
        ({"player_id": p.id, "web_name": p.web_name, "position": p.position,
          "team_id": p.team_id, "xg": round(float(xg or 0), 2), "xag": round(float(xa or 0), 2),
          "minutes": int(mins or 0)}
         for p, xg, xa, mins in rows),
        key=lambda d: d["xg"] + d["xag"], reverse=True,
    )
    return {"from_gw": lo, "players": players}
```

- [ ] **Step 4:** `python -m pytest services/api/tests/test_xg_api.py -q` → **4 passed**. `python -m pytest -q -W error` → **194 passed**. `ruff` clean.
  `feat(api): GET /players/{id}/xg + GET /xg-snapshot`

---

## Task 7: web — xG snapshot tab

**Files:** `apps/web/src/lib/api.ts`, `apps/web/src/lib/api.xg.test.ts` (new), `apps/web/src/app/tools/ToolsHub.tsx`.

- [ ] **Step 1: failing test** — `apps/web/src/lib/api.xg.test.ts`:
```ts
import { describe, expect, it, vi } from "vitest";

import { getXgSnapshot } from "./api";

describe("getXgSnapshot", () => {
  it("passes last + position", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ players: [] }) });
    global.fetch = f as unknown as typeof fetch;
    await getXgSnapshot("http://api.test", 6, "MID");
    expect(String(f.mock.calls[0][0])).toContain("last=6");
    expect(String(f.mock.calls[0][0])).toContain("position=MID");
  });
});
```

- [ ] **Step 2: `api.ts`** append:
```ts
export type XgRow = {
  player_id: number;
  web_name: string;
  position: string;
  team_id: number;
  xg: number;
  xag: number;
  minutes: number;
};
export type XgSnapshot = { from_gw: number | null; players: XgRow[] };

export function getXgSnapshot(base: string, last = 6, position?: string) {
  const q = new URLSearchParams({ last: String(last) });
  if (position) q.set("position", position);
  return fetch(`${base}/xg-snapshot?${q}`, { cache: "no-store" }).then(asJson<XgSnapshot>);
}
```

- [ ] **Step 3: `ToolsHub.tsx`** — add `"xG"` to `TABS`; on that tab fetch `getXgSnapshot(API, 6)`
  and render a table (Player · Pos · xG · xA · min), plus a position `<select>` (All/GK/DEF/MID/FWD)
  that re-fetches. Empty state: "No xG data yet — the `sync_xg` task fills this after matches."

- [ ] **Step 4:** `./node_modules/.bin/vitest run` → **19 passed** (18 + 1). `./node_modules/.bin/next build` → success.
  `feat(web): xG snapshot tab on /tools`

---

## Task 8: docs

**Files:** `README.md`, `docs/plans/2026-08-27-fplguru-master-build-plan.md`, `docs/RESUME-foundation.md`.

- [ ] **Step 1: `README.md`** — new "xG (PitchAPI)" section: `sync_xg` worker task (Beat, daily)
  resolves finished fixtures → PitchAPI matches, maps ids (`pitch_team_map` / `pitch_player_map`,
  auto surname+initial+team match; fix misses with `scripts/pitch_map.py`), upserts `player_xg`.
  Endpoints `GET /players/{id}/xg?last=6`, `GET /xg-snapshot?last=6&position=`. **Blank
  `FPLGURU_PITCHAPI_KEY` → the task is a no-op.** Note `scripts/pitch_probe.py` verifies the live
  response shape (the normalizers were written against the published docs). Add `sync_xg` to the
  worker task list.
- [ ] **Step 2: master plan** — mark **P2a** ✅ (branch `feature/p2a-pitchapi-xg`); one-line summary;
  note it **unblocks P2b (Advanced xP)**; list deferrals: team-level xG, shot-level storage,
  automated season backfill scheduling, ops alerting on fragility, manual-map HTTP endpoint.
  Decrement remaining count.
- [ ] **Step 3: `docs/RESUME-foundation.md`** — top status line + a `## P2a` section (task table +
  commits + the "shapes are from docs, verify with `pitch_probe.py`" caveat) + note P2b is next
  unblocked.
- [ ] **Step 4: full verification** — `pytest -q -W error` → **194 passed**; `ruff` clean;
  `alembic check` clean; web `vitest run` → 19 passed; `next build` → success.
- [ ] **Step 5:** `docs: P2a PitchAPI xG ingestion complete`

---

## Self-Review

**Spec coverage (master §3 P2a / PRD §5.3, §5.6, §10.1):**
- Player + team xG/xA ingested → `player_xg` (xg from shot sums, xag from advanced) + `pitch_team_map`;
  team-level xG rollups are a follow-up ✓ (partial)
- Mapped to FPL player IDs → `match_players` (surname + first-initial + mapped team), stored in
  `pitch_player_map`; unmatched parked with `method="unmatched"` + `scripts/pitch_map.py` override ✓
- Historical backfill → `scripts/backfill_xg.py` (date-range walk) ✓
- Fragility monitor (alert on scrape-shape change) → `_sync_xg` lets `PitchApiError` (401/404/non-JSON)
  and unexpected exceptions write a `DataSyncLog` error row via `_log_error`, surfaced on `/status`;
  429 is retried with `Retry-After`. A push/email ops-alert is a documented follow-up ✓ (partial)

**Type/name consistency:**
- `PitchClient(key, *, base, http)` methods `matches_on(date) -> list`, `match_advanced_players(id) -> list`,
  `match_shots(id) -> list` — Task 1 defs == Task 4 fake + calls ✓
- `match_teams(fpl_teams, pitch_teams) -> {pitch_id: fpl_id}`, `match_players(fpl_players,
  pitch_players, team_map) -> (matched, unmatched)`, `normalize_match_xg(shots, advanced) -> [rows]`
  with row keys `pitch_player_id, xg, xg_ot, xag, minutes, key_passes, chances_created, vaep`
  — Task 2 defs == Task 4 use ✓
- `PlayerXg` cols == `_upsert_xg` conflict-safe set == `xg_rows` dict keys (`player_id, fixture_id,
  gameweek_id, pitch_match_id` + the six metrics) == migration ✓; UQ `(player_id, fixture_id)` ==
  `_upsert_xg` index_elements ✓
- API JSON (`per_gw` rows, `totals`, snapshot `players`) == web `XgRow` / `XgSnapshot` ✓

**Migration drift:** `0011` adds three tables; `alembic check` in Task 3 Step 5;
`test_expected_tables_registered` updated same task. No `server_default` on `player_xg` floats
(model `default=0.0` Python-side only).

**Placeholder scan:** Task 4's `_sync_xg` is large — a reviewer should confirm the day→fixture
grouping and the match-resolution `next(...)`; behaviour is fully specified by the two tests. Task 5
scripts and Task 7 Step 3 are described, not fully coded — acceptable for spec-check (they are ops
glue / presentational; the API + normalizer shapes they depend on are complete). **All PitchAPI
response shapes are assumptions from the docs — flagged throughout; `pitch_probe.py` is the
gate before a real sync.**

---

## Execution Handoff

Branch `feature/p2a-pitchapi-xg` off `main`. Subagent-driven, order 1 → 8. Task 1 (client) +
Task 2 (matcher/normalizer) + Task 4 (worker orchestration) get a full review; Tasks 3, 6
spec-check + quality-check; Tasks 5, 7, 8 spec-check. After Task 8: whole-branch review, PR →
`main`, watch CI, squash-merge. **Then P2b (Advanced xP) is unblocked** — but confirm the live
PitchAPI shapes with `pitch_probe.py` (needs the real key) before relying on ingested xG.

### Deferred follow-ups
- Verify/adjust normalizers against a live `pitch_probe.py` dump; widen `_TEAM_ALIASES` from the
  first real `sync_xg` run's `pitch_player_map` unmatched rows.
- Team-level xG / xGA rollup table (for FDR-xG and clean-sheet modelling).
- Store shot-level rows (`/matches/{id}/shots` full) for shot-map features.
- Ops alert (email/Slack/webhook) when `pitch_xg` logs an error — currently only visible on `/status`.
- Scheduled season backfill (currently a manual `scripts/backfill_xg.py` run).
- Fold xG/xag features into the P1c feature builder → **P2b Advanced xP**.
