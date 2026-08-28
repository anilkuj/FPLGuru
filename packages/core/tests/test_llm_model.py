from fplguru_core.models import Base, CaptainRationale, LlmCall


def test_llm_tables_registered():
    assert {"llm_calls", "captain_rationale"} <= set(Base.metadata.tables)
    uq = {tuple(sorted(c.name for c in con.columns))
          for con in CaptainRationale.__table__.constraints
          if con.__class__.__name__ == "UniqueConstraint"}
    assert ("gameweek_id", "kind", "player_id") in uq
    assert "created_at" in {c.name for c in LlmCall.__table__.columns}
