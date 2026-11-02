"use strict";
/* Train tab: play hands against the solver, or drill one exact decision. */

const TRAIN = { hand: null, tally: { correct: 0, mix: 0, mistake: 0 }, lastFeedback: null };

function renderTally() {
  const t = TRAIN.tally, n = t.correct + t.mix + t.mistake;
  PL.$("#train-session").textContent = n ? `This session: ${n} decisions · ${t.correct} correct · ${t.mix} mix · ${t.mistake} mistakes` : "";
}

async function fillSolveSelect() {
  const list = (await PL.api("/api/solves")).filter((s) => s.status === "done");
  const sel = PL.$("#train-solve");
  const keep = sel.value;
  sel.replaceChildren(...list.map((s) => PL.el("option", { value: s.id, textContent: `${s.board} · pot ${s.pot}` })));
  if (keep && list.some((s) => s.id === keep)) sel.value = keep;
  PL.$("#train-deal").disabled = list.length === 0;
  if (!list.length) PL.$("#train-table").replaceChildren(PL.el("p", { className: "muted" }, "Solve a spot in the Solver tab first."));
}

function showState(st) {
  const table = PL.$("#train-table");
  const parts = [];
  if (TRAIN.lastFeedback) parts.push(PL.feedbackView(TRAIN.lastFeedback));
  if (st.finished) {
    parts.push(PL.resultView(st.result, st.hero_combo));
    const next = PL.el("button", {}, "Deal next hand");
    next.addEventListener("click", () => deal());
    parts.push(next);
  } else {
    parts.push(PL.decisionView(st, act));
  }
  table.replaceChildren(...parts);
}

async function deal(opts = {}) {
  const err = PL.$("#train-error");
  err.textContent = "";
  TRAIN.lastFeedback = null;
  const solve_id = opts.solve_id || PL.$("#train-solve").value;
  if (!solve_id) return;
  try {
    const st = await PL.post("/api/trainer/hands", {
      solve_id, hero: opts.path ? "random" : PL.$("#train-hero").value, path: opts.path || "", single: !!opts.path,
    });
    TRAIN.hand = st.hand_id;
    showState(st);
  } catch (e) {
    err.textContent = e.message;
  }
}

async function act(action) {
  const err = PL.$("#train-error");
  err.textContent = "";
  try {
    const out = await PL.post(`/api/trainer/hands/${TRAIN.hand}/act`, { action });
    TRAIN.lastFeedback = out.feedback;
    TRAIN.tally[out.feedback.verdict] += 1;
    renderTally();
    showState(out.state);
  } catch (e) {
    err.textContent = e.message;
  }
}

PL.startDrill = async (solve_id, path) => {
  PL.showTab("train");
  await fillSolveSelect();
  PL.$("#train-solve").value = solve_id;
  await deal({ solve_id, path });
};

PL.$("#train-deal").addEventListener("click", () => deal());
PL.hooks.train = () => { fillSolveSelect().catch(() => {}); renderTally(); };
