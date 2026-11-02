import time

import pytest
from fastapi.testclient import TestClient

from pokerlab.api import create_app
from pokerlab.solver import SolveOutput, SolverError


@pytest.fixture()
def client(tmp_path, river_tree):
    calls = []

    def fake_runner(spot, on_progress=None, **_):
        calls.append(spot.spot_id())
        if spot.board.startswith("As"):
            raise SolverError("boom")
        if on_progress:
            on_progress(11, 3.2)
        return SolveOutput(tree=river_tree, exploitability=0.4, iterations=51, log_tail="")

    app = create_app(data_dir=tmp_path, runner=fake_runner)
    c = TestClient(app)
    c.calls = calls
    c.app_ = app
    return c


def wait_done(client, sid, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        meta = client.get(f"/api/solves/{sid}").json()
        if meta["status"] in ("done", "error"):
            return meta
        time.sleep(0.02)
    raise AssertionError("solve did not finish")


def body(river_spot, **kw):
    d = river_spot.to_dict()
    d.update(kw)
    return d


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_solve_lifecycle_and_viewer_endpoints(client, river_spot):
    r = client.post("/api/solves", json=body(river_spot))
    assert r.status_code == 202
    sid = r.json()["id"]
    meta = wait_done(client, sid)
    assert meta["status"] == "done" and meta["iterations"] == 51
    assert meta["spot"]["board"] == river_spot.board

    node = client.get(f"/api/solves/{sid}/node").json()
    assert node["actor"] == "oop" and "QQ" in node["grid"]

    bet = next(a for a in node["actions"] if a.startswith("BET"))
    child = client.get(f"/api/solves/{sid}/node", params={"path": bet}).json()
    assert child["actor"] == "ip"

    combos = client.get(f"/api/solves/{sid}/combos", params={"hand": "QQ"}).json()
    assert len(combos["combos"]) == 3

    assert any(s["id"] == sid for s in client.get("/api/solves").json())


def test_identical_spot_is_cached_not_resolved(client, river_spot):
    sid = client.post("/api/solves", json=body(river_spot)).json()["id"]
    wait_done(client, sid)
    again = client.post("/api/solves", json=body(river_spot, threads=7)).json()
    assert again["id"] == sid and again["new"] is False
    assert len(client.calls) == 1


def test_errors_are_recorded_and_retryable(client, river_spot):
    b = body(river_spot, board="As,Jh,2h,7d,3c")
    sid = client.post("/api/solves", json=b).json()["id"]
    meta = wait_done(client, sid)
    assert meta["status"] == "error" and "boom" in meta["error"]
    assert client.get(f"/api/solves/{sid}/node").status_code == 409
    again = client.post("/api/solves", json=b).json()
    assert again["new"] is True  # failed solves can be retried


def test_validation_and_not_found(client, river_spot):
    assert client.post("/api/solves", json=body(river_spot, board="Qs,Qs,2h")).status_code == 422
    assert client.get("/api/solves/nope").status_code == 404
    assert client.get("/api/solves/nope/node").status_code == 404


def test_bad_path_is_404(client, river_spot):
    sid = client.post("/api/solves", json=body(river_spot)).json()["id"]
    wait_done(client, sid)
    assert client.get(f"/api/solves/{sid}/node", params={"path": "NOPE"}).status_code == 404


def test_delete(client, river_spot):
    sid = client.post("/api/solves", json=body(river_spot)).json()["id"]
    wait_done(client, sid)
    assert client.delete(f"/api/solves/{sid}").status_code == 200
    assert client.get(f"/api/solves/{sid}").status_code == 404
