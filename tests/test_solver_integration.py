"""Runs the real solver. Skipped automatically if scripts/build_solver.sh hasn't been run."""

import math

import pytest

from pokerlab.solver import find_solver_dir, run_solve
from pokerlab.strategy import SolveView

pytestmark = [
    pytest.mark.solver,
    pytest.mark.skipif(find_solver_dir() is None, reason="TexasSolver not built"),
]


def test_real_river_solve_end_to_end(river_spot):
    progress = []
    out = run_solve(river_spot, on_progress=lambda it, ex: progress.append((it, ex)))
    assert out.exploitability is not None and out.exploitability < 1.0  # % of pot
    assert progress, "expected progress callbacks"

    view = SolveView(out.tree, river_spot)
    d = view.describe([])
    assert math.isclose(sum(d["overall"]), 1.0, abs_tol=1e-6)
    # Solver was run on the same spot as the fixture, so the shape must match.
    assert d["actions"][0] == "CHECK" and d["actor"] == "oop"
