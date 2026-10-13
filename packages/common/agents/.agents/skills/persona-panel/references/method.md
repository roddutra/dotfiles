# Method: bias controls, models, limits and lessons learned

## Bias controls

| Control | How | Why |
|---|---|---|
| Neutral labels | `init_study.py` copies each site to `concept-<L>/` with a shuffled label, and `capture.py` writes every kind of concept to `panel/materials/concept-<L>/`, a file as `item-<NN>`; the key lives outside `panel/`. The site copies, which are page source under its own file names, are in `panel/sites/` only when panellists browse, and in `<study>/sites/` otherwise | Folder names like `13-before-and-after` leak the designer's intent, and so do file names and URLs |
| Randomised order | Seeded per persona, identical across that persona's models and replicates. A variant takes its parent's order. `init_study.py` and `plan` warn when the seed gives every persona the same order: set another `seed` | Removes order and fatigue effects without confounding model comparisons, or a variant's comparison with its parent |
| Isolation | The launcher starts each panellist in `panel/` and switches off instruction files, memory, hooks, plugins and MCP servers where the harness has a switch (`references/runners.md`) | Panellists that inherited project instructions leaked internal terms into reviews |
| Sandboxed reading | Run prompt restricts reading to `panel/`; "ignore background in your system context" | No harness's isolation is complete, and `launch.py plan` lists what each could not switch off |
| No cross-talk | "Do not read any other persona file"; the launcher records a persona file changed by another run | Runs otherwise copy each other's opinions |
| Cold rounds | Follow-up rounds get no results from earlier rounds | Prior results anchor scores and themes |
| Placeholder notes | `context_notes` states what is fictitious or placeholder (prices, demo company) | Panellists judge everything literally, including placeholder prices and build notes |
| Leak scan | `leak_terms` checked by `check_runs.py`; `forbidden_terms` checked in page text by `capture.py` | Catches background leakage and build notes like "Future-state concept" |
| Brief kept out | `init_study.py` refuses to scaffold while a copy of `study-brief.md` is under `panel/` or in a concept folder, by name or by content. Every script refuses one in `synthesis.context_files` | The brief holds the team's hypotheses, and an analyst who knows them tends to find them |
| Neutral follow-ups | A follow-up question reveals no other panellist's answer, no result and nothing the team hopes to hear; `followup.py` sends one question, word for word, to every run named | A leading question gets the answer it asks for |

The working directory's full path is in every panellist's context on every runner. Give the study folders neutral names.

Each harness's own default system prompt also stays in a panellist's context. That is deliberate: replacing it was tested and changed nothing in the research output (`references/runners.md`, System prompt).

## Models

- Run every persona on at least 2 models. A single model's taste is indistinguishable from the persona's.
- Use models from two vendors when runners for both are available. Until October 2026 every panel ran on one vendor's models, so agreement between models has only been measured within a vendor. `analyze.py` compares every pair of model keys, across vendors too.
- Treat level differences between models (one marks 0.4 higher) as calibration, not signal. This matters more across vendors: a new model may mark higher or lower throughout, compress its scores, skip materials or invent claims. Compare concepts within a run, and read rankings and Borda beside mean scores.
- Pilot every new model entry before the panel (`launch.py pilot`) and read its file against the materials. When a model needs tighter instructions, add `model_notes` to `study.json`, keyed by model key or model name: each note becomes a line in that model's run prompts.
- In a 56-run study (Sept 2026, Claude opus, sonnet, haiku, fable): opus and fable agreed most within persona (Spearman 0.73) and caught copy contradictions inside mock-ups; sonnet read mostly marketing copy; haiku compressed scores, mislabelled concepts, skipped materials, made "no concept covers X" claims that were false, and leaked internal terms. Excluding haiku didn't change the leaderboard.
- Default on the `claude` runner: `["opus", "fable"]` for follow-ups; add sonnet (and haiku only with its model notes) for a wide first round where model skew itself is a question.
- A model entry without `model` uses the harness's default, which depends on the account. Name the model when rounds must compare.
- A model reached through the `pi` runner, on a local or OpenAI-compatible endpoint above all, is a new model every time: in the pilot, check that it quotes text that appears only in a screenshot, since a model wrongly listed as reading images reviews without them and says nothing. Expect to need `model_notes` (`references/runners.md`, `pi`).
- Capabilities differ between runners. Every runner of the skill can browse, each with gaps of its own, which the plan lists. If a runner that cannot browse is ever in the panel, set `"browse": false` so every panellist works from the same materials (see the switches lesson under Capture).

## What agent panellists add (October 2026 trial)

