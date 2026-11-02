import pytest

from pokerlab.handhistory import ParseError, money, parse_hand, parse_text, split_hands

import hh_samples as hh


def test_money_handles_symbols_and_commas():
    assert money("$1,250.50") == 1250.5 and money("€0.25") == 0.25 and money("1500") == 1500


def test_parse_basic_cash_hand():
    h = parse_hand(hh.HAND_A)
    assert h["id"] == "900000001" and h["sb"] == 0.5 and h["bb"] == 1.0
    assert h["time"] == "2026/10/20 21:14:05" and h["button"] == 1
    assert h["hero"] == "Hero" and h["hero_cards"] == ["Ah", "Ad"]
    assert h["board"] == {"flop": ["Qs", "Jh", "2h"], "turn": "3c", "river": None}
    assert [(s["seat"], s["name"], s["stack"]) for s in h["seats"]] == [(1, "Hero", 22.5), (2, "Vil", 22.5)]
    kinds = [(a["street"], a["player"], a["kind"]) for a in h["actions"]]
    assert kinds[:2] == [("preflop", "Hero", "posts"), ("preflop", "Vil", "posts")]
    assert ("preflop", "Hero", "raises") in kinds and ("flop", "Vil", "bets") in kinds and ("turn", "Vil", "folds") in kinds
    raise_ = next(a for a in h["actions"] if a["kind"] == "raises")
    assert raise_["amount"] == 1.5 and raise_["to"] == 2.5
    assert any(a["kind"] == "uncalled" and a["player"] == "Hero" and a["amount"] == 5 for a in h["actions"])


def test_showdown_and_summary_are_not_parsed_as_actions():
    h = parse_hand(hh.HAND_A)
    assert all(a["player"] != "Total pot $10 | Rake $0" for a in h["actions"])
    assert "collected" not in " ".join(a["kind"] for a in h["actions"])


def test_tournament_header_and_all_in_flags():
    text = """PokerStars Hand #77:  Tournament #5, $10+$1 USD Hold'em No Limit - Level I (10/20) - 2026/10/20 21:14:05 ET
Table '5 1' 9-max Seat #1 is the button
Seat 1: A (1500 in chips)
Seat 2: B (1500 in chips)
B: posts small blind 10
A: posts big blind 20
*** HOLE CARDS ***
Dealt to A [As Ks]
B: raises 1480 to 1500 and is all-in
A: calls 1480 and is all-in
*** SUMMARY ***
"""
    h = parse_hand(text)
    assert (h["sb"], h["bb"]) == (10, 20)
    r = next(a for a in h["actions"] if a["kind"] == "raises")
    assert r["allin"] and r["to"] == 1500
    assert next(a for a in h["actions"] if a["kind"] == "calls")["allin"]


def test_parse_text_multiple_hands_and_bad_chunks():
    bad = "PokerStars Hand #5:  Hold'em No Limit - nothing useful here\nTable 'x'\n"
    hands, errors = parse_text(hh.HAND_A + "\n\n" + bad + "\n" + hh.HAND_MULTIWAY)
    assert [h["id"] for h in hands] == ["900000001", "900000002"]
    assert len(errors) == 1 and "#5" in errors[0]


def test_parse_text_rejects_other_formats():
    hands, errors = parse_text("This is not a hand history at all")
    assert hands == [] and "PokerStars" in errors[0]


def test_split_hands_handles_windows_line_endings():
    assert len(split_hands((hh.HAND_A + "\n" + hh.HAND_B).replace("\n", "\r\n"))) == 2


def test_parse_hand_requires_basics():
    with pytest.raises(ParseError):
        parse_hand("Hello")
