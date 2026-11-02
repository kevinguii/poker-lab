"""PokerStars-format hand history parser (cash games and tournaments, No-Limit Hold'em).

Produces plain JSON-serialisable dicts. All amounts stay in the hand's own currency/chips;
:mod:`pokerlab.analysis` converts to big blinds.
"""

from __future__ import annotations

import re

_CARD = r"[2-9TJQKA][shdc]"
_SPLIT = re.compile(r"(?m)^(?=PokerStars (?:Zoom )?(?:Hand|Game) #\d+)")
_HEADER = re.compile(r"^PokerStars (?:Zoom )?(?:Hand|Game) #(\d+):(.*)$")
_BLINDS = re.compile(r"\(([^\s/()]+)/([^\s/()]+)(?: [A-Z]{3})?\)")
_BUTTON = re.compile(r"Seat #(\d+) is the button")
_SEAT = re.compile(r"^Seat (\d+): (.+?) \(([^\s]+) in chips")
_POST = re.compile(r"^(.+?): posts (small blind|big blind|the ante|small & big blinds) ([^\s]+)")
_DEALT = re.compile(rf"^Dealt to (.+?) \[({_CARD}) ({_CARD})\]")
_FLOP = re.compile(rf"^\*\*\* FLOP \*\*\* \[({_CARD}) ({_CARD}) ({_CARD})\]")
_TURN = re.compile(rf"^\*\*\* TURN \*\*\* \[.+?\] \[({_CARD})\]")
_RIVER = re.compile(rf"^\*\*\* RIVER \*\*\* \[.+?\] \[({_CARD})\]")
_ACTION = re.compile(r"^(.+?): (folds|checks|calls|bets|raises)(?: ([^\s]+))?(?: to ([^\s]+))?")
_UNCALLED = re.compile(r"^Uncalled bet \(([^)]+)\) returned to (.+)$")
_TIME = re.compile(r"- (\d{4}/\d\d/\d\d \d\d:\d\d:\d\d)")


class ParseError(ValueError):
    pass


def money(token: str) -> float:
    cleaned = re.sub(r"[^\d.]", "", token.replace(",", ""))
    if not cleaned:
        raise ParseError(f"bad amount: {token!r}")
    return float(cleaned)


def split_hands(text: str) -> list[str]:
    return [c.strip() for c in _SPLIT.split(text.replace("\r\n", "\n")) if c.strip().startswith("PokerStars")]


def parse_hand(chunk: str) -> dict:
    lines = [ln.rstrip() for ln in chunk.splitlines() if ln.strip()]
    m = _HEADER.match(lines[0])
    if not m:
        raise ParseError("not a PokerStars hand")
    hand_id, rest = m.group(1), m.group(2)
    bm = _BLINDS.search(rest)
    if not bm:
        raise ParseError("could not read the blinds from the header")
    sb, bb = money(bm.group(1)), money(bm.group(2))
    if bb <= 0:
        raise ParseError("big blind is zero")
    tm = _TIME.search(rest)

    out: dict = {
        "id": hand_id, "site": "pokerstars", "sb": sb, "bb": bb, "time": tm.group(1) if tm else None,
        "button": None, "seats": [], "hero": None, "hero_cards": None,
        "board": {"flop": None, "turn": None, "river": None}, "actions": [], "antes": {},
    }
    street = "preflop"
    seen_hole = False
    for ln in lines[1:]:
        if ln.startswith("***"):
            if ln.startswith("*** HOLE CARDS"):
                seen_hole = True
            elif (fm := _FLOP.match(ln)):
                street, out["board"]["flop"] = "flop", list(fm.groups())
            elif (tm2 := _TURN.match(ln)):
                street, out["board"]["turn"] = "turn", tm2.group(1)
            elif (rm := _RIVER.match(ln)):
                street, out["board"]["river"] = "river", rm.group(1)
            elif ln.startswith("*** SHOW DOWN") or ln.startswith("*** SUMMARY"):
                break
            continue
        if (b := _BUTTON.search(ln)) and ln.startswith("Table"):
            out["button"] = int(b.group(1))
        elif (s := _SEAT.match(ln)) and not seen_hole and street == "preflop":
            out["seats"].append({"seat": int(s.group(1)), "name": s.group(2), "stack": money(s.group(3))})
        elif (d := _DEALT.match(ln)):
            out["hero"], out["hero_cards"] = d.group(1), [d.group(2), d.group(3)]
        elif (p := _POST.match(ln)):
            name, kind, amt = p.group(1), p.group(2), money(p.group(3))
            if kind == "the ante":
                out["antes"][name] = out["antes"].get(name, 0.0) + amt
            else:
                out["actions"].append({"street": "preflop", "player": name, "kind": "posts", "amount": amt, "to": None})
        elif (u := _UNCALLED.match(ln)):
            out["actions"].append({"street": street, "player": u.group(2), "kind": "uncalled", "amount": money(u.group(1)), "to": None})
        elif (a := _ACTION.match(ln)):
            kind = a.group(2)
            out["actions"].append({
                "street": street, "player": a.group(1), "kind": kind,
                "amount": money(a.group(3)) if a.group(3) else None,
                "to": money(a.group(4)) if a.group(4) else None,
                "allin": "and is all-in" in ln,
            })
    if len(out["seats"]) < 2:
        raise ParseError("fewer than two seats found")
    if out["button"] is None:
        raise ParseError("button seat not found")
    return out


def parse_text(text: str) -> tuple[list[dict], list[str]]:
    """Parse a whole file. Returns ``(hands, errors)``; one bad hand never loses the others."""
    hands, errors = [], []
    for chunk in split_hands(text):
        try:
            hands.append(parse_hand(chunk))
        except ParseError as e:
            errors.append(f"{chunk.splitlines()[0][:60]}: {e}")
    if not hands and not errors:
        errors.append("no PokerStars hands found (only the PokerStars text format is supported)")
    return hands, errors
