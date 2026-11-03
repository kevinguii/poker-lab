"""Expected value of every action at a node of a solved tree.

TexasSolver's dump has strategies only, so EV is rebuilt by walking the subtree below a node once, for one
player (the *target*), against the opponent's reach at that node:

    V(h) = sum over opponent hands o and runouts of  reach(o) * payoff(h, o)      (unnormalised)
    M(h) = sum over the same terms of                reach(o)                      (the mass V is summed over)
    EV(h) = V(h) / M(h)

Dividing by M makes the result a proper conditional expectation, so card blocking and chance nodes need no
bookkeeping about how many cards are left. Both players follow the solved strategy below the node.

Payoffs are chips won from the *start of the tree*, with the spot's pot treated as dead money: winning pays
``pot + opponent's commitment``, losing costs your own commitment. Only differences between actions at one node are
meaningful, and those do not depend on the earlier commitments.

Chance nodes (and runouts) are averaged uniformly over the cards that fit each pair of hands, then rescaled to the plain
opponent mass so that every branch of a node is weighted the same way.

Exactness: showdowns on a complete board and fold endings are exact. Where the solve stopped before a street
(a chance node without ``dealcards`` and not all-in) the remaining cards are enumerated (one card) or sampled (two
cards) and the players are assumed to check it down, so the result is flagged ``exact=False``. An all-in runout is exact. Subtrees larger than a work budget are
not evaluated at all (``None``), so callers fall back to frequency grading.
"""

from __future__ import annotations

import random
from bisect import bisect_left, bisect_right
from itertools import accumulate

from .evaluator import fast_rank
from .strategy import _combo_strategies, has_card, parse_action

DECK = [r + s for r in "AKQJT98765432" for s in "cdhs"]
RUNOUT_SAMPLES = 8                 # runouts sampled when two cards are missing
DEFAULT_MAX_WORK = 12_000_000      # rough count of per-combo operations; ~seconds in CPython


class EvBudgetExceeded(Exception):
    pass