On 12 October 2026 one home page from the Sept study was run through Althing, an open-source panel tool, with the same nine personas on the same model. Its panellists are single text completions: they cannot open a file, look at a screenshot or choose another page.

- The copy findings largely matched the skill's.
- Overall scores averaged 6.1 against 8.2. The four personas who fell furthest were the ones whose questions are answered on pages the text panel could not open.
- The text-only readers caught copy contradictions that the visual panel missed, in about four minutes.

What follows from it:

- Panellists that can open files and choose pages are the skill's advantage. A low score from a run that could not see the page with the answer says nothing about that page, so check what a low-scoring run opened before relying on it.
- A quick text-only read is worth having beside a full panel, for copy contradictions: the text-only pass below.

## Text-only pass

`"materials": "text"` in `study.json` makes a study a quick check of the copy, run before the full panel or beside it.

- **What changes.** Panellists read each page's `page-text.txt` and nothing else: no sheets, no screenshots and no browser, whatever `browse` says. They are told they cannot see the design and must not comment on it.
- **Factors.** The factors that need the design are left out of the templates, the scores and the analysis: `visual` and `mobile`, and any custom factor with `"needs_design": true`. One named in `fit_factors` is dropped from there too, and `plan` notes it.
- **Its own study directory.** Its scores do not compare with a full panel's, so never pool them or report one against the other. In the October 2026 trial the text panel averaged 6.1 Overall against 8.2.
- **When to use it.** Once the copy is drafted and before paying for a full panel, because copy contradictions are cheaper to fix first. It is also the only kind of study for a model that reads no images.
- **What it finds.** Contradictions between lines, claims nobody believes, jargon and unanswered questions. The trial's text-only readers caught contradictions the visual panel missed, in about four minutes.
- **What it cannot find.** Anything about layout, visual design or mobile. In the trial the personas whose scores fell furthest were the ones whose questions are answered on pages they could not open, so capture every page a prospect would open, and check what a low-scoring run read.
- **The flattened-page artefact.** `page-text.txt` is the page in one column: navigation and footer labels repeat, and a label, number or button loses the layout that explains it. The instructions tell panellists not to report either, and the briefs tell the analysts and the writer, whose method section must name it. Discount any that slip through.
- **Capture** still renders each page in a browser, writes the text only and removes the images of an earlier capture. The site copies are in `<study>/sites/`, outside `panel/`, as in every study that does not browse, so no run can open a page or its source. Read one `page-text.txt` per concept before launching.
- **The plan** has no token figure for a text-only run until a pilot has measured one.

## When to run a panel

Run a small panel after the first round of concepts, not after several. In the Sept 2026 study five design rounds (14 concepts) were iterated on the lead's and user's judgement before the first panel; the panel then showed in one pass that every story, console and chatbot concept lost to plain pages on all four models. A 2-model panel after round 1 would have cut two or three design rounds.

## Replicates and variants

Both are set in `study.json` before scaffolding, and both add runs: a study has personas x model entries x replicates.

**Replicates** (`"replicates": 2`) repeat every run as `<pid>-<key>-r2`: the same persona, model and review order, in a session of its own.

- **Use them as a stability check,** when a decision rests on a narrow gap or on one persona's preference. Two replicates double the runs, so check stability on a small panel.
- **They are not more people.** `analyze.py` counts replicates as separate runs and never merges them, so every run count in the leaderboard includes them. A replicate is the same persona and model asked again.
- **"Replicate spread" in `quant.md`** compares one persona's complete replicates on one model key, pair by pair:
  - Spearman across their Overall scores, with three or more concepts
  - the share of concepts given the same Overall
  - the mean absolute difference in Overall per concept
  - the concept each replicate put first, and whether they agree
- **Read it beside "Model agreement by persona".** A gap between models or concepts no wider than the mean absolute difference between replicates is noise. A persona whose replicates put different concepts first is unsettled on that model, whatever the models agree on.

**Variants** are personas with `"variant_of": "<pid>"`: the parent with one trait changed, written by the lead, to test what that trait does (`references/personas.md`).

- **A variant is a persona like any other,** with its own runs and files.
- **A variant reviews in its parent's order.** `init_study.py` seeds the order by the parent's id, so order is no part of the difference between the two. `key.md` marks the variant.
- **"Variants" in `quant.md`** shows parent / variant (difference) for mean Overall on the strongest concepts and for persona fit, over the complete runs on the model keys both have. Check its "Differs in" column names the one trait you changed. The variant also sits under its parent in the persona matrix and the persona-fit table, with the difference in brackets.
- **Everywhere else a variant counts as a persona of its own,** so the parent's type has double weight in the leaderboard, the factor means and its segment.
  - A variant that stands for real people in the audience can stay in the headline.
  - One that exists only to test a trait should stay out of it: report the headline from `analyze.py <study> --exclude-persona <id>`, which writes `quant-no-<id>.md` beside `quant.md`. The option repeats, or takes ids separated by commas, and leaves the persona out of every table, the run counts and the tallies.
  - Read "Variants" in the unfiltered `quant.md`. A view that leaves the variant out has no pair to compare.
