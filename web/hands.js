"use strict";
/* Hands tab: import PokerStars histories, solve the flop spot, see each decision graded. */

const HANDS = { list: [], sel: null, preset: "", timer: null };

function handBadge(h) {
  if (!h.eligible) return PL.el("span", { className: "badge error", title: h.reason }, "n/a");
  if (!h.solve) return PL.el("span", { className: "badge" }, "needs solve");
  return PL.el("span", { className: `badge ${h.solve.status}` }, h.solve.status);
}

async function loadHands() {
  HANDS.list = await PL.api("/api/hands");
  const ul = PL.$("#hand-list");
  if (!HANDS.list.length) { ul.replaceChildren(PL.el("li", { className: "muted" }, "No hands yet.")); return; }
  ul.replaceChildren(...HANDS.list.map((h) => {
    const li = PL.el("li", { className: h.id === HANDS.sel ? "sel" : "" },
      PL.el("div", {},
        PL.el("div", {}, h.hero_cards ? PL.cardsEl(h.hero_cards) : "?", PL.el("span", { className: "gap" }),
          h.board.flop ? PL.cardsEl(h.board.flop) : PL.el("span", { className: "muted" }, "no flop")),
        PL.el("div", { className: "sub", textContent: h.eligible ? `${h.pot_type} · hero ${h.hero_role.toUpperCase()}` : h.reason })),
      handBadge(h));
    li.addEventListener("click", () => { HANDS.sel = h.id; openHand(); loadHands(); });
    return li;
  }));
}

function sizesSummary(spot) {
  const out = [];
  for (const p of ["oop", "ip"]) {
    const f = spot.bet_sizes[p].flop;
    out.push(`${p.toUpperCase()} flop bet ${f.bet.join("/")}% raise ${f.raise.join("/")}%`);
  }
  return out.join(" · ");
}

function decisionCard(d) {
  const head = PL.el("div", { className: "row-line" },
    PL.el("span", { className: "tag" }, d.street),
    PL.el("strong", {}, d.action),
    PL.el("span", { className: "muted" }, `pot ${PL.num(d.pot_bb)}bb${d.to_call_bb ? ` · facing ${PL.num(d.to_call_bb)}bb` : ""}`));
  let body;
  if (d.status === "graded") {
    body = PL.feedbackView({ ...d.feedback, explanation: d.note || "" });
  } else {
    const text = {
      out_of_range: "Your hand is not in the preset range at this node, so the solver has no strategy for it. Use a preset that includes it.",
      not_in_solve: d.note || "This part of the hand is not in the solve.",
      river_not_covered: "River decisions are not graded: a flop solve does not include the river. Solve the river spot on its own to study it.",
    }[d.status] || d.status;
    body = PL.el("p", { className: "muted" }, text);
  }
  return PL.el("div", { className: "dcard" }, head, body);
}

