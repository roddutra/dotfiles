# Communicating results

## To the user during runs

Report at milestones, not per run: panel launched (with the run matrix), mid-way only if something changes the plan (a systematic misreading, a broken capture), all runs in, analysis done. A line per finished run buries the signal and repeats itself. Keep per-run observations in `analysis/lead-notes.md` for the analysts instead.

At the end, give the user:
- the winner and for whom, the size of the gap, and whether it holds across models
- the ICP signal: who it resonated with most and least, and why
- what is still missing, and what regressed since the last round
- decisions only they can make, including claims the concepts invented
- a recommendation, and whether another round is worth running

## Visual summary page

When the session can publish a page, a one-page visual summary is the best way to share a panel. Sections that worked in the Sept 2026 study:

1. Header: question, run and review counts, personas, models.
2. Three headline takeaways.
3. Leaderboard as a dot plot (truncated axes are fine for dots, not bars), coloured by concept type, with the gap marked.
4. Reviewer quotes, each with persona role, model, and one line of context.
5. Per-run matrix: persona x model rows, concept columns, the run's first choice filled.
6. Factor heat table: concepts x factors, leader outlined.
7. Round-over-round dumbbell: previous winners vs current, per factor.
8. Find-the-answer bars (Found / Partly per question).
9. Lines not believed (with counts) and lines to keep.
10. Asks tracker across rounds with status pills (solved, partly, missing, regressed).
11. ICP tiers: ideal, strong, not yet, gatekeepers, out of scope, each with personas, fit, why, and a quote.
12. Recommendation and decisions.
13. Method and caveats, including "simulated buyers" and model-skew notes.

`analysis/quant.json` holds the data for most of these (leaderboard, factors, per-model levels, persona agreement, fit). An archived example is `report/index.html` in the TomoBroker research repo's `customer-research/2026-09-25-homepage-concepts/`.
