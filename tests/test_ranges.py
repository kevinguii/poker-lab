import pytest

from pokerlab.ranges import (
    all_classes, canon_combo, class_combos, expand_range, grid_class, hand_class, parse_range,
)


def test_combo_counts():
    assert len(class_combos("AA")) == 6
    assert len(class_combos("AKs")) == 4
    assert len(class_combos("AKo")) == 12


def test_all_classes_is_169_unique():
    classes = all_classes()
    assert len(classes) == 169 and len(set(classes)) == 169


def test_grid_layout_pairs_diagonal_suited_above():
    assert grid_class(0, 0) == "AA"
    assert grid_class(0, 1) == "AKs"  # upper right = suited
    assert grid_class(1, 0) == "AKo"  # lower left = offsuit
    assert grid_class(12, 12) == "22"


def test_hand_class_and_canon_are_order_independent():
    assert hand_class("KdAs") == hand_class("AsKd") == "AKo"
    assert hand_class("2d2c") == "22"
    assert hand_class("9h8h") == "98s"
    assert canon_combo("KdAs") == canon_combo("AsKd") == "AsKd"


def test_parse_range_weights_and_expansion():
    r = parse_range("AA,KK:0.5,AKs,AQo:0.75,KQ")
    assert r["AA"] == 1.0 and r["KK"] == 0.5
    assert r["AKs"] == 1.0 and "AKo" not in r
    assert r["AQo"] == 0.75
    assert r["KQs"] == 1.0 and r["KQo"] == 1.0  # no suffix = both


def test_parse_range_normalises_rank_order():
    assert parse_range("KAs") == {"AKs": 1.0}


@pytest.mark.parametrize("bad", ["", "AA+", "AAs", "XYs", "AK:2", "AK:0", "A"])
def test_parse_range_rejects_bad_tokens(bad):
    with pytest.raises(ValueError):
        parse_range(bad)


def test_expand_removes_dead_cards():
    combos = expand_range({"QQ": 1.0, "AQs": 0.5}, dead={"Qs"})
    assert len([c for c in combos if hand_class(c) == "QQ"]) == 3  # QQ minus Qs combos
    assert len([c for c in combos if hand_class(c) == "AQs"]) == 3
    assert all(w in (1.0, 0.5) for w in combos.values())
    assert not any("Qs" in (c[:2], c[2:]) for c in combos)
