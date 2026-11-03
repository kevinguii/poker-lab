# Plan: turn pokerlab into a learning + testing app

Put this file at `docs/PLAN_LEARNING_APP.md`. Read `README.md` and `docs/ROADMAP.md` first.

## Who this is for
One person who does **not** play much poker and has little hand data. They want to learn the game, be tested on
**EV** and **flop** concepts, understand the **reasoning**, and get many more scenarios than the daily quiz gives.
So content must come from generated spots and computed facts, never from their play history.

## Principles (do not break these)
1. **The solver and our own computations are the source of truth for every number.** An LLM may only explain
   or critique, using facts we computed and pass in. It never produces a frequency, EV or equity.
2. **Be honest about ranges.** Preflop ranges come from presets and are approximations unless the user supplies
   trusted ones. Anything built on approximate ranges must say so in the UI.
3. **Local only.** No hosting, no auth, bind to 127.0.0.1. TexasSolver is AGPL-3.0: keep it as a separate process,
   never copy its code into the repo.
4. **Test with exact numbers.** Use hand-built trees (`tests/trees.py`) for logic and `@pytest.mark.solver` tests
   against the real solver for format assumptions. Don't weaken existing tests; run the full suite before each commit.
5. Small commits, update `README.md` / `docs/ROADMAP.md` as features land.

## Current state (v0.2)
Modules in `src/pokerlab/`: `ranges`, `spot`, `solver`, `strategy` (SolveView: walk, reach, context, describe),
`evaluator`, `training` (grading, matchup sampling, HandSession, question generation), `quiz` (daily quiz),
`handhistory`, `analysis`, `cache`, `progress` (SQLite), `jobs`, `api*`. Front end is no-build vanilla JS in `web/`
(tabs: Solver, Train, Daily quiz, Hands, Stats).

Facts about the solver output you must respect:
- Dump has **conditional strategies only**: no reach, no EV. Reach is rebuilt in `SolveView.reach`.
- A path is a list of steps: action strings (`"BET 25.000000"`) or deals (`"@7d"`). Bet/raise amounts are the
  player's **street total**. A missing child means the hand ends (fold or river showdown).
- `dump_rounds=1` stores the current street only; `2` also stores the next street (10-20 MB JSON per solve).
- The solver **rounds bet amounts to whole chips**, so hand-derived spots use units of 0.1 big blind.
- Grading today is **frequency based** (correct / mix / mistake). EV is not used yet.

## Work items, in order

### 0. EV (already in progress in Claude Code; do not redo)
Per-combo EV for every action at every node, computed from the saved tree, ranges, reach and showdown equity.
Expected outcome: `SolveView` exposes EV per combo/action; grading adds **EV loss in bb**; the viewer and trainer show
EV per action. Acceptance: on river-complete trees, our best-response/exploitability agrees with the solver's printed
exploitability within tolerance; EV is zero-sum-consistent; exact-number test on `tests/trees.py`.
Everything below should use EV loss once this lands.

### 1. Solver-free drills (new "Learn" tab, module `drills.py`)
Deterministic, seedable generators with exact answers and tolerance grading:
pot odds and break-even equity, counting outs and the rule of 2/4, EV of a call given equity, minimum defense
frequency, bluff-to-value ratio for a bet size, and **equity estimation vs a range** (needs an equity calculator built on
`evaluator.py`; enumerate when small, Monte Carlo otherwise). Each drill shows the worked solution after answering.
Tests: math checked against hand-computed cases.

### 2. Generalise the question engine (`questions.py`)
Today `quiz.py` only asks "what action?". Add question types, all graded from computed data:
frequency guess (slider, scored by distance), range advantage (who has more equity), sizing choice, "which action has the
highest EV", and EV-loss decisions. Add modes: endless practice with filters (street, pot type, texture, role),
a timed 20-question test with an end report (score, EV lost, weakest areas), and **mistake review** with spaced
repetition (Leitner boxes over the `attempts` table; re-ask missed spots later). Keep the daily quiz working.

### 3. Spot library and background queue
Pack definitions in JSON: pot types x flops x stack depths x a small sizing tree. A batch enqueue (extend `jobs.py`)
that runs while idle, with progress shown in the UI and a storage budget. Flop-concept packs use `dump_rounds=1` to stay small.
Add a pure-Python **flop texture classifier** (high card, paired, suit pattern, connectedness) and an aggregator:
c-bet frequency, size mix, range-vs-range equity, nut advantage. Use it for a "Learn" view that shows how strategy shifts
across textures, then quiz on it.

### 4. Re-solve from a node (unlimited turn/river scenarios)
Given a solve and a flop line, build the next-street `Spot` with ranges narrowed by reach, pot/stacks from
`SolveView.context`. Current ranges only support class-level weights; combo-level weights differ by blockers. **Verify
with the real solver** whether it accepts specific combos (e.g. `AsKs:0.5`); if not, aggregate to class weights and
label it as an approximation. This also unlocks river grading in hand analysis.

### 5. LLM explanations and reasoning grading (`explain_llm.py`)
- Build a **facts object** per decision: hand category, draws, blockers, equity vs the opponent's range, range advantage,
  board texture, EV and frequency per action.
- Explanation: send only the facts; require the LLM to cite them and never add numbers. Cache by facts hash in SQLite.
- Reasoning grading: user types why; LLM returns JSON `{score 0-3, matched_facts, missing_facts, wrong_claims}` judged
  against the facts only.
- Client injectable; API key from `ANTHROPIC_API_KEY`, model name from an env var (do not hardcode). With no key,
  fall back to a template explanation. Triggered by the user, never automatic. Label output as AI-written.
- Tests with a fake client; no network in tests.

### 6. Curriculum and progress
Order concepts (equity, pot odds, position, c-betting, sizing, check-raising, barrels, river), track mastery per concept
from `attempts`, unlock the next module when mastery is reached, show it on Stats.

## Cross-cutting
- New SQLite tables go in `progress.py` using `CREATE TABLE IF NOT EXISTS`, as the existing ones do.
- New API routes in their own `api_*.py` router, registered in `api.py`; new UI as its own `web/*.js`, hooked in `main.js`.
- Keep solver runs off the request thread (use `jobs.py`).
- Verify UI changes in a real browser (Playwright is available) against a real solve, not only unit tests.
