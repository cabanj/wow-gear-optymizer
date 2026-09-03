"""SQLAlchemy models mirroring docs/database-schema.md."""
import uuid
from datetime import datetime, date

from sqlalchemy import (
    Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def pk_uuid() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = pk_uuid()
    bnet_id: Mapped[str] = mapped_column(String, unique=True)
    battletag: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BlizzardAccount(Base):
    __tablename__ = "blizzard_accounts"
    id: Mapped[uuid.UUID] = pk_uuid()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    region: Mapped[str] = mapped_column(String(2))
    wow_accounts: Mapped[dict] = mapped_column(JSONB, default=dict)
    tokens_encrypted: Mapped[bytes | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[float | None] = mapped_column(nullable=True)


class Character(Base):
    __tablename__ = "characters"
    id: Mapped[uuid.UUID] = pk_uuid()
    blizzard_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("blizzard_accounts.id"))
    region: Mapped[str] = mapped_column(String(2))
    realm_slug: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_name: Mapped[str | None] = mapped_column(String, nullable=True)
    active_spec_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_spec_name: Mapped[str | None] = mapped_column(String, nullable=True)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    race_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    media_url: Mapped[str | None] = mapped_column(String, nullable=True)
    __table_args__ = ({"comment": "UNIQUE(region, realm_slug, name) added in migration"},)


class CharacterSnapshot(Base):
    __tablename__ = "character_snapshots"
    id: Mapped[uuid.UUID] = pk_uuid()
    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"))
    source: Mapped[str] = mapped_column(Enum("blizzard_armory", "simc_addon_import", name="snapshot_source"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw: Mapped[dict] = mapped_column(JSONB)
    simc_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_level: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)


class Item(Base):
    __tablename__ = "items"
    id: Mapped[uuid.UUID] = pk_uuid()
    item_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String)
    slot: Mapped[str] = mapped_column(String)
    item_class: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_subclass: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality: Mapped[str | None] = mapped_column(String, nullable=True)
    unique_equipped: Mapped[bool] = mapped_column(Boolean, default=False)
    required_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    identity: Mapped[dict] = mapped_column(JSONB, default=dict)


class ContentSource(Base):
    __tablename__ = "content_sources"
    id: Mapped[uuid.UUID] = pk_uuid()
    type: Mapped[str] = mapped_column(Enum("raid", "dungeon", name="content_type"))
    journal_instance_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String)
    slug: Mapped[str] = mapped_column(String)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    wow_build: Mapped[str | None] = mapped_column(String, nullable=True)


class ContentEncounter(Base):
    __tablename__ = "content_encounters"
    id: Mapped[uuid.UUID] = pk_uuid()
    content_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("content_sources.id"))
    journal_encounter_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String)
    order: Mapped[int] = mapped_column(Integer, default=0)


class ContentItem(Base):
    __tablename__ = "content_items"
    id: Mapped[uuid.UUID] = pk_uuid()
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("content_encounters.id"), nullable=True)
    dungeon_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("content_sources.id"), nullable=True)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id"))
    difficulty: Mapped[str] = mapped_column(Enum("lfr", "normal", "heroic", "mythic", name="difficulty"))
    item_level: Mapped[int] = mapped_column(Integer)
    upgrade_track: Mapped[str | None] = mapped_column(String, nullable=True)
    bonus_ids: Mapped[list] = mapped_column(JSONB, default=list)
    source_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    id: Mapped[uuid.UUID] = pk_uuid()
    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"))
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("character_snapshots.id"))
    simc_version: Mapped[str | None] = mapped_column(String, nullable=True)
    simc_commit: Mapped[str | None] = mapped_column(String, nullable=True)
    wow_build: Mapped[str | None] = mapped_column(String, nullable=True)
    content_version: Mapped[str | None] = mapped_column(String, nullable=True)
    simulation_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    profile: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("pending", "running", "completed", "failed", name="run_status"), default="pending"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SimulationResult(Base):
    __tablename__ = "simulation_results"
    id: Mapped[uuid.UUID] = pk_uuid()
    simulation_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("simulation_runs.id"))
    profileset_name: Mapped[str | None] = mapped_column(String, nullable=True)  # NULL = baseline
    profile_type: Mapped[str] = mapped_column(Enum("raid", "mplus", name="profile_type"))
    mean: Mapped[float] = mapped_column(Numeric)
    median: Mapped[float] = mapped_column(Numeric)
    min: Mapped[float] = mapped_column(Numeric)
    max: Mapped[float] = mapped_column(Numeric)
    stddev: Mapped[float] = mapped_column(Numeric)
    iterations: Mapped[int] = mapped_column(Integer)
    confidence_interval: Mapped[dict] = mapped_column(JSONB, default=dict)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[uuid.UUID] = pk_uuid()
    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"))
    simulation_run_raid: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("simulation_runs.id"), nullable=True
    )
    simulation_run_mplus: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("simulation_runs.id"), nullable=True
    )
    report_date: Mapped[date] = mapped_column(Date)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    baseline_dps_raid: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    baseline_dps_mplus: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    best_raid_upgrade_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("items.id"), nullable=True
    )
    best_mplus_upgrade_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("items.id"), nullable=True
    )
    snapshot_age_warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_path: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("generating", "completed", "failed", name="report_status"), default="generating"
    )
