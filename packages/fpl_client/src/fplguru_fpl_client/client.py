import logging
from typing import Any

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
)

logger = logging.getLogger("fplguru.fpl_client")
logger.addHandler(logging.NullHandler())

_RETRYABLE_STATUS = {408, 429}
_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=10.0, pool=5.0)


class FplApiError(Exception):
    pass


class FplClient:
    def __init__(self, base_url: str, http: httpx.AsyncClient | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._http = http or httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "FPLGuru/0.1 (+https://fplguru.app)"},
        )
        self._owns_http = http is None

    async def __aenter__(self) -> "FplClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    @retry(
        stop=stop_after_attempt(4) | stop_after_delay(30),
        wait=wait_exponential(multiplier=0.5, max=8),
        retry=retry_if_exception_type((httpx.TransportError, FplApiError)),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def _get(self, path: str) -> Any:
        resp = await self._http.get(f"{self._base}/{path}")
        if resp.status_code >= 500 or resp.status_code in _RETRYABLE_STATUS:
            raise FplApiError(f"GET {path} -> {resp.status_code}")
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError as exc:
            raise FplApiError(f"GET {path} -> non-JSON body ({resp.status_code})") from exc

    async def bootstrap_static(self) -> dict:
        data = await self._get("bootstrap-static/")
        if not isinstance(data, dict):
            raise FplApiError("bootstrap-static did not return an object")
        return data

    async def fixtures(self) -> list:
        data = await self._get("fixtures/")
        if not isinstance(data, list):
            raise FplApiError("fixtures did not return an array")
        return data

    async def event_live(self, gameweek: int) -> dict:
        return await self._get(f"event/{gameweek}/live/")

    async def entry(self, entry_id: int) -> dict:
        return await self._get(f"entry/{entry_id}/")

    async def entry_history(self, entry_id: int) -> dict:
        return await self._get(f"entry/{entry_id}/history/")

    async def entry_picks(self, entry_id: int, gameweek: int) -> dict:
        return await self._get(f"entry/{entry_id}/event/{gameweek}/picks/")
