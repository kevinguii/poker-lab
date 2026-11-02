"use strict";
/* Shared helpers. Everything hangs off one global namespace, PL. No build step. */
const PL = {
  RANKS: "AKQJT98765432",
  SEP: "|",
  SUIT: { s: "♠", h: "♥", d: "♦", c: "♣" },
  hooks: {},          // tabs register refresh functions here
};

PL.$ = (sel, root = document) => root.querySelector(sel);
PL.$$ = (sel, root = document) => [...root.querySelectorAll(sel)];
PL.el = (tag, props = {}, ...kids) => {
  const n = Object.assign(document.createElement(tag), props);
  kids.flat().forEach((k) => { if (k !== null && k !== undefined && k !== false) n.append(k); });
  return n;
};

PL.api = async (url, opts) => {
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (_) {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.json();
};
PL.post = (url, body) => PL.api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });
PL.put = (url, body) => PL.api(url, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

/* ---------- formatting ---------- */
PL.num = (x) => (Math.round(x * 100) / 100).toString();
PL.pct = (x) => (x * 100).toFixed(x > 0.9995 || x < 0.0005 ? 0 : 1) + "%";
PL.amount = (a) => { const m = a.match(/([\d.]+)$/); return m ? parseFloat(m[1]) : 0; };
PL.isAggro = (a) => /^(BET|RAISE|DONK)/.test(a);
PL.label = (a) => {
  if (a.startsWith("@")) return `Deal ${a.slice(1)}`;
  const [kind, amt] = a.split(" ");
  const k = kind[0] + kind.slice(1).toLowerCase();
  return amt ? `${k} ${parseFloat(amt).toString()}` : k;
};

/* ---------- colours: fold blue, check/call green, bets red (darker = bigger) ---------- */
PL.colours = (actions) => {
  const aggro = actions.filter(PL.isAggro).sort((x, y) => PL.amount(x) - PL.amount(y));
  const map = {};
  actions.forEach((a) => {
    if (a === "FOLD") map[a] = "#3b82c4";
    else if (a === "CHECK" || a === "CALL") map[a] = "#3fa66b";
    else {
      const i = aggro.indexOf(a);
      const t = aggro.length > 1 ? i / (aggro.length - 1) : 0.3;
      map[a] = `hsl(2 70% ${62 - t * 28}%)`;
    }
  });
  return map;
};

/* ---------- cards ---------- */
PL.cardEl = (card) => {
  const red = card[1] === "h" || card[1] === "d";
  return PL.el("span", { className: "card" + (red ? " red" : ""), title: card }, card[0] === "T" ? "10" : card[0], PL.SUIT[card[1]]);
};
PL.cardsEl = (cards) => PL.el("span", { className: "cards" }, cards.map(PL.cardEl));
PL.comboCards = (combo) => [combo.slice(0, 2), combo.slice(2)];

/* ---------- solver mix: stacked bar + legend ---------- */
PL.mixBars = (actions, freqs, chosen) => {
  const cols = PL.colours(actions);
  const bar = PL.el("div", { className: "mixbar" });
  actions.forEach((a, i) => {
    if (freqs[i] > 0.0005) bar.append(PL.el("div", { style: `width:${freqs[i] * 100}%;background:${cols[a]}`, title: `${PL.label(a)} ${PL.pct(freqs[i])}` }));
  });
  const legend = PL.el("div", { className: "mixlegend" }, actions.map((a, i) =>
    PL.el("span", { className: "leg" + (a === chosen ? " chosen" : "") },
      PL.el("span", { className: "sw", style: `background:${cols[a]}` }), `${PL.label(a)} ${PL.pct(freqs[i])}`)));
  return PL.el("div", {}, bar, legend);
};

/* ---------- a decision (shared by Train and Daily quiz) ---------- */
PL.historyText = (history) => {
  const byStreet = {};
  history.forEach((h) => {
    const s = h.street;
    (byStreet[s] = byStreet[s] || []).push(h.deal ? `deal ${h.deal}` : `${h.actor.toUpperCase()} ${h.label.toLowerCase()}`);
  });
  return Object.entries(byStreet).map(([s, items]) => `${s}: ${items.join(", ")}`).join("  ·  ");
};

PL.decisionView = (st, onAct, disabled = false) => {
  const money = PL.num;
  const root = PL.el("div", { className: "decision" });
  root.append(
    PL.el("div", { className: "row-line" },
      PL.el("span", { className: "tag" }, st.street),
      PL.cardsEl(st.board),
    ),
    PL.el("div", { className: "row-line" },
      PL.el("span", { className: "tag you" }, `You · ${st.hero_role.toUpperCase()}`),
      PL.cardsEl(PL.comboCards(st.hero_combo)),
      st.hero_hand ? PL.el("span", { className: "muted" }, st.hero_hand) : null,
    ),
    PL.el("div", { className: "muted" },
      `Pot ${money(st.pot)} · ${st.to_call > 0 ? `to call ${money(st.to_call)}` : "no bet to face"} · your stack ${money(st.hero_stack)} · villain ${money(st.villain_stack)}`),
  );
  if (st.history && st.history.length) root.append(PL.el("div", { className: "history muted" }, PL.historyText(st.history)));
  const acts = PL.el("div", { className: "actions" }, st.actions.map((a) => {
    const b = PL.el("button", { className: "act", disabled }, a.label);
    b.addEventListener("click", () => onAct(a.action));
    return b;
  }));
  root.append(acts);
  return root;
};

PL.feedbackView = (fb) => {
  const word = { correct: "Correct", mix: "Acceptable (low-frequency)", mistake: "Mistake" }[fb.verdict];
  return PL.el("div", { className: `feedback ${fb.verdict}` },
    PL.el("div", { className: "fb-head" },
      PL.el("strong", {}, word),
      PL.el("span", { className: "muted" }, ` You chose ${PL.label(fb.chosen)} — the solver does that ${PL.pct(fb.freq)} of the time with this hand.` +
        (fb.best !== fb.chosen ? ` Its top choice is ${PL.label(fb.best)}.` : ""))),
    PL.mixBars(fb.actions, fb.freqs, fb.chosen),
    fb.explanation ? PL.el("p", { className: "muted small" }, fb.explanation) : null,
  );
};

PL.resultView = (res, heroCombo) => {
  const lines = [];
  const vill = PL.el("span", {}, "Villain had ", PL.cardsEl(PL.comboCards(res.villain_combo)));
  const names = res.hero_hand ? `You: ${res.hero_hand}. Villain: ${res.villain_hand}.` : "";
  if (res.reason === "fold") {
    lines.push(res.winner === "hero" ? `Villain folds. You win a pot of ${PL.num(res.pot)}.` : `You fold. Villain wins a pot of ${PL.num(res.pot)}.`);
  } else if (res.reason === "showdown") {
    const w = { hero: "You win at showdown", villain: "Villain wins at showdown", split: "Split pot" }[res.winner] || "Showdown";
    lines.push(`${w} (pot ${PL.num(res.pot)}). ${names}`);
  } else if (res.reason === "street_end") {
    lines.push("The street is over. The next card is not part of this solve, so the hand stops here. Solve with “Keep the next street” to play on.");
  } else if (res.reason === "drill") {
    lines.push("Drill complete.");
  }
  // net = chips won/lost from this hand's own betting (the money already in the pot is not counted)
  if (res.net) lines.push(`Net from this hand's betting: ${res.net > 0 ? "+" : ""}${PL.num(res.net)} chips.`);
  return PL.el("div", { className: "result" },
    PL.el("div", { className: "row-line" }, PL.el("span", { className: "tag" }, "final board"), PL.cardsEl(res.board)),
    res.reason === "drill" ? null : PL.el("div", { className: "row-line" }, vill),
    lines.map((l) => PL.el("p", {}, l)),
  );
};

/* ---------- tabs ---------- */
PL.showTab = (name) => {
  PL.$$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
  PL.$$(".tab").forEach((t) => { t.hidden = t.id !== `tab-${name}`; });
  if (PL.hooks[name]) PL.hooks[name]();
};
