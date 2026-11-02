import math

import pytest

from pokerlab.ranges import hand_class, parse_range
from pokerlab.strategy import PathError, SolveView


@pytest.fixture()
def view(river_tree, river_spot):
    return SolveView(river_tree, river_spot)


def test_root_is_oop_and_frequencies_normalise(view):
    d = view.describe([])
    assert d["actor"] == "oop"
    assert d["actions"][0] == "CHECK"
    assert math.isclose(sum(d["overall"]), 1.0, abs_tol=1e-6)
    for cls, cell in d["grid"].items():
        assert math.isclose(sum(cell["freqs"]), 1.0, abs_tol=1e-6), cls


def test_grid_only_contains_range_classes_with_dead_cards_removed(view, river_spot):
    d = view.describe([])
    oop_classes = set(parse_range(river_spot.oop_range))
    assert set(d["grid"]) <= oop_classes
    assert d["grid"]["QQ"]["combos"] == 3          # Qs is on the board
    assert d["grid"]["76s"]["combos"] == 3         # 7d is on the board
    assert d["grid"]["JJ"]["combos"] == 3          # Jh is on the board


def test_root_reach_equals_initial_range_weights(view):
    reach = view.reach([])
    assert all(w == 1.0 for w in reach["oop"].values())
    assert math.isclose(reach["ip"][next(c for c in reach["ip"] if hand_class(c) == "T9s")], 0.5)


def test_reach_shrinks_by_the_chosen_actions_probability(view):
    root = view.describe([])
    action = root["actions"][1]  # first bet
    r = view.reach([action])
    total_oop_after = sum(r["oop"].values())
    expected = sum(c["weight"] * c["freqs"][1] for c in root["grid"].values())
    assert math.isclose(total_oop_after, expected, rel_tol=1e-6)
    # IP did not act, so its range is untouched
    assert math.isclose(sum(r["ip"].values()), sum(view.reach([])["ip"].values()))


def test_navigation_alternates_players_and_flags_terminals(view):
    d = view.describe([])
    bet = next(a for a in d["actions"] if a.startswith("BET"))
    d2 = view.describe([bet])
    assert d2["actor"] == "ip"
    assert "FOLD" in d2["actions"]
    fold = next(c for c in d2["children"] if c["action"] == "FOLD")
    assert fold["terminal"] is True


def test_invalid_paths_raise(view):
    with pytest.raises(PathError):
        view.describe(["NOPE"])
    bet = next(a for a in view.describe([])["actions"] if a.startswith("BET"))
    with pytest.raises(PathError):
        view.describe([bet, "FOLD"])  # fold ends the hand


def test_combos_detail(view):
    c = view.combos([], "QQ")
    assert len(c["combos"]) == 3
    for row in c["combos"]:
        assert hand_class(row["combo"]) == "QQ"
        assert math.isclose(sum(row["freqs"]), 1.0, abs_tol=1e-6)
        assert row["reach"] == 1.0
