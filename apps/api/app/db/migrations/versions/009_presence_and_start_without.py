"""Player presence and starting Who Knows Who without stragglers (additive).

Revision ID: 009_presence_start_without
Revises: 008_used_magic_links
Create Date: 2026-10-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "009_presence_start_without"
down_revision: Union[str, None] = "008_used_magic_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "participants",
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "experience_instances",
        sa.Column("excluded_participant_ids", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("experience_instances", "excluded_participant_ids")
    op.drop_column("participants", "last_seen_at")
