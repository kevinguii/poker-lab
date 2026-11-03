"""EV engine vs. an independent brute force that enumerates every hand pair and runout."""
import math

import pytest

from pokerlab.ev import DECK, node_evs
from pokerlab.evaluator import showdown
from pokerlab.strategy import SolveView, _combo_strategies, has_card, parse_action

import trees


def reference(view: SolveView, path: list[str], hero_combo: str):
    """Per-action EV for ``hero_combo`` at ``path`` by direct enumeration (nodes with <= 1 card still to come)."""
    node = view.walk(path)[-1]
    me = view.actor(node)
    opp = "ip" if me == "oop" else "oop"
    ctx = view.context(path)
    base = float(view.spot.pot)
    reach_o = view.reach(path)[opp]
    prior0 = {p: ctx["committed_total"][p] - ctx["committed"][p] for p in ("oop", "ip")}

    def after(n, a, board, prior, street, h, o):
        """Rows of (weight, payoff to me) once action ``a`` is taken at node ``n`` with both hands known."""
        who = view.actor(n)
        other = "ip" if who == "oop" else "oop"
        st = dict(street)
        kind, amt = parse_action(a)
        if kind == "CALL":
            st[who] = st[other]
        elif kind in ("BET", "RAISE"):
            st[who] = amt
        child = n.get("childrens", {}).get(a)
        if child is not None:
            return play(child, board, prior, st, h, o)
        put = {p: prior[p] + st[p] for p in prior}
        if kind == "FOLD":
            return [(1.0, -put[me] if who == me else base + put[opp])]
        assert len(board) >= 4, "reference supports at most one missing card"
        rest = [c for c in DECK if c not in board and not has_card(h, c) and not has_card(o, c)]
        tails = [[]] if len(board) == 5 else [[c] for c in rest]
        rows = []
        for tail in tails:
            r = showdown([h[:2], h[2:]], [o[:2], o[2:]], board + tail)
            pay = base + put[opp] if r > 0 else -put[me] if r < 0 else (base + put[opp] - put[me]) / 2
            rows.append((1.0 / len(tails), pay))
        return rows

    def play(n, board, prior, street, h, o):
        if n.get("node_type") == "chance_node":
            put = {p: prior[p] + street[p] for p in prior}
            cards = [c for c in n["dealcards"] if c not in board and not has_card(h, c) and not has_card(o, c)]
            out = []
            for c in cards:
                out += [(w / len(cards), x) for w, x in play(n["dealcards"][c], board + [c], put, {"oop": 0.0, "ip": 0.0}, h, o)]
            return out
        who = view.actor(n)
        strat = _combo_strategies(n)[h if who == me else o]
        out = []
        for i, a in enumerate(n["actions"]):
            if strat[i] > 0:
                out += [(strat[i] * w, x) for w, x in after(n, a, board, prior, street, h, o)]
        return out

    evs = []
    for a in node["actions"]:
        num = den = 0.0
        for o, w in reach_o.items():
            if w <= 0 or has_card(o, hero_combo[:2]) or has_card(o, hero_combo[2:]):
                continue
            rows = after(node, a, list(ctx["board"]), prior0, dict(ctx["committed"]), hero_combo, o)
            num += w * sum(p * x for p, x in rows)
            den += w * sum(p for p, _ in rows)
        evs.append(num / den if den else None)
    return evs


def check(view, path, tol=1e-9):
    res = node_evs(view, path)
    assert res is not None
    node = view.walk(path)[-1]
    for combo, row in res["ev"].items():
        ref = reference(view, path, combo)
        for got, want in zip(row, ref):
            assert (got is None) == (want is None)
            if got is not None:
                assert math.isclose(got, want, rel_tol=tol, abs_tol=tol), (path, combo, node["actions"], row, ref)
    return res


def test_fold_value_by_hand_and_flop_runouts_are_flagged_inexact():
    # OOP faces IP's RAISE 85 after betting 25: FOLD loses the 25 already put in, for every hand.
    view = SolveView(trees.build(), trees.spot())
    res = node_evs(view, ["BET 25.000000", "RAISE 85.000000"])
    assert res["actions"] == ["FOLD", "CALL"]
    for row in res["ev"].values():
        assert math.isclose(row[0], -25.0)
    assert res["exact"] is False      # CALL ends on the flop with two cards to come: sampled, not exact


@pytest.mark.parametrize("path", [
    ["BET 25.000000", "CALL", "@3c"],                            # turn nodes: one card to come, enumerated
    ["BET 25.000000", "CALL", "@Ac"],
    ["BET 25.000000", "CALL", "@3c", "CHECK"],
])
def test_matches_brute_force_on_hand_built_tree(path):
    view = SolveView(trees.build(), trees.spot())
    res = check(view, path)
    assert res["exact"] is True


def test_matches_brute_force_on_real_river_solve(river_tree, river_spot):
    view = SolveView(river_tree, river_spot)
    res = check(view, [], tol=1e-6)
    assert res["exact"] is True
    child = next(a for a in river_tree["actions"] if a in river_tree["childrens"])
    check(view, [child], tol=1e-6)


def test_zero_sum_on_real_river(river_tree, river_spot):
    """Per hand pair the two payoffs add up to the dead money, so after weighting by reach and mass the two
    players' values add up to ``pot`` times the number of compatible pairs."""
    view = SolveView(river_tree, river_spot)
    reach = view.reach([])
    oop = node_evs(view, [])
    # IP's values at the same spot: take the first line OOP can play that keeps the hand going.
    line = next(a for a in river_tree["actions"] if a in river_tree["childrens"])
    node = river_tree["childrens"][line]
    ip = node_evs(view, [line])
    # Compare the full-strategy EV of OOP-after-line with IP's, both restricted to that line's reach.
    r2 = view.reach([line])
    strat = _combo_strategies(river_tree)
    idx = river_tree["actions"].index(line)
    num = sum(r2["oop"].get(c, 0) * (oop["ev"][c][idx] or 0) * oop["mass"][c] for c in oop["ev"] if c in r2["oop"])
    ev_ip = sum(r2["ip"].get(c, 0) * (v * ip["mass"][c]) for c in ip["ev"] for v in [sum(
        p * (e or 0) for p, e in zip(_combo_strategies(node)[c], ip["ev"][c]))])
    pairs = sum(r2["oop"][a] * r2["ip"][b] for a in r2["oop"] for b in r2["ip"]
                if not ({a[:2], a[2:]} & {b[:2], b[2:]}))
    assert pairs > 0
    assert math.isclose(num / 1.0 + ev_ip, view.spot.pot * pairs, rel_tol=1e-3)


def test_strategy_mix_ev_is_consistent(river_tree, river_spot):
    """The EV of an action never exceeds the best action's, and the frequency-weighted mix lies between min and max."""
    view = SolveView(river_tree, river_spot)
    res = node_evs(view, [])
    strat = _combo_strategies(river_tree)
    for combo, row in res["ev"].items():
        vals = [v for v in row if v is not None]
        mix = sum(p * v for p, v in zip(strat[combo], row) if v is not None and p > 0)
        assert min(vals) - 1e-9 <= mix <= max(vals) + 1e-9


def test_budget_returns_none(river_tree, river_spot):
    view = SolveView(river_tree, river_spot)
    assert node_evs(view, [], max_work=10) is None


def test_non_action_node_returns_none():
    view = SolveView(trees.build(), trees.spot())
    assert node_evs(view, ["BET 25.000000", "CALL"]) is None
