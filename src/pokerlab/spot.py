"""A ``Spot`` fully describes one solve: board, ranges, stacks, bet tree, accuracy.

Its content hash is the cache key, so identical spots are solved only once.
Units for ``pot`` and ``effective_stack`` are arbitrary chips, as long as they
are consistent (the solver sample uses pot=50, stack=200, i.e. 100bb SPR 4).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from .ranges import CARD_RE, parse_range

STREETS_BY_BOARD_LEN = {3: ("flop", "turn", "river"), 4: ("turn", "river"), 5: ("river",)}

# Percent-of-pot sizes. "allin" is a flag (empty list). "donk" only exists for OOP.
DEFAULT_BET_SIZES: dict[str, dict[str, dict[str, list[int]]]] = {
    p: {
        "flop": {"bet": [50], "raise": [60], "allin": []},
        "turn": {"bet": [50], "raise": [60], "allin": []},
        "river": {"bet": [50], "raise": [60, 100], "allin": []},
    }
    for p in ("oop", "ip")
}
DEFAULT_BET_SIZES["oop"]["river"]["donk"] = [50]


def _default_sizes() -> dict:
    return json.loads(json.dumps(DEFAULT_BET_SIZES))


@dataclass
class Spot:
    board: str  # "Qs,Jh,2h" (3-5 cards)
    ip_range: str
    oop_range: str
    pot: float = 50
    effective_stack: float = 200
    bet_sizes: dict = field(default_factory=_default_sizes)
    allin_threshold: float = 0.67
    accuracy: float = 0.5  # target exploitability, % of pot
    max_iteration: int = 200
    use_isomorphism: bool = True
    dump_rounds: int = 1  # 1 = current street only (small); 2 = also the next street
    threads: int = 0  # 0 = use all cores; not part of the cache key

    # ---- validation -------------------------------------------------------
    def board_cards(self) -> list[str]:
        return [c.strip() for c in self.board.split(",") if c.strip()]

    def validate(self) -> None:
        cards = self.board_cards()
        if len(cards) not in STREETS_BY_BOARD_LEN:
            raise ValueError("board must have 3, 4 or 5 cards")
        if len(set(cards)) != len(cards) or not all(CARD_RE.match(c) for c in cards):
            raise ValueError(f"invalid board: {self.board!r}")
        parse_range(self.ip_range)
        parse_range(self.oop_range)
        if self.pot <= 0 or self.effective_stack <= 0:
            raise ValueError("pot and effective_stack must be positive")
        if not 0 < self.accuracy <= 100:
            raise ValueError("accuracy must be in (0, 100]")
        if not 1 <= self.max_iteration <= 5000:
            raise ValueError("max_iteration must be in [1, 5000]")
        if self.dump_rounds not in (1, 2):
            raise ValueError("dump_rounds must be 1 or 2")
        for player, streets in self.bet_sizes.items():
            if player not in ("oop", "ip"):
                raise ValueError(f"unknown player in bet_sizes: {player!r}")
            for street, kinds in streets.items():
                if street not in ("flop", "turn", "river"):
                    raise ValueError(f"unknown street in bet_sizes: {street!r}")
                for kind, sizes in kinds.items():
                    if kind not in ("bet", "raise", "donk", "allin"):
                        raise ValueError(f"unknown action kind: {kind!r}")
                    if any((not isinstance(s, (int, float))) or s <= 0 for s in sizes):
                        raise ValueError("bet sizes must be positive percentages")

    # ---- identity ---------------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Spot":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def spot_id(self) -> str:
        d = self.to_dict()
        d.pop("threads", None)
        d["board"] = ",".join(self.board_cards())
        blob = json.dumps(d, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    # ---- solver input -----------------------------------------------------
    def solver_config(self, dump_path: str, threads: int) -> str:
        """Render the TexasSolver console script for this spot."""
        self.validate()
        streets = STREETS_BY_BOARD_LEN[len(self.board_cards())]
        lines = [
            f"set_pot {self.pot:g}",
            f"set_effective_stack {self.effective_stack:g}",
            f"set_board {','.join(self.board_cards())}",
            f"set_range_ip {self.ip_range}",
            f"set_range_oop {self.oop_range}",
        ]
        for player in ("oop", "ip"):
            for street in streets:
                for kind, sizes in self.bet_sizes.get(player, {}).get(street, {}).items():
                    if kind == "allin":
                        lines.append(f"set_bet_sizes {player},{street},allin")
                    elif sizes:
                        joined = ",".join(f"{s:g}" for s in sizes)
                        lines.append(f"set_bet_sizes {player},{street},{kind},{joined}")
        lines += [
            f"set_allin_threshold {self.allin_threshold:g}",
            "build_tree",
            f"set_thread_num {threads}",
            f"set_accuracy {self.accuracy:g}",
            f"set_max_iteration {self.max_iteration}",
            "set_print_interval 10",
            f"set_use_isomorphism {1 if self.use_isomorphism else 0}",
            "start_solve",
            f"set_dump_rounds {self.dump_rounds}",
            f"dump_result {dump_path}",
        ]
        return "\n".join(lines) + "\n"
