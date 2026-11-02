"""Everything about *you* (as opposed to solves): attempts, daily quiz, presets, imported hands.

Shares the SQLite connection of :class:`SolveStore`, so the whole app state is one file.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import date, timedelta

_SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        REAL NOT NULL,
  solve_id  TEXT NOT NULL,
  mode      TEXT NOT NULL,              -- play | drill | quiz
  street    TEXT NOT NULL,
  path      TEXT NOT NULL,              -- JSON list of steps
  hero_role TEXT NOT NULL,
  combo     TEXT NOT NULL,
  chosen    TEXT NOT NULL,
  best      TEXT NOT NULL,
  freq      REAL NOT NULL,
  score     REAL NOT NULL,
  verdict   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quiz_questions (
  day       TEXT NOT NULL,
  idx       INTEGER NOT NULL,
  solve_id  TEXT NOT NULL,
  path      TEXT NOT NULL,
  hero_role TEXT NOT NULL,
  combo     TEXT NOT NULL,
  PRIMARY KEY (day, idx)
);
CREATE TABLE IF NOT EXISTS quiz_answers (
  day       TEXT NOT NULL,
  idx       INTEGER NOT NULL,
  chosen    TEXT NOT NULL,
  attempt_id INTEGER,
  ts        REAL NOT NULL,
  PRIMARY KEY (day, idx)
);
CREATE TABLE IF NOT EXISTS presets (
  name      TEXT PRIMARY KEY,
  pot_type  TEXT NOT NULL,              -- srp | 3bp | 4bp | limp | any custom tag
  ip_range  TEXT NOT NULL,
  oop_range TEXT NOT NULL,
  notes     TEXT NOT NULL DEFAULT '',
  builtin   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS hands (
  id          TEXT PRIMARY KEY,
  imported_at REAL NOT NULL,
  hero        TEXT,
  json        TEXT NOT NULL
);
"""

# The only ranges shipped: the example from TexasSolver's own README (a single-raised pot).
# They are a starting point, not a claim about correct ranges. Replace with your own.
SAMPLE_SRP = {
    "name": "srp-sample",
    "pot_type": "srp",
    "oop_range": "QQ:0.5,JJ:0.75,TT,99,88,77,66,55,44,33,22,AKo:0.25,AQs,AQo:0.75,AJs,AJo:0.75,ATs,ATo:0.75,A9s,A8s,"
                 "A7s,A6s,A5s,A4s,A3s,A2s,KQ,KJ,KTs,KTo:0.5,K9s,K8s,K7s,K6s,K5s,K4s:0.5,K3s:0.5,K2s:0.5,QJ,QTs,Q9s,"
                 "Q8s,Q7s,JTs,JTo:0.5,J9s,J8s,T9s,T8s,T7s,98s,97s,96s,87s,86s,76s,75s,65s,64s,54s,53s,43s",
    "ip_range": "AA,KK,QQ,JJ,TT,99:0.75,88:0.75,77:0.5,66:0.25,55:0.25,AK,AQs,AQo:0.75,AJs,AJo:0.5,ATs:0.75,A6s:0.25,"
                "A5s:0.75,A4s:0.75,A3s:0.5,A2s:0.5,KQs,KQo:0.5,KJs,KTs:0.75,K5s:0.25,K4s:0.25,QJs:0.75,QTs:0.75,"
                "Q9s:0.5,JTs:0.75,J9s:0.75,J8s:0.75,T9s:0.75,T8s:0.75,T7s:0.75,98s:0.75,97s:0.75,96s:0.5,87s:0.75,"
                "86s:0.5,85s:0.5,76s:0.75,75s:0.5,65s:0.75,64s:0.5,54s:0.75,53s:0.5,43s:0.5",
    "notes": "Example ranges from the TexasSolver README. Replace with your own for real study.",
}


