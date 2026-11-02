"""Small 5-7 card Texas hold'em hand evaluator (best 5 of up to 7 cards).

Ranks are comparable tuples ``(category, tiebreakers)`` where a bigger tuple wins.
Used for showdown results in the trainer; speed is not a concern (<= 21 subsets).
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations

_VAL = {r: 14 - i for i, r in enumerate("AKQJT98765432")}
_NAME = {14: "Ace", 13: "King", 12: "Queen", 11: "Jack", 10: "Ten", 9: "Nine", 8: "Eight",
         7: "Seven", 6: "Six", 5: "Five", 4: "Four", 3: "Three", 2: "Two"}
_PLURAL = {**{v: n + "s" for v, n in _NAME.items()}, 6: "Sixes"}
CATEGORIES = ["High card", "Pair", "Two pair", "Three of a kind", "Straight", "Flush",
              "Full house", "Four of a kind", "Straight flush"]

Rank = tuple[int, tuple[int, ...]]


def rank5(cards: list[str] | tuple[str, ...]) -> Rank:
    vals = sorted((_VAL[c[0]] for c in cards), reverse=True)
    flush = len({c[1] for c in cards}) == 1
    uniq = sorted(set(vals), reverse=True)
    straight = None
    if len(uniq) == 5:
        if uniq[0] - uniq[4] == 4:
            straight = uniq[0]
        elif uniq == [14, 5, 4, 3, 2]:  # the wheel
            straight = 5
    counts = Counter(vals)
    groups = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    shape = [c for _, c in groups]
    ordered = tuple(v for v, _ in groups)
    if straight and flush:
        return (8, (straight,))
    if shape == [4, 1]:
        return (7, ordered)
    if shape == [3, 2]:
        return (6, ordered)
    if flush:
        return (5, tuple(vals))
    if straight:
        return (4, (straight,))
    if shape == [3, 1, 1]:
        return (3, ordered)
    if shape == [2, 2, 1]:
        return (2, ordered)
    if shape == [2, 1, 1, 1]:
        return (1, ordered)
    return (0, tuple(vals))


def best_hand(cards: list[str]) -> Rank:
    if not 5 <= len(cards) <= 7:
        raise ValueError("need 5 to 7 cards")
    return max(rank5(c) for c in combinations(cards, 5))


def describe(rank: Rank) -> str:
    cat, t = rank
    if cat == 0:
        return f"{_NAME[t[0]]} high"
    if cat == 1:
        return f"Pair of {_PLURAL[t[0]]}"
    if cat == 2:
        return f"Two pair, {_PLURAL[t[0]]} and {_PLURAL[t[1]]}"
    if cat == 3:
        return f"Three of a kind, {_PLURAL[t[0]]}"
    if cat == 4:
        return f"Straight, {_NAME[t[0]]} high"
    if cat == 5:
        return f"Flush, {_NAME[t[0]]} high"
    if cat == 6:
        return f"Full house, {_PLURAL[t[0]]} full of {_PLURAL[t[1]]}"
    if cat == 7:
        return f"Four of a kind, {_PLURAL[t[0]]}"
    return "Royal flush" if t[0] == 14 else f"Straight flush, {_NAME[t[0]]} high"


def showdown(hero: list[str], villain: list[str], board: list[str]) -> int:
    """1 if hero wins, -1 if villain wins, 0 for a split pot."""
    h, v = best_hand(hero + board), best_hand(villain + board)
    return (h > v) - (h < v)
