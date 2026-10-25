"""A name for each account, asked for once at first sign-in (additive).

Revision ID: 010_user_display_name
Revises: 009_presence_start_without
Create Date: 2026-10-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010_user_display_name"
down_revision: Union[str, None] = "009_presence_start_without"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "name_prompt_done",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "name_prompt_done")
    op.drop_column("users", "display_name")
