from typing import Any

import httpx
from tenacity import (
    retry, retry_if_exception_type, stop_after_attempt, wait_exponential,
)


class FplApiError(Exception):
    pass


class FplClient:
    def __init__(self, base_url: str, http: httpx.AsyncClient | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._http = http or httpx.AsyncClient(
            timeout=15.0, headers={"User-Agent": "FPLGuru/0.1 (+https://fplguru.app)"}
        )
        self._owns_http = http is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, max=8),
        retry=retry_if_exception_type((httpx.TransportError, FplApiError)),
        reraise=True,
    )
    async def _get(self, path: str) -> Any:
        try:
            resp = await self._http.get(f"{self._base}/{path}")
        except httpx.TransportError:
            raise
        if resp.status_code >= 500:
            raise FplApiError(f"GET {path} -> {resp.status_code}")
        resp.raise_for_status()
        return resp.json()

    async def bootstrap_static(self) -> dict:
        return await self._get("bootstrap-static/")

    async def fixtures(self) -> list:
        return await self._get("fixtures/")
