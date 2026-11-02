"""A single background worker that runs solves one at a time.

Solves already saturate the CPU, so a queue of one worker is the right default.
``runner`` is injectable so tests can fake the solver.
"""

from __future__ import annotations

import queue
import threading
from typing import Callable

from .cache import SolveStore
from .solver import SolveOutput, SolverError, SolverUnavailable, run_solve
from .spot import Spot

Runner = Callable[..., SolveOutput]


class JobRunner:
    def __init__(self, store: SolveStore, runner: Runner = run_solve):
        self.store = store
        self.runner = runner
        self._q: "queue.Queue[tuple[str, Spot]]" = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name="pokerlab-solver", daemon=True)
        self._thread.start()

    def submit(self, spot: Spot) -> tuple[str, bool]:
        sid, is_new = self.store.create_or_get(spot)
        if is_new:
            self._q.put((sid, spot))
        return sid, is_new

    def wait_idle(self) -> None:
        self._q.join()

    def _loop(self) -> None:
        while True:
            sid, spot = self._q.get()
            try:
                self.store.set_running(sid)
                out = self.runner(spot, on_progress=lambda it, ex: self.store.set_progress(sid, it, ex))
                self.store.set_done(sid, out.tree, out.iterations, out.exploitability)
            except (SolverError, SolverUnavailable, ValueError) as e:
                self.store.set_error(sid, str(e))
            except Exception as e:  # keep the worker alive no matter what
                self.store.set_error(sid, f"unexpected error: {e!r}")
            finally:
                self._q.task_done()
