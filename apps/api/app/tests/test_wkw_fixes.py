"""Who Knows Who: host-only controls, hidden answer owner, fair rounds, replay,
names and the three-player minimum."""

import uuid
from collections import Counter

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.experience import ExperienceInstance
from app.db.models.game_round import GameRound
from app.db.models.prompt import PromptInstance
from app.services.games import who_knows_who as wkw
from app.services.games.scoring import compute_scores
from app.services.games.state import get_game_state_payload


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


def make_game(db, names=("Bea", "Cal"), host="Quin"):
    created = wkw.create_game(db, None, host)
    exp = db.get(ExperienceInstance, uuid.UUID(created["experience_instance_id"]))
    host_id = uuid.UUID(created["participant_id"])
    others = [
        uuid.UUID(wkw.join_game(db, created["join_code"], n)["participant_id"])
        for n in names
    ]
    return created, exp, host_id, others


def start_and_answer(db, exp, host_id, everyone, answer="something"):
    wkw.start_answer_collection(db, exp, host_id)
    prompts = (
        db.query(PromptInstance)
        .filter(PromptInstance.experience_instance_id == exp.id)
        .all()
    )
    for pid in everyone:
        for pi in prompts:
            wkw.submit_self_answer(db, exp, pi.id, pid, f"{answer} {uuid.uuid4().hex[:4]}")
    db.refresh(exp)


def current_round(db, exp):
    return (
        db.query(GameRound)
        .filter(
            GameRound.experience_instance_id == exp.id,
            GameRound.round_number == exp.current_round,
        )
        .one()
    )


def code_of(excinfo):
    return excinfo.value.status_code


class TestNamesAndRoster:
    def test_blank_and_long_names_rejected(self, db):
        for bad in ("", "   ", "x" * 41):
            with pytest.raises(HTTPException) as e:
                wkw.create_game(db, None, bad)
            assert code_of(e) == 422

    def test_names_are_trimmed(self, db):
        created = wkw.create_game(db, None, "  Quin   Daly ")
        lobby = wkw.get_lobby_payload(
            db, db.get(ExperienceInstance, uuid.UUID(created["experience_instance_id"]))
        )
        assert lobby["participants"][0]["display_name"] == "Quin Daly"

    def test_duplicate_name_rejected_case_insensitively(self, db):
        created, exp, host_id, _ = make_game(db, names=("Bea",))
        with pytest.raises(HTTPException) as e:
            wkw.join_game(db, created["join_code"], "bea")
        assert code_of(e) == 409
        with pytest.raises(HTTPException) as e:
            wkw.join_game(db, created["join_code"], "QUIN")
        assert code_of(e) == 409

    def test_guest_host_is_recorded_as_anonymous(self, db):
        from app.db.models.participant import Participant

        created = wkw.create_game(db, None, "Quin")
        host = db.get(Participant, uuid.UUID(created["participant_id"]))
        assert host.join_type == "anonymous"

    def test_full_game_rejects_more_players(self, db):
        created = wkw.create_game(db, None, "Host")
        for i in range(wkw.MAX_PLAYERS - 1):
            wkw.join_game(db, created["join_code"], f"P{i}")
        with pytest.raises(HTTPException) as e:
            wkw.join_game(db, created["join_code"], "OneTooMany")
        assert code_of(e) == 409


