import math

import pytest

from pokerlab.analysis import evaluate, positions, pot_type, prepare, replay
from pokerlab.cache import SolveStore
from pokerlab.handhistory import parse_hand
from pokerlab.progress import ProgressStore
from pokerlab.spot import Spot
from pokerlab.strategy import SolveView

import hh_samples as hh
import trees


@pytest.fixture()
def progress(tmp_path):
    p = ProgressStore(*SolveStore(tmp_path).shared())
    # tiny ranges that match tests/trees.py (the built-in sample preset has huge ones)
    p.save_preset("tiny-srp", "srp", ip_range="AA,QQ", oop_range="KK,AQs")
    return p


def info_for(text, progress):
    hand = parse_hand(text)
    return hand, prepare(hand, progress)


# ------------------------------------------------------------------- replay ----
def test_replay_pot_and_stacks_in_big_blinds():
    rp = replay(parse_hand(hh.HAND_A))
    assert rp["flop"]["start_pot"] == 5.0 and rp["flop"]["active"] == ["Hero", "Vil"]
    assert rp["flop"]["start_stacks"] == {"Hero": 20.0, "Vil": 20.0}
    assert [(a["player"], a["kind"], a["to"]) for a in rp["flop"]["actions"]] == [("Vil", "bets", 2.5), ("Hero", "calls", 2.5)]
    assert rp["turn"]["start_pot"] == 10.0 and rp["turn"]["start_stacks"] == {"Hero": 17.5, "Vil": 17.5}
    bet = rp["turn"]["actions"][1]
    assert bet["kind"] == "bets" and bet["to"] == 5.0 and bet["pot_before"] == 10.0


def test_uncalled_bets_do_not_inflate_the_pot():
    rp = replay(parse_hand(hh.HAND_A))
    assert "river" not in rp
    # the returned $5 must not count as committed: only used when a later street starts
    hand = parse_hand(hh.HAND_A)
    hand["actions"].append({"street": "river", "player": "Hero", "kind": "checks", "amount": None, "to": None})
    assert replay(hand)["river"]["start_pot"] == 10.0


def test_positions_follow_the_button():
    hand = parse_hand(hh.HAND_A)
    assert positions(hand, "Hero", "Vil") == {"Vil": "oop", "Hero": "ip"}      # button is last to act
    six = parse_hand(hh.HAND_MULTIWAY)                                       # button seat 3
    assert positions(six, "Alice", "Bob")["Bob"] == "ip" and positions(six, "Hero", "Bob")["Bob"] == "ip"
    assert positions(six, "Alice", "Hero")["Hero"] == "ip"                   # after the button: seat 1 before seat 2


@pytest.mark.parametrize("text,expected", [(hh.HAND_A, "srp"), (hh.HAND_3BET, "3bp"),
                                           (hh.HAND_MULTIWAY, "srp"), (hh.HAND_PREFLOP_ONLY, "limp")])
def test_pot_type(text, expected):
    assert pot_type(parse_hand(text)) == expected


# ------------------------------------------------------------------ prepare ----
def test_prepare_builds_the_expected_spot(progress):
    hand, info = info_for(hh.HAND_A, progress)
    assert info["eligible"] and info["hero_role"] == "ip" and info["preset"] == "tiny-srp"
    spot = Spot.from_dict(info["spot"])
    assert spot.board == "Qs,Jh,2h" and spot.pot == 50 and spot.effective_stack == 200
    assert spot.dump_rounds == 2 and spot.ip_range == "AA,QQ"
    assert spot.bet_sizes["oop"]["flop"]["bet"] == [50]      # 2.5bb into 5bb already exists: nothing added
    assert info["spot_id"] == spot.spot_id()


@pytest.mark.parametrize("text,fragment", [
    (hh.HAND_MULTIWAY, "3 players"),
    (hh.HAND_3BET, "no preset for 3bp"),
    (hh.HAND_PREFLOP_ONLY, "never reached the flop"),
])
def test_prepare_explains_why_a_hand_is_not_analysable(text, fragment, progress):
    _, info = info_for(text, progress)
    assert not info["eligible"] and fragment in info["reason"] and info["spot"] is None


def test_prepare_needs_hero_cards(progress):
    hand = parse_hand(hh.HAND_A)
    hand["hero_cards"] = None
    assert "cards" in prepare(hand, progress)["reason"]


def test_actual_bet_sizes_are_added_to_the_tree(progress):
    text = hh.HAND_A.replace("Vil: bets $2.50", "Vil: bets $3.50").replace("Hero: calls $2.50", "Hero: calls $3.50")
    _, info = info_for(text, progress)
    spot = Spot.from_dict(info["spot"])
    assert 70 in spot.bet_sizes["oop"]["flop"]["bet"] and 50 in spot.bet_sizes["oop"]["flop"]["bet"]