class ProgressStore:
    def __init__(self, db: sqlite3.Connection, lock: threading.Lock):
        self._db, self._lock = db, lock
        with self._lock:
            self._db.executescript(_SCHEMA)
            if not self._db.execute("SELECT 1 FROM presets WHERE name=?", (SAMPLE_SRP["name"],)).fetchone():
                self._db.execute(
                    "INSERT INTO presets (name, pot_type, ip_range, oop_range, notes, builtin) VALUES (?,?,?,?,?,1)",
                    (SAMPLE_SRP["name"], SAMPLE_SRP["pot_type"], SAMPLE_SRP["ip_range"], SAMPLE_SRP["oop_range"],
                     SAMPLE_SRP["notes"]),
                )
            self._db.commit()

    def _rows(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    def _one(self, sql: str, args: tuple = ()) -> dict | None:
        rows = self._rows(sql, args)
        return rows[0] if rows else None

    # ---- attempts / stats -------------------------------------------------
    def record_attempt(self, fb: dict) -> int:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO attempts (ts, solve_id, mode, street, path, hero_role, combo, chosen, best, freq, score, verdict)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (time.time(), fb["solve_id"], fb["mode"], fb["street"], json.dumps(fb["path"]), fb["hero_role"],
                 fb["combo"], fb["chosen"], fb["best"], fb["freq"], fb["score"], fb["verdict"]),
            )
            self._db.commit()
            return int(cur.lastrowid)

    def stats(self, days: int = 14) -> dict:
        overall = self._one(
            "SELECT COUNT(*) AS n, AVG(score) AS avg_score,"
            " AVG(verdict='correct') AS correct, AVG(verdict='mix') AS mix, AVG(verdict='mistake') AS mistake FROM attempts"
        ) or {}
        n = overall.get("n") or 0
        by_street = self._rows(
            "SELECT street, COUNT(*) AS n, AVG(score) AS avg_score, AVG(verdict='mistake') AS mistake "
            "FROM attempts GROUP BY street ORDER BY n DESC"
        )
        by_solve = self._rows(
            "SELECT a.solve_id, COUNT(*) AS n, AVG(a.score) AS avg_score, AVG(a.verdict='mistake') AS mistake "
            "FROM attempts a GROUP BY a.solve_id ORDER BY n DESC LIMIT 20"
        )
        recent = self._rows(
            "SELECT ts, solve_id, street, path, hero_role, combo, chosen, best, freq FROM attempts "
            "WHERE verdict='mistake' ORDER BY id DESC LIMIT 15"
        )
        for r in recent:
            r["path"] = json.loads(r["path"])
        since = time.time() - days * 86400
        daily = self._rows(
            "SELECT strftime('%Y-%m-%d', ts, 'unixepoch', 'localtime') AS day, COUNT(*) AS n, AVG(score) AS avg_score "
            "FROM attempts WHERE ts >= ? GROUP BY day ORDER BY day", (since,)
        )
        return {
            "total": n,
            "avg_score": overall.get("avg_score") if n else None,
            "correct": overall.get("correct") if n else None,
            "mix": overall.get("mix") if n else None,
            "mistake": overall.get("mistake") if n else None,
            "by_street": by_street,
            "by_solve": by_solve,
            "recent_mistakes": recent,
            "daily": daily,
        }

    # ---- daily quiz ----------------------------------------------------------
    def quiz_questions(self, day: str) -> list[dict]:
        rows = self._rows("SELECT * FROM quiz_questions WHERE day=? ORDER BY idx", (day,))
        for r in rows:
            r["path"] = json.loads(r["path"])
        return rows

    def save_quiz_questions(self, day: str, questions: list[dict]) -> None:
        with self._lock:
            self._db.execute("DELETE FROM quiz_answers WHERE day=?", (day,))
            self._db.execute("DELETE FROM quiz_questions WHERE day=?", (day,))
            for i, q in enumerate(questions):
                self._db.execute(
                    "INSERT INTO quiz_questions (day, idx, solve_id, path, hero_role, combo) VALUES (?,?,?,?,?,?)",
                    (day, i, q["solve_id"], json.dumps(q["path"]), q["role"], q["combo"]),
                )
            self._db.commit()

    def replace_quiz_question(self, day: str, idx: int, q: dict) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO quiz_questions (day, idx, solve_id, path, hero_role, combo) VALUES (?,?,?,?,?,?)",
                (day, idx, q["solve_id"], json.dumps(q["path"]), q["role"], q["combo"]),
            )
            self._db.commit()

    def quiz_answers(self, day: str) -> dict[int, dict]:
        return {r["idx"]: r for r in self._rows(
            "SELECT qa.idx, qa.chosen, qa.attempt_id, a.best, a.freq, a.score, a.verdict "
            "FROM quiz_answers qa LEFT JOIN attempts a ON a.id = qa.attempt_id WHERE qa.day=?", (day,))}

    def save_quiz_answer(self, day: str, idx: int, chosen: str, attempt_id: int) -> bool:
        """False if this question was already answered (answers are final)."""
        with self._lock:
            try:
                self._db.execute(
                    "INSERT INTO quiz_answers (day, idx, chosen, attempt_id, ts) VALUES (?,?,?,?,?)",
                    (day, idx, chosen, attempt_id, time.time()),
                )
            except sqlite3.IntegrityError:
                return False
            self._db.commit()
            return True

    def quiz_streak(self, today: str, required: int) -> int:
        """Consecutive days (ending today, or yesterday if today is unfinished) with every question answered."""
        done = {r["day"] for r in self._rows(
            "SELECT day FROM quiz_answers GROUP BY day HAVING COUNT(*) >= ?", (required,))}
        d = date.fromisoformat(today)
        if today not in done:
            d -= timedelta(days=1)
        streak = 0
        while d.isoformat() in done:
            streak += 1
            d -= timedelta(days=1)
        return streak

    # ---- presets ---------------------------------------------------------------
    def list_presets(self) -> list[dict]:
        return self._rows("SELECT * FROM presets ORDER BY builtin DESC, name")

    def get_preset(self, name: str) -> dict | None:
        return self._one("SELECT * FROM presets WHERE name=?", (name,))

    def preset_for_pot_type(self, pot_type: str) -> dict | None:
        # user presets win over the built-in sample
        return self._one("SELECT * FROM presets WHERE pot_type=? ORDER BY builtin ASC, name LIMIT 1", (pot_type,))

    def save_preset(self, name: str, pot_type: str, ip_range: str, oop_range: str, notes: str = "") -> None:
        with self._lock:
            row = self._db.execute("SELECT builtin FROM presets WHERE name=?", (name,)).fetchone()
            if row and row["builtin"]:
                raise ValueError("built-in presets cannot be overwritten; save under a new name")
            self._db.execute(
                "INSERT OR REPLACE INTO presets (name, pot_type, ip_range, oop_range, notes, builtin) VALUES (?,?,?,?,?,0)",
                (name, pot_type, ip_range, oop_range, notes),
            )
            self._db.commit()

    def delete_preset(self, name: str) -> bool:
        with self._lock:
            cur = self._db.execute("DELETE FROM presets WHERE name=? AND builtin=0", (name,))
            self._db.commit()
            return cur.rowcount > 0

    # ---- imported hands ---------------------------------------------------------
    def save_hand(self, hand_id: str, hero: str | None, data: dict) -> bool:
        """True if newly inserted, False if the hand was already imported."""
        with self._lock:
            if self._db.execute("SELECT 1 FROM hands WHERE id=?", (hand_id,)).fetchone():
                return False
            self._db.execute("INSERT INTO hands (id, imported_at, hero, json) VALUES (?,?,?,?)",
                             (hand_id, time.time(), hero, json.dumps(data)))
            self._db.commit()
            return True

    def list_hands(self) -> list[dict]:
        rows = self._rows("SELECT id, imported_at, hero, json FROM hands ORDER BY imported_at DESC, id DESC")
        for r in rows:
            r["data"] = json.loads(r.pop("json"))
        return rows

    def get_hand(self, hand_id: str) -> dict | None:
        r = self._one("SELECT id, imported_at, hero, json FROM hands WHERE id=?", (hand_id,))
        if r:
            r["data"] = json.loads(r.pop("json"))
        return r

    def delete_hand(self, hand_id: str) -> bool:
        with self._lock:
            cur = self._db.execute("DELETE FROM hands WHERE id=?", (hand_id,))
            self._db.commit()
            return cur.rowcount > 0
