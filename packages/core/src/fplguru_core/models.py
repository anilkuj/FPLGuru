from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
    func,
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
    # event id 1..38
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(32))
    deadline_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    is_next: Mapped[bool] = mapped_column(Boolean, default=False)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    average_entry_score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Player(_TimestampMixin, Base):
    __tablename__ = "players"
    # FPL element id
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
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
    # FPL fixture id
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
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
    started: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    finished_provisional: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class DataSyncLog(Base):
    __tablename__ = "data_sync_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), index=True)  # fpl_bootstrap | fpl_fixtures
    status: Mapped[str] = mapped_column(String(16))  # ok | error
    detail: Mapped[str] = mapped_column(String, default="", server_default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlayerGwStat(_TimestampMixin, Base):
    """Actual per-player-per-gameweek scoring, from event/{gw}/live."""
    __tablename__ = "player_gw_stats"
    __table_args__ = (
        UniqueConstraint("player_id", "gameweek_id",
                         name="uq_player_gw_stats_player_id_gameweek_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    clean_sheets: Mapped[int] = mapped_column(Integer, default=0)
    goals_conceded: Mapped[int] = mapped_column(Integer, default=0)
    bonus: Mapped[int] = mapped_column(Integer, default=0)
    was_home: Mapped[bool] = mapped_column(Boolean, default=False)
    opponent_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    value: Mapped[int] = mapped_column(Integer, default=0)  # price at that GW, tenths


class PlayerGwLive(_TimestampMixin, Base):
    """Provisional in-play scoring for the current gameweek: live points
    (excl. bonus) + a BPS-derived bonus projection. Superseded by
    player_gw_stats once the gameweek is finished."""
    __tablename__ = "player_gw_live"
    __table_args__ = (
        UniqueConstraint("player_id", "gameweek_id",
                         name="uq_player_gw_live_player_id_gameweek_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    live_points: Mapped[int] = mapped_column(Integer, default=0)  # excludes bonus
    bps: Mapped[int] = mapped_column(Integer, default=0)
    projected_bonus: Mapped[int] = mapped_column(Integer, default=0)
    total_points: Mapped[int] = mapped_column(Integer, default=0)  # live_points + projected_bonus


class PlayerGwFeature(_TimestampMixin, Base):
    """Versioned feature vector for a player-GW (JSON blob keyed by FEATURE_NAMES)."""
    __tablename__ = "player_gw_features"
    __table_args__ = (
        UniqueConstraint("player_id", "gameweek_id", "feature_set_version",
                         name="uq_player_gw_features_player_id_gameweek_id_feature_set_version"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    feature_set_version: Mapped[str] = mapped_column(String(16))
    features: Mapped[dict] = mapped_column(JSON)


class PlayerGwPrediction(_TimestampMixin, Base):
    """xP for a player in a future GW under a model version."""
    __tablename__ = "player_gw_predictions"
    __table_args__ = (
        UniqueConstraint("player_id", "gameweek_id", "model_version",
                         name="uq_player_gw_predictions_player_id_gameweek_id_model_version"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    horizon_gw: Mapped[int] = mapped_column(Integer)  # 1 = next GW ... 5
    model_version: Mapped[str] = mapped_column(String(32))
    xp: Mapped[float] = mapped_column(Float)
    x_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    x_goals: Mapped[float] = mapped_column(Float, default=0.0)
    x_assists: Mapped[float] = mapped_column(Float, default=0.0)
    x_cs_or_gc: Mapped[float] = mapped_column(Float, default=0.0)
    x_bonus: Mapped[float] = mapped_column(Float, default=0.0)
    xp_floor: Mapped[float] = mapped_column(Float, default=0.0)
    xp_ceiling: Mapped[float] = mapped_column(Float, default=0.0)


class LinkedTeam(_TimestampMixin, Base):
    __tablename__ = "linked_teams"
    __table_args__ = (UniqueConstraint("fpl_entry_id", name="uq_linked_teams_fpl_entry_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fpl_entry_id: Mapped[int] = mapped_column(Integer, index=True)
    manager_name: Mapped[str] = mapped_column(String(128), default="")
    started_event: Mapped[int | None] = mapped_column(Integer, nullable=True)
    favourite_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    alert_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = uncapped


class EntryGwHistory(_TimestampMixin, Base):
    __tablename__ = "entry_gw_history"
    __table_args__ = (
        UniqueConstraint("linked_team_id", "gameweek_id",
                         name="uq_entry_gw_history_linked_team_id_gameweek_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    linked_team_id: Mapped[int] = mapped_column(ForeignKey("linked_teams.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    points: Mapped[int] = mapped_column(Integer, default=0)
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    overall_rank: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    bank: Mapped[int] = mapped_column(Integer, default=0)          # tenths of a million
    team_value: Mapped[int] = mapped_column(Integer, default=0)    # tenths of a million
    transfers: Mapped[int] = mapped_column(Integer, default=0)
    transfer_cost: Mapped[int] = mapped_column(Integer, default=0)
    points_on_bench: Mapped[int] = mapped_column(Integer, default=0)


class EntryPick(_TimestampMixin, Base):
    __tablename__ = "entry_picks"
    __table_args__ = (
        UniqueConstraint("linked_team_id", "gameweek_id", "player_id",
                         name="uq_entry_picks_linked_team_id_gameweek_id_player_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    linked_team_id: Mapped[int] = mapped_column(ForeignKey("linked_teams.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    slot: Mapped[int] = mapped_column(Integer)              # 1..15 (FPL "position" field)
    multiplier: Mapped[int] = mapped_column(Integer, default=1)
    is_captain: Mapped[bool] = mapped_column(Boolean, default=False)
    is_vice: Mapped[bool] = mapped_column(Boolean, default=False)


class Alert(_TimestampMixin, Base):
    """A ranked, de-duplicated notification for one linked team."""
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("linked_team_id", "dedup_key",
                         name="uq_alerts_linked_team_id_dedup_key"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    linked_team_id: Mapped[int] = mapped_column(ForeignKey("linked_teams.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    type: Mapped[str] = mapped_column(String(24))              # availability | dgw | bgw
    dedup_key: Mapped[str] = mapped_column(String(128))
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(String, default="", server_default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
