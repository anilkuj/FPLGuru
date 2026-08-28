from datetime import UTC, datetime

from fplguru_core.models import (
    EntryGwHistory,
    Gameweek,
    LeagueStanding,
    LinkedTeam,
    LinkedTeamLeague,
)


async def _seed(db_session):
    db_session.add_all([
        Gameweek(id=1, name="GW1", deadline_time=datetime(2025, 8, 1, tzinfo=UTC)),
        Gameweek(id=2, name="GW2", deadline_time=datetime(2025, 8, 8, tzinfo=UTC)),
        LinkedTeam(id=1, fpl_entry_id=7, manager_name="Sam"),
    ])
    await db_session.commit()
    db_session.add_all([
        LinkedTeamLeague(linked_team_id=1, league_id=111, league_name="Work League",
                         entry_rank=4, entry_last_rank=6),
        EntryGwHistory(linked_team_id=1, gameweek_id=1, points=60, total_points=60,
                       overall_rank=1_000_000, bank=0, team_value=1000, transfers=0,
                       transfer_cost=0, points_on_bench=5),
        EntryGwHistory(linked_team_id=1, gameweek_id=2, points=70, total_points=130,
                       overall_rank=800_000, bank=0, team_value=1001, transfers=1,
                       transfer_cost=0, points_on_bench=2),
        LeagueStanding(league_id=111, entry_id=7, entry_name="My Team", player_name="Sam Q",
                       rank=4, last_rank=6, total=512, event_total=61),
        LeagueStanding(league_id=111, entry_id=99, entry_name="Rival FC", player_name="Alex P",
                       rank=5, last_rank=3, total=508, event_total=44),
    ])
    await db_session.commit()


async def test_entry_leagues_lists_mini_leagues_with_delta(client, db_session):
    await _seed(db_session)
    body = (await client.get("/entries/7/leagues")).json()
    assert body[0]["league_id"] == 111
    assert body[0]["entry_rank"] == 4 and body[0]["delta"] == 2      # 6 -> 4 = +2


async def test_league_standings_endpoint_sorted_by_rank(client, db_session):
    await _seed(db_session)
    body = (await client.get("/leagues/111/standings")).json()
    assert body["league_id"] == 111
    assert [r["rank"] for r in body["standings"]] == [4, 5]
    assert body["standings"][0]["delta"] == 2


async def test_league_search(client, db_session):
    await _seed(db_session)
    body = (await client.get("/leagues/111/search?q=rival")).json()
    assert [r["entry_id"] for r in body] == [99]


async def test_rank_history(client, db_session):
    await _seed(db_session)
    body = (await client.get("/entries/7/rank-history")).json()
    assert [(r["gameweek_id"], r["overall_rank"]) for r in body] == [(1, 1_000_000), (2, 800_000)]


async def test_leagues_unknown_entry_404(client, db_session):
    assert (await client.get("/entries/999/leagues")).status_code == 404
