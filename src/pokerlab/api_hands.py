"""Presets and hand-history endpoints."""

from __future__ import annotations

import re

from fastapi import APIRouter, Body, HTTPException

from .analysis import evaluate, prepare
from .handhistory import parse_text
from .ranges import parse_range
from .spot import Spot

_NAME_RE = re.compile(r"^[\w .+\-]{1,40}$")


def make_router(ctx) -> APIRouter:
    r = APIRouter(prefix="/api")

    # ---- presets -----------------------------------------------------------
    @r.get("/presets")
    def presets():
        return ctx.progress.list_presets()

    @r.put("/presets/{name}")
    def put_preset(name: str, body: dict = Body(...)):
        if not _NAME_RE.match(name):
            raise HTTPException(422, "name must be 1-40 letters, digits, spaces or . + - _")
        try:
            parse_range(body.get("ip_range", ""))
            parse_range(body.get("oop_range", ""))
            pot_type = (body.get("pot_type") or "").strip().lower()
            if not pot_type:
                raise ValueError("pot_type is required (srp, 3bp, 4bp, limp ...)")
            ctx.progress.save_preset(name, pot_type, body["ip_range"].strip(), body["oop_range"].strip(),
                                     body.get("notes", ""))
        except ValueError as e:
            raise HTTPException(422, str(e))
        return ctx.progress.get_preset(name)

    @r.delete("/presets/{name}")
    def del_preset(name: str):
        if not ctx.progress.delete_preset(name):
            raise HTTPException(404, "no such user preset (built-in presets cannot be deleted)")
        return {"deleted": name}

    # ---- hands -------------------------------------------------------------
    def solve_status(spot_id: str | None) -> dict | None:
        m = ctx.store.get_meta(spot_id) if spot_id else None
        return {"status": m["status"], "exploitability": m["exploitability"], "iterations": m["iterations"],
                "error": m["error"]} if m else None

    def card_info(row: dict, preset: str | None = None) -> dict:
        info = prepare(row["data"], ctx.progress, preset)
        info.pop("spot", None)
        info["solve"] = solve_status(info.get("spot_id"))
        info["time"] = row["data"].get("time")
        return info

    @r.post("/hands/import")
    def import_hands(body: dict = Body(...)):
        text = body.get("text", "")
        if not text.strip():
            raise HTTPException(422, "paste some hand history text")
        hands, errors = parse_text(text)
        new = sum(1 for h in hands if ctx.progress.save_hand(h["id"], h.get("hero"), h))
        return {"parsed": len(hands), "new": new, "duplicates": len(hands) - new, "errors": errors}

    @r.get("/hands")
    def list_hands():
        return [card_info(row) for row in ctx.progress.list_hands()]

    def get_row(hand_id: str) -> dict:
        row = ctx.progress.get_hand(hand_id)
        if not row:
            raise HTTPException(404, "unknown hand")
        return row

    @r.get("/hands/{hand_id}/analysis")
    def analysis(hand_id: str, preset: str | None = None):
        row = get_row(hand_id)
        info = prepare(row["data"], ctx.progress, preset)
        spot = info.get("spot")
        out = {**{k: v for k, v in info.items() if k != "spot"}, "spot": spot,
               "solve": solve_status(info.get("spot_id")), "evaluation": None}
        if info["eligible"] and out["solve"] and out["solve"]["status"] == "done":
            view = ctx.get_view(info["spot_id"])
            out["evaluation"] = evaluate(view, row["data"], info)
        return out

    @r.post("/hands/{hand_id}/solve", status_code=202)
    def solve_hand(hand_id: str, body: dict | None = Body(None)):
        row = get_row(hand_id)
        info = prepare(row["data"], ctx.progress, (body or {}).get("preset"))
        if not info["eligible"]:
            raise HTTPException(422, info["reason"])
        sid, is_new = ctx.jobs.submit(Spot.from_dict(info["spot"]))
        return {"id": sid, "new": is_new, "solve": solve_status(sid)}

    @r.delete("/hands/{hand_id}")
    def del_hand(hand_id: str):
        if not ctx.progress.delete_hand(hand_id):
            raise HTTPException(404, "unknown hand")
        return {"deleted": hand_id}

    return r
