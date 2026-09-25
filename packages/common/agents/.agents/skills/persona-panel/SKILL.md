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

1. **Frame the study with the user.** What is being decided, who the target audience is, which concepts, what's fictitious or a placeholder (demo company, prices), and what must stay local or uncommitted. Confirm the scale (runs cost tokens: 56 runs of 14 concepts is a large job; 18 runs of 3 concepts is a small one).
2. **Design the roster.** Read `references/personas.md`. Cover role x experience x personality, add 2 to 4 adjacent or out-of-scope personas on a wide round, and keep only the closest-to-target personas on a follow-up.
3. **Write `study.json`** from `assets/study.example.json`. Set `context_notes` for everything a literal reader would misjudge, `find_the_answer` for the 4 to 6 questions a page must answer, `leak_terms` (internal vocabulary that must never appear in a review) and `forbidden_terms` (build notes that must never appear on a page). Pin `labels` only when reproducing an earlier study.
4. **Scaffold:** `init_study.py <study>`. It copies the concepts under neutral labels, writes the instructions, persona files, run prompts, runs.json and key.md.
5. **Capture:** `capture.py <study>`. Then look at one desktop sheet and one mobile sheet per concept yourself: blank reveal bands, a repeated last screen or a missing page will be scored as real defects. Fix the concept or add a `context_notes` line, then recapture.
6. **Launch runs.** `runs.py <study> next --limit 20 --running <ids>` prints the prompts that fit in free slots. Launch each as a background subagent with its model and the prompt text verbatim (Claude Code: Agent tool, `run_in_background: true`, `model` from the run, description `Panel <run id>`). As runs finish, check `runs.py <study> status` and fill slots. Resume interrupted runs with SendMessage rather than relaunching.
7. **Validate:** `check_runs.py <study>`. Fix blocking problems (missing or duplicated sections, unscored concepts, invented labels) by resuming or rerunning that run. Record non-blocking flags; the analysts weight them.
8. **Score and analyse:** `extract_scores.py <study>` then `analyze.py <study>`. Add segment views (`--segment a,b`) for the headline audience and a sensitivity view (`--exclude-model <weakest>`).
9. **Qualitative synthesis.** Split the persona files between one or two Opus analysts using `assets/qual-brief.md` (fill every `<PLACEHOLDER>`), then one writer using `assets/synthesis-brief.md`. Analysts never see the product's docs; give them the decisions and constraints that apply now so findings are read through them. If a subagent can't write its file, save its reply with `extract_agent_reply.py`.
10. **Review and report.** Read the synthesis yourself, check surprising claims against the persona files, then give the user the headline, the ICP signal, what to change, and the decisions only they can make. Offer a visual report page if the session can publish one.
11. **Archive** when the user wants it kept: `references/archive.md`.

## Follow-up rounds

New concepts built from the findings get a smaller, cold panel: target personas only, at least 2 models, the same factors and questions so scores compare, and no knowledge of earlier rounds in any persona file, prompt or instruction. Add a new question to the template only when it answers something the last round couldn't.

## Rules for every study

- Panellists see only `panel/`. Nothing about the team's preferences, hypotheses or earlier results goes into persona files, prompts or instructions.
- Same review order across a persona's models; different orders across personas. `init_study.py` does this from the seed; don't hand-edit orders.
- Launch prompts verbatim from `prompts/`. Edits drift between runs and break comparability.
- Treat the output as a hypothesis to test with real people, and say so when reporting. Simulated readers read more than real ones.

Read `references/method.md` before launching runs: it covers model choice, concurrency, resumes, capture pitfalls and how much to trust each result.
