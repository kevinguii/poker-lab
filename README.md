# pokerlab

A local-only poker study app: solve a spot, browse the strategy on a 13×13 grid, click through the
betting tree. Built to reproduce the core ideas of GTO-training sites (solution browser, custom
solves, trainer, hand analysis) for personal use, with no hosting and no account.

It does **not** ship a solution library. Spots are solved on demand by an external open-source
solver ([TexasSolver](https://github.com/bupticybee/TexasSolver)) and cached in a single SQLite file.

## Quick start

```bash
# 1. Build the solver (needs git, cmake, a C++17 compiler; ~1-2 min). Cloned into ./vendor
scripts/build_solver.sh

# 2. Install and run
pip install -e ".[dev]"
pokerlab                      # http://127.0.0.1:8000

# 3. Tests (the real-solver test runs automatically once step 1 is done)
pytest
```

In the UI: fill in a board and two ranges, hit **Solve**, then click cells to see per-combo
frequencies and the action buttons to walk the tree. Identical spots are cached by content hash.

Range syntax: `AA,KK:0.5,AKs,AQo:0.75,KQ` (pairs, `s`/`o` suffix, optional `:weight`; no suffix means both).
Pot and stack are arbitrary chip units (the sample uses pot 50, stack 200).

## Layout

```
scripts/build_solver.sh     clones + builds TexasSolver into ./vendor (gitignored)
src/pokerlab/
  ranges.py                 range parsing, 169-class grid helpers
  spot.py                   Spot model, validation, content hash, solver script generation
  solver.py                 runs console_solver, streams progress, parses result JSON
  strategy.py               SolveView: walk the tree, rebuild reach, aggregate to the grid
  cache.py                  SQLite store (gzip'd result trees)
  jobs.py                   single background worker (solves already use all cores)
  api.py / cli.py           FastAPI app (/api/*) + static viewer, `pokerlab` command
web/                        no-build static front end (vanilla JS)
tests/                      unit + API tests, and a real-solver end-to-end test
docs/                       FEATURE_MATRIX.md (what the target sites offer), ROADMAP.md
```

## Things worth knowing

- **Speed.** Measured on a 2-core cloud box: a tiny river solve takes about 5 s; a full flop solve
  with the default sizes runs about 1.7 s per iteration, so 200 iterations is several minutes.
  Start with river/turn boards or narrow ranges, and raise `accuracy` (it is % of pot) for quick looks.
- **No EV in the output.** TexasSolver's dump contains strategies only. That is why the viewer shows
  frequencies, not EV, and why a trainer scored by EV loss needs extra work (see ROADMAP).
- **Aggregation is reach-weighted.** The dump has conditional strategies only, so the viewer
  rebuilds each combo's reach probability along the path before averaging into hand classes.
- **`dump_rounds`.** `1` (default) stores only the current street, which keeps results small.
  `2` also stores the next street (the sample dump was 22 MB uncompressed).
- **Licence.** TexasSolver is AGPL-3.0 and is run as a separate process, never copied into this
  repo. Personal local use is fine. If you ever host this for other people, its README says network
  services need a commercial licence, so check first.
- **No auth.** The server binds to 127.0.0.1 by default. Keep it that way.

See [docs/ROADMAP.md](docs/ROADMAP.md) for what is next.
