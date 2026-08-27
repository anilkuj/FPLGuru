"""Shared FPL-entry (manager team) sync — used by both services/worker and services/api."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from fplguru_core.db import get_sessionmaker
from fplguru_core.models import DataSyncLog, EntryGwHistory, EntryPick, Gameweek, LinkedTeam
from fplguru_core.settings import get_settings
from fplguru_fpl_client import FplClient
from fplguru_ingest.fpl import normalize_entry, normalize_entry_history, normalize_entry_picks

logger = logging.getLogger("fplguru.entrysync")

__all__ = ["sync_entry"]


async def _upsert(session, model, rows: list[dict], keys: tuple[str, ...]) -> None:
    if not rows:
        return
    stmt = pg_insert(model).values(rows)
    update = {c: stmt.excluded[c] for c in rows[0] if c not in keys}
    update["updated_at"] = func.now()
    await session.execute(
        stmt.on_conflict_do_update(index_elements=list(keys), set_=update)
    )


async def sync_entry(entry_id: int) -> int:
    """Fetch one FPL entry, upsert its link row + GW history + latest-finished-GW picks.
    Returns the linked_team id."""
    started = datetime.now(UTC)
    client = FplClient(get_settings().fpl_api_base)
    try:
        profile = await client.entry(entry_id)
        history = await client.entry_history(entry_id)
        async with get_sessionmaker()() as session:
            latest_finished = (await session.execute(
                select(func.max(Gameweek.id)).where(Gameweek.finished.is_(True))
            )).scalar()
        picks: dict = {"picks": []}
        if latest_finished is not None:
            try:
                picks = await client.entry_picks(entry_id, latest_finished)
            except httpx.HTTPStatusError:
                picks = {"picks": []}   # manager has no squad for that GW yet
    finally:
        await client.aclose()

    ent = normalize_entry(profile)
    async with get_sessionmaker()() as session, session.begin():
        lt = (await session.execute(
            select(LinkedTeam).where(LinkedTeam.fpl_entry_id == entry_id)
        )).scalar_one_or_none()
        if lt is None:
            lt = LinkedTeam(**ent, last_synced_at=datetime.now(UTC))
            session.add(lt)
            await session.flush()
        else:
            lt.manager_name = ent["manager_name"]
            lt.started_event = ent["started_event"]
            lt.favourite_team_id = ent["favourite_team_id"]
            lt.last_synced_at = datetime.now(UTC)
        lt_id = lt.id

        hist_rows = [{"linked_team_id": lt_id, **r} for r in normalize_entry_history(history)]
        await _upsert(session, EntryGwHistory, hist_rows, ("linked_team_id", "gameweek_id"))

        n_picks = 0
        if latest_finished is not None:
            pick_rows = [
                {"linked_team_id": lt_id, **r}
                for r in normalize_entry_picks(latest_finished, picks)
            ]
            n_picks = len(pick_rows)
            await _upsert(session, EntryPick, pick_rows,
                          ("linked_team_id", "gameweek_id", "player_id"))

        session.add(DataSyncLog(
            source="fpl_entry", status="ok",
            detail=f"entry {entry_id}: {len(hist_rows)} gw, {n_picks} picks",
            started_at=started, finished_at=datetime.now(UTC),
        ))
    logger.info("synced entry %s -> linked_team %s", entry_id, lt_id)
    return lt_id