class TestStartRules:
    def test_needs_three_players(self, db):
        _, exp, host_id, _ = make_game(db, names=("Bea",))
        with pytest.raises(HTTPException) as e:
            wkw.start_answer_collection(db, exp, host_id)
        assert code_of(e) == 409

    def test_host_of_another_game_cannot_start_this_one(self, db):
        _, exp, _, _ = make_game(db)
        _, _, other_host, _ = make_game(db)
        with pytest.raises(HTTPException) as e:
            wkw.start_answer_collection(db, exp, other_host)
        assert code_of(e) == 403

    def test_stranger_cannot_answer(self, db):
        _, exp, host_id, _ = make_game(db)
        wkw.start_answer_collection(db, exp, host_id)
        prompt = db.query(PromptInstance).filter_by(experience_instance_id=exp.id).first()
        with pytest.raises(HTTPException) as e:
            wkw.submit_self_answer(db, exp, prompt.id, uuid.uuid4(), "hello")
        assert code_of(e) == 403

    def test_answers_closed_once_the_game_is_underway(self, db):
        _, exp, host_id, others = make_game(db)
        start_and_answer(db, exp, host_id, [host_id, *others])
        prompt = db.query(PromptInstance).filter_by(experience_instance_id=exp.id).first()
        with pytest.raises(HTTPException) as e:
            wkw.submit_self_answer(db, exp, prompt.id, host_id, "again")
        assert code_of(e) == 409

    def test_short_and_long_answers(self, db):
        _, exp, host_id, _ = make_game(db)
        wkw.start_answer_collection(db, exp, host_id)
        prompt = db.query(PromptInstance).filter_by(experience_instance_id=exp.id).first()
        with pytest.raises(HTTPException) as e:
            wkw.submit_self_answer(db, exp, prompt.id, host_id, "x")
        assert code_of(e) == 422
        with pytest.raises(HTTPException) as e:
            wkw.submit_self_answer(db, exp, prompt.id, host_id, "x" * (wkw.MAX_ANSWER_LEN + 1))
        assert code_of(e) == 422
        assert wkw.submit_self_answer(db, exp, prompt.id, host_id, "No")["ok"]

    def test_prompts_report_what_a_player_already_answered(self, db):
        _, exp, host_id, others = make_game(db)
        wkw.start_answer_collection(db, exp, host_id)
        prompts = wkw.get_prompts_for_experience(db, exp.id, host_id)
        wkw.submit_self_answer(db, exp, uuid.UUID(prompts[0]["id"]), host_id, "first")
        mine = wkw.get_prompts_for_experience(db, exp.id, host_id)
        theirs = wkw.get_prompts_for_experience(db, exp.id, others[0])
        assert [p["answered"] for p in mine][:2] == [True, False]
        assert not any(p["answered"] for p in theirs)


class TestRounds:
    def test_every_player_gets_a_fair_share_and_nobody_repeats(self, db):
        for _ in range(5):
            _, exp, host_id, others = make_game(db)
            start_and_answer(db, exp, host_id, [host_id, *others])
            rounds = (
                db.query(GameRound)
                .filter(GameRound.experience_instance_id == exp.id)
                .order_by(GameRound.round_number)
                .all()
            )
            assert len(rounds) == 10
            owners = [r.answering_participant_id for r in rounds]
            counts = Counter(owners).values()
            assert max(counts) - min(counts) <= 1
            assert all(a != b for a, b in zip(owners, owners[1:]))

    def test_state_hides_the_owner_until_the_reveal(self, db):
        _, exp, host_id, others = make_game(db)
        start_and_answer(db, exp, host_id, [host_id, *others])
        rnd = current_round(db, exp)
        owner = rnd.answering_participant_id
        guesser = next(p for p in [host_id, *others] if p != owner)

        as_guesser = get_game_state_payload(db, exp, guesser)["round"]
        assert "answering_participant_id" not in as_guesser
        assert as_guesser["is_yours"] is False
        assert as_guesser["you_guessed"] is False
        as_owner = get_game_state_payload(db, exp, owner)["round"]
        assert as_owner["is_yours"] is True

        wkw.submit_guess(db, exp, rnd.id, guesser, owner)
        after = get_game_state_payload(db, exp, guesser)["round"]
        assert after["you_guessed"] is True
        assert after["guessed_count"] == 1
        assert after["guesser_count"] == 2

    def test_guesses_must_name_players_of_this_game(self, db):
        _, exp, host_id, others = make_game(db)
        start_and_answer(db, exp, host_id, [host_id, *others])
        rnd = current_round(db, exp)
        guesser = next(p for p in [host_id, *others] if p != rnd.answering_participant_id)
        with pytest.raises(HTTPException) as e:
            wkw.submit_guess(db, exp, rnd.id, uuid.uuid4(), guesser)
        assert code_of(e) == 403
        with pytest.raises(HTTPException) as e:
            wkw.submit_guess(db, exp, rnd.id, guesser, uuid.uuid4())
        assert code_of(e) == 422


