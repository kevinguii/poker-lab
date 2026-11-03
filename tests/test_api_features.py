"""Trainer / quiz / stats / presets / hands endpoints, with the solver faked by the hand-built tree."""

import time

import pytest
from fastapi.testclient import TestClient

from pokerlab.api import create_app
from pokerlab.solver import SolveOutput

import hh_samples as hh
import trees


@pytest.fixture()
def client(tmp_path):
    def fake_runner(spot, on_progress=None, **_):
        return SolveOutput(tree=trees.build(), exploitability=0.3, iterations=100, log_tail="")

    return TestClient(create_app(data_dir=tmp_path, runner=fake_runner))


def wait_done(c, sid, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        s = c.get(f"/api/solves/{sid}").json()["status"]
        if s in ("done", "error"):
            return s
        time.sleep(0.02)
    raise AssertionError("not done")


@pytest.fixture()
def sid(client):
    r = client.post("/api/solves", json=trees.spot().to_dict())
    assert r.status_code == 202
    assert wait_done(client, r.json()["id"]) == "done"
    return r.json()["id"]


# ------------------------------------------------------------------ trainer ----
def test_play_a_hand_end_to_end(client, sid):
    r = client.post("/api/trainer/hands", json={"solve_id": sid, "hero": "oop", "seed": 1})
    assert r.status_code == 201
    st = r.json()
    assert st["hero_role"] == "oop" and st["street"] == "flop" and st["pot"] == 50 and not st["finished"]
    assert "villain_combo" not in st
    hid = st["hand_id"]

    out = client.post(f"/api/trainer/hands/{hid}/act", json={"action": st["actions"][0]["action"]}).json()
    fb = out["feedback"]
    assert fb["verdict"] in ("correct", "mix", "mistake") and 0 <= fb["freq"] <= 1 and fb["explanation"]
    # keep going until the hand ends
    state = out["state"]
    for _ in range(10):
        if state["finished"]:
            break
        state = client.post(f"/api/trainer/hands/{hid}/act", json={"action": state["actions"][0]["action"]}).json()["state"]
    assert state["finished"] and state["result"]["villain_combo"] and state["result"]["reason"]
    assert client.get(f"/api/trainer/hands/{hid}").json()["finished"] is True
    assert client.post(f"/api/trainer/hands/{hid}/act", json={"action": "CHECK"}).status_code == 422   # already over
    assert client.get("/api/stats").json()["total"] >= 1


def test_drill_a_specific_node(client, sid):
    r = client.post("/api/trainer/hands", json={"solve_id": sid, "path": "BET 25.000000", "seed": 3})
    st = r.json()
    assert r.status_code == 201 and st["hero_role"] == "ip" and st["to_call"] == 25 and st["pot"] == 75
    out = client.post(f"/api/trainer/hands/{st['hand_id']}/act", json={"action": "CALL"}).json()
    assert out["state"]["finished"] and out["state"]["result"]["reason"] == "drill"
    assert out["feedback"]["mode"] == "drill" and out["feedback"]["path"] == ["BET 25.000000"]


def test_trainer_errors(client, sid):
    assert client.post("/api/trainer/hands", json={}).status_code == 422
    assert client.post("/api/trainer/hands", json={"solve_id": "nope"}).status_code == 404
    assert client.post("/api/trainer/hands", json={"solve_id": sid, "hero": "btn"}).status_code == 422
    assert client.post("/api/trainer/hands", json={"solve_id": sid, "path": "NOPE"}).status_code == 422
    assert client.post("/api/trainer/hands", json={"solve_id": sid, "path": "BET 25.000000|CALL"}).status_code == 422
    assert client.get("/api/trainer/hands/zzz").status_code == 404
    st = client.post("/api/trainer/hands", json={"solve_id": sid, "hero": "oop"}).json()
    assert client.post(f"/api/trainer/hands/{st['hand_id']}/act", json={"action": "FOLD"}).status_code == 422


# --------------------------------------------------------------------- quiz ----
def test_quiz_needs_a_solve_then_works(client):
    r = client.get("/api/quiz/today")
    assert r.status_code == 409 and "Solve at least one spot" in r.json()["detail"]
    s = client.post("/api/solves", json=trees.spot().to_dict()).json()["id"]
    wait_done(client, s)
    q = client.get("/api/quiz/today").json()
    assert q["size"] == 5 and q["answered"] == 0 and all("state" in x for x in q["questions"])
    first = q["questions"][0]
    r = client.post("/api/quiz/today/0/answer", json={"action": first["state"]["actions"][0]["action"]})
    assert r.status_code == 200 and r.json()["progress"]["answered"] == 1
    assert client.post("/api/quiz/today/0/answer", json={"action": "CHECK"}).status_code == 422   # final
    assert client.post("/api/quiz/today/99/answer", json={"action": "CHECK"}).status_code == 404
    again = client.get("/api/quiz/today").json()
    assert again["questions"][0]["result"]["chosen"] == first["state"]["actions"][0]["action"]
    assert [x["state"]["hero_combo"] for x in again["questions"]] == [x["state"]["hero_combo"] for x in q["questions"]]


# ------------------------------------------------------------------ presets ----
def test_preset_crud_and_validation(client):
    names = [p["name"] for p in client.get("/api/presets").json()]
    assert "srp-sample" in names
    ok = client.put("/api/presets/my 3bp", json={"pot_type": "3BP", "ip_range": "AA,KK", "oop_range": "QQ,AKs"})
    assert ok.status_code == 200 and ok.json()["pot_type"] == "3bp"
    assert client.put("/api/presets/bad", json={"pot_type": "srp", "ip_range": "ZZ", "oop_range": "AA"}).status_code == 422
    assert client.put("/api/presets/bad", json={"pot_type": "", "ip_range": "AA", "oop_range": "KK"}).status_code == 422
    assert client.put("/api/presets/srp-sample", json={"pot_type": "srp", "ip_range": "AA", "oop_range": "KK"}).status_code == 422
    assert client.put("/api/presets/%3Cscript%3E", json={"pot_type": "srp", "ip_range": "AA", "oop_range": "KK"}).status_code == 422
    assert client.delete("/api/presets/my 3bp").status_code == 200
    assert client.delete("/api/presets/srp-sample").status_code == 404


# -------------------------------------------------------------------- hands ----
def import_text(c, text):
    r = c.post("/api/hands/import", json={"text": text})
    assert r.status_code == 200
    return r.json()


def test_import_dedupes_and_reports_errors(client):
    a = import_text(client, hh.HAND_A + "\n" + hh.HAND_MULTIWAY)
    assert a["parsed"] == 2 and a["new"] == 2 and a["errors"] == []
    b = import_text(client, hh.HAND_A)
    assert b["new"] == 0 and b["duplicates"] == 1
    assert client.post("/api/hands/import", json={"text": "  "}).status_code == 422
    assert import_text(client, "garbage")["errors"]


def test_hand_list_explains_eligibility(client):
    import_text(client, hh.HAND_A + "\n" + hh.HAND_MULTIWAY + "\n" + hh.HAND_PREFLOP_ONLY)
    by_id = {h["id"]: h for h in client.get("/api/hands").json()}
    assert by_id["900000001"]["eligible"] and by_id["900000001"]["solve"] is None
    assert "3 players" in by_id["900000002"]["reason"] and "flop" in by_id["900000004"]["reason"]
    assert "spot" not in by_id["900000001"]


def test_analyze_a_hand_end_to_end(client):
    client.put("/api/presets/tiny", json={"pot_type": "srp", "ip_range": "AA,QQ", "oop_range": "KK,AQs"})
    import_text(client, hh.HAND_A)
    a = client.get("/api/hands/900000001/analysis").json()
    assert a["eligible"] and a["preset"] == "tiny" and a["solve"] is None and a["evaluation"] is None
    assert a["spot"]["dump_rounds"] == 2

    s = client.post("/api/hands/900000001/solve")
    assert s.status_code == 202 and s.json()["new"] is True
    assert wait_done(client, s.json()["id"]) == "done"
    assert client.post("/api/hands/900000001/solve").json()["new"] is False          # cached

    a = client.get("/api/hands/900000001/analysis").json()
    assert a["solve"]["status"] == "done"
    decs = a["evaluation"]["decisions"]
    assert [d["street"] for d in decs] == ["flop", "turn"] and all(d["status"] == "graded" for d in decs)
    assert 0.9 < a["evaluation"]["summary"]["avg_score"] <= 1.0
    listed = {h["id"]: h for h in client.get("/api/hands").json()}["900000001"]
    assert listed["solve"]["status"] == "done"


def test_unanalysable_hand_cannot_be_solved_and_unknown_ids_404(client):
    import_text(client, hh.HAND_MULTIWAY)
    r = client.post("/api/hands/900000002/solve")
    assert r.status_code == 422 and "players" in r.json()["detail"]
    assert client.get("/api/hands/nope/analysis").status_code == 404
    assert client.delete("/api/hands/900000002").status_code == 200
    assert client.delete("/api/hands/900000002").status_code == 404


def test_analysis_picks_the_preset_by_name(client):
    client.put("/api/presets/other", json={"pot_type": "weird", "ip_range": "KK", "oop_range": "QQ"})
    import_text(client, hh.HAND_A)
    a = client.get("/api/hands/900000001/analysis", params={"preset": "other"}).json()
    assert a["preset"] == "other" and a["spot"]["ip_range"] == "KK"
