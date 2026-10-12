---
name: persona-panel
description: "Run a simulated customer research panel: AI agents play realistic prospect personas (buyers, users, managers, gatekeepers, sceptics, early adopters) across several models, from one vendor or more, review design concepts such as landing pages, websites, pricing pages or onboarding flows from screenshots and page text only, score them on fixed factors, and the results are analysed into a leaderboard, quotes, ICP signal and recommendations. Load whenever the user wants personas, a persona panel, simulated users or customers, synthetic user research, or AI agents to review, compare, score or give feedback on design concepts or pages 'like real customers would', wants to know which concept prospects prefer or who the ideal customer is, or wants to rerun or extend an earlier persona research round, even if they don't say 'panel'."
---

# Persona panel

Simulated customer research: AI panellists review concepts the way busy prospects would, on more than one model, with bias controls. Each panellist is one headless process of a coding agent's CLI, started through a runner by `scripts/launch.py`, which also limits, tracks and resumes the runs. Scripts do everything deterministic (scaffolding, capture, launching, validation, scoring, statistics, archiving). The lead (an agent on any harness, or a person in a terminal) designs the study, reads the results and reports; it never hand-builds these steps.

Scripts are in `scripts/` (Python 3 standard library; capture also needs the `agent-browser` CLI and ImageMagick; each runner needs its harness CLI installed and signed in). Every script takes the study directory and documents itself with `--help`.

## Study layout

```
<study>/study.json      lead config: concepts, personas, model entries, limits, factors, notes (copy assets/study.example.json)
<study>/key.md          label -> concept key and review orders (lead only)
<study>/runs.json       one entry per run and synthesis job: state, session, attempts, usage
<study>/prompts/        one launch prompt per run, one filled brief per analyst and writer job
<study>/panel/          the only folder panellists may read
<study>/analysis/       scores.csv, rankings.csv, runs.csv, checks, quant, usage.md, qual, synthesis
<study>/logs/           input and output of every process the launcher started
<study>/.launch.lock    present while a launcher has the study (one launcher per study)
```

One study directory per round (`round-1/`, `round-2/`). Keep the study outside the concepts folder, and never inside the product's source tree where panellists could wander into docs.

## Workflow