async function openHand() {
  const box = PL.$("#hand-detail");
  clearTimeout(HANDS.timer);
  if (!HANDS.sel) return;
  let a;
  try {
    a = await PL.api(`/api/hands/${HANDS.sel}/analysis${HANDS.preset ? `?preset=${encodeURIComponent(HANDS.preset)}` : ""}`);
  } catch (e) { box.textContent = e.message; return; }

  const parts = [PL.el("div", { className: "viewer-head" },
    PL.el("div", {}, PL.el("strong", {}, `Hand #${a.id}`), PL.el("span", { className: "gap" }),
      a.hero_cards ? PL.cardsEl(a.hero_cards) : "", PL.el("span", { className: "gap" }),
      a.board.flop ? PL.cardsEl(a.board.flop.concat(a.board.turn || [], a.board.river || [])) : ""),
    (() => { const b = PL.el("button", { className: "ghost" }, "Delete hand"); b.addEventListener("click", async () => {
      await PL.api(`/api/hands/${a.id}`, { method: "DELETE" }); HANDS.sel = null; box.replaceChildren(PL.el("div", { className: "muted center" }, "Hand deleted.")); loadHands(); }); return b; })())];

  if (!a.eligible) {
    parts.push(PL.el("p", {}, PL.el("strong", {}, "Not analysable: "), a.reason));
    box.replaceChildren(...parts);
    return;
  }

  const sel = PL.el("select", {}, PL.el("option", { value: "" }, `auto (${a.pot_type})`),
    ...(PL.presets || []).map((p) => PL.el("option", { value: p.name, selected: p.name === HANDS.preset }, `${p.name} (${p.pot_type})`)));
  sel.addEventListener("change", () => { HANDS.preset = sel.value; openHand(); });
  parts.push(
    PL.el("div", { className: "muted" }, `${a.pot_type.toUpperCase()} · you were ${a.hero_role.toUpperCase()} · pot ${PL.num(a.pot_bb)}bb · effective stack ${PL.num(a.eff_stack_bb)}bb`),
    PL.el("div", { className: "controls" }, PL.el("label", {}, "Ranges from preset ", sel), PL.el("span", { className: "muted" }, `using “${a.preset}”`)),
    PL.el("div", { className: "muted small" }, sizesSummary(a.spot)),
  );

  const solve = a.solve;
  if (!solve || solve.status === "error") {
    if (solve && solve.error) parts.push(PL.el("p", { className: "error" }, solve.error));
    const b = PL.el("button", {}, "Solve this spot");
    b.addEventListener("click", async () => {
      b.disabled = true;
      try { await PL.post(`/api/hands/${a.id}/solve`, { preset: HANDS.preset || null }); } catch (e) { parts.push(e.message); }
      openHand(); loadHands();
    });
    parts.push(b, PL.el("p", { className: "hint" }, "A flop solve with the next street included usually takes minutes. You can leave this page; the result is cached."));
  } else if (solve.status !== "done") {
    parts.push(PL.el("div", { className: "status-box" }, `${solve.status}… ${solve.iterations != null ? `iteration ${solve.iterations}, exploitability ${solve.exploitability?.toFixed(2)}% of pot` : ""}`));
    HANDS.timer = setTimeout(() => { openHand(); loadHands(); }, 2500);
  } else {
    const ev = a.evaluation;
    const open = PL.el("button", { className: "ghost" }, "Open this solve in the viewer");
    open.addEventListener("click", () => PL.openSolve(a.spot_id));
    parts.push(open);
    const s = ev.summary;
    parts.push(PL.el("div", { className: "summary-row" },
      PL.el("span", {}, `${s.graded} decisions graded`),
      s.avg_score != null ? PL.el("span", {}, `average score ${(s.avg_score * 100).toFixed(0)}%`) : null,
      PL.el("span", {}, `${s.mistakes} mistakes · ${s.mixes} low-frequency`),
      PL.el("span", { className: "muted" }, `solve exploitability ${solve.exploitability?.toFixed(2) ?? "?"}% of pot`)));
    if (!ev.decisions.length) parts.push(PL.el("p", { className: "muted" }, "Hero made no decisions after the flop in this hand."));
    ev.decisions.forEach((d) => parts.push(decisionCard(d)));
  }
  box.replaceChildren(...parts);
}

/* ---------- import ---------- */
PL.$("#hh-import").addEventListener("click", async () => {
  const msg = PL.$("#hh-msg");
  msg.textContent = "";
  try {
    const r = await PL.post("/api/hands/import", { text: PL.$("#hh-text").value });
    msg.textContent = `${r.parsed} parsed · ${r.new} new · ${r.duplicates} already imported` + (r.errors.length ? ` · ${r.errors.length} problems: ${r.errors.join("; ")}` : "");
    if (r.new) PL.$("#hh-text").value = "";
    await loadHands();
  } catch (e) { msg.textContent = e.message; }
});
PL.$("#hh-file").addEventListener("change", (ev) => {
  const f = ev.target.files[0];
  if (f) f.text().then((t) => { PL.$("#hh-text").value = t; });
});

/* ---------- presets list ---------- */
function renderPresets() {
  const ul = PL.$("#preset-list");
  ul.replaceChildren(...(PL.presets || []).map((p) => {
    const li = PL.el("li", {}, PL.el("div", {}, PL.el("strong", {}, p.name), `  ${p.pot_type}`, p.builtin ? PL.el("span", { className: "badge" }, "example") : null,
      PL.el("div", { className: "sub" }, p.notes || `${p.ip_range.split(",").length} IP / ${p.oop_range.split(",").length} OOP hand entries`)));
    if (!p.builtin) {
      const b = PL.el("button", { className: "ghost small" }, "Delete");
      b.addEventListener("click", async () => { await PL.api(`/api/presets/${encodeURIComponent(p.name)}`, { method: "DELETE" }); await PL.loadPresets(); });
      li.append(b);
    }
    return li;
  }));
}
PL.hooks.presetsChanged = renderPresets;
PL.hooks.hands = async () => { await PL.loadPresets(); renderPresets(); await loadHands(); if (HANDS.sel) openHand(); };
