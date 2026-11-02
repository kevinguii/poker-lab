"""SQLite store for solve metadata and (gzip-compressed) result trees.

One file, no server. Default location: ``./data/pokerlab.db`` (override with
``POKERLAB_DATA``). Identical spots hash to the same id and are solved once.
"""

from __future__ import annotations

import gzip
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

from .spot import Spot

_SCHEMA = """
CREATE TABLE IF NOT EXISTS solves (
  id            TEXT PRIMARY KEY,
  spot_json     TEXT NOT NULL,
  status        TEXT NOT NULL,           -- queued | running | done | error
  created_at    REAL NOT NULL,
  finished_at   REAL,
  exploitability REAL,
  iterations    INTEGER,
  error         TEXT,
  result        BLOB
);
"""


def default_data_dir() -> Path:
    return Path(os.environ.get("POKERLAB_DATA", "data"))


class SolveStore:
    def __init__(self, data_dir: str | Path | None = None):
        self.dir = Path(data_dir) if data_dir else default_data_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.dir / "pokerlab.db", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(_SCHEMA)
            # Anything left "running" from a previous process can never finish.
            self._db.execute(
                "UPDATE solves SET status='error', error='interrupted (app restarted)' "
                "WHERE status IN ('queued','running')"
            )
            self._db.commit()

    # ---- writes -----------------------------------------------------------
    def create_or_get(self, spot: Spot) -> tuple[str, bool]:
        """Insert a queued solve unless one exists. Returns ``(id, is_new)``.

        A previous *error* is retried (the row is reset to queued)."""
        sid = spot.spot_id()
        with self._lock:
            row = self._db.execute("SELECT status FROM solves WHERE id=?", (sid,)).fetchone()
            if row and row["status"] != "error":
                return sid, False
            self._db.execute(
                "INSERT OR REPLACE INTO solves (id, spot_json, status, created_at) VALUES (?,?,?,?)",
                (sid, json.dumps(spot.to_dict()), "queued", time.time()),
            )
            self._db.commit()
        return sid, True

    def set_running(self, sid: str) -> None:
        self._update(sid, status="running")

    def set_progress(self, sid: str, iterations: int | None, exploitability: float | None) -> None:
        self._update(sid, iterations=iterations, exploitability=exploitability)

    def set_done(self, sid: str, tree: dict, iterations: int | None, exploitability: float | None) -> None:
        blob = gzip.compress(json.dumps(tree, separators=(",", ":")).encode(), compresslevel=6)
        self._update(
            sid, status="done", result=blob, iterations=iterations,
            exploitability=exploitability, finished_at=time.time(), error=None,
        )

    def set_error(self, sid: str, message: str) -> None:
        self._update(sid, status="error", error=message, finished_at=time.time())

    def delete(self, sid: str) -> bool:
        with self._lock:
            cur = self._db.execute("DELETE FROM solves WHERE id=?", (sid,))
            self._db.commit()
            return cur.rowcount > 0

    def _update(self, sid: str, **cols) -> None:
        sets = ", ".join(f"{k}=?" for k in cols)
        with self._lock:
            self._db.execute(f"UPDATE solves SET {sets} WHERE id=?", (*cols.values(), sid))
            self._db.commit()

    # ---- reads ------------------------------------------------------------
    @staticmethod
    def _meta(row: sqlite3.Row) -> dict:
        spot = json.loads(row["spot_json"])
        return {
            "id": row["id"],
            "status": row["status"],
            "board": spot["board"],
            "pot": spot["pot"],
            "effective_stack": spot["effective_stack"],
            "created_at": row["created_at"],
            "finished_at": row["finished_at"],
            "exploitability": row["exploitability"],
            "iterations": row["iterations"],
            "error": row["error"],
        }

    def get_meta(self, sid: str) -> dict | None:
        with self._lock:
            row = self._db.execute(
                "SELECT id, spot_json, status, created_at, finished_at, exploitability, iterations, error "
                "FROM solves WHERE id=?", (sid,),
            ).fetchone()
        return self._meta(row) if row else None

    def list_meta(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, spot_json, status, created_at, finished_at, exploitability, iterations, error "
                "FROM solves ORDER BY created_at DESC"
            ).fetchall()
        return [self._meta(r) for r in rows]

    def get_spot(self, sid: str) -> Spot | None:
        with self._lock:
            row = self._db.execute("SELECT spot_json FROM solves WHERE id=?", (sid,)).fetchone()
        return Spot.from_dict(json.loads(row["spot_json"])) if row else None

    def get_tree(self, sid: str) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT result FROM solves WHERE id=?", (sid,)).fetchone()
        if not row or row["result"] is None:
            return None
        return json.loads(gzip.decompress(row["result"]))
