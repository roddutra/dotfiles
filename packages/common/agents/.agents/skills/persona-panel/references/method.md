# Method: bias controls, models, limits and lessons learned

## Bias controls

| Control | How | Why |
|---|---|---|
| Neutral labels | `init_study.py` copies each concept to `panel/sites/concept-<L>/` with a shuffled label; the key lives outside `panel/` | Folder names like `13-before-and-after` leak the designer's intent |
| Randomised order | Seeded per persona, identical across that persona's models | Removes order and fatigue effects without confounding model comparisons |
| Isolation | The launcher starts each panellist in `panel/` and switches off instruction files, memory, hooks, plugins and MCP servers where the harness has a switch (`references/runners.md`) | Panellists that inherited project instructions leaked internal terms into reviews |
| Sandboxed reading | Run prompt restricts reading to `panel/`; "ignore background in your system context" | No harness's isolation is complete, and `launch.py plan` lists what each could not switch off |
| No cross-talk | "Do not read any other persona file"; the launcher records a persona file changed by another run | Runs otherwise copy each other's opinions |
| Cold rounds | Follow-up rounds get no results from earlier rounds | Prior results anchor scores and themes |
| Placeholder notes | `context_notes` states what is fictitious or placeholder (prices, demo company) | Panellists judge everything literally, including placeholder prices and build notes |
| Leak scan | `leak_terms` checked by `check_runs.py`; `forbidden_terms` checked in page text by `capture.py` | Catches background leakage and build notes like "Future-state concept" |

The working directory's full path is in every panellist's context on both runners. Give the study folders neutral names.

## Models

- Run every persona on at least 2 models. A single model's taste is indistinguishable from the persona's.
- Use models from two vendors when both runners are available. Until October 2026 every panel ran on one vendor's models, so agreement between models has only been measured within a vendor. `analyze.py` compares every pair of model keys, across vendors too.
- Treat level differences between models (one marks 0.4 higher) as calibration, not signal. This matters more across vendors: a new model may mark higher or lower throughout, compress its scores, skip materials or invent claims. Compare concepts within a run, and read rankings and Borda beside mean scores.
- Pilot every new model entry before the panel (`launch.py pilot`) and read its file against the materials. When a model needs tighter instructions, add `model_notes` to `study.json`, keyed by model key or model name: each note becomes a line in that model's run prompts.
- In a 56-run study (Sept 2026, Claude opus, sonnet, haiku, fable): opus and fable agreed most within persona (Spearman 0.73) and caught copy contradictions inside mock-ups; sonnet read mostly marketing copy; haiku compressed scores, mislabelled concepts, skipped materials, made "no concept covers X" claims that were false, and leaked internal terms. Excluding haiku didn't change the leaderboard.
- Default on the `claude` runner: `["opus", "fable"]` for follow-ups; add sonnet (and haiku only with its model notes) for a wide first round where model skew itself is a question.
- A model entry without `model` uses the harness's default, which depends on the account. Name the model when rounds must compare.
- Capabilities differ between runners. When one runner can browse and another cannot, set `"browse": false` so every panellist works from the same materials (see the switches lesson under Capture).

## What agent panellists add (October 2026 trial)

On 12 October 2026 one home page from the Sept study was run through Althing, an open-source panel tool, with the same nine personas on the same model. Its panellists are single text completions: they cannot open a file, look at a screenshot or choose another page.

- The copy findings largely matched the skill's.
- Overall scores averaged 6.1 against 8.2. The four personas who fell furthest were the ones whose questions are answered on pages the text panel could not open.
- The text-only readers caught copy contradictions that the visual panel missed, in about four minutes.

What follows from it:

- Panellists that can open files and choose pages are the skill's advantage. A low score from a run that could not see the page with the answer says nothing about that page, so check what a low-scoring run opened before relying on it.
- A quick text-only read is worth having beside a full panel, for copy contradictions. The skill has no text-only pass yet.

## When to run a panel

Run a small panel after the first round of concepts, not after several. In the Sept 2026 study five design rounds (14 concepts) were iterated on the lead's and user's judgement before the first panel; the panel then showed in one pass that every story, console and chatbot concept lost to plain pages on all four models. A 2-model panel after round 1 would have cut two or three design rounds.

