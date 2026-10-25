"""Remember which sign-in links were used so each works once (additive).

Revision ID: 008_used_magic_links
Revises: 007_replay_presence
Create Date: 2026-10-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008_used_magic_links"
down_revision: Union[str, None] = "007_replay_presence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "used_magic_links",
        sa.Column("jti", sa.Text(), primary_key=True),
        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("used_magic_links")
