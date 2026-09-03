"""Recreate full initial schema (tables already existed once; canonical migration).

Revision ID: 016e6db09f59
Revises:
Create Date: 2026-09-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "016e6db09f59"
down_revision: Union[str, None] = None
branch_labels = None
depends_on = None


def _uuid_pk() -> object:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                     server_default=sa.text("gen_random_uuid()"))


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("bnet_id", sa.String(), nullable=False),
        sa.Column("battletag", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("bnet_id", name="uq_users_bnet_id"),
    )
    op.create_table(
        "blizzard_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("region", sa.String(length=2), nullable=False),
        sa.Column("wow_accounts", postgresql.JSONB(), nullable=True),
        sa.Column("tokens_encrypted", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.Float(), nullable=True),
    )
    op.create_table(
        "characters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("blizzard_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("blizzard_accounts.id"), nullable=False),
        sa.Column("region", sa.String(length=2), nullable=False),
        sa.Column("realm_slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=True),
        sa.Column("class_name", sa.String(), nullable=True),
        sa.Column("active_spec_id", sa.Integer(), nullable=True),
        sa.Column("active_spec_name", sa.String(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=True),
        sa.Column("race_id", sa.Integer(), nullable=True),
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("media_url", sa.String(), nullable=True),
        sa.UniqueConstraint("region", "realm_slug", "name", name="uq_characters_identity"),
    )
    op.create_table(
        "character_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("character_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("characters.id"), nullable=False),
        sa.Column("source", sa.Enum("blizzard_armory", "simc_addon_import", name="snapshot_source"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("simc_text", sa.Text(), nullable=True),
        sa.Column("item_level", sa.Numeric(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slot", sa.String(), nullable=False),
        sa.Column("item_class", sa.Integer(), nullable=True),
        sa.Column("item_subclass", sa.Integer(), nullable=True),
        sa.Column("quality", sa.String(), nullable=True),
        sa.Column("unique_equipped", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("required_level", sa.Integer(), nullable=True),
        sa.Column("identity", postgresql.JSONB(), nullable=True),
    )
    op.create_table(
        "content_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("type", sa.Enum("raid", "dungeon", name="content_type"), nullable=False),
        sa.Column("journal_instance_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("wow_build", sa.String(), nullable=True),
    )
    op.create_table(
        "content_encounters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("content_source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content_sources.id"), nullable=False),
        sa.Column("journal_encounter_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_table(
        "content_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content_encounters.id"), nullable=True),
        sa.Column("dungeon_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content_sources.id"), nullable=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("difficulty", sa.Enum("lfr", "normal", "heroic", "mythic", name="difficulty"), nullable=False),
        sa.Column("item_level", sa.Integer(), nullable=False),
        sa.Column("upgrade_track", sa.String(), nullable=True),
        sa.Column("bonus_ids", postgresql.JSONB(), nullable=True),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=True),
    )
    op.create_table(
        "simulation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("character_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("characters.id"), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("character_snapshots.id"), nullable=False),
        sa.Column("simc_version", sa.String(), nullable=True),
        sa.Column("simc_commit", sa.String(), nullable=True),
        sa.Column("wow_build", sa.String(), nullable=True),
        sa.Column("content_version", sa.String(), nullable=True),
        sa.Column("simulation_config", postgresql.JSONB(), nullable=True),
        sa.Column("profile", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("pending", "running", "completed", "failed", name="run_status"), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "simulation_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("simulation_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("simulation_runs.id"), nullable=False),
        sa.Column("profileset_name", sa.String(), nullable=True),
        sa.Column("profile_type", sa.Enum("raid", "mplus", name="profile_type"), nullable=False),
        sa.Column("mean", sa.Numeric(), nullable=False),
        sa.Column("median", sa.Numeric(), nullable=False),
        sa.Column("min", sa.Numeric(), nullable=False),
        sa.Column("max", sa.Numeric(), nullable=False),
        sa.Column("stddev", sa.Numeric(), nullable=False),
        sa.Column("iterations", sa.Integer(), nullable=False),
        sa.Column("confidence_interval", postgresql.JSONB(), nullable=True),
        sa.Column("raw", postgresql.JSONB(), nullable=True),
    )
    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("character_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("characters.id"), nullable=False),
        sa.Column("simulation_run_raid", postgresql.UUID(as_uuid=True), sa.ForeignKey("simulation_runs.id"), nullable=True),
        sa.Column("simulation_run_mplus", postgresql.UUID(as_uuid=True), sa.ForeignKey("simulation_runs.id"), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("baseline_dps_raid", sa.Numeric(), nullable=True),
        sa.Column("baseline_dps_mplus", sa.Numeric(), nullable=True),
        sa.Column("best_raid_upgrade_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=True),
        sa.Column("best_mplus_upgrade_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=True),
        sa.Column("snapshot_age_warning", sa.Text(), nullable=True),
        sa.Column("html_path", sa.String(), nullable=True),
        sa.Column("status", sa.Enum("generating", "completed", "failed", name="report_status"), nullable=False, server_default="generating"),
    )
    op.create_table(
        "api_cache",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("fetched_at", sa.Float(), nullable=False),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    for t in ("api_cache", "reports", "simulation_results", "simulation_runs",
              "content_items", "content_encounters", "content_sources", "items",
              "character_snapshots", "characters", "blizzard_accounts", "users"):
        op.drop_table(t)
    for e in ("report_status", "profile_type", "run_status", "difficulty", "content_type", "snapshot_source"):
        op.execute(f"DROP TYPE IF EXISTS {e}")