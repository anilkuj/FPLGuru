"""Backfill PitchAPI xG for a date range (inclusive), one day at a time.

    python scripts/backfill_xg.py 2024-08-01 2025-05-25

Only fixtures already in the DB (from sync_fixtures) that fall on those dates and
belong to a finished gameweek are ingested. Re-runnable — existing player_xg rows
are skipped.
"""
import asyncio
import sys
from datetime import date, timedelta

from fplguru_worker.tasks import _run_and_dispose, _sync_xg


def _dates(a: str, b: str) -> list[str]:
    d0 = date.fromisoformat(a)
    d1 = date.fromisoformat(b)
    out = []
    while d0 <= d1:
        out.append(d0.isoformat())
        d0 += timedelta(days=1)
    return out


async def _main(a: str, b: str) -> None:
    days = _dates(a, b)
    print(f"backfilling {len(days)} days: {days[0]} .. {days[-1]}")
    await _run_and_dispose(lambda: _sync_xg(only_dates=set(days)))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python scripts/backfill_xg.py START_DATE END_DATE")
    asyncio.run(_main(sys.argv[1], sys.argv[2]))
