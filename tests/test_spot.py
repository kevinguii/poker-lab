import pytest

from pokerlab.spot import Spot


def make(**kw) -> Spot:
    base = dict(board="Qs,Jh,2h", ip_range="AA,KK", oop_range="QQ,JJ")
    base.update(kw)
    return Spot(**base)


def test_spot_id_is_stable_and_ignores_threads():
    assert make().spot_id() == make().spot_id()
    assert make(threads=1).spot_id() == make(threads=8).spot_id()


def test_spot_id_changes_with_inputs():
    base = make().spot_id()
    assert make(board="Qs,Jh,3h").spot_id() != base
    assert make(pot=60).spot_id() != base
    assert make(oop_range="QQ").spot_id() != base


def test_board_whitespace_does_not_change_id():
    assert make(board="Qs, Jh, 2h").spot_id() == make(board="Qs,Jh,2h").spot_id()


def test_roundtrip_dict():
    s = make(pot=70)
    assert Spot.from_dict(s.to_dict()).spot_id() == s.spot_id()


@pytest.mark.parametrize(
    "kw",
    [
        dict(board="Qs,Jh"),                # too few cards
        dict(board="Qs,Qs,2h"),             # duplicate
        dict(board="Qs,Jh,1h"),             # bad rank
        dict(ip_range="ZZ"),                # bad range
        dict(pot=0),
        dict(accuracy=0),
        dict(max_iteration=0),
        dict(dump_rounds=3),
        dict(bet_sizes={"oop": {"flop": {"bet": [-5]}}}),
        dict(bet_sizes={"btn": {}}),
    ],
)
def test_validation_rejects(kw):
    with pytest.raises(ValueError):
        make(**kw).validate()


def test_solver_config_contents():
    cfg = make().solver_config("/tmp/out.json", threads=3)
    lines = cfg.splitlines()
    assert lines[0] == "set_pot 50" and "set_board Qs,Jh,2h" in lines
    assert "set_bet_sizes oop,flop,bet,50" in lines
    assert "set_bet_sizes ip,river,raise,60,100" in lines
    assert "set_bet_sizes oop,river,donk,50" in lines
    assert "set_thread_num 3" in lines
    # solve happens after the tree is built, dump comes last
    assert lines.index("build_tree") < lines.index("start_solve") < lines.index("dump_result /tmp/out.json")
    assert lines[-1] == "dump_result /tmp/out.json"


def test_river_board_only_configures_river_sizes():
    cfg = make(board="Qs,Jh,2h,7d,3c").solver_config("/tmp/o.json", 1)
    assert ",flop," not in cfg and ",turn," not in cfg and ",river," in cfg
