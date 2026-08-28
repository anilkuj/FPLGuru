"""Dump raw PitchAPI responses for one date so the normalizers can be verified
against the live response shape.

    python scripts/pitch_probe.py 2025-11-09
"""
import asyncio
import json
import sys

from fplguru_core.settings import get_settings
from fplguru_pitch import PitchClient


async def _main(date: str) -> None:
    s = get_settings()
    if not s.pitchapi_key:
        raise SystemExit("set FPLGURU_PITCHAPI_KEY first")
    client = PitchClient(s.pitchapi_key, base=s.pitchapi_base)
    try:
        matches = await client.matches_on(date)
        print(f"# matches_on({date}) -> {len(matches)}")
        print(json.dumps(matches[:3], indent=2))
        if not matches:
            return
        mid = matches[0]["id"]
        print(f"\n# match_advanced_players({mid})")
        print(json.dumps((await client.match_advanced_players(mid))[:3], indent=2))
        print(f"\n# match_shots({mid})")
        print(json.dumps((await client.match_shots(mid))[:5], indent=2))
    finally:
        await client.aclose()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/pitch_probe.py YYYY-MM-DD")
    asyncio.run(_main(sys.argv[1]))
