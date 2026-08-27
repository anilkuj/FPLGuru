from sqlalchemy import select

from fplguru_core.models import Team


async def test_can_insert_and_read(db_session):
    db_session.add(Team(id=1, name="Arsenal", short_name="ARS"))
    await db_session.commit()
    got = (await db_session.execute(select(Team).where(Team.id == 1))).scalar_one()
    assert got.short_name == "ARS"
