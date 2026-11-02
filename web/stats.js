"use strict";
/* Stats tab: accuracy over everything you've answered (trainer, drills and the daily quiz). */

function statTile(label, value, cls = "") {
  return PL.el("div", { className: `tile ${cls}` }, PL.el("div", { className: "tile-v" }, value), PL.el("div", { className: "muted small" }, label));
}

async function loadStats() {
  const box = PL.$("#stats-body");
  const s = await PL.api("/api/stats");
  if (!s.total) {
    box.replaceChildren(PL.el("p", { className: "muted" }, "Nothing yet. Play a hand in the Train tab or answer the daily quiz."));
    return;
  }
  const pc = (x) => (x == null ? "–" : `${(x * 100).toFixed(0)}%`);
  const parts = [
    PL.el("div", { className: "tiles" },
      statTile("decisions", String(s.total)),
      statTile("average score", pc(s.avg_score)),
      statTile("correct", pc(s.correct), "good"),
      statTile("low-frequency", pc(s.mix), "mid"),
      statTile("mistakes", pc(s.mistake), "bad")),
  ];

  const max = Math.max(...s.daily.map((d) => d.n), 1);
  parts.push(PL.el("h2", {}, "Last 14 days"),
    PL.el("div", { className: "bars" }, s.daily.map((d) =>
      PL.el("div", { className: "bar", title: `${d.day}: ${d.n} decisions, score ${(d.avg_score * 100).toFixed(0)}%` },
        PL.el("div", { className: "bar-fill", style: `height:${(d.n / max) * 100}%` }), PL.el("div", { className: "bar-l" }, d.day.slice(5))))));

  parts.push(PL.el("h2", {}, "By street"),
    PL.el("table", {}, PL.el("tr", {}, ["street", "decisions", "avg score", "mistakes"].map((h) => PL.el("th", {}, h))),
      ...s.by_street.map((r) => PL.el("tr", {}, PL.el("td", {}, r.street), PL.el("td", {}, String(r.n)), PL.el("td", {}, pc(r.avg_score)), PL.el("td", {}, pc(r.mistake))))));

  if (s.by_solve.length) {
    parts.push(PL.el("h2", {}, "By solve"),
      PL.el("table", {}, PL.el("tr", {}, ["solve", "decisions", "avg score", "mistakes"].map((h) => PL.el("th", {}, h))),
        ...s.by_solve.map((r) => {
          const meta = (PL.solveList || []).find((x) => x.id === r.solve_id);
          return PL.el("tr", {}, PL.el("td", {}, meta ? meta.board : r.solve_id.slice(0, 8) + " (deleted)"), PL.el("td", {}, String(r.n)), PL.el("td", {}, pc(r.avg_score)), PL.el("td", {}, pc(r.mistake)));
        })));
  }

  if (s.recent_mistakes.length) {
    parts.push(PL.el("h2", {}, "Recent mistakes"),
      PL.el("ul", { className: "mistakes" }, s.recent_mistakes.map((m) =>
        PL.el("li", {}, PL.cardsEl(PL.comboCards(m.combo)), `  ${m.street}, ${m.hero_role.toUpperCase()}: you ${PL.label(m.chosen)}, solver prefers ${PL.label(m.best)}`,
          PL.el("span", { className: "muted" }, `  (${PL.pct(m.freq)} for your choice)`)))));
  }
  box.replaceChildren(...parts);
}

PL.hooks.stats = () => { (PL.solveList ? Promise.resolve() : PL.api("/api/solves").then((l) => { PL.solveList = l; })).then(loadStats).catch((e) => { PL.$("#stats-body").textContent = e.message; }); };
