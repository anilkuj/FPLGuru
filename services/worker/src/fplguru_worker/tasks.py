import asyncio
import json
import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from fplguru_alerts import (
    availability_alerts,
    deadline_reminder_alerts,
    dgw_bgw_alerts,
    score_alert,
)
from fplguru_core.db import dispose_engine, get_sessionmaker, reset_state
from fplguru_core.models import (
    DEFAULT_REMINDER_OFFSETS,
    Alert,
    DataSyncLog,
    EntryPick,
    Fixture,
    Gameweek,
    LeagueStanding,
    LinkedTeam,
    LinkedTeamLeague,
    Player,
    PlayerGwLive,
    PlayerGwStat,
    PushSubscription,
    Team,
)
from fplguru_core.settings import get_settings
from fplguru_fpl_client import FplClient
from fplguru_ingest.fpl import (
    normalize_event_live,
    normalize_fixtures,
    normalize_gameweeks,
    normalize_league_standings,
    normalize_players,
    normalize_teams,
)
from fplguru_live import build_live_rows
from fplguru_push import pending_push_targets
from fplguru_worker.app import celery_app
from fplguru_worker.entries import sync_entry
from fplguru_worker.xp import compute_and_store_xp

logger = logging.getLogger("fplguru.worker")


async def _upsert(session, model, rows: list[dict]) -> int:
    if not rows:
        return 0
    present = set(rows[0])
    stmt = pg_insert(model).values(rows)
    update_cols = {
        c.name: stmt.excluded[c.name]
        for c in model.__table__.columns
        if c.name != "id" and c.name in present
    }
    if "updated_at" in model.__table__.columns:
        update_cols["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols)
    await session.execute(stmt)
    return len(rows)


async def _record(
    session, source: str, status: str, started: datetime, detail: str = ""
) -> None:
    session.add(
        DataSyncLog(
            source=source,
            status=status,
            detail=detail,
            started_at=started,
            finished_at=datetime.now(UTC),
        )
    )


async def _log_error(source: str, started: datetime, exc: Exception) -> None:
    """Record an error row on a FRESH session so a broken connection on the
    working session cannot also swallow the audit trail."""
    logger.exception("%s sync failed", source)
    try:
        async with get_sessionmaker()() as session, session.begin():
            await _record(session, source, "error", started, str(exc)[:500])
    except Exception:
        logger.exception("could not record %s error row", source)


async def _sync_bootstrap() -> None:
    started = datetime.now(UTC)
    try:
        client = FplClient(get_settings().fpl_api_base)
        try:
            data = await client.bootstrap_static()
        finally:
            await client.aclose()
        async with get_sessionmaker()() as session, session.begin():
            n_t = await _upsert(session, Team, normalize_teams(data))
            n_g = await _upsert(session, Gameweek, normalize_gameweeks(data))
            n_p = await _upsert(session, Player, normalize_players(data))
            await _record(session, "fpl_bootstrap", "ok", started)
        logger.info("bootstrap synced: %d teams / %d gameweeks / %d players", n_t, n_g, n_p)
    except Exception as exc:
        await _log_error("fpl_bootstrap", started, exc)
        raise


async def _sync_fixtures() -> None:
    started = datetime.now(UTC)
    try:
        client = FplClient(get_settings().fpl_api_base)
        try:
            data = await client.fixtures()
        finally:
            await client.aclose()
        async with get_sessionmaker()() as session, session.begin():
            if not await session.scalar(select(func.count()).select_from(Team)):
                await _record(
                    session, "fpl_fixtures", "ok", started,
                    "skipped: teams not populated yet",
                )
                logger.info("fixtures sync skipped: teams table empty")
                return
            n = await _upsert(session, Fixture, normalize_fixtures(data))
            await _record(session, "fpl_fixtures", "ok", started)
        logger.info("fixtures synced: %d rows", n)
    except Exception as exc:
        await _log_error("fpl_fixtures", started, exc)
        raise


async def sync_all() -> None:
    """Bootstrap then fixtures in one event loop — the entry point for
    manual DB population:

        python - <<'PY'
        import asyncio
        from fplguru_worker.tasks import sync_all
        asyncio.run(sync_all())
        PY
    """
    await _sync_bootstrap()
    await _sync_fixtures()


async def _run_and_dispose(coro_fn) -> None:
    """Run one sync, then drop the process-cached engine so the next Celery
    task (a fresh event loop via asyncio.run) doesn't reuse asyncpg
    connections bound to a closed loop."""
    try:
        await coro_fn()
    finally:
        await dispose_engine()
        reset_state()


@celery_app.task(name="sync_bootstrap", bind=True, max_retries=3, default_retry_delay=60)
def sync_bootstrap(self) -> None:
    try:
        asyncio.run(_run_and_dispose(_sync_bootstrap))
    except Exception as exc:
        raise self.retry(exc=exc) from exc


@celery_app.task(name="sync_fixtures", bind=True, max_retries=3, default_retry_delay=60)
def sync_fixtures(self) -> None:
    try:
        asyncio.run(_run_and_dispose(_sync_fixtures))
    except Exception as exc:
        raise self.retry(exc=exc) from exc


async def _upsert_stats(session, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(PlayerGwStat).values(rows)
    update_cols = {
        c: stmt.excluded[c] for c in rows[0] if c not in ("player_id", "gameweek_id")
    }
    update_cols["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(
        index_elements=["player_id", "gameweek_id"], set_=update_cols
    )
    await session.execute(stmt)


async def _sync_gw_stats() -> None:
    started = datetime.now(UTC)
    try:
        async with get_sessionmaker()() as session, session.begin():
            finished_gw_ids = (
                await session.execute(
                    select(Gameweek.id).where(Gameweek.finished.is_(True)).order_by(Gameweek.id)
                )
            ).scalars().all()
            players = {
                p.id: p for p in (await session.execute(select(Player))).scalars().all()
            }
            fixtures = (
                await session.execute(
                    select(Fixture).where(Fixture.gameweek_id.in_(finished_gw_ids))
                )
            ).scalars().all()
            side: dict[tuple[int, int], tuple[bool, int]] = {}
            for f in fixtures:
                side[(f.gameweek_id, f.home_team_id)] = (True, f.away_team_id)
                side[(f.gameweek_id, f.away_team_id)] = (False, f.home_team_id)

        if not finished_gw_ids:
            async with get_sessionmaker()() as session, session.begin():
                await _record(session, "fpl_gw_stats", "ok", started, "no finished gameweeks")
            return

        client = FplClient(get_settings().fpl_api_base)
        rows: list[dict] = []
        try:
            for gw_id in finished_gw_ids:
                payload = await client.event_live(gw_id)
                for r in normalize_event_live(gw_id, payload):
                    p = players.get(r["player_id"])
                    if p is None:
                        continue
                    was_home, opp = side.get((gw_id, p.team_id), (False, None))
                    r["was_home"] = was_home
                    r["opponent_team_id"] = opp
                    r["value"] = p.now_cost
                    rows.append(r)
        finally:
            await client.aclose()

        async with get_sessionmaker()() as session, session.begin():
            await _upsert_stats(session, rows)
            await _record(session, "fpl_gw_stats", "ok", started, f"{len(rows)} rows")
        logger.info("gw stats synced: %d rows over %d gameweeks", len(rows), len(finished_gw_ids))
    except Exception as exc:
        await _log_error("fpl_gw_stats", started, exc)
        raise


@celery_app.task(name="sync_gw_stats", bind=True, max_retries=3, default_retry_delay=60)
def sync_gw_stats(self) -> None:
    try:
        asyncio.run(_run_and_dispose(_sync_gw_stats))
    except Exception as exc:
        raise self.retry(exc=exc) from exc


async def _upsert_live(session, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(PlayerGwLive).values(rows)
    update_cols = {
        c: stmt.excluded[c] for c in rows[0] if c not in ("player_id", "gameweek_id")
    }
    update_cols["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(
        index_elements=["player_id", "gameweek_id"], set_=update_cols
    )
    await session.execute(stmt)


async def _poll_live() -> None:
    started = datetime.now(UTC)
    try:
        async with get_sessionmaker()() as session:
            gw = (
                await session.execute(select(Gameweek).where(Gameweek.is_current))
            ).scalar_one_or_none()
        if gw is None:
            async with get_sessionmaker()() as session, session.begin():
                await _record(session, "live_poll", "ok", started, "no current gameweek")
            return

        client = FplClient(get_settings().fpl_api_base)
        try:
            all_fixtures = await client.fixtures()
            gw_fixtures = [f for f in all_fixtures if f.get("event") == gw.id]
            live = [f for f in gw_fixtures if f.get("started") and not f.get("finished")]
            payload = await client.event_live(gw.id) if live else None
        finally:
            await client.aclose()

        async with get_sessionmaker()() as session, session.begin():
            await _upsert(session, Fixture, normalize_fixtures(gw_fixtures))
            if payload is None:
                await _record(session, "live_poll", "ok", started, "no live fixtures")
                return
            rows = build_live_rows(gw.id, payload)
            await _upsert_live(session, rows)
            await _record(session, "live_poll", "ok", started, f"{len(rows)} rows")
        logger.info("live poll: %d players over %d live fixtures", len(rows), len(live))
    except Exception as exc:
        await _log_error("live_poll", started, exc)
        raise


@celery_app.task(name="poll_live", bind=True, max_retries=2, default_retry_delay=30)
def poll_live(self) -> None:
    try:
        asyncio.run(_run_and_dispose(_poll_live))
    except Exception as exc:
        raise self.retry(exc=exc) from exc


async def _upsert_alerts(session, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(Alert).values(rows)
    update_cols = {
        c: stmt.excluded[c]
        for c in rows[0]
        if c not in ("linked_team_id", "dedup_key", "seen_at")
    }
    update_cols["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(
        index_elements=["linked_team_id", "dedup_key"], set_=update_cols
    )
    await session.execute(stmt)


def _team_flag(by_player: dict, team_names: list[str], attr: str) -> bool:
    return any(p[attr] for p in by_player.values() if p["web_name"] in team_names)


async def _generate_alerts() -> None:
    started = datetime.now(UTC)
    try:
        async with get_sessionmaker()() as session, session.begin():
            gw = (
                await session.execute(select(Gameweek).where(Gameweek.is_current))
            ).scalar_one_or_none()
            if gw is None:
                await _record(session, "alerts", "ok", started, "no current gameweek")
                return
            now = datetime.now(UTC)
            before_deadline = gw.deadline_time > now
            next_dl_gw = (await session.execute(
                select(Gameweek).where(Gameweek.deadline_time > now)
                .order_by(Gameweek.deadline_time).limit(1)
            )).scalar_one_or_none()

            teams = (await session.execute(select(LinkedTeam))).scalars().all()
            fx_counts: dict[int, int] = {}
            for f in (await session.execute(
                select(Fixture).where(Fixture.gameweek_id == gw.id)
            )).scalars().all():
                fx_counts[f.home_team_id] = fx_counts.get(f.home_team_id, 0) + 1
                fx_counts[f.away_team_id] = fx_counts.get(f.away_team_id, 0) + 1

            total = 0
            for lt in teams:
                pick_gw = (await session.execute(
                    select(func.max(EntryPick.gameweek_id))
                    .where(EntryPick.linked_team_id == lt.id)
                )).scalar()
                if pick_gw is None:
                    continue
                picked = (await session.execute(
                    select(EntryPick, Player).join(Player, Player.id == EntryPick.player_id)
                    .where(EntryPick.linked_team_id == lt.id,
                           EntryPick.gameweek_id == pick_gw)
                )).all()
                picks = [{
                    "player_id": pl.id, "web_name": pl.web_name, "status": pl.status,
                    "chance_of_playing_next_round": pl.chance_of_playing_next_round,
                    "news": pl.news, "multiplier": ep.multiplier,
                    "is_captain": ep.is_captain, "is_vice": ep.is_vice, "team_id": pl.team_id,
                } for ep, pl in picked]
                by_player = {p["player_id"]: p for p in picks}
                owned_teams = {p["team_id"] for p in picks}
                names_by_team: dict[int, list[str]] = {}
                for p in picks:
                    names_by_team.setdefault(p["team_id"], []).append(p["web_name"])

                generated = availability_alerts(picks, gameweek_id=gw.id)
                if sum(fx_counts.values()) > 0:  # fixtures for this GW are loaded
                    generated += dgw_bgw_alerts(
                        owned_teams, fx_counts, names_by_team, gameweek_id=gw.id
                    )
                if next_dl_gw is not None:
                    generated += deadline_reminder_alerts(
                        next_dl_gw.deadline_time, now,
                        lt.reminder_offsets or list(DEFAULT_REMINDER_OFFSETS),
                        gameweek_id=next_dl_gw.id,
                    )
                rows = []
                for a in generated:
                    if a["player_id"]:
                        owner = by_player.get(a["player_id"])
                        in_xi = bool(owner and owner["multiplier"] > 0)
                        is_cap = bool(owner and (owner["is_captain"] or owner["is_vice"]))
                    else:
                        team_names = a["payload"].get("player_names", [])
                        in_xi = _team_flag(by_player, team_names, "multiplier")
                        is_cap = (
                            _team_flag(by_player, team_names, "is_captain")
                            or _team_flag(by_player, team_names, "is_vice")
                        )
                    rows.append({
                        "linked_team_id": lt.id,
                        "gameweek_id": a["gameweek_id"],
                        "type": a["type"],
                        "dedup_key": a["dedup_key"],
                        "player_id": a["player_id"],
                        "title": a["title"],
                        "body": a["body"],
                        "payload": a["payload"],
                        "priority": score_alert(
                            a, in_xi=in_xi, is_captain=is_cap,
                            before_deadline=before_deadline,
                        ),
                        "suppressed": False,
                    })
                await _upsert_alerts(session, rows)
                total += len(rows)

                # cap application per distinct gameweek this team has alerts in
                team_gw_ids = {r["gameweek_id"] for r in rows} | {gw.id}
                for gwid in team_gw_ids:
                    ranked = (await session.execute(
                        select(Alert)
                        .where(Alert.linked_team_id == lt.id, Alert.gameweek_id == gwid)
                        .order_by(Alert.priority.desc(), Alert.id)
                    )).scalars().all()
                    for i, row in enumerate(ranked):
                        row.suppressed = lt.alert_cap is not None and i >= lt.alert_cap

            await _record(
                session, "alerts", "ok", started,
                f"{total} alerts over {len(teams)} teams",
            )
        logger.info("alerts generated: %d rows", total)
    except Exception as exc:
        await _log_error("alerts", started, exc)
        raise


@celery_app.task(name="generate_alerts", bind=True, max_retries=2, default_retry_delay=60)
def generate_alerts(self) -> None:
    try:
        asyncio.run(_run_and_dispose(_generate_alerts))
    except Exception as exc:
        raise self.retry(exc=exc) from exc


class PushGone(Exception):
    """Subscription endpoint returned 404/410 — delete it."""


_PUSH_MIN_PRIORITY = 50


def _send_web_push(sub: PushSubscription, payload: dict) -> None:
    """Encrypt + POST one Web Push message. Optional: needs `pywebpush` (not in
    requirements-dev — installed only in the deploy image) and a configured VAPID
    private key. Absent either, this is a no-op the caller still treats as 'sent'."""
    settings = get_settings()
    if not settings.vapid_private_key:
        logger.info("push not configured (no VAPID private key) — skipping send")
        return
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.warning("pywebpush not installed — skipping push send")
        return
    try:
        webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=json.dumps(payload),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
        )
    except WebPushException as exc:  # pragma: no cover - needs pywebpush
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            raise PushGone(str(status)) from exc
        raise


async def _deliver_push() -> None:
    started = datetime.now(UTC)
    try:
        async with get_sessionmaker()() as session, session.begin():
            teams = (await session.execute(select(LinkedTeam))).scalars().all()
            sent_total = 0
            for lt in teams:
                subs = (await session.execute(
                    select(PushSubscription).where(PushSubscription.linked_team_id == lt.id)
                )).scalars().all()
                if not subs:
                    continue
                alerts = (await session.execute(
                    select(Alert).where(
                        Alert.linked_team_id == lt.id,
                        Alert.suppressed.is_(False),
                        Alert.seen_at.is_(None),
                        Alert.pushed_at.is_(None),
                    ).order_by(Alert.priority.desc())
                )).scalars().all()
                a_dicts = [{
                    "id": a.id, "title": a.title, "body": a.body,
                    "priority": a.priority, "suppressed": a.suppressed,
                    "seen": a.seen_at is not None, "pushed": a.pushed_at is not None,
                } for a in alerts]
                s_dicts = [{"endpoint": s.endpoint, "p256dh": s.p256dh, "auth": s.auth,
                            "_row": s} for s in subs]
                dead: set[str] = set()
                pushed_alert_ids: set[int] = set()
                for t in pending_push_targets(a_dicts, s_dicts,
                                              min_priority=_PUSH_MIN_PRIORITY):
                    sub_row = t["subscription"]["_row"]
                    if sub_row.endpoint in dead:
                        continue
                    try:
                        _send_web_push(sub_row, t["payload"])
                        pushed_alert_ids.add(t["alert"]["id"])
                        sent_total += 1
                    except PushGone:
                        dead.add(sub_row.endpoint)
                for a in alerts:
                    if a.id in pushed_alert_ids:
                        a.pushed_at = func.now()
                for s in subs:
                    if s.endpoint in dead:
                        await session.delete(s)
            await _record(session, "push", "ok", started, f"{sent_total} sent")
        logger.info("push delivered: %d", sent_total)
    except Exception as exc:
        await _log_error("push", started, exc)
        raise


@celery_app.task(name="deliver_push", bind=True, max_retries=2, default_retry_delay=60)
def deliver_push(self) -> None:
    try:
        asyncio.run(_run_and_dispose(_deliver_push))
    except Exception as exc:
        raise self.retry(exc=exc) from exc


@celery_app.task(name="compute_xp", bind=True, max_retries=3, default_retry_delay=120)
def compute_xp(self) -> None:
    try:
        asyncio.run(_run_and_dispose(lambda: compute_and_store_xp(horizon=5)))
    except Exception as exc:
        raise self.retry(exc=exc) from exc


@celery_app.task(name="sync_entry", bind=True, max_retries=3, default_retry_delay=60)
def sync_entry_task(self, entry_id: int) -> None:
    try:
        asyncio.run(_run_and_dispose(lambda: sync_entry(entry_id)))
    except Exception as exc:
        raise self.retry(exc=exc) from exc


async def _sync_linked_teams() -> None:
    async with get_sessionmaker()() as session:
        ids = (await session.execute(select(LinkedTeam.fpl_entry_id))).scalars().all()
    for eid in ids:
        await sync_entry(eid)


@celery_app.task(name="sync_linked_teams", bind=True, max_retries=2, default_retry_delay=120)
def sync_linked_teams(self) -> None:
    try:
        asyncio.run(_run_and_dispose(_sync_linked_teams))
    except Exception as exc:
        raise self.retry(exc=exc) from exc


async def _upsert_standings(session, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(LeagueStanding).values(rows)
    cols = {c: stmt.excluded[c] for c in rows[0] if c not in ("league_id", "entry_id")}
    cols["updated_at"] = func.now()
    await session.execute(stmt.on_conflict_do_update(
        index_elements=["league_id", "entry_id"], set_=cols))


async def _sync_league_standings() -> None:
    started = datetime.now(UTC)
    try:
        async with get_sessionmaker()() as session:
            league_ids = sorted({
                lid for (lid,) in (await session.execute(
                    select(LinkedTeamLeague.league_id).distinct()
                )).all()
            })
        client = FplClient(get_settings().fpl_api_base)
        total = 0
        try:
            for lid in league_ids:
                payload = await client.league_standings(lid, page=1)
                norm = normalize_league_standings(lid, payload)
                async with get_sessionmaker()() as session, session.begin():
                    await _upsert_standings(session, norm["rows"])
                total += len(norm["rows"])
        finally:
            await client.aclose()
        async with get_sessionmaker()() as session, session.begin():
            await _record(session, "leagues", "ok", started,
                          f"{total} rows over {len(league_ids)} leagues")
        logger.info("league standings synced: %d rows / %d leagues", total, len(league_ids))
    except Exception as exc:
        await _log_error("leagues", started, exc)
        raise


@celery_app.task(name="sync_league_standings", bind=True, max_retries=2, default_retry_delay=120)
def sync_league_standings(self) -> None:
    try:
        asyncio.run(_run_and_dispose(_sync_league_standings))
    except Exception as exc:
        raise self.retry(exc=exc) from exc
