from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, MetaData, String, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class _TimestampMixin:
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Team(_TimestampMixin, Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # FPL team id
    name: Mapped[str] = mapped_column(String(64))
    short_name: Mapped[str] = mapped_column(String(8))
    strength_overall_home: Mapped[int] = mapped_column(Integer, default=0)
    strength_overall_away: Mapped[int] = mapped_column(Integer, default=0)
    strength_attack_home: Mapped[int] = mapped_column(Integer, default=0)
    strength_attack_away: Mapped[int] = mapped_column(Integer, default=0)
    strength_defence_home: Mapped[int] = mapped_column(Integer, default=0)
    strength_defence_away: Mapped[int] = mapped_column(Integer, default=0)


class Gameweek(_TimestampMixin, Base):
    __tablename__ = "gameweeks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # event id 1..38
    name: Mapped[str] = mapped_column(String(32))
    deadline_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    is_next: Mapped[bool] = mapped_column(Boolean, default=False)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    average_entry_score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Player(_TimestampMixin, Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # FPL element id
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    first_name: Mapped[str] = mapped_column(String(64))
    second_name: Mapped[str] = mapped_column(String(64))
    web_name: Mapped[str] = mapped_column(String(64))
    position: Mapped[str] = mapped_column(String(3))  # GK/DEF/MID/FWD
    now_cost: Mapped[int] = mapped_column(Integer)  # tenths of a million
    status: Mapped[str] = mapped_column(String(1))  # a/d/i/s/u/n
    chance_of_playing_next_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    news: Mapped[str] = mapped_column(String, default="", server_default="")
    selected_by_percent: Mapped[float] = mapped_column(Float, default=0.0)
    total_points: Mapped[int] = mapped_column(Integer, default=0)


class Fixture(_TimestampMixin, Base):
    __tablename__ = "fixtures"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # FPL fixture id
    gameweek_id: Mapped[int | None] = mapped_column(
        ForeignKey("gameweeks.id"), nullable=True
    )  # null = not yet scheduled to a GW
    kickoff_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    home_difficulty: Mapped[int] = mapped_column(Integer)
    away_difficulty: Mapped[int] = mapped_column(Integer)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DataSyncLog(Base):
    __tablename__ = "data_sync_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), index=True)  # fpl_bootstrap | fpl_fixtures
    status: Mapped[str] = mapped_column(String(16))  # ok | error
    detail: Mapped[str] = mapped_column(String, default="", server_default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