- **A difference under about 0.4 is a tie,** as for any small panel. A parent and a variant on two models are two runs each.

## Limits and the plan

Every run has two limits, and they cover all its attempts: the first, the retry and every resume. A usability run has a third, a step limit for each task (`references/usability.md`).

| Limit | Enforced by | Default |
|---|---|---|
| `minutes` | Each run's own watchdog process, on every runner. At the limit the process gets a stop signal, 10 seconds to finish its write (`--grace`), then is killed | 15 per run (in a usability study, 30 seconds for each step its tasks permit plus 5 minutes), 30 per synthesis job, 5 per follow-up question |
| `budget_usd` | The harness, on runners with a budget cap. Elsewhere only the time limit bounds a run | $2 per run, $5 for the synthesis pool, $0.50 per follow-up question |

- **Set limits from the materials.** A 14-concept run took about 7 minutes in Sept 2026. Raise one slow model entry with `limits.overrides` instead of raising everyone.
- **The synthesis pool is separate.** It is divided equally among the analysts and the writer, each share a cap, and panellist runs never spend it.
- **Follow-up questions are separate too, and outside the ceiling.** Each run asked has `limits.followup` for each question, apart from its run limits. `plan` and `status` say how many were asked.
- **Read `launch.py plan` before anything starts, and again after the pilot.** It works before scaffolding and capture too, and says what is missing. `run`, `pilot` and `resume` start no panellist run while a concept has nothing captured or is short of a page, state or item: they name the concept, what it lacks and `capture.py`.
- **The estimate is a forecast.** Before any run has finished it is a token figure only (about 20k tokens of context per concept page, times what a run opens: each web page, each page of a PDF and each supplied image counts as one), with no dollar figure, because the skill keeps no price tables. After a pilot it is the mean of what each model entry's finished runs reported, times the runs to go. A pilot is one run per model entry, so treat it as rough.
- **A run whose reported usage is known to be short counts for the time only.** That is a finished run with a process that was stopped before reporting, or whose usage came in one total with a follow-up's. The plan says how many it left out of the mean tokens and cost, so a run measures the same whether or not it was asked a follow-up.
- **Billed tokens are several times the context figure.** Every turn re-reads the context, mostly from cache: one ten-command run in discovery reported 182,000 input tokens, 167,000 of them cached. Expect the pilot's figure to be well above the pre-pilot one.
- **The ceiling is a maximum only when every run and job has an enforced cap.** Otherwise it is labelled an estimate and the uncapped runs are left out of it.
- **Read the ceiling's caveats.** The plan never calls the figure guaranteed without them. A cap checked after each turn (the `claude` runner) can be overshot by one turn. A process stopped at its time limit, or by `stop`, can end before it reports what it spent: `status` and `analysis/usage.md` show "not reported (process was stopped)", and until its session is resumed and reports its total, the attempt that resumes it can be given more budget than is left.
- **Dollar figures are list-price equivalents** under a subscription login: how much allowance is used, not what is paid.
- **Confirm three things with the user from the plan:** the estimate and ceiling, which provider receives the materials, and each runner's gaps (no budget cap, what it could not switch off, what browsing opens). The plan also names any environment variable that can change who is billed.
- **Browsing gives each run in flight a browser of its own,** about 330 MiB, which the launcher starts before the run and stops after it (`references/runners.md`, Browser sessions). The plan gives the total for the concurrency in force, and says what the session refuses: a panellist can click, type and take screenshots, and cannot run scripts or read page source, cookies or storage. On a small machine lower `runners.<name>.concurrency`. Set `"browse": false` when the captured materials are enough: a Codex run that may browse has network access in its shell.
- **`plan`, `run`, `pilot` and `resume` need the `agent-browser` CLI on PATH** when a run may browse. The plan names its absence as a problem, and the others refuse.
- **`resume --extend` breaks the ceiling.** It gives a `limited` run one more allowance. `plan` and `status` then say the ceiling no longer holds.

## Budget

Measured in the Sept 2026 study (Claude models, native mode):

| Panel | Per-run peak context | Per-run time | Wall clock |
|---|---|---|---|
| 14 single-page concepts, 4 models | ~300k (opus, sonnet, fable), ~135k haiku | ~7 min | 56 runs in ~40 min at 20 concurrent |
| 3 multi-page concepts, 2 models | ~140k | under 5 min for most opus runs | 18 runs, 20 concurrent |

