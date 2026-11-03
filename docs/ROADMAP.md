# Roadmap

## Done
- **v0.1** Spot model, TexasSolver adapter, SQLite cache, API, 13×13 viewer.
- **v0.2** Street-aware engine (chance nodes, dealt-card blocking, pot/stack tracking), trainer and drills with showdowns,
  daily quiz with streak, stats, presets, PokerStars hand history import and flop/turn analysis, tabbed UI.
  Verified against real solver output (street changes, 60 simulated hands, a real hand analysis) and in a browser.

- **v0.3** EV and EV-loss grading (`ev.py`), verified against a brute-force reference on a real river solve.

## Next, roughly by value
1. **EV on bigger trees.** The Python walk is skipped above a work budget and is approximate where the solve stops before the
   river. Options: numpy/vectorised showdowns, a per-solve EV cache in SQLite, or solving the river for hand analysis.
2. **Solver-free drills ("Learn" tab, `drills.py`).** Deterministic, seedable generators with exact answers and tolerance
   grading: pot odds and break-even equity, counting outs and the rule of 2/4, EV of a call given equity, minimum defense
   frequency, bluff-to-value ratio for a bet size, and equity estimation vs a range (needs an equity calculator on top of
   `evaluator.py`: enumerate when small, Monte Carlo otherwise). Each drill shows the worked solution after answering.
3. **Generalise the question engine (`questions.py`).** Today `quiz.py` only asks "what action?". Add question types, all
   graded from computed data: frequency guess (slider, scored by distance), range advantage (who has more equity), sizing
   choice, "which action has the highest EV", and EV-loss decisions. Add modes: endless practice with filters (street, pot
   type, texture, role), a timed 20-question test with an end report (score, EV lost, weakest areas), and mistake review
   with spaced repetition (Leitner boxes over the `attempts` table). Keep the daily quiz working.
4. **Spot library and background queue.** Pack definitions in JSON: pot types × flops × stack depths × a small sizing
   tree. A batch enqueue (extend `jobs.py`) that runs while idle, with progress shown in the UI and a storage budget.
   Flop-concept packs use `dump_rounds=1` to stay small. Add a pure-Python flop texture classifier (high card, paired,
   suit pattern, connectedness) and an aggregator (c-bet frequency, size mix, range-vs-range equity, nut advantage) for a
   "Learn" view that shows how strategy shifts across textures, then quizzes on it.
5. **Re-solve from a node (river decisions in hand analysis, unlimited turn/river scenarios).** Given a solve and a
   flop line, build the next-street `Spot` with ranges narrowed by reach, pot/stacks from `SolveView.context`. Current
   ranges only support class-level weights; combo-level weights differ by blockers — verify with the real solver whether
   it accepts specific combos (e.g. `AsKs:0.5`); if not, aggregate to class weights and label it as an approximation. This
   is what unlocks grading river decisions in hand analysis.
6. **LLM explanations and reasoning grading (`explain_llm.py`).** Build a facts object per decision (hand category,
   draws, blockers, equity vs the opponent's range, range advantage, board texture, EV and frequency per action); send
   only the facts to the LLM and require it to cite them, never add numbers. Cache by facts hash in SQLite. Reasoning
   grading: user types why, LLM returns JSON `{score 0-3, matched_facts, missing_facts, wrong_claims}` judged against the
   facts only. Client injectable; API key from `ANTHROPIC_API_KEY`, model name from an env var. With no key, fall back to
   a template explanation. Triggered by the user, never automatic; label output as AI-written. Tests with a fake client,
   no network in tests. **The solver and our own computations stay the source of truth for every number — an LLM only
   explains or critiques using facts we pass in, it never produces a frequency, EV or equity.**
7. **Curriculum and progress.** Order concepts (equity, pot odds, position, c-betting, sizing, check-raising, barrels,
   river), track mastery per concept from `attempts`, unlock the next module when mastery is reached, show it on Stats.
8. **Range editor.** Paint ranges on the 13×13 grid instead of typing strings; import/export presets.
9. **More hand history sources.** GGPoker and other formats; multiway hands (needs a multiway engine).
10. **Presets by position.** Today a preset is keyed by pot type only (`srp`, `3bp`...). BTN-vs-BB and CO-vs-BTN differ a lot.
11. **Solve queue controls.** Cancel a running solve, reorder the queue.

Cross-cutting, for items 2-7: new SQLite tables go in `progress.py` using `CREATE TABLE IF NOT EXISTS`, as the existing
ones do; new API routes get their own `api_*.py` router registered in `api.py`; new UI is its own `web/*.js` hooked into
`main.js`; keep solver runs off the request thread (`jobs.py`); verify UI changes in a real browser against a real solve.
Preflop ranges remain presets/approximations unless the user supplies trusted ones — anything built on them must say so
in the UI (item 4's texture aggregator and item 7's curriculum both touch this).

## Later / maybe
- Preflop solving (no open-source postflop solver covers it).
- ICM, PLO, multiway (each needs a different engine).
- Desktop packaging (Tauri) once the API settles.