## Limits and the plan

Every run has two limits, and they cover all its attempts: the first, the retry and every resume.

| Limit | Enforced by | Default |
|---|---|---|
| `minutes` | Each run's own watchdog process, on every runner. At the limit the process gets a stop signal, 10 seconds to finish its write (`--grace`), then is killed | 15 per run, 30 per synthesis job |
| `budget_usd` | The harness, on runners with a budget cap. Elsewhere only the time limit bounds a run | $2 per run, $5 for the synthesis pool |

- **Set limits from the materials.** A 14-concept run took about 7 minutes in Sept 2026. Raise one slow model entry with `limits.overrides` instead of raising everyone.
- **The synthesis pool is separate.** It is divided equally among the analysts and the writer, each share a cap, and panellist runs never spend it.
- **Read `launch.py plan` before anything starts, and again after the pilot.** It works before scaffolding and capture too, and says what is missing.
- **The estimate is a forecast.** Before any run has finished it is a token figure only (about 20k tokens of context per concept page, times the pages), with no dollar figure, because the skill keeps no price tables. After a pilot it is the mean of what each model entry's finished runs reported, times the runs to go. A pilot is one run per model entry, so treat it as rough.
- **Billed tokens are several times the context figure.** Every turn re-reads the context, mostly from cache: one ten-command run in discovery reported 182,000 input tokens, 167,000 of them cached. Expect the pilot's figure to be well above the pre-pilot one.
- **The ceiling is a maximum only when every run and job has an enforced cap.** Otherwise it is labelled an estimate and the uncapped runs are left out of it.
- **Read the ceiling's caveats.** The plan never calls the figure guaranteed without them. A cap checked after each turn (the `claude` runner) can be overshot by one turn. A process stopped at its time limit, or by `stop`, can end before it reports what it spent: `status` and `analysis/usage.md` show "not reported (process was stopped)", and until its session is resumed and reports its total, the attempt that resumes it can be given more budget than is left.
- **Dollar figures are list-price equivalents** under a subscription login: how much allowance is used, not what is paid.
- **Confirm three things with the user from the plan:** the estimate and ceiling, which provider receives the materials, and each runner's gaps (no budget cap, no browser, what it could not switch off). The plan also names any environment variable that can change who is billed.
- **`resume --extend` breaks the ceiling.** It gives a `limited` run one more allowance. `plan` and `status` then say the ceiling no longer holds.

## Budget

Measured in the Sept 2026 study (Claude models, native mode):

| Panel | Per-run peak context | Per-run time | Wall clock |
|---|---|---|---|
| 14 single-page concepts, 4 models | ~300k (opus, sonnet, fable), ~135k haiku | ~7 min | 56 runs in ~40 min at 20 concurrent |
| 3 multi-page concepts, 2 models | ~140k | under 5 min for most opus runs | 18 runs, 20 concurrent |

- Images dominate: roughly 20k tokens per concept page reviewed. Above ~8 single-page concepts, split the panel (each persona reviews a subset in balanced blocks) or drop haiku.
- Check the user's usage headroom before a large panel. A session usage limit cut off 10 of 18 runs mid-review in round 2, and they resumed cleanly. The launcher now marks such runs `blocked`, stops new launches on that runner only, and `resume` continues them once the limit lifts.
- `analysis/usage.md` is the record of what was used: per run, per role, per model key and in total, rewritten after every process that ends. It says "not reported" where a harness gave no figure (the `codex` runner reports tokens only), and "not reported (process was stopped)" where the launcher stopped a process before it reported: that usage is unknown, not zero. Give the user the total when reporting, with what is missing from it.

## Running

