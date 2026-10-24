"""Server-side phase clock for timed Hot Seat phases (additive).

Revision ID: 005_phase_deadlines
Revises: 004_choice_revision
Create Date: 2026-10-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005_phase_deadlines"
down_revision: Union[str, None] = "004_choice_revision"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "experience_instances",
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "experience_instances",
        sa.Column("phase_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "experience_instances",
        sa.Column("phase_deadline_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("experience_instances", "phase_deadline_at")
    op.drop_column("experience_instances", "phase_started_at")
    op.drop_column("experience_instances", "state_version")
