"""Async Google Gemini REST client (no SDK) + cost estimation."""
from __future__ import annotations

import logging

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
)

__all__ = ["GeminiClient", "LlmError", "estimate_cost"]

logger = logging.getLogger("fplguru.llm")
logger.addHandler(logging.NullHandler())

_DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta"
_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)

# USD per 1,000,000 tokens: (input, output)
_PRICES = {
    "gemini-2.0-flash": (0.075, 0.30),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-1.5-pro": (1.25, 5.00),
}
_FALLBACK_PRICE = (0.075, 0.30)


class LlmError(Exception):
    pass


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = _PRICES.get(model, _FALLBACK_PRICE)
    return (prompt_tokens * pin + completion_tokens * pout) / 1_000_000


class GeminiClient:
    def __init__(self, api_key: str, *, base: str = _DEFAULT_BASE,
                 model: str = "gemini-2.0-flash",
                 http: httpx.AsyncClient | None = None) -> None:
        self._key = api_key
        self._base = base.rstrip("/")
        self._model = model
        self._http = http or httpx.AsyncClient(timeout=_TIMEOUT)
        self._owns_http = http is None

    async def __aenter__(self) -> GeminiClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    @retry(
        stop=stop_after_attempt(4) | stop_after_delay(30),
        wait=wait_exponential(multiplier=0.5, max=8),
        retry=retry_if_exception_type((httpx.TransportError, LlmError)),
        reraise=True,
    )
    async def _call(self, prompt: str, max_output_tokens: int) -> dict:
        resp = await self._http.post(
            f"{self._base}/models/{self._model}:generateContent",
            params={"key": self._key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_output_tokens},
            },
        )
        if resp.status_code == 429 or resp.status_code >= 500:
            raise LlmError(f"gemini {resp.status_code}")
        if resp.status_code >= 400:
            raise LlmError(f"gemini {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    async def generate(self, prompt: str, *,
                       max_output_tokens: int = 256) -> tuple[str, int, int]:
        data = await self._call(prompt, max_output_tokens)
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmError(f"gemini: no candidate text ({data.get('promptFeedback')})") from exc
        usage = data.get("usageMetadata", {})
        return (
            text,
            int(usage.get("promptTokenCount", 0)),
            int(usage.get("candidatesTokenCount", 0)),
        )