1. **Frame the study with the user.** What is being decided, who the target audience is, which concepts, what's fictitious or a placeholder (demo company, prices), and what must stay local or uncommitted. Agree the scale: images dominate cost, about 20k tokens per concept page per run, and step 6 puts figures on it. Run a small panel early, after the first round of concepts, rather than after several rounds of iterating on judgement.
2. **Design the roster.** Read `references/personas.md`. Cover role x experience x personality, add 2 to 4 adjacent or out-of-scope personas on a wide round, and keep only the closest-to-target personas on a follow-up. Fix the full persona x model matrix now; adding models later means re-queuing.
3. **Write `study.json`** from `assets/study.example.json`. Set `runner` and `models`: each entry is a model name on the study's runner, or `{"key", "runner", "model", "effort"}` (`references/runners.md` lists the runners). Set `limits` (minutes and budget for each run, one pool for the synthesis), `synthesis.analyst` and `synthesis.writer` (there is no default), and `browse`. Set `context_notes` for everything a literal reader would misjudge, `find_the_answer` for the 4 to 6 questions a page must answer, `leak_terms` (internal vocabulary that must never appear in a review) and `forbidden_terms` (build notes that must never appear on a page). Add `states` for any toggle or switch that changes content, and `capture.media` if animations would be caught mid-way. Pin `labels` only when reproducing an earlier study.
4. **Scaffold:** `init_study.py <study>`. It copies the concepts under neutral labels, writes the instructions, persona files, run prompts, runs.json and key.md.
5. **Capture:** `capture.py <study>`. Then look at one desktop sheet and one mobile sheet per concept yourself: blank reveal bands, a repeated last screen or a missing page will be scored as real defects. Fix the concept or add a `context_notes` line, then recapture.
6. **Plan:** `launch.py <study> plan`. It starts nothing. Read all of it: every run and its limits, what each provider receives, what each runner lacks or could not switch off, the estimate, and the ceiling with its label (guaranteed maximum or estimate) and its caveats. Confirm the cost and the gaps with the user before any run starts. Exit code 1 means a runner cannot be used or `study.json` asks one for something it cannot do.
7. **Pilot:** `launch.py <study> pilot` runs the first persona on each model entry. Read those files as they land. Fix instructions or materials now, before the real runs, so no protocol change lands mid-panel: `init_study.py --force` (it resets every run and its recorded usage), recapture if needed, and pilot again. Then run `plan` again: its estimate now comes from measured usage.
8. **Run:** `launch.py <study> run`, in the background with your harness's shell tool or in a terminal. It stays in the foreground until its runs end and prints one line per state change; `launch.py <study> status` shows every run's state, time and usage. After a usage limit, rate limit or capacity refusal (`blocked`) or an interruption (`partial`), `launch.py <study> resume` continues those runs in their original sessions. A run stopped by its own limit is `limited`: `resume --runs <ids> --extend` gives it one more allowance, and the plan's ceiling then no longer holds, so ask the user first. `launch.py <study> stop` stops the processes and leaves them resumable.
9. **Review as runs land.** Spot-check suspicious claims against the materials and log them in `analysis/lead-notes.md`. Report to the user at milestones, not per run (`references/communicating.md`).
10. **Validate:** `check_runs.py <study>`. A missing or unscored concept leaves its run `partial`, so `resume` sends it back. No command sends back a run that is `done`: fix a duplicated or invented section by hand while nothing is running, and log it in `analysis/lead-notes.md`. Record non-blocking flags; the analysts weight them.
11. **Score and analyse:** `extract_scores.py <study>` then `analyze.py <study>`. Add segment views (`--segment a,b`) for the headline audience and a sensitivity view (`--exclude-model <weakest>`). Read "Model agreement by persona": unsettled personas are model taste, not segment signal. The output states "N of M runs complete" and lists the rest under "Incomplete runs".
12. **Qualitative synthesis:** `launch.py <study> run --role analyst`, read `analysis/qual-*.md`, then `launch.py <study> run --role writer`. The launcher writes each job's brief to `prompts/` from the templates in `assets/`, tells each analyst which of its runs are incomplete, and saves each reply. Analysts wait for the panel unless `--allow-incomplete`. They never see the product's docs: put the decisions and constraints that apply now in a file in the study directory, outside `panel/`, and name it in `synthesis.context_files`.
13. **Review and report.** Read the synthesis yourself, check surprising claims against the persona files, then give the user the headline, the ICP signal, what to change, what was used (`analysis/usage.md`), and the decisions only they can make (`references/communicating.md`). Offer a visual summary page if the session can publish one.
14. **Next round** if the user wants one: brief designers with `assets/next-round-brief.md`, then run a follow-up panel (below).
15. **Archive** when the user wants it kept: `references/archive.md`. When they want the harness sessions gone, `launch.py <study> purge-sessions` lists them and `--yes` deletes them, which ends resume for those runs.

**Native mode.** A study whose model entries name no runner is started by the lead with its own subagent tool and tracked with `runs.py`. It has no limits, no usage record and no isolation beyond instructions. Use it only when the lead's harness has subagents and no usable headless CLI, or as a fallback: `references/runners.md`, Native mode.

## Follow-up rounds

New concepts built from the findings get a smaller, cold panel: target personas only, at least 2 models, the same factors and questions so scores compare, and no knowledge of earlier rounds in any persona file, prompt or instruction. Add a new question to the template only when it answers something the last round couldn't.

## Rules for every study

- Panellists see only `panel/`. Nothing about the team's preferences, hypotheses or earlier results goes into persona files, prompts or instructions.
- Same review order across a persona's models; different orders across personas. `init_study.py` does this from the seed; don't hand-edit orders.
- Launch prompts are the files in `prompts/`, verbatim. The launcher sends them as they are; edits drift between runs and break comparability.
- A study is all runners or all native mode, never a mix.
- Model keys are letters and digits only, and unique within a study: file names and run ids split on hyphens.
- `run` starts only `pending` and `failed` runs. It never restarts a `partial` or `limited` run, and neither should you: continue it with `resume`.
- Incomplete runs stay out of the headline tables. Report their scores only as what the "Incomplete runs" table shows.
- Treat the output as a hypothesis to test with real people, and say so when reporting. Simulated readers read more than real ones.

Read `references/method.md` before launching runs: it covers when to run, runners and model choice across vendors, limits and the plan, piloting, what each run state means, capture pitfalls, concept design for panels, and how much to trust each result.
