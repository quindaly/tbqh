"""One account per email address, however it is capitalised.

Sign-in has lowercased addresses for a while, but nothing in the database
stopped two rows that differ only by case (an account made before that, say).
This merges any such pair into the oldest account, lowercases every address,
and adds a unique index so it cannot happen again.

Revision ID: 011_unique_lower_email
Revises: 010_user_display_name
Create Date: 2026-10-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "011_unique_lower_email"
down_revision: Union[str, None] = "010_user_display_name"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every column that points at users.id.
REFERENCES = [
    ("groups", "created_by_user_id"),
    ("participants", "user_id"),
    ("user_question_feedback", "user_id"),
]


def upgrade() -> None:
    # Which duplicate rows fold into which survivor (the oldest of each pair).
    op.execute(
        """
        CREATE TEMP TABLE _email_merge ON COMMIT DROP AS
        SELECT id AS loser_id,
               first_value(id) OVER (
                   PARTITION BY lower(email) ORDER BY created_at, id
               ) AS keeper_id
        FROM users
        """
    )
    op.execute("DELETE FROM _email_merge WHERE loser_id = keeper_id")

    for table, column in REFERENCES:
        op.execute(
            f"""
            UPDATE {table} t SET {column} = m.keeper_id
            FROM _email_merge m WHERE t.{column} = m.loser_id
            """
        )
    # A kept account takes the name of the one it absorbed if it has none.
    op.execute(
        """
        UPDATE users k
        SET display_name = l.display_name, name_prompt_done = true
        FROM _email_merge m JOIN users l ON l.id = m.loser_id
        WHERE k.id = m.keeper_id AND k.display_name IS NULL AND l.display_name IS NOT NULL
        """
    )
    op.execute("DELETE FROM users WHERE id IN (SELECT loser_id FROM _email_merge)")

    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")
    op.execute("CREATE UNIQUE INDEX ix_users_email_lower ON users (lower(email))")


def downgrade() -> None:
    # Merged accounts stay merged; only the index goes.
    op.execute("DROP INDEX IF EXISTS ix_users_email_lower")
