"use strict";

const RANKS = "AKQJT98765432";
const SEP = "|";
const SAMPLE = {
  oop_range:
    "QQ:0.5,JJ:0.75,TT,99,88,77,66,55,44,33,22,AKo:0.25,AQs,AQo:0.75,AJs,AJo:0.75,ATs,ATo:0.75,A9s,A8s,A7s,A6s,A5s,A4s,A3s,A2s,KQ,KJ,KTs,KTo:0.5,K9s,K8s,K7s,K6s,K5s,K4s:0.5,K3s:0.5,K2s:0.5,QJ,QTs,Q9s,Q8s,Q7s,JTs,JTo:0.5,J9s,J8s,T9s,T8s,T7s,98s,97s,96s,87s,86s,76s,75s,65s,64s,54s,53s,43s",
  ip_range:
    "AA,KK,QQ,JJ,TT,99:0.75,88:0.75,77:0.5,66:0.25,55:0.25,AK,AQs,AQo:0.75,AJs,AJo:0.5,ATs:0.75,A6s:0.25,A5s:0.75,A4s:0.75,A3s:0.5,A2s:0.5,KQs,KQo:0.5,KJs,KTs:0.75,K5s:0.25,K4s:0.25,QJs:0.75,QTs:0.75,Q9s:0.5,JTs:0.75,J9s:0.75,J8s:0.75,T9s:0.75,T8s:0.75,T7s:0.75,98s:0.75,97s:0.75,96s:0.5,87s:0.75,86s:0.5,85s:0.5,76s:0.75,75s:0.5,65s:0.75,64s:0.5,54s:0.75,53s:0.5,43s:0.5",
};

const $ = (s) => document.querySelector(s);
const el = (tag, props = {}, ...kids) => {
  const n = Object.assign(document.createElement(tag), props);
  kids.flat().forEach((k) => n.append(k));
  return n;
};

