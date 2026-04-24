"""Ranking: top similarity + explore bucket + diversity constraints."""

from __future__ import annotations

import logging
import random
import uuid
from typing import Any

from sqlalchemy.orm import Session as DbSession

from app.db.models.question_item import QuestionItem
from app.db.models.content_item import ContentItem
from app.db.models.experience import ExperienceInstance, ContentExposure
from app.db.models.session import Session, SessionParticipant
from app.db.models.participant import Participant
from app.services.embeddings.vector_store import find_similar_questions
from app.services.recommend.filters import (
    get_blocked_question_ids,
    get_previously_shown_question_ids,
)
from app.services.llm.client import call_llm_json
from app.services.llm.prompts import (
    CONSTRAINED_REWORDING_SYSTEM,
    CONSTRAINED_REWORDING_USER,
)
from app.services.llm.schemas import constrained_rewording_schema

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    "batch_size": 10,
    "candidate_k": 200,
    "top_similarity_n": 7,
    "explore_n": 3,
    "explore_policy": "diverse",
    "exclude_previously_shown": True,
    "rewording_enabled": False,
    "diversity": {
        "max_per_topic": 2,
        "min_topic_coverage": 4,
    },
}


def _merge_config(base: dict, overrides: dict | None) -> dict:
    merged = {**base}
    if overrides:
        for k, v in overrides.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = {**merged[k], **v}
            else:
                merged[k] = v
    return merged


def _apply_diversity(
    candidates: list[tuple[QuestionItem, float]],
    top_n: int,
    max_per_topic: int,
) -> list[tuple[QuestionItem, float]]:
    """Select top_n items with diversity constraint on topics."""
    selected: list[tuple[QuestionItem, float]] = []
    topic_counts: dict[str, int] = {}

    for item, dist in candidates:
        topics = item.topics or []
        # Check if adding this would violate max_per_topic
        can_add = True
        for t in topics:
            if topic_counts.get(t, 0) >= max_per_topic:
                can_add = False
                break

        if can_add:
            selected.append((item, dist))
            for t in topics:
                topic_counts[t] = topic_counts.get(t, 0) + 1

        if len(selected) >= top_n:
            break

    # If we don't have enough, fill from remaining
    if len(selected) < top_n:
        selected_ids = {s[0].id for s in selected}
        for item, dist in candidates:
            if item.id not in selected_ids:
                selected.append((item, dist))
                if len(selected) >= top_n:
                    break

    return selected


def _build_explore_set(
    candidates: list[tuple[QuestionItem, float]],
    similarity_ids: set[uuid.UUID],
    explore_n: int,
    explore_policy: str,
    similarity_topics: set[str],
) -> list[tuple[QuestionItem, float]]:
    """Build the explore set from remaining candidates."""
    remaining = [(q, d) for q, d in candidates if q.id not in similarity_ids]

    if not remaining or explore_n <= 0:
        return []

    if explore_policy == "random":
        return random.sample(remaining, min(explore_n, len(remaining)))
    elif explore_policy == "diverse":
        # Pick from topics NOT represented in similarity set
        diverse_candidates = [
            (q, d)
            for q, d in remaining
            if q.topics and not set(q.topics).intersection(similarity_topics)
        ]
        if len(diverse_candidates) >= explore_n:
            return random.sample(diverse_candidates, explore_n)
        # Fill from rest
        result = diverse_candidates[:explore_n]
        if len(result) < explore_n:
            other = [
                (q, d) for q, d in remaining if q.id not in {r[0].id for r in result}
            ]
            result.extend(other[: explore_n - len(result)])
        return result
    else:  # popular — for now just take top candidates by score
        return remaining[:explore_n]


