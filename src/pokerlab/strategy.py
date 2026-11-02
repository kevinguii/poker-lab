"""Navigate a solved tree and turn per-combo strategies into viewer/trainer data.

Solver JSON shape (TexasSolver ``dump_result``):

    action node = {
      "node_type": "action_node",
      "player": 0|1,
      "actions": ["CHECK", "BET 25.000000", ...],
      "strategy": {"actions": [...], "strategy": {"AsKd": [p_check, p_bet, ...], ...}},
      "childrens": {"CHECK": node, ...}     # a missing key means the hand ends (fold / showdown)
    }
    chance node = {"node_type": "chance_node", "deal_number": n, "dealcards": {"2c": node, ...}}
                  ("dealcards" is absent when the dump did not include the next street)

A *path* is a list of steps from the root. A step is an action string
(``"BET 25.000000"``) or a deal (``"@7d"``) that crosses a chance node.

The dump holds *conditional* strategies only (no reach, no EV), so reach
probabilities are rebuilt by walking the path from the root. Bet/raise amounts
in action names are the player's total commitment on that street.
"""

from __future__ import annotations

from .evaluator import best_hand, describe
from .ranges import all_classes, canon_combo, expand_range, grid_class, hand_class, parse_range
from .spot import Spot

PATH_SEP = "|"
STREET_BY_CARDS = {3: "flop", 4: "turn", 5: "river"}
DEAL = "@"


class PathError(KeyError):
    pass


def parse_action(step: str) -> tuple[str, float | None]:
    kind, _, amt = step.partition(" ")
    return kind, (float(amt) if amt else None)


def is_deal(step: str) -> bool:
    return step.startswith(DEAL)


def action_label(step: str) -> str:
    if is_deal(step):
        return f"Deal {step[1:]}"
    kind, amt = parse_action(step)
    name = kind[0] + kind[1:].lower()
    return f"{name} {amt:g}" if amt is not None else name


def _combo_strategies(node: dict) -> dict[str, list[float]]:
    return {canon_combo(k): v for k, v in node["strategy"]["strategy"].items()}


def has_card(combo: str, card: str) -> bool:
    return combo[:2] == card or combo[2:] == card


