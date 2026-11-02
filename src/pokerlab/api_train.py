"""Trainer, daily quiz and stats endpoints."""

from __future__ import annotations

import random
import uuid

from fastapi import APIRouter, Body, HTTPException

from .quiz import DailyQuiz, QuizUnavailable
from .strategy import PathError
from .training import HandSession

MAX_SESSIONS = 200


def make_router(ctx) -> APIRouter:
    from .api import parse_path

    r = APIRouter(prefix="/api")
    quiz = DailyQuiz(ctx.progress, ctx.done_ids, ctx.get_view)

    def session(hand_id: str) -> HandSession:
        s = ctx.sessions.get(hand_id)
        if s is None:
            raise HTTPException(404, "unknown or expired hand")
        return s

    @r.post("/trainer/hands", status_code=201)
    def new_hand(body: dict = Body(...)):
        sid = body.get("solve_id")
        if not sid:
            raise HTTPException(422, "solve_id is required")
        view = ctx.get_view(sid)
        rng = random.Random(body.get("seed"))
        path = parse_path(body.get("path", ""))
        single = bool(body.get("single", False)) or bool(body.get("drill", False))
        hero = body.get("hero", "random")
        try:
            if path and hero == "random":                     # drill: the player is whoever acts at that node
                node = view.walk(path)[-1]
                if node.get("node_type") != "action_node":
                    raise ValueError("start_path must end at an action node")
                hero = view.actor(node)
                single = True
            if hero == "random":
                hero = rng.choice(["oop", "ip"])
            if hero not in ("oop", "ip"):
                raise ValueError("hero must be oop, ip or random")
            hand_id = uuid.uuid4().hex[:12]
            s = HandSession(hand_id, sid, view, hero, rng, start_path=path, single=single,
                            on_attempt=_hook(ctx), mode="drill" if single else "play")
        except (ValueError, PathError) as e:
            raise HTTPException(422, str(e))
        ctx.sessions[hand_id] = s
        while len(ctx.sessions) > MAX_SESSIONS:
            ctx.sessions.popitem(last=False)
        return s.state() | {"hand_id": hand_id}

    @r.get("/trainer/hands/{hand_id}")
    def hand_state(hand_id: str):
        return session(hand_id).state()

    @r.post("/trainer/hands/{hand_id}/act")
    def act(hand_id: str, body: dict = Body(...)):
        s = session(hand_id)
        try:
            out = s.act(body.get("action", ""))
        except ValueError as e:
            raise HTTPException(422, str(e))
        out["state"]["hand_id"] = hand_id
        return out

    @r.get("/stats")
    def stats():
        return ctx.progress.stats()

    @r.get("/quiz/today")
    def quiz_today():
        try:
            return quiz.today()
        except QuizUnavailable as e:
            raise HTTPException(409, str(e))

    @r.post("/quiz/today/{idx}/answer")
    def quiz_answer(idx: int, body: dict = Body(...)):
        try:
            return quiz.answer(idx, body.get("action", ""))
        except QuizUnavailable as e:
            raise HTTPException(409, str(e))
        except KeyError:
            raise HTTPException(404, "unknown question")
        except ValueError as e:
            raise HTTPException(422, str(e))

    return r


def _hook(ctx):
    def record(fb: dict) -> None:
        ctx.progress.record_attempt(fb)
    return record
