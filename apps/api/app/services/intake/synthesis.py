"""GroupProfile synthesis from free text + follow-up answers."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.db.models.group_profile import GroupProfile
from app.db.models.prompt import PromptInstance, PromptResponse
from app.db.models.session import Session as SessionModel
from app.services.llm.client import call_llm_json
from app.services.llm.prompts import (
    GROUP_PROFILE_SYNTHESIS_SYSTEM,
    GROUP_PROFILE_SYNTHESIS_USER,
)
from app.services.llm.schemas import group_profile_synthesis_schema
from app.services.embeddings.embedder import embed_text

logger = logging.getLogger(__name__)


def commit_group_profile(
    db: Session,
    session: SessionModel,
    profile: GroupProfile,
) -> GroupProfile:
    """Synthesize derived_attributes, compute embedding, and activate profile."""

    # Gather all follow-up Q&A
    instances = (
        db.query(PromptInstance)
        .filter(PromptInstance.group_profile_id == profile.id)
        .all()
    )

    qa_lines: list[str] = []
    for inst in instances:
        responses = (
            db.query(PromptResponse)
            .filter(PromptResponse.prompt_instance_id == inst.id)
            .all()
        )
        for resp in responses:
            answer = resp.selected_option or resp.other_text or "(skipped)"
            qa_lines.append(f"Q: {inst.prompt_text}\nA: {answer}")

    followup_qa = "\n\n".join(qa_lines) if qa_lines else "(no follow-ups answered)"

    # Call LLM to synthesize profile
    policy = session.policy_profile
    synthesis = call_llm_json(
        GROUP_PROFILE_SYNTHESIS_SYSTEM,
        GROUP_PROFILE_SYNTHESIS_USER.format(
            free_text=profile.source_free_text or "",
            followup_qa=followup_qa,
            policy_name=policy.name,
        ),
        group_profile_synthesis_schema(),
    )

    # Build text representation for embedding
    embed_parts = [
        profile.source_free_text or "",
        synthesis.get("summary", ""),
        " ".join(synthesis.get("key_traits", [])),
        " ".join(synthesis.get("topics_of_interest", [])),
    ]
    embed_string = " | ".join(p for p in embed_parts if p)

    embedding = embed_text(embed_string)

    # Deactivate previous profiles
    db.query(GroupProfile).filter(
        GroupProfile.group_id == profile.group_id,
        GroupProfile.id != profile.id,
    ).update({"is_active": False})

    # Update and activate
    profile.derived_attributes = synthesis
    profile.embedding = embedding
    profile.is_active = True
    db.add(profile)
    db.commit()
    db.refresh(profile)

    return profile
