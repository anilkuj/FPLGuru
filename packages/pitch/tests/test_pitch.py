import httpx
import pytest
import respx

from fplguru_pitch import PitchApiError, PitchClient

BASE = "https://pitch.test/v1"


@respx.mock
async def test_matches_on_sends_key_header_and_returns_matches():
    route = respx.get(f"{BASE}/date/2025-11-09").mock(return_value=httpx.Response(200, json={
        "data": {"date": "2025-11-09", "matches": [{"id": "m_1", "status": "finished"}]}
    }))
    async with PitchClient("pk_test_x", base=BASE) as c:
        out = await c.matches_on("2025-11-09")
    assert out[0]["id"] == "m_1"
    assert route.calls.last.request.headers["x-api-key"] == "pk_test_x"


@respx.mock
async def test_match_advanced_players_and_shots():
    respx.get(f"{BASE}/matches/m_1/advanced/players").mock(return_value=httpx.Response(
        200, json={"data": {"players": [{"player": {"id": "p_9"}, "minutes_played": 90}]}}))
    respx.get(f"{BASE}/matches/m_1/shots").mock(return_value=httpx.Response(
        200, json={"data": {"shots": [{"player": {"id": "p_9"}, "expected_goals": 0.3}]}}))
    async with PitchClient("k", base=BASE) as c:
        adv = await c.match_advanced_players("m_1")
        shots = await c.match_shots("m_1")
    assert adv[0]["player"]["id"] == "p_9"
    assert shots[0]["expected_goals"] == 0.3


@respx.mock
async def test_404_raises_pitchapierror_not_retried():
    route = respx.get(f"{BASE}/matches/nope/shots").mock(return_value=httpx.Response(
        404, json={"error": {"code": "RESOURCE_NOT_FOUND", "message": "match not found"}}))
    async with PitchClient("k", base=BASE) as c:
        with pytest.raises(PitchApiError):
            await c.match_shots("nope")
    assert route.call_count == 1


@respx.mock
async def test_429_is_retried_then_raises():
    route = respx.get(f"{BASE}/date/2025-01-01").mock(return_value=httpx.Response(
        429, headers={"Retry-After": "0"},
        json={"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "slow down"}}))
    async with PitchClient("k", base=BASE) as c:
        with pytest.raises(PitchApiError):
            await c.matches_on("2025-01-01")
    assert route.call_count >= 2
