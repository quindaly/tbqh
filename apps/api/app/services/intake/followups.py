"""Follow-up generation from intake extraction."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.db.models.group_profile import GroupProfile
from app.db.models.prompt import PromptInstance
from app.db.models.session import Session as SessionModel
from app.services.llm.client import call_llm_json
from app.services.llm.prompts import (
    INTAKE_EXTRACTION_SYSTEM,
    INTAKE_EXTRACTION_USER,
)
from app.services.intake.options import normalize_options
from app.services.llm.schemas import intake_extraction_schema

logger = logging.getLogger(__name__)


def generate_followups(
    db: Session,
    session: SessionModel,
    free_text: str,
    participant_id: uuid.UUID,
) -> tuple[GroupProfile, list[PromptInstance]]:
    """Run intake extraction LLM call and create followup prompt_instances.

    Returns (provisional GroupProfile, list of PromptInstances).
    """
    policy = session.policy_profile
    excluded = ", ".join(policy.excluded_categories) if policy.excluded_categories else "none"

    # Call LLM for intake extraction
    extraction = call_llm_json(
        INTAKE_EXTRACTION_SYSTEM,
        INTAKE_EXTRACTION_USER.format(
            free_text=free_text,
            policy_name=policy.name,
            excluded_categories=excluded,
        ),
        intake_extraction_schema(),
        temperature=0.4,
    )

    # Create provisional group profile (not active yet)
    existing_count = (
        db.query(GroupProfile)
        .filter(GroupProfile.group_id == session.group_id)
        .count()
    )

    profile = GroupProfile(
        group_id=session.group_id,
        source_free_text=free_text,
        derived_attributes=extraction,  # provisional; will be replaced on commit
        version=existing_count + 1,
        is_active=False,
    )
    db.add(profile)
    db.flush()

    # Create prompt_instances from followup_question_specs
    instances: list[PromptInstance] = []
    specs = extraction.get("followup_question_specs", [])

    for position, spec in enumerate(specs, start=1):
        # "Other (type your own)" is always the last option, exactly once.
        options = normalize_options(spec["options"])

        pi = PromptInstance(
            session_id=session.id,
            group_profile_id=profile.id,
            participant_id=participant_id,
            prompt_type="group_followup",
            round_number=position,  # keeps the questions in the order the model wrote them
            prompt_text=spec["prompt_text"],
            options=options,
            allow_other=True,
        )
        db.add(pi)
        instances.append(pi)

    db.flush()
    return profile, instances
