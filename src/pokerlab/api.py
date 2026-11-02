"""FastAPI app: JSON API under /api, static front end at /."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from . import __version__
from .cache import SolveStore
from .jobs import JobRunner, Runner
from .progress import ProgressStore
from .solver import find_solver_dir, run_solve
from .spot import DEFAULT_BET_SIZES, Spot
from .strategy import PATH_SEP, PathError, SolveView

WEB_DIR = Path(__file__).resolve().parents[2] / "web"


def parse_path(path: str) -> list[str]:
    return [p for p in path.split(PATH_SEP) if p]


@dataclass
class Ctx:
    """State shared by all routers."""
    store: SolveStore
    progress: ProgressStore
    jobs: JobRunner
    get_view: Callable[[str], SolveView]
    sessions: "OrderedDict" = field(default_factory=OrderedDict)   # live trainer hands

    def done_ids(self) -> list[str]:
        return [m["id"] for m in self.store.list_meta() if m["status"] == "done"]


def create_app(data_dir: str | Path | None = None, runner: Runner = run_solve) -> FastAPI:
    from .api_hands import make_router as hands_router
    from .api_train import make_router as train_router

    app = FastAPI(title="pokerlab", version=__version__)
    store = SolveStore(data_dir)
    progress = ProgressStore(*store.shared())
    jobs = JobRunner(store, runner)
    views: "OrderedDict[str, SolveView]" = OrderedDict()  # tiny LRU: trees are big

    def get_view(sid: str) -> SolveView:
        if sid in views:
            views.move_to_end(sid)
            return views[sid]
        meta = store.get_meta(sid)
        if not meta:
            raise HTTPException(404, "unknown solve")
        if meta["status"] != "done":
            raise HTTPException(409, f"solve is {meta['status']}")
        tree, spot = store.get_tree(sid), store.get_spot(sid)
        if tree is None or spot is None:
            raise HTTPException(404, "result missing")
        views[sid] = SolveView(tree, spot)
        while len(views) > 3:
            views.popitem(last=False)
        return views[sid]

    ctx = Ctx(store, progress, jobs, get_view)
    app.state.ctx = ctx
    app.state.store, app.state.jobs = store, jobs

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__, "solver_available": find_solver_dir() is not None}

    @app.get("/api/defaults")
    def defaults():
        return {"bet_sizes": DEFAULT_BET_SIZES}

    @app.post("/api/solves", status_code=202)
    def create_solve(spot: dict = Body(...)):
        try:
            s = Spot.from_dict(spot)
            s.validate()
        except (ValueError, TypeError) as e:
            raise HTTPException(422, str(e))
        sid, is_new = jobs.submit(s)
        return {"id": sid, "new": is_new, **(store.get_meta(sid) or {})}

    @app.get("/api/solves")
    def list_solves():
        return store.list_meta()

    @app.get("/api/solves/{sid}")
    def solve_meta(sid: str):
        meta = store.get_meta(sid)
        if not meta:
            raise HTTPException(404, "unknown solve")
        spot = store.get_spot(sid)
        return {**meta, "spot": spot.to_dict() if spot else None}

    @app.delete("/api/solves/{sid}")
    def delete_solve(sid: str):
        views.pop(sid, None)
        if not store.delete(sid):
            raise HTTPException(404, "unknown solve")
        return {"deleted": sid}

    @app.get("/api/solves/{sid}/node")
    def node(sid: str, path: str = Query("", description="steps joined with '|' (deals look like @7d)")):
        try:
            return get_view(sid).describe(parse_path(path))
        except PathError as e:
            raise HTTPException(404, str(e))

    @app.get("/api/solves/{sid}/combos")
    def combos(sid: str, hand: str = Query(...), path: str = Query("")):
        try:
            return get_view(sid).combos(parse_path(path), hand)
        except PathError as e:
            raise HTTPException(404, str(e))

    app.include_router(train_router(ctx))
    app.include_router(hands_router(ctx))

    if WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
