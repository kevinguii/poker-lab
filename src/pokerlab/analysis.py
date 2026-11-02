"""Hand history analysis: replay a hand, derive a solvable spot, grade the hero's decisions.

Scope (v1, on purpose narrow so the numbers can be trusted):

* heads-up on the flop, hero known, a preset exists for the pot type;
* the spot is a *flop* solve with ``dump_rounds=2`` so flop **and turn** decisions are graded
  with properly narrowed ranges; river decisions are listed but not graded;
* ranges come from your presets, not from the hand. If your actual hand is not in the preset
  range at a node it is reported as ``out_of_range`` rather than graded.
"""

from __future__ import annotations

import copy

from .progress import ProgressStore
from .ranges import canon_combo
from .spot import DEFAULT_BET_SIZES, Spot
from .strategy import SolveView, parse_action, action_label, DEAL
from .training import grade

UNIT = 10                      # solver chips per big blind (the solver rounds bets to whole chips)
ANALYSIS_ACCURACY = 1.0        # % of pot: looser than the viewer default, flop solves are slow
ANALYSIS_ITERATIONS = 150
POT_TYPES = {0: "limp", 1: "srp", 2: "3bp", 3: "4bp"}
STREETS = ("flop", "turn", "river")


# ------------------------------------------------------------------ replay ----
def replay(hand: dict) -> dict:
    """Walk the actions and return, per street, the pot / stacks at its start (in bb) and each action."""
    bb = hand["bb"]
    stack0 = {s["name"]: s["stack"] for s in hand["seats"]}
    invested = {n: hand["antes"].get(n, 0.0) for n in stack0}
    commit = {n: 0.0 for n in stack0}
    active = list(stack0)
    out: dict = {}
    cur = None

    def start(street: str) -> None:
        out[street] = {
            "start_pot": sum(invested.values()) / bb,
            "start_stacks": {n: (stack0[n] - invested[n]) / bb for n in stack0},
            "active": list(active),
            "actions": [],
        }

    for a in hand["actions"]:
        if a["street"] != cur:
            if cur is not None:
                for n in commit:
                    invested[n] += commit[n]
                    commit[n] = 0.0
            cur = a["street"]
            start(cur)
        p, kind = a["player"], a["kind"]
        if kind == "uncalled":
            commit[p] -= a["amount"]
            continue
        rec = {
            "player": p, "kind": kind, "allin": bool(a.get("allin")),
            "pot_before": (sum(invested.values()) + sum(commit.values())) / bb,
            "commit_before": commit[p] / bb,
            "facing": max(commit.values()) / bb,
        }
        if kind == "posts":
            commit[p] += a["amount"]
        elif kind == "calls":
            commit[p] += a["amount"]
        elif kind == "bets":
            commit[p] += a["amount"]
        elif kind == "raises":
            commit[p] = a["to"] if a["to"] is not None else commit[p] + (a["amount"] or 0.0)
        elif kind == "folds":
            if p in active:
                active.remove(p)
        rec["to"] = commit[p] / bb
        if kind != "posts":
            out[cur]["actions"].append(rec)
    return out


def positions(hand: dict, a: str, b: str) -> dict[str, str]:
    """Map two players to ``ip``/``oop`` from seat order relative to the button."""
    seats = sorted(s["seat"] for s in hand["seats"])
    after = [x for x in seats if x > hand["button"]] + [x for x in seats if x <= hand["button"]]
    by_seat = {s["name"]: s["seat"] for s in hand["seats"]}
    first, second = sorted((a, b), key=lambda n: after.index(by_seat[n]))
    return {first: "oop", second: "ip"}


def pot_type(hand: dict) -> str:
    raises = sum(1 for a in hand["actions"] if a["street"] == "preflop" and a["kind"] == "raises")
    return POT_TYPES.get(raises, "5bp+")


# -------------------------------------------------------------- spot building ----
def _extra_sizes(rp: dict, role_of: dict[str, str]) -> dict:
    """Default sizes plus every flop/turn bet and raise actually made, so they exist in the tree."""
    sizes = copy.deepcopy(DEFAULT_BET_SIZES)
    for street in ("flop", "turn"):
        if street not in rp:
            continue
        stack = max(rp[street]["start_stacks"].values())
        for a in rp[street]["actions"]:
            if a["kind"] not in ("bets", "raises") or a["player"] not in role_of:
                continue
            if a["allin"] or a["to"] >= 0.97 * stack:
                continue                                   # all-in is always in the tree
            if a["kind"] == "bets":
                pct = a["to"] / a["pot_before"] * 100
                kind = "bet"
            else:
                call = a["facing"] - a["commit_before"]
                pct = (a["to"] - a["facing"]) / (a["pot_before"] + call) * 100
                kind = "raise"
            pct = int(round(pct))
            if not 10 <= pct <= 400:
                continue
            have = sizes[role_of[a["player"]]][street].setdefault(kind, [])
            if all(abs(pct - h) > 4 for h in have):
                have.append(pct)
                have.sort()
    return sizes


