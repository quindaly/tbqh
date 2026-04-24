"""Social games extension – game state, rounds, guesses.

Revision ID: 002_social_games
Revises: 001_initial
Create Date: 2026-04-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002_social_games"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- experience_instances: add game columns ---
    op.add_column(
        "experience_instances", sa.Column("game_state", sa.Text(), nullable=True)
    )
    op.add_column(
        "experience_instances",
        sa.Column("current_round", sa.Integer(), nullable=True, server_default="0"),
    )
    op.add_column(
        "experience_instances", sa.Column("max_rounds", sa.Integer(), nullable=True)
    )
    op.add_column(
        "experience_instances",
        sa.Column("game_config", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "experience_instances",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "experience_instances",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "experience_instances",
        sa.Column(
            "parent_experience_instance_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("experience_instances.id"),
            nullable=True,
        ),
    )

    # Make group_profile_id nullable (games don't need a group profile)
    op.alter_column(
        "experience_instances",
        "group_profile_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    op.create_check_constraint(
        "ck_experience_game_state",
        "experience_instances",
        "game_state IS NULL OR game_state IN ('lobby', 'question_collection', 'ready_to_start', 'round_active', 'round_reveal', 'leaderboard', 'completed')",
    )

    # Add experience_type check (original schema had no such constraint)
    op.create_check_constraint(
        "ck_experience_type",
        "experience_instances",
        "experience_type IN ('discussion_recs', 'who_knows_who')",
    )

    # --- prompt_instances: add experience link + round number ---
    op.add_column(
        "prompt_instances",
        sa.Column(
            "experience_instance_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("experience_instances.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "prompt_instances", sa.Column("round_number", sa.Integer(), nullable=True)
    )

    # --- game_rounds ---
    op.create_table(
        "game_rounds",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "experience_instance_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("experience_instances.id"),
            nullable=False,
        ),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column(
            "source_prompt_instance_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompt_instances.id"),
            nullable=False,
        ),
        sa.Column(
            "source_response_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompt_responses.id"),
            nullable=False,
        ),
        sa.Column(
            "answering_participant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("participants.id"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'revealed', 'completed')",
            name="ck_game_round_status",
        ),
    )

    # --- game_guesses ---
    op.create_table(
        "game_guesses",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "game_round_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("game_rounds.id"),
            nullable=False,
        ),
        sa.Column(
            "guessing_participant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("participants.id"),
            nullable=False,
        ),
        sa.Column(
            "guessed_participant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("participants.id"),
            nullable=False,
        ),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column(
            "submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "game_round_id", "guessing_participant_id", name="uq_guess_per_round"
        ),
    )


def downgrade() -> None:
    op.drop_table("game_guesses")
    op.drop_table("game_rounds")
    op.drop_column("prompt_instances", "round_number")
    op.drop_column("prompt_instances", "experience_instance_id")
    op.drop_constraint(
        "ck_experience_game_state", "experience_instances", type_="check"
    )
    op.drop_constraint("ck_experience_type", "experience_instances", type_="check")
    op.alter_column(
        "experience_instances",
        "group_profile_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_column("experience_instances", "parent_experience_instance_id")
    op.drop_column("experience_instances", "completed_at")
    op.drop_column("experience_instances", "started_at")
    op.drop_column("experience_instances", "game_config")
    op.drop_column("experience_instances", "max_rounds")
    op.drop_column("experience_instances", "current_round")
    op.drop_column("experience_instances", "game_state")
