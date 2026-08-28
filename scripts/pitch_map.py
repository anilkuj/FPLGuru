"""Manually fix a PitchAPI -> FPL player-id mapping.

    python scripts/pitch_map.py p_7YtX4q 233     # map pitch id -> FPL player id
    python scripts/pitch_map.py --list-unmatched
"""
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from fplguru_core.db import get_sessionmaker
from fplguru_core.models import PitchPlayerMap


async def _list_unmatched() -> None:
    async with get_sessionmaker()() as session:
        rows = (await session.execute(
            select(PitchPlayerMap).where(PitchPlayerMap.player_id.is_(None))
        )).scalars().all()
    for r in rows:
        print(f"{r.pitch_player_id}\t{r.pitch_name}\t({r.method})")
    print(f"# {len(rows)} unmatched")


async def _set(pitch_id: str, fpl_id: int) -> None:
    async with get_sessionmaker()() as session, session.begin():
        stmt = pg_insert(PitchPlayerMap).values(
            pitch_player_id=pitch_id, player_id=fpl_id, method="manual", pitch_name=""
        ).on_conflict_do_update(
            index_elements=["pitch_player_id"],
            set_={"player_id": fpl_id, "method": "manual"},
        )
        await session.execute(stmt)
    print(f"{pitch_id} -> FPL {fpl_id} (manual)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--list-unmatched"]:
        asyncio.run(_list_unmatched())
    elif len(args) == 2:
        asyncio.run(_set(args[0], int(args[1])))
    else:
        raise SystemExit(__doc__)