def test_raise_size_uses_the_solvers_definition(progress):
    # bet 2.5, raise to 8.5 => (8.5 - 2.5) / (7.5 + 2.5) = 60% which already exists
    _, info = info_for(hh.HAND_B, progress)
    assert Spot.from_dict(info["spot"]).bet_sizes["ip"]["flop"]["raise"] == [60]


# ----------------------------------------------------------------- evaluate ----
def run(text, progress):
    hand, info = info_for(text, progress)
    assert info["eligible"], info["reason"]
    view = SolveView(trees.build(), Spot.from_dict(info["spot"]))
    return evaluate(view, hand, info)


def test_flop_call_and_turn_bet_are_graded_against_the_tree(progress):
    ev = run(hh.HAND_A, progress)
    flop, turn = ev["decisions"]
    assert (flop["street"], flop["status"], flop["matched"]) == ("flop", "graded", "CALL")
    fb = flop["feedback"]
    assert math.isclose(fb["freq"], 0.5) and fb["verdict"] == "correct"
    assert (turn["street"], turn["status"], turn["matched"]) == ("turn", "graded", "BET 50.000000")
    assert math.isclose(turn["feedback"]["freq"], 0.5)
    assert ev["summary"]["graded"] == 2 and ev["summary"]["mistakes"] == 0 and ev["summary"]["avg_score"] == 1.0


def test_raise_is_matched_to_the_nearest_tree_size(progress):
    ev = run(hh.HAND_B, progress)
    (d,) = ev["decisions"]
    assert d["matched"] == "RAISE 85.000000" and math.isclose(d["feedback"]["freq"], 0.5)


def test_a_zero_frequency_action_is_a_mistake(progress):
    text = hh.HAND_A.replace(
        "Hero: calls $2.50\n*** TURN *** [Qs Jh 2h] [3c]\nVil: checks\nHero: bets $5\nVil: folds\nUncalled bet ($5) returned to Hero\nHero collected $10 from pot",
        "Hero: folds\nUncalled bet ($2.50) returned to Vil\nVil collected $5 from pot")
    ev = run(text, progress)
    (d,) = ev["decisions"]
    assert d["matched"] == "FOLD" and d["feedback"]["verdict"] == "mistake" and d["feedback"]["score"] == 0.0
    assert ev["summary"]["mistakes"] == 1


def test_hand_outside_the_preset_range_is_reported_not_graded(progress):
    ev = run(hh.HAND_A.replace("Dealt to Hero [Ah Ad]", "Dealt to Hero [7c 2d]"), progress)
    assert [d["status"] for d in ev["decisions"]] == ["out_of_range", "out_of_range"]
    assert ev["summary"]["graded"] == 0 and ev["summary"]["avg_score"] is None


def test_turn_card_missing_from_the_solve_stops_grading_cleanly(progress):
    text = hh.HAND_A.replace("[3c]", "[9d]")
    ev = run(text, progress)
    flop, turn = ev["decisions"]
    assert flop["status"] == "graded" and turn["status"] == "not_in_solve" and "not part of the solve" in turn["note"]


def test_river_decisions_are_listed_but_never_graded(progress):
    text = hh.HAND_A.replace(
        "Hero: bets $5\nVil: folds\nUncalled bet ($5) returned to Hero\nHero collected $10 from pot",
        "Hero: checks\n*** RIVER *** [Qs Jh 2h 3c] [9d]\nVil: bets $5\nHero: calls $5")
    ev = run(text, progress)
    assert [d["street"] for d in ev["decisions"]] == ["flop", "turn", "river"]
    assert ev["decisions"][2]["status"] == "river_not_covered" and ev["decisions"][2]["feedback"] is None
    assert ev["decisions"][1]["status"] == "graded"        # the turn check is still graded


def test_an_action_the_tree_cannot_represent_diverges_without_crashing(progress):
    # a 100bb-sized flop bet is far from every size in the tree
    text = hh.HAND_A.replace("Vil: bets $2.50", "Vil: bets $9").replace("Hero: calls $2.50", "Hero: calls $9")
    hand, info = info_for(text, progress)
    # use the *original* tree (which lacks that size) with the new hand
    view = SolveView(trees.build(), Spot.from_dict(info["spot"]))
    ev = evaluate(view, hand, info)
    assert all(d["status"] == "not_in_solve" for d in ev["decisions"]) and ev["decisions"]
