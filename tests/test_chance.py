"""Street-crossing behaviour of SolveView, on the hand-built tree in tests/trees.py."""

import math

import pytest

from pokerlab.ranges import hand_class
from pokerlab.strategy import PathError, SolveView

import trees

B25, C, R85 = "BET 25.000000", "CALL", "RAISE 85.000000"


@pytest.fixture()
def view():
    return SolveView(trees.build(), trees.spot())


def test_chance_node_lists_legal_deals_without_dead_cards(view):
    d = view.describe([B25, C])
    assert d["node_type"] == "chance_node" and d["deals"] == ["3c", "Ac"]
    assert view.legal_deals([B25, C], exclude={"3c"}) == ["Ac"]   # trainer excludes the players' cards


def test_chance_without_next_street_says_so(view):
    d = view.describe(["CHECK", "CHECK"])
    assert d["node_type"] == "chance_node" and d["deals"] == [] and "not part of this solve" in d["note"]


def test_walking_through_a_deal(view):
    d = view.describe([B25, C, "@3c"])
    assert d["node_type"] == "action_node" and d["actor"] == "oop"
    assert d["context"]["board"] == ["Qs", "Jh", "2h", "3c"] and d["context"]["street"] == "turn"


def test_deal_errors(view):
    with pytest.raises(PathError):
        view.walk([B25, C, "@Qs"])        # on the board already
    with pytest.raises(PathError):
        view.walk([B25, C, "@9d"])        # not in this tree
    with pytest.raises(PathError):
        view.walk([B25, "@3c"])           # not a chance node
    with pytest.raises(PathError):
        view.walk(["CHECK", "CHECK", "@3c"])  # no next street in the dump


def test_dealt_card_removes_blocked_combos_from_reach(view):
    reach = view.reach([B25, C, "@Ac"])
    assert not any("Ac" in (c[:2], c[2:]) for r in reach.values() for c in r)
    aa = [c for c in reach["ip"] if hand_class(c) == "AA"]
    assert len(aa) == 3                                   # AA minus the three combos holding Ac
    assert len([c for c in reach["oop"] if hand_class(c) == "AQs"]) == 2


def test_reach_applies_each_players_own_choices(view):
    r = view.reach([B25, C, "@3c"])
    kk = next(c for c in r["oop"] if hand_class(c) == "KK")
    aq = next(c for c in r["oop"] if hand_class(c) == "AQs")
    assert math.isclose(r["oop"][kk], 0.8) and math.isclose(r["oop"][aq], 0.1)   # P(bet) at the root
    aa = next(c for c in r["ip"] if hand_class(c) == "AA")
    qq = next(c for c in r["ip"] if hand_class(c) == "QQ")
    assert math.isclose(r["ip"][aa], 0.5) and math.isclose(r["ip"][qq], 0.9)     # P(call) facing the bet


def test_context_pot_and_stacks_across_streets(view):
    ctx = view.context([B25])
    assert ctx["pot"] == 75 and ctx["to_call"] == 25 and ctx["stacks"] == {"oop": 175, "ip": 200}
    ctx = view.context([B25, C])                          # at the chance node: bets still on the table
    assert ctx["pot"] == 100 and "to_call" not in ctx
    ctx = view.context([B25, C, "@3c"])
    assert ctx["pot"] == 100 and ctx["stacks"] == {"oop": 175, "ip": 175} and ctx["to_call"] == 0
    assert ctx["committed"] == {"oop": 0, "ip": 0} and ctx["committed_total"] == {"oop": 25, "ip": 25}
    ctx = view.context([B25, C, "@3c", "CHECK"])
    assert ctx["pot"] == 100 and ctx["history"][-1]["actor"] == "oop"


def test_raise_amounts_are_totals_for_the_street(view):
    ctx = view.context([B25, R85])
    # starting pot 50 + OOP's 25 + IP's raise to 85
    assert ctx["pot"] == 160 and ctx["to_call"] == 60 and ctx["committed"] == {"oop": 25, "ip": 85}


def test_final_action_that_ends_the_hand(view):
    ctx = view.context([B25], final="FOLD")
    assert ctx["pot"] == 75 and ctx["committed_total"] == {"oop": 25, "ip": 0}
    ctx = view.context([B25, R85], final="CALL")          # OOP calls the raise
    assert ctx["pot"] == 220 and ctx["committed_total"] == {"oop": 85, "ip": 85}   # 50 + 85 + 85


def test_combo_strategy_lookup_and_hand_name(view):
    actions, freqs = view.combo_strategy([], "KhKd")
    assert actions == ["CHECK", B25] and freqs == [0.2, 0.8]
    assert view.combo_strategy([], "7c7d") is None
    assert view.hand_name("KhKd", ["Qs", "Jh", "2h"]) == "Pair of Kings"
    assert view.hand_name("KhKd", []) is None


def test_existing_viewer_payloads_still_work_across_a_deal(view):
    d = view.describe([B25, C, "@Ac"])
    assert set(d["grid"]) == {"KK", "AQs"} and d["grid"]["AQs"]["combos"] == 2
    assert math.isclose(sum(d["overall"]), 1.0)
    assert len(view.combos([B25, C, "@Ac"], "AQs")["combos"]) == 2
