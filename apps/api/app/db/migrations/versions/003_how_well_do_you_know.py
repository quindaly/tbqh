"""How Well Do You Know game – choices, MC guesses, extended states.

Revision ID: 003_how_well_do_you_know
Revises: 002_social_games
Create Date: 2026-05-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003_how_well_do_you_know"
down_revision: Union[str, None] = "002_social_games"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- experience_instances: add main_person_participant_id ---
    op.add_column(
        "experience_instances",
        sa.Column(
            "main_person_participant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("participants.id"),
            nullable=True,
        ),
    )

    # --- Update ck_experience_type to include new game ---
    op.drop_constraint("ck_experience_type", "experience_instances", type_="check")
    op.create_check_constraint(
        "ck_experience_type",
        "experience_instances",
        "experience_type IN ('discussion_recs', 'who_knows_who', 'how_well_do_you_know')",
    )

    # --- Update ck_experience_game_state to include new states ---
    op.drop_constraint(
        "ck_experience_game_state", "experience_instances", type_="check"
    )
    op.create_check_constraint(
        "ck_experience_game_state",
        "experience_instances",
        "game_state IS NULL OR game_state IN ("
        "'lobby', 'question_collection', 'ready_to_start', 'round_active', "
        "'round_reveal', 'leaderboard', 'completed', "
        "'main_person_answering', 'ai_generating_choices', "
        "'main_person_reviewing_choices', 'players_submitting_fake_answers')",
    )

    # --- game_rounds: add new columns for HWDYK ---
    op.add_column("game_rounds", sa.Column("question_text", sa.Text(), nullable=True))
    op.add_column(
        "game_rounds",
        sa.Column(
            "correct_choice_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "game_rounds",
        sa.Column("timer_duration", sa.Integer(), nullable=True, server_default="60"),
    )
    op.add_column(
        "game_rounds",
        sa.Column("round_locked_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Update game_rounds status constraint to include 'setup'
    op.drop_constraint("ck_game_round_status", "game_rounds", type_="check")
    op.create_check_constraint(
        "ck_game_round_status",
        "game_rounds",
        "status IN ('pending', 'active', 'revealed', 'completed', 'setup')",
    )

    # Make source_prompt_instance_id and source_response_id nullable for HWDYK rounds
    op.alter_column(
        "game_rounds",
        "source_prompt_instance_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.alter_column(
        "game_rounds",
        "source_response_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # --- game_choices ---
    op.create_table(
        "game_choices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "game_round_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("game_rounds.id"),
            nullable=False,
        ),
        sa.Column("choice_text", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column(
            "created_by_participant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("participants.id"),
            nullable=True,
        ),
        sa.Column("original_ai_text", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "source_type IN ('main_person', 'ai_generated', 'main_person_edited', 'player_fake', 'ai_fallback')",
            name="ck_game_choice_source_type",
        ),
        sa.UniqueConstraint(
            "game_round_id", "choice_text", name="uq_round_choice_text"
        ),
    )
    op.create_index("ix_game_choices_round", "game_choices", ["game_round_id"])

    # Now add FK from game_rounds.correct_choice_id → game_choices.id
    op.create_foreign_key(
        "fk_game_rounds_correct_choice",
        "game_rounds",
        "game_choices",
        ["correct_choice_id"],
        ["id"],
    )

    # --- game_mc_guesses ---
    op.create_table(
        "game_mc_guesses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "game_round_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("game_rounds.id"),
            nullable=False,
        ),
        sa.Column(
            "participant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("participants.id"),
            nullable=False,
        ),
        sa.Column(
            "selected_choice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("game_choices.id"),
            nullable=False,
        ),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("points_awarded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "game_round_id", "participant_id", name="uq_mc_guess_round_participant"
        ),
    )


def downgrade() -> None:
    op.drop_table("game_mc_guesses")

    op.drop_constraint(
        "fk_game_rounds_correct_choice", "game_rounds", type_="foreignkey"
    )
    op.drop_index("ix_game_choices_round", "game_choices")
    op.drop_table("game_choices")

    op.drop_column("game_rounds", "round_locked_at")
    op.drop_column("game_rounds", "timer_duration")
    op.drop_column("game_rounds", "correct_choice_id")
    op.drop_column("game_rounds", "question_text")

    # Restore original constraints
    op.drop_constraint("ck_game_round_status", "game_rounds", type_="check")
    op.create_check_constraint(
        "ck_game_round_status",
        "game_rounds",
        "status IN ('pending', 'active', 'revealed', 'completed')",
    )

    op.alter_column(
        "game_rounds",
        "source_prompt_instance_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.alter_column(
        "game_rounds",
        "source_response_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    op.drop_constraint(
        "ck_experience_game_state", "experience_instances", type_="check"
    )
    op.create_check_constraint(
        "ck_experience_game_state",
        "experience_instances",
        "game_state IS NULL OR game_state IN ('lobby', 'question_collection', 'ready_to_start', 'round_active', 'round_reveal', 'leaderboard', 'completed')",
    )

    op.drop_constraint("ck_experience_type", "experience_instances", type_="check")
    op.create_check_constraint(
        "ck_experience_type",
        "experience_instances",
        "experience_type IN ('discussion_recs', 'who_knows_who')",
    )

    op.drop_column("experience_instances", "main_person_participant_id")
