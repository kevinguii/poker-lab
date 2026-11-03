"""Trainer engine: play hands against the solver, drill single nodes, grade decisions.

Grading has two bases. When the EV of every action is available (see :mod:`pokerlab.ev`) and exact:

    ev_loss = EV(best action) - EV(chosen)          as a fraction of the pot at the decision
    score   = 1 - loss / 25% of pot, floored at 0
    verdict = "correct"  chosen is a solver action played >= 25% of the time (solve noise can show up as a small
                         EV gap between mixed actions), or loses <= 2% of the pot
              "mix"      loses 2-5% of the pot
              "mistake"  loses more than 5% of the pot

Otherwise (EV too expensive to compute, or only approximate because the solve stops before the river) it falls back to
the solver's frequency for your exact hand:

    score   = freq(chosen) / freq(best)            1.0 when you pick the solver's top action
    verdict = "correct"  chosen is the top action, or the solver takes it >= 25% of the time
              "mix"      the solver takes it 5-25% of the time (acceptable low-frequency play)
              "mistake"  the solver takes it < 5% of the time

``basis`` in the result says which one was used; ``freq`` is always reported.
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Callable

from .evaluator import best_hand, describe
from .strategy import SolveView, action_label, is_deal, parse_action, DEAL

CORRECT_MIN_FREQ = 0.25
MIX_MIN_FREQ = 0.05

EV_CORRECT_MAX_LOSS = 0.02   # fraction of the pot
EV_MIX_MAX_LOSS = 0.05
EV_SCORE_ZERO_AT = 0.25      # a loss of this fraction of the pot scores 0

AttemptHook = Callable[[dict], None]


# ---------------------------------------------------------------- grading ----
def grade(actions: list[str], freqs: list[float], chosen: str,
          evs: list[float | None] | None = None, pot: float | None = None, ev_exact: bool = True) -> dict:
    """Grade ``chosen``. Pass ``evs`` (EV per action) and ``pot`` to grade by EV loss; see the module docstring."""
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
    out = {
        "chosen": chosen,
        "best": best,
        "freq": f,
        "score": score,
        "verdict": verdict,
        "basis": "frequency",
        "ev_loss": None,
        "ev_loss_pot": None,
        "ev_best": None,
        "evs": None,
        "actions": actions,
        "freqs": list(freqs),
        "labels": [action_label(a) for a in actions],
    }
    known = [e for e in (evs or []) if e is not None]
    if evs and ev_exact and pot and pot > 0 and known and evs[actions.index(chosen)] is not None:
        top = max(known)
        loss = max(0.0, top - evs[actions.index(chosen)])
        frac = loss / pot
        out.update(
            basis="ev",
            evs=list(evs),
            ev_best=actions[evs.index(top)],
            ev_loss=loss,
            ev_loss_pot=frac,
            score=max(0.0, 1.0 - frac / EV_SCORE_ZERO_AT),
            verdict="correct" if chosen == best or f >= CORRECT_MIN_FREQ or frac <= EV_CORRECT_MAX_LOSS
            else "mix" if frac <= EV_MIX_MAX_LOSS else "mistake",
        )
    elif evs:
        out["evs"] = list(evs)  # shown for information even when it is not used for the verdict
    return out


def grade_at(view: SolveView, path: list[str], combo: str, chosen: str) -> dict | None:
    """Grade ``chosen`` for an exact hand at a node of ``view`` (EV when available); None if the hand has no strategy."""
    cs = view.combo_strategy(path, combo)
    if cs is None:
        return None
    ev = view.combo_evs(path, combo)
    pot = view.context(path)["pot"]
    return grade(cs[0], cs[1], chosen, *( (ev[0], pot, ev[1]) if ev else (None, None) ))


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
        fb = grade_at(self.view, self.path, self.hero_combo, action)
        if fb is None:
            raise ValueError("no strategy for your hand at this node")
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
