# Method: bias controls, models and lessons learned

## Bias controls

| Control | How | Why |
|---|---|---|
| Neutral labels | `init_study.py` copies each concept to `panel/sites/concept-<L>/` with a shuffled label; the key lives outside `panel/` | Folder names like `13-before-and-after` leak the designer's intent |
| Randomised order | Seeded per persona, identical across that persona's models | Removes order and fatigue effects without confounding model comparisons |
| Sandboxed reading | Run prompt restricts reading to `panel/`; "ignore background in your system context" | Subagents inherit project instructions (CLAUDE.md, AGENTS.md) and leak internal terms into reviews |
| No cross-talk | "Do not read any other persona file" | Runs otherwise copy each other's opinions |
| Cold rounds | Follow-up rounds get no results from earlier rounds | Prior results anchor scores and themes |
| Placeholder notes | `context_notes` states what is fictitious or placeholder (prices, demo company) | Panellists judge everything literally, including placeholder prices and build notes |
| Leak scan | `leak_terms` checked by `check_runs.py`; `forbidden_terms` checked in page text by `capture.py` | Catches background leakage and build notes like "Future-state concept" |

## Models

- Run every persona on at least 2 models. A single model's taste is indistinguishable from the persona's.
- In a 56-run study (Sept 2026, Claude opus, sonnet, haiku, fable): opus and fable agreed most within persona (Spearman 0.73) and caught copy contradictions inside mock-ups; sonnet read mostly marketing copy; haiku compressed scores, mislabelled concepts, skipped materials, made "no concept covers X" claims that were false, and leaked internal terms. Excluding haiku didn't change the leaderboard.
- Default: `["opus", "fable"]` for follow-ups; add sonnet (and haiku only with its context notes) for a wide first round where model skew itself is a question.
- Treat level differences between models (one marks 0.4 higher) as calibration, not signal. Compare concepts within a run.

## When to run a panel

Run a small panel after the first round of concepts, not after several. In the Sept 2026 study five design rounds (14 concepts) were iterated on the lead's and user's judgement before the first panel; the panel then showed in one pass that every story, console and chatbot concept lost to plain pages on all four models. A 2-model panel after round 1 would have cut two or three design rounds.

## Budget

Measured in the Sept 2026 study (Claude models):

| Panel | Per-run peak context | Per-run time | Wall clock |
|---|---|---|---|
| 14 single-page concepts, 4 models | ~300k (opus, sonnet, fable), ~135k haiku | ~7 min | 56 runs in ~40 min at 20 concurrent |
| 3 multi-page concepts, 2 models | ~140k | under 5 min for most opus runs | 18 runs, 20 concurrent |

Images dominate: roughly 20k tokens per concept page reviewed. Above ~8 single-page concepts, split the panel (each persona reviews a subset in balanced blocks) or drop haiku. Check the user's usage headroom before a large panel: a session usage limit cut off 10 of 18 runs mid-review in round 2 (they resumed cleanly with `runs.py resume`).

## Running

- **Fix the model matrix before launching.** Adding models after a first wave meant renaming files and re-queuing 42 runs. Decide personas x models up front.
- **Pilot first.** Launch one persona on each model, read the files as they land, and fix the materials or instructions before launching the rest. In Sept 2026 the first finished run exposed a false "content cut off" claim and invented concept titles; the fixes (accuracy rules, label discipline) were then added mid-panel, which is a protocol change the analysts had to account for. A pilot moves that change before any real run.
- **Record agent ids** with `runs.py mark` as each run launches, so a resume after compaction or a usage limit goes to the right agent.
- Claude Code allows about 20 background subagents at once. Use `runs.py next --limit 20 --running <ids>` to fill free slots; launch each with the Agent tool, `run_in_background: true`, the run's `model`, and the prompt text verbatim.
- If a run is interrupted (usage limit, crash), resume the same agent with SendMessage ("continue from where you stopped; don't repeat finished sections"). Then run `check_runs.py`: resumed runs sometimes duplicate a section.
- Harnesses may block subagents from writing files that look like reports (for example `SUMMARY.md`). Persona files usually save fine; for analyst output, ask for the document as the reply and save it with `extract_agent_reply.py`.

## Lead review of finished runs

- Read the first few files of each model as they land. Check suspicious claims ("no concept covers X", "content was cut off", "04 is a repeat of 06") against the materials before relying on them, and log each in `analysis/lead-notes.md` for the analysts rather than silently correcting.
- Send a run back only for a blocking error (a skipped or mislabelled concept). Re-scoring after a redo tends to produce flat scores; mark it low confidence instead of iterating.
- Don't verify reported rendering defects on concepts that will be rebuilt. List them as "reported, not verified" in the synthesis; the user judged a verification pass not worth the time.

## Capture lessons

- Collapsed content (FAQ accordions, tabs) is invisible to `innerText` unless expanded. `capture.py` opens `<details>` and clicks `aria-expanded="false"` before extracting text.
- Scroll-reveal sections render blank if screenshots are taken without scrolling. `capture.py` scrolls in steps and waits; still look at one sheet per concept before launching.
- Animations captured mid-way (a calculator at $0, a clock over text, counts mid-tween) were reported as defects in 20+ runs. Set `capture.media` to `"light reduced-motion"` when the concepts respect reduced motion, or give animations time to settle.
- Interactive switches (industry, country, audience toggles) split the panel: models that clicked them rated the concept differently from those that didn't, and aggregator rankings swung on it. Capture each variant with `states` in study.json so every run sees it.
- Montage sheets can repeat the last screen when the page is shorter than the final 2x2 slot; panellists report it as a defect. Mention it in `context_notes` if it happens.
- Remove build notes and placeholder markers from concepts, or declare them in `context_notes`.
- Names and towns in concept demo content that match a persona bias that persona. Check the roster against the concepts.

## Designing concepts for a panel

- Concepts that share a demo story (the same client across three concepts) scored lower when read later: repetition fatigue cost one concept 1.3 points. Give each concept its own cast.
- Make concepts in a round differ in structure, not message, so the panel measures one thing. Round 2's three concepts shared most copy, so the results measured structure and order.
- A build note in a footer ("Future-state concept") was read literally as "none of this exists" and moved one concept from first to seventh for a compliance reader.
- Use `assets/next-round-brief.md` to brief the next design round from the synthesis.

## Analysis lessons

- Report differences under about 0.4 points as ties for panels under ~20 runs.
- Next step, Why care and Relevance usually track Overall most closely; Visual and Trust move it less. Check `What drives Overall` in quant.md rather than assuming.
- Rankings sometimes contradict the run's own scores (`check_runs.py` flags these). Use Borda from rankings alongside mean scores.
- Check `Model agreement by persona` in quant.md. Personas whose models pick different winners (the aggregator, compliance, asset finance and NZ personas in Sept 2026, Spearman under 0.25) are unsettled: report their preferences as model-dependent, not as that segment's view.
- Comparing rounds is directional only. A small round of strong, similar concepts scores lower than a wide round whose weak concepts flattered the winners; compare factor changes (Structure fell 1.4 while Trust rose), not overall levels.
- Split panels for the synthesis between two analysts by persona (not by model), so each sees all models of a persona and can separate persona signal from model taste.
- The persona-fit table (mean of `fit_factors` on the strongest concepts) is the ICP signal: it says which profile the best version of the offer resonates with. Pair it with each persona's "What I'd need to see to say yes" before naming an ICP, and call it a hypothesis for real customer interviews.
- Simulated buyers read more than real ones. Researcher notes consistently said a real reader would give it about 60 seconds, so weight first-screen findings up.
