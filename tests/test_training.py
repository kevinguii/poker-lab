import math
import random
from collections import Counter

import pytest

from pokerlab.strategy import SolveView
from pokerlab.training import HandSession, generate_question, grade, sample_matchup

import trees

B25, C, R85 = "BET 25.000000", "CALL", "RAISE 85.000000"


@pytest.fixture()
def view():
    return SolveView(trees.build(), trees.spot())


# ---------------------------------------------------------------- grading ----
def test_grade_verdicts():
    acts = ["CHECK", "BET 25.000000", "BET 100.000000"]
    freqs = [0.70, 0.27, 0.03]
    g = grade(acts, freqs, "CHECK")
    assert g["verdict"] == "correct" and g["best"] == "CHECK" and g["score"] == 1.0
    g = grade(acts, freqs, "BET 25.000000")
    assert g["verdict"] == "correct" and math.isclose(g["score"], 0.27 / 0.70)     # >= 25% counts as correct
    g = grade(acts, [0.9, 0.07, 0.03], "BET 25.000000")
    assert g["verdict"] == "mix"
    g = grade(acts, freqs, "BET 100.000000")
    assert g["verdict"] == "mistake" and g["freq"] == 0.03


def test_grade_best_action_with_low_top_frequency_is_correct():
    g = grade(["A", "B", "C", "D", "E"], [0.21, 0.2, 0.2, 0.2, 0.19], "A")
    assert g["verdict"] == "correct"


def test_grade_rejects_unavailable_action():
    with pytest.raises(ValueError):
        grade(["CHECK"], [1.0], "FOLD")


# ---------------------------------------------------------------- sampling ----
def test_sample_matchup_never_shares_cards_and_matches_exact_distribution():
    hero = {"AsKs": 1.0, "AdKd": 1.0, "QcQd": 0.5}
    vill = {"AsAh": 1.0, "KcKd": 1.0, "QcQh": 1.0, "7h7d": 0.25}
    # exact joint over card-compatible pairs
    joint = {}
    for h, wh in hero.items():
        for v, wv in vill.items():
            if not ({h[:2], h[2:]} & {v[:2], v[2:]}):
                joint[(h, v)] = wh * wv
    z = sum(joint.values())
    rng = random.Random(7)
    n = 40000
    seen = Counter(sample_matchup(rng, hero, vill) for _ in range(n))
    assert set(seen) == set(joint)                       # incompatible pairs never appear
    for pair, w in joint.items():
        assert abs(seen[pair] / n - w / z) < 0.01, pair


def test_sample_matchup_is_deterministic_for_a_seed():
    hero, vill = {"AsKs": 1.0, "QcQd": 1.0}, {"7h7d": 1.0, "8h8d": 1.0}
    a = [sample_matchup(random.Random(3), hero, vill) for _ in range(3)]
    assert a[0] == a[1] == a[2]


def test_sample_matchup_with_no_compatible_hands():
    with pytest.raises(ValueError):
        sample_matchup(random.Random(0), {"AsKs": 1.0}, {"AsKs": 1.0})


# ----------------------------------------------------------------- sessions ----
def play_randomly(view, role, seed):
    rng = random.Random(seed)
    s = HandSession("t", "sid", view, role, rng)
    guard = 0
    while not s.finished and guard < 20:
        st = s.state()
        s.act(rng.choice([a["action"] for a in st["actions"]]))
        guard += 1
    return s


@pytest.mark.parametrize("role", ["oop", "ip"])
def test_many_random_hands_keep_invariants(view, role):
    reasons = Counter()
    for seed in range(120):
        s = play_randomly(view, role, seed)
        assert s.finished and s.result
        h, v = s.hero_combo, s.villain_combo
        assert not ({h[:2], h[2:]} & {v[:2], v[2:]}), "players share a card"
        board = s.result["board"]
        assert len(set(board)) == len(board)
        assert not ({h[:2], h[2:], v[:2], v[2:]} & set(board[3:])), "dealt card collides with a hand"
        reasons[s.result["reason"]] += 1
        if s.result["reason"] == "fold":
            assert s.result["winner"] in ("hero", "villain") and s.result["net"] is not None
    assert "fold" in reasons or "street_end" in reasons
    assert sum(reasons.values()) == 120


