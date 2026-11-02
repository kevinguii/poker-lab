"use strict";

PL.$$("#tabs button").forEach((b) => b.addEventListener("click", () => PL.showTab(b.dataset.tab)));

(async function init() {
  try {
    const h = await PL.api("/api/health");
    const p = PL.$("#solver-status");
    p.textContent = h.solver_available ? "solver ready" : "solver missing: run scripts/build_solver.sh";
    p.classList.add(h.solver_available ? "ok" : "bad");
  } catch (_) {}
  await PL.solverInit();
})();
