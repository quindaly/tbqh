"""Edge-case tests for the social games feature."""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.db.base import Base
from app.db.models.experience import ExperienceInstance
from app.db.models.game_round import GameRound
from app.db.models.group import Group
from app.db.models.participant import Participant
from app.db.models.policy import PolicyProfile
from app.db.models.prompt import PromptInstance
from app.db.models.session import Session as SessionModel, SessionParticipant
from app.db.models.user import User
from app.services.games import who_knows_who as wkw


@pytest.fixture(scope="module")
def engine():
    from app.core.config import settings

    return create_engine(settings.DATABASE_URL, echo=False)


@pytest.fixture(scope="module")
def tables(engine):
    Base.metadata.create_all(engine)
    yield


@pytest.fixture()
def db(engine, tables):
    conn = engine.connect()
    txn = conn.begin()
    session = sessionmaker(bind=conn, expire_on_commit=False)()
    yield session
    session.close()
    txn.rollback()
    conn.close()


def _seed_lobby(db: Session, num_participants: int = 2):
    user = User(email=f"edge-{uuid.uuid4().hex[:8]}@example.com")
    db.add(user)
    db.flush()

    policy = PolicyProfile(name="default", excluded_categories=[])
    db.add(policy)
    db.flush()

    group = Group(created_by_user_id=user.id, name="Edge Group")
    db.add(group)
    db.flush()

    host = Participant(
        group_id=group.id,
        user_id=user.id,
        display_name="Host",
        role="host",
        join_type="authenticated",
    )
    db.add(host)
    db.flush()

    guests = []
    for i in range(num_participants - 1):
        g = Participant(
            group_id=group.id,
            display_name=f"Guest{i+1}",
            role="guest",
            join_type="anonymous",
        )
        db.add(g)
        guests.append(g)
    db.flush()

    session = SessionModel(
        group_id=group.id,
        policy_profile_id=policy.id,
        join_code=uuid.uuid4().hex[:8].upper(),
    )
    db.add(session)
    db.flush()

    all_participants = [host] + guests
    for p in all_participants:
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

    return user, host, guests, session, exp


class TestCannotJoinAfterLobby:
    def test_join_after_start_rejected(self, db):
        from fastapi import HTTPException

        _, host, guests, session, exp = _seed_lobby(db, num_participants=2)
        wkw.start_answer_collection(db, exp, host.id)

        with pytest.raises(HTTPException) as exc_info:
            wkw.join_game(db, session.join_code, "LateJoiner")
        assert exc_info.value.status_code == 409


class TestMinimumParticipants:
    def test_cannot_start_with_one_player(self, db):
        from fastapi import HTTPException

        _, host, _, session, exp = _seed_lobby(db, num_participants=1)
        with pytest.raises(HTTPException) as exc_info:
            wkw.start_answer_collection(db, exp, host.id)
        assert exc_info.value.status_code == 409


class TestNonHostCannotStart:
    def test_guest_cannot_start(self, db):
        from fastapi import HTTPException

        _, host, guests, session, exp = _seed_lobby(db, num_participants=2)
        with pytest.raises(HTTPException) as exc_info:
            wkw.start_answer_collection(db, exp, guests[0].id)
        assert exc_info.value.status_code == 403


class TestDuplicateAnswer:
    def test_cannot_answer_same_prompt_twice(self, db):
        from fastapi import HTTPException

        _, host, guests, session, exp = _seed_lobby(db, num_participants=2)
        wkw.start_answer_collection(db, exp, host.id)
        prompts = (
            db.query(PromptInstance)
            .filter(PromptInstance.experience_instance_id == exp.id)
            .all()
        )

        wkw.submit_self_answer(db, exp, prompts[0].id, host.id, "my answer")
        with pytest.raises(HTTPException) as exc_info:
            wkw.submit_self_answer(db, exp, prompts[0].id, host.id, "another answer")
        assert exc_info.value.status_code == 409
