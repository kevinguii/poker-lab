"""Navigate a solved tree and turn per-combo strategies into viewer data.

Solver JSON shape (TexasSolver ``dump_result``):

    node = {
      "node_type": "action_node",
      "player": 0|1,
      "actions": ["CHECK", "BET 25.000000", ...],
      "strategy": {"actions": [...], "strategy": {"AsKd": [p_check, p_bet, ...], ...}},
      "childrens": {"CHECK": node, "BET 25.000000": node, ...}   # missing key => terminal (fold)
    }
    chance node = {"node_type": "chance_node", "deal_number": n, "dealcards": {...}}

The dump holds *conditional* strategies only (no reach or EV), so we rebuild
reach probabilities by walking the path from the root.
"""

from __future__ import annotations

from .ranges import all_classes, canon_combo, expand_range, grid_class, hand_class, parse_range
from .spot import Spot

PATH_SEP = "|"


class PathError(KeyError):
    pass


def _combo_strategies(node: dict) -> dict[str, list[float]]:
    raw = node["strategy"]["strategy"]
    return {canon_combo(k): v for k, v in raw.items()}


class SolveView:
    """Read-only helper around one solved tree and the spot that produced it."""

    def __init__(self, tree: dict, spot: Spot):
        self.tree = tree
        self.spot = spot
        dead = frozenset(spot.board_cards())
        self._init = {
            "ip": expand_range(parse_range(spot.ip_range), dead),
            "oop": expand_range(parse_range(spot.oop_range), dead),
        }
        # The first player to act postflop is OOP.
        self._oop_id = tree["player"]
        self._ids = {"oop": self._oop_id, "ip": 1 - self._oop_id}

    # ---- navigation -------------------------------------------------------
    def walk(self, path: list[str]) -> list[dict]:
        """Nodes visited along ``path`` (root first, target node last)."""
        nodes = [self.tree]
        for action in path:
            node = nodes[-1]
            if node.get("node_type") != "action_node":
                raise PathError(f"cannot take {action!r}: not an action node")
            children = node.get("childrens", {})
            if action not in children:
                if action in node.get("actions", []):
                    raise PathError(f"{action!r} ends the hand")
                raise PathError(f"unknown action {action!r}")
            nodes.append(children[action])
        return nodes

    def reach(self, path: list[str]) -> dict[str, dict[str, float]]:
        """Reach weight of every combo for both players at the end of ``path``."""
        reach = {p: dict(self._init[p]) for p in ("ip", "oop")}
        nodes = self.walk(path)
        for node, action in zip(nodes, path):
            if node.get("node_type") != "action_node":
                continue
            who = "oop" if node["player"] == self._ids["oop"] else "ip"
            idx = node["actions"].index(action)
            strat = _combo_strategies(node)
            reach[who] = {c: w * strat[c][idx] for c, w in reach[who].items() if c in strat}
        return reach

    # ---- viewer payloads ----------------------------------------------------
    def describe(self, path: list[str]) -> dict:
        nodes = self.walk(path)
        node = nodes[-1]
        out: dict = {"path": path, "node_type": node.get("node_type")}
        if node.get("node_type") != "action_node":
            out["note"] = (
                "Next street was not included in this solve (dump_rounds=1)."
                if node.get("node_type") == "chance_node"
                else "Terminal node."
            )
            return out

        reach = self.reach(path)
        who = "oop" if node["player"] == self._ids["oop"] else "ip"
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
        who = "oop" if node["player"] == self._ids["oop"] else "ip"
        reach = self.reach(path)[who]
        strat = _combo_strategies(node)
        rows = [
            {"combo": c, "reach": reach.get(c, 0.0), "freqs": strat[c]}
            for c in sorted(strat)
            if hand_class(c) == cls
        ]
        return {"class": cls, "actions": node["actions"], "combos": rows}


def empty_grid() -> list[list[str]]:
    return [[grid_class(r, c) for c in range(13)] for r in range(13)]


__all__ = ["SolveView", "PathError", "PATH_SEP", "all_classes", "empty_grid"]
