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
