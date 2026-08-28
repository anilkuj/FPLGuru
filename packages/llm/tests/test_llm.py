import httpx
import pytest
import respx

from fplguru_llm import GeminiClient, LlmError, estimate_cost

BASE = "https://gen.test/v1beta"


def test_estimate_cost_uses_per_model_prices():
    c = estimate_cost("gemini-2.0-flash", 1_000_000, 1_000_000)
    assert round(c, 4) == round(0.075 + 0.30, 4)
    assert estimate_cost("mystery", 0, 0) == 0.0


@respx.mock
async def test_generate_returns_text_and_token_counts():
    route = respx.post(f"{BASE}/models/gemini-2.0-flash:generateContent").mock(
        return_value=httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "Salah at home — captain him."}]}}],
            "usageMetadata": {"promptTokenCount": 42, "candidatesTokenCount": 9},
        })
    )
    async with GeminiClient("k", base=BASE, model="gemini-2.0-flash") as c:
        text, pt, ct = await c.generate("who to captain?", max_output_tokens=64)
    assert text == "Salah at home — captain him."
    assert (pt, ct) == (42, 9)
    assert route.calls.last.request.url.params["key"] == "k"
    body = route.calls.last.request.content.decode()
    assert "who to captain?" in body and "maxOutputTokens" in body


@respx.mock
async def test_generate_raises_llmerror_on_500_after_retries():
    respx.post(f"{BASE}/models/gemini-2.0-flash:generateContent").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )
    async with GeminiClient("k", base=BASE, model="gemini-2.0-flash") as c:
        with pytest.raises(LlmError):
            await c.generate("x", max_output_tokens=8)


@respx.mock
async def test_generate_raises_llmerror_on_blocked_or_empty_response():
    respx.post(f"{BASE}/models/gemini-2.0-flash:generateContent").mock(
        return_value=httpx.Response(200, json={"candidates": []})
    )
    async with GeminiClient("k", base=BASE, model="gemini-2.0-flash") as c:
        with pytest.raises(LlmError):
            await c.generate("x", max_output_tokens=8)
