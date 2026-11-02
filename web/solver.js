"use strict";
/* Solver tab: create solves, browse strategies, walk the tree (including street changes). */

const SOLVER = { sid: null, path: [], node: null, meta: null, cell: null, presets: [] };
PL.solver = SOLVER;

/* ---------- grid ---------- */
function buildGrid() {
  const g = PL.$("#grid");
  g.replaceChildren();
  for (let r = 0; r < 13; r++) {
    for (let c = 0; c < 13; c++) {
      const hi = PL.RANKS[Math.min(r, c)], lo = PL.RANKS[Math.max(r, c)];
      const cls = r === c ? hi + lo : hi + lo + (r < c ? "s" : "o");
      const cell = PL.el("div", { className: "cell empty", textContent: cls });
      cell.dataset.cls = cls;
      cell.addEventListener("click", () => selectCell(cls, cell));
      g.append(cell);
    }
  }
}

function paintGrid(node) {
  const cols = PL.colours(node.actions);
  PL.$$(".cell").forEach((cell) => {
    const d = node.grid[cell.dataset.cls];
    cell.classList.remove("sel");
    if (!d) {
      cell.className = "cell empty";
      cell.style.background = "";
      cell.title = "";
      return;
    }
    cell.className = "cell";
    let acc = 0;
    const stops = d.freqs.map((f, i) => {
      const from = acc * 100; acc += f;
      return `${cols[node.actions[i]]} ${from}% ${acc * 100}%`;
    });
    cell.style.background = `linear-gradient(90deg, ${stops.join(",")})`;
    cell.title = `${cell.dataset.cls}: ` + node.actions.map((a, i) => `${PL.label(a)} ${PL.pct(d.freqs[i])}`).join(", ");
  });
}

async function selectCell(cls, cell) {
  if (cell.classList.contains("empty")) return;
  PL.$$(".cell.sel").forEach((c) => c.classList.remove("sel"));
  cell.classList.add("sel");
  SOLVER.cell = cls;
  await showCombos(cls);
}

async function showCombos(cls) {
  const box = PL.$("#detail");
  try {
    const d = await PL.api(`/api/solves/${SOLVER.sid}/combos?hand=${cls}&path=${encodeURIComponent(SOLVER.path.join(PL.SEP))}`);
    const head = PL.el("tr", {}, PL.el("th", { textContent: "Combo" }), PL.el("th", { textContent: "Reach" }),
      ...d.actions.map((a) => PL.el("th", { textContent: PL.label(a) })));
    const rows = d.combos.map((c) => PL.el("tr", {}, PL.el("td", {}, PL.cardsEl(PL.comboCards(c.combo))), PL.el("td", { textContent: PL.pct(c.reach) }),
      ...c.freqs.map((f) => PL.el("td", { textContent: PL.pct(f) }))));
    box.replaceChildren(PL.el("div", { textContent: cls, style: "font-weight:600;margin-bottom:6px" }), PL.el("table", {}, head, ...rows));
  } catch (e) {
    box.textContent = e.message;
  }
}

/* ---------- node view ---------- */
function ctxLine(ctx) {
  const parts = [`${ctx.street}`, `pot ${PL.num(ctx.pot)}`, `stacks OOP ${PL.num(ctx.stacks.oop)} / IP ${PL.num(ctx.stacks.ip)}`];
  if (ctx.to_call) parts.push(`to call ${PL.num(ctx.to_call)}`);
  return PL.el("span", {}, PL.cardsEl(ctx.board), "  ", parts.join(" · "));
}

