# Persona panel: other harnesses, limits and wider research

**Status:** Draft. Reviewed by Codex on 12 October 2026 over three rounds and
approved. Not yet approved by Rod; see [Open questions](#open-questions-for-rod).

PRD for extending the `persona-panel` skill
(`packages/common/agents/.agents/skills/persona-panel/`) so that it covers most
of what a separate synthetic research platform would offer:

1. **Runners:** panellists run through any coding agent's headless CLI, with
   Claude Code and Codex first and room for others.
2. **A launcher:** a script starts, limits, tracks and resumes runs, so a panel
   no longer depends on one harness's subagent tool.
3. **Limits and a pre-run plan:** a cap for each run, an estimate before
   anything starts, and a record of what was used.
4. **Wider inputs and study types:** files and live URLs as artefacts, a
   text-only pass, follow-up questions, and task-based usability tests in a
   real browser.

Drafted 12 October 2026.

## Problem

The skill produces useful findings, but four things hold it back.

- **It only runs Claude models.** Runs start through Claude Code's subagent
  tool. The method notes say a single model's taste is indistinguishable from
  the persona's, and every model in a panel today comes from one vendor.
- **The lead agent is the scheduler.** Claude Code allows about 20 background
  subagents, so the lead fills slots by hand from `runs.py next`. A session
  usage limit stopped 10 of 18 runs in the September 2026 study. Resuming
  depends on agent ids the lead recorded with `runs.py mark`.
- **Nothing bounds a run.** There is no budget, time or step limit, and no
  estimate before launch beyond the rule of thumb in `references/method.md`.
- **It reviews one kind of thing.** A concept must be a folder with an
  `index.html`. A PDF, a single screenshot, a live URL or a task in a running
  product are all out of reach.

### Evidence from a trial

On 12 October 2026 one home page from the September study was run through
Althing, an open-source panel tool, with the same nine personas on the same
model. Althing's panellists are single text completions: they cannot open a
file, look at a screenshot or choose another page.

- The copy findings largely matched the skill's.
- Overall scores averaged 6.1 against 8.2. The four personas who fell furthest
  were the ones whose questions are answered on pages the Althing panel could
  not open.
- Text-only readers caught copy contradictions that the visual panel missed,
  in about four minutes.

Two conclusions shape this PRD. Panellists that are agents with tools are the
skill's real advantage, and it is the foundation that browser-based research
needs. A cheap text-only pass is worth having alongside the full panel.

## Goals

- A panel can mix panellists from Claude Code, Codex and at least one harness
  that reaches an OpenAI-compatible endpoint.
- Adding a harness means adding one adapter, with no change to the rest of
  the skill.
- The lead agent can be any harness, and Rod can run the launcher from a
  terminal with no agent at all.
- Every run has a time limit, and a budget limit where the harness can
  enforce one. The plan shows the cost before launch.
- Runs survive usage limits, crashes and context compaction without the lead
  tracking anything in its own context.
- Studies can review files and live URLs, and can test tasks in a running
  product with a login for each participant.
- Existing studies and archives keep loading. The current subagent workflow
  keeps working.

## Non-goals

- **Large surveys.** Hundreds of cheap respondents, answer distributions and
  calibration against human survey data stay with tools built for that, such
  as Althing.
- **A user interface, a hosted service or use by non-technical people.** The
  skill still needs a coding agent or a terminal.
- **Handling credentials for model providers.** Each runner calls a CLI the
  user has already signed in to. The skill never reads, stores or relays a
  provider login or key.
- **Claims of validity.** Output remains a hypothesis to test with real
  people. Nothing here changes that rule.
- **Automatic persona variants written by a model.** Variants are written by
  the lead, as personas are today.
- **Moderated interviews.** Follow-up questions cover the light version.

## Terms

| Term | Meaning |
| --- | --- |
| Harness | A coding agent product: Claude Code, Codex, Pi, OMP, OpenCode, Grok |
| Runner | The skill's adapter for one harness's headless CLI |
| Model entry | One item in `study.json` `models`: a runner, a model, an optional thinking effort, and a short key |
| Run | One persona on one model entry (and one replicate) |
| Lead | The agent, or person, running the study |
| Launcher | `scripts/launch.py`, which starts and supervises runs |
| Native mode | Today's flow: the lead starts runs with its own subagent tool |

## How the parts divide the work

```text
study.json ──> init_study.py ──> panel/, prompts/, runs.json
                                      │
                 launch.py plan ──────┤  estimate, materials per provider, limits
                 launch.py pilot ─────┤  one persona per model entry
                 launch.py run ───────┤  starts CLI processes through runners
                                      │     runners/claude.py   claude -p
                                      │     runners/codex.py    codex exec
                                      │     runners/pi.py       pi -p
                                      ▼
                          panel/personas/*.md   (the result, as today)
                                      │
   check_runs.py, extract_scores.py, extract_answers.py, analyze.py
                                      │
                 launch.py run --role analyst, then the writer
```

The persona file stays the source of truth for whether a run is done.
`runs.json` gains facts only the launcher knows: session id, process state,
attempts, usage and why a run stopped.

## Harness independence

Two separate questions, answered separately.

**Who can lead.** Any harness, or Rod in a terminal.

- `SKILL.md` uses only the common `name` and `description` frontmatter and
  names no harness tool. It says "run in the background with your harness's
  shell tool", not "use the Agent tool".
- Native mode is described once, as an option for a harness that has
  subagents, in a reference file.
- Scripts stay Python 3 standard library, as now. `agent-browser`,
  ImageMagick and Poppler remain optional dependencies that fail with a clear
  message naming the missing tool.
- No script relies on an environment variable a particular harness sets.
- A lead's own sandbox may block starting another CLI or reaching the
  network. The launcher fails soft and says which command was refused.
  Running `launch.py` from a terminal is always available.

**Who can be a panellist.** Any harness with a runner.

A runner is one Python module in `scripts/runners/` exposing the same small
interface:

| Function | Does |
| --- | --- |
| `capabilities()` | What this harness supports: images by path, image attachment, browser use, budget cap, effort levels, resume, usage reporting |
| `launch_command(run, prompt, workdir, limits)` | The argv, stdin and environment for a new run |
| `resume_command(run, session_id, message)` | The same for continuing a run |
| `parse_result(stdout, stderr, exit_code)` | Session id, final reply, usage, and a classified outcome: ok, usage limit, budget reached, error |
| `check()` | Whether the CLI is installed and signed in, without making a model call where possible |

Nothing outside `runners/` contains a harness name. A capability the harness
lacks is reported by the plan step before launch, never discovered mid-panel.

Flags below were checked for existence on 12 October 2026 against Claude Code
2.1.296, codex-cli 0.162.1 and Pi 1.1.0. The Claude Code and Codex columns
were then corrected from real runs; see [Discovery](#discovery). The Pi
column is still untested.

| Need | Claude Code | Codex | Pi |
| --- | --- | --- | --- |
| Headless run | `claude -p`, prompt on stdin | `codex exec -`, prompt on stdin | `pi -p` |
| Model | `--model` | `-m` | `--model <provider>/<id>` |
| Thinking effort | `--effort`, validated by the runner | `-c model_reasoning_effort=`, validated by the runner | `--thinking` |
| Working directory | process cwd | `-C` | process cwd |
| Keep user and project instructions out | `--safe-mode --restricted --strict-mcp-config --disable-slash-commands --settings '{"includeGitInstructions":false}'` | `--ignore-user-config --ignore-rules -c project_doc_max_bytes=0 -c skills.include_instructions=false --disable plugins --disable tool_suggest`; the user-level `AGENTS.md` cannot be excluded | to be found |
| Restrict tools | `--tools`, `--allowed-tools`, `--permission-mode dontAsk` | `-s workspace-write`, `-c approval_policy=never` | `--tools` |
| See an image | reads files by path | reads files by path; `-i` exists and is not used | to be found |
| Machine-readable output | `--output-format stream-json --verbose` | `--json` | `--mode json` |
| Session id | `--session-id <uuid>`, chosen by the runner | `thread_id` on the first output line | to be found |
| Resume | `--resume <id>`, with every launch flag repeated | `codex exec <every launch flag> resume <id>` | `--session-id` |
| Budget cap | `--max-budget-usd`, per process | none | none found |
| Delete a session | remove its transcript file | `codex delete --force <id>` | to be found |

## `study.json` changes

All new keys are optional. A study file written for the current skill loads
unchanged.

```json
{
  "type": "review",
  "materials": "full",
  "runner": "claude",
  "models": [
    "opus",
    {"key": "opusHigh", "runner": "claude", "model": "opus", "effort": "high"},
    {"key": "codex", "runner": "codex"},
    {"key": "local", "runner": "pi", "model": "<provider>/<model id>"}
  ],
  "replicates": 1,
  "limits": {
    "run": {"budget_usd": 2.0, "minutes": 15},
    "synthesis": {"budget_usd": 5.0, "minutes": 30},
    "overrides": {"local": {"minutes": 25}}
  },
  "runners": {"claude": {"concurrency": 6}, "codex": {"concurrency": 4}}
}
```

Rules:

- **A bare string in `models`** means that model on the study's `runner`. With
  no `runner` key the study is in native mode, which is today's behaviour.
- **`key`** is the short name used in file names, run ids and analysis. It
  holds letters and digits only, because the persona file name pattern
  (`<pid>-<slug>--<key>.md`) and run ids (`<pid>-<key>`) split on hyphens.
  Keys are unique within a study. A bare string is its own key.
- **A model entry without `model`** uses the harness's default model.
- **`effort`** is passed through where the harness supports it. Where it does
  not, the plan step reports it and the run proceeds without it.
- **`replicates`** above 1 adds a suffix to the run id (`P05-opus-r2`). The
  persona file name pattern is extended to carry the replicate, and files
  without one still parse.
- **`limits.overrides`** is keyed by model key.

## Part 1: Runners and the launcher

### Launcher commands

`scripts/launch.py <study-dir> <command>`:

| Command | Does |
| --- | --- |
| `plan` | Prints every run, the estimate and the ceiling, the limits, and what each provider will receive. Starts nothing |
| `pilot` | Runs one persona on each model entry, then stops |
| `run` | Starts runs that are `pending` or `failed`, within each runner's concurrency |
| `resume` | Continues `partial` and `blocked` runs in their original sessions |
| `stop` | Stops running processes cleanly and leaves them resumable |
| `status` | The same view as `runs.py status`, plus process state and usage |
| `purge-sessions` | Deletes the study's harness sessions, where the harness allows it |

`run` and `resume` accept `--runs <ids>` and `--role panellist|analyst`.

No command restarts or continues a run outside the states named above, with
one exception: `resume --runs <ids> --extend` continues a `limited` run with
one more allowance of its limits. The plan's ceiling then no longer holds for
the study, and `status` says so.

### Run lifecycle

| State | Meaning | Next |
| --- | --- | --- |
| `pending` | Not started | `run` |
| `running` | A process is alive | wait |
| `done` | The persona file is complete for the study type | none |
| `partial` | The process ended with some sections written | `resume` |
| `limited` | Stopped by a run limit | reported; `resume --extend` only |
| `blocked` | The harness reported a usage or rate limit | `resume` later |
| `failed` | The process ended with nothing written, or the CLI errored | `run` |

Rules:

- **`done` is decided by the persona file**, never by the exit code. A run
  whose process exits cleanly with a missing section is `partial`. What
  counts as complete depends on the study:

  | Study | Complete when the persona file has |
  | --- | --- |
  | Review, several concepts | A scored section for every concept, and the final marker (today's check) |
  | Review, one concept | A scored section for the concept, and the final marker |
  | Usability | A scored `### Task <id>` section for every task, and the final marker |

  `parse_persona_file`, `runs.py`, `check_runs.py` and the resume message
  take their unit, concept or task, from the study type. A usability resume
  message names the tasks already written and the tasks left.
- **One launcher per study.** A lock file in the study directory stops a
  second launcher. A stale lock from a dead process is detected and cleared.
- **`runs.json` is written atomically** after every state change, so a killed
  launcher loses nothing. On start the launcher reconciles `running` entries
  whose process is gone.
- **A usage limit stops new launches for that runner only.** Other runners
  continue. Affected runs become `blocked` and the launcher reports the reset
  time if the harness gave one.
- **Resume uses the existing `resume_message`** text from `runs.py`, sent
  through the runner's resume command. A run with no recorded session id, or
  on a runner without resume, is restarted only when its persona file has no
  sections; otherwise it is reported for the lead to decide.
- **A failed run is retried once** by the same `run` command. A second
  failure leaves it `failed` until `run` is called again.
- **A run's limits cover all its attempts.** Time and reported spend add up
  across the first attempt, the retry and every resume. A retried or resumed
  run gets what is left, and becomes `limited` when nothing is.
- **The launch prompt is the file in `prompts/`, verbatim**, as the method
  requires. Runners add nothing to it.

### Isolation

Today "read nothing outside `panel/`" is an instruction. Subagents inherit
project instructions, and internal terms have leaked into reviews. With CLI
runners the launcher enforces what it can:

- The process starts in `panel/`.
- User and project instruction files, memory, hooks, plugins and MCP servers
  are excluded where the harness has a switch for it.
- Tools are limited to reading files, writing under `panel/`, and the
  `agent-browser` CLI when the study allows browsing.
- The environment is passed through unchanged, and the plan step reports any
  provider API key variable that is set, because it can change who is billed.

Instructions in the run prompt stay, since no sandbox is assumed to be
complete. `check_runs.py` keeps scanning for leak terms.

### Native mode

`runs.py next`, `mark` and `resume` keep working as they do now. Native mode
has no limits, no usage record and no isolation beyond instructions, and the
plan step says so. It is kept for harnesses without a usable headless CLI and
as a fallback.

### Analysts and the writer

The qualitative analysts and the synthesis writer run through the launcher
too, with models chosen separately from the panel's:

```json
"synthesis": {
  "analysts": 2,
  "analyst": {"runner": "claude", "model": "opus"},
  "writer": {"runner": "claude", "model": "opus"}
}
```

- **`analyst` and `writer` are model entries**, in the same shape as `models`.
  There is no default. `plan` reports them as missing, and `run --role
  analyst` refuses to start without them.
- **`analysts` is 1 or 2.** With 2, personas are split into two halves in
  persona id order, so each analyst sees every model of a persona, as the
  method requires.
- **Jobs are recorded in `runs.json`** with a `role` and the ids `analyst-1`,
  `analyst-2` and `writer`. They follow the same lifecycle as panellist runs.
- **The launcher fills the briefs.** It writes each job's prompt to
  `prompts/` from `assets/qual-brief.md` or `assets/synthesis-brief.md`, with
  the persona files, `analysis/lead-notes.md` and the output path filled in.
- **A job is `done` when its output file exists and is not empty.** The
  launcher saves the runner's final reply to `analysis/`, which replaces
  `extract_agent_reply.py` outside native mode.
- **Order is enforced.** Analyst jobs refuse to start while any panellist run
  is `pending`, `running` or `blocked`, unless `--allow-incomplete` is
  passed. The writer starts only when every analyst job is `done`.
- **They run under `limits.synthesis`**, separate from the run limits.

### Incomplete runs in the analysis

Today `extract_scores.py` exports every score it finds, including those from
unfinished runs, and `analyze.py` does not filter them. That changes:

- `extract_scores.py` marks each row with whether its run is complete.
- Every headline table in `analyze.py` (leaderboard, factors, segments,
  persona fit, model agreement) uses complete runs only, and states "N of M
  runs complete".
- A separate table lists each `partial`, `limited` and `failed` run with its
  state and what it wrote. Their scores appear there and nowhere else.
- Analyst prompts name the incomplete files, so their content is read as
  partial evidence.

### Deviations decided during milestone 1

- **The Claude runner strips the host session's nesting variables** from the
  child environment (`CLAUDECODE`, `CLAUDE_PID`, `CLAUDE_EFFORT`, `AI_AGENT`,
  `CLAUDE_AGENT_SDK_*` and `CLAUDE_CODE_*` other than user configuration).
  [Isolation](#isolation) said the environment passes through unchanged.
  Inherited, they change the session's effort and label and may leave token
  refresh to a host process that is not there. Login and billing variables
  still pass through, and the plan still reports them.
- **`resume_command` also takes the working directory and the limits.** No
  harness inherits them on resume, so the runner repeats every launch
  setting.
- **A `browse` study key controls browser use** (default true). Codex has no
  browser capability yet: browser state does not survive between shell calls
  in its sandbox. Its runs are told to review from the files alone.
- **Codex's user-level instruction file cannot be excluded** without
  redirecting its home directory, which would mean handling its login. It is
  reported as an isolation gap instead.
- **`--role` also accepts `writer`.** The writer is started with
  `run --role writer`, after the analysts.
- **Without a pilot the plan gives a token estimate and no dollar estimate,**
  because the skill keeps no price tables. The plan step said list-price
  cost would come from the figures in `references/method.md`.
- **One launcher command was added: `usage`,** which rewrites and prints
  `analysis/usage.md`.
- **The runner interface has a sixth function, `purge_command`,** and
  `capabilities()` also reports purge, default concurrency, the provider,
  billing variables and isolation gaps.
- **Each attempt runs under a watchdog process of its own**
  (`scripts/run_watchdog.py`), which outlives the launcher. [Limits](#limits)
  says the launcher enforces `minutes`: the watchdog does, so a killed
  launcher does not unbound its runs. It also ends whatever the CLI left
  running, and writes an end record (end time, exit code, why it stopped the
  process) that the launcher settles the run from.
- **`parse_result` also reports `session_lost`:** a resume whose session the
  harness no longer has. The launcher treats that session as a purged one.

## Part 2: Limits, the plan and usage

### Limits

| Limit | Enforced by | Applies to |
| --- | --- | --- |
| `minutes` | The launcher, on every runner | All runs |
| `budget_usd` | The harness, where it has a cap | Runners with the capability |
| `steps` | The panellist, per task, with the launcher as backstop from the step log | Usability runs only |

- A run stopped by a limit keeps everything it wrote and becomes `limited`.
- Stopping gives the process a short grace period to finish its current
  write before it is killed.
- Defaults ship in the skill and are used when `limits` is absent. The plan
  step always prints the values in force.
- `limits.synthesis` is reserved before the panel starts and is never spent
  by panellist runs. Its `budget_usd` is one pool for all analyst and writer
  jobs: the launcher divides it equally among the planned jobs and gives each
  job its share as a cap. Its `minutes` applies to each job.

### The plan step

`launch.py plan` prints, without starting anything:

- every run: persona, model key, runner, model, effort, limits, prompt file
- what each run can read: number of pages, images and bytes
- which provider receives which materials
- capabilities each model entry lacks (no images, no budget cap, no resume)
- an **estimate** of tokens and list-price cost, from measured usage when the
  study has a pilot, otherwise from the figures in `references/method.md`
- a **ceiling**: the sum of enforced budget caps plus the synthesis budget

The ceiling counts each run's cap once, because a cap covers all of a run's
attempts, and counts the synthesis pool once, because the pool is split into
per-job caps. It is a guaranteed maximum only when every run has an enforced
budget cap. If any run is on a runner without one, the figure is labelled an
estimate and the time limit is what bounds that run. Subscription usage has
no price per token, so dollar figures there are list-price equivalents and
are labelled as such.

### Usage record

After each run the launcher stores what the harness reported (tokens, cost,
duration) in `runs.json` and writes `analysis/usage.md`: per run, per model
key and in total. A pilot therefore measures a real baseline, and the next
`plan` uses it. Where a harness reports nothing, the record says "not
reported" and the estimate falls back to duration.

## Part 3: Small additions

### Text-only pass

`"materials": "text"` makes a study a quick copy check:

- Panellists read `page-text.txt` only. No sheets, no browser.
- The `visual` and `mobile` factors are dropped automatically, with every
  template and parser adjusted to the remaining factors.
- The run prompt tells panellists they cannot see the design and must not
  comment on it.
- The synthesis notes the known artefact of flattened pages: repeated
  navigation, and labels that lose the layout that explains them.

The workflow gains an optional step before the full panel. A text pass is its
own study directory, so its scores are never mixed with a full panel's.

### Follow-up questions

`scripts/followup.py <study-dir> ask --runs <ids> --question-file <file>`:

- resumes each named run's session with the question
- the panellist appends a `## Follow-up <n>` section to its own persona file
- `followups.json` records the question, the runs and the time
- scores are never changed by a follow-up, and analysis treats the answers as
  qualitative only

Rule for `SKILL.md`: a follow-up never reveals another panellist's answer, a
result, or what the team hopes to hear.

### Answer tallies

`scripts/extract_answers.py <study-dir>` reads the persona files and writes:

- `analysis/answers.csv`: Found, Partly or Not found for each
  `find_the_answer` question, per run and concept
- `analysis/lines.csv`: the line to keep, to cut and not believed, and the
  forward answer, per run and concept

`analyze.py` adds a table of each. An entry the script cannot parse is listed
as unparsed, never guessed.

### Replicates and variants

- **Replicates** repeat a run. `analyze.py` reports the spread between
  replicates beside model agreement, so a finding can be checked for
  stability.
- **Variants** are personas with `"variant_of": "<pid>"` and one changed
  trait, written by the lead. Analysis groups a variant with its parent.

### Roster grid and reusable rosters

`scripts/roster.py`:

- `grid <study-dir>` reads `roster.roles`, `roster.personalities`, an
  optional `roster.stages` and `roster.caps` (`personas`, `runs`) from
  `study.json`, and writes skeleton personas: id, role, personality and
  segment, with an empty bio for the lead to write.
- When the cap is below the full grid, selection is deterministic for the
  study seed and every role and every personality appears at least once. If
  the cap is too small for that, the script says so and stops.
- `caps.runs` counts personas x model entries x replicates. The script
  refuses a roster that exceeds it and prints the arithmetic.
- `export` and `import` move personas to and from a roster file kept in the
  project, with stable ids so results compare across studies.

### Study brief

A new asset, `assets/study-brief.md`, records what the lead agrees with the
user in step 1: the decision being made, the audience, what is fictitious,
the hypotheses, and what must stay local. It lives beside `study.json`,
outside `panel/`, and `init_study.py` refuses to run if a copy is found
inside `panel/`.

### Synthetic panel notice

Every persona file header, the synthesis, the report and the archive README
carry one fixed line stating that the content was generated by AI personas
and is not user research. `archive.py` adds it to anything it copies that
lacks it.

### Deviations decided during milestone 2

Text-only pass:

- **The site copies of a text study live in `<study>/sites/`,** outside
  `panel/`, so no panellist can open a page or its source. `capture.py`
  reads them from there and removes the images of an earlier capture.
- **A factor can declare `"needs_design": true`.** A text study drops every
  such factor, not only `visual` and `mobile`, and drops it from
  `fit_factors` too. `overall` cannot be one.
- **A text study never browses,** whatever `browse` says. The plan notes it.

Follow-up questions:

- **Follow-ups have their own allowance, `limits.followup`** (default 5
  minutes and $0.50), for each run asked and each question. It is apart from
  the run's limits and outside the plan's ceiling. `plan` and `status` count
  the questions asked, and `analysis/usage.md` lists what they used under a
  role of its own, "follow-up".
- **"Scores are never changed" is enforced by snapshot and restore.** The
  persona file is copied before the question. Afterwards it must be that
  copy plus one appended `## Follow-up <n>` section with no other heading.
  Anything else is rejected: the file is put back, and what the panellist
  left is kept in `logs/`.
- **`followups.json` records an outcome for each run:** answered, answered
  from the reply, rejected, unanswered, turned away, could not start, not
  asked, or sent by hand.
- **A panellist that replies without writing** has its section written from
  the reply by the launcher, marked as such.
- **Only a finished run with a live session can be asked.** One run named
  that cannot be asked stops the command, unless `--skip-unfit`. `--runs all`
  asks every finished panellist run.
- **A second command, `followup.py list`,** prints the questions asked and
  how each run answered.
- **Asking again is a new follow-up** with the next number. There is no
  retry of a numbered follow-up.
- **The message frame is an asset,** `assets/followup-message.md`.
- **The analysts' and the writer's briefs name the follow-ups asked,**
  through a `<FOLLOWUPS>` placeholder filled from
  `assets/qual-brief-followups.md` and `assets/synthesis-brief-followups.md`.
- **`check_runs.py` notes** a follow-up section that `followups.json` does
  not record as an answer, and a recorded answer whose section is missing.
- **In native mode nothing is sent or enforced.** `ask` prints each message
  for the lead to send and records the follow-up as sent by hand.
- **`init_study.py --force` removes `followups.json`,** because it rewrites
  the persona files that held the answers.
- **`ask --dry-run`** prints what `ask` prints before it starts (the runs,
  each one's allowance, the most they can use and whether each harness
  enforces it), starts nothing and records nothing.
- **Settling is in recorded steps:** the decision, what it does to the file,
  the outcome, the attempt's end in `runs.json`, then the copy is deleted. A
  later launcher carries out a decision it finds and never decides again.
- **A run still queued when its launcher was killed is `not asked`.** The
  next launcher command records it, and so does `followup.py list` when no
  launcher has the study.
- **Readers use the copy until a follow-up is settled.** `status`, the
  extract scripts and `check_runs.py` read the persona file as it stood
  before the question and name each such run in a line. `archive.py` refuses
  the study.
- **Usage a follow-up cannot be told apart from is "unallocated".** A
  follow-up to a run with a process that was stopped unreported gets one
  total for both. It is counted in the totals, in neither's own figures, and
  such a run is left out of the plan's mean tokens and cost.

Answer tallies:

- **`lines.csv` is long format:** four rows per run and concept, one each for
  keep, cut, not believed and forward, with an `entry` column.
- **A forward answer can be `maybe`,** as well as yes or no.
- **An entry the panellist left out is `missing`,** counted apart from
  `unparsed`. "Partially" reads as Partly.
- **The tables use complete runs only.** Both CSVs carry a `complete` column,
  and an incomplete run's rows stay in the CSVs.
- **`analyze.py` adds three tables, not two:** "Find the answer", "Forward
  test" and "Lines that recur", which lists the lines more than one run
  quoted.

Replicates and variants:

- **A variant counts as a persona of its own in every table.** It is also
  shown under its parent in the persona matrix and the persona-fit table,
  with the difference, and a "Variants" table compares the two over the
  model keys both have complete runs on. The PRD said analysis groups a
  variant with its parent.
- **A variant of a variant is refused,** as is a `variant_of` that names no
  persona or the persona itself.
- **"Replicate spread" is per persona and model key,** with one summary line
  per model key. Its Spearman column needs three or more concepts.
- **A variant reviews in its parent's order.** The order is seeded by the
  parent's id, so order is no part of the difference between the two.
- **`analyze.py --exclude-persona <id>`** leaves a persona out of every
  table, the run counts and the tallies, as `--exclude-model` does a model
  key. It is how a variant that only tests a trait stays out of the headline.

Roster:

- **A skeleton is named `TODO`,** and `init_study.py` refuses a study while
  one is left. `roster.py export` refuses one too.
- **`grid --append`** keeps written personas and adds skeletons after them.
  Without it, `grid` stops when `study.json` holds a written persona, and it
  never changes one.
- **Every stage appears at least once too,** when the cap is at least the
  number of stages. `grid --append` is refused, with the least cap that would
  do, when the written personas leave too few places for that.
- **A role can be an object** that gives its segment.
- **The study directory comes first:** `roster.py <study-dir> grid`, `export`
  or `import`, as in every other script. The PRD wrote `grid <study-dir>`.
- **A roster file merges by id.** `export` stops on a persona with the same
  id and different content unless `--update`, `import` never changes a
  persona in a study and takes `--ids`, and a variant travels with its
  parent. Only the eight persona fields move.

Study brief:

- **The template has a sixth heading, "Scale":** the personas, models and
  replicates agreed, and the cost ceiling the user accepted.
- **The guard also covers concept folders** that are about to be copied into
  `panel/`, and matches a copy by name or by content.
- **The brief is refused in `synthesis.context_files`,** by name, by path or
  by content, so the team's hypotheses never reach an analyst or the writer.

Synthetic panel notice:

- **`archive.py` adds the notice to every markdown file it keeps** and to
  nothing else: CSV, JSON and what `--concepts` copies stay byte for byte.
- **The analysts' files carry it too.** Both briefs ask for it through a
  `<NOTICE>` placeholder, and the launcher adds it to a saved analyst or
  writer output that lacks it.
- **`archive.py` also keeps `study-brief.md` and `followups.json`.**
- **`extract_agent_reply.py` adds the notice** to the file it saves, so a
  native-mode analyst's or writer's reply carries it too.

Sessions and the plan:

- **`init_study.py --force` carries the replaced runs' sessions over** to
  `logs/earlier-sessions.json`. `purge-sessions` without `--runs` deletes
  them too, and `status` and `plan` say how many are on that record.
- **`init_study.py --force` is refused while the study is in use:** a
  launcher has it, or a process of one of its runs is alive. It holds the
  launcher's lock while it works.
- **Runners declare `browse_gaps` apart from `isolation_gaps`:** what stays
  open only for a run that may browse. The plan prints them only when the
  study's panellists can browse on that runner.
- **The plan's "In all" line names the model entries its sums leave out,**
  such as the analyst and writer jobs before any has run.

## Part 4: Artefact kinds

A concept gains an optional `kind`:

| Kind | Source | Captured as |
| --- | --- | --- |
| `site` (default) | A folder with `index.html` | As today |
| `url` | One or more URLs, public or on a local host | The same sheets and page text, taken from the live page |
| `files` | Images and PDFs | Images as they are; each PDF page rendered to an image, plus extracted text |

- Neutral labels and shuffled order apply to every kind.
- `url` concepts are not copied into `panel/sites/`. Browsing by panellists
  is allowed only when the study sets it, and then by URL.
- `files` needs Poppler for PDFs. Without it the script names the missing
  tool and stops before any run starts.
- A study with one concept has no ranking and no score summary. The
  templates, `check_runs.py` and `analyze.py` handle a single concept.
- The existing capture checks (forbidden terms, leak terms) run on text from
  every kind.

## Part 5: A runner for OpenAI-compatible endpoints

A third runner, for Pi, reaches any OpenAI-compatible endpoint and other
providers Pi supports. Pi is recommended over OpenCode and OMP because it is
already installed and exposes a tool allowlist, a thinking level
and session ids from the command line.

- The endpoint and its key are configured in Pi, never in `study.json`.
- The plan step reports whether each Pi model can read images. A model that
  cannot is limited to text-only studies, and a full-materials study that
  includes it is refused at the plan step.
- Every new model gets a pilot and, where needed, `model_notes`, as the
  method already requires. The September study showed a weaker model
  mislabelling concepts and inventing claims until its notes were tightened.

## Part 6: Usability studies

`"type": "usability"` tests whether a persona can complete tasks in a running
product, thinking aloud.

### Study definition

```json
{
  "type": "usability",
  "target": {"base_url": "http://app.localhost:8080", "allow_remote": false},
  "tasks": [
    {
      "id": "T1",
      "goal": "You want to find out how much you could borrow. See how far you get.",
      "start": "/",
      "steps": 25,
      "success_check": "scripts/check-t1.sh"
    }
  ],
  "accounts": {"provision": "scripts/make-account.sh", "teardown": "scripts/drop-account.sh"},
  "sequential": false
}
```

- **`goal`** is written in the user's words and names no interface element.
- **`success_check`** is optional and lead-only. It receives the run id and
  exits 0 when the task was really completed.
- **`accounts.provision`** prints one JSON object for a run, with two parts.
  `identifiers` holds made-up values that may be seen: username, email,
  display name. `secrets` holds values that must never be seen: password,
  token, one-time code. It may also name a saved browser state, so the
  panellist starts signed in and never handles a secret. A static
  `accounts.map` keyed by run id, in the same shape, is the alternative.
- **Signed-in start is the default.** A study gives panellists a secret to
  type only when signing in is itself the task under test.

### Protocol

For each task the panellist:

1. Opens the start page in its own `agent-browser` session.
2. Before every action, appends an `intent` entry to its step log: what it
   sees, what it expects, what it will do.
3. Acts, saves a screenshot, and appends a `result` entry: what happened, and
   the screenshot's file name.
4. Stops the task when it believes the task is done, when it would give up in
   real life, or when it has used the task's step limit.
5. Writes the task section of its persona file: outcome in its own words,
   where it hesitated or got stuck, what it expected instead, and scores.
6. Moves to the next task, and writes the final sections after the last one.

The step log is `panel/evidence/<run-id>/steps.jsonl`, one JSON object per
line, each with the task id, the step number and the phase. Screenshots are
saved beside it as `<task>-<step>.png`. A step is complete when it has both
its `intent` and its `result`.

Rules written into the instructions:

- Decide from what a person would see on the screen. Use the browser's
  element list to act, not to discover things a person could not see.
- Never read the page source, the product's code or its documentation.
- Enter only the test credentials given. Never create real accounts, pay, or
  send messages to real people.
- Never reveal a secret on screen: no "show password" control, and no secret
  typed into a field that displays it. Mark the `result` entry of any step
  that entered a secret as `"sensitive": true`.

Usability studies use their own default factors: task success, ease,
confidence, clarity of next step, trust, and overall.

### Limits and evidence

- **The step limit is per task and counts complete steps.** The task brief
  tells the panellist its limit. A panellist that uses it up records the
  outcome as "ran out of steps" and moves on, so the last permitted step
  always has its result and screenshot.
- **The launcher is the backstop.** If an `intent` appears with a step number
  above the task's limit, the launcher stops the run as `limited`, after the
  grace period.
- The time limit applies as for any run.
- After a run, `success_check` runs for each task. Analysis reports the
  panellist's own claim beside the check, and flags every mismatch.
- The step log and screenshots are the evidence for each finding. The
  synthesis cites the step.

### Accounts and safety

- By default the target must be a local development host: `localhost`,
  `127.0.0.1`, `[::1]`, or a name ending in `.localhost` or `.test`. Anything
  else needs `allow_remote: true`, and then tasks are limited to actions that
  change nothing.
- Credentials are written to `panel/scratch/<run-id>/account.json` and are
  test accounts only. Identifiers are made up, are not secrets, and may
  appear in evidence. Secrets never appear in persona files, step logs, the
  synthesis or the archive. `check_runs.py` fails a run whose persona file or
  step log contains a secret value.
- **Evidence and secrets are kept apart.** `panel/evidence/` holds step logs
  and screenshots and nothing else. `archive.py` copies it, with screenshots
  downscaled, so every step the synthesis cites survives in the archive. It
  refuses to archive if a step log contains a secret value, naming the file
  and line. It never copies the scratch folder or the accounts map.
- **Screenshots cannot be scanned for text**, so they are kept safe by
  construction. The archive leaves out the screenshot of every step marked
  `sensitive`, and of every step in a task whose run was given a secret to
  type, and puts a one-line note in its place. The step log entry stays, so
  the finding can still be cited. With a signed-in start no step is affected.
- **Harness transcripts are outside this guarantee.** Each harness keeps its
  own session record, which resume depends on, and that record will contain
  any credential a panellist read or typed. The skill cannot edit it. Three
  measures bound the exposure: credentials are throwaway accounts on a local
  build, `teardown` invalidates them when the run ends, and
  `launch.py purge-sessions` deletes the study's sessions, where the harness
  allows it, once the study is archived.
- `teardown` runs when the run reaches a final state, including `limited` and
  `failed`.
- With `"sequential": true` the launcher runs one panellist at a time and
  calls an optional `accounts.reset` command between runs, for products where
  separate accounts cannot be created.

### Analysis

`analyze.py` adds, for usability studies:

- completion rate per task, by persona and by model key, checked and claimed
- steps taken, and where runs stopped
- stuck points ranked by how many runs hit them, each with its step evidence
- a separate synthesis brief, `assets/usability-synthesis-brief.md`

## Changes to the skill's documents

- **`SKILL.md`:** harness-neutral wording; the launcher workflow as the main
  path; the optional text pass; study types; the rules above. It stays short,
  with detail in `references/`.
- **`references/method.md`:** runners, limits and the plan step; model
  comparison across vendors (level differences between models are
  calibration, not signal; pilot every new model); the September and October
  findings.
- **New `references/runners.md`:** how to add a runner, each harness's
  capabilities, and native mode.
- **New `references/usability.md`:** designing tasks, the protocol, accounts,
  and how much to trust the result.
- **`assets/`:** run prompts and instructions for text-only and usability
  studies, the study brief, and the usability synthesis brief.

## Discovery

To settle before the affected part is built. Record results in this document.

Results for Claude Code, Codex and all runners were established on 12 October
2026 against Claude Code 2.1.296 (Claude Max subscription login) and codex-cli
0.162.1 (ChatGPT plan login), by running each CLI in fixture directories with
planted marker terms. **Verified** means seen in a real run. **Inferred**
means read from help text, the binary's strings or old session files. The
exact flags and output formats are in the docstrings of
`scripts/runners/claude.py` and `scripts/runners/codex.py`.

Claude Code:

- The flags that exclude user and project instructions while keeping the
  subscription login working.
  - **Result (verified):** `--safe-mode --restricted --strict-mcp-config
    --disable-slash-commands --settings '{"includeGitInstructions":false}'`.
    With markers planted in user, project, parent and local instruction
    files, a project skill, a hook, an MCP config and a commit message, none
    reached the model and the login kept working.
  - `--setting-sources ""` is not enough: the auto-memory of the enclosing
    git repository still loads. `--bare` breaks the subscription login.
  - No switch was found for the signed-in account's email address, the
    working directory path, the OS version or the date. All reach the model.
- A tool allowlist and permission mode that allow reading and writing under
  `panel/` and running `agent-browser`, with nothing else.
  - **Result (verified):** `--tools Read,Write,Edit,Glob,Grep,Bash
    --allowed-tools "Read,Write,Edit,Glob,Grep,Bash(agent-browser:*)"
    --permission-mode dontAsk`, with `--restricted` confining the file tools
    to the working directory. Reads and writes outside it and other shell
    commands were denied at once, and nothing waited for approval. Without
    browsing, `Bash` is left out.
  - Two gaps remain with browsing on (verified): `agent-browser` can open
    any `file://` path and save screenshots outside `panel/`, and read-only
    shell commands inside the working directory run without an allow rule.
- Whether `--max-budget-usd` stops a run under a subscription login, or only
  with an API key.
  - **Result (verified):** it stops the run under a subscription login, at
    list prices. The check runs after each turn, so a run overshoots by up
    to one turn (0.0015 against a cap of 0.001). The cap counts one process,
    not earlier spend in a resumed session, so the launcher passes what is
    left on each attempt.
- What usage the JSON output reports, and how the session id is returned.
  - **Result (verified):** `--output-format stream-json --verbose` prints
    one line per event with `session_id` on each, ending in a `result` line
    with `total_cost_usd`, tokens per model in `modelUsage`, and
    `duration_ms`. Cost and tokens are running totals for the session. The
    runner chooses the id itself with `--session-id <uuid>`.
  - A killed process prints no result. Its spend appears in the next result
    of the same session.

Codex:

- Whether a panellist can open an image by path, or needs `-i` at launch. If
  only `-i`, whether attaching every sheet up front fits the context budget.
  - **Result (verified):** a run opens an image by path, inside the sandbox.
    A 2880x1800 sheet was read down to its small print. `-i` also works but
    is not used, so the context question does not arise.
- The sandbox mode that allows writes under `panel/` and `agent-browser`
  against `file://` and local hosts.
  - **Result (verified):** `-s workspace-write` allows writes in the working
    directory and `/tmp`, with the network off and the whole disk readable.
  - `agent-browser` does not work in it. It needs the network even for
    `file://` pages, and each shell call gets its own process namespace, so
    the browser's state is lost between calls. It worked only with all
    outbound network on and a browser session started outside the sandbox.
    Codex therefore has no browser capability in milestone 1.
- Whether `--ignore-user-config` affects the login or the default model.
  - **Result (verified):** the login keeps working. The approval policy
    becomes `never` and the effort falls back to the model's default. The
    model was the same with and without it, but the user's config named the
    model the account lists first, so the test cannot tell them apart.
  - It removes neither the skills list (`-c skills.include_instructions=false`
    does) nor the user-level `AGENTS.md` (nothing short of another home
    directory does).
- How the session id and token usage appear in `--json` output, and whether
  `codex exec resume` continues a run started without `--ephemeral`.
  - **Result (verified):** the id is `thread_id` on the first line,
    `thread.started`, before any model call. Usage is in
    `turn.completed.usage` (input, cached input and output tokens) as a
    running total for the thread. There is no cost and no duration.
  - Resume continues the run with its memory, also after SIGTERM. It
    inherits nothing: every launch option is repeated, before the word
    `resume`.

Pi:

- How to exclude global instruction files.
- Image input per model, and how the plan step can detect it.

All runners:

- The error text and exit code for a usage or rate limit.
  - **Result (inferred, still open):** no limit could be triggered on either
    harness. Claude Code is expected to end with an error result whose text
    starts "You've hit your", status 429 and exit code 1, with the reset
    time in its `rate_limit_event`. Codex is expected to end with
    `turn.failed` and exit code 1, its message naming a usage limit, with
    the reset time in the session file.
- Where each harness stores a session, and whether it can be deleted by id.
  - **Result (verified):** Claude Code keeps one transcript per session
    under its projects directory, in a folder named after the working
    directory. It has no command that deletes one session, and removing the
    file makes the id unknown to resume. Codex keeps a session file under
    `$CODEX_HOME/sessions/` and database rows, and
    `codex delete --force <id>` removes both.
- A safe default concurrency on a subscription.
  - **Result (still open):** no cap was found in either CLI. Four concurrent
    Claude Code runs and three concurrent Codex runs raised no error. The
    defaults stay at 6 and 4.
- Whether `agent-browser` runs inside each harness's sandbox.
  - **Result (verified):** yes in Claude Code, through an allow rule for
    `agent-browser` commands. No in Codex, as above.

Still open after milestone 1:

- The real output and exit code at a usage or rate limit, on both harnesses.
- Safe concurrency figures on each subscription.
- Whether `claude auth status` notices a revoked token.
- Whether the account email can be kept out of Claude Code's context.
- Whether a separate Codex home directory holding a link to the login
  survives a token refresh. This decides whether the user-level `AGENTS.md`
  can ever be excluded.
- A Codex network rule narrower than all or nothing, and a way to stop reads
  outside `panel/`.
- How to remove Codex's sub-agent tools and their instructions.
- Whether the trust entry Codex writes to the user's `config.toml`, for a
  run inside a git repository, can be prevented.
- What `--ignore-rules` does in practice: its effect was read from the help
  text, not observed.

Usability:

- Whether panellists follow the "decide from the screen" rule, checked by
  comparing step logs with screenshots in a pilot.
- How often a panellist claims success that the check denies.
- Whether `agent-browser` can save a signed-in browser state and load it into
  a panellist's session, which the signed-in start depends on.

## Edge cases

- **A model entry's CLI is missing or signed out.** `plan` reports it and
  `run` refuses to start any run on that runner. Other runners proceed only
  if the lead passes `--allow-missing`, because a panel short of a model is a
  different study.
- **Two model entries resolve to the same model.** Allowed, since effort may
  differ. Their keys must differ.
- **The launcher is killed.** The next start reconciles `runs.json` against
  live processes and the persona files.
- **A panellist writes outside its own file.** `check_runs.py` already flags
  malformed files. It also flags a persona file changed by a run other than
  its owner, using the modification record the launcher keeps.
- **A resumed run repeats a section.** Already detected by `check_runs.py`.
- **A harness changes a flag.** The runner's `check()` fails with the CLI's
  own message, before any run starts.
- **A study mixes native mode and runners.** Not allowed. A study is one or
  the other.
- **An old study is analysed.** `runs.json` entries without the new fields
  are read as native-mode runs with no usage.
- **A text-only study names `visual` in `fit_factors`.** The factor is
  dropped from there too, with a note in the plan.
- **A usability task needs a second factor or a real payment.** Out of scope.
  The task design notes say to stub it in the test build.

## Order of work

Each part is usable without the ones after it.

1. **Runners and the launcher**, with Claude Code and Codex, limits, the plan
   step and the usage record.
2. **Small additions:** text-only pass, follow-ups, tallies, replicates, the
   roster grid, the study brief and the notice.
3. **Artefact kinds:** files, URLs and single-concept studies.
4. **The Pi runner.**
5. **Usability studies.**

## Tests

Contract tests live in `packages/common/agents/tests/test_persona_panel.py`
and follow the `test-audit` authoring gate: one test per observable contract
with a credible way to break. The existing tests keep passing.

Runners are tested against fake CLI executables on `PATH`, so no test calls a
model. Contracts worth a test:

- each runner's launch and resume command for a given run and limits
- result parsing for the outcomes: ok, usage limit, budget reached, error
- the lifecycle: concurrency cap, time limit, retry once, `blocked` stops
  only one runner, reconciliation after a killed launcher, the study lock
- `done` decided by the persona file, not the exit code, for each study type
- `run` starts only `pending` and `failed` runs, and `resume` only `partial`
  and `blocked` ones, unless `--extend` is given
- a run's limits add up across its attempts
- the synthesis pool is split into per-job caps, and the writer waits for the
  analysts
- headline tables use complete runs only, and incomplete runs are listed
  separately
- a current-format `study.json` and `runs.json` load unchanged
- model key validation and run id and file name construction
- the plan's ceiling is labelled an estimate when any run lacks a budget cap
- the roster grid: deterministic, covers every role and personality, refuses
  an impossible cap
- text-only studies drop the visual factors end to end
- answer tallies, including unparsed entries
- single-concept studies pass checks and analysis
- usability: the per-task step limit and its backstop, secret leak detection
  in persona files and step logs, the local-host rule, teardown on every
  final state, claimed against checked completion, and an archive that keeps
  evidence, refuses a step log holding a secret, and leaves out screenshots
  from sensitive steps and from tasks where a secret was typed

## Acceptance criteria

**E2E** means verified with real harnesses; **tests** means covered by the
contract tests.

Runners and launcher:

- A panel with Claude Code and Codex model entries runs to completion from
  one `launch.py run`, with every persona file passing `check_runs.py`. E2E
- The same panel is started from a Codex session, from a Claude Code session
  and from a plain terminal. E2E
- Model agreement in `analyze.py` covers pairs across vendors. E2E
- A run that exceeds its time limit stops, keeps what it wrote and is
  reported as `limited`. Tests, and once E2E
- A simulated usage limit leaves runs `blocked`, other runners unaffected,
  and `resume` finishes them. Tests; E2E when one occurs
- Killing the launcher mid-panel and starting it again loses no completed
  work and starts no duplicate run. Tests and E2E
- A panellist launched through a runner does not see the lead project's
  instruction files: a planted marker term in them never appears. E2E
- `plan` starts no process and makes no model call. Tests
- `run` never restarts a `partial` or `limited` run. Tests
- Analyst and writer jobs run on the models named in `synthesis`, and the
  writer starts only after the analysts finish. Tests, and once E2E
- An existing archived study still passes `extract_scores.py` and
  `analyze.py`. Tests

Limits and usage:

- `plan` shows an estimate, a ceiling and its label, and the limits in force.
  Tests
- After a pilot, `plan` uses the measured usage. Tests
- `analysis/usage.md` matches what each harness reported. E2E
- A run stopped by a limit is absent from every headline table and appears in
  the incomplete runs table. Tests

Small additions:

- A text-only study of one page completes and its analysis has no visual
  factors. E2E
- A follow-up reaches the original session and appends one section without
  changing any score. E2E
- Tallies for a finished study match a hand count of three runs. E2E

Artefact kinds:

- A PDF and a set of screenshots are reviewed under neutral labels. E2E
- A page on a local host is captured and reviewed. E2E

Pi runner:

- A panel includes a model on an OpenAI-compatible endpoint. E2E
- A full-materials study with a text-only model is refused at the plan step.
  Tests

Usability:

- Panellists on two harnesses attempt a task on a local build, each with its
  own account, and produce step logs with screenshots. E2E
- A task that uses its step limit ends with its last step's result and
  screenshot saved, and the run goes on to the next task. Tests and E2E
- An archived usability study contains the step logs and screenshots its
  synthesis cites. Tests
- A claimed success that the check denies is flagged in the analysis. Tests
- No secret value appears in any persona file, step log or synthesis, and
  the archive holds no screenshot from a step that could show one. Tests
- A remote target without `allow_remote` is refused. Tests

Documents:

- `SKILL.md` names no harness tool, and a harness other than Claude Code
  completes a study by following it. E2E

## Risks

- **Harness CLIs change.** Flags and output formats move between versions.
  Mitigation: all harness knowledge sits in one module per harness, with a
  `check()` that fails early.
- **Models from different vendors are not comparable out of the box.** A new
  model may compress scores, skip materials or invent claims. Mitigation: the
  pilot step for every model entry, model notes, and reporting model
  disagreement instead of averaging it away.
- **Isolation is partial.** A harness may load something the launcher cannot
  switch off. Mitigation: instructions stay, the leak scan stays, and the
  marker-term check is an acceptance criterion.
- **Budget caps are uneven.** Only some harnesses enforce one, and
  subscription usage has no true price. Mitigation: the time limit applies
  everywhere and the plan labels every figure honestly.
- **Provider terms.** Each vendor's rules for using a subscription outside
  its own app differ and change. The skill only drives official CLIs the
  user signed in to, and holds no credentials. Recheck the terms before
  sharing the skill with others.
- **Usability results may mislead.** An agent reads a page more thoroughly
  than a person and does not get bored. Mitigation: the "decide from the
  screen" rule, the objective check beside the claim, and the existing rule
  that every result is a hypothesis.
- **Scope.** This is a large change to a skill that works. Mitigation: the
  order of work, with native mode and the existing tests intact throughout.

## Open questions for Rod

1. **Default concurrency.** What is safe on each subscription? The draft
   uses 6 for Claude Code and 4 for Codex until discovery says otherwise.
2. **Native mode.** Keep it for good, or remove it once the launcher has run
   two real studies?
3. **Pi as the third runner.** Agreed, or would you rather OpenCode or OMP?
4. **Reusable rosters.** The draft keeps them in each project's own
   repository. Should there also be a shared location?
5. **Remote targets for usability studies.** Allow them with
   `allow_remote`, as drafted, or local hosts only?
6. **Credentials in harness transcripts.** The concept brief says secrets
   never appear in transcripts. The draft cannot promise that for a harness's
   own session record, and bounds it with throwaway accounts, teardown and
   `purge-sessions` instead. Is that acceptable?
