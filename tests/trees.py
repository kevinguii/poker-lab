"""A small hand-built solver tree with exact, known numbers (same JSON shape as TexasSolver).

Spot: board Qs Jh 2h, pot 50, effective stack 200
      OOP = KK + AQs   (KK: 6 combos, AQs: 3 combos because Qs is on the board)
      IP  = AA + QQ    (AA: 6 combos, QQ: 3 combos)
OOP acts first (player id 1, like the real solver output).

Tree:
  root OOP [CHECK, BET 25]
    CHECK -> IP [CHECK, BET 25]
        CHECK -> chance (no dealcards)
        BET 25 -> OOP [FOLD, CALL, RAISE 85]  (CALL/RAISE end the tree here)
    BET 25 -> IP [FOLD, CALL, RAISE 85]
        CALL -> chance with turn cards 3c and Ac
              3c -> OOP [CHECK, BET 50] ; CHECK -> IP [CHECK, BET 50]
              Ac -> OOP [CHECK, BET 50]   (combos holding Ac are absent)
        RAISE 85 -> OOP [FOLD, CALL]
"""

from __future__ import annotations

from pokerlab.ranges import expand_range, parse_range
from pokerlab.spot import Spot

OOP, IP = 1, 0
BOARD = ["Qs", "Jh", "2h"]


def spot() -> Spot:
    return Spot(board=",".join(BOARD), ip_range="AA,QQ", oop_range="KK,AQs", pot=50, effective_stack=200)


def combos(rng: str, dead: list[str]) -> list[str]:
    return sorted(expand_range(parse_range(rng), frozenset(dead)))


def node(player: int, actions: list[str], strat_by_class: dict[str, list[float]], rng: str,
         children: dict | None = None, dead: list[str] | None = None) -> dict:
    from pokerlab.ranges import hand_class

    strategy = {c: list(strat_by_class[hand_class(c)]) for c in combos(rng, dead or BOARD)}
    return {
        "node_type": "action_node",
        "player": player,
        "actions": actions,
        "strategy": {"actions": actions, "strategy": strategy},
        "childrens": children or {},
    }


def chance(deals: dict[str, dict] | None) -> dict:
    n: dict = {"node_type": "chance_node", "deal_number": len(deals or {})}
    if deals:
        n["dealcards"] = deals
    return n


def build() -> dict:
    oop_r, ip_r = "KK,AQs", "AA,QQ"
    dead3c = BOARD + ["3c"]
    deadAc = BOARD + ["Ac"]

    turn_3c = node(OOP, ["CHECK", "BET 50.000000"], {"KK": [0.7, 0.3], "AQs": [0.4, 0.6]}, oop_r,
                   {"CHECK": node(IP, ["CHECK", "BET 50.000000"], {"AA": [0.5, 0.5], "QQ": [0.0, 1.0]}, ip_r, dead=dead3c)},
                   dead=dead3c)
    turn_Ac = node(OOP, ["CHECK", "BET 50.000000"], {"KK": [0.7, 0.3], "AQs": [0.4, 0.6]}, oop_r, dead=deadAc)

    ip_vs_bet = node(
        IP, ["FOLD", "CALL", "RAISE 85.000000"], {"AA": [0.0, 0.5, 0.5], "QQ": [0.1, 0.9, 0.0]}, ip_r,
        {
            "CALL": chance({"3c": turn_3c, "Ac": turn_Ac}),
            "RAISE 85.000000": node(OOP, ["FOLD", "CALL"], {"KK": [0.0, 1.0], "AQs": [0.7, 0.3]}, oop_r),
        },
    )
    oop_vs_bet = node(OOP, ["FOLD", "CALL", "RAISE 85.000000"], {"KK": [0.0, 0.6, 0.4], "AQs": [0.5, 0.5, 0.0]}, oop_r,
                      {"CALL": chance(None)})
    ip_after_check = node(
        IP, ["CHECK", "BET 25.000000"], {"AA": [0.5, 0.5], "QQ": [0.0, 1.0]}, ip_r,
        {"CHECK": chance(None), "BET 25.000000": oop_vs_bet},
    )
    return node(
        OOP, ["CHECK", "BET 25.000000"], {"KK": [0.2, 0.8], "AQs": [0.9, 0.1]}, oop_r,
        {"CHECK": ip_after_check, "BET 25.000000": ip_vs_bet},
    )