async function loadNode() {
  const node = await PL.api(`/api/solves/${SOLVER.sid}/node?path=${encodeURIComponent(SOLVER.path.join(PL.SEP))}`);
  SOLVER.node = node;
  renderBreadcrumb();
  PL.$("#ctx-line").replaceChildren(ctxLine(node.context));
  const box = PL.$("#node-box"), status = PL.$("#status-box"), dealBox = PL.$("#deal-box");
  PL.$("#drill-node").hidden = node.node_type !== "action_node";
  status.hidden = true; box.hidden = true; dealBox.hidden = true;

  if (node.node_type === "chance_node") {
    if (!node.deals.length) { status.hidden = false; status.textContent = node.note; return; }
    dealBox.hidden = false;
    PL.$("#deal-note").textContent = "The street ends here. Pick the next card to keep going:";
    PL.$("#deal-cards").replaceChildren(...node.deals.map((c) => {
      const b = PL.el("button", { className: "dealbtn" }, PL.cardEl(c));
      b.addEventListener("click", () => { SOLVER.path.push("@" + c); SOLVER.cell = null; loadNode(); });
      return b;
    }));
    return;
  }
  if (node.node_type !== "action_node") { status.hidden = false; status.textContent = node.note || "End of tree."; return; }

  box.hidden = false;
  PL.$("#actor").replaceChildren(PL.el("b", { textContent: node.actor.toUpperCase() }), " to act · ",
    `OOP ${node.range_combos.oop} combos · IP ${node.range_combos.ip} combos in range here`);
  const cols = PL.colours(node.actions);
  PL.$("#legend").replaceChildren(...node.actions.map((a, i) =>
    PL.el("span", { className: "leg" }, PL.el("span", { className: "sw", style: `background:${cols[a]}` }), `${PL.label(a)} ${PL.pct(node.overall[i])}`)));
  paintGrid(node);
  PL.$("#actions").replaceChildren(...node.actions.map((a, i) => {
    const ch = node.children[i];
    const b = PL.el("button", { className: "act", disabled: ch.terminal, title: ch.terminal ? "Ends the hand" : "Follow this action" },
      PL.el("span", { className: "sw", style: `background:${cols[a]}` }), PL.label(a),
      PL.el("span", { className: "pct", textContent: PL.pct(node.overall[i]) }), ch.terminal ? "" : " →");
    b.addEventListener("click", () => { SOLVER.path.push(a); SOLVER.cell = null; PL.$("#detail").replaceChildren(); loadNode(); });
    return b;
  }));
  if (SOLVER.cell && node.grid[SOLVER.cell]) {
    PL.$(`.cell[data-cls="${SOLVER.cell}"]`)?.classList.add("sel");
    showCombos(SOLVER.cell);
  } else {
    PL.$("#detail").replaceChildren();
  }
}

function renderBreadcrumb() {
  const crumbs = [["Root", 0], ...SOLVER.path.map((a, i) => [PL.label(a), i + 1])];
  PL.$("#breadcrumb").replaceChildren(...crumbs.map(([text, depth]) => {
    const b = PL.el("button", { textContent: text, className: depth === SOLVER.path.length ? "cur" : "" });
    b.addEventListener("click", () => { SOLVER.path = SOLVER.path.slice(0, depth); SOLVER.cell = null; loadNode(); });
    return b;
  }));
}

/* ---------- solves list ---------- */
async function refreshList() {
  const list = await PL.api("/api/solves");
  PL.$("#solve-list").replaceChildren(...list.map((s) => {
    const li = PL.el("li", { className: s.id === SOLVER.sid ? "sel" : "" },
      PL.el("div", {}, PL.el("div", { textContent: s.board }),
        PL.el("div", { className: "sub", textContent: s.status === "done" || s.status === "running"
          ? `${s.iterations ?? 0} iters · expl ${s.exploitability?.toFixed(2) ?? "–"}%` : s.error ? s.error.split("\n")[0].slice(0, 40) : "" })),
      PL.el("span", { className: `badge ${s.status}`, textContent: s.status }));
    li.addEventListener("click", () => openSolve(s.id));
    return li;
  }));
  if (SOLVER.sid) {
    const cur = list.find((s) => s.id === SOLVER.sid);
    if (cur && SOLVER.meta && cur.status !== SOLVER.meta.status) openSolve(SOLVER.sid, true);
    else if (cur && cur.status === "running") showStatus(cur);
  }
  PL.solveList = list;
  return list;
}

function showStatus(meta) {
  const s = PL.$("#status-box");
  PL.$("#node-box").hidden = true; PL.$("#deal-box").hidden = true;
  s.hidden = false;
  s.textContent = meta.status === "error"
    ? `Solve failed:\n${meta.error}`
    : `${meta.status}… ${meta.iterations != null ? `iteration ${meta.iterations}, exploitability ${meta.exploitability?.toFixed(2)}% of pot` : ""}`;
}

