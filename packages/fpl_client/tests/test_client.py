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
    async with FplClient(BASE) as client:
        assert await client.bootstrap_static() == {"teams": [], "elements": [], "events": []}


@respx.mock
async def test_fixtures_returns_list():
    respx.get(f"{BASE}/fixtures/").mock(return_value=httpx.Response(200, json=[{"id": 1}]))
    async with FplClient(BASE) as client:
        assert await client.fixtures() == [{"id": 1}]


@respx.mock
async def test_retries_on_5xx_then_succeeds():
    route = respx.get(f"{BASE}/fixtures/")
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(200, json=[{"id": 9}]),
    ]
    async with FplClient(BASE) as client:
        assert await client.fixtures() == [{"id": 9}]
    assert route.call_count == 3


@respx.mock
async def test_raises_after_exhausting_retries():
    route = respx.get(f"{BASE}/fixtures/").mock(return_value=httpx.Response(503))
    async with FplClient(BASE) as client:
        with pytest.raises(FplApiError):
            await client.fixtures()
    assert route.call_count == 4


@respx.mock
async def test_does_not_retry_on_404():
    route = respx.get(f"{BASE}/fixtures/").mock(return_value=httpx.Response(404))
    async with FplClient(BASE) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.fixtures()
    assert route.call_count == 1


@respx.mock
async def test_retries_on_429():
    route = respx.get(f"{BASE}/fixtures/")
    route.side_effect = [httpx.Response(429), httpx.Response(200, json=[])]
    async with FplClient(BASE) as client:
        assert await client.fixtures() == []
    assert route.call_count == 2


@respx.mock
async def test_retries_on_transport_error():
    route = respx.get(f"{BASE}/fixtures/")
    route.side_effect = [httpx.ConnectError("boom"), httpx.Response(200, json=[{"id": 1}])]
    async with FplClient(BASE) as client:
        assert await client.fixtures() == [{"id": 1}]
    assert route.call_count == 2


@respx.mock
async def test_non_json_body_becomes_fpl_api_error():
    respx.get(f"{BASE}/fixtures/").mock(
        return_value=httpx.Response(200, text="<html>maintenance</html>")
    )
    async with FplClient(BASE) as client:
        with pytest.raises(FplApiError):
            await client.fixtures()


@respx.mock
async def test_injected_client_is_not_closed_by_aclose():
    respx.get(f"{BASE}/fixtures/").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient() as shared:
        client = FplClient(BASE, http=shared)
        assert await client.fixtures() == []
        await client.aclose()
        assert not shared.is_closed


@respx.mock
async def test_event_live_returns_elements():
    respx.get(f"{BASE}/event/7/live/").mock(
        return_value=httpx.Response(200, json={"elements": [{"id": 11, "stats": {"minutes": 90}}]})
    )
    async with FplClient(BASE) as client:
        data = await client.event_live(7)
    assert data["elements"][0]["id"] == 11
