"""Daily quiz: a fixed set of solver decisions per day, drawn from your solved spots.

Questions are generated from a seed (the date + your solve ids) and then *persisted*, so
the set stays the same all day even if you solve more spots. Answers are final.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date
from typing import Callable

from .progress import ProgressStore
from .strategy import SolveView
from .training import decision_state, explain, generate_question, grade, grade_at

QUIZ_SIZE = 5


class QuizUnavailable(RuntimeError):
    pass


def _seed(day: str, solve_ids: list[str], salt: str = "") -> int:
    return int.from_bytes(hashlib.sha256(f"{day}|{','.join(sorted(solve_ids))}|{salt}".encode()).digest()[:8], "big")


class DailyQuiz:
    def __init__(
        self,
        progress: ProgressStore,
        done_solve_ids: Callable[[], list[str]],
        get_view: Callable[[str], SolveView],
        size: int = QUIZ_SIZE,
    ):
        self.progress, self.done_solve_ids, self.get_view, self.size = progress, done_solve_ids, get_view, size

    # ---- question set ---------------------------------------------------------
    def _make(self, day: str, ids: list[str], salt: str) -> dict:
        rng = random.Random(_seed(day, ids, salt))
        sid = rng.choice(sorted(ids))
        return {"solve_id": sid, **generate_question(self.get_view(sid), rng)}

    def _ensure(self, day: str) -> list[dict]:
        ids = self.done_solve_ids()
        questions = self.progress.quiz_questions(day)
        answers = self.progress.quiz_answers(day)
        if not questions:
            if not ids:
                raise QuizUnavailable("Solve at least one spot first: the quiz is built from your solves.")
            qs = [self._make(day, ids, str(i)) for i in range(self.size)]
            self.progress.save_quiz_questions(day, qs)
            return self.progress.quiz_questions(day)
        # A solve behind an *unanswered* question was deleted: replace just that question.
        changed = False
        for q in questions:
            if q["solve_id"] not in ids and q["idx"] not in answers and ids:
                new = self._make(day, ids, f"{q['idx']}-r")
                self.progress.replace_quiz_question(day, q["idx"], new)
                changed = True
        return self.progress.quiz_questions(day) if changed else questions

    # ---- public ----------------------------------------------------------------
    def today(self, day: str | None = None) -> dict:
        day = day or date.today().isoformat()
        questions = self._ensure(day)
        answers = self.progress.quiz_answers(day)
        ids = set(self.done_solve_ids())
        out = []
        for q in questions:
            item: dict = {"idx": q["idx"], "answered": q["idx"] in answers}
            a = answers.get(q["idx"])
            if q["solve_id"] in ids:
                view = self.get_view(q["solve_id"])
                item["state"] = decision_state(view, q["path"], q["hero_role"], q["combo"])
                item["solve_id"] = q["solve_id"]
                if a:
                    # Frequencies are re-derived for display; the verdict, score and EV loss are the ones stored when
                    # it was answered (re-grading by EV would walk the subtree again on every page load).
                    fb = grade(*view.combo_strategy(q["path"], q["combo"]), a["chosen"])
                    fb.update({k: a[k] for k in ("verdict", "score", "ev_loss", "ev_loss_pot", "basis")})
                    item["result"] = {**fb, "explanation": explain(view, q["path"], q["combo"], fb)}
            elif a:
                item["result"] = {"chosen": a["chosen"], "best": a["best"], "freq": a["freq"], "score": a["score"],
                                  "verdict": a["verdict"], "explanation": "(the solve behind this question was deleted)"}
            out.append(item)
        answered = [i for i in out if i["answered"]]
        scores = [i["result"]["score"] for i in answered if "result" in i and i["result"].get("score") is not None]
        return {
            "day": day,
            "size": len(out),
            "questions": out,
            "answered": len(answered),
            "avg_score": sum(scores) / len(scores) if scores else None,
            "complete": len(answered) == len(out),
            "streak": self.progress.quiz_streak(day, self.size),
        }

    def answer(self, idx: int, chosen: str, day: str | None = None) -> dict:
        day = day or date.today().isoformat()
        questions = self._ensure(day)
        q = next((x for x in questions if x["idx"] == idx), None)
        if q is None:
            raise KeyError("unknown question")
        if idx in self.progress.quiz_answers(day):
            raise ValueError("already answered")
        if q["solve_id"] not in set(self.done_solve_ids()):
            raise ValueError("the solve behind this question was deleted")
        view = self.get_view(q["solve_id"])
        fb = grade_at(view, q["path"], q["combo"], chosen)
        if fb is None:
            raise ValueError("question is no longer valid")
        ctx = view.context(q["path"])
        fb.update(solve_id=q["solve_id"], mode="quiz", street=ctx["street"], path=q["path"],
                  hero_role=q["hero_role"], combo=q["combo"], explanation=explain(view, q["path"], q["combo"], fb))
        attempt_id = self.progress.record_attempt(fb)
        self.progress.save_quiz_answer(day, idx, chosen, attempt_id)
        return {"feedback": fb, "progress": self.today(day)}
