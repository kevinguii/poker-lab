# Roadmap

Status: **v0.1** = solve, cache, browse. Everything below is ordered by how much it unlocks.

## Done (v0.1)
- Spot model with validation and content-hash cache key
- TexasSolver adapter with live progress (iteration / exploitability)
- SQLite store, background worker, FastAPI API, static viewer
- Tests including a real-solver end-to-end run and a real-output fixture

## Next
1. **Spot presets.** Saved range/size templates (SRP BTN vs BB, 3-bet pots, etc.), so a new solve is two clicks.
   Preflop ranges can come from your own notes or the ranges you are allowed to export from your accounts.
2. **Trainer v1.** Pick a cached solve, deal a random hand from the actor's range, ask for an action, and score it by
   the solver's frequency for that action (since the dump has no EV). Track accuracy per spot/street in SQLite.
3. **EV.** Needed for a real "EV loss" trainer. Options: compute best-response EV ourselves from the tree and ranges
   (the tree and reach weights are already available), or switch/add an engine that exports EV.
   Decide after trying option 1 on a river solve, where it is cheap to verify.
4. **Hand history analyzer.** Parse PokerStars/GG text histories, map each hero postflop decision to the nearest cached
   or newly solved spot (board + approximate ranges + stacks), flag the biggest frequency/EV deviations.
5. **Daily quiz.** One random decision per day from your solves, with a short explanation of the solver's mix.

## Later / maybe
- Turn and river re-solving from a flop solve (`dump_rounds=2`, or re-solve from a chosen node).
- Range editor (13×13 painting) instead of text.
- Preflop solving (hard: not covered by open-source postflop solvers).
- Multiway, ICM, PLO (each needs a different engine).
- Packaging as a desktop app (Tauri) once the API is stable.
