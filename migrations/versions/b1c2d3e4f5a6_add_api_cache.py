"""add api_cache table (canonical model version)

Revision ID: b1c2d3e4f5a6
Revises: 016e6db09f59
Create Date: 2026-09-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "016e6db09f59"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_cache",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("fetched_at", sa.Float(), nullable=False),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("api_cache")