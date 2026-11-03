# pokerlab

A local-only poker study app in one repo: **solve** a spot, **browse** the strategy, **train** against the
solver, take a **daily quiz**, and **analyse your own hand histories**. No hosting, no account, one SQLite file.

It does not ship a solution library. Spots are solved on demand by an external open-source solver
([TexasSolver](https://github.com/bupticybee/TexasSolver)) and cached by content hash.

## Quick start

```bash
# 1. Build the solver (needs git, cmake, a C++17 compiler; on macOS also `brew install libomp`; ~1-2 min). Cloned into ./vendor
scripts/build_solver.sh

# 2. Run (creates .venv and installs on first use)
scripts/run.sh                # http://127.0.0.1:8000   (data lives in ./data, override with POKERLAB_DATA)

# 3. Tests (real-solver tests run automatically once step 1 is done, ~35 s extra)
.venv/bin/python -m pytest
```

## What is in it

| Tab | What it does |
|---|---|
| **Solver** | Enter a board, ranges, stacks and bet sizes, then solve. Browse the result on a 13×13 grid with per-combo detail, click through the tree, and **cross street changes** by picking the next card (turn/river need *Keep the next street*). **Drill this node** jumps to the trainer on that exact decision. Presets can be loaded or saved from here. |
| **Train** | Play hands against the solver (it samples the opponent's hand and every action from the solution, deals the next card, and settles showdowns). Or drill one decision repeatedly. |
| **Daily quiz** | Five realistic decisions per day, drawn from your own solves, fixed all day, answers final, with a streak. |
| **Hands** | Import PokerStars text histories. Heads-up flop hands become a solvable spot (ranges from a preset, the bet sizes actually used are added to the tree). Once solved, every one of *your* flop and turn decisions is graded against the solver. |
| **Stats** | Accuracy across the trainer, drills and quiz: by street, by solve, daily activity, recent mistakes. |

### How decisions are graded

TexasSolver's dump has strategies but no EV, so the app rebuilds EV itself (`src/pokerlab/ev.py`): it walks the subtree
below the decision once, with both players following the solution, and averages the payoffs over the opponent's range
(with card blocking) and over the cards still to come. That gives the EV of **every action for your exact hand**.

| Verdict | EV-graded (preferred) | Frequency-graded (fallback) |
|---|---|---|
| **correct** | the solver plays your action ≥ 25% of the time, or you lose ≤ 2% of the pot | you chose the top action, or the solver takes your action ≥ 25% of the time |
| **mix** | lose 2-5% of the pot | solver takes it 5-25% of the time |
| **mistake** | lose more than 5% of the pot | solver takes it < 5% of the time |

`score` is `1 - loss / (25% of pot)` (floored at 0) when graded by EV, and `freq(yours) / freq(best)` otherwise. Each
result says which basis it used (`basis`), and Stats shows the average EV loss.

When EV is not used:
- **The solve stops before the river** and betting could still continue (a flop solve that keeps only the turn). All-in runouts are exact. Beyond the last street in the solve there is no
  strategy, so EV there would only be an equity guess. It is still shown, labelled approximate, but the verdict stays
  frequency-based. River-complete trees (any solve started on the turn or river, or flops solved with the turn *and* river
  kept) are exact.
- **The subtree is too big** to evaluate in reasonable time in Python (`DEFAULT_MAX_WORK` in `ev.py`). Early flop decisions in
  large trees are the usual case.

EV is chips won from the start of the tree with the pot treated as dead money, so only differences between actions at one
decision mean anything. Thresholds live at the top of `src/pokerlab/training.py`.

### Hand history analysis: scope (read this before trusting a verdict)

- PokerStars text format, no-limit hold'em, cash or tournament. Other sites are not parsed.
- Only **heads-up flops with a known hero** are analysed; the reason is shown for every other hand.
- Ranges come from your **presets** by pot type (`srp`, `3bp`, ...), not from the hand. The built-in
  `srp-sample` is only the example from the solver's README, so replace it with ranges you trust, or
  every verdict inherits that assumption. If your hand is not in the preset range it is reported as
  `out_of_range`, not graded.
- The spot is a flop solve that keeps the turn, so **flop and turn** decisions are graded with properly
  narrowed ranges. **River decisions are listed but not graded.**
- Solves use looser settings (accuracy 1% of pot, 150 iterations) because flop solves are slow. The
  exploitability of each solve is shown next to the result; treat verdicts from poorly converged solves with care.
- Graded hand decisions are shown per hand and are not added to Stats. Flop decisions are usually frequency-graded (the
  solve keeps only the turn); turn decisions are graded by EV only when the river is also in the solve, which it is not here.
- Amounts are converted to big blinds and solved in 0.1bb units. Your real bet sizes are added to the tree so they
  can be matched; an action with no close equivalent stops grading at that point instead of guessing.

## Layout

```
scripts/build_solver.sh     clones + builds TexasSolver into ./vendor (gitignored)
src/pokerlab/
  ranges.py                 range parsing, 169-class grid helpers
  spot.py                   Spot model, validation, content hash, solver script generation
  solver.py                 runs console_solver, streams progress, parses result JSON
  strategy.py               SolveView: walk the tree (incl. chance nodes), reach, pot/stack tracking, grid
  evaluator.py              best-of-7 hand evaluator (showdowns, hand names)
  ev.py                     EV of every action at a node (fold/showdown payoffs, blocking, chance nodes)
  training.py               grading (EV or frequency), exact matchup sampling, HandSession, question generation
  quiz.py                   deterministic, persisted daily quiz
  handhistory.py            PokerStars parser
  analysis.py               replay a hand, build its spot, grade the hero's decisions
  cache.py / progress.py    SQLite: solves; attempts, quiz, presets, hands (one shared file)
  jobs.py                   single background solver worker
  api.py api_train.py api_hands.py   FastAPI app (/api/*) + static front end
web/                        no-build front end: common, solver, trainer, quiz, hands, stats, main (.js)
tests/                      unit + API tests, hand-built tree with exact numbers, real-solver tests
docs/                       FEATURE_MATRIX.md, ROADMAP.md
```

## Things worth knowing

- **Speed.** Measured on a 2-core cloud box: a tiny river solve ≈ 5 s, a turn+river solve with small ranges ≈ 10 s,
  a full flop solve with default sizes ≈ 1.7 s per iteration. Start with small boards/ranges. Your own machine is
  probably faster.
- **Size.** *Keep the next street* stores the turn (and river on turn boards) in the result: 10-20 MB of JSON per solve
  before compression. It is needed to play on or browse past a street change and for turn grading in Hands.
- **Reach is rebuilt.** The dump has conditional strategies only, so the viewer reconstructs each combo's reach along the
  path (and removes combos blocked by dealt cards) before aggregating to hand classes.
- **Solver rounding.** TexasSolver rounds bet amounts to whole chips, which is why hand-derived spots use 0.1bb units.
- **Licence.** TexasSolver is AGPL-3.0 and is run as a separate process, never copied into this repo. Personal local use
  is fine. If you ever host this for other people, its README says network services need a commercial licence.
- **No auth.** The server binds to 127.0.0.1 by default. Keep it that way.

See [docs/ROADMAP.md](docs/ROADMAP.md) for what is next.
