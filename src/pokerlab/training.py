"""Trainer engine: play hands against the solver, drill single nodes, grade decisions.

Grading (no EV is available in TexasSolver's dump, so this is frequency based):

    score   = freq(chosen) / freq(best)            1.0 when you pick the solver's top action
    verdict = "correct"  chosen is the top action, or the solver takes it >= 25% of the time
              "mix"      the solver takes it 5-25% of the time (acceptable low-frequency play)
              "mistake"  the solver takes it < 5% of the time
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Callable

from .evaluator import best_hand, describe
from .strategy import SolveView, action_label, is_deal, parse_action, DEAL

CORRECT_MIN_FREQ = 0.25
MIX_MIN_FREQ = 0.05

AttemptHook = Callable[[dict], None]


# ---------------------------------------------------------------- grading ----
def grade(actions: list[str], freqs: list[float], chosen: str) -> dict:
    if chosen not in actions:
        raise ValueError(f"{chosen!r} is not available here")
    f = freqs[actions.index(chosen)]
    fmax = max(freqs)
    best = actions[freqs.index(fmax)]
    score = f / fmax if fmax > 0 else 0.0
    if chosen == best or f >= CORRECT_MIN_FREQ:
        verdict = "correct"
    elif f >= MIX_MIN_FREQ:
        verdict = "mix"
    else:
        verdict = "mistake"
    return {
        "chosen": chosen,
        "best": best,
        "freq": f,
        "score": score,
        "verdict": verdict,
        "actions": actions,
        "freqs": list(freqs),
        "labels": [action_label(a) for a in actions],
    }


# --------------------------------------------------------------- sampling ----
def _shares_card(a: str, b: str) -> bool:
    return bool({a[:2], a[2:]} & {b[:2], b[2:]})


def sample_matchup(rng: random.Random, hero_w: dict[str, float], vill_w: dict[str, float]) -> tuple[str, str]:
    """Draw ``(hero_combo, villain_combo)`` with probability proportional to
    ``hero_w[h] * vill_w[v]`` over pairs that do not share a card (exact, no rejection)."""
    card_mass: dict[str, float] = defaultdict(float)
    for v, w in vill_w.items():
        card_mass[v[:2]] += w
        card_mass[v[2:]] += w
    total = sum(vill_w.values())
    hs, ws = [], []
    for h, w in hero_w.items():
        if w <= 0:
            continue
        # villain mass on combos sharing a card with h (h itself counted once)
        conflict = card_mass[h[:2]] + card_mass[h[2:]] - vill_w.get(h, 0.0)
        compatible = total - conflict
        if compatible > 1e-12:
            hs.append(h)
            ws.append(w * compatible)
    if not hs:
        raise ValueError("no compatible hands for this matchup")
    hero = rng.choices(hs, ws)[0]
    vs = [v for v, w in vill_w.items() if w > 0 and not _shares_card(hero, v)]
    villain = rng.choices(vs, [vill_w[v] for v in vs])[0]
    return hero, villain


# -------------------------------------------------------------- decisions ----
def decision_state(view: SolveView, path: list[str], role: str, combo: str) -> dict:
    """What the player sees at one of their decisions (never includes the opponent's hand)."""
    node = view.walk(path)[-1]
    ctx = view.context(path)
    opp = "ip" if role == "oop" else "oop"
    return {
        "hero_role": role,
        "hero_combo": combo,
        "hero_hand": view.hand_name(combo, ctx["board"]),
        "board": ctx["board"],
        "street": ctx["street"],
        "pot": ctx["pot"],
        "to_call": ctx.get("to_call", 0.0),
        "hero_stack": ctx["stacks"][role],
        "villain_stack": ctx["stacks"][opp],
        "hero_committed": ctx["committed"][role],
        "villain_committed": ctx["committed"][opp],
        "history": ctx["history"],
        "actions": [{"action": a, "label": action_label(a)} for a in node["actions"]],
    }


def explain(view: SolveView, path: list[str], combo: str, feedback: dict) -> str:
    """One-paragraph, solver-grounded explanation shown after an answer."""
    mix = ", ".join(
        f"{action_label(a)} {f * 100:.0f}%"
        for a, f in sorted(zip(feedback["actions"], feedback["freqs"]), key=lambda x: -x[1])
        if f >= 0.005
    )
    rng_line = ""
    node = view.describe(path)
    if node.get("overall"):
        rmix = ", ".join(
            f"{action_label(a)} {f * 100:.0f}%"
            for a, f in sorted(zip(node["actions"], node["overall"]), key=lambda x: -x[1])
            if f >= 0.005
        )
        rng_line = f" Across its whole range here, {node['actor'].upper()} plays: {rmix}."
    return f"With {combo[:2]}{combo[2:]} the solver plays: {mix}.{rng_line}"


# ------------------------------------------------------------------ session ---
class HandSession:
    """One hand: the player is ``hero_role``; the opponent is sampled from the solver.

    Starting at ``start_path`` lets you drill a specific node. With ``single=True`` the
    session ends after the player's first decision (a drill); otherwise it plays on
    until the hand ends, the next street is not in the solve, or a showdown.
    """

    def __init__(
        self,
        session_id: str,
        solve_id: str,
        view: SolveView,
        hero_role: str,
        rng: random.Random,
        start_path: list[str] | None = None,
        single: bool = False,
        on_attempt: AttemptHook | None = None,
        mode: str = "play",
    ):
        self.id = session_id
        self.solve_id = solve_id
        self.view = view
        self.rng = rng
        self.single = single
        self.mode = mode
        self.on_attempt = on_attempt
        self.path: list[str] = list(start_path or [])
        self.start_path = list(self.path)
        self.hero_role = hero_role
        self.villain_role = "ip" if hero_role == "oop" else "oop"
        self.finished = False
        self.result: dict | None = None
        self.decisions: list[dict] = []

        node = view.walk(self.path)[-1]
        if self.path and node.get("node_type") != "action_node":
            raise ValueError("start_path must end at an action node")
        if single and self.path and view.actor(node) != hero_role:
            raise ValueError("the chosen node is not a decision for the chosen player")
        reach = view.reach(self.path)
        self.hero_combo, self.villain_combo = sample_matchup(rng, reach[hero_role], reach[self.villain_role])
        self._advance()

    # -- internals ---------------------------------------------------------
    def _node(self) -> dict:
        return self.view.walk(self.path)[-1]

    def _advance(self) -> None:
        """Play the opponent's actions and deal cards until it is the player's turn or the hand ends."""
        while not self.finished:
            node = self._node()
            kind = node.get("node_type")
            if kind == "chance_node":
                deals = self.view.legal_deals(self.path, exclude={self.hero_combo[:2], self.hero_combo[2:],
                                                                  self.villain_combo[:2], self.villain_combo[2:]})
                if not deals:
                    self._finish("street_end")
                    return
                self.path.append(DEAL + self.rng.choice(deals))
                continue
            if kind != "action_node":
                self._finish("end")
                return
            who = self.view.actor(node)
            if who == self.hero_role:
                return
            cs = self.view.combo_strategy(self.path, self.villain_combo)
            if cs is None:
                raise ValueError("solver output has no strategy for the opponent's hand")
            actions, freqs = cs
            action = self.rng.choices(actions, freqs)[0]
            self._apply(who, action)

    def _apply(self, who: str, action: str) -> None:
        node = self._node()
        if action in node.get("childrens", {}):
            self.path.append(action)
        else:
            self._finish("fold" if parse_action(action)[0] == "FOLD" else "showdown", who=who, final=action)

    def _finish(self, reason: str, who: str | None = None, final: str | None = None) -> None:
        self.finished = True
        ctx = self.view.context(self.path, final=final)
        board = ctx["board"]
        hero_cards, vill_cards = [self.hero_combo[:2], self.hero_combo[2:]], [self.villain_combo[:2], self.villain_combo[2:]]
        res: dict = {
            "reason": reason,
            "villain_combo": self.villain_combo,
            "board": board,
            "pot": ctx["pot"],
            "winner": None,
            "net": None,
            "hero_hand": describe(best_hand(hero_cards + board)) if len(board) >= 3 else None,
            "villain_hand": describe(best_hand(vill_cards + board)) if len(board) >= 3 else None,
            "history": ctx["history"],
        }
        paid = ctx["committed_total"]
        if reason == "fold":
            hero_won = who == self.villain_role
            res["winner"] = "hero" if hero_won else "villain"
            res["net"] = paid[self.villain_role] if hero_won else -paid[self.hero_role]
        elif reason == "showdown":
            if len(board) == 5:
                h, v = best_hand(hero_cards + board), best_hand(vill_cards + board)
                if h > v:
                    res["winner"], res["net"] = "hero", paid[self.villain_role]
                elif h < v:
                    res["winner"], res["net"] = "villain", -paid[self.hero_role]
                else:
                    res["winner"], res["net"] = "split", 0.0
        self.result = res

    # -- public API ----------------------------------------------------------
    def state(self) -> dict:
        if self.finished:
            return {"finished": True, "single": self.single, "hero_role": self.hero_role,
                    "hero_combo": self.hero_combo, "result": self.result, "decisions": self.decisions}
        s = decision_state(self.view, self.path, self.hero_role, self.hero_combo)
        s.update(finished=False, single=self.single, session_id=self.id, solve_id=self.solve_id)
        return s

    def act(self, action: str) -> dict:
        """Grade ``action``, advance the hand, and return ``{"feedback": ..., "state": ...}``."""
        if self.finished:
            raise ValueError("hand is already finished")
        cs = self.view.combo_strategy(self.path, self.hero_combo)
        if cs is None:
            raise ValueError("no strategy for your hand at this node")
        actions, freqs = cs
        fb = grade(actions, freqs, action)
        ctx = self.view.context(self.path)
        fb.update(
            solve_id=self.solve_id, mode=self.mode, street=ctx["street"], path=list(self.path),
            hero_role=self.hero_role, combo=self.hero_combo,
            explanation=explain(self.view, self.path, self.hero_combo, fb),
        )
        self.decisions.append(fb)
        if self.on_attempt:
            self.on_attempt(fb)
        self._apply(self.hero_role, action)
        if not self.finished:
            if self.single:
                self._finish("drill")
            else:
                self._advance()
        return {"feedback": fb, "state": self.state()}

    def autoplay_decisions(self) -> list[dict]:
        """Play the whole hand with the *player* also following the solver; return their decision points.

        Used to pick varied, realistic quiz questions (deep nodes included)."""
        points: list[dict] = []
        while not self.finished:
            cs = self.view.combo_strategy(self.path, self.hero_combo)
            if cs is None:
                break
            actions, freqs = cs
            points.append({"path": list(self.path), "role": self.hero_role, "combo": self.hero_combo})
            self._apply(self.hero_role, self.rng.choices(actions, freqs)[0])
            if not self.finished:
                self._advance()
        return points


def generate_question(view: SolveView, rng: random.Random, tries: int = 30) -> dict:
    """Pick one realistic decision (path + role + exact hand) from a solved tree."""
    for _ in range(tries):
        role = rng.choice(["oop", "ip"])
        try:
            s = HandSession("q", "", view, role, rng)
        except ValueError:
            continue
        points = s.autoplay_decisions()
        if points:
            return rng.choice(points)
    raise ValueError("could not generate a question from this solve")
