---
name: persona-panel
description: "Run a simulated customer research panel: AI subagents play realistic prospect personas (buyers, users, managers, gatekeepers, sceptics, early adopters) across several models, review design concepts such as landing pages, websites, pricing pages or onboarding flows from screenshots and page text only, score them on fixed factors, and the results are analysed into a leaderboard, quotes, ICP signal and recommendations. Load whenever the user wants personas, a persona panel, simulated users or customers, synthetic user research, or AI agents to review, compare, score or give feedback on design concepts or pages 'like real customers would', wants to know which concept prospects prefer or who the ideal customer is, or wants to rerun or extend an earlier persona research round, even if they don't say 'panel'."
---

# Persona panel

Simulated customer research: persona subagents review concepts the way busy prospects would, on more than one model, with bias controls, and scripts do everything deterministic (scaffolding, capture, run tracking, validation, scoring, statistics, archiving). The lead agent designs the study, launches the runs and synthesises; it never hand-builds these steps.

Scripts are in `scripts/` (Python 3 standard library; capture also needs the `agent-browser` CLI and ImageMagick). Every script takes the study directory and documents itself with `--help`.

## Study layout

```
<study>/study.json      lead config: concepts, personas, models, factors, notes (copy assets/study.example.json)
<study>/key.md          label -> concept key and review orders (lead only)
<study>/runs.json       persona x model runs
<study>/prompts/        one launch prompt per run
<study>/panel/          the only folder panellists may read
<study>/analysis/       scores, checks, quant, qual, synthesis
```

One study directory per round (`round-1/`, `round-2/`). Keep the study outside the concepts folder, and never inside the product's source tree where panellists could wander into docs.

## Workflow

1. **Frame the study with the user.** What is being decided, who the target audience is, which concepts, what's fictitious or a placeholder (demo company, prices), and what must stay local or uncommitted. Confirm the scale and budget: images dominate cost, about 20k tokens per concept page per run (`references/method.md`, Budget). Run a small panel early, after the first round of concepts, rather than after several rounds of iterating on judgement.
2. **Design the roster.** Read `references/personas.md`. Cover role x experience x personality, add 2 to 4 adjacent or out-of-scope personas on a wide round, and keep only the closest-to-target personas on a follow-up. Fix the full persona x model matrix now; adding models later means re-queuing.
3. **Write `study.json`** from `assets/study.example.json`. Set `context_notes` for everything a literal reader would misjudge, `find_the_answer` for the 4 to 6 questions a page must answer, `leak_terms` (internal vocabulary that must never appear in a review) and `forbidden_terms` (build notes that must never appear on a page). Add `states` for any toggle or switch that changes content, and `capture.media` if animations would be caught mid-way. Pin `labels` only when reproducing an earlier study.
4. **Scaffold:** `init_study.py <study>`. It copies the concepts under neutral labels, writes the instructions, persona files, run prompts, runs.json and key.md.
5. **Capture:** `capture.py <study>`. Then look at one desktop sheet and one mobile sheet per concept yourself: blank reveal bands, a repeated last screen or a missing page will be scored as real defects. Fix the concept or add a `context_notes` line, then recapture.
6. **Pilot.** Launch one persona on each model and read those files as they land. Fix instructions or materials now (then `init_study.py --force` and recapture if needed), before the real runs, so no protocol change lands mid-panel.
7. **Launch runs.** `runs.py <study> next --limit 20 --running <ids>` prints the prompts that fit in free slots. Launch each as a background subagent with its model and the prompt text verbatim (Claude Code: Agent tool, `run_in_background: true`, `model` from the run, description `Panel <run id>`), then record its id with `runs.py <study> mark <run> <agent-id>`. As runs finish, check `runs.py <study> status` and fill slots. After an interruption (usage limit, compaction), `runs.py <study> resume` prints a tailored message per unfinished run for SendMessage to its recorded agent.
8. **Review as runs land.** Spot-check suspicious claims against the materials and log them in `analysis/lead-notes.md`. Send a run back only for a blocking error. Report to the user at milestones, not per run (`references/communicating.md`).
9. **Validate:** `check_runs.py <study>`. Fix blocking problems (missing or duplicated sections, unscored concepts, invented labels) by resuming or rerunning that run. Record non-blocking flags; the analysts weight them.
10. **Score and analyse:** `extract_scores.py <study>` then `analyze.py <study>`. Add segment views (`--segment a,b`) for the headline audience and a sensitivity view (`--exclude-model <weakest>`). Read "Model agreement by persona": unsettled personas are model taste, not segment signal.
11. **Qualitative synthesis.** Split the persona files by persona (all models of a persona to one analyst) between one or two Opus analysts using `assets/qual-brief.md` (fill every `<PLACEHOLDER>`, and pass `analysis/lead-notes.md`), then one writer using `assets/synthesis-brief.md`. Analysts never see the product's docs; give them the decisions and constraints that apply now. If a subagent can't write its file, save its reply with `extract_agent_reply.py`.
12. **Review and report.** Read the synthesis yourself, check surprising claims against the persona files, then give the user the headline, the ICP signal, what to change, and the decisions only they can make (`references/communicating.md`). Offer a visual summary page if the session can publish one.
13. **Next round** if the user wants one: brief designers with `assets/next-round-brief.md`, then run a follow-up panel (below).
14. **Archive** when the user wants it kept: `references/archive.md`.

## Follow-up rounds

New concepts built from the findings get a smaller, cold panel: target personas only, at least 2 models, the same factors and questions so scores compare, and no knowledge of earlier rounds in any persona file, prompt or instruction. Add a new question to the template only when it answers something the last round couldn't.

## Rules for every study

- Panellists see only `panel/`. Nothing about the team's preferences, hypotheses or earlier results goes into persona files, prompts or instructions.
- Same review order across a persona's models; different orders across personas. `init_study.py` does this from the seed; don't hand-edit orders.
- Launch prompts verbatim from `prompts/`. Edits drift between runs and break comparability.
- Treat the output as a hypothesis to test with real people, and say so when reporting. Simulated readers read more than real ones.

Read `references/method.md` before launching runs: it covers when to run, budget, model choice, piloting, concurrency, resumes, capture pitfalls, concept design for panels, and how much to trust each result.
