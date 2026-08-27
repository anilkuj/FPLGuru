import httpx
import pytest
import respx

from fplguru_fpl_client import FplApiError, FplClient

BASE = "https://fpl.test/api"


@respx.mock
async def test_bootstrap_static_returns_json():
    respx.get(f"{BASE}/bootstrap-static/").mock(
        return_value=httpx.Response(200, json={"teams": [], "elements": [], "events": []})
    )
    client = FplClient(BASE)
    data = await client.bootstrap_static()
    await client.aclose()
    assert data == {"teams": [], "elements": [], "events": []}


@respx.mock
async def test_fixtures_returns_list():
    respx.get(f"{BASE}/fixtures/").mock(return_value=httpx.Response(200, json=[{"id": 1}]))
    client = FplClient(BASE)
    assert await client.fixtures() == [{"id": 1}]
    await client.aclose()


@respx.mock
async def test_retries_on_5xx_then_succeeds():
    route = respx.get(f"{BASE}/fixtures/")
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(200, json=[{"id": 9}]),
    ]
    client = FplClient(BASE)
    assert await client.fixtures() == [{"id": 9}]
    await client.aclose()
    assert route.call_count == 3


@respx.mock
async def test_raises_after_exhausting_retries():
    respx.get(f"{BASE}/fixtures/").mock(return_value=httpx.Response(503))
    client = FplClient(BASE)
    with pytest.raises(FplApiError):
        await client.fixtures()
    await client.aclose()
