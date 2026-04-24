"""Tests for the social games feature – Who Knows Who."""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.db.base import Base
from app.db.models.experience import ExperienceInstance
from app.db.models.game_guess import GameGuess
from app.db.models.game_round import GameRound
from app.db.models.group import Group
from app.db.models.participant import Participant
from app.db.models.policy import PolicyProfile
from app.db.models.prompt import PromptInstance, PromptResponse
from app.db.models.session import Session as SessionModel, SessionParticipant
from app.db.models.user import User
from app.services.games.state import transition_state, VALID_TRANSITIONS
from app.services.games.scoring import compute_scores
from app.services.games import who_knows_who as wkw


# --------------- fixtures ---------------


@pytest.fixture(scope="module")
def engine():
    """Use the real DATABASE_URL (test against actual Postgres w/ pgvector)."""
    from app.core.config import settings

    eng = create_engine(settings.DATABASE_URL, echo=False)
    return eng


@pytest.fixture(scope="module")
def tables(engine):
    Base.metadata.create_all(engine)
    yield
    # Leave tables in place; tests are isolated by rollback.


@pytest.fixture()
def db(engine, tables):
    """Each test runs inside a rolled-back transaction."""
    conn = engine.connect()
    txn = conn.begin()
    session = sessionmaker(bind=conn, expire_on_commit=False)()
    yield session
    session.close()
    txn.rollback()
    conn.close()


def _seed(db: Session):
    """Create a minimal user + policy + two-participant game in lobby."""
    user = User(email=f"test-{uuid.uuid4().hex[:8]}@example.com")
    db.add(user)
    db.flush()

    policy = PolicyProfile(name="default", excluded_categories=[])
    db.add(policy)
    db.flush()

    group = Group(created_by_user_id=user.id, name="Test Group")
    db.add(group)
    db.flush()

    host = Participant(
        group_id=group.id,
        user_id=user.id,
        display_name="Host",
        role="host",
        join_type="authenticated",
    )
    guest = Participant(
        group_id=group.id, display_name="Guest", role="guest", join_type="anonymous"
    )
    db.add_all([host, guest])
    db.flush()

    session = SessionModel(
        group_id=group.id,
        policy_profile_id=policy.id,
        join_code=uuid.uuid4().hex[:8].upper(),
    )
    db.add(session)
    db.flush()

    for p in [host, guest]:
        db.add(SessionParticipant(session_id=session.id, participant_id=p.id))
    db.flush()

    exp = ExperienceInstance(
        session_id=session.id,
        experience_type="who_knows_who",
        game_state="lobby",
        game_config={"num_questions": 3, "max_rounds": 3, "min_answer_length": 2},
        max_rounds=3,
        current_round=0,
    )
    db.add(exp)
    db.flush()

    return user, policy, group, host, guest, session, exp


# --------------- state machine tests ---------------


class TestStateMachine:
    def test_valid_transitions(self, db):
        _, _, _, _, _, _, exp = _seed(db)
        transition_state(db, exp, "question_collection")
        assert exp.game_state == "question_collection"

    def test_invalid_transition_raises(self, db):
        _, _, _, _, _, _, exp = _seed(db)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            transition_state(db, exp, "round_active")
        assert exc_info.value.status_code == 409

    def test_full_lifecycle(self, db):
        _, _, _, _, _, _, exp = _seed(db)
        for target in [
            "question_collection",
            "ready_to_start",
            "round_active",
            "round_reveal",
            "leaderboard",
            "completed",
        ]:
            transition_state(db, exp, target)
            assert exp.game_state == target


# --------------- answer collection tests ---------------


class TestAnswerCollection:
    def test_start_creates_prompts(self, db):
        _, _, _, host, guest, session, exp = _seed(db)
        wkw.start_answer_collection(db, exp, host.id)
        prompts = (
            db.query(PromptInstance)
            .filter(PromptInstance.experience_instance_id == exp.id)
            .all()
        )
        assert len(prompts) == 3  # num_questions = 3

    def test_submit_answers_and_auto_transition(self, db):
        _, _, _, host, guest, session, exp = _seed(db)
        wkw.start_answer_collection(db, exp, host.id)
        prompts = (
            db.query(PromptInstance)
            .filter(PromptInstance.experience_instance_id == exp.id)
            .all()
        )

        # Both participants answer all prompts
        for p_id in [host.id, guest.id]:
            for pi in prompts:
                wkw.submit_self_answer(
                    db, exp, pi.id, p_id, f"answer-{uuid.uuid4().hex[:4]}"
                )

        # After all answers, state should have advanced to round_active
        db.refresh(exp)
        assert exp.game_state == "round_active"
        assert exp.current_round == 1

    def test_reject_blank_answer(self, db):
        from fastapi import HTTPException

        _, _, _, host, guest, session, exp = _seed(db)
        wkw.start_answer_collection(db, exp, host.id)
        prompts = (
            db.query(PromptInstance)
            .filter(PromptInstance.experience_instance_id == exp.id)
            .all()
        )

        with pytest.raises(HTTPException) as exc_info:
            wkw.submit_self_answer(db, exp, prompts[0].id, host.id, "a")
        assert exc_info.value.status_code == 422