- Images dominate: roughly 20k tokens per concept page reviewed. Above ~8 single-page concepts, split the panel (each persona reviews a subset in balanced blocks) or drop haiku.
- Check the user's usage headroom before a large panel. A session usage limit cut off 10 of 18 runs mid-review in round 2, and they resumed cleanly. The launcher now marks such runs `blocked`, stops new launches on that runner only, and `resume` continues them once the limit lifts.
- `analysis/usage.md` is the record of what was used: per run, per role, per model key and in total, rewritten after every process that ends. What follow-up questions used is under the role "follow-up" and in no run's own row. It says "not reported" where a harness gave no figure (the `codex` runner reports tokens only), and "not reported (process was stopped)" where the launcher stopped a process before it reported: that usage is unknown, not zero. Give the user the total when reporting, with what is missing from it.
- "unallocated" in `analysis/usage.md` and `status` is one total that a follow-up reported for itself and for a process of its run that had been stopped before reporting. Nothing can split it: it is in the total, under the role "unallocated", and in neither the run's row nor the follow-up's.

## Running

- **Fix the model matrix before launching.** Adding models after a first wave meant renaming files and re-queuing 42 runs. `init_study.py --force` resets every run. Decide personas x models up front.
- **`init_study.py --force` deletes no session.** It replaces `runs.json`, so it carries the sessions of the replaced runs over to `logs/earlier-sessions.json`. `status` and `plan` say how many are on that record, and `purge-sessions` without `--runs` deletes them with the rest.
- **`init_study.py --force` is refused while the study is in use:** while a launcher has it, or a run, job or follow-up still has a process at work. Stop them first with `launch.py <study> stop`.
- **Pilot first.** `launch.py pilot` runs the first persona on each model entry. Read the files as they land, and fix the materials or instructions before running the rest. In Sept 2026 the first finished run exposed a false "content cut off" claim and invented concept titles; the fixes (accuracy rules, label discipline) were then added mid-panel, which is a protocol change the analysts had to account for. A pilot moves that change before any real run. Pilot runs that need no fix count as panel runs: `run` starts only the rest.
- **The launcher is the scheduler.** It keeps each runner at its concurrency (`runners.<name>.concurrency`), records each session in `runs.json`, and writes that file after every state change. Nothing depends on the lead's context, so compaction loses nothing.
- **A killed launcher loses nothing and unbounds nothing.** Each run's watchdog enforces its time limit and records how the run ended, whether or not a launcher is alive. The next `run`, `resume` or `stop` adopts the live runs and settles the finished ones from those records, without starting a duplicate. Only a launcher starts queued runs, so run it again to carry on.
- **`resume` says when a session no longer exists.** A run whose harness has lost its session is started afresh when it wrote nothing. With sections written it is left alone: finish it by hand, or reset it.
- **`run` retries a failed run once.** After a second failure, read its reason in `status` and its output in `logs/` before running it again.
- **A missing or signed-out CLI stops the whole command.** A panel short of a model is a different study. `--allow-missing` goes ahead without that runner and leaves its runs untouched.
- **So does a CLI that the launcher's shell cannot run.** A sandboxed shell tool can leave a CLI installed, signed in and unable to do a run. `plan` shows such a runner as `CANNOT BE USED` with what it cannot do there, and nothing starts. Ask your harness to run the command outside its sandbox, or run `launch.py` from a terminal (`references/runners.md`, When the lead's own sandbox blocks the launcher).
- **After a resume, run `check_runs.py`.** Resumed runs sometimes duplicate a section.
- **A usage limit, rate limit or capacity refusal stops one runner.** Its runs become `blocked` with the harness's own message as the reason, other runners carry on, and `status` shows when a limit lifts if the harness said.
- **A resumed run that browses gets a new browser,** on a blank page, and its resume message says so. Nothing it had opened or typed is still there.
- **A browser session that cannot be started is not a failure either.** The CLI never runs: the launcher says "could not be started" with the reason, marks nothing failed, and starts nothing more on that runner in the command. `logs/<run id>.<attempt>.hooks` has what the session printed.
- **A killed watchdog leaves its browser running,** about 330 MiB of it. The next launcher command stops it, and `status` says what was found.
- **A CLI that never ran is not a failure.** When a process exits with an error before printing anything, the launcher says "could not be started", records no attempt and starts nothing more on that runner in the command. It happens when the lead's sandbox lets a CLI start and then refuses what it needs: ask your harness to run the command outside its sandbox, or run `launch.py` from a terminal (`references/runners.md`).
- **A run that shows its CLI cannot work from this shell is not retried.** Its CLI could not build a sandbox of its own, or could not reach its provider. The run is `failed` with the CLI's words as the reason, and nothing more starts on that runner in the command. The way out is the same.
- **"session not saved" means the run cannot be continued.** Its harness kept no session for it, so `resume` and a follow-up are refused. A `done` run is still done, and its file counts.

