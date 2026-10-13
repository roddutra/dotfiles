# Persona panel: other harnesses, limits and wider research

**Status:** Paused on 13 October 2026. All six parts are built, reviewed by
Codex and committed on the branch `persona-panel-expansion`: milestones 1 to
5, and follow-up work in one more commit (`5e5dfe3`). 105 contract tests
pass. Nothing is merged to `main`. Two acceptance criteria are not verified:
a panel with a model on an OpenAI-compatible endpoint, and a harness other
than Claude Code completing a study by following `SKILL.md`. Codex reviewed
this PRD on 12 October 2026 over three rounds and approved it, and the user
settled the open questions on 13 October 2026. See
[Implementation status](#implementation-status).

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

## Implementation status

As at 13 October 2026. Work is paused.

All six parts are built on the branch `persona-panel-expansion`, which is not
merged to `main`. Each of milestones 1 to 5 was committed once Codex approved
it. One follow-up commit (`5e5dfe3`) fixes the 14 problems that the last fix
pass had listed and left, settles how a panel is started from a Codex
session and from a terminal, and keeps a study safe from a shell that cannot
see its processes. Codex approved it in round 27: see
[Follow-up work](#follow-up-work) for what it holds. 105 contract tests
pass.

Real end-to-end runs passed for milestones 1, 2, 3 and 5 on Claude Code and
Codex, for milestone 4 on Pi through its `openai-codex` provider only, and
for the follow-up work on Claude Code and Codex in three rounds. The third
round ran on a snapshot taken before the last lock changes, which tests and
fake panels inside real sandboxes cover and no real panel does
([Built but not tested](#built-but-not-tested)). Two acceptance criteria are
not verified: a panel with a model on an OpenAI-compatible endpoint, and a
harness other than Claude Code completing a study by following `SKILL.md`.
Everything ran on Linux. The evidence sat in temporary directories that will
not survive, so this section carries the conclusions.

Terms used here:

- **Milestone** is the PRD's [order of work](#order-of-work). Milestone 1
  covers parts 1 and 2, and milestones 2 to 5 cover parts 3 to 6.
- **Follow-up work** is what the user asked for on 13 October 2026, after
  milestone 5 was committed (`d3b4451`, with the status note `21ff323`). It
  is commit `5e5dfe3`.
- **Real run** means a study run end to end with real harness CLIs and real
  models. The models were Claude Code on `haiku` and `sonnet`, Codex on its
  default model at low effort, and Pi on `openai-codex/gpt-6-luna` at low
  effort. The largest panel was 6 runs (3 personas on 2 model entries).
- **Tests** are the contract tests in
  `packages/common/agents/tests/test_persona_panel.py`, which run against fake
  CLIs and call no model. Run them with
  `python3 -m unittest discover -s packages/common/agents/tests -p 'test_persona_panel.py'`.

### What is built, part by part

Part 1, runners and the launcher:

| Item | Detail |
| --- | --- |
| Built | `scripts/launch.py` (`plan`, `pilot`, `run`, `resume`, `stop`, `status`, `usage`, `purge-sessions`), a watchdog for each attempt (`scripts/run_watchdog.py`), the `claude` and `codex` runners, analyst and writer jobs, incomplete runs kept out of the headline tables. Native mode is kept |
| Commit | `0f2abe1` |
| Tests | `RunnerTest` (commands, parsing, checks and purge against fake CLIs) and the lifecycle tests of `LauncherTest`. 55 tests passed when the milestone was reviewed |
| Real run | Passed on Claude Code (`sonnet`) and Codex. A study of two personas and two concepts: pilot, run, the launcher killed mid-panel and started again, a time limit on both harnesses then `resume --extend`, `stop`, an analyst and the writer, and `purge-sessions`. A planted marker term reached no persona file |
| Codex review | Rounds 1 to 4 (four rounds). Final verdict: APPROVE |

Part 2, limits, the plan and usage:

| Item | Detail |
| --- | --- |
| Built | The time limit for every run, the budget cap where the harness has one (Claude Code only), limits that add up over a run's attempts, `plan` with its estimate and ceiling, `analysis/usage.md` |
| Commit | `0f2abe1` |
| Tests | `test_plan_starts_nothing_and_labels_its_ceiling_by_whether_every_run_has_a_cap`, `test_limits_add_up_across_a_runs_attempts`, `test_usage_record_counts_a_resumed_session_once_and_the_next_plan_estimates_from_it`, `test_run_over_its_time_limit_is_stopped_and_keeps_what_it_wrote` |
| Real run | Passed on Claude Code and Codex, in the milestone 1 study. The usage record equals what each CLI printed. Claude Code's budget cap was seen to stop a run during discovery, not in the study |
| Codex review | Reviewed with part 1: rounds 1 to 4. Final verdict: APPROVE |

Part 3, small additions:

| Item | Detail |
| --- | --- |
| Built | The text-only pass, `scripts/followup.py`, `scripts/extract_answers.py`, replicate spread and variants in `analyze.py`, `scripts/roster.py`, the study brief and its guard, the synthetic panel notice |
| Commit | `a068777` |
| Tests | One or more for each addition, for example `test_text_only_study_gives_panellists_the_words_alone_and_scores_no_design_factor` and `test_follow_up_reaches_the_original_session_and_appends_one_section_without_changing_a_score`. 70 tests passed when the milestone was reviewed |
| Real run | Passed on Claude Code (`haiku`) and Codex. A text-only study built from the roster grid, with a variant persona: 6 runs, two follow-up questions, tallies, an analyst and the writer, the brief guard, and an archive. No real study set `replicates` above 1 |
| Codex review | Rounds 5 to 8 (four rounds). Final verdict: APPROVE |

Part 4, artefact kinds:

| Item | Detail |
| --- | --- |
| Built | `url` and `files` concepts, mixed kinds in one study, single-concept studies, the format caution, a capture that publishes each page or item whole or not at all |
| Commit | `2389a29` |
| Tests | `test_url_and_files_concepts_reach_panellists_under_neutral_names_and_a_url_only_when_the_study_browses`, `test_single_concept_study_passes_checks_and_analysis_with_nothing_ranked_or_compared`, the capture tests. 80 tests passed when the milestone was reviewed |
| Real run | Passed on Claude Code (`haiku`) and Codex. One study of a screenshots concept, a PDF concept and a live page on a local host, a single-concept study with an analyst and the writer, a text-only variant, an archive with concepts, the refusal without Poppler, and one browsing run that opened the live address |
| Codex review | Rounds 9 to 11 (three rounds). Final verdict: APPROVE |

Part 5, the Pi runner:

| Item | Detail |
| --- | --- |
| Built | `scripts/runners/pi.py`, its guard extension `scripts/runners/pi_guard.ts`, and `model_status()` on every runner |
| Commit | `b88c7de` |
| Tests | The `pi` rows of `RunnerTest`, `test_full_materials_study_with_a_model_that_reads_no_images_is_refused_at_the_plan_step`, `test_model_its_harness_does_not_list_or_cannot_sign_in_for_is_refused_before_any_run_starts`. The guard is TypeScript that Pi runs, so it has no test here. 81 tests passed when the milestone was reviewed |
| Real run | Passed on Pi 1.1.0 through its `openai-codex` provider (a ChatGPT subscription login) only: plan, a pilot that read images by path, a time limit then `resume --extend`, the refusals of an unlisted model, a text-only model and a dead login, and `purge-sessions`. Nothing ran on an OpenAI-compatible endpoint |
| Codex review | Rounds 12 and 13 (two rounds). Final verdict: APPROVE |

Part 6, usability studies and launcher-owned browser sessions:

| Item | Detail |
| --- | --- |
| Built | `"type": "usability"`, `scripts/accounts.py` (provision, teardown, reset, success checks), `scripts/browser_session.py` (one session for each attempt of every run that browses, in review studies too), the step limit's backstop, `launch.py check` and `release`, the usability analysis, the secret scan, the archive rules for evidence, `references/usability.md` |
| Commit | `d3b4451` |
| Tests | `BrowserSessionTest`, the browser session and usability tests of `LauncherTest`. 97 tests passed when the milestone was reviewed |
| Real run | Passed on Claude Code (`haiku`) and Codex. Browser sessions: a browsing review study on Claude Code, Codex and Pi. Usability, against a local test app: a study of two personas on both harnesses with two tasks, accounts, success checks, an analyst, the writer and an archive, a study whose panellist signs in, a run stopped and resumed twice, and a task that ran out of steps. These runs came before the fixes of review rounds 16 to 19, which change no instruction a panellist is given and were covered by the tests alone until the usability run under [Follow-up work](#follow-up-work) |
| Codex review | Rounds 14 onwards. The browser sessions were approved with one note in round 15, and round 16 confirmed the note resolved. Round 16 required changes to the usability part (nine findings, all since fixed). Round 17 found seven of the nine resolved, and round 18 the other two. Round 18 also classed as blocking two archive problems that the fix pass had found and disclosed (an unreadable folder, and an empty folder named with a secret); both were fixed. Rounds 14 to 19 (six rounds). Final verdict: APPROVE |

### Follow-up work

Done on 13 October 2026, after milestone 5. It touches the launcher, the
runners, the accounts, the scaffold, the archive and the scripts that read a
study, in studies of both types. The design decisions are under
[Follow-up work after milestone 5](#follow-up-work-after-milestone-5), and
the runs from each kind of shell under
[A lead in a sandboxed shell](#a-lead-in-a-sandboxed-shell).

| Item | Detail |
| --- | --- |
| Built | Fixes for all 14 problems that the milestone 5 fix pass had listed and left. Archive (`archive.py`): one walk and one copy for both study types, a refusal of links and special files, a round built beside the destination and published whole, no empty folders, an empty folder it cannot remove named on stderr with exit code 0, and a closing line that counts the markdown files carrying the synthetic notice. Launcher and accounts: earlier evidence set aside when a run starts afresh, a step count of the launcher's own, harness messages checked for secrets, a `stop` that always stops, and "cannot tell" kept apart from "nothing left". Reading: one safe way to open a persona file, escaped `step_notes`, and safe opens for follow-up copies. And what the runs from other shells showed was missing: a check of what the shell can do before a runner is called ready (`shell_check()` on every runner), `cannot_run` and `session_saved` in `parse_result()`, and scripts that end in one sentence when the study directory cannot be written. Liveness decided by locks where a shell cannot see the study's processes: a study lock file that persists between launchers and that `init_study.py` makes at every scaffold, a lock each attempt's watchdog holds for life, the process namespace on the launcher's lock record and on each watchdog's pid file, no recorded id looked up or signalled across namespaces, a shared lock for the archive of a study that cannot be written, and a lock and a namespace record for a lead's account command |
| Commit | `5e5dfe3` |
| Tests | Eight added, one or more for each area: `test_archive_reads_nothing_through_a_link_or_a_special_file_and_one_that_fails_leaves_no_part_of_itself`, `test_persona_file_that_cannot_be_read_as_the_runs_own_is_no_persona_file_and_nothing_waits_for_it`, `test_step_log_that_is_emptied_or_cannot_be_read_as_the_runs_own_does_not_switch_the_step_backstop_off`, `test_runner_says_what_its_cli_cannot_do_from_a_sandboxed_shell_without_calling_a_model`, `test_run_that_shows_its_cli_cannot_work_from_this_shell_is_not_retried_and_closes_its_runner`, `test_run_whose_session_its_harness_did_not_keep_is_said_once_and_cannot_be_resumed_or_asked`, `test_held_lock_is_a_launcher_running_and_status_says_nothing_of_processes_it_cannot_see`, `test_archive_of_a_study_it_cannot_write_turns_launchers_away_until_the_round_is_copied`. The other fixes extend tests that were there: the scaffold's lock file in `test_scaffold_is_neutral_and_deterministic`, a run settled across namespaces with its browser session in `test_killed_launcher_loses_no_work_and_starts_no_duplicate`, and a lead command recorded in another namespace in `test_provision_command_that_outlived_its_launcher_is_stopped_before_the_run_is_provisioned_again`, among others. 105 tests pass, on Python 3.14. At 104 tests the archive tests also passed on Python 3.12 and 3.13 |
| Real run | Three rounds on 13 October 2026, on Claude Code 2.1.296 (`haiku`) and codex-cli 0.162.1 (default model, low effort), of one text-only review of four runs (two personas on two model entries), with a usability study in the second. Round 1, on the tree at `21ff323`, before the shell check existed: 4 of 4 done from a Claude Code session's shell, from a plain terminal and with no terminal, and from a Codex session only with `run` approved outside its sandbox. Round 2, on a snapshot after the fixes and before liveness was decided by locks: the terminal leg through plan, run, status, checks, extraction, analysis, archive, a second archive (byte for byte the same), two follow-ups (both reached the original sessions) and purge; the Codex lead leg, where `plan` refused inside the sandbox as designed and the lead asked for `run` outside; and a usability study of one persona on both harnesses with two tasks, accounts, success checks and an archive (both runs done, the launcher's step count equal to the step log for every task, no run stopped in error, accounts torn down, no secret found by its shape in any output or in the archive). Round 3, on a snapshot with the lock each watchdog holds, the namespace on each watchdog's pid file and `status` by lock: the same review study from a clean terminal, 4 runs done from one `run` with one attempt each. Mid-run, `status` from the ordinary shell showed four runs alive and the launcher running, and inside a Codex sandbox (no model) it showed the recorded states, "Launcher: running" and the line saying that this shell cannot see the launcher's processes, with no advice to resume or stop. `stop` inside the sandbox exited with 1, signalled nothing and left `runs.json` byte for byte the same, and the runs finished. Each attempt's lock was held by its watchdog while the run lived and by nothing after, and both shells then said "Launcher: not running". Follow-ups reached the original sessions, the archive was complete with no empty folder, a second archive was byte for byte the same, and 4 sessions were purged. No real panel covered what came after that snapshot: the persistent lock file, the shared lock for a read-only archive, the namespace on the launcher's lock record, the account command's lock with its recovery across namespaces, and the scaffold's lock-file failure. Tests cover those, and fake panels inside real sandboxes (Codex's, and `bwrap` for a process namespace of its own), with no model |
| Codex review | Rounds 20 to 27 (eight rounds), in the review session of the earlier rounds. Round 20: launcher and accounts approved, reading approved, the archive sent back with four findings, the lead shell work approved with notes and one finding. Round 20 also confirmed 13 of the 14 problems resolved. Round 21: approved with notes, one finding left (empty folders, the fourteenth problem). Round 22: APPROVE. Rounds 23 to 27 reviewed the sandbox visibility and lock changes. Round 23: changes required, one blocking finding and one that should be fixed. Round 24: changes required, one should-fix finding left, and one item the lead had disclosed classed as blocking. Round 25: approved with notes, two should-fix findings. Round 26: approved with notes, one should-fix finding. Round 27: APPROVE. Every finding Codex required was fixed. Final verdict: APPROVE |

### Acceptance criteria

Every criterion from [Acceptance criteria](#acceptance-criteria), with one of
three marks. A criterion marked "verified on real harnesses" may have a test
as well, named in its evidence.

Runners and launcher:

| Criterion | Status | Evidence |
| --- | --- | --- |
| A Claude Code and Codex panel runs to completion from one `launch.py run`, every persona file passing `check_runs.py` | verified on real harnesses | Milestone 2 study: one `run` finished the four runs left after the pilot, 6 of 6 run files with no blocking problem. Milestone 1 study: 4 of 4 |
| The same panel is started from a Codex session, a Claude Code session and a plain terminal | verified on real harnesses | 13 October 2026, claude 2.1.296 and codex-cli 0.162.1 on Linux, one text-only review of four runs on a `claude` and a `codex` entry: 4 of 4 done from a Claude Code session's shell, from a plain terminal (a clean login environment, a real tty, no harness variable) and with no terminal (`nohup`, stdin from `/dev/null`). From a Codex session it holds on one condition: `launch.py run` is approved to run outside the Codex sandbox (seen with `codex exec --approve-for-me`, where Codex's automatic reviewer decides). Inside the default read-only sandbox `run` is refused in a sentence, and inside `workspace-write` no Codex panellist can complete. An interactive session's approval prompt was not tested. Round 3 of the follow-up work, the same day: 4 of 4 again from a clean terminal, one attempt each, while `status` and `stop` from inside a Codex sandbox reported the recorded states, signalled nothing and changed nothing. [A lead in a sandboxed shell](#a-lead-in-a-sandboxed-shell) |
| Model agreement covers pairs across vendors | verified on real harnesses | Milestone 3 study: `haiku-codex`, Spearman 0.50 over three concepts |
| A run past its time limit stops, keeps what it wrote and is `limited` | verified on real harnesses | `test_run_over_its_time_limit_is_stopped_and_keeps_what_it_wrote`. Milestone 1 on Claude Code and Codex, milestone 4 on Pi |
| A usage limit leaves runs `blocked`, other runners unaffected, and `resume` finishes them | verified by tests only | `test_usage_limit_blocks_one_runner_and_resume_finishes_its_run`. No usage or rate limit has been seen in a real run. The nearest real case was the milestone 1 pilot, Codex only: a capacity refusal left its run `blocked`, the Claude Code run finished, and `resume` completed it. See [Built but not tested](#built-but-not-tested) |
| Killing the launcher mid-panel loses no work and starts no duplicate | verified on real harnesses | `test_killed_launcher_loses_no_work_and_starts_no_duplicate`. Milestone 1 study: the next `run` cleared the stale lock, adopted the live Codex run and finished 4 of 4. Since the follow-up work the next launcher tells a live run by the lock its watchdog holds, also where it cannot see the run's processes. Round 3 of the follow-up work: each attempt's lock was held by its watchdog while the run lived and by nothing after, and a `stop` from inside a Codex sandbox signalled nothing and left `runs.json` byte for byte the same. No launcher was killed in that round. A launcher killed with its runs alive, one killed with its runs ended and one killed inside a sandbox were checked with fake panels inside real Codex sandboxes |
| A panellist does not see the lead project's instruction files | verified on real harnesses | Milestone 1: a marker term in the project's `AGENTS.md` and `CLAUDE.md` is in no persona file or analysis file, on Claude Code and Codex. Pi: in its discovery fixture only. Codex's user-level `AGENTS.md` is not covered |
| `plan` starts no process and makes no model call | verified by tests only | `test_plan_starts_nothing_and_labels_its_ceiling_by_whether_every_run_has_a_cap`. Since milestone 4 the claim is narrower: `plan` starts no run and changes no study file, and a sign-in check may let a harness refresh its own login. Since the follow-up work it also tests the shell: a write to the study directory that leaves nothing behind, and for `codex` a probe that builds a sandbox with no model call (`test_runner_says_what_its_cli_cannot_do_from_a_sandboxed_shell_without_calling_a_model`). Where the shell cannot run a panel it shows the runner as `CANNOT BE USED` and exits with 1, which was seen with the real CLIs in real Codex sandboxes |
| `run` never restarts a `partial` or `limited` run | verified by tests only | `test_run_and_resume_start_only_the_states_they_own` |
| Analyst and writer jobs run on the `synthesis` models, the writer after the analysts | verified on real harnesses | `test_analysts_then_the_writer_run_on_their_own_models_within_a_share_of_the_pool`. Milestones 1, 2, 3 and 5, always on Claude Code `sonnet` |
| An existing archived study still passes `extract_scores.py` and `analyze.py` | verified by tests only | `test_archived_study_from_before_run_completeness_still_analyses`, `test_runs_json_from_before_model_entries_still_works` |

Limits and usage:

| Criterion | Status | Evidence |
| --- | --- | --- |
| `plan` shows an estimate, a ceiling and its label, and the limits in force | verified by tests only | `test_plan_starts_nothing_and_labels_its_ceiling_by_whether_every_run_has_a_cap` |
| After a pilot, `plan` uses the measured usage | verified by tests only | `test_usage_record_counts_a_resumed_session_once_and_the_next_plan_estimates_from_it` |
| `analysis/usage.md` matches what each harness reported | verified on real harnesses | Milestone 1 study: the Claude Code and Codex figures equal the totals in each CLI's output, rechecked on 13 October 2026. Pi's figures were not rechecked against its session file |
| A run stopped by a limit is absent from every headline table and listed as incomplete | verified by tests only | `test_run_stopped_by_a_limit_is_listed_apart_from_the_headline_tables` |

Small additions:

| Criterion | Status | Evidence |
| --- | --- | --- |
| A text-only study completes and its analysis has no visual factors | verified on real harnesses | Milestone 2 study: 6 runs on Claude Code and Codex, and no visual or mobile factor in `quant.md` or `scores.csv` |
| A follow-up reaches the original session and appends one section without changing any score | verified on real harnesses | `test_follow_up_reaches_the_original_session_and_appends_one_section_without_changing_a_score`. Milestone 2 study: one Claude Code run and one Codex run answered in their recorded sessions, with no score changed. Follow-up work, round 2: two follow-ups, both in the original sessions. Round 3: follow-ups again reached the original sessions |
| Tallies match a hand count of three runs | verified on real harnesses | Milestone 2 study: three persona files recounted on 13 October 2026 (6 Found; 5 Found and 1 Partly; 6 Found), the same as `answers.csv` |

Artefact kinds:

| Criterion | Status | Evidence |
| --- | --- | --- |
| A PDF and a set of screenshots are reviewed under neutral labels | verified on real harnesses | Milestone 3 study: both reached the panel as `item-<NN>` folders under concept letters, and 4 runs on Claude Code and Codex finished |
| A page on a local host is captured and reviewed | verified on real harnesses | Milestone 3 study: a page served on `127.0.0.1` was the third concept |

Pi runner:

| Criterion | Status | Evidence |
| --- | --- | --- |
| A panel includes a model on an OpenAI-compatible endpoint | not verified | No such endpoint is configured in Pi on this machine. Pi ran through its `openai-codex` provider only |
| A full-materials study with a text-only model is refused at the plan step | verified by tests only | `test_full_materials_study_with_a_model_that_reads_no_images_is_refused_at_the_plan_step` |

Usability:

| Criterion | Status | Evidence |
| --- | --- | --- |
| Panellists on two harnesses attempt a task on a local build, each with its own account, and produce step logs with screenshots | verified on real harnesses | Milestone 5 study: 4 runs on Claude Code and Codex, each with a provisioned account that was torn down |
| A task that uses its step limit keeps its last step, and the run goes on to the next task | verified on real harnesses | `test_task_that_uses_its_step_limit_keeps_its_last_step_and_a_run_that_passes_the_limit_is_stopped`. Milestone 5, Claude Code: a task with a limit of 3 ended "ran out of steps" with its third result and screenshot saved, then the run did the next task. The launcher's backstop has stopped a run only in the tests. In the follow-up usability run its count equalled the step log for every task and it stopped nothing |
| An archived usability study contains the step logs and screenshots its synthesis cites | verified on real harnesses | `test_usability_archive_keeps_the_evidence_without_a_secret_or_a_screenshot_that_could_show_one`. Milestone 5 archive: all 59 step and screenshot citations in the synthesis resolve in the archived evidence, checked on 13 October 2026 |
| A claimed success that the check denies is flagged | verified by tests only | `test_claim_that_the_success_check_denies_is_flagged_and_a_check_that_fails_to_run_is_no_verdict`. No real run in milestone 5 made such a claim. The follow-up usability run had success checks, and whether a claim and a check disagreed in it is not on record here |
| No secret value in any persona file, step log or synthesis, and no archived screenshot from a step that could show one | verified by tests only | `test_secret_value_in_a_persona_file_or_step_log_fails_its_run_and_is_never_printed` and the archive test above. In milestone 5 a planted secret was refused by `check_runs.py` and `archive.py`, and the archive of the sign-in study left out every screenshot. In the follow-up usability run, on the changed tree, a search by shape found no secret in any output or in the archive. That is one small run and a search that knows only the shape of a secret, so the mark stays |
| A remote target without `allow_remote` is refused | verified by tests only | `test_invalid_model_entries_and_options_are_refused`, the case "a usability target that is not a local host" |

Documents:

| Criterion | Status | Evidence |
| --- | --- | --- |
| `SKILL.md` names no harness tool, and a harness other than Claude Code completes a study by following it | not verified | `SKILL.md` says "your harness's shell tool" and names no tool. A Codex session led the `plan` and `run` steps of one panel on 13 October 2026. No harness other than Claude Code has completed a study by following `SKILL.md` |

### Built but not tested

- **Pi against an OpenAI-compatible endpoint.** None is configured in the
  user's Pi. It needs a provider in `~/.pi/agent/models.json` or an
  OpenRouter login, which is the user's to set up. Tool calling, usage
  figures, image input and error text on such an endpoint are all unknown.
- **macOS.** Everything ran on Linux. The watchdog's path for a Python
  without `os.waitid` runs in the tests (`LauncherWithoutWaitidTest`), on
  Linux. The locks that say whether a launcher, a run or a lead's command is
  alive are plain `flock`, which macOS has. macOS names no process
  namespace, so nothing records one there, none of the work on a sandboxed
  lead was run there, and Codex's sandbox on macOS is a different one.
- **Usage-limit and rate-limit detection, on all three harnesses.** The
  patterns are inferred from documentation and message shapes, and no limit
  was ever seen. The one refusal seen in a real run was a Codex capacity
  error ("Selected model is at capacity"), which ends in the same `blocked`
  state.
- **A harness other than Claude Code as the lead of a whole study.** A Codex
  session led the `plan` and `run` steps of one panel on 13 October 2026. No
  harness other than Claude Code has completed a study by following
  `SKILL.md`. Not tested from a Codex lead:
  - an interactive Codex session, where the request to run outside the
    sandbox goes to the user as an approval prompt
  - full access mode
  - `pilot`, `resume`, follow-ups, `purge-sessions --yes` and the analyst and
    writer jobs
  - a usability study
- **The last lock changes on a real panel.** Round 3 of the follow-up runs
  used a snapshot with the lock each watchdog holds, the namespace on each
  watchdog's pid file and `status` by lock. What came after it is covered by
  tests and by fake panels inside real sandboxes (Codex's, and `bwrap` for a
  process namespace of its own), with no model:
  - the study lock file that persists between launchers
  - the shared lock for the archive of a study that cannot be written
  - the namespace on the launcher's lock record
  - the account command's lock and its recovery across namespaces
  - the scaffold's failure when it cannot make the lock file
- **A launcher killed while a real panel runs under the lock work.** A
  launcher killed with its runs alive, with its runs ended, inside a sandbox
  that ended and inside one that stayed open was checked with fake panels
  inside real Codex sandboxes. So was the archive's report of an empty
  folder it cannot remove.
- **Sandbox cases checked under `bwrap` only, not under `codex sandbox`:** a
  lead's account command left on the other side of the sandbox, and
  `archive.py` inside while a launcher starts outside.
- **A process inside a sandbox that holds the launcher's process id under
  the same start time.** No sandbox was made to produce one. The tests cover
  it with a lock file edited to name a live process and another namespace.
- **The `pi` runner in any sandbox.** Its `shell_check()` is inferred.
- **The usability protocol on larger panels and larger models.** The largest
  usability study was 4 runs, on `haiku` and on Codex at low effort. The
  default time limit and the "decide from the screen" result both rest on
  that.
- **Features with tests and no real run on record:** the step limit's
  backstop stopping a run, a sequential usability study with
  `accounts.reset`, a remote usability target (`allow_remote`), and
  `replicates` above 1.
- **Refusals and failure paths of the follow-up work, which have tests and
  no real run on record:** the archive's refusal of a link or a special file
  and its recovery from an interrupted publish, a persona file or step log
  that cannot be read as the run's own, a step log cut or rewritten,
  evidence set aside on a fresh start, a harness message withheld for a
  secret, and a run ended as `cannot_run` or as "session not saved". Both
  endings were seen in round 1, before the code that names them existed, and
  `cannot_run` is recognised from output recorded then.
- **Analyst and writer jobs on Codex or Pi.** Every real one ran on Claude
  Code.
- **A usability study with a Pi panellist.** Pi browsed in a review study
  only.
- **The discovery questions still open.** The lists "Still open after
  milestone 1", "milestone 4" and "milestone 5" under
  [Discovery](#discovery) stand as written.

### Not built

- Runners for OMP and OpenCode.
- A study option that replaces a harness's system prompt
  ([decision](#system-prompt-override-experiment-and-decision)).
- A limit on where a panellist's browser can go.
- A test of network access before a run starts. A proxy or a custom endpoint
  makes any general test unreliable, so a run's own output shows it.
- A way for a Codex panellist to run inside a lead's Codex sandbox
  (`workspace-write`). A Codex CLI cannot build its own sandbox there, and
  no writable directory changes that.

### Known limitations

The user set the trust boundary: a panellist can write only under `panel/`.
`logs/`, `accounts/`, `runs.json` and the records are lead-only and trusted.
A finding that needs someone to tamper with a lead-only file is out of scope
and is recorded here, not fixed.

Harnesses and isolation:

- Codex cannot exclude the user-level `AGENTS.md`, so it reaches every Codex
  panellist.
- Codex and Pi have no budget cap. The time limit is what bounds their runs.
- Codex reports no cost and no duration, and Pi no duration.
- Claude Code always gives the model the account email, the working
  directory path, the OS version and the date.
- A Codex run that may browse has network access for its whole shell: the
  setting is all or nothing.
- Codex writes a trust entry to the user's `config.toml` for a run inside a
  git repository.
- The Pi guard is tied to Pi 1.1.0: it repeats that version's path handling
  step by step. It does not see a link swapped in between its check and the
  tool's use, or a hard link.

Browsing and usability:

- The rules for a remote target are instructions to the panellist only.
  Nothing stops a browser from submitting a form.
- Nothing limits where the browser goes. The local-host rule reads the host
  name alone, so a local name that proxies a hosted service passes.
- The browser's debugging port stays open, and the element list shows more
  than the screen does.
- The secret scan covers known fingerprints only. It misses a value written
  another way (split, in another case, encoded or masked) and a secret
  shorter than 4 characters. Screenshots and saved-state cookies cannot be
  scanned.
- The fingerprint hash is fast, so a weak test password can be guessed from
  the lead-only file until teardown makes it worthless.
- A harness's own transcript holds any credential a panellist read or typed.
- `launch.py check --force` on a kept verdict, while the run has a new
  account, judges the old task against the new account. The output warns.
- Browser processes can survive when a session's daemon and the browser's
  main process were both killed outright.
- `status` never holds the study lock (it only asks whether one is held), so
  it settles nothing. The next `run`, `resume`, `stop` or follow-up does.

Recovery:

- When a watchdog was itself killed, the launcher checks who holds the CLI's
  process id and then signals its group. The id could change hands between
  the two.
- A study directory that cannot be written is archived under a shared lock
  on `.launch.lock`, not under the launcher's own. It keeps launchers out
  for the copy. The one study it cannot protect is in the list below.
- The reader that keeps an unsettled follow-up's edits away from the scripts
  has no permanent test for its race: it was checked with a throwaway stress
  run.
- A watchdog killed on its own in another process namespace can leave its
  CLI running. A launcher in any other shell settles the run and adds to its
  reason that the CLI could not be checked from there. Look for the CLI in
  the shell that started the run.

The 14 problems that the milestone 5 fix pass listed here and left are fixed
([Follow-up work](#follow-up-work)).

Noticed during the follow-up work and left as they are:

- `purge-sessions` lists a run once for each attempt's session, with nothing
  to tell the lines apart, and says "found no session to delete" for a
  session that was never saved.
- A usability study's `analysis/` has a `rankings.csv` that holds a header
  line only.
- Two archives to one destination at the same time are not serialised. Each
  leaves whole files, but one can fail with a "could not be finished"
  message.
- `capture.py` still decides by process id that another capture's scratch
  folder is dead. A reused id delays its recovery, and a capture started
  inside a sandbox could remove the scratch of one running outside.
  Captures can be regenerated.
- Archiving a round that is already archived would skip its personas and
  panel instructions, because the kept names are the study's paths. Not
  tested.
- The secret scan of `analysis/*.md` and the archive's scan still guard
  against links with a path comparison (`read_kept()`), which is weaker than
  the descriptor walk used elsewhere. The scan and the copy read a file
  separately.
- A persona file that is not valid UTF-8 ends every reader in a traceback.
- `launch.py status` shows a run whose persona file cannot be read as
  `pending` and does not say why (only `check_runs.py` does), and `run`
  would start it afresh.
- An analyst's brief names persona files by path, and the analyst's own
  tools would follow a link there. It can happen only with
  `--allow-incomplete`.
- `init_study.py --force` does not remove `logs/*.evidence` from an earlier
  scaffold.
- A launcher killed between setting evidence aside and writing `runs.json`
  leaves the earlier evidence in `logs/` with the run unchanged.
- Messages that do not come from a harness result are printed without a
  check for secrets: those of `purge-sessions`, of the runner checks and of
  a browser session that failed to start. None comes from a panellist
  process.
- `browser_session.py` treats "no process list" as "nothing left".
- `shell_check()` does not probe the folder a CLI keeps for one working
  directory under its sessions root.
- The `claude` runner calls `claude auth status` once for each attempt that
  ends, to find where sessions are kept.
- On a file system without `flock`, a sandboxed shell falls back to process
  ids and can settle runs it cannot see.
- A run settled as "watchdog was killed", as every run is that was settled
  after its sandbox ended, has no flag that its spend was not reported.
- Liveness across process namespaces is Linux only in what it records: a
  launcher, a watchdog and a lead's command name their namespace there and
  not on macOS. macOS was not run at all.
- A study scaffolded before the lock file was kept has none until a launcher
  or a new scaffold makes one, so a read-only archive of it cannot keep a
  launcher out. Start no launcher on that study until the archive has
  finished.
- Archiving an already archived round from a shell that can write it leaves
  an empty `.launch.lock` in that source round, never in the copy.
- A lead who deletes `.launch.lock` while a launcher runs breaks the
  one-launcher guarantee. The skill's documents say not to delete it.
- After a sandbox ended part of the way through a lead's account command,
  the study waits for the lead to delete the command's record.
- A process that a lead's command means to leave running keeps the command's
  lock if it keeps the descriptor. After a killed launcher it holds the
  study until the lead stops it or deletes the record.
- A command started through `sudo`, or a worker started with its descriptors
  closed, holds no lock while it runs. Recovery in the same namespace still
  goes by process ids for that reason.
- `followup.py list` waits 5 seconds behind an archive that is reading the
  study.
- `archive.py` prints a traceback on Ctrl-C.
- From a shell outside a sandbox that can write the study, `archive.py`
  takes the lock and archives a study whose launcher was killed while its
  runs are still alive and in sight. Only `init_study.py --force` refuses on
  runs still at work.
- Inside a sandbox, `status` still prints each run's recorded process id,
  which names nothing in that shell.
- `init_study.py` and `analyze.py` label a study by its folder name, while
  `plan` uses the study's own name.

Up to round 19 Codex raised no finding that was left unfixed, and none
outside the trust boundary. In rounds 20 to 27 every finding it required was
fixed, and none was left. The `shell_check()` item above is one it classed
as optional.

### The user's decisions

All made on 13 October 2026.

- **The Pi runner stays as built,** with no further Pi work. Runners for OMP
  and OpenCode are not started.
- **The `claude` and `codex` runners keep their harness's default system
  prompt.** The experiment showed no measurable difference
  ([System prompt override](#system-prompt-override-experiment-and-decision)).
- **Open questions 5 and 6 are built as drafted.**
- **Fix the 14 problems that the milestone 5 fix pass had left, and settle
  the criterion on starting a panel from a Codex session, a Claude Code
  session and a plain terminal.** Both are done
  ([Follow-up work](#follow-up-work)).
- **The PRD and the skill say "the user" and name no person,** because the
  repository is public.

How each of the [open questions](#open-questions-for-the-user) was settled:

| Question | Settled as |
| --- | --- |
| 1. Default concurrency | 6 for Claude Code, 4 for Codex, 3 for Pi |
| 2. Native mode | Kept |
| 3. Pi as the third runner | Pi, as built. No OMP or OpenCode runner |
| 4. Reusable rosters | Project-local. No shared location |
| 5. Remote targets for usability studies | Only with `allow_remote: true`, with read-only tasks and no accounts |
| 6. Credentials in harness transcripts | Accepted: bounded by throwaway accounts, teardown and `purge-sessions` |

### Where to pick up

1. Run the tests and confirm that all 105 pass.
2. Lead one small study from a harness other than Claude Code by following
   `SKILL.md` from its first step to the archive. That settles one
   criterion. On Codex, follow `references/runners.md`, "A lead on Codex",
   and cover what a Codex lead has not done: an interactive session's
   approval prompt, `pilot`, `resume`, a follow-up, the analyst and writer
   jobs, and a usability study.
3. Run one small panel on the tree as committed, with a shell inside a
   sandbox beside it, to cover what no real panel has: a read-only archive
   while a launcher starts outside, a launcher killed with its runs alive,
   and a usability study whose account command is cut off when its sandbox
   ends ([Built but not tested](#built-but-not-tested)).
4. Run the tests and one small study on macOS, with a lead inside Codex's
   sandbox there.
5. When a usage or rate limit next happens, keep the CLI's output and exit
   code, compare them with the patterns in `scripts/runners/` (each is marked
   verified or inferred), and add the real output to
   `test_runner_parses_recorded_outcomes`.
6. Run a usability study of real size on larger models. Check the default
   time limit against the measured time for each step, and whether panellists
   open their screenshots.
7. Decide which of the items under "Noticed during the follow-up work and
   left as they are", above, are worth fixing.
8. If Pi work resumes: configure a provider for an OpenAI-compatible endpoint
   in Pi, pilot a model on it, and recheck the guard against the installed Pi
   version. That settles the other criterion.
9. Merge the branch, then update the status line at the top.

### Leftovers on this machine

- Two scratch `trust_level` entries in `~/.codex/config.toml`, for the
  projects `.../scratchpad/disc-codex/iso/parent/proj` and
  `.../scratchpad/e2e-m1/project`. The user may want to remove them. The
  follow-up work did not change that file.
- Eight `/tmp/agent-browser-chrome-*` directories, dated 12 October 2026.
- The scratch studies, under the scratchpad directory of the Claude Code
  session that did the work (under `/tmp/claude-<uid>/`). The scratch
  folders of the checks made with fake panels are there too.
- Harness sessions of the scratch studies. `purge-sessions` was run in
  milestones 1 and 4, for the round 1 panels of the follow-up work that
  finished, in the terminal leg of round 2 and in round 3 (4 sessions).
  Whether the other studies' sessions were purged is not verified.
- Nine Codex sessions in `~/.codex/sessions/2026/10/13/`, of the Codex leads
  used in the follow-up runs and of their automatic reviewers. The lead
  agent left them. `codex delete --force <id>` removes one.
- Empty folders in `~/.claude/projects/`, named for the scratch studies. The
  study of round 3 left one more.
- Two small folders, `/tmp/persona-panel-launch-*`, left by a proof run of
  the old code.

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
- The lead agent can be any harness, and the user can run the launcher from a
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

**Who can lead.** Any harness, or the user in a terminal.

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
were then corrected from real runs, and the Pi column on 13 October 2026; see
[Discovery](#discovery).

| Need | Claude Code | Codex | Pi |
| --- | --- | --- | --- |
| Headless run | `claude -p`, prompt on stdin | `codex exec -`, prompt on stdin | `pi -p --mode text`, prompt on stdin |
| Model | `--model` | `-m` | `--provider <provider> --model <id>`, an exact row of the model listing, checked by the runner |
| Thinking effort | `--effort`, validated by the runner | `-c model_reasoning_effort=`, validated by the runner | `--thinking`, validated by the runner |
| Working directory | process cwd | `-C` | process cwd |
| Keep user and project instructions out | `--safe-mode --restricted --strict-mcp-config --disable-slash-commands --settings '{"includeGitInstructions":false}'` | `--ignore-user-config --ignore-rules -c project_doc_max_bytes=0 -c skills.include_instructions=false --disable plugins --disable tool_suggest`; the user-level `AGENTS.md` cannot be excluded | `-nc -ns -ne -np --no-themes --no-mcp --no-approve --system-prompt "" --append-system-prompt ""` |
| Restrict tools | `--tools`, `--allowed-tools`, `--permission-mode dontAsk` | `-s workspace-write`, `-c approval_policy=never` | `--tools`, and a guard extension loaded with `-e`: Pi has no sandbox and no approvals |
| See an image | reads files by path | reads files by path; `-i` exists and is not used | reads files by path, on a model its listing says takes images; `@file` exists and is not used |
| Machine-readable output | `--output-format stream-json --verbose` | `--json` | the session file: `--mode json` exists and is not used |
| Session id | `--session-id <uuid>`, chosen by the runner | `thread_id` on the first output line | `--session-id <uuid>`, chosen by the runner |
| Resume | `--resume <id>`, with every launch flag repeated | `codex exec <every launch flag> resume <id>` | `--session <id>`, with every launch flag repeated, from the same directory |
| Budget cap | `--max-budget-usd`, per process | none | none |
| Delete a session | remove its transcript file | `codex delete --force <id>` | remove its session file |

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

### Deviations decided during milestone 3

Config:

- **A `url` concept's pages are named:** `"pages": [{"name", "url"}, ...]`,
  the first named `index`, or `"url"` alone for one page. A URL is `http` or
  `https`. `states` work on them as on site pages.
- **A `files` concept is `"files"`, an ordered list, or `"path"`, a folder**
  whose images and PDFs are taken in natural name order (`screen-9` before
  `screen-10`). Other files in the folder are ignored.
- **Kinds can mix in one study.** Labels and orders are shuffled over all.
- **Concept ids must be unique,** and a key that belongs to another kind is
  refused with the `kind` it implies.
- **A study with one concept needs `artefact`,** the singular of
  `artefact_plural`, when it sets the plural. The default has both.
- **Two capture settings:** `capture.max_pdf_pages` (default 20) and
  `capture.pdf_pixels` (default 1600, the long side of a page image).

Materials:

- **A file is a folder `item-<NN>`,** numbered in reading order, never named
  after the file. An image is `image.<type>`, a PDF is `page-<NN>.png` and
  `page-text.txt`, set out as on the page, with a `[Page N]` line before each
  page.
- **A very tall image is also cut into overlapping `part-<NN>.png` pieces.**
  The PRD said images as they are: the original is kept, but a full-page
  export is shrunk by whatever reads it until its text is unreadable.
  Panellists review it from the parts, and the default `haiku` note rules out
  opening the whole image.
- **A PDF past the page limit is cut, images and text alike,** with a loud
  warning. A PDF with no text warns, and stops a text-only capture.
- **Nothing is copied for `url` or `files` at scaffold time.** `capture.py`
  reads the live page and the source files, and nothing but `key.md` holds a
  file name or URL.
- **`capture.py` removes page folders a concept no longer has,** when it
  captures the whole concept, and keeps an earlier capture when a page
  cannot be opened. It warns when a server answers 400 or above.
- **A text-only study takes a `files` concept's PDFs and leaves its images
  out.** A concept of images alone is refused.
- **Poppler is checked by `init_study.py`, `capture.py` and `plan`.** The
  first two stop, and the plan lists it as missing.

Browsing:

- **A study of `files` concepts alone never browses,** whatever `browse`
  says.
- **With `"browse": true` the instructions list each URL page's address,**
  tell panellists to stay on those sites and to submit, buy, download or log
  in to nothing, and to score from the materials when the live page differs.
  A `files` concept is named as having nothing to open.
- **Nothing limits the browser to those hosts.** The plan says so, names the
  external hosts and the ones on this machine, and the Claude runner's
  browsing gap now names network addresses beside `file://` paths.
- **The instructions drop "They are drafts, not live"** when a study has a
  `url` concept. The lead says which it is in `context_notes`.
- **`init_study.py` makes `panel/scratch/<run id>/` for each run that may
  browse,** and the instructions say to run each `agent-browser` command on
  its own: a runner may allow that command and no other. This changes the
  scaffold of a study of sites that browses.

Single-concept studies:

- **The persona file has no "Review order" row,** `key.md` no review orders,
  and the concept template carries the label itself.
- **`rankings.csv` is the header alone,** whatever a panellist wrote.
- **`analyze.py` reports "Scores"** (mean, median, SD, lowest and highest of
  each factor) in the leaderboard's place, every factor by segment and by
  model, and model agreement on the one concept: the mean absolute
  difference between a persona's runs on two models, and the Spearman across
  their factor scores. `quant.json` has `concept` and `scores`, and no
  `leaderboard` or `order`.
- **`quant.json` never holds `NaN`,** in any study: a value that could not be
  computed is `null`, so a strict JSON reader can load the file.
- **The briefs take three new placeholders:** `<REVIEWED>` (in place of the
  count, labels and plural), `<ONE_CONCEPT_NOTE>` and `<KINDS_NOTE>`, filled
  from `assets/*-brief-one.md` and `assets/brief-kinds-*.md`.
- **Counts in the briefs are placeholders with their noun,** so one persona
  or one model reads right: `<PERSONAS>`, `<MODELS>`, `<RUNS>`,
  `<OWN_PERSONAS>` and `<FILES>` replace `<N_PERSONAS>`, `<N_MODELS>`,
  `<N_RUNS>`, `<PERSONA_RANGE>` and `<N_FILES>`.

Plan and archive:

- **The plan lists each concept's kind, when a live page was captured,** a
  concept with nothing captured, a source the scaffold or the capture will
  refuse (a folder of images alone in a text-only study, a file that is
  gone), and a folder under `panel/materials` that belongs to no concept. It
  notes that Mobile is a guess for `files` concepts, and that the token
  estimate is one too.
- **The plan counts a PDF as a PDF with its pages and an image as one
  image.** The estimate before a pilot multiplies the method's figure per
  page by what a run opens: each web page, PDF page and supplied image.
- **`run`, `pilot` and `resume` start no panellist run while a concept has
  nothing captured,** and name the concept and `capture.py` as the plan
  does. Analyst and writer jobs are not held back.
- **`archive.py --concepts` copies a `files` concept's files** and takes no
  screenshot of them. For a `url` it copies nothing: `key.md` has the
  addresses, and `snapshot.py --url` screenshots the live page as it is at
  archive time, skipping one that cannot be opened.
- **A second example, `assets/study.files.example.json`:** one concept made
  of files.

Found in the first real run on two vendors:

- **Concepts of different forms get a format caution.** A form is a captured
  page (site or URL), image files or PDF files, so a PDF beside a screenshot
  counts though both are `files`. `quant.md` says so above "Key numbers" and
  under "By factor", naming each concept's form and the `needs_design`
  factors, `quant.json` has `forms`, and the briefs add
  `assets/brief-kinds-mixed.md`. A text-only study gets none.
- **`init_study.py` and the plan warn when every persona reviews in the same
  order,** variants apart, and suggest another `seed`. The shuffle is
  unchanged, so existing studies keep their orders.
- **`resume` names a section written without its score row** and asks for
  the score table to be added to it, with nothing else changed.
- **`archive.py --concepts` says, for each `url` concept, how many pages were
  screenshotted and how many skipped.** It calls `snapshot.take()` in place
  of running `snapshot.py`.
- **One helper makes every counted sentence agree:** `agree()` and its
  counted form `plural()` in `panel_lib.py`. "N of M runs complete" is "1 of
  1 run complete" for one run.

Found in review:

- **Site copies are in `panel/sites/` only when panellists browse.** A copy
  is page source under its own file names, so every other study (`"browse":
  false`, a `url` concept without `"browse": true`, a text-only study) keeps
  them in `<study>/sites/`. `init_study.py --force` moves them when `browse`
  changes, and the plan notes copies left in the wrong place.
- **Names that become paths are validated when `study.json` is loaded:**
  state names (the page-name rule), concept ids, persona ids and slugs (one
  part of a file name, with no leading dot or hyphen), and pinned `labels`
  (letters and digits, one for every concept). Concept ids and persona ids
  are unique ignoring case, a concept id has no `--`, and two states of a
  page cannot share a name. `capture` settings must be numbers and words.
  A persona id holds no hyphen, the rule `roster.py` already had, and a
  persona whose name gives an empty slug needs a `"slug"`.
- **`capture.py` checks every path it fills or deletes** resolves inside
  `panel/materials`, and refuses before touching anything. A site page file
  whose name cannot name a folder stops the scaffold.
- **A page or item is captured whole or not at all.** Each is captured in
  `<study>/.capture-*/` and moved into place on success. A failure leaves an
  earlier capture as it was, the rest are captured, and `capture.py` exits
  non-zero with every failure. An address that cannot be opened no longer
  stops the capture. A killed capture's scratch folder is settled and
  removed by the next one, and is never archived: a move into place that was
  under way is recorded there, and the next capture finishes it or puts the
  earlier capture back, so an earlier capture is never lost with the folder.
- **The plan and `run` need every page, state and item,** not one folder per
  concept: a page folder counts with its `page-text.txt`, an image item with
  its image. `plan --json` has `materials.incomplete`.
- **External tools get no name from `study.json`.** ImageMagick runs in the
  folder it writes to, with file names the script chose, and Poppler and
  `agent-browser` get absolute paths. `snapshot.py` refuses two pages that
  would share a file name, and a `--url` that is not `http`, `https` or
  `file`.
- **`archive.py --concepts` names each copied file `item-<NN>-<its name>`,**
  so files of one name from different folders are all kept, and says when it
  replaces an earlier archive's file of other content.
- **`forms.json`, beside `key.md`, records each `files` concept's form.**
  `init_study.py` and `capture.py` write it, `archive.py` carries it, and the
  analysis reads it when the source files are gone, so an archived PDF beside
  an image keeps its format caution.

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

### Deviations decided during milestone 4

- **Nothing was run on an OpenAI-compatible endpoint.** The Pi installation
  the runner was built against had one working provider, a ChatGPT
  subscription login, and no endpoint configured. The runner was verified
  against that provider. The acceptance criterion "A panel includes a model
  on an OpenAI-compatible endpoint" is still open: it needs a provider in
  Pi's `models.json` or a built-in provider signed in.
- **The runner ships a guard extension,** `scripts/runners/pi_guard.ts`,
  loaded into every run. Pi has no sandbox and no approvals: its file tools
  read and write wherever the user can. The guard keeps them inside the
  working directory with symbolic links followed, refuses the shell, and
  with browsing on allows one `agent-browser` command at a time.
- **A run cannot start without the guard.** The launch passes a flag that
  only the guard defines, so Pi refuses to start when the guard is missing
  or fails to load, and `check()` fails first.
- **The runner interface has a seventh function, `model_status(entry)`,**
  on every runner. It reports, for one model entry and without a model call,
  whether the harness has the model, whether its provider is signed in,
  whether it reads images and who receives the materials. `plan` and `run`
  refuse a model the harness lacks, one whose provider is signed out and, in
  a full-materials study, one that reads no images. Claude Code and Codex
  cannot tell without a model call, so their runner-wide answers stand.
- **A Pi model entry needs `model`,** an exact `<provider>/<id>` from Pi's
  model listing. [`study.json` changes](#studyjson-changes) says an entry
  without one uses the harness default: in Pi that is the user's own default
  model and thinking level, and Pi matches an inexact name loosely or sends
  it to the API as it is.
- **Pi runs print text, and their facts come from Pi's session file.** The
  JSON event stream repeats every image a run reads six times (17.4 MB of
  output for one 2.9 MB sheet), which would put gigabytes in `logs/`. A
  real run that read four sheets left 191 bytes of output and a 2.8 MB
  session file.
- **`parse_result` takes a fourth argument, the session id** the command was
  built with, which the launcher passes back. Text output does not name the
  session, so the Pi runner needs it to find the session file.
- **Pi usage is session-scoped,** summed from the session file, so the
  finished requests of a stopped run are counted at once.
- **The runner passes `--session-dir`,** set to the folder Pi would use by
  default, so a `sessionDir` setting cannot move sessions away from where
  the runner reads and purges them.
- **Default concurrency is 3,** the most that was run at once.
- **`assets/study.example.json` has no Pi entry.** A placeholder model id
  would make the example fail its own plan. The entry's shape is in
  `references/runners.md`.

## Part 6: Usability studies

`"type": "usability"` tests whether a persona can complete tasks in a running
product, thinking aloud.

What was built differs from this part in places: who owns the browser
session, what a panellist's `account.json` holds, how a remote target is
held to its rules, and what a success check's exit code means. Each is in
[Deviations decided during milestone 5](#deviations-decided-during-milestone-5),
which wins where the two disagree.

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

### Deviations decided during milestone 5

Browser sessions, which every browsing study now uses:

- **The launcher side owns the browser, and a panellist only sends it
  commands.** [Protocol](#protocol) says a panellist opens the start page
  "in its own `agent-browser` session", and review studies had each run
  start one. Nothing a run starts survives a Codex shell call, an unpoliced
  session lets a run read cookies and page source, and cleanup was left to
  the panellist.
- **Each attempt has a session of its own, started and stopped by its
  watchdog.** `run_watchdog.py` takes optional "before" and "after" commands
  and knows nothing of browsers. "after" runs however the attempt ends, so
  cleanup does not depend on a launcher being alive. When "before" fails the
  CLI is never executed: the run "could not be started", with the reason,
  and nothing is marked failed.
- **A new script, `scripts/browser_session.py`,** starts and stops a
  session. It makes a socket directory for the session alone, starts the
  session in the run's working directory at the study's desktop viewport,
  puts the action policy in place and checks that it is in force. It
  records the daemon and the browser with their start identities, and stops
  only processes it can still identify as its own.
- **Stopping a session never runs `agent-browser`.** Every close path of
  the CLI (0.38.1) can end in a signal to whatever process a pid file
  names: `close --all` when the socket does not answer, and `close` for one
  session when it restarts a session whose settings differ. The stop asks
  each session to close through its socket, then signals only a process
  that still holds its id under the start identity it was noted with.
- **A second session in the same socket directory is found by its socket,**
  not by a pid file. The system names the process that listens on a socket
  (peer credentials), and that process is then held to its start identity
  like a recorded one. A session whose process the system does not name is
  asked to close and otherwise left, with its socket directory, and reported.
  The browser of a second session whose daemon was killed outright is not
  found.
- **The session's record is untrusted input.** A record that is a symbolic
  link, is not a regular file of the user, or is not what the start wrote
  is refused: nothing is stopped or removed, and the launcher and `status`
  say so. No path to delete is taken from it. The record and the policy are
  named by the attempt's log base, which the launcher passes to both
  commands. The socket directory is removed only when it holds a random
  token that the record also holds, is the user's alone (mode 0700) and
  sits directly in the temporary directory. A profile directory is removed
  only when a browser process the stop identified named it. What fails its
  proof stays and is reported, on the record under `kept`.
- **The start records each thing before or as it comes into being,** so a
  start that is killed at any point leaves nothing the stop cannot find.
- **The watchdog records the command that starts the session** in the pid
  file, with its start identity, from before it can act until it has ended.
  A launcher that settles an attempt whose watchdog was killed ends that
  command's process group first, by the rule it uses for the CLI's, and
  only then stops the session. The CLI was never executed, so the run
  "could not be started" and nothing is marked failed.
- **The run reaches its session through three environment variables,** which
  the launcher hands each runner as `run["browser_env"]`. No session name
  is on a command line. Every other `AGENT_BROWSER_*` variable of the
  lead's environment is kept out of a run, except the two that say how a
  browser starts on the machine.
- **The action policy's allow list is in `browser_session.py`,** the one
  place it is kept: what a visitor does with a page, and nothing that reads
  what a person could not see.
- **Codex can browse.** Its runner turns network access on for a run that
  may browse and makes the temporary directories read-only. The plan
  states that such a run's shell can reach the network directly. This
  replaces the milestone 1 decision that Codex has no browser.
- **The Claude runner allows each `agent-browser` command by its own rule,**
  in place of one rule for the CLI. An option after the command still gets
  through, so the action policy is the control and the rules a second layer.
- **A resumed run gets a new session, on a blank page,** and its resume
  message says so. A follow-up question gets one too.
- **A watchdog that was killed leaves its session running.** The launcher
  that settles the attempt stops it, and `status` shows what it found. The
  next launcher also stops any session on record that no live attempt owns.
- **Starting a session holds the launcher** until the session is up, about
  half a second for each run, because a run's process is recorded only once
  its session exists.
- **The instructions tell a browsing panellist** that its session is open
  already and is closed for it, to run one command per shell call, to
  snapshot before acting, to save each screenshot by a relative path in its
  scratch folder, and which commands the session takes. This is for studies
  that run through runners. A native-mode study has no launcher, so its
  instructions and run prompts are as before: each panellist starts a
  session named by its run id, saves screenshots by absolute path and closes
  the session when done.
- **Runners list what browsing leaves open** in `browse_gaps`: no limit on
  where the browser goes, an element list that shows more than the screen,
  and the browser's debugging port. The plan also gives the memory the
  sessions hold with the concurrency in force.

The usability study type, its protocol and its accounts:

- **A study is one type or the other.** A usability study refuses the keys
  only a review has (`concepts`, `labels`, `find_the_answer`, `artefact` and
  the like), `"materials": "text"`, `"browse": false`, every `capture` key
  but `desktop`, and native mode. A review refuses `target`, `tasks`,
  `accounts` and `sequential`. A key that is quietly ignored reads as a
  setting in force.
- **`target.base_url` is scheme, host and port alone,** and a task's `start`
  is a path on it. Task ids are unique ignoring case, because they name files.
- **`base_url` is read by a grammar of its own, not a URL parser.**
  `http://example.com\.localhost` parsed as a `.localhost` name and a
  browser goes to `example.com`. Accepted: `http` or `https`, a host, an
  optional port (1 to 65535) and at most one trailing `/`, in ASCII. The host
  is a plain name (letters, digits, hyphens, single dots, no dot at either
  end), four decimal numbers or a bracketed IPv6 address. A user name, a
  path, a backslash, `@`, `%` and a host whose last label is a number in
  another notation (`2130706433`, `0x7f.1`, `127.1`) are refused outright.
- **Local means the three exact forms and the two endings.** `127.0.0.2`,
  `0.0.0.0`, `[::ffff:127.0.0.1]`, `[0:0:0:0:0:0:0:1]` and a `.localhost` or
  `.test` name with a punycode label are valid hosts that are not local, so
  they need `allow_remote`.
- **Panellists get the address rebuilt from the validated parts,**
  lower-cased, never the text as written.
- **A task's `start` is one leading `/`, no `//`, no backslash, space or
  control character,** in ASCII with anything else percent-encoded.
- **A remote target is held to its rules by instruction only.** `read_only`
  is the lead's declaration that a task can be met by looking. Nothing stops
  a browser from submitting a form, and the plan says so.
- **Whether a command's file exists is checked at the scaffold, the plan and
  every start,** not when study.json is loaded, so an archived study still
  loads. The shape of every command is checked on load.
- **`accounts.signin`** is the setting that hands a panellist secrets:
  `"session"` (the default) or `"panellist"`.
- **The panellist's `account.json` holds identifiers, not credentials.**
  [Accounts and safety](#accounts-and-safety) says credentials are written
  there. It now has `signed_in`, `identifiers` and a `note` that says how
  the run starts, and `secrets` only with `"signin": "panellist"`. The whole
  account is in `<study>/accounts/<run id>.json`, lead only, mode 0600.
- **A saved state reaches a browser session as a private copy** in `logs/`,
  which the session deletes once loaded or when it cannot start. The
  original stays for a resume, and is deleted after teardown when a provision
  command made it.
- **`accounts.map` needs an account for every run,** and one saved state
  under `panel/` is refused.
- **A step is one action on the page.** Opening a task's start page,
  snapshots, screenshots, scrolling and waiting are not steps. The start
  page's screenshot is step 0.
- **Choosing from a drop-down list is one step, made with `select`,** with
  the choice read from the element list. [Protocol](#protocol) says the
  element list is for acting, not for finding things out. This is its one
  exception, and it does not break "decide from the screen": a person would
  open the list and see the same choices. In the end-to-end study a
  panellist that clicked a list open counted two steps for one choice, and
  the open list hid other controls in its screenshot. The instructions, the
  run prompt and the analyst's brief all state the rule.
- **What a panellist sees after scrolling is a further view of the step,**
  saved as `<task>-<step>b.png`, then `c`, with no entry of its own in the
  step log. A further view is archived with its step, and left out with a
  step marked `sensitive`.
- **A test account's display name is the test's, not a finding.** The
  instructions and each `account.json` say the account is lent, and the
  briefs tell the analysts and the writer never to report the name as a
  finding about the product.
- **`product` is required,** and `product_phrase` does not stand in for it:
  the briefs name the product by it.
- **A restarted task is a new attempt in the step log.** Every entry has
  `attempt`, 1 at first. The resume message gives a task that was under way
  its next number and names its screenshots `<task>-a<attempt>-<step>.png`,
  so the superseded steps and their screenshots stay.
- **The attempt number is the launcher's to issue.** It is on the run's
  entry (`task_attempts`) before the resume message is made. An entry that
  is not a step (no whole step number, a phase that is neither), or that
  carries a number the launcher did not issue, is left out before attempts
  are chosen, in the analysis and in the backstop. `check_runs.py` notes it.
- **The resume message says which account the run has.** A run that kept
  its account is "signed in to the same test account again". One that was
  provisioned again is told its account "is a new one", that nothing it did
  in the first is in it, and to read `account.json` again.
- **A task section opens its outcome with one of three fixed phrases:**
  completed, gave up, ran out of steps.
- **Teardown follows every provisioning once.** A failed run that is retried
  is torn down and provisioned again. A teardown that fails leaves the
  account in force, is reported in capitals, and is tried again by the next
  launcher command that settles runs.
- **No run carries on in an account that is owed a teardown.** A failed run
  whose teardown fails is not retried and stays failed. A later `run` (or
  `resume --extend` of a limited run) tears the account down first and only
  then provisions and starts. While the teardown still fails the run is not
  started and the command exits with 1.
- **A teardown is ordered so that a kill leaves it finishable.** The
  account's record gets `cleanup` (the files to remove and rewrite) before
  the command runs. The files are seen to after it, and one last write marks
  the account torn down and takes `cleanup` off. Until then the account is
  in force, so the whole teardown is done again: by the next launcher
  command, whatever state the run is in, and by `init_study.py --force`.
- **A provisioning that did not finish is cleared up first.** The record
  notes that a provision command started. When the next start finds no
  account for it, it runs `teardown` for the run id, then provisions.
- **A lead command's output is never printed or recorded.** Messages,
  `runs.json` and `status` carry the exit code and a fixed sentence. What
  the command wrote goes to `accounts/<run id>.<command>.output`, mode 0600,
  never archived, and the message names it. A provisioning payload that
  cannot be used goes there too and is never quoted.
- **One lead command at a time, on record with its process identity.**
  `accounts/command.running` names the command, the run and the
  provisioning before the process exists, then its pid and start identity.
  The process becomes the command only once that is written. The next
  launcher command, and `init_study.py --force`, first ends a command still
  running under that identity (SIGTERM, the grace, SIGKILL), waits for it,
  and treats it as unfinished. A group is signalled only while that process
  is there to prove whose it is. When the command has gone and its process
  group still holds a process that has not ended, such as a worker that
  ignored SIGTERM, the launcher kills nothing, keeps the record, starts no
  lead command and exits with 1, naming the pids and how to check them. Once
  the group is empty the next command clears the record and carries on.
- **When provisioning or `reset` fails the run "could not be started",**
  nothing is marked failed, and no further run starts in that command.
- **`init_study.py --force` tears down every account still in force,** and
  stops before replacing anything when one fails.
- **`reset` runs before an attempt whenever another run used the product
  since:** before every launch, retry and restart but the study's first, and
  before a resume unless the same run ran last. `reset` without
  `"sequential": true` is refused.
- **A run's time limit defaults to 30 seconds for each step its tasks permit,
  plus 5 minutes,** when `limits.run.minutes` is not set.
- **A follow-up to a usability run gets no browser session.** Its account is
  gone, so it answers from its persona file, step log and screenshots, in a
  frame of its own.
- **Scripts that have nothing to do refuse in one line:** `capture.py` and
  `extract_answers.py`. `scores.csv` names its unit column `task`, and
  `rankings.csv` is the header alone. A usability study has no `key.md`.
- **The fourth default factor's key is `clarity`,** because `next_step`
  means something else in a review.

Secret scanning and the archive of a usability study:

- **A scan knows the secrets by fingerprint.** Teardown takes them off every
  record, and follow-ups and the synthesis are written after it.
  `accounts/fingerprints.json`, lead only and never archived, holds a salted
  hash of each secret. `accounts.py` adds to it whenever it writes an account
  record, and every scan adds what is still written out.
- **A scan fingerprints every run of characters as long as a known secret,**
  so it finds a value inside a longer word, and in a JSON string as it
  decodes. It does not find a value written another way (split across lines,
  in another case, encoded or masked), a secret shorter than 4 characters, or
  one of 4 to 7 characters with a letter or digit against it.
- **The hash is a fast one,** so a weak password can be guessed from the
  file. Teardown is what makes the password worthless.
- **An account torn down before the record heard of it cannot be scanned
  for.** `check_runs.py` and `archive.py` name its run and carry on.
- **A file that could not be scanned is never "nothing found".**
  `check_runs.py` blocks on a persona file, step log or analysis file that
  cannot be read or is a symbolic link, and `archive.py` refuses. Each is
  named with the reason.
- **No message repeats a panellist's own text unchecked.** One function,
  `panel_lib.shown()`, quotes a task id or label the study does not have, a
  file or screenshot name and a page address. A value that holds a known
  secret, is longer than 40 characters (120 for a page) or has characters
  outside letters, digits, spaces and `. _ - / : # ~` is described ("a
  value that is not a task id, 14 characters"). It covers the launcher's
  lines, `analysis/checks.md`, `runs.csv`, `tasks.csv` and `steps.csv`.
- **Evidence is never read through a symbolic link.** The evidence root, a
  run's folder and each file are opened without following one, by the
  backstop, the scan, `check_runs.py`, `extract_scores.py` and `archive.py`.
  A refused folder is named: `check_runs.py` blocks and the archive is
  refused. A usability archive also refuses a symbolic link among the kept
  files.
- **In `check_runs.py` only a secret value, or a file that could not be
  scanned, blocks:** in a run's persona file
  or step log, or in a markdown file of `analysis/`. Notes cover stray files
  in an evidence folder, the form of a step log, a named screenshot that is
  not there, a task written up with no step logged, and another account's
  identifier in a run's files.
- **`archive.py` scans every file it would hold,** not step logs alone:
  persona files, prompts, analysis, `runs.json`, `followups.json` and its own
  copy of `study.json`.
- **No archive while a test account is in force.** A run that is not done,
  limited or failed keeps its account, so it has to finish first.
- **A screenshot is a PNG file whose name gives its step, or that a result
  entry names.** Nothing else in an evidence folder is copied, a link least
  of all, and a line counts what was passed over.
- **Screenshots stay PNG under their own names,** at half size and 256
  colours, so a citation is found as it was written. Without ImageMagick
  they are copied whole, and a line says so.
- **A third kind of screenshot is left out:** a file that is not a PNG
  image. The note in place of a screenshot is `<its name>.left-out.txt`.
- **The archived `study.json` has each `accounts.map` secret replaced with
  "(removed from the archive)",** so it still loads with
  `"signin": "panellist"`. Without a map it is copied byte for byte.

The step limit's backstop, success checks, analysis and the jobs:

- **The backstop's reason is on record before the run is asked to stop.**
  The launcher writes the decision to the attempt in `runs.json` (`stop`:
  task, step, limit), then asks the attempt's watchdog, which stops the CLI
  as at a time limit. The watchdog knows nothing of steps: its end record
  says "stop", and whichever launcher settles the attempt reads the decision.
  The run is `limited` with `"limited_by": "steps"`.
- **The backstop reads only what the current attempt added** to the step
  log. A resumed run is not stopped again for the step that stopped it.
- **The backstop counts intents, whatever attempt they carry.** An intent
  numbered above the limit stops the run, and so does one intent more for a
  task than the limit allows. An entry under a number of the panellist's own
  is one more step, so renumbering buys none.
- **A time limit that comes first stands as the reason.**
- **A success check's exit code is its verdict: 0 completed, 1 not
  completed.** Any other code, a check that cannot be run and one that
  times out are "failed to run": no verdict, reported in capitals, and never
  counted as not completed.
- **Checks run when a run is done, limited or failed, before teardown,** and
  not for a failed run about to be retried. A run that is continued has its
  check records dropped, so they are made again when it next finishes.
- **A run continued with a new account keeps the check of each task it had
  written up,** marked `kept`, through every later attempt. It does not
  attempt that task again, and the new account has none of its data, so a
  check made then would read "not completed". Only the tasks it attempts
  afterwards are checked on the new account.
- **`launch.py check [--runs <ids>]` runs the checks again by hand,** for a
  lead who has mended a check.
- **`check` keeps a verdict whose account is gone.** In the end-to-end study
  a check run again after teardown turned "completed" into "failed to run".
  A verdict of completed or not completed, made while the account was
  there, is now kept, and a line says so for each task. `--force` runs the
  check all the same and says that the earlier verdict was replaced. A task
  with no verdict, or with "failed to run", is tried either way. An account
  let go in a study with no `accounts.teardown` is still in the product, so
  its checks run again.
- **`launch.py release --runs <ids>` lets go of the account of a run the
  lead will not continue.** A partial, blocked or pending run otherwise keeps
  its account, and the archive refuses the study. Its checks are run first,
  as for a finished run, then its account is torn down and the run is marked
  `released`. `run` and `resume` leave a released run alone unless it is
  named with `--released`, which gives it a new account.
- **A teardown is tried once for each run in a command.** Settling a run and
  then catching up on final states tried a failed teardown twice.
- **A `result` entry also has `url`,** the address the action left the
  browser on, from `agent-browser get url`. Without it no script can tell
  one screen from another. It costs one more command for each step.
- **A stuck point is a task and a page address without its query.** A run
  hits it in one of two ways. It did not complete the task (gave up, ran out
  of steps, stopped at the step limit), and this is the screen that held
  it: the one most of its last 4 steps left it on, and the later of two
  that tie. Or it took 4 or more steps in a row there that left the address
  unchanged. The report prints the definition and says that the analysts
  refine it.
- **The screen that held a run is not the screen it ended on.** The first
  definition was "where the task ended". In the end-to-end study two runs
  left the form that blocked them for the help page and gave up there, so
  the help page ranked first. The evidence of each run now gives the screen
  it ended on, the screen its last step was taken on, and the steps that
  left it on the stuck point's screen.
- **Completion, steps and stuck points count every run; the score tables
  count complete runs only.** A run stopped at a step limit is incomplete,
  and leaving it out would make its task look easier than it was. Completion
  counts the attempts of a task that ended: its section is written, or a
  limit stopped the run in it.
- **Checked completion is a share of the attempts a check gave a verdict
  on.** Checks that failed to run and attempts not checked each have a
  column of their own.
- **A mismatch is one of two things:** a claim of completed that the check
  denies, or a claim of gave up or ran out of steps that the check passes.
  An Outcome line that cannot be read is listed apart and is no claim.
- **`extract_scores.py` writes `analysis/tasks.csv` and `steps.csv`,** one
  row for each run and task and one for each step, so `analyze.py` still
  reads only `analysis/*.csv`. The sentences a panellist wrote stay in the
  step log.
- **The usability briefs are assets of their own:**
  `usability-qual-brief.md` and `usability-synthesis-brief.md`, each with a
  `-followups` fragment. The review briefs are unchanged.
- **`plan` and `run` stop when the `agent-browser` CLI is not on PATH** and
  a run may browse, in a review study too.
- **An attempt's stream files and the launcher's lock are opened like every
  other file of an attempt.** `logs/<run id>.<attempt>.in`, `.out` and `.err`
  are made anew and handed to the process by descriptor, and read back
  without following a link or waiting. `.launch.lock` is opened the same
  way: a link or a FIFO at its name is no lock, and a command that needs the
  study refuses in a sentence. The lock itself is unchanged: `flock` on the
  one file every launcher opens.

### Follow-up work after milestone 5

Decided on 13 October 2026, while fixing the 14 problems that the milestone 5
fix pass had left and while starting one panel from each kind of shell
([A lead in a sandboxed shell](#a-lead-in-a-sandboxed-shell)). They reach
studies of both types, not only usability studies.

The archive:

- **One walk and one copy serve both study types.** `archive.py` finds the
  kept files by one walk that opens each folder by descriptor, then copies
  the files that walk listed and no others, each opened without following a
  link at its name or at a folder above it. A review study has a plan step
  too. Before, a review-study archive copied through symbolic links in kept
  folders. A file that can no longer be read when it is copied now ends the
  archive in the same refusal as one the walk found.
- **A symbolic link, a FIFO, a socket or a device at or under a kept name
  refuses the archive,** in a study of either type. A link could bring in a
  file from outside the study. The others are no file to copy, and opening
  one may never return.
- **The round is built in a scratch folder beside the destination,**
  `.<round>.archive-<random>`, and everything that reads the study happens
  there. A failure while the study is read therefore leaves the destination
  as it was.
- **Publishing is one rename to a new destination, and file by file into an
  earlier archive,** each file moved into place whole with `os.replace`. An
  interrupted publish leaves whole files, some of this round and the rest as
  the earlier archive had them, and archiving again completes it.
- **No empty folder is archived.** A folder travels only as part of the path
  of a kept file, and folders left empty at the destination are pruned. A
  folder that held only ignored names used to be archived empty, and an
  empty folder named with a secret had to be refused.
- **An empty folder that cannot be removed is named on stderr and left.**
  The round is archived all the same, the exit code is 0 and no permission
  is changed to get at it.
- **Archived files get default permissions and keep their modification
  times.** Each is written to a file made anew, not copied with its mode.
- **A stray evidence file keeps its run id in the message,** also when its
  own name is not shown.
- **The closing line counts the markdown files that carry the synthetic
  notice,** not the ones this archive gave it to, so archiving twice prints
  the same line.

The launcher and accounts:

- **A run that is started afresh has its earlier evidence set aside,** in
  `logs/<run id>.<attempt>.evidence/`. A new session logs every task as
  attempt 1 and names its screenshots as the earlier one did, so the two
  would mix. Nothing is deleted, the folder is put back when the start never
  ran as the CLI, and the run's `task_attempts` go with it.
- **The step backstop keeps a count of its own in `runs.json`,** which never
  goes down when a step log is cut or rewritten. A panellist could otherwise
  switch the backstop off by truncating its own log.
- **A step log that cannot be read as the run's own stops the run,** as
  `limited`. A log refused as a link used to stop nothing. A log that does
  not exist yet stops nothing.
- **The backstop is stated as a backstop.** It counts the steps a log shows
  while a launcher is running. A run that logs nothing is bounded by its
  time limit, and the documents say so.
- **A harness message that holds a known secret is withheld** before it is
  printed or stored. The reason names the attempt's `.err` and `.out` files
  in `logs/`, which have it and are the lead's alone.
- **`stop` stops live runs first,** also while a process left by a lead
  command holds up recovery. It then starts no command of the study, says
  what holds the study up and exits with 1. Before, it exited without
  stopping anything.
- **"No process list can be had" is never read as "empty".** With no `/proc`
  and no `ps`, the launcher says that it could not check a process group,
  and keeps the record of a command it cannot prove gone.

Reading what a panellist can write:

- **Every persona file is opened one way** (`panel_lib.persona_bytes`):
  without following a link at the file or at any folder above it, regular
  files only, and never waiting, as an open of a FIFO would. Before, only
  the secret scan refused a persona file that was a link.
- **A persona file that cannot be read as the run's own is no persona
  file.** Its run is not done, it gives nothing to the scores or the
  answers, and `check_runs.py` blocks it and names the reason.
- **`step_notes` cells are escaped,** so a note that holds "; " stays one
  note. An existing `runs.csv` reads as before.
- **Follow-up `.before` copies go through the safe-open helpers** that every
  other file of an attempt uses. They were read by name.

A lead in a sandboxed shell:

- **The shell is tested before a runner is called ready.** `plan`, `run`,
  `pilot`, `resume` and follow-ups test that the study directory can be
  written, that each CLI can write where it keeps its sessions, and for
  `codex` that it can build its sandbox. In the first round of runs `plan`
  said "ready" inside every sandbox. Codex runs there then could not start,
  or called the model for up to 160,000 input tokens a run and wrote
  nothing.
- **The runner interface gains `shell_check()`,** asked after a `check()`
  that passed. It makes no model call, and the `codex` probe builds a
  sandbox and runs nothing in it. Only what is known to stop a run refuses:
  a test that cannot be made passes.
- **A runner the shell cannot run is shown as `CANNOT BE USED`,** with what
  it cannot do there and the two ways out, and `plan` exits with 1. Other
  runners are judged on their own.
- **Network access is not tested.** A proxy or a custom endpoint makes any
  general test unreliable. A run's own output shows it.
- **`parse_result()` gains `cannot_run`:** a Codex run whose every shell
  command failed to build its sandbox, and a Claude Code run that cannot
  reach its provider. The run is not retried and the runner is closed for
  the command, because the next run would spend the same time and tokens to
  end the same way.
- **`parse_result()` gains `session_saved`.** A run whose session was not
  saved says so once, shows it in `status`, and is refused for `resume` and
  for a follow-up. A Claude Code run completes without a saved session
  where its CLI cannot write its own folder.
- **`check_runs.py`, `extract_scores.py`, `extract_answers.py` and
  `analyze.py` end in a sentence,** not a traceback, when the study
  directory cannot be written.
- **A Codex lead asks for `plan` and `run` outside its sandbox.** Inside it,
  `plan` answers for the sandbox and never says `ready`. A Codex CLI cannot
  build its own sandbox inside another Codex sandbox, so nothing tried
  inside `workspace-write` lets a Codex panellist run. A study with only
  Claude Code panellists can stay inside, with network on and the Claude
  configuration directory writable.

Runs that a shell cannot see (another process namespace, as inside a
sandbox):

- **Whether a launcher is running is what the `flock` on `.launch.lock`
  says,** not whether its process can be seen. Every shell sees a lock.
  `status`, `plan` and `stop` ask with a shared lock that they do not wait
  for and let go at once, and a launcher that finds only such a lock in its
  way asks again, so a question never turns a launcher away.
- **The lock file persists.** A launcher that ends empties its record and
  leaves the file, and no command removes it. A killed launcher still leaves
  its record, and the next launcher clears it. A shell that cannot write the
  study, as in a read-only sandbox, can lock a file and cannot make one, so
  the file has to be there while the study is at rest.
- **`init_study.py` makes the lock file at every scaffold,** of a
  native-mode study too, so a study has one before it has had a launcher.
  When it cannot, it says so in one sentence that names the file and the
  system's reason, and exits with 1. A link, a FIFO or a folder at the name
  is refused the same way and left there.
- **Each attempt's watchdog holds a lock of its own for life,**
  `logs/<run id>.<attempt>.lock`. The system lets go of it when the watchdog
  ends, however it ends, so the lock says whether the attempt is alive when
  no launcher is. The watchdog closes the descriptor before a child becomes
  the CLI or a hook, so nothing a panellist runs holds the lock or can let
  go of it.
- **The launcher's lock record and each watchdog's pid file name the
  process namespace,** where the system names one (Linux does, macOS does
  not). A launcher or a run counts as visible only when the process id, the
  start identity and the namespace all agree. A process id means its process
  only within a namespace, and a start identity can be the same on both
  sides of a sandbox, so the two alone could take a stranger's process for
  the launcher.
- **A recorded id is never looked up or signalled across namespaces.** That
  covers the daemon and the browser of a run's browser session, which is
  closed through its socket.
- **A held lock whose holder cannot be seen is a live run out of sight.**
  `status` reports the recorded states with one line saying so, and every
  command that takes the study refuses before it changes anything. Going by
  process ids, a launcher in a sandbox would have taken live runs for gone
  and settled or restarted them.
- **A free lock means the watchdog has ended,** in whatever namespace it
  ran, and any launcher settles the run as always. That lets any shell
  settle the runs that died with a sandbox, with nothing edited by hand.
- **The namespace on record never decides whether a run is alive.** An
  earlier version did decide by it: a record from another namespace was a
  run out of sight, and every command refused. A launcher killed inside a
  sandbox then left a dead end. Its runs had died with the sandbox, their
  records named a namespace no shell would ever be in again, and every shell
  refused the study. The locks replaced that rule, because the system frees
  a lock when its holder ends, whatever shell asks. The namespace now only
  says which ids may be looked up and signalled.
- **One case is left: a watchdog killed on its own in another namespace.**
  The ids on record name nothing in this shell, so the launcher looks none
  up and signals nothing, settles the run as one whose watchdog was killed,
  and notes that its CLI could not be checked.
- **A study that cannot be written is archived under a shared lock on
  `.launch.lock`,** held from before `archive.py` looks at the study until
  the round is copied. A shell that only reads can take a shared lock, and
  it turns every launcher away, so no run or follow-up starts under the
  copy. A launcher that meets it waits 5 seconds, says that something is
  reading the study and exits with 1. Under that lock the archive asks each
  watchdog's lock and refuses a study with a run it cannot see. Before, such
  a study was archived with no lock at all.
- **A study from before the lock file was kept is the one unprotected
  case.** It has no file to share until a launcher or a new scaffold makes
  one, and a read-only shell cannot. `archive.py` refuses it with a run on
  record as running, and copies any other with nothing to keep a launcher
  out.
- **A lead's account command holds a lock for as long as it or anything it
  started lives,** `accounts/command.lock`, and its record names the
  namespace it was started in. In the same namespace recovery goes by the
  process ids as before, because a process that closed the descriptor it was
  given (one started through `sudo` or by Python's `subprocess`) holds no
  lock. A lock still held when the command's group is empty holds the study:
  a process left the group and kept the lock.
- **Recovery of a command recorded in another namespace waits for the
  lead.** It never clears the record and signals nothing. It keeps
  `accounts/command.running`, starts no command, exits with 1 and says to
  run the launcher from the shell that started the command, or to delete the
  record and the lock file if that shell was a sandbox that has ended. A
  run's free lock proves that its watchdog ended, because the watchdog never
  gives the lock up. A command's free lock proves nothing, because what the
  command started may have closed the descriptor and still be running where
  this shell cannot look. This is the one place where a study waits for the
  lead after a sandbox has ended.
- **Without a lock the old rule stands.** An attempt from before watchdogs
  held a lock, and one on a file system without `flock`, is looked for by
  the process ids on record.

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
0.162.1 (ChatGPT plan login), and for Pi on 13 October 2026 against Pi 1.1.0
(a ChatGPT subscription login, its only working provider), by running each CLI
in fixture directories with planted marker terms. **Verified** means seen in a
real run. **Inferred** means read from help text, bundled docs, the binary's
strings or old session files. The exact flags and output formats are in the
docstrings of `scripts/runners/claude.py`, `scripts/runners/codex.py` and
`scripts/runners/pi.py`.

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
  - **Result (verified):** `-nc -ns -ne -np --no-themes --no-mcp
    --no-approve --system-prompt "" --append-system-prompt ""`. With markers
    planted in the working directory's and its parents' instruction files,
    project skills, a project extension and the project's `.pi/` folder, and
    with the user's global rules in place, none reached the model and the
    login kept working.
  - `-nc` removes every `AGENTS.md` and `CLAUDE.md`, the global one and
    those of every parent directory. `--no-approve` is needed because a
    user setting can trust project files in headless mode. The two empty
    system prompt flags keep out a global `SYSTEM.md` or `APPEND_SYSTEM.md`,
    which no other flag does.
  - The config directory variable is not used: the login lives in that
    directory.
  - No switch was found for the working directory path, the path of the Pi
    installation or Pi's own system prompt. All reach the model.
- Image input per model, and how the plan step can detect it.
  - **Result (verified):** a run opens an image by path with the `read`
    tool. A 2880x1800 sheet was resized by Pi to 2000x1250 and read down to
    its small print.
  - `pi --offline -ne --list-models` prints an `images` column for every
    model, without a model call. The plan step reads the model's exact row.
    A custom model in `models.json` is listed as text only unless it
    declares image input.
  - **Result (inferred):** a text-only model is not an error. Pi swaps each
    image for a line of placeholder text and carries on, so the listing is
    what refuses it.
- Tool restriction. Not a question at the start.
  - **Result (verified):** Pi has no sandbox, no permission system and no
    approval prompts. With only the file tools enabled, a run read
    `/etc/hostname` and wrote outside its working directory. Confinement
    takes an extension that vetoes tool calls, loaded with `-e`.
  - With the guard, every read, write, listing and search outside the
    working directory was refused, through `..`, an absolute path, `~`, a
    `file://` address and symbolic links, and so were every shell command
    but a single `agent-browser` command. Nothing waited for approval.
  - Pi refuses to start when an extension given with `-e` is missing, has a
    syntax error or throws while loading.
- Output, session id and resume.
  - **Result (verified):** text mode prints the final reply alone, and exits
    with code 1 after a provider error. JSON mode exits 0 for the same
    error, and repeats each image read six times.
  - The runner chooses the id with `--session-id <uuid>`. Resume is
    `--session <id>`, which fails when the session is gone.
    `--session-id` never fails: it creates an empty session of the same id.
  - Resume keeps its memory, also after SIGTERM, and inherits the model and
    thinking level but not the tools. From another directory it asks
    whether to fork the session and stops.
- Models and thinking levels.
  - **Result (verified):** an inexact model name is matched loosely with no
    warning, an unknown id under a known provider is sent to the API, and an
    invalid thinking level only warns and runs at the user's default. The
    runner validates all three.
- Usage and budget.
  - **Result (verified):** each request's tokens and a list-price cost are
    in the session file, also under a subscription login. There is no
    duration for a process and no budget cap of any kind.
- What is configured for the acceptance test.
  - **Result (verified):** nothing on an OpenAI-compatible endpoint. The
    only working provider was the ChatGPT subscription login. The endpoint
    path is untested.

All runners:

- The error text and exit code for a usage or rate limit.
  - **Result (inferred, still open):** no limit could be triggered on either
    harness. Claude Code is expected to end with an error result whose text
    starts "You've hit your", status 429 and exit code 1, with the reset
    time in its `rate_limit_event`. Codex is expected to end with
    `turn.failed` and exit code 1, its message naming a usage limit, with
    the reset time in the session file. Pi is expected to end with a
    provider error whose message names the limit, with at most "Try again
    in ~N min" as the reset time.
- Where each harness stores a session, and whether it can be deleted by id.
  - **Result (verified):** Claude Code keeps one transcript per session
    under its projects directory, in a folder named after the working
    directory. It has no command that deletes one session, and removing the
    file makes the id unknown to resume. Codex keeps a session file under
    `$CODEX_HOME/sessions/` and database rows, and
    `codex delete --force <id>` removes both. Pi keeps one file per session
    under its sessions folder, in a folder named after the working
    directory. It has no command that deletes one, its docs say to remove
    the file, and removing it makes the id unknown to resume.
- A safe default concurrency on a subscription.
  - **Result (still open):** no cap was found in any CLI. Four concurrent
    Claude Code runs, three concurrent Codex runs and three concurrent Pi
    runs raised no error. The defaults stay at 6 and 4, and Pi's is 3.
- Whether `agent-browser` runs inside each harness's sandbox.
  - **Result (verified):** yes in Claude Code, through an allow rule for
    `agent-browser` commands. No in Codex, as above. Yes in Pi, which has no
    sandbox: the browser session persists between shell calls, and the
    guard extension is what limits the shell to `agent-browser`.
  - Since milestone 5 a Codex run drives a session that is started outside
    its sandbox: "Codex and the browser", under Usability below.

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

Still open after milestone 4:

- Everything on an OpenAI-compatible endpoint through Pi: tool calling,
  whether the endpoint reports usage, image input and the text of its
  errors.
- What Pi does with a text-only model and an image: read from its source,
  not seen.
- Pi concurrency above three runs, and two processes refreshing one login
  at once.
- Compaction in a long Pi run, and its usage.

Usability:

- Whether panellists follow the "decide from the screen" rule, checked by
  comparing step logs with screenshots in a pilot.
  - **Result (verified, small sample):** yes. The end-to-end study compared
    step logs with screenshots step by step. No step on either harness
    acted on an element that no screenshot showed, in 25 and 24 steps
    examined.
  - One small-model run chose from a closed list using the element list in
    4 of 25 steps. The list rule now makes that the stated protocol
    (Deviations decided during milestone 5).
  - Earlier, in discovery: a Codex run at low effort answered that a name
    was "not shown in the snapshot" when its screenshot showed it. The list
    of elements to act on leaves out plain text, and the run had not opened
    the image. The instructions now say that the screenshot is what is
    visible, and ask for the `result` entry after looking at it.
  - Codex's event stream shows no image views, so on that runner whether a
    run opened a screenshot cannot be checked from the logs. Claude Code's
    stream shows every read.
- How often a panellist claims success that the check denies.
  - **Result (verified, small sample):** 0 of 12 task attempts across the
    studies run.
  - One mismatch of the opposite kind: a panellist reported giving up on a
    task that the check passed.
- Both answers are small samples from one test app.
- Whether `agent-browser` can save a signed-in browser state and load it into
  a panellist's session, which the signed-in start depends on.
  - **Result (verified):** yes. `state save <file>` writes cookies and local
    storage as JSON, and `--state <file>` at launch loads it into another
    session. Six sessions on three accounts each showed their own account.
  - The file holds the session cookie in plain text. The state is applied
    when it is loaded: the file was deleted straight after and the session
    stayed signed in. So the launcher loads the state and deletes the file,
    and a panellist never has a file to read. `browser_session.py start`
    takes `--state` and `--delete-state`.
  - `--state` cannot be combined with `--allowed-domains`.
  - The cookie is still in the browser. Without a policy, `cookies get` and
    `state save` print it. The action policy below refuses both.
- Codex and the browser. Not a question at the start.
  - **Result (verified):** a Codex run can drive a browser that was started
    outside its sandbox. Each shell call is a process namespace of its own,
    so a browser started inside dies when the call returns, with `setsid`
    and `nohup` too.
  - The sandbox refuses to connect to a Unix socket unless
    `sandbox_workspace_write.network_access=true`. Network access is all or
    nothing in the stable settings, so the run's shell can then reach the
    internet and the target directly.
  - A command that cannot reach its session takes it for stale and deletes
    its socket files, which cuts the session off for good. The launcher
    therefore records the daemon's process id and stops it by signal.
  - With `exclude_slash_tmp=true` and `exclude_tmpdir_env_var=true` the
    temporary directories are read-only in the sandbox, so a run cannot
    start a session of its own in the socket directory.
  - **Result (inferred):** an experimental proxy feature can narrow the
    network to one host, but it puts proxy variables into the shell, which
    restart the session blank. Not usable yet.
- What keeps a panellist from reading what a person could not see. Not a
  question at the start.
  - **Result (verified):** `agent-browser` enforces an action policy inside
    the session, a JSON allow list named by `AGENT_BROWSER_ACTION_POLICY`.
    With it, `eval`, `cookies`, `storage`, `state`, page source, reading an
    element by selector, network requests, the console and every option that
    relaunches the browser are refused on every harness. The file is read
    again for every command, so the launcher sets the session up under a
    policy that allows everything and then swaps the strict one in.
  - A command that reaches a session with other `AGENT_BROWSER_*` settings
    than it was started with restarts it, blank and signed out. The launcher
    and the run must use the same environment. A run that drops the policy
    loses its session and gains nothing.
  - Not covered: where the browser goes, where a screenshot is saved,
    commands that never reach a session (`profiles`, `session list`,
    `connect`), and the browser's debugging port, through which a
    determined run could read a cookie.
  - The element list is the accessibility tree. It holds screen-reader-only
    text and off-screen elements, and leaves out `aria-hidden` content that
    is visible. "Use it to act, not to discover" stays an instruction.
- Session behaviour that shaped the launcher (all verified).
  - Relative screenshot paths resolve against the session's working
    directory, not the run's, and a screenshot with no path goes to the
    user's home directory.
  - `click` returns before the navigation it starts has finished, so a
    screenshot chained to it fails or shows the old page.
  - The default viewport is 1280 x 577.
  - SIGTERM to a session's daemon is a clean close. SIGKILL leaves its
    browser running, with a profile directory in the temporary directory.
  - A session holds about 330 MiB. Commands take 2 to 50 ms and a launch
    under a second, so the harness sets the pace: about 6 s a step on a
    small Claude model and 7 to 10 s on Codex at low effort.
  - A cookie is tied to its host: a state saved on `127.0.0.1` does not
    sign in `localhost`.
- What the protocol had to say that the draft did not (all verified).
  - A Claude Code panellist cannot append to its step log from the shell:
    redirection is refused even with `echo` allowed, and the run gave up
    after two refusals. Told to keep the log with its file tools, it did.
  - A panellist told it was one person stopped at step 1 when the page
    greeted another. The instructions now say the account is lent.
  - "Step" needs a definition. One run counted each snapshot as an action
    and used 3 of its 10 steps looking.
- What a typed secret leaves behind. Not a question at the start.
  - **Result (verified):** a password field is masked in the element list
    and in a screenshot, though its length shows. A "show password" control,
    or any field that is not a password field, puts the value in both. No
    screenshot option masks a field.
  - The policy refuses reading a field's value back. The value is still in
    the harness's transcript, as part of the command that typed it.
  - `agent-browser auth login` fills a sign-in form from a vault, so a
    panellist never holds the password. It worked on the CLI alone and was
    not tried inside a harness. It is not used: the panellist would not
    experience typing, and the vault sits beside the user's own profiles.
- The default time limit.
  - **Result (inferred):** 30 seconds for each step plus 5 minutes for the
    run leaves room above the measured 6 to 10 s a step. Larger models and
    higher effort were not measured.

Still open after milestone 5:

- Whether panellists look at their screenshots, and how often a claim and a
  check disagree, on a panel of real size.
- Timing on larger models and higher effort, and how context grows over a
  task of 25 screenshots.
- A limit on where the browser goes. `--allowed-domains` cannot be combined
  with a saved state, and it blocks the fonts, scripts and images a product
  loads from other hosts.
- A Codex network rule narrower than all or nothing.
- The browser's debugging port: no `agent-browser` option was found that
  starts the browser without one.
- A sign-in kept in IndexedDB or session storage. `state save` does not
  carry IndexedDB. Not tested.
- `--headed` and `--cdp` under the action policy: inferred to be refused,
  not run. And `install`, `upgrade`, `plugin add`, `dashboard start`, `mcp`
  and `chat`: inferred never to reach a session, so the policy does not
  cover them. Not run.
- Whether the vault is acceptable for a study where signing in is the task.

### System prompt override (experiment and decision)

Tested on 13 October 2026 with claude 2.1.296 (Claude Max login) and codex-cli
0.162.1 (ChatGPT login, default model `gpt-6.1-sol`). **Outcome:** both CLIs
can replace their built-in prompt, ten panellist runs showed no difference in
the research output, and both runners keep the default prompt (Decision,
below).

**Question.** The Claude Code and Codex runners strip user and project
instruction files, memory, skills, hooks and MCP servers, but leave each
harness's default system prompt in place, and that prompt addresses a coding
agent. The user asked whether replacing it would let a panellist take on its
persona more reliably.

Findings come from each harness's session record (the `prompt_snapshot` record
of a Claude Code transcript, `session_meta.base_instructions` and the recorded
messages of a Codex rollout file), not from what a model said about its own
instructions. What was read from help text, or not tested, is marked.

**What Claude Code supports** (probes used the runner's own arguments and
`--model haiku`):

- **What is replaced.** `--system-prompt <text>` makes the prompt exactly the
  text passed, as one block. With the runner's isolation flags, the default it
  replaces is 11 blocks of about 7,100 characters (about 2,200 tokens):
  guidance for a general agent on code style, confirming hard-to-reverse
  actions, context management and, in one block of 2,800 characters, finishing
  the task within the turn.
- **`--system-prompt-file <path>`** works the same way. It is not listed in
  `claude --help`, so `--system-prompt <text>` is the documented form.
- **What still reaches the model:**
  - a prefix line, sent ahead of the replacement text:
    `You are a Claude agent, built on Anthropic's Claude Agent SDK.`
  - the tool definitions (about 10,200 characters for the five file tools)
  - the working directory path, platform, shell, OS version and whether the
    directory is a git repository
  - the model's name, id and knowledge cutoff, and today's date
  - the account email, in a system reminder in the user turn
  - a token budget line, a rule about untrusted downloaded files and a line
    about making independent tool calls in parallel

  Nothing but the prompt body disappeared or moved.
- **Tools with a replaced prompt.** Read, Write, Edit, Glob, Grep and reading
  a PNG all worked. With Bash added, an allowed command ran and a command with
  no allow rule was denied, as with the default prompt.
- **Resume.** `--system-prompt-snapshot` defaults to `on`: the prompt is
  rendered on the conversation's first request, recorded in the transcript,
  and sent again on every later request and every resume.
  - A resume without the flag kept the replaced prompt.
  - A resume that passed different text kept the recorded prompt. The cache
    read on that request was 6,909 tokens, against 3,188 when the prompt
    changed.
  - With `--system-prompt-snapshot off`, a resume used the text passed at that
    launch.
  - The help text says the record holds "until the conversation is compacted".
    What a compaction renders was not tested.
- **An empty string fails.** `--system-prompt ""` gave three thinking-only
  responses, then `terminal_reason: malformed_tool_use_exhausted` and exit
  code 1 (one probe).
- `--exclude-dynamic-system-prompt-sections` is documented as ignored with
  `--system-prompt`, and was not tested.

**What Codex supports** (probes used the runner's own arguments at low
effort):

None of these keys is in `codex exec --help`, and no docs ship with the
package. The names come from the binary's config schema and the behaviour from
experiment. An unknown `-c` key is ignored with no error. `--strict-config` is
the CLI's switch for unknown config fields, and whether it also checks `-c`
overrides was not tested.

| Key, passed with `-c` | Effect |
| --- | --- |
| `model_instructions_file=<absolute path>` | The base instructions become exactly the file's content. The default is 21,769 characters, starting "You are Codex, an agent based on GPT-6" |
| `instructions=<text>` | The same effect, from text |
| `developer_instructions=<text>` | Adds one developer message ahead of the built-in developer blocks. Replaces nothing |
| `include_environment_context=false` | Removes the `<environment_context>` user message: working directory, shell, date, timezone and filesystem permissions, 1,515 characters |
| `include_permissions_instructions=false`, `include_collaboration_mode_instructions=false`, `include_apps_instructions=false` | Set together in one probe, with the key above. The `<permissions instructions>` (591 characters) and `<collaboration_mode>` (920) developer blocks were gone. The probe did not separate the three keys |

- **What still reaches the model** after the base instructions are replaced:
  - the developer blocks `<permissions instructions>`, `<collaboration_mode>`,
    `<multi_agent_role>` (2,400 characters) and `<multi_agent_mode>` (271)
  - the user's global `~/.codex/AGENTS.md` (5,260 characters), the runner's
    known isolation gap
  - `<environment_context>`, unless it is switched off
  - the same tool set: `exec` (which carries `exec_command`, `apply_patch`,
    `view_image` and others), `wait`, `request_user_input`, the sub-agent
    tools and `clock.sleep`

  No account email or name reached the model in any variant.
- **Tools with a replaced prompt.** Reading a file, writing one in the working
  directory, changing it and opening a PNG by path all worked.
- **Resume.** A thread keeps its base instructions: a resume with the runner's
  plain resume arguments still followed the replacement, and its request was
  10,787 tokens, where a default base would add about 4,300. Instructions
  passed on a resume replace the thread's. The `include_*` settings are per
  process: their blocks came back on a resume that omitted them.

**Input tokens for one trivial turn:**

| CLI | Variant | Input tokens |
| --- | --- | --- |
| Claude Code, `haiku` | default prompt | 6,434 |
| Claude Code, `haiku` | replaced with the 79-word prompt below | 4,345 |
| Claude Code, `haiku` | empty string (first request of the failed run) | 4,230 |
| Codex, low effort | default | 15,233 |
| Codex, low effort | base replaced by `instructions`, one extra developer line | 11,046 |
| Codex, low effort | base replaced by file, no environment context | 10,554 |
| Codex, low effort | base replaced, permissions, collaboration and environment blocks off, prompt `hello` | 9,871 |

The default body costs about 2,200 tokens on Claude Code and about 4,300
tokens per request on Codex.

**The A/B.**

- **Fixture:** round 1 of the `e2e-m1` Tallybird study: two landing-page
  concepts, personas P01 Tracey Vukovic and P02 Dinesh Ramanathan. One copy
  per arm, outside any git repository, with the persona files reset and the
  review order B then A in every run.
- **Arm A:** the runner's arguments as `launch_command()` builds them, with
  `--max-budget-usd 1.5` on Claude Code.
- **Arm B:** the same plus `--system-prompt "<the replacement prompt>"` on
  Claude Code, or `-c model_instructions_file=<absolute path to the prompt>`
  on Codex.
- **Runs:** ten, five per arm, one per cell: P01 and P02 on `haiku`, P01 on
  `sonnet`, and P01 and P02 on Codex's default model at low effort. All ten
  started together, each under a 900-second timeout.

The replacement prompt, 79 words, used unchanged for both CLIs:

```
You are taking part in a research study as a participant. You are the person described in your persona file: think, judge and write as that person would, in their own words, for the whole session.

You work by reading the files you are pointed to and by writing your answers to your own file, using the tools provided. Read images by opening them with the same tools.

Your task instructions follow in the next message. Follow them exactly.
```

**Results.**

- **Completion and checks.** All ten runs were complete: a scored section for
  both concepts and every final section. `check_runs.py` reported 0 blocking
  problems and 0 notes for each arm, `extract_scores.py` gave 10 score rows
  from 5 complete runs per arm, and `extract_answers.py` parsed every answer
  and line entry in both. No run had a tool error, a refusal, a failed edit or
  an early stop. Nothing broke in arm B.
- **Behaviour.** Every run in both arms read the instructions, its own persona
  file, both images and the page text of each concept, and nothing else, and
  changed only its own persona file. Each opened the same four images (each
  concept's desktop sheet and mobile screens), and arm A, P01 codex zoomed
  into one more. No persona file mentions a path, a tool, the model, the
  operating system, the date or the account.
- **Voice.** Both arms read as the persona. Read side by side, the arms could
  not be told apart by voice. Gut-reaction lines for the same persona and
  model, arm A then arm B:
  - P01 haiku, Concept B: "Looks tidy, now prove the numbers and tell me what
    my blokes have to do." / "Right audience, now show me who's behind the
    numbers."
  - P01 sonnet, Concept A: "Finally someone who answers the crew question
    straight." / "That table is my Sunday night spreadsheet, and it didn't
    make me feel like I'm being sold to."
  - P01 codex, Concept B: "You've named my Sunday night, now show me where the
    numbers come from." / "You've named my Sunday-night headache, now show me
    who's doing the input."
  - P02 codex, Concept B: "Leave the ledger alone, then show me where the
    profit number comes from." / "You've answered my first safety question,
    not proved the answer."
  - P02 haiku, Concept B: "Decent answers at the bottom, but the big claims at
    the top have no backing." / "Tidy, quick to read, but the numbers are
    doing a lot of work with no source behind them."
- **Out-of-character slips.** Neither arm offered help, wrote "on the one
  hand" summaries or used consultant language inside the in-character
  sections.
  - Arm A, P01 haiku broke character once inside a template field: "(Note:
    Dave is a placeholder name I've made up for my bookkeeper, not from the
    materials.)" Arm B had no equivalent.
  - Arm A, both Codex runs narrated the study's rules in character: "I checked
    the full page text; those details aren't explained", "the placeholder
    amount hasn't influenced my score", "These are placeholder amounts, not my
    basis for scoring".
  - Arm B, P01 codex did the same in milder words: "Those are draft prices,
    but the payment structure is clear", "The draft amount doesn't affect my
    verdict". Arm B, P02 codex kept that to the researcher notes.
  - Final chat replies, which are not the persona file, open in assistant
    voice on Claude Code in both arms ("I've finished both reviews and the
    final sections"). Codex replies are two or three terse lines in both arms.
  - That is one or two fewer slips in arm B across five pairs. It points the
    hoped-for way, and it is within what a rerun of either arm would change.
- **Template discipline.** Every run in both arms has all twelve fields in
  order for both concepts, the eleven-column score row and the seven final
  headings in order, with no invented heading and no concept given a title.
  - Quoted keep, cut and don't-believe lines are verbatim page text in 30 of
    30 cases in arm A and 29 of 30 in arm B (the miss is a sentence cut
    short).
  - Section length is 371 to 669 words per concept section in arm A and 371 to
    665 in arm B.
  - Neither arm used an em or en dash.
  - One formatting difference: arm B, P01 codex wrote 24 curly quotation marks
    around its own phrases, and no other run in either arm has any. The
    default Codex prompt may be what keeps punctuation plain, and one run
    cannot show that.

**Scores.** Concept A ranked first in all ten runs, and no pair changed its
ranking. The eleven factors, in template order: First impression, Relevance,
Problem recognition, How it works, Why care, Trust, Visual design, Structure
and flow, Mobile, Next step, Overall.

| Persona | Model | Concept | Arm A | Arm B | Sum of absolute differences |
| --- | --- | --- | --- | --- | --- |
| P01 | haiku | A | 7 8 9 8 8 7 7 8 6 7 8 | 8 6 8 8 8 6 7 8 6 7 7 | 6 |
| P01 | haiku | B | 7 7 7 6 7 4 7 7 8 5 6 | 7 9 7 6 6 5 8 7 8 6 6 | 6 |
| P02 | haiku | A | 8 7 7 7 7 7 8 8 6 6 7 | 7 7 7 6 6 6 7 8 5 5 6 | 8 |
| P02 | haiku | B | 6 3 5 4 5 3 7 6 7 3 4 | 6 5 6 4 5 3 7 7 7 3 4 | 4 |
| P01 | sonnet | A | 8 8 8 8 8 6 7 8 5 8 8 | 8 9 9 8 8 7 8 8 6 8 8 | 5 |
| P01 | sonnet | B | 7 6 7 4 6 4 7 7 7 6 6 | 8 8 7 4 7 5 7 8 8 7 7 | 9 |
| P01 | codex | A | 8 9 8 8 9 7 8 9 6 8 8 | 9 9 8 8 9 7 8 9 6 7 8 | 2 |
| P01 | codex | B | 9 9 9 4 8 4 8 7 8 6 6 | 8 8 9 4 8 4 8 7 8 5 6 | 3 |
| P02 | codex | A | 9 8 9 8 8 7 8 9 6 6 8 | 9 9 8 8 8 7 8 9 6 6 8 | 2 |
| P02 | codex | B | 8 7 8 4 7 4 8 7 8 3 6 | 8 7 8 4 7 4 8 8 8 3 6 | 1 |

- **Mean absolute difference per cell:** 0.42 over 110 cells (codex 0.18,
  haiku 0.55, sonnet 0.64).
- **No direction:** the mean signed difference, arm B minus arm A, is +0.07.
  The mean score is 6.87 in arm A and 6.95 in arm B, with a spread of 1.51 and
  1.48.
- **Run-to-run variation is as large.** The fixture's earlier run of P01
  sonnet with the default prompt differs from arm A (also the default) by 12
  points over the same 22 cells, and from arm B by 6. The earlier default P01
  codex run is identical to arm B on all 22 cells and differs from arm A by 5.
  Two default runs differ from each other as much as the arms do.
- Neither arm scored flatter or more generously.

**Tokens and cost.**

| Arm | Run | Wall | Input tokens (cached) | Output tokens | Cost | Tool calls |
| --- | --- | --- | --- | --- | --- | --- |
| A | P01 haiku | 43 s | 128,162 (103,148) | 8,459 | $0.010 | 12 |
| B | P01 haiku | 44 s | 136,238 (110,831) | 8,128 | $0.010 | 12 |
| A | P02 haiku | 61 s | 193,876 (164,959) | 11,612 | $0.013 | 13 |
| B | P02 haiku | 41 s | 112,574 (88,046) | 7,652 | $0.010 | 11 |
| A | P01 sonnet | 40 s | 92,110 (69,325) | 5,035 | $0.148 | 10 |
| B | P01 sonnet | 40 s | 85,929 (60,398) | 5,085 | $0.159 | 11 |
| A | P01 codex | 82 s | 218,539 (186,240) | 2,752 | not reported | 8 |
| B | P01 codex | 74 s | 152,615 (132,096) | 2,449 | not reported | 7 |
| A | P02 codex | 105 s | 217,527 (190,464) | 2,777 | not reported | 8 |
| B | P02 codex | 92 s | 150,699 (114,304) | 2,377 | not reported | 7 |

- Codex arm B used about 30% fewer input tokens: 303,314 against 436,066 for
  the two runs. That is the only measurable gain.
- Claude Code shows no consistent change.
- Tool calls on Codex are `exec` calls counted from the rollout. On Claude
  Code they are Read, Glob, Edit and, in one run, Grep.
- Dollar figures are list prices under a subscription login. Codex reports no
  cost.

**What ten runs can and cannot show.**

- **They can show** that replacement does not break the plain panellist path
  on these three models, and that there is no large effect on voice, template
  or scores. A large effect would have been visible in five pairs, and none
  was.
- **They cannot show** a small effect. With two personas, one study and one
  run per cell, the slightly lower count of slips in arm B and the curly
  quotes in one Codex run are both within noise.
- **Limits of the setup:** both arms' working directory path contained
  `exp-sysprompt`, which the models could see. The arms ran at the same time.
  Only landing pages were reviewed, with no browsing, no follow-up question
  and no Pi runner.
- **The experiment's reading:** no real difference in research output.
  Confidence is high that nothing breaks, and moderate that there is no effect
  worth having.

**Decision (the user, 13 October 2026).** The `claude` and `codex` runners keep
their harness's default system prompt for now, and no study option replaces
it. The user's reason: the experiment showed no tangible benefit or difference in
the research output when the default system prompts were overridden. The
question is set aside, not closed.

What the experiment adds to that reason:

- The persona file and the panel instructions already do the work under the
  default prompt.
- With the runner's isolation flags the Claude Code default is small (about
  2,200 tokens), and nothing in it showed up in any persona file.
- The Codex key is undocumented, and a renamed key would silently restore the
  default without the runner's `check()` noticing.
- A second prompt path adds resume rules that differ between the two CLIs.

The experiment did not cover Pi, and the `pi` runner is unchanged. It passes
`--system-prompt ""` and `--append-system-prompt ""`, a choice made for that
runner's isolation before this decision: the two flags keep a global
`SYSTEM.md` or `APPEND_SYSTEM.md` out, and Pi's own system prompt stays (Pi,
above).

Worth revisiting when, for example:

- a larger A/B is run on real studies, with more personas and at least two
  runs per cell and arm
- the Codex saving of about 4,300 input tokens per request, about 30% of a
  run's input, starts to matter
- a harness documents its key, or changes its default prompt
- out-of-character output in a real study is traced to the default prompt

**If it is revisited.**

- A study option that is off by default.
- One prompt asset that the skill owns and every runner uses, so that runners
  still add nothing of their own. The file sits outside `panel/`, for example
  in the skill's `assets/`.
- Panellist runs only (a run whose `role` is `panellist`). Analyst and writer
  runs were not tested.
- The plan output says that the harness prompt was replaced, because scores
  from the two settings were not shown to be interchangeable beyond this small
  test.

Claude Code, at launch and on resume alike, after the existing options:

```
--system-prompt "<text of the prompt asset>"
```

- Pass the same text on every resume. The recorded prompt wins while the
  snapshot is on, so repeating it changes nothing today and covers a compacted
  conversation.
- Never pass an empty string, and never pass `--system-prompt-snapshot off`.
- A session started before the option was switched on keeps its original
  prompt on resume, whatever is passed.

Codex, at launch and on resume alike, among the `-c` options before `-C`:

```
-c model_instructions_file=<absolute path to the prompt asset>
```

- Pass it on every resume, before the word `resume`. A resume without it keeps
  the thread's instructions and a resume with different text replaces them, so
  identical text on every call is the only stable rule.
- Guard against a renamed key, which would silently restore the default. A
  check that does not depend on `--strict-config`: after the first launch,
  read `session_meta.base_instructions` from the rollout once per study and
  compare it with the asset.

**Not settled.**

- Any effect smaller than run-to-run noise. Settling it needs more personas
  and at least two runs per cell and arm.
- Claude Code after a compaction with a replaced prompt.
- Why the empty-string prompt made haiku produce no visible output three times
  (one probe).
- Whether the curly quotes in one Codex arm B run come from losing the default
  prompt.
- Codex's `include_permissions_instructions=false`,
  `include_collaboration_mode_instructions=false` and
  `include_environment_context=false` on a real panellist run. They remove
  their blocks at launch, and the blocks return on a resume that omits them.
- The `<multi_agent_role>` and `<multi_agent_mode>` blocks and the global
  `AGENTS.md` still reach a Codex panellist with either prompt.
- Whether another Codex model or an API-key login refuses custom base
  instructions. The default model under the ChatGPT login accepted them.
- Browsing runs, follow-up questions on a resumed panellist, the Pi runner,
  and the analyst and writer roles.
- The account email stays in a Claude Code panellist's context with either
  prompt.

**Side finding, left unchanged.** On Codex,
`-c include_environment_context=false` removes the block that carries the
working directory, shell, date and timezone, an isolation gap the plan reports
today. The key is undocumented and was not tried on a full panellist run, so
the runner does not pass it.

### A lead in a sandboxed shell

Checked on 13 October 2026 on Linux, with claude 2.1.296 and codex-cli
0.162.1. **Outcome:** a panel starts from a Claude Code session's shell, from
a terminal and with no terminal at all. From a Codex session it starts only
when `launch.py run` is approved to run outside the Codex sandbox. The full
text, with what each refusal means and how a Codex lead works, is in
`references/runners.md`, "When the lead's own sandbox blocks the launcher".
The decisions it led to are under
[Follow-up work after milestone 5](#follow-up-work-after-milestone-5).

**Round 1.** One text-only review of four runs: two personas, on `haiku`
through `claude` and on the default model at low effort through `codex`. It
ran before the launcher tested the shell, when `plan` said "ready"
everywhere. The last column is what `plan` says since, checked the same day
in the same shells with no model.

| Where `run` was started | What the runs did | `plan` now |
| --- | --- | --- |
| A Claude Code session's shell tool, its sandbox off | 4 done | Both ready |
| A plain terminal: a clean login environment, a real tty, no harness variable | 4 done | Both ready |
| No terminal: `nohup`, stdin from `/dev/null` | 4 done | Both ready |
| Codex sandbox, read-only (the default of a headless Codex session) | Nothing started. `run` was refused in one sentence, for the lock file it could not write | Refuses the study directory and both runners |
| Codex sandbox, `workspace-write` | Codex: the CLI exited before printing anything. Claude Code: no network, so each run and its retry failed | Refuses both runners |
| The same, with network access | Codex: the same. Claude Code: 2 of 2 done, with no session saved | Refuses both runners |
| The same, with the Codex and Claude configuration directories writable | Claude Code: 2 of 2 done, sessions saved. Codex: each run called the model, had every shell command refused and wrote nothing, for up to 160,000 input tokens a run | Refuses `codex`, `claude` ready |
| A Codex session as the lead (`codex exec --approve-for-me`), `run` approved to run outside its sandbox | 4 done | Refuses inside the sandbox (round 2) |

**Round 2,** on the tree after the fixes:

- **Terminal:** plan, run, status, checks, extraction, analysis, archive, a
  second archive (byte for byte the same), two follow-ups (both reached the
  original sessions) and purge.
- **Codex lead:** `plan` refused inside the sandbox, as designed, and the
  lead asked for `run` outside it.
- **Usability:** one persona on Claude Code (`haiku`) and on Codex (low
  effort), two tasks, accounts, success checks and an archive. Both runs
  done, the launcher's step count equal to the step log for every task, no
  run stopped in error, accounts torn down, and no secret found by its shape
  in any output or in the archive.

Round 2 ran on a snapshot taken before the archive reported a folder it
cannot prune and before liveness was decided by locks.

**Round 3,** on a snapshot with the lock each watchdog holds, the namespace
on each watchdog's pid file and `status` by lock. The same four-run review
study, started from a clean terminal:

- **Runs:** 4 done from one `run`, one attempt each.
- **`status` mid-run, from the ordinary shell:** four runs alive and the
  launcher running.
- **`status` mid-run, inside a Codex sandbox (no model):** the recorded
  states, "Launcher: running" and the line saying that this shell cannot see
  the launcher's processes, with no advice to resume or stop.
- **`stop` inside the sandbox:** exit code 1, nothing signalled, `runs.json`
  byte for byte the same, and the runs finished.
- **Locks:** each attempt's lock was held by its watchdog while the run
  lived and by nothing after. Both shells then said "Launcher: not running".
- **After the runs:** follow-ups reached the original sessions, the archive
  was complete with no empty folder, a second archive was byte for byte the
  same, and 4 sessions were purged.

Checked with fake panels only, inside real sandboxes and with no model:

- **Inside `codex sandbox`, against a launcher outside it:** `status`,
  `plan`, `run`, `resume` and `stop`, with the launcher running, killed with
  its runs alive, and killed with its runs ended. Also a launcher started
  and killed inside a sandbox, one killed inside a sandbox that stayed open,
  `archive.py` on a study the sandbox showed read-only, and the archive's
  report of a folder it cannot prune.
- **Inside a `bwrap` sandbox with a process namespace of its own:** the
  shared lock of `archive.py` on a read-only study while a launcher command
  waited outside, and a lead's account command on the other side of the
  sandbox from the launcher, in both directions, also after the sandbox had
  ended.
- **By tests alone:** a process that holds the launcher's process id and
  start identity in another namespace (a lock file edited to say so), and
  the scaffold's failure when it cannot make the lock file.

Round 3's snapshot came before the last lock changes, so no real panel has
run on them: the lock file that persists between launchers, the shared lock
for a read-only archive, the namespace on the launcher's lock record, and
the account command's lock with its recovery across namespaces.

What the runs showed:

- A Codex CLI cannot build its own sandbox inside another Codex sandbox. No
  writable directory changes that.
- A study with only Claude Code panellists can stay inside the sandbox, with
  network on and the Claude configuration directory writable.
- The approval of `run` was decided by Codex's automatic reviewer, itself a
  model. It refused while nothing in the session said that the user had
  agreed to the materials going to the providers, and allowed the same run
  once the session said so.

Not tested:

- an interactive Codex session, where the request goes to the user as an
  approval prompt
- full access mode: with no model the `codex` CLI could build its sandbox
  under it, and no run was made
- `pilot`, `resume`, follow-ups, `purge-sessions --yes` and the analyst and
  writer jobs from a Codex lead
- a usability study from a Codex lead
- macOS, where Codex's sandbox is a different one, and the `pi` runner in
  any sandbox
- a lead's account command left on the other side of `codex sandbox`, and
  `archive.py` there while a launcher starts outside it: both were checked
  under `bwrap` only

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

## Open questions for the user

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