async function openSolve(sid, keepPath = false) {
  SOLVER.sid = sid;
  if (!keepPath) { SOLVER.path = []; SOLVER.cell = null; }
  const meta = await PL.api(`/api/solves/${sid}`);
  SOLVER.meta = meta;
  PL.$("#empty").hidden = true; PL.$("#viewer-body").hidden = false;
  PL.$("#solve-title").replaceChildren(meta.board, PL.el("small", {
    textContent: `pot ${meta.pot} · stack ${meta.effective_stack}` +
      (meta.exploitability != null ? ` · exploitability ${meta.exploitability.toFixed(2)}% of pot` : "") +
      (meta.spot && meta.spot.dump_rounds === 2 ? " · includes next street" : "") }));
  if (meta.status === "done") await loadNode();
  else { renderBreadcrumb(); showStatus(meta); PL.$("#drill-node").hidden = true; PL.$("#ctx-line").replaceChildren(); }
  refreshList();
}
PL.openSolve = (sid) => { PL.showTab("solver"); return openSolve(sid); };

/* ---------- presets ---------- */
async function loadPresets() {
  SOLVER.presets = await PL.api("/api/presets");
  const sel = PL.$("#preset-select");
  sel.replaceChildren(PL.el("option", { value: "", textContent: "(pick a preset)" }),
    ...SOLVER.presets.map((p) => PL.el("option", { value: p.name, textContent: `${p.name} (${p.pot_type})` })));
  PL.presets = SOLVER.presets;
  if (PL.hooks.presetsChanged) PL.hooks.presetsChanged();
}
PL.loadPresets = loadPresets;

/* ---------- form ---------- */
const nums = (s) => s.split(",").map((x) => parseFloat(x)).filter((x) => x > 0);

PL.$("#spot-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target), err = PL.$("#form-error");
  err.textContent = "";
  const bets = nums(f.get("bets")), raises = nums(f.get("raises"));
  const sizes = {};
  for (const p of ["oop", "ip"]) {
    sizes[p] = {};
    for (const st of ["flop", "turn", "river"]) {
      sizes[p][st] = { bet: bets, raise: raises, allin: [] };
      if (p === "oop" && st === "river") sizes[p][st].donk = bets;
    }
  }
  const spot = {
    board: f.get("board").trim(),
    pot: parseFloat(f.get("pot")),
    effective_stack: parseFloat(f.get("effective_stack")),
    oop_range: f.get("oop_range").trim(),
    ip_range: f.get("ip_range").trim(),
    accuracy: parseFloat(f.get("accuracy")),
    max_iteration: parseInt(f.get("max_iteration"), 10),
    dump_rounds: f.get("next_street") ? 2 : 1,
    bet_sizes: sizes,
  };
  try {
    const r = await PL.post("/api/solves", spot);
    await openSolve(r.id);
  } catch (e) {
    err.textContent = e.message;
  }
});

PL.$("#preset-select").addEventListener("change", (ev) => {
  const p = SOLVER.presets.find((x) => x.name === ev.target.value);
  if (!p) return;
  const f = PL.$("#spot-form");
  f.oop_range.value = p.oop_range;
  f.ip_range.value = p.ip_range;
});

PL.$("#save-preset").addEventListener("click", async () => {
  const f = PL.$("#spot-form"), err = PL.$("#form-error");
  const name = prompt("Preset name?");
  if (!name) return;
  const potType = prompt("Pot type tag (srp, 3bp, 4bp, limp, ...)?", "srp");
  if (!potType) return;
  try {
    await PL.put(`/api/presets/${encodeURIComponent(name)}`, { pot_type: potType, ip_range: f.ip_range.value, oop_range: f.oop_range.value });
    err.textContent = "";
    await loadPresets();
  } catch (e) {
    err.textContent = e.message;
  }
});

PL.$("#delete-solve").addEventListener("click", async () => {
  if (!SOLVER.sid || !confirm("Delete this solve?")) return;
  await PL.api(`/api/solves/${SOLVER.sid}`, { method: "DELETE" });
  SOLVER.sid = null;
  PL.$("#viewer-body").hidden = true; PL.$("#empty").hidden = false;
  refreshList();
});

PL.$("#drill-node").addEventListener("click", () => {
  if (SOLVER.node?.node_type !== "action_node") return;
  PL.startDrill(SOLVER.sid, SOLVER.path.join(PL.SEP));
});

PL.hooks.solver = () => { refreshList().catch(() => {}); };
PL.solverInit = async () => {
  const f = PL.$("#spot-form");
  buildGrid();
  await loadPresets();
  const sample = SOLVER.presets.find((p) => p.name === "srp-sample");
  if (sample) { f.oop_range.value = sample.oop_range; f.ip_range.value = sample.ip_range; }
  await refreshList();
  setInterval(() => refreshList().catch(() => {}), 2000);
};
