"""Initial tables and pgvector extension.

Revision ID: 001_initial
Revises:
Create Date: 2026-03-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- groups ---
    op.create_table(
        "groups",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("created_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- participants ---
    op.create_table(
        "participants",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("group_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("join_type", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('host', 'guest')", name="ck_participant_role"),
        sa.CheckConstraint("join_type IN ('authenticated', 'anonymous')", name="ck_participant_join_type"),
    )

    # --- policy_profiles ---
    op.create_table(
        "policy_profiles",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("excluded_categories", sa.dialects.postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- sessions ---
    op.create_table(
        "sessions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("group_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("policy_profile_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("policy_profiles.id"), nullable=False),
        sa.Column("join_code", sa.Text(), nullable=False, unique=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active', 'ended')", name="ck_session_status"),
    )

    # --- session_participants ---
    op.create_table(
        "session_participants",
        sa.Column("session_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), primary_key=True),
        sa.Column("participant_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("participants.id"), primary_key=True),
    )

    # --- group_profiles ---
    op.create_table(
        "group_profiles",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("group_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("source_free_text", sa.Text(), nullable=True),
        sa.Column("derived_attributes", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_group_profiles_embedding", "group_profiles", ["embedding"], postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"})

    # --- prompt_templates ---
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- prompt_instances ---
    op.create_table(
        "prompt_instances",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("session_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("group_profile_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("group_profiles.id"), nullable=True),
        sa.Column("participant_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("participants.id"), nullable=True),
        sa.Column("prompt_type", sa.Text(), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("options", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("allow_other", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- prompt_responses ---
    op.create_table(
        "prompt_responses",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("prompt_instance_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("prompt_instances.id"), nullable=False),
        sa.Column("participant_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("participants.id"), nullable=False),
        sa.Column("selected_option", sa.Text(), nullable=True),
        sa.Column("other_text", sa.Text(), nullable=True),
        sa.Column("normalized_value", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- question_items ---
    op.create_table(
        "question_items",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("content_categories", sa.dialects.postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("topics", sa.dialects.postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("audience_fit", sa.dialects.postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("depth_level", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active', 'retired')", name="ck_question_item_status"),
    )
    op.create_index("ix_question_items_embedding", "question_items", ["embedding"], postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"})

    # --- content_items ---
    op.create_table(
        "content_items",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("source_question_item_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("question_items.id"), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- experience_instances ---
    op.create_table(
        "experience_instances",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("session_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("group_profile_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("group_profiles.id"), nullable=False),
        sa.Column("experience_type", sa.Text(), nullable=False),
        sa.Column("config", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active', 'completed')", name="ck_experience_status"),
    )

    # --- content_exposures ---
    op.create_table(
        "content_exposures",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("experience_instance_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("experience_instances.id"), nullable=False),
        sa.Column("content_item_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("content_items.id"), nullable=False),
        sa.Column("shown_to_participant_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("participants.id"), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("shown_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("experience_instance_id", "content_item_id", name="uq_exposure_content"),
    )

    # --- user_question_feedback ---
    op.create_table(
        "user_question_feedback",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("participant_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("participants.id"), nullable=False),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("question_item_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("question_items.id"), nullable=False),
        sa.Column("content_item_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("content_items.id"), nullable=True),
        sa.Column("experience_instance_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("experience_instances.id"), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("feedback IN ('like', 'dislike', 'skip')", name="ck_feedback_type"),
    )

    # --- event_log ---
    op.create_table(
        "event_log",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("session_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("experience_instance_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("participant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- player_actions ---
    op.create_table(
        "player_actions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("experience_instance_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("experience_instances.id"), nullable=False),
        sa.Column("participant_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("participants.id"), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- score_snapshots ---
    op.create_table(
        "score_snapshots",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("experience_instance_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("experience_instances.id"), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Seed default policy profile
    op.execute(
        """
        INSERT INTO policy_profiles (id, name, excluded_categories)
        VALUES (gen_random_uuid(), 'family_friendly', '{sexual,violence,drugs,hate_speech}')
        """
    )


def downgrade() -> None:
    op.drop_table("score_snapshots")
    op.drop_table("player_actions")
    op.drop_table("event_log")
    op.drop_table("user_question_feedback")
    op.drop_table("content_exposures")
    op.drop_table("experience_instances")
    op.drop_table("content_items")
    op.drop_index("ix_question_items_embedding", table_name="question_items")
    op.drop_table("question_items")
    op.drop_table("prompt_responses")
    op.drop_table("prompt_instances")
    op.drop_table("prompt_templates")
    op.drop_index("ix_group_profiles_embedding", table_name="group_profiles")
    op.drop_table("group_profiles")
    op.drop_table("session_participants")
    op.drop_table("sessions")
    op.drop_table("policy_profiles")
    op.drop_table("participants")
    op.drop_table("groups")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS vector")
