"""Real TexasSolver output, multi-street. Skipped automatically unless scripts/build_solver.sh was run.

These guard the assumptions the hand-built tree cannot: how the solver actually represents street
changes, dealt cards, bet amounts and terminal nodes.
"""

import random
from collections import Counter

import pytest

from pokerlab.analysis import evaluate, prepare
from pokerlab.cache import SolveStore
from pokerlab.handhistory import parse_hand
from pokerlab.progress import ProgressStore
from pokerlab.solver import find_solver_dir, run_solve
from pokerlab.spot import Spot
from pokerlab.strategy import SolveView
from pokerlab.training import HandSession, generate_question

import hh_samples as hh

pytestmark = [
    pytest.mark.solver,
    pytest.mark.skipif(find_solver_dir() is None, reason="TexasSolver not built"),
]


@pytest.fixture(scope="module")
def turn_view():
    """Turn + river solve (dump_rounds=2) with small ranges: ~10 s."""
    spot = Spot(board="Qs,Jh,2h,7d", ip_range="AA,KK,QQ,AKs,QJs,JTs,T9s:0.5,88",
                oop_range="KK,QQ,JJ,AQs,KQs,76s,A5s", pot=55, effective_stack=975,
                max_iteration=60, accuracy=0.5, dump_rounds=2)
    return SolveView(run_solve(spot).tree, spot)


def test_real_tree_crosses_to_the_river_with_correct_bookkeeping(turn_view):
    v = turn_view
    # find a line that reaches the river: check, check
    d = v.describe([])
    assert d["actor"] == "oop" and d["context"]["street"] == "turn" and d["context"]["pot"] == 55
    chk = v.describe(["CHECK", "CHECK"])
    assert chk["node_type"] == "chance_node" and len(chk["deals"]) >= 40
    assert not {"Qs", "Jh", "2h", "7d"} & set(chk["deals"])                      # board cards are never dealt
    card = chk["deals"][0]
    river = v.describe(["CHECK", "CHECK", "@" + card])
    assert river["node_type"] == "action_node" and river["context"]["street"] == "river"
    assert river["context"]["pot"] == 55 and len(river["context"]["board"]) == 5
    # no blocked combos survive the dealt card
    assert all(card not in (c[:2], c[2:]) for r in v.reach(["CHECK", "CHECK", "@" + card]).values() for c in r)


def test_real_bet_amounts_are_street_totals(turn_view):
    v = turn_view
    d = v.describe([])
    bet = next(a for a in d["actions"] if a.startswith("BET") and float(a.split()[1]) < 975)
    amt = float(bet.split()[1])
    ctx = v.describe([bet])["context"]
    assert ctx["pot"] == 55 + amt and ctx["to_call"] == amt and ctx["stacks"]["oop"] == 975 - amt


def test_play_many_real_hands_across_streets(turn_view):
    reasons, streets = Counter(), Counter()
    for seed in range(60):
        rng = random.Random(seed)
        s = HandSession("t", "sid", turn_view, rng.choice(["oop", "ip"]), rng)
        for _ in range(12):
            if s.finished:
                break
            st = s.state()
            s.act(rng.choice([a["action"] for a in st["actions"]]))
        assert s.finished
        res = s.result
        h, vc = s.hero_combo, s.villain_combo
        assert not ({h[:2], h[2:]} & {vc[:2], vc[2:]})
        assert not ({h[:2], h[2:], vc[:2], vc[2:]} & set(res["board"][4:]))
        reasons[res["reason"]] += 1
        streets[len(res["board"])] += 1
        if res["reason"] == "showdown":
            assert len(res["board"]) == 5 and res["winner"] in ("hero", "villain", "split") and res["net"] is not None
            assert res["hero_hand"] and res["villain_hand"]
        if res["reason"] == "fold":
            assert res["winner"] in ("hero", "villain")
    assert reasons["showdown"] > 0 and reasons["fold"] > 0
    assert streets[5] > 0                                           # some hands really reached the river


def test_real_quiz_questions_are_valid_and_varied(turn_view):
    qs = [generate_question(turn_view, random.Random(i)) for i in range(40)]
    assert all(turn_view.combo_strategy(q["path"], q["combo"]) is not None for q in qs)
    assert len({q["role"] for q in qs}) == 2
    assert any(any(step.startswith("@") for step in q["path"]) for q in qs), "expected some river decisions"


def test_real_hand_history_analysis_end_to_end(tmp_path):
    """HAND_A through a genuine flop solve (dump_rounds=2) with tiny ranges."""
    progress = ProgressStore(*SolveStore(tmp_path).shared())
    progress.save_preset("tiny", "srp", ip_range="AA,KK,QQ,JJ,AKs,QJs", oop_range="KK,QQ,JJ,AQs,KQs,JTs")
    hand = parse_hand(hh.HAND_A)
    info = prepare(hand, progress)
    assert info["eligible"]
    spot = Spot.from_dict(info["spot"])
    spot.max_iteration = 60                                          # keep the test quick
    view = SolveView(run_solve(spot).tree, spot)
    ev = evaluate(view, hand, info)
    flop = ev["decisions"][0]
    assert flop["street"] == "flop" and flop["status"] == "graded" and flop["matched"] == "CALL"
    assert 0 <= flop["feedback"]["freq"] <= 1 and abs(sum(flop["feedback"]["freqs"]) - 1) < 1e-6
    # AA facing a 50% flop bet on Q-J-2: the solver must not be folding it
    assert flop["feedback"]["freqs"][flop["feedback"]["actions"].index("FOLD")] < 0.05
    turn = ev["decisions"][1]
    assert turn["street"] == "turn" and turn["status"] in ("graded", "not_in_solve", "out_of_range")