class SolveView:
    """Read-only helper around one solved tree and the spot that produced it."""

    def __init__(self, tree: dict, spot: Spot):
        self.tree = tree
        self.spot = spot
        self._board = spot.board_cards()
        dead = frozenset(self._board)
        self._init = {
            "ip": expand_range(parse_range(spot.ip_range), dead),
            "oop": expand_range(parse_range(spot.oop_range), dead),
        }
        # The first player to act postflop is OOP.
        self._oop_id = tree["player"]
        self._ids = {"oop": self._oop_id, "ip": 1 - self._oop_id}

    # ---- basics -------------------------------------------------------------
    def actor(self, node: dict) -> str:
        return "oop" if node["player"] == self._ids["oop"] else "ip"

    def initial_weights(self) -> dict[str, dict[str, float]]:
        return {p: dict(w) for p, w in self._init.items()}

    def dead_cards(self, path: list[str]) -> list[str]:
        return self._board + [s[1:] for s in path if is_deal(s)]

    # ---- navigation -----------------------------------------------------------
    def walk(self, path: list[str]) -> list[dict]:
        """Nodes visited along ``path`` (root first, target node last)."""
        nodes = [self.tree]
        dead = set(self._board)
        for step in path:
            node = nodes[-1]
            kind = node.get("node_type")
            if is_deal(step):
                card = step[1:]
                if kind != "chance_node":
                    raise PathError(f"cannot deal {card}: not a chance node")
                deals = node.get("dealcards") or {}
                if not deals:
                    raise PathError("next street is not part of this solve")
                if card in dead or card not in deals:
                    raise PathError(f"cannot deal {card}")
                dead.add(card)
                nodes.append(deals[card])
                continue
            if kind != "action_node":
                raise PathError(f"cannot take {step!r}: not an action node")
            children = node.get("childrens", {})
            if step not in children:
                if step in node.get("actions", []):
                    raise PathError(f"{step!r} ends the hand")
                raise PathError(f"unknown action {step!r}")
            nodes.append(children[step])
        return nodes

    def legal_deals(self, path: list[str], exclude: set[str] | frozenset[str] = frozenset()) -> list[str]:
        node = self.walk(path)[-1]
        if node.get("node_type") != "chance_node":
            return []
        dead = set(self.dead_cards(path)) | set(exclude)
        return sorted(c for c in (node.get("dealcards") or {}) if c not in dead)

    def reach(self, path: list[str]) -> dict[str, dict[str, float]]:
        """Reach weight of every combo for both players at the end of ``path``."""
        reach = self.initial_weights()
        nodes = self.walk(path)
        for node, step in zip(nodes, path):
            if is_deal(step):
                card = step[1:]
                reach = {p: {c: w for c, w in r.items() if not has_card(c, card)} for p, r in reach.items()}
                continue
            who = self.actor(node)
            idx = node["actions"].index(step)
            strat = _combo_strategies(node)
            reach[who] = {c: w * strat[c][idx] for c, w in reach[who].items() if c in strat}
        return reach

    # ---- pot / stack / board bookkeeping --------------------------------------
    def context(self, path: list[str], final: str | None = None) -> dict:
        """Board, pot, stacks and betting history at the end of ``path``.

        ``final`` optionally applies one last action that ends the hand (fold,
        call, check-back on the river), which has no node of its own.
        """
        nodes = self.walk(path)
        board = list(self._board)
        base = float(self.spot.pot)
        stack = {"oop": float(self.spot.effective_stack), "ip": float(self.spot.effective_stack)}
        committed = {"oop": 0.0, "ip": 0.0}
        history: list[dict] = []

        def apply(who: str, step: str) -> None:
            opp = "ip" if who == "oop" else "oop"
            kind, amt = parse_action(step)
            if kind == "CALL":
                committed[who] = committed[opp]
            elif kind in ("BET", "RAISE", "DONK"):
                committed[who] = amt or 0.0
            history.append({"street": STREET_BY_CARDS[len(board)], "actor": who, "action": step,
                            "label": action_label(step)})

        for node, step in zip(nodes, path):
            if is_deal(step):
                base += committed["oop"] + committed["ip"]
                for p in stack:
                    stack[p] -= committed[p]
                committed = {"oop": 0.0, "ip": 0.0}
                board.append(step[1:])
                history.append({"street": STREET_BY_CARDS[len(board)], "deal": step[1:], "label": f"Deal {step[1:]}"})
            else:
                apply(self.actor(node), step)
        if final is not None:
            apply(self.actor(nodes[-1]), final)

        last = nodes[-1]
        out = {
            "board": board,
            "street": STREET_BY_CARDS[len(board)],
            "pot": base + committed["oop"] + committed["ip"],
            "stacks": {p: stack[p] - committed[p] for p in stack},
            "committed": dict(committed),
            "committed_total": {p: (self.spot.effective_stack - stack[p]) + committed[p] for p in stack},
            "history": history,
        }
        if last.get("node_type") == "action_node" and final is None:
            who = self.actor(last)
            opp = "ip" if who == "oop" else "oop"
            out["to_call"] = max(0.0, committed[opp] - committed[who])
        return out

    # ---- viewer payloads -------------------------------------------------------
    def describe(self, path: list[str]) -> dict:
        nodes = self.walk(path)
        node = nodes[-1]
        out: dict = {"path": path, "node_type": node.get("node_type"), "context": self.context(path)}
        if node.get("node_type") == "chance_node":
            deals = self.legal_deals(path)
            out["deals"] = deals
            if not deals:
                out["note"] = "The next street is not part of this solve (it was solved with dump_rounds=1)."
            return out
        if node.get("node_type") != "action_node":
            out["note"] = "Terminal node."
            return out

        reach = self.reach(path)
        who = self.actor(node)
        actions = node["actions"]
        strat = _combo_strategies(node)
        n = len(actions)

        # Aggregate to 169 classes, weighting each combo by how often the actor
        # actually arrives here with it.
        grid: dict[str, dict] = {}
        totals = [0.0] * n
        total_w = 0.0
        sums: dict[str, list[float]] = {}
        weights: dict[str, float] = {}
        counts: dict[str, int] = {}
        for combo, w in reach[who].items():
            if w <= 0 or combo not in strat:
                continue
            cls = hand_class(combo)
            weights[cls] = weights.get(cls, 0.0) + w
            counts[cls] = counts.get(cls, 0) + 1
            acc = sums.setdefault(cls, [0.0] * n)
            for i, p in enumerate(strat[combo]):
                acc[i] += w * p
                totals[i] += w * p
            total_w += w
        for cls, acc in sums.items():
            w = weights[cls]
            grid[cls] = {"weight": w, "combos": counts[cls], "freqs": [a / w for a in acc]}

        children = node.get("childrens", {})
        out.update(
            actor=who,
            actions=actions,
            overall=[t / total_w for t in totals] if total_w else [0.0] * n,
            grid=grid,
            children=[
                {
                    "action": a,
                    "terminal": a not in children,
                    "chance": a in children and children[a].get("node_type") == "chance_node",
                }
                for a in actions
            ],
            range_combos={"ip": round(sum(reach["ip"].values()), 3), "oop": round(sum(reach["oop"].values()), 3)},
        )
        return out

    def combos(self, path: list[str], cls: str) -> dict:
        """Per-combo strategy for one hand class at the end of ``path``."""
        node = self.walk(path)[-1]
        if node.get("node_type") != "action_node":
            raise PathError("not an action node")
        reach = self.reach(path)[self.actor(node)]
        strat = _combo_strategies(node)
        rows = [
            {"combo": c, "reach": reach.get(c, 0.0), "freqs": strat[c]}
            for c in sorted(strat)
            if hand_class(c) == cls
        ]
        return {"class": cls, "actions": node["actions"], "combos": rows}

    # ---- trainer helpers --------------------------------------------------------
    def combo_strategy(self, path: list[str], combo: str) -> tuple[list[str], list[float]] | None:
        """``(actions, frequencies)`` for one exact combo at an action node, or None."""
        node = self.walk(path)[-1]
        if node.get("node_type") != "action_node":
            return None
        freqs = _combo_strategies(node).get(canon_combo(combo))
        return (node["actions"], freqs) if freqs is not None else None

    def hand_name(self, combo: str, board: list[str]) -> str | None:
        if len(board) < 3:
            return None
        return describe(best_hand([combo[:2], combo[2:]] + board))


def empty_grid() -> list[list[str]]:
    return [[grid_class(r, c) for c in range(13)] for r in range(13)]


__all__ = ["SolveView", "PathError", "PATH_SEP", "DEAL", "all_classes", "empty_grid",
           "parse_action", "action_label", "is_deal", "has_card", "STREET_BY_CARDS"]
