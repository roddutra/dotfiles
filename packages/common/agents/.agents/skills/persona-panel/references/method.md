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

## Running

- Claude Code allows about 20 background subagents at once. Use `runs.py next --limit 20 --running <ids>` to fill free slots; launch each with the Agent tool, `run_in_background: true`, the run's `model`, and the prompt text verbatim.
- If a run is interrupted (usage limit, crash), resume the same agent with SendMessage ("continue from where you stopped; don't repeat finished sections"). Then run `check_runs.py`: resumed runs sometimes duplicate a section.
- Harnesses may block subagents from writing files that look like reports (for example `SUMMARY.md`). Persona files usually save fine; for analyst output, ask for the document as the reply and save it with `extract_agent_reply.py`.

## Capture lessons

- Collapsed content (FAQ accordions, tabs) is invisible to `innerText` unless expanded. `capture.py` opens `<details>` and clicks `aria-expanded="false"` before extracting text.
- Scroll-reveal sections render blank if screenshots are taken without scrolling. `capture.py` scrolls in steps and waits; still look at one sheet per concept before launching.
- Montage sheets can repeat the last screen when the page is shorter than the final 2x2 slot; panellists report it as a defect. Mention it in `context_notes` if it happens.
- Remove build notes and placeholder markers from concepts, or declare them in `context_notes`.
- Names and towns in concept demo content that match a persona bias that persona. Check the roster against the concepts.

## Analysis lessons

- Report differences under about 0.4 points as ties for panels under ~20 runs.
- Next step, Why care and Relevance usually track Overall most closely; Visual and Trust move it less. Check `What drives Overall` in quant.md rather than assuming.
- Rankings sometimes contradict the run's own scores (`check_runs.py` flags these). Use Borda from rankings alongside mean scores.
- The persona-fit table (mean of `fit_factors` on the strongest concepts) is the ICP signal: it says which profile the best version of the offer resonates with. Pair it with each persona's "What I'd need to see to say yes" before naming an ICP, and call it a hypothesis for real customer interviews.
- Simulated buyers read more than real ones. Researcher notes consistently said a real reader would give it about 60 seconds, so weight first-screen findings up.
