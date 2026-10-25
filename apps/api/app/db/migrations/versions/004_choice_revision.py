"""Add game_choices.revision and a one-fake-answer-per-player index (additive).

Revision ID: 004_choice_revision
Revises: 003_how_well_do_you_know
Create Date: 2026-10-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_choice_revision"
down_revision: Union[str, None] = "003_how_well_do_you_know"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "game_choices",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "uq_round_player_fake",
        "game_choices",
        ["game_round_id", "created_by_participant_id"],
        unique=True,
        postgresql_where=sa.text("source_type = 'player_fake'"),
    )


def downgrade() -> None:
    op.drop_index("uq_round_player_fake", table_name="game_choices")
    op.drop_column("game_choices", "revision")