class _Walker:
    def __init__(self, view, target: str, max_work: int):
        self.view = view
        self.target = target
        self.opp = "ip" if target == "oop" else "oop"
        self.base = float(view.spot.pot)
        self.stack = float(view.spot.effective_stack)
        self.exact = True
        self.work = 0
        self.max_work = max_work
        self._ranks: dict[tuple[str, ...], dict[str, int]] = {}
        self._rng = random.Random(0)

    # ---- bookkeeping ------------------------------------------------------------
    def _spend(self, n: int) -> None:
        self.work += n
        if self.work > self.max_work:
            raise EvBudgetExceeded

    def _board_ranks(self, board: tuple[str, ...], combos) -> dict[str, int]:
        known = self._ranks.setdefault(board, {})
        fresh = [c for c in combos if c not in known]
        if fresh:
            self._spend(6 * len(fresh))
            for c in fresh:
                known[c] = fast_rank((c[:2], c[2:]) + board)
        return known

    @staticmethod
    def _commit(street: dict[str, float], who: str, step: str) -> dict[str, float]:
        out = dict(street)
        opp = "ip" if who == "oop" else "oop"
        kind, amt = parse_action(step)
        if kind == "CALL":
            out[who] = out[opp]
        elif kind in ("BET", "RAISE", "DONK"):
            out[who] = amt or 0.0
        return out

    # ---- terminals ------------------------------------------------------------
    @staticmethod
    def _masses(opp_w: dict[str, float], hero: list[str]) -> dict[str, float]:
        """Opponent weight that does not share a card with each hero combo."""
        card_mass: dict[str, float] = {}
        total = 0.0
        for o, w in opp_w.items():
            total += w
            card_mass[o[:2]] = card_mass.get(o[:2], 0.0) + w
            card_mass[o[2:]] = card_mass.get(o[2:], 0.0) + w
        return {h: total - card_mass.get(h[:2], 0.0) - card_mass.get(h[2:], 0.0) + opp_w.get(h, 0.0) for h in hero}

    def _rescaled(self, v: dict[str, float], m: dict[str, float], opp_w: dict[str, float], hero: list[str]):
        """Turn sums over several runouts into one conditional expectation weighted by the plain opponent mass.

        This keeps every branch of a node on the same footing, whatever number of cards each one dealt."""
        mass = self._masses(opp_w, hero)
        return ({h: v[h] * mass[h] / m[h] for h in v if m.get(h, 0.0) > 1e-12},
                {h: mass[h] for h in v if m.get(h, 0.0) > 1e-12})

    def _fold(self, folder: str, put: dict[str, float], opp_w: dict[str, float], hero: list[str]):
        value = -put[self.target] if folder == self.target else self.base + put[self.opp]
        mass = self._masses(opp_w, hero)
        return {h: value * m for h, m in mass.items()}, mass

    def _showdown(self, board: tuple[str, ...], put: dict[str, float], opp_w: dict[str, float], hero: list[str]):
        ranks = self._board_ranks(board, list(opp_w) + hero)
        self._spend(len(opp_w) + len(hero))
        opp = sorted((ranks[o], w, o) for o, w in opp_w.items() if w > 0)
        keys = [r for r, _, _ in opp]
        pref = [0.0, *accumulate(w for _, w, _ in opp)]
        total = pref[-1]
        per_card: dict[str, tuple[list[int], list[float]]] = {}
        grouped: dict[str, list[tuple[int, float]]] = {}
        for r, w, o in opp:
            grouped.setdefault(o[:2], []).append((r, w))
            grouped.setdefault(o[2:], []).append((r, w))
        for card, rows in grouped.items():
            per_card[card] = ([r for r, _ in rows], [0.0, *accumulate(w for _, w in rows)])

        t, o_ = self.target, self.opp
        won, lost = self.base + put[o_], put[t]
        tied = (self.base + put[o_] - put[t]) / 2
        v: dict[str, float] = {}
        m: dict[str, float] = {}
        for h in hero:
            r = ranks[h]
            lt, le, compat = pref[bisect_left(keys, r)], pref[bisect_right(keys, r)], total
            for card in (h[:2], h[2:]):
                pc = per_card.get(card)
                if pc:
                    ck, cp = pc
                    lt -= cp[bisect_left(ck, r)]
                    le -= cp[bisect_right(ck, r)]
                    compat -= cp[-1]
            same = opp_w.get(h, 0.0)  # the identical combo was subtracted twice and ties itself
            le += same
            compat += same
            win, tie, lose = lt, le - lt, compat - le
            v[h] = won * win - lost * lose + tied * tie
            m[h] = compat
        return v, m

    def _runout(self, board: tuple[str, ...], put, opp_w, hero, truncated: bool):
        missing = 5 - len(board)
        if missing == 0:
            return self._showdown(board, put, opp_w, hero)
        if truncated:
            self.exact = False  # the players are assumed to check the rest down
        left = [c for c in DECK if c not in board]
        if missing == 1:
            runouts = [(c,) for c in left]
        else:
            self.exact = False
            runouts = [tuple(self._rng.sample(left, missing)) for _ in range(RUNOUT_SAMPLES)]
        v: dict[str, float] = {}
        m: dict[str, float] = {}
        for extra in runouts:
            b = board + extra
            h2 = [h for h in hero if not any(has_card(h, c) for c in extra)]
            o2 = {o: w for o, w in opp_w.items() if not any(has_card(o, c) for c in extra)}
            dv, dm = self._showdown(b, put, o2, h2)
            for h in dv:
                v[h] = v.get(h, 0.0) + dv[h]
                m[h] = m.get(h, 0.0) + dm[h]
        return self._rescaled(v, m, opp_w, hero)

    # ---- recursion ------------------------------------------------------------
    def edge(self, node, action, board, prior, street, opp_w, hero):
        """(V, M) after ``action`` is taken at action node ``node``."""
        who = self.view.actor(node)
        street = self._commit(street, who, action)
        child = node.get("childrens", {}).get(action)
        if child is not None:
            return self.visit(child, board, prior, street, opp_w, hero)
        put = {p: prior[p] + street[p] for p in prior}
        if parse_action(action)[0] == "FOLD":
            return self._fold(who, put, opp_w, hero)
        return self._runout(board, put, opp_w, hero, truncated=False)

    def visit(self, node, board, prior, street, opp_w, hero):
        self._spend(len(opp_w) + len(hero))
        kind = node.get("node_type")
        if kind == "chance_node":
            put = {p: prior[p] + street[p] for p in prior}
            deals = node.get("dealcards")
            if not deals:
                # Both all-in: nothing more can happen, so enumerating the runout is exact. Otherwise the solve
                # simply stopped here and the players are assumed to check the rest down.
                all_in = min(put.values()) >= self.stack - 1e-9
                return self._runout(board, put, opp_w, hero, truncated=not all_in)
            v: dict[str, float] = {}
            m: dict[str, float] = {}
            for card, child in deals.items():
                if card in board:
                    continue
                h2 = [h for h in hero if not has_card(h, card)]
                o2 = {o: w for o, w in opp_w.items() if not has_card(o, card)}
                dv, dm = self.visit(child, board + (card,), put, {"oop": 0.0, "ip": 0.0}, o2, h2)
                for h in dv:
                    v[h] = v.get(h, 0.0) + dv[h]
                    m[h] = m.get(h, 0.0) + dm[h]
            return self._rescaled(v, m, opp_w, hero)
        if kind != "action_node":
            raise ValueError(f"unexpected node type {kind!r}")

        who = self.view.actor(node)
        strat = _combo_strategies(node)
        v = {h: 0.0 for h in hero}
        m = {h: 0.0 for h in hero}
        for i, action in enumerate(node["actions"]):
            if who == self.target:
                dv, dm = self.edge(node, action, board, prior, street, opp_w, hero)
                for h in dv:
                    p = strat[h][i] if h in strat else 0.0
                    if p:
                        v[h] += p * dv[h]
                        m[h] = dm[h]  # identical for every action: the opponent's mass does not depend on ours
            else:
                w2 = {o: w * strat[o][i] for o, w in opp_w.items() if o in strat and w * strat[o][i] > 0}
                if not w2:
                    continue
                dv, dm = self.edge(node, action, board, prior, street, w2, hero)
                for h in dv:
                    v[h] += dv[h]
                    m[h] += dm[h]
        return v, m