# --------------- round + guess tests ---------------


class TestGameplay:
    def _setup_active_game(self, db):
        _, _, _, host, guest, session, exp = _seed(db)
        wkw.start_answer_collection(db, exp, host.id)
        prompts = (
            db.query(PromptInstance)
            .filter(PromptInstance.experience_instance_id == exp.id)
            .all()
        )
        for p_id in [host.id, guest.id]:
            for pi in prompts:
                wkw.submit_self_answer(
                    db, exp, pi.id, p_id, f"answer-{uuid.uuid4().hex[:6]}"
                )
        db.refresh(exp)
        return host, guest, session, exp

    def test_rounds_created(self, db):
        host, guest, session, exp = self._setup_active_game(db)
        rounds = (
            db.query(GameRound)
            .filter(GameRound.experience_instance_id == exp.id)
            .order_by(GameRound.round_number)
            .all()
        )
        assert len(rounds) <= 3
        assert rounds[0].status == "active"

    def test_submit_guess_correct(self, db):
        host, guest, session, exp = self._setup_active_game(db)
        game_round = (
            db.query(GameRound)
            .filter(
                GameRound.experience_instance_id == exp.id,
                GameRound.round_number == 1,
            )
            .first()
        )

        # Determine who is NOT the answering participant
        guesser = host if game_round.answering_participant_id != host.id else guest
        result = wkw.submit_guess(
            db, exp, game_round.id, guesser.id, game_round.answering_participant_id
        )
        assert result["is_correct"] is True

    def test_answer_owner_cannot_guess(self, db):
        from fastapi import HTTPException

        host, guest, session, exp = self._setup_active_game(db)
        game_round = (
            db.query(GameRound)
            .filter(
                GameRound.experience_instance_id == exp.id,
                GameRound.round_number == 1,
            )
            .first()
        )

        with pytest.raises(HTTPException) as exc_info:
            wkw.submit_guess(
                db,
                exp,
                game_round.id,
                game_round.answering_participant_id,
                game_round.answering_participant_id,
            )
        assert exc_info.value.status_code == 403

    def test_no_duplicate_guess(self, db):
        from fastapi import HTTPException

        host, guest, session, exp = self._setup_active_game(db)
        game_round = (
            db.query(GameRound)
            .filter(
                GameRound.experience_instance_id == exp.id,
                GameRound.round_number == 1,
            )
            .first()
        )

        guesser = host if game_round.answering_participant_id != host.id else guest
        wkw.submit_guess(
            db, exp, game_round.id, guesser.id, game_round.answering_participant_id
        )
        with pytest.raises(HTTPException) as exc_info:
            wkw.submit_guess(
                db, exp, game_round.id, guesser.id, game_round.answering_participant_id
            )
        assert exc_info.value.status_code == 409


# --------------- leaderboard / scoring tests ---------------


class TestScoring:
    def test_compute_scores(self, db):
        _, _, _, host, guest, session, exp = _seed(db)
        wkw.start_answer_collection(db, exp, host.id)
        prompts = (
            db.query(PromptInstance)
            .filter(PromptInstance.experience_instance_id == exp.id)
            .all()
        )
        for p_id in [host.id, guest.id]:
            for pi in prompts:
                wkw.submit_self_answer(
                    db, exp, pi.id, p_id, f"answer-{uuid.uuid4().hex[:6]}"
                )
        db.refresh(exp)

        # Submit a correct guess on round 1
        game_round = (
            db.query(GameRound)
            .filter(
                GameRound.experience_instance_id == exp.id,
                GameRound.round_number == 1,
            )
            .first()
        )

        guesser = host if game_round.answering_participant_id != host.id else guest
        wkw.submit_guess(
            db, exp, game_round.id, guesser.id, game_round.answering_participant_id
        )

        scores = compute_scores(db, exp.id)
        assert len(scores) == 2
        assert scores[0]["score"] >= 1  # At least the correct guesser has 1


# --------------- replay tests ---------------


class TestReplay:
    def test_replay_creates_new_experience(self, db):
        _, _, _, host, guest, session, exp = _seed(db)
        result = wkw.replay_game(db, exp)
        assert result["experience_instance_id"] != str(exp.id)

        new_exp = db.get(
            ExperienceInstance, uuid.UUID(result["experience_instance_id"])
        )
        assert new_exp.parent_experience_instance_id == exp.id
        assert new_exp.game_state == "lobby"
        assert new_exp.session_id == exp.session_id
