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


# ---- fast integer ranking (used by the EV engine, which ranks thousands of hands per board) ----
_SUIT = {"c": 0, "d": 1, "h": 2, "s": 3}


def _straight_high(mask: int) -> int:
    """Highest card of a straight in a rank bitmask (bit v set = rank value v present), or 0."""
    for hi in range(14, 5, -1):
        run = 0x1F << (hi - 4)
        if mask & run == run:
            return hi
    return 5 if mask & 0x403C == 0x403C else 0  # wheel: A,2,3,4,5


def _pack(cat: int, vals: tuple[int, ...]) -> int:
    out = cat
    for v in vals:
        out = (out << 4) | v
    return out << (4 * (5 - len(vals)))


def pack_rank(rank: Rank) -> int:
    """Integer form of a :func:`best_hand` rank; ``fast_rank(cards) == pack_rank(best_hand(cards))``."""
    return _pack(rank[0], rank[1])


def fast_rank(cards: list[str] | tuple[str, ...]) -> int:
    """Same ordering as :func:`best_hand`, as a single int, without enumerating 5-card subsets (5-7 cards)."""
    counts = [0] * 15
    suits = [0, 0, 0, 0]
    for c in cards:
        v = _VAL[c[0]]
        counts[v] += 1
        suits[_SUIT[c[1]]] |= 1 << v
    for m in suits:
        if m.bit_count() >= 5:  # with <= 7 cards a flush can never coexist with quads or a full house
            sf = _straight_high(m)
            if sf:
                return _pack(8, (sf,))
            top = [v for v in range(14, 1, -1) if m >> v & 1][:5]
            return _pack(5, tuple(top))
    quads, trips, pairs, singles = [], [], [], []
    mask = 0
    for v in range(14, 1, -1):
        n = counts[v]
        if n:
            mask |= 1 << v
            (quads if n == 4 else trips if n == 3 else pairs if n == 2 else singles).append(v)
    if quads:
        kicker = max(trips + pairs + singles) if (trips or pairs or singles) else 0
        return _pack(7, (quads[0], kicker))
    if trips and (len(trips) > 1 or pairs):
        second = max(trips[1:] + pairs)
        return _pack(6, (trips[0], second))
    st = _straight_high(mask)
    if st:
        return _pack(4, (st,))
    if trips:
        return _pack(3, (trips[0], *singles[:2]))
    if len(pairs) >= 2:
        kicker = max(pairs[2:] + singles) if (pairs[2:] or singles) else 0
        return _pack(2, (pairs[0], pairs[1], kicker))
    if pairs:
        return _pack(1, (pairs[0], *singles[:3]))
    return _pack(0, tuple(singles[:5]))