class TestRevealAndAdvance:
    def _live(self, db):
        _, exp, host_id, others = make_game(db)
        everyone = [host_id, *others]
        start_and_answer(db, exp, host_id, everyone)
        return exp, host_id, others, everyone

    def test_only_the_host_reveals_early(self, db):
        exp, host_id, others, _ = self._live(db)
        rnd = current_round(db, exp)
        with pytest.raises(HTTPException) as e:
            wkw.reveal_round(db, exp, rnd.id, others[0])
        assert code_of(e) == 403
        with pytest.raises(HTTPException) as e:
            wkw.reveal_round(db, exp, rnd.id, uuid.uuid4())
        assert code_of(e) == 403
        assert wkw.reveal_round(db, exp, rnd.id, host_id)["ok"]
        db.refresh(exp)
        assert exp.game_state == "round_reveal"

    def test_anyone_can_reveal_once_everyone_guessed(self, db):
        exp, host_id, others, everyone = self._live(db)
        rnd = current_round(db, exp)
        owner = rnd.answering_participant_id
        for p in everyone:
            if p != owner:
                wkw.submit_guess(db, exp, rnd.id, p, owner)
        non_host = next(p for p in others)
        assert wkw.reveal_round(db, exp, rnd.id, non_host)["ok"]

    def test_cannot_reveal_twice_or_advance_before_reveal(self, db):
        exp, host_id, others, _ = self._live(db)
        rnd = current_round(db, exp)
        with pytest.raises(HTTPException) as e:
            wkw.advance_round(db, exp, rnd.id, host_id)
        assert code_of(e) == 409
        wkw.reveal_round(db, exp, rnd.id, host_id)
        with pytest.raises(HTTPException) as e:
            wkw.reveal_round(db, exp, rnd.id, host_id)
        assert code_of(e) == 409

    def test_only_the_host_advances(self, db):
        exp, host_id, others, _ = self._live(db)
        rnd = current_round(db, exp)
        wkw.reveal_round(db, exp, rnd.id, host_id)
        with pytest.raises(HTTPException) as e:
            wkw.advance_round(db, exp, rnd.id, others[0])
        assert code_of(e) == 403
        assert wkw.advance_round(db, exp, rnd.id, host_id) == {"ok": True, "is_last": False}
        db.refresh(exp)
        assert exp.current_round == 2 and exp.game_state == "round_active"

    def test_full_game_to_the_leaderboard(self, db):
        exp, host_id, others, everyone = self._live(db)
        for _ in range(exp.max_rounds):
            rnd = current_round(db, exp)
            wkw.reveal_round(db, exp, rnd.id, host_id)
            res = wkw.advance_round(db, exp, rnd.id, host_id)
        assert res["is_last"] is True
        db.refresh(exp)
        assert exp.game_state == "leaderboard"
        assert len(compute_scores(db, exp.id)) == 3


class TestScoringRanks:
    def test_ties_share_a_rank(self, db):
        _, exp, host_id, others = make_game(db)
        ranks = [r["rank"] for r in compute_scores(db, exp.id)]
        assert ranks == [1, 1, 1]

    def test_scores_are_ordered_and_ranked(self, db):
        _, exp, host_id, others = make_game(db)
        start_and_answer(db, exp, host_id, [host_id, *others])
        rnd = current_round(db, exp)
        owner = rnd.answering_participant_id
        guesser = next(p for p in [host_id, *others] if p != owner)
        wkw.submit_guess(db, exp, rnd.id, guesser, owner)
        scores = compute_scores(db, exp.id)
        assert scores[0]["participant_id"] == str(guesser)
        assert [s["rank"] for s in scores] == [1, 2, 2]


