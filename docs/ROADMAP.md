# Roadmap

## Done
- **v0.1** Spot model, TexasSolver adapter, SQLite cache, API, 13×13 viewer.
- **v0.2** Street-aware engine (chance nodes, dealt-card blocking, pot/stack tracking), trainer and drills with showdowns,
  daily quiz with streak, stats, presets, PokerStars hand history import and flop/turn analysis, tabbed UI.
  Verified against real solver output (street changes, 60 simulated hands, a real hand analysis) and in a browser.

## Next, roughly by value
1. **EV.** Needed for an "EV loss" score instead of frequency. The tree, ranges and reach are already available, so a
   best-response / EV pass over the tree is the likely route. River-complete trees are the cheap place to verify it.
2. **River decisions in hand analysis.** Needs a river solve whose ranges are narrowed by the actual flop/turn line
   (take the reach from the flop solve, then solve the river spot).
3. **Range editor.** Paint ranges on the 13×13 grid instead of typing strings; import/export presets.
4. **More hand history sources.** GGPoker and other formats; multiway hands (needs a multiway engine).
5. **Presets by position.** Today a preset is keyed by pot type only (`srp`, `3bp`...). BTN-vs-BB and CO-vs-BTN differ a lot.
6. **Solve queue controls.** Cancel a running solve, reorder the queue.

## Later / maybe
- Preflop solving (no open-source postflop solver covers it).
- ICM, PLO, multiway (each needs a different engine).
- Desktop packaging (Tauri) once the API settles.