Native mode has its own running notes in `references/runners.md`.

## Run states and the analysis

| State | What happened | Next | In the analysis |
|---|---|---|---|
| `done` | Every concept, or every task of a usability study, is scored and the final sections are written | none | Every table |
| `partial` | The process ended with some sections written | `resume` | "Incomplete runs" only |
| `limited` | Stopped at its time or budget limit, or at a task's step limit in a usability study. `limited_by` in `runs.json` and the reason in `status` say which | Read the file, then `resume --runs <ids> --extend` if it is worth more | "Incomplete runs" only. A usability study also counts it in completion, steps and stuck points |
| `blocked` | The harness reported a usage limit, rate limit or capacity refusal | `resume` once it takes requests again | "Incomplete runs" only; analysts wait unless `--allow-incomplete` |
| `failed` | The process ended with nothing written | `run` | "Incomplete runs" only |

- **The persona file decides `done`**, never the exit code.
- **A section without its score row is not scored,** so its run stays `partial`. `resume` names the section and asks for the score table to be added to it, with nothing else changed.
- **Incomplete runs stay out of the headline tables** because a run that stopped early scored only the first concepts in its review order, and concepts are compared within a run. Their Overall scores appear in the "Incomplete runs" table of `quant.md` and nowhere else.
- **Report "N of M runs complete"** with the results. A persona left with one complete model has no model agreement, so its preference is one model's taste.
- **Several `limited` runs on one model entry** point at the entry, not the runs: raise its limit with `limits.overrides`, or cut what it views with `model_notes`, before extending run by run.
- **Analysts are told which runs are incomplete.** They quote what such a run wrote as partial evidence and never count it as a full review.
- **A released run keeps its state.** In a usability study, `launch.py <study> release --runs <ids>` lets go of the test account of an unfinished run you will not continue. `status` shows it as "released by the lead", and `run` and `resume` leave it alone unless it is named with `--released` (`references/usability.md`, Accounts).
- **A persona file changed by another run** is a blocking problem in `check_runs.py`. Once dealt with, take its entry out of `logs/modifications.json`.
- **Only a plain file is a persona file.** A panellist can write anywhere under `panel/`, so every script opens a persona file without following a symbolic link, at its name or at a folder above it, and without waiting, as an open of a FIFO would. A link, a FIFO, a folder or a file that may not be read leaves its run not `done`, gives nothing to the scores or the answers, and is a blocking problem in `check_runs.py`, which names the file and the reason. Put a plain file at the name, or remove what is there. The launcher writes a persona file the same way, so a follow-up is never settled through a link.

## Lead review of finished runs

- Read the first few files of each model as they land. Check suspicious claims ("no concept covers X", "content was cut off", "04 is a repeat of 06") against the materials before relying on them, and log each in `analysis/lead-notes.md` for the analysts rather than silently correcting.
- Send a run back only for a blocking error (a skipped or mislabelled concept). Re-scoring after a redo tends to produce flat scores; mark it low confidence instead of iterating.
- Don't verify reported rendering defects on concepts that will be rebuilt. List them as "reported, not verified" in the synthesis; the user judged a verification pass not worth the time.

## Follow-up questions

`followup.py <study> ask --runs <ids>|all --question-file <file>` puts one question to finished runs, each in the session it reviewed in, so the panellist still has what it read. Each appends a `## Follow-up <n>` section to its own persona file.

- **What they are good for.** An answer that was ambiguous, the reason behind a surprising score, what would change a "no", a question the template did not ask. Ask what a moderator could ask one participant who has seen nothing but the materials.
- **Qualitative only.** An answer is prompted, comes after the scores and was asked only of the runs you chose. No script tallies it and no score or ranking can change. The analysts quote it with the run and the follow-up number and say it was prompted.
- **Leading questions.** A follow-up never reveals another panellist's answer, a result, or what the team hopes to hear. A question that names the answer gets it: "Would a pricing table have helped?" is answered yes. Ask "What, if anything, was missing when you looked for the cost?" instead.
- **One wording for everyone.** One `ask` sends the file's text, word for word, to every run named, so answers to it compare. A reworded question is a new follow-up.
- **Who can be asked.** A panellist run that is `done`, whose session was saved and not purged or lost, on a runner whose CLI is ready and which can still launch the run's model entry: what stops `plan` and `run` (a model no longer listed, a provider no longer signed in) stops a follow-up, before anything is recorded or started. One run named that cannot be asked stops the whole command, with the reason, unless `--skip-unfit`. Ask before `purge-sessions`.
- **Cost.** Each run asked has `limits.followup` for each question: 5 minutes and $0.50 by default, apart from its run limits and outside the plan's ceiling. `--runs all` on a 36-run panel is up to $18 a question on a runner with a budget cap, and bounded only by time on one without. `ask` prints the runs and the most they can use, then starts without waiting. When a ceiling was agreed, run it with `--dry-run` first and show the user: it prints the same lines, starts nothing and records nothing.
- **In a usability study** a follow-up gets no browser. The run's test account is gone, so it answers from its persona file, step log and screenshots.
- **Ask before the analysts.** An analyst's brief lists each question its personas answered, with the runs, and the writer's brief lists them all. A question asked after a job has finished is not in that job's brief. `run --role analyst` and `run --role writer` are refused while a follow-up is not settled.