def node_evs(view, path: list[str], max_work: int = DEFAULT_MAX_WORK) -> dict | None:
    """EV of each action for every combo of the player to act at ``path``.

    Returns ``{"actions": [...], "ev": {combo: [ev per action, or None]}, "exact": bool}``, or ``None`` when the
    node is not an action node or the subtree is over the work budget.
    """
    node = view.walk(path)[-1]
    if node.get("node_type") != "action_node":
        return None
    who = view.actor(node)
    walker = _Walker(view, who, max_work)
    ctx = view.context(path)
    street = dict(ctx["committed"])
    prior = {p: ctx["committed_total"][p] - street[p] for p in street}
    board = tuple(ctx["board"])
    reach = view.reach(path)
    opp_w = {c: w for c, w in reach[walker.opp].items() if w > 0}
    hero = list(_combo_strategies(node))
    try:
        per_action = [
            walker.edge(node, a, board, prior, street, opp_w, hero) for a in node["actions"]
        ]
    except EvBudgetExceeded:
        return None
    ev: dict[str, list[float | None]] = {}
    for h in hero:
        row = []
        for v, m in per_action:
            row.append(v[h] / m[h] if h in m and m[h] > 1e-12 else None)
        ev[h] = row
    mass = per_action[0][1] if per_action else {}
    return {"actions": list(node["actions"]), "ev": ev, "mass": mass, "exact": walker.exact, "work": walker.work}