def generate_recommendations(
    db: DbSession,
    experience: ExperienceInstance,
    *,
    config_overrides: dict | None = None,
) -> list[ContentItem]:
    """The full recommendation pipeline for a batch of discussion questions."""
    from app.db.models.group_profile import GroupProfile

    config = _merge_config(
        _merge_config(DEFAULT_CONFIG, experience.config),
        config_overrides,
    )

    profile = db.get(GroupProfile, experience.group_profile_id)
    if profile is None or profile.embedding is None:
        raise ValueError("GroupProfile missing or has no embedding")

    # --- 1. Get participants for blocklist ---
    session = db.get(Session, experience.session_id)
    sp_rows = (
        db.query(SessionParticipant.participant_id)
        .filter(SessionParticipant.session_id == session.id)
        .all()
    )
    participant_ids = [r[0] for r in sp_rows]
    user_ids = [
        p.user_id
        for p in db.query(Participant).filter(Participant.id.in_(participant_ids)).all()
        if p.user_id
    ]

    # --- 2. Blocked IDs ---
    blocked_ids = get_blocked_question_ids(
        db, participant_ids=participant_ids, user_ids=user_ids or None
    )

    # --- 3. Previously shown ---
    if config.get("exclude_previously_shown", True):
        shown_ids = get_previously_shown_question_ids(db, profile.id)
        excluded_ids = blocked_ids | shown_ids
    else:
        excluded_ids = blocked_ids

    # --- 4. Get policy profile excluded categories ---
    policy = session.policy_profile
    excluded_cats = (
        list(policy.excluded_categories) if policy.excluded_categories else []
    )

    # --- 5. Vector search ---
    candidates = find_similar_questions(
        db,
        list(profile.embedding),
        limit=config["candidate_k"],
        excluded_ids=excluded_ids or None,
        excluded_categories=excluded_cats or None,
    )

    if not candidates:
        logger.warning("No candidates found for experience %s", experience.id)
        return []

    # --- 6. Top similarity with diversity ---
    diversity_cfg = config.get("diversity", {})
    max_per_topic = diversity_cfg.get("max_per_topic", 2)
    top_sim_n = config["top_similarity_n"]

    similarity_set = _apply_diversity(candidates, top_sim_n, max_per_topic)
    similarity_ids = {q.id for q, _ in similarity_set}
    similarity_topics: set[str] = set()
    for q, _ in similarity_set:
        if q.topics:
            similarity_topics.update(q.topics)

    # --- 7. Explore set ---
    explore_set = _build_explore_set(
        candidates,
        similarity_ids,
        config["explore_n"],
        config["explore_policy"],
        similarity_topics,
    )

    # --- 8. Combine ---
    final = similarity_set + explore_set
    batch_size = config["batch_size"]
    final = final[:batch_size]

    # --- 9. Create content_items and exposures ---
    # Count existing exposures for position numbering
    existing_count = (
        db.query(ContentExposure)
        .filter(ContentExposure.experience_instance_id == experience.id)
        .count()
    )

    content_items: list[ContentItem] = []
    for idx, (question, _dist) in enumerate(final):
        text = question.question_text
        metadata: dict = {"original_question_item_id": str(question.id)}

        # Optional rewording
        if config.get("rewording_enabled") and profile.derived_attributes:
            try:
                rewording_result = call_llm_json(
                    CONSTRAINED_REWORDING_SYSTEM,
                    CONSTRAINED_REWORDING_USER.format(
                        profile_summary=profile.derived_attributes.get("summary", ""),
                        key_traits=", ".join(
                            profile.derived_attributes.get("key_traits", [])
                        ),
                        question_text=question.question_text,
                        restricted_categories=", ".join(excluded_cats),
                    ),
                    constrained_rewording_schema(),
                )
                if rewording_result.get("should_reword") and rewording_result.get(
                    "reworded_question"
                ):
                    text = rewording_result["reworded_question"]
                    metadata["reworded"] = True
                    metadata["reword_reason"] = rewording_result.get("reason", "")
            except Exception:
                logger.warning("Rewording failed for question %s", question.id)

        ci = ContentItem(
            content_type="discussion_question",
            source_question_item_id=question.id,
            text=text,
            metadata_=metadata,
        )
        db.add(ci)
        db.flush()

        exposure = ContentExposure(
            experience_instance_id=experience.id,
            content_item_id=ci.id,
            position=existing_count + idx + 1,
        )
        db.add(exposure)
        content_items.append(ci)

    db.commit()
    return content_items