What is enforced, on a study that runs through runners:

- The persona file is copied before the question. Afterwards it must be that copy plus one appended section headed `## Follow-up <n>`, with no other heading, and its scores, ranking and sections must read as before.
- Anything else is `rejected`: the file is put back from the copy, and what the panellist left is kept in `logs/<run id>.<attempt>.rejected.md`. A file that is no longer a plain file (a symbolic link at its name, say) is rejected too: the copy takes the name, and nothing is read or kept through the link.
- A panellist that replied without writing has its section written from the reply, and the section says so.
- The run stays `done` throughout, and its own time and spend are not touched.
- Nothing reads the persona file for scores or progress until the launcher has settled the question. `status`, `extract_scores.py`, `extract_answers.py` and `check_runs.py` read the copy made before it and name each such run in a line, and `archive.py` refuses the study, as it does while any launcher has it. Let `ask` finish before you analyse.
- A killed `ask` loses nothing. The next launcher command, or `followup.py <study> list`, settles what its processes left, to the outcome the killed launcher had decided or would have, and records the runs it had not reached as `not asked`.

`followup.py <study> list` and `followups.json` give each run's outcome:

| Outcome | What happened | Next |
|---|---|---|
| `answered` | The panellist appended its section and changed nothing else | none |
| `answered from the reply` | It replied without writing, and the launcher wrote the section from the reply | none |
| `rejected` | It changed something else, and the file was put back | Read the rejected file, and ask again if the answer matters |
| `unanswered` | Its process ended with no section and no reply | Ask again |
| `turned away` | Its harness was refusing requests (a usage limit, a rate limit or no capacity) | Ask again once it takes requests |
| `could not start` | Its CLI could not be started, or its session was gone | Fix the CLI and ask again. A run whose session is gone cannot be asked |
| `not asked` | The command stopped, its runner closed or its launcher was killed, before its turn | Ask again |
| `sent by hand` | Native mode: the lead sent it, and nothing was checked | `references/runners.md`, Native mode |

- **Asking again** is a new `ask` with the same question file. It becomes the next follow-up, with the next number.
- **`ask` exits 0** when every run asked has its section, and 1 otherwise.
- **`check_runs.py` notes** a follow-up section that `followups.json` does not record as an answer, and a recorded answer whose section is missing. Neither blocks.

## Capture lessons

- Collapsed content (FAQ accordions, tabs) is invisible to `innerText` unless expanded. `capture.py` opens `<details>` and clicks `aria-expanded="false"` before extracting text.
- Scroll-reveal sections render blank if screenshots are taken without scrolling. `capture.py` scrolls in steps and waits; still look at one sheet per concept before launching.
- Animations captured mid-way (a calculator at $0, a clock over text, counts mid-tween) were reported as defects in 20+ runs. Set `capture.media` to `"light reduced-motion"` when the concepts respect reduced motion, or give animations time to settle.
- Interactive switches (industry, country, audience toggles) split the panel: models that clicked them rated the concept differently from those that didn't, and aggregator rankings swung on it. Capture each variant with `states` in study.json so every run sees it.
- Montage sheets can repeat the last screen when the page is shorter than the final 2x2 slot; panellists report it as a defect. Mention it in `context_notes` if it happens.
- Remove build notes and placeholder markers from concepts, or declare them in `context_notes`.
- Names and towns in concept demo content that match a persona bias that persona. Check the roster against the concepts.

## Concept kinds

A concept is a site folder, a live URL or a set of images and PDFs (`references/runners.md`, Concepts). Each kind has its own traps.

Every kind:

