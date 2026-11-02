"""Runs the external TexasSolver console binary and returns its parsed JSON tree."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .spot import Spot

REPO_ROOT = Path(__file__).resolve().parents[2]
_ITER_RE = re.compile(r"^Iter:\s*(\d+)")
_EXPL_RE = re.compile(r"Total exploitability\s+([-\d.eE+]+)")


class SolverUnavailable(RuntimeError):
    pass


class SolverError(RuntimeError):
    pass


@dataclass
class SolveOutput:
    tree: dict
    exploitability: float | None  # % of pot, last value reported by the solver
    iterations: int | None
    log_tail: str


def find_solver_dir() -> Path | None:
    """Directory holding ``console_solver`` and its ``resources`` folder."""
    candidates = []
    if os.environ.get("POKERLAB_SOLVER_DIR"):
        candidates.append(Path(os.environ["POKERLAB_SOLVER_DIR"]))
    candidates.append(REPO_ROOT / "vendor" / "TexasSolver" / "install")
    for c in candidates:
        if (c / "console_solver").is_file():
            return c
    return None


def run_solve(
    spot: Spot,
    solver_dir: Path | None = None,
    timeout: float = 3600,
    on_progress: Callable[[int | None, float | None], None] | None = None,
) -> SolveOutput:
    """Solve ``spot`` and return the parsed result tree.

    The solver is launched with its own directory as cwd because it loads
    lookup tables from a relative ``resources/`` path.
    """
    solver_dir = solver_dir or find_solver_dir()
    if solver_dir is None:
        raise SolverUnavailable("TexasSolver not found. Run scripts/build_solver.sh")
    threads = spot.threads or os.cpu_count() or 2

    with tempfile.TemporaryDirectory(prefix="pokerlab-") as tmp:
        dump_path = os.path.join(tmp, "result.json")
        cfg_path = os.path.join(tmp, "input.txt")
        Path(cfg_path).write_text(spot.solver_config(dump_path, threads))

        proc = subprocess.Popen(
            [str(Path(solver_dir) / "console_solver"), "-i", cfg_path],
            cwd=str(solver_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        tail: list[str] = []
        iters: int | None = None
        expl: float | None = None
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip("\n")
                tail.append(line)
                del tail[:-40]
                if m := _ITER_RE.match(line):
                    iters = int(m.group(1))
                elif m := _EXPL_RE.search(line):
                    expl = float(m.group(1))
                    if on_progress:
                        on_progress(iters, expl)
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise SolverError(f"solver timed out after {timeout:.0f}s")
        finally:
            if proc.poll() is None:
                proc.kill()

        if proc.returncode != 0 or not os.path.exists(dump_path):
            raise SolverError(
                f"solver exited with code {proc.returncode}; last output:\n" + "\n".join(tail[-15:])
            )
        with open(dump_path) as f:
            tree = json.load(f)
        return SolveOutput(tree=tree, exploitability=expl, iterations=iters, log_tail="\n".join(tail))