class TestReplay:
    def _finished(self, db):
        created, exp, host_id, others = make_game(db)
        start_and_answer(db, exp, host_id, [host_id, *others])
        exp.game_state = "leaderboard"
        db.flush()
        return created, exp, host_id, others

    def test_everyone_lands_in_the_same_next_lobby(self, db):
        _, exp, host_id, others = self._finished(db)
        first = wkw.replay_game(db, exp, others[0])
        second = wkw.replay_game(db, exp, host_id)
        assert first["experience_instance_id"] == second["experience_instance_id"]
        assert first["experience_instance_id"] != str(exp.id)

    def test_only_those_who_come_back_are_in_the_next_game(self, db):
        _, exp, host_id, others = self._finished(db)
        res = wkw.replay_game(db, exp, others[0])
        nxt = db.get(ExperienceInstance, uuid.UUID(res["experience_instance_id"]))
        lobby = wkw.get_lobby_payload(db, nxt)
        assert [p["id"] for p in lobby["participants"]] == [str(others[0])]
        # The original host is not back, so the first returner hosts.
        assert lobby["host_id"] == str(others[0])
        wkw.replay_game(db, exp, host_id)
        lobby = wkw.get_lobby_payload(db, nxt)
        assert {p["id"] for p in lobby["participants"]} == {str(others[0]), str(host_id)}
        assert lobby["host_id"] == str(host_id)

    def test_a_game_in_progress_cannot_be_replayed(self, db):
        _, exp, host_id, others = make_game(db)
        with pytest.raises(HTTPException) as e:
            wkw.replay_game(db, exp, host_id)
        assert code_of(e) == 409

    def test_strangers_cannot_replay(self, db):
        _, exp, _, _ = self._finished(db)
        with pytest.raises(HTTPException) as e:
            wkw.replay_game(db, exp, uuid.uuid4())
        assert code_of(e) == 403

    def test_replay_game_plays_with_only_the_returners(self, db):
        created, exp, host_id, others = self._finished(db)
        returned = [host_id, others[0], others[1]]
        for p in returned:
            res = wkw.replay_game(db, exp, p)
        nxt = db.get(ExperienceInstance, uuid.UUID(res["experience_instance_id"]))
        start_and_answer(db, nxt, host_id, returned)
        assert nxt.game_state == "round_active"

    def test_join_code_leads_to_the_newest_lobby(self, db):
        created, exp, host_id, others = self._finished(db)
        res = wkw.replay_game(db, exp, host_id)
        joined = wkw.join_game(db, created["join_code"], "Late")
        assert joined["experience_instance_id"] == res["experience_instance_id"]
        nxt = db.get(ExperienceInstance, uuid.UUID(res["experience_instance_id"]))
        ids = {p["id"] for p in wkw.get_lobby_payload(db, nxt)["participants"]}
        assert joined["participant_id"] in ids

    def test_status_reports_who_is_back(self, db):
        _, exp, host_id, others = self._finished(db)
        assert wkw.replay_status(db, exp)["next_experience_id"] is None
        wkw.replay_game(db, exp, others[1])
        st = wkw.replay_status(db, exp)
        assert st["returned_ids"] == [str(others[1])]
        assert st["participant_count"] == 3


class TestLobbyPayload:
    def test_replay_lobby_lists_who_is_not_back_yet(self, db):
        _, exp, host_id, others = make_game(db)
        start_and_answer(db, exp, host_id, [host_id, *others])
        exp.game_state = "leaderboard"
        db.flush()
        res = wkw.replay_game(db, exp, others[0])
        nxt = db.get(ExperienceInstance, uuid.UUID(res["experience_instance_id"]))
        lobby = wkw.get_lobby_payload(db, nxt)
        assert lobby["is_replay"] is True
        assert {p["id"] for p in lobby["absent_participants"]} == {str(host_id), str(others[1])}
        first = wkw.get_lobby_payload(db, exp)
        assert first["is_replay"] is False and first["absent_participants"] == []
        assert first["min_players"] == 3