- **A page or item is captured whole or not at all.** One that fails (an address that will not open, a PDF or image that cannot be read) is printed as `FAILED`, the rest are captured, and `capture.py` exits non-zero with the list. An earlier capture of it stays as it was. One never captured has no folder, so the plan lists it as missing and no run starts.
- **Changing `browse` needs `init_study.py --force`:** it moves the site copies into or out of `panel/` and rewrites the instructions. The plan says when the copies are in the wrong place.

Live URLs (`"kind": "url"`):

- **A capture is one moment.** The page can change between capture and runs, and between runs. Capture just before the pilot, and again if the page changes. The plan prints the capture time.
- **Say whether the page is live.** The instructions call site and file concepts drafts. They say nothing either way about a study with a URL, so add a `context_notes` line: a draft on a local host, or the page customers see today.
- **Browsing is off unless `"browse": true`.** With it on, a panellist sees the page as it is at review time, and is told to score from the materials and note any difference. Every visit reaches the site's server and its analytics, and only the instructions stop a panellist submitting a form. Leave it off for a production page unless the interaction is what is being tested.
- **A local host must be serving** during capture, and during the runs when browsing is on.
- **The URL is in the provider's hands** once browsing is on: it is in the instructions every run reads.
- **An error page captures like any other.** `capture.py` warns when the server answers 400 or above. Look at a sheet.

Images and PDFs (`"kind": "files"`):

- **File names leak** the way folder names do ("pricing-v3-FINAL-bold.png"). Panellists see `item-01`, `item-02`, and `key.md` has the names.
- **Order is yours.** List `files` in the order a reader would meet them, or number the names in a folder.
- **No interaction, and no phone view** unless a file shows one. Panellists are told to score a factor they cannot see from what is shown and to say so. Read the Mobile score of such a concept as a guess, drop the factor with a `factors` list, or supply a phone screenshot.
- **An image has no text.** The term scan and "search `page-text.txt`" cover PDFs only, so read the images yourself for build notes.
- **A very tall image** (a full-page export) is also cut into `part-NN.png`, because whatever reads a tall image shrinks it until the text is unreadable. Panellists are told to review it from the parts, in order. Both haiku runs of the first real study opened the whole image instead and could not read it, so the default haiku note now rules the whole image out.
- **A long PDF is cut at `capture.max_pdf_pages`** (default 20), and `capture.py` says so loudly. Panellists are told the materials are complete: raise the limit or add a `context_notes` line.
- **A scanned PDF has no text.** `capture.py` warns, and a text-only study refuses it.
- **PDF text keeps the page's layout,** so a table stays in rows and columns sit side by side.
- **The plan's token estimate is a guess** for files until a pilot has measured one: the method's figure comes from captured web pages, and the plan counts each PDF page and each image as one such page.

Mixing kinds is allowed, since a real round may compare a live page with a mock-up. The comparison is then partly between formats: a mock-up cannot be scrolled or clicked.

- **Format moves scores.** In the first mixed study a PDF scored far lower on Mobile than a screenshot and a live page, and one panellist ranked it down "because it's a PDF".
- **What counts as a different form:** a captured page (site or URL, which are captured alike), image files, and PDF files. A PDF beside a screenshot is a mix, though both are `files`.
- **`quant.md` says so** above "Key numbers" and under "By factor" when forms differ, with each concept's form, and the analyst and writer briefs carry the same caution (`assets/brief-kinds-mixed.md`).
- **`forms.json` keeps each `files` concept's form** (images, PDFs or both) beside `key.md`, so an archived round, which has no source file to tell a PDF from an image, still gets the caution when it is analysed again.
- **The factors most exposed** are the ones marked `needs_design`: Visual design and Mobile by default. Compare them within one form only, or leave them out. Overall and the rankings carry them too, so say so when reporting.

## Single-concept studies

A study with one concept answers "how does this land, and for whom", not "which is better".

- **What changes.** The instructions say there is one design to review. The final sections have no ranking and no score summary, and the persona files have no review order. `check_runs.py` expects no ranking.
- **Set `artefact`** when the study sets `artefact_plural`: the instructions use the singular.
- **What `analyze.py` reports.** "Scores": each factor's mean, median, SD, lowest and highest across runs. Every factor's mean by segment and by model. Persona fit, replicate spread and the answer tallies as usual. No leaderboard, winner, Borda count or order effect.
- **Model agreement** is measured on the one concept: the mean absolute difference between a persona's runs on two models, in Overall and over all factors, and the Spearman across the factor scores the two runs gave. The last says whether the models agree on what is strong and weak, whatever level each marks at. A persona whose models sit 2 points or more apart is unsettled.
- **A level means little alone.** With nothing to compare against, 7.2 is not good or bad: models mark at different levels, and simulated readers are generous. Report which factors are strong and weak, where personas differ, and the quotes. Compare levels only with an earlier round that used the same personas, models and factors, and then only as a direction.
- **Use replicates.** With no ranking to steady the result, the spread between two runs of the same persona and model is the only measure of noise.

