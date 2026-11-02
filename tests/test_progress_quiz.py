import json

import pytest

from pokerlab.cache import SolveStore
from pokerlab.progress import ProgressStore
from pokerlab.quiz import DailyQuiz, QuizUnavailable
from pokerlab.strategy import SolveView

import trees


def fb(**kw):
    base = dict(solve_id="s1", mode="play", street="flop", path=[], hero_role="oop", combo="KhKd",
                chosen="CHECK", best="BET 25.000000", freq=0.2, score=0.25, verdict="correct")
    base.update(kw)
    return base


@pytest.fixture()
def stores(tmp_path):
    solves = SolveStore(tmp_path)
    return solves, ProgressStore(*solves.shared())


# ----------------------------------------------------------------- progress ----
def test_stats_empty(stores):
    _, p = stores
    s = p.stats()
    assert s["total"] == 0 and s["avg_score"] is None and s["recent_mistakes"] == []


def test_stats_aggregate(stores):
    _, p = stores
    p.record_attempt(fb(verdict="correct", score=1.0, street="flop"))
    p.record_attempt(fb(verdict="mix", score=0.2, street="flop"))
    p.record_attempt(fb(verdict="mistake", score=0.0, street="turn", freq=0.01, solve_id="s2"))
    s = p.stats()
    assert s["total"] == 3 and abs(s["avg_score"] - 1.2 / 3) < 1e-9
    assert abs(s["correct"] - 1 / 3) < 1e-9 and abs(s["mistake"] - 1 / 3) < 1e-9
    assert {r["street"]: r["n"] for r in s["by_street"]} == {"flop": 2, "turn": 1}
    assert len(s["recent_mistakes"]) == 1 and s["recent_mistakes"][0]["solve_id"] == "s2"
    assert s["daily"][0]["n"] == 3


def test_presets_builtin_is_protected_and_user_presets_win(stores):
    _, p = stores
    assert p.get_preset("srp-sample")["builtin"] == 1
    with pytest.raises(ValueError):
        p.save_preset("srp-sample", "srp", "AA", "KK")
    assert not p.delete_preset("srp-sample")
    p.save_preset("mine", "srp", "AA", "KK", "notes")
    assert p.preset_for_pot_type("srp")["name"] == "mine"           # user preset beats the sample
    assert p.preset_for_pot_type("3bp") is None
    assert p.delete_preset("mine") and p.preset_for_pot_type("srp")["name"] == "srp-sample"


def test_hands_store_dedupes(stores):
    _, p = stores
    assert p.save_hand("H1", "Hero", {"x": 1}) is True
    assert p.save_hand("H1", "Hero", {"x": 2}) is False
    assert p.get_hand("H1")["data"] == {"x": 1} and len(p.list_hands()) == 1
    assert p.delete_hand("H1") and p.get_hand("H1") is None


def test_state_survives_reopening_the_database(tmp_path):
    a = SolveStore(tmp_path)
    pa = ProgressStore(*a.shared())
    pa.record_attempt(fb())
    pa.save_preset("keep", "srp", "AA", "KK")
    b = SolveStore(tmp_path)
    pb = ProgressStore(*b.shared())
    assert pb.stats()["total"] == 1 and pb.get_preset("keep")


# --------------------------------------------------------------------- quiz ----
@pytest.fixture()
def quiz(stores):
    solves, progress = stores
    spot = trees.spot()
    sid, _ = solves.create_or_get(spot)
    solves.set_done(sid, trees.build(), 10, 0.4)
    tree = trees.build()

    def done_ids():
        return [m["id"] for m in solves.list_meta() if m["status"] == "done"]

    q = DailyQuiz(progress, done_ids, lambda s: SolveView(tree, spot), size=3)
    q.sid, q.solves, q.progress = sid, solves, progress
    return q


def test_quiz_needs_a_solve(stores):
    solves, progress = stores
    q = DailyQuiz(progress, lambda: [], lambda s: None)
    with pytest.raises(QuizUnavailable):
        q.today("2026-11-02")


def test_questions_are_deterministic_and_persisted(quiz, stores):
    a = quiz.today("2026-11-02")
    assert a["size"] == 3 and a["answered"] == 0 and not a["complete"]
    stored = quiz.progress.quiz_questions("2026-11-02")
    again = quiz.today("2026-11-02")
    assert [q["state"]["hero_combo"] for q in again["questions"]] == [q["state"]["hero_combo"] for q in a["questions"]]
    assert [q["combo"] for q in stored] == [q["state"]["hero_combo"] for q in a["questions"]]
    # a different day gives a different set (with overwhelming probability), and never leaks the villain hand
    other = quiz.today("2026-11-03")
    assert "villain" not in json.dumps(other).replace("villain_stack", "").replace("villain_committed", "")


def test_answering_is_graded_final_and_updates_progress(quiz):
    day = "2026-11-02"
    t = quiz.today(day)
    q0 = t["questions"][0]
    action = q0["state"]["actions"][0]["action"]
    out = quiz.answer(0, action, day)
    assert out["feedback"]["verdict"] in ("correct", "mix", "mistake") and out["feedback"]["mode"] == "quiz"
    assert out["progress"]["answered"] == 1
    assert quiz.today(day)["questions"][0]["result"]["chosen"] == action
    with pytest.raises(ValueError):
        quiz.answer(0, action, day)                      # answers are final
    with pytest.raises(ValueError):
        quiz.answer(1, "NOT_AN_ACTION", day)
    with pytest.raises(KeyError):
        quiz.answer(9, action, day)
    assert quiz.progress.stats()["total"] == 1           # quiz answers feed the shared stats


def test_streak_counts_consecutive_complete_days(quiz):
    for day in ("2026-11-01", "2026-11-02"):
        for i, q in enumerate(quiz.today(day)["questions"]):
            quiz.answer(i, q["state"]["actions"][0]["action"], day)
    assert quiz.today("2026-11-02")["streak"] == 2
    assert quiz.today("2026-11-03")["streak"] == 2        # today unfinished: streak through yesterday survives
    assert quiz.progress.quiz_streak("2026-11-05", 3) == 0   # a gap resets it


def test_deleted_solve_replaces_unanswered_questions(quiz):
    day = "2026-11-02"
    quiz.today(day)
    spot2 = trees.spot()
    spot2.pot = 60                                        # a second, different solve
    sid2, _ = quiz.solves.create_or_get(spot2)
    quiz.solves.set_done(sid2, trees.build(), 5, 0.5)
    quiz.progress.replace_quiz_question(day, 0, {"solve_id": "gone", "path": [], "role": "oop", "combo": "KhKd"})
    t = quiz.today(day)
    assert t["questions"][0]["solve_id"] in (quiz.sid, sid2)       # replaced with a valid one