- **Fix the model matrix before launching.** Adding models after a first wave meant renaming files and re-queuing 42 runs. `init_study.py --force` resets every run. Decide personas x models up front.
- **Pilot first.** `launch.py pilot` runs the first persona on each model entry. Read the files as they land, and fix the materials or instructions before running the rest. In Sept 2026 the first finished run exposed a false "content cut off" claim and invented concept titles; the fixes (accuracy rules, label discipline) were then added mid-panel, which is a protocol change the analysts had to account for. A pilot moves that change before any real run. Pilot runs that need no fix count as panel runs: `run` starts only the rest.
- **The launcher is the scheduler.** It keeps each runner at its concurrency (`runners.<name>.concurrency`), records each session in `runs.json`, and writes that file after every state change. Nothing depends on the lead's context, so compaction loses nothing.
- **A killed launcher loses nothing and unbounds nothing.** Each run's watchdog enforces its time limit and records how the run ended, whether or not a launcher is alive. The next `run`, `resume` or `stop` adopts the live runs and settles the finished ones from those records, without starting a duplicate. Only a launcher starts queued runs, so run it again to carry on.
- **`resume` says when a session no longer exists.** A run whose harness has lost its session is started afresh when it wrote nothing. With sections written it is left alone: finish it by hand, or reset it.
- **`run` retries a failed run once.** After a second failure, read its reason in `status` and its output in `logs/` before running it again.
- **A missing or signed-out CLI stops the whole command.** A panel short of a model is a different study. `--allow-missing` goes ahead without that runner and leaves its runs untouched.
- **After a resume, run `check_runs.py`.** Resumed runs sometimes duplicate a section.
- **A usage limit, rate limit or capacity refusal stops one runner.** Its runs become `blocked` with the harness's own message as the reason, other runners carry on, and `status` shows when a limit lifts if the harness said.
- **A CLI that never ran is not a failure.** When a process exits with an error before printing anything, the launcher says "could not be started", records no attempt and starts nothing more on that runner in the command. It happens when the lead's sandbox lets a CLI start and then refuses what it needs: run `launch.py` from a terminal (`references/runners.md`).

Native mode has its own running notes in `references/runners.md`.

## Run states and the analysis

| State | What happened | Next | In the analysis |
|---|---|---|---|
| `done` | Every concept is scored and the final sections are written | none | Every table |
| `partial` | The process ended with some sections written | `resume` | "Incomplete runs" only |
| `limited` | Stopped at its time or budget limit | Read the file, then `resume --runs <ids> --extend` if it is worth more | "Incomplete runs" only |
| `blocked` | The harness reported a usage limit, rate limit or capacity refusal | `resume` once it takes requests again | "Incomplete runs" only; analysts wait unless `--allow-incomplete` |
| `failed` | The process ended with nothing written | `run` | "Incomplete runs" only |

- **The persona file decides `done`**, never the exit code.
- **Incomplete runs stay out of the headline tables** because a run that stopped early scored only the first concepts in its review order, and concepts are compared within a run. Their Overall scores appear in the "Incomplete runs" table of `quant.md` and nowhere else.
- **Report "N of M runs complete"** with the results. A persona left with one complete model has no model agreement, so its preference is one model's taste.
- **Several `limited` runs on one model entry** point at the entry, not the runs: raise its limit with `limits.overrides`, or cut what it views with `model_notes`, before extending run by run.
- **Analysts are told which runs are incomplete.** They quote what such a run wrote as partial evidence and never count it as a full review.
- **A persona file changed by another run** is a blocking problem in `check_runs.py`. Once dealt with, take its entry out of `logs/modifications.json`.

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
- With fewer than three concepts there is no Spearman figure for model agreement. The model pairs and "Same top" are still shown, and "Same top" is then the only agreement signal.
- Comparing rounds is directional only. A small round of strong, similar concepts scores lower than a wide round whose weak concepts flattered the winners; compare factor changes (Structure fell 1.4 while Trust rose), not overall levels.
- The synthesis is split between two analysts by persona (not by model), so each sees all models of a persona and can separate persona signal from model taste. The launcher does this when `synthesis.analysts` is 2.
- The persona-fit table (mean of `fit_factors` on the strongest concepts) is the ICP signal: it says which profile the best version of the offer resonates with. Pair it with each persona's "What I'd need to see to say yes" before naming an ICP, and call it a hypothesis for real customer interviews.
- Simulated buyers read more than real ones. Researcher notes consistently said a real reader would give it about 60 seconds, so weight first-screen findings up.
