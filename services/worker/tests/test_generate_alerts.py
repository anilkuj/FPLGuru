from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from fplguru_core.models import (
    Alert,
    EntryPick,
    Fixture,
    Gameweek,
    LinkedTeam,
    Player,
    Team,
)
from fplguru_worker import tasks


async def _seed(db_session, *, alert_cap=None):
    db_session.add_all([
        Team(id=10, name="Liverpool", short_name="LIV"),
        Team(id=11, name="Newcastle", short_name="NEW"),
        Team(id=12, name="Everton", short_name="EVE"),
    ])
    db_session.add(Gameweek(id=9, name="GW9",
                            deadline_time=datetime.now(UTC) + timedelta(days=1),
                            is_current=True))
    await db_session.commit()
    db_session.add_all([
        Player(id=1, team_id=10, first_name="M", second_name="Salah", web_name="Salah",
               position="MID", now_cost=130, status="a"),
        Player(id=2, team_id=11, first_name="A", second_name="Isak", web_name="Isak",
               position="FWD", now_cost=100, status="i", chance_of_playing_next_round=0,
               news="Knee - out"),
        Player(id=3, team_id=11, first_name="A", second_name="Gordon", web_name="Gordon",
               position="MID", now_cost=75, status="a", chance_of_playing_next_round=75,
               news="Knock"),
    ])
    db_session.add(LinkedTeam(id=1, fpl_entry_id=555, manager_name="Sam", alert_cap=alert_cap))
    await db_session.commit()
    db_session.add_all([
        EntryPick(linked_team_id=1, gameweek_id=9, player_id=1, slot=1, multiplier=2,
                  is_captain=True, is_vice=False),
        EntryPick(linked_team_id=1, gameweek_id=9, player_id=2, slot=2, multiplier=1),
        EntryPick(linked_team_id=1, gameweek_id=9, player_id=3, slot=12, multiplier=0),
    ])
    db_session.add_all([
        Fixture(id=901, gameweek_id=9, home_team_id=10, away_team_id=12,
                home_difficulty=3, away_difficulty=3),
        Fixture(id=902, gameweek_id=9, home_team_id=12, away_team_id=10,
                home_difficulty=3, away_difficulty=3),
    ])
    await db_session.commit()


async def test_generate_alerts_creates_ranked_rows(db_session):
    await _seed(db_session)
    await tasks._generate_alerts()

    rows = {a.dedup_key: a for a in (await db_session.execute(select(Alert))).scalars()}
    # _seed's GW9 deadline is ~1 day out, so the 1440-min reminder also fires
    assert set(rows) == {
        "avail:2:i:0", "avail:3:a:75", "dgw:10:9", "bgw:11:9", "deadline:9:1440",
    }
    assert rows["avail:2:i:0"].priority == 100                    # 60+15+15+10, clamped
    assert rows["avail:3:a:75"].priority == 60 + 10               # bench doubtful, pre-deadline
    assert rows["dgw:10:9"].priority == 40 + 25 + 10              # Salah is captain on Liverpool
    assert rows["bgw:11:9"].priority == 45 + 15 + 10             # Isak (XI) on Newcastle
    assert rows["deadline:9:1440"].priority == 55 + 10           # far-out, pre-deadline
    assert all(a.suppressed is False for a in rows.values())
    assert rows["avail:2:i:0"].linked_team_id == 1


async def test_generate_alerts_is_idempotent(db_session):
    await _seed(db_session)
    await tasks._generate_alerts()
    await tasks._generate_alerts()
    n = len((await db_session.execute(select(Alert))).scalars().all())
    assert n == 5


async def test_generate_alerts_applies_cap(db_session):
    await _seed(db_session, alert_cap=2)
    await tasks._generate_alerts()
    visible = (await db_session.execute(
        select(Alert).where(Alert.suppressed.is_(False)).order_by(Alert.priority.desc())
    )).scalars().all()
    assert len(visible) == 2
    assert [a.dedup_key for a in visible] == ["avail:2:i:0", "dgw:10:9"]
    suppressed = (await db_session.execute(
        select(Alert).where(Alert.suppressed.is_(True))
    )).scalars().all()
    assert {a.dedup_key for a in suppressed} == {
        "avail:3:a:75", "bgw:11:9", "deadline:9:1440",
    }


async def test_generate_alerts_emits_deadline_reminders(db_session):
    await _seed(db_session)
    gw = (await db_session.execute(select(Gameweek).where(Gameweek.id == 9))).scalar_one()
    gw.deadline_time = datetime.now(UTC) + timedelta(minutes=25)
    await db_session.commit()

    await tasks._generate_alerts()

    keys = {a.dedup_key for a in (await db_session.execute(select(Alert))).scalars()}
    assert {"deadline:9:30", "deadline:9:60", "deadline:9:120", "deadline:9:1440"} <= keys
    row = (await db_session.execute(
        select(Alert).where(Alert.dedup_key == "deadline:9:30")
    )).scalar_one()
    assert row.type == "deadline"
    assert row.priority == 55 + 15 + 10          # tight + pre-deadline
    assert row.linked_team_id == 1