def test_street_change_deals_a_turn_card(view):
    for seed in range(300):
        s = play_randomly(view, "oop", seed)
        if len(s.result["board"]) == 4:
            assert s.result["board"][3] in ("3c", "Ac") and s.result["reason"] in ("street_end", "showdown")
            return
    pytest.fail("no hand reached the turn in 300 tries")


def test_attempt_hook_gets_the_graded_decision(view):
    seen = []
    s = HandSession("t", "sid", view, "oop", random.Random(1), on_attempt=seen.append)
    action = s.state()["actions"][0]["action"]
    out = s.act(action)
    assert len(seen) == 1 and seen[0] is out["feedback"]
    fb = seen[0]
    assert fb["solve_id"] == "sid" and fb["street"] == "flop" and fb["path"] == [] and fb["hero_role"] == "oop"
    assert fb["combo"] == s.hero_combo and fb["chosen"] == action
    kk = fb["combo"][0] == "K"                           # KK: [0.2, 0.8] ; AQs: [0.9, 0.1]
    assert math.isclose(fb["freq"], (0.2 if kk else 0.9) if action == "CHECK" else (0.8 if kk else 0.1))
    assert "solver plays" in fb["explanation"]


def test_state_hides_the_opponents_hand_until_the_end(view):
    s = HandSession("t", "sid", view, "oop", random.Random(2))
    st = s.state()
    assert "villain_combo" not in st and s.villain_combo not in str(st)
    assert st["hero_hand"] and st["pot"] == 50 and st["to_call"] == 0


def test_drill_at_a_specific_node(view):
    s = HandSession("t", "sid", view, "ip", random.Random(5), start_path=[B25], single=True)
    st = s.state()
    assert st["pot"] == 75 and st["to_call"] == 25 and [a["action"] for a in st["actions"]] == ["FOLD", C, R85]
    out = s.act(C)
    assert out["state"]["finished"] and out["state"]["result"]["reason"] == "drill"
    assert out["feedback"]["path"] == [B25]


def test_drill_rejects_wrong_player_or_non_action_node(view):
    with pytest.raises(ValueError):
        HandSession("t", "sid", view, "oop", random.Random(0), start_path=[B25], single=True)  # IP acts there
    with pytest.raises(ValueError):
        HandSession("t", "sid", view, "oop", random.Random(0), start_path=[B25, C])            # chance node


def test_cannot_act_after_the_hand_or_with_illegal_action(view):
    s = HandSession("t", "sid", view, "oop", random.Random(1))
    with pytest.raises(ValueError):
        s.act("FOLD")
    s2 = play_randomly(view, "oop", 3)
    with pytest.raises(ValueError):
        s2.act("CHECK")


def test_villain_actions_follow_the_solver_distribution(view):
    """OOP hero checks; IP villain (AA: 50/50, QQ: always bets) must act accordingly."""
    bets = Counter()
    for seed in range(400):
        s = HandSession("t", "sid", view, "oop", random.Random(seed))
        s.act("CHECK")
        if not s.finished or s.result["reason"] != "street_end":
            bets[(s.villain_combo[0], "bet" if (not s.finished or s.result["reason"] != "street_end") else "check")] += 1
    qq_bets = sum(v for (r, a), v in bets.items() if r == "Q" and a == "bet")
    qq_total = sum(v for (r, _), v in bets.items() if r == "Q")
    assert qq_total > 20 and qq_bets == qq_total          # QQ never checks back in this tree


# ---------------------------------------------------------------- questions ----
def test_autoplay_points_are_valid_decisions(view):
    s = HandSession("t", "sid", view, "ip", random.Random(11))
    pts = s.autoplay_decisions()
    assert pts and all(p["role"] == "ip" for p in pts)
    for p in pts:
        assert view.combo_strategy(p["path"], p["combo"]) is not None


def test_generate_question_is_deterministic_and_valid(view):
    a = generate_question(view, random.Random(42))
    b = generate_question(view, random.Random(42))
    assert a == b
    assert view.combo_strategy(a["path"], a["combo"]) is not None
