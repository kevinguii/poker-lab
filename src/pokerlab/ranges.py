"""Poker range parsing and hand-class helpers.

Range syntax (same family the solver accepts):

    AA,KK:0.5,AKs,AQo:0.75,KQ

* ``AA``       a pair
* ``AKs``      suited, ``AKo`` offsuit, ``AK`` both
* ``:w``       optional weight in (0, 1]
"""

from __future__ import annotations

import re
from itertools import combinations

RANKS = "AKQJT98765432"
SUITS = "shdc"
_RANK_IDX = {r: i for i, r in enumerate(RANKS)}
_SUIT_IDX = {s: i for i, s in enumerate(SUITS)}
CARD_RE = re.compile(r"^[2-9TJQKA][shdc]$")
_TOKEN_RE = re.compile(r"^([2-9TJQKA])([2-9TJQKA])([so]?)(?::(\d*\.?\d+))?$")


def card_sort_key(card: str) -> tuple[int, int]:
    return (_RANK_IDX[card[0]], _SUIT_IDX[card[1]])


def canon_combo(combo: str) -> str:
    """Return a two-card combo like ``AsKd`` with cards in a stable order."""
    if len(combo) != 4:
        raise ValueError(f"bad combo: {combo!r}")
    a, b = combo[:2], combo[2:]
    if not (CARD_RE.match(a) and CARD_RE.match(b)) or a == b:
        raise ValueError(f"bad combo: {combo!r}")
    return "".join(sorted((a, b), key=card_sort_key))


def hand_class(combo: str) -> str:
    """Map a combo (``AsKd``) to its 169-grid class (``AKo``)."""
    a, b = sorted((combo[:2], combo[2:]), key=card_sort_key)
    if a[0] == b[0]:
        return a[0] + b[0]
    return a[0] + b[0] + ("s" if a[1] == b[1] else "o")


def grid_class(row: int, col: int) -> str:
    """Class shown in cell (row, col) of the 13x13 grid: pairs on the diagonal,
    suited above it, offsuit below it."""
    hi, lo = RANKS[min(row, col)], RANKS[max(row, col)]
    if row == col:
        return hi + lo
    return hi + lo + ("s" if row < col else "o")


def all_classes() -> list[str]:
    return [grid_class(r, c) for r in range(13) for c in range(13)]


def class_combos(cls: str) -> list[str]:
    """All 2-card combos belonging to a hand class."""
    r1, r2 = cls[0], cls[1]
    if r1 == r2:
        return [canon_combo(a + b) for a, b in combinations([r1 + s for s in SUITS], 2)]
    suffix = cls[2:] if len(cls) == 3 else ""
    out = []
    for s1 in SUITS:
        for s2 in SUITS:
            suited = s1 == s2
            if suffix == "s" and not suited:
                continue
            if suffix == "o" and suited:
                continue
            out.append(canon_combo(r1 + s1 + r2 + s2))
    return out


def parse_range(text: str) -> dict[str, float]:
    """Parse a range string into ``{hand_class: weight}``.

    ``KQ`` (no suffix) expands to both ``KQs`` and ``KQo``.
    """
    out: dict[str, float] = {}
    for raw in text.replace(" ", "").split(","):
        if not raw:
            continue
        m = _TOKEN_RE.match(raw)
        if not m:
            raise ValueError(f"unsupported range token: {raw!r}")
        r1, r2, kind, w = m.groups()
        weight = float(w) if w is not None else 1.0
        if not 0.0 < weight <= 1.0:
            raise ValueError(f"weight out of range in {raw!r}")
        if r1 == r2:
            if kind:
                raise ValueError(f"pairs cannot be suited/offsuit: {raw!r}")
            out[r1 + r2] = weight
            continue
        hi, lo = sorted((r1, r2), key=_RANK_IDX.__getitem__)
        for k in ([kind] if kind else ["s", "o"]):
            out[hi + lo + k] = weight
    if not out:
        raise ValueError("empty range")
    return out


def expand_range(class_weights: dict[str, float], dead: set[str] | frozenset[str] = frozenset()) -> dict[str, float]:
    """Expand class weights to ``{combo: weight}``, dropping combos that use dead cards."""
    out: dict[str, float] = {}
    for cls, w in class_weights.items():
        for combo in class_combos(cls):
            if combo[:2] in dead or combo[2:] in dead:
                continue
            out[combo] = w
    return out
