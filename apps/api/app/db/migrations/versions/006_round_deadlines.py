"""Per-round guess deadline and frozen guesser roster (additive).

Revision ID: 006_round_deadlines
Revises: 005_phase_deadlines
Create Date: 2026-10-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "006_round_deadlines"
down_revision: Union[str, None] = "005_phase_deadlines"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "game_rounds",
        sa.Column("guess_deadline_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "game_rounds",
        sa.Column(
            "eligible_participant_ids", postgresql.JSONB(), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("game_rounds", "eligible_participant_ids")
    op.drop_column("game_rounds", "guess_deadline_at")