## Usability studies

`"type": "usability"` is the other kind of study: panellists attempt tasks in a running local build through a browser, and the analysis reports completion and stuck points instead of a leaderboard. `references/usability.md` covers it: when to use one, designing tasks and success checks, test accounts, the protocol, running, reading the results, safety and how much to trust them.

What carries over from this document: the model advice, limits and the plan, piloting, run states and follow-up questions. What does not: labels, review order, capture, concept kinds, rankings and answer tallies.

## Designing concepts for a panel

- Concepts that share a demo story (the same client across three concepts) scored lower when read later: repetition fatigue cost one concept 1.3 points. Give each concept its own cast.
- Make concepts in a round differ in structure, not message, so the panel measures one thing. Round 2's three concepts shared most copy, so the results measured structure and order.
- A build note in a footer ("Future-state concept") was read literally as "none of this exists" and moved one concept from first to seventh for a compliance reader.
- Use `assets/next-round-brief.md` to brief the next design round from the synthesis.

## Answer tallies

`extract_answers.py <study>` reads every persona file and writes two files. Run it after `extract_scores.py` and before `analyze.py`, and again after any resume.

- `analysis/answers.csv`: one row per run, concept and `find_the_answer` question, with the verdict (Found, Partly or Not found), where the panellist found it, and the entry as written in `raw`.
- `analysis/lines.csv`: four rows per run and concept, one each for the line to keep, the line to cut, the line not believed and the forward answer (yes, no or maybe, who it would go to, and the message).

`analyze.py` then adds three tables to `quant.md`, and leaves them out when the files are missing:

- "Find the answer": the count of each verdict for each question and concept.
- "Forward test": yes, no and maybe for each concept.
- "Lines that recur": the lines more than one run quoted for a concept, with how many quoted each as the line to keep, to cut and not believed.

How to read them:

- **Complete runs only.** An incomplete run's rows stay in the CSVs, with `complete` 0, and are in no table.
- **Nothing is guessed.** An entry not written the way the template asks is `unparsed`, and one the panellist left out is `missing`. Unparsed entries include:
  - an answer that does not start with Found, Partly, Partially or Not found, or that goes straight on to another verdict ("Found, partly")
  - a forward answer that starts with none of yes, no and maybe ("Not yet", "yes/no")
  - a line field with more than one quoted passage
- **Check the unparsed rows by hand.** `extract_answers.py` prints the count, and the tables show it. Filter the CSV for `unparsed`, read `raw`, and report your reading beside the table's counts.
- **Many unparsed entries from one model** point at the model. Add a `model_notes` line for it before the next round.
- **"Lines that recur" matches loosely on form only:** case, quote style, spacing and a closing full stop. A paraphrase or a shorter quotation of the same line counts as a different line, so the analysts still read for those. A line that some runs keep and others cut divides the panel.
- **A stale tally says so.** When the CSVs cover fewer complete runs than the other tables, `quant.md` says to run `extract_answers.py` again.

## Analysis lessons

- Report differences under about 0.4 points as ties for panels under ~20 runs.
- Next step, Why care and Relevance usually track Overall most closely; Visual and Trust move it less. Check `What drives Overall` in quant.md rather than assuming.
- Rankings sometimes contradict the run's own scores (`check_runs.py` flags these). Use Borda from rankings alongside mean scores.
- Check `Model agreement by persona` in quant.md. Personas whose models pick different winners (the aggregator, compliance, asset finance and NZ personas in Sept 2026, Spearman under 0.25) are unsettled: report their preferences as model-dependent, not as that segment's view.
- With fewer than three concepts there is no Spearman figure for model agreement. The model pairs and "Same top" are still shown, and "Same top" is then the only agreement signal. With one concept, see Single-concept studies.
- Comparing rounds is directional only. A small round of strong, similar concepts scores lower than a wide round whose weak concepts flattered the winners; compare factor changes (Structure fell 1.4 while Trust rose), not overall levels.
- The synthesis is split between two analysts by persona (not by model), so each sees all models of a persona and can separate persona signal from model taste. The launcher does this when `synthesis.analysts` is 2.
- The persona-fit table (mean of `fit_factors` on the strongest concepts) is the ICP signal: it says which profile the best version of the offer resonates with. Pair it with each persona's "What I'd need to see to say yes" before naming an ICP, and call it a hypothesis for real customer interviews.
- Simulated buyers read more than real ones. Researcher notes consistently said a real reader would give it about 60 seconds, so weight first-screen findings up.
