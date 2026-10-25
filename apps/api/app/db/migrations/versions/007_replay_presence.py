"""Which participants are in a replay lobby (additive).

Revision ID: 007_replay_presence
Revises: 006_round_deadlines
Create Date: 2026-10-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "007_replay_presence"
down_revision: Union[str, None] = "006_round_deadlines"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NULL = everyone in the session, so existing games behave exactly as before.
    op.add_column(
        "experience_instances",
        sa.Column("present_participant_ids", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("experience_instances", "present_participant_ids")