def prepare(hand: dict, progress: ProgressStore, preset_name: str | None = None) -> dict:
    """Eligibility + the spot to solve. Never raises for an unusable hand: it explains why."""
    info: dict = {
        "id": hand["id"], "hero": hand.get("hero"), "hero_cards": hand.get("hero_cards"),
        "board": hand["board"], "pot_type": pot_type(hand), "eligible": False, "reason": None,
        "hero_role": None, "preset": None, "spot": None, "spot_id": None,
    }
    if not hand.get("hero_cards"):
        info["reason"] = "hero's cards are not in this history"
        return info
    rp = replay(hand)
    if "flop" not in rp or not hand["board"]["flop"]:
        info["reason"] = "the hand never reached the flop"
        return info
    active = rp["flop"]["active"]
    if hand["hero"] not in active:
        info["reason"] = "hero folded before the flop"
        return info
    if len(active) != 2:
        info["reason"] = f"{len(active)} players saw the flop (only heads-up pots are analysed)"
        return info
    villain = next(n for n in active if n != hand["hero"])
    role_of = positions(hand, hand["hero"], villain)
    preset = progress.get_preset(preset_name) if preset_name else progress.preset_for_pot_type(info["pot_type"])
    if preset is None:
        info["reason"] = f"no preset for {info['pot_type']} pots: add one in the Presets tab"
        return info

    start = rp["flop"]
    eff = min(start["start_stacks"][hand["hero"]], start["start_stacks"][villain])
    spot = Spot(
        board=",".join(hand["board"]["flop"]),
        ip_range=preset["ip_range"], oop_range=preset["oop_range"],
        pot=round(start["start_pot"] * UNIT), effective_stack=round(eff * UNIT),
        bet_sizes=_extra_sizes(rp, role_of),
        accuracy=ANALYSIS_ACCURACY, max_iteration=ANALYSIS_ITERATIONS, dump_rounds=2,
    )
    try:
        spot.validate()
    except ValueError as e:
        info["reason"] = f"could not build a spot: {e}"
        return info
    info.update(
        eligible=True, hero_role=role_of[hand["hero"]], villain=villain, preset=preset["name"],
        spot=spot.to_dict(), spot_id=spot.spot_id(),
        pot_bb=start["start_pot"], eff_stack_bb=eff,
    )
    return info


# ---------------------------------------------------------------- evaluation ----
def _match(actions: list[str], kind: str, to_units: float, pot_units: float) -> str | None:
    """Map what was actually done onto the closest action available in the tree."""
    want = {"checks": "CHECK", "calls": "CALL", "folds": "FOLD"}.get(kind)
    if want:
        return want if want in actions else None
    prefixes = ("BET", "DONK") if kind == "bets" else ("RAISE",)
    cands = [a for a in actions if parse_action(a)[0] in prefixes]
    if not cands:
        return None
    best = min(cands, key=lambda a: abs((parse_action(a)[1] or 0) - to_units))
    if abs((parse_action(best)[1] or 0) - to_units) > 0.2 * pot_units:
        return None
    return best


def _label(a: dict) -> str:
    to = f" to {a['to']:.1f}bb" if a["kind"] in ("bets", "raises") else ""
    return {"checks": "Check", "calls": "Call", "folds": "Fold", "bets": "Bet", "raises": "Raise"}[a["kind"]] + to


def evaluate(view: SolveView, hand: dict, info: dict) -> dict:
    """Walk the real betting line through the solved tree and grade every hero decision."""
    rp = replay(hand)
    hero, villain = hand["hero"], info["villain"]
    hero_role = info["hero_role"]
    role_of = {hero: hero_role, villain: "ip" if hero_role == "oop" else "oop"}
    combo = canon_combo("".join(hand["hero_cards"]))
    path: list[str] = []
    alive, why = True, ""
    cur_street = "flop"
    decisions = []

    for street in STREETS:
        if street not in rp:
            continue
        for a in rp[street]["actions"]:
            if a["player"] not in role_of or a["kind"] in ("posts",):
                continue
            is_hero = a["player"] == hero
            status, fb, matched, reach_note = "graded", None, None, None

            if alive and street != cur_street:                        # crossing a street: deal the real card
                node = view.walk(path)[-1]
                card = hand["board"].get(street)
                if node.get("node_type") == "chance_node" and card and card in view.legal_deals(path):
                    path.append(DEAL + card)
                    cur_street = street
                else:
                    alive, why = False, "this street is not part of the solve"
            if alive:
                node = view.walk(path)[-1]
                if node.get("node_type") != "action_node":
                    alive, why = False, "the solver tree ended before this action"
                elif view.actor(node) != role_of[a["player"]]:
                    alive, why = False, "the hand's action order differs from the tree"
                else:
                    ctx = view.context(path)
                    matched = _match(node["actions"], a["kind"], a["to"] * UNIT, ctx["pot"])
                    if matched is None:
                        alive, why = False, f"{_label(a)} has no close equivalent in the tree"

            if alive:
                if is_hero:
                    cs = view.combo_strategy(path, combo)
                    if cs is None:
                        status = "out_of_range"
                    else:
                        fb = grade(cs[0], cs[1], matched)
                        fb["labels"] = [action_label(x) for x in fb["actions"]]
                        reach = view.reach(path)[hero_role].get(combo, 0.0)
                        if reach < 0.001:
                            reach_note = "an earlier action had ~0% solver frequency for your hand, so this node is off-tree"
                        fb["reach"] = reach
                if matched in node.get("childrens", {}):
                    path.append(matched)
                else:
                    alive, why = False, "the hand ends here in the solver tree"
            elif is_hero:
                status = "river_not_covered" if street == "river" else "not_in_solve"

            if is_hero:
                decisions.append({
                    "street": street, "action": _label(a), "pot_bb": a["pot_before"],
                    "to_call_bb": max(0.0, a["facing"] - a["commit_before"]),
                    "status": status, "matched": matched, "feedback": fb,
                    "note": reach_note or (why if status in ("not_in_solve",) else None),
                })
    graded = [d for d in decisions if d["status"] == "graded" and d["feedback"]]
    return {
        "decisions": decisions,
        "summary": {
            "graded": len(graded),
            "avg_score": sum(d["feedback"]["score"] for d in graded) / len(graded) if graded else None,
            "mistakes": sum(1 for d in graded if d["feedback"]["verdict"] == "mistake"),
            "mixes": sum(1 for d in graded if d["feedback"]["verdict"] == "mix"),
        },
    }