async function api(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (_) {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.json();
}

const state = { sid: null, path: [], node: null, meta: null, cell: null };

/* ---------- colours & labels ---------- */
function amount(a) { const m = a.match(/([\d.]+)$/); return m ? parseFloat(m[1]) : 0; }
function isAggro(a) { return /^(BET|RAISE|DONK)/.test(a); }
function label(a) {
  const [kind, amt] = a.split(" ");
  const k = kind[0] + kind.slice(1).toLowerCase();
  return amt ? `${k} ${parseFloat(amt).toString()}` : k;
}
function colours(actions) {
  const aggro = actions.filter(isAggro).sort((x, y) => amount(x) - amount(y));
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
}
const pct = (x) => (x * 100).toFixed(x > 0.9995 || x < 0.0005 ? 0 : 1) + "%";

/* ---------- grid ---------- */
function buildGrid() {
  const g = $("#grid");
  g.replaceChildren();
  for (let r = 0; r < 13; r++) {
    for (let c = 0; c < 13; c++) {
      const hi = RANKS[Math.min(r, c)], lo = RANKS[Math.max(r, c)];
      const cls = r === c ? hi + lo : hi + lo + (r < c ? "s" : "o");
      const cell = el("div", { className: "cell empty", textContent: cls });
      cell.dataset.cls = cls;
      cell.addEventListener("click", () => selectCell(cls, cell));
      g.append(cell);
    }
  }
}

function paintGrid(node) {
  const cols = colours(node.actions);
  document.querySelectorAll(".cell").forEach((cell) => {
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
    cell.title = `${cell.dataset.cls}: ` + node.actions.map((a, i) => `${label(a)} ${pct(d.freqs[i])}`).join(", ");
  });
}

async function selectCell(cls, cell) {
  if (cell.classList.contains("empty")) return;
  document.querySelectorAll(".cell.sel").forEach((c) => c.classList.remove("sel"));
  cell.classList.add("sel");
  state.cell = cls;
  await showCombos(cls);
}

async function showCombos(cls) {
  const box = $("#detail");
  try {
    const d = await api(`/api/solves/${state.sid}/combos?hand=${cls}&path=${encodeURIComponent(state.path.join(SEP))}`);
    const head = el("tr", {}, el("th", { textContent: "Combo" }), el("th", { textContent: "Reach" }),
      ...d.actions.map((a) => el("th", { textContent: label(a) })));
    const rows = d.combos.map((c) => el("tr", {}, el("td", { textContent: c.combo }), el("td", { textContent: pct(c.reach) }),
      ...c.freqs.map((f) => el("td", { textContent: pct(f) }))));
    box.replaceChildren(el("div", { textContent: cls, style: "font-weight:600;margin-bottom:6px" }), el("table", {}, head, ...rows));
  } catch (e) {
    box.textContent = e.message;
  }
}

/* ---------- node view ---------- */
async function loadNode() {
  const node = await api(`/api/solves/${state.sid}/node?path=${encodeURIComponent(state.path.join(SEP))}`);
  state.node = node;
  renderBreadcrumb();
  const box = $("#node-box"), status = $("#status-box");
  if (node.node_type !== "action_node") {
    box.hidden = true; status.hidden = false;
    status.textContent = node.note || "End of tree.";
    return;
  }
  status.hidden = true; box.hidden = false;
  $("#actor").replaceChildren(el("b", { textContent: node.actor.toUpperCase() }), " to act · ",
    `OOP ${node.range_combos.oop} combos · IP ${node.range_combos.ip} combos in range here`);
  const cols = colours(node.actions);
  $("#legend").replaceChildren(...node.actions.map((a, i) =>
    el("span", { className: "leg" }, el("span", { className: "sw", style: `background:${cols[a]}` }), `${label(a)} ${pct(node.overall[i])}`)));
  paintGrid(node);
  $("#actions").replaceChildren(...node.actions.map((a, i) => {
    const ch = node.children[i];
    const dead = ch.terminal;
    const b = el("button", { className: "act", disabled: dead, title: dead ? "Ends the hand" : "Follow this action" },
      el("span", { className: "sw", style: `background:${cols[a]}` }), label(a),
      el("span", { className: "pct", textContent: pct(node.overall[i]) }), dead ? "" : " →");
    b.addEventListener("click", () => { state.path.push(a); state.cell = null; $("#detail").replaceChildren(); loadNode(); });
    return b;
  }));
  if (state.cell && node.grid[state.cell]) {
    document.querySelector(`.cell[data-cls="${state.cell}"]`)?.classList.add("sel");
    showCombos(state.cell);
  } else {
    $("#detail").replaceChildren();
  }
}

function renderBreadcrumb() {
  const crumbs = [["Root", 0], ...state.path.map((a, i) => [label(a), i + 1])];
  $("#breadcrumb").replaceChildren(...crumbs.map(([text, depth]) => {
    const b = el("button", { textContent: text, className: depth === state.path.length ? "cur" : "" });
    b.addEventListener("click", () => { state.path = state.path.slice(0, depth); loadNode(); });
    return b;
  }));
}

/* ---------- solves ---------- */
async function refreshList() {
  const list = await api("/api/solves");
  $("#solve-list").replaceChildren(...list.map((s) => {
    const li = el("li", { className: s.id === state.sid ? "sel" : "" },
      el("div", {}, el("div", { textContent: s.board }),
        el("div", { className: "sub", textContent: s.status === "done" || s.status === "running"
          ? `${s.iterations ?? 0} iters · expl ${s.exploitability?.toFixed(2) ?? "–"}%` : s.error ? s.error.split("\n")[0].slice(0, 40) : "" })),
      el("span", { className: `badge ${s.status}`, textContent: s.status }));
    li.addEventListener("click", () => openSolve(s.id));
    return li;
  }));
  if (state.sid) {
    const cur = list.find((s) => s.id === state.sid);
    if (cur && state.meta && cur.status !== state.meta.status) openSolve(state.sid, true);
    else if (cur && cur.status === "running") showStatus(cur);
  }
}

function showStatus(meta) {
  const s = $("#status-box");
  $("#node-box").hidden = true;
  s.hidden = false;
  s.textContent = meta.status === "error"
    ? `Solve failed:\n${meta.error}`
    : `${meta.status}… ${meta.iterations != null ? `iteration ${meta.iterations}, exploitability ${meta.exploitability?.toFixed(2)}% of pot` : ""}`;
}

async function openSolve(sid, keepPath = false) {
  state.sid = sid;
  if (!keepPath) { state.path = []; state.cell = null; }
  const meta = await api(`/api/solves/${sid}`);
  state.meta = meta;
  $("#empty").hidden = true; $("#viewer-body").hidden = false;
  $("#solve-title").replaceChildren(meta.board, el("small", {
    textContent: `pot ${meta.pot} · stack ${meta.effective_stack}` +
      (meta.exploitability != null ? ` · exploitability ${meta.exploitability.toFixed(2)}% of pot` : "") }));
  if (meta.status === "done") await loadNode();
  else { renderBreadcrumb(); showStatus(meta); }
  document.querySelectorAll("#solve-list li").forEach((li) => li.classList.remove("sel"));
  refreshList();
}

/* ---------- form ---------- */
const nums = (s) => s.split(",").map((x) => parseFloat(x)).filter((x) => x > 0);

$("#spot-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target), err = $("#form-error");
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
    bet_sizes: sizes,
  };
  try {
    const r = await api("/api/solves", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(spot) });
    await openSolve(r.id);
  } catch (e) {
    err.textContent = e.message;
  }
});

$("#delete-solve").addEventListener("click", async () => {
  if (!state.sid || !confirm("Delete this solve?")) return;
  await api(`/api/solves/${state.sid}`, { method: "DELETE" });
  state.sid = null;
  $("#viewer-body").hidden = true; $("#empty").hidden = false;
  refreshList();
});

async function init() {
  const f = $("#spot-form");
  f.oop_range.value = SAMPLE.oop_range;
  f.ip_range.value = SAMPLE.ip_range;
  buildGrid();
  try {
    const h = await api("/api/health");
    const p = $("#solver-status");
    p.textContent = h.solver_available ? "solver ready" : "solver missing: run scripts/build_solver.sh";
    p.classList.add(h.solver_available ? "ok" : "bad");
  } catch (_) {}
  await refreshList();
  setInterval(() => refreshList().catch(() => {}), 2000);
}
init();
