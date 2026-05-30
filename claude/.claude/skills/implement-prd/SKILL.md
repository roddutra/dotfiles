---
name: implement-prd
description: "Implement a PRD end-to-end as a PM delegating to subagents. Full workflow: digest the PRD and codebase, resolve every ambiguity or open decision with the user, then execute via task delegation with Codex code review (iterative per milestone for large PRDs). Use when the user wants to build out an existing PRD document."
disable-model-invocation: true
---

# Implement-PRD: Build a PRD as PM

End-to-end workflow: digest the PRD that was injected when this skill was invoked, drive out every ambiguity with the user, then execute the PRD as a project manager delegating to subagents, with Codex reviewing the resulting code.

## Phase 1: Understand the PRD

1. Read and digest the injected PRD thoroughly. It is the primary requirements source. Read any docs or files it references.
2. Explore the codebase thoroughly — understand the relevant code, architecture, patterns, and conventions. Read files, search for related code, check existing tests and docs.

## Phase 2: Resolve Ambiguity and Decisions

1. Identify every gap, ambiguity, contradiction, or unresolved decision in the PRD that would force a subagent to guess. This includes underspecified behaviour, undefined edge cases, missing acceptance criteria, conflicting requirements, and open technical choices.
2. Resolve what you can by reading the codebase or the PRD's referenced material — do not ask the user something the code already answers.
3. For everything that genuinely needs a human decision, interview the user. Present concrete options with trade-offs rather than open-ended questions where possible.
4. Do NOT begin execution until the PRD is unambiguous and every open decision is settled. Confirm the resolved understanding with the user before proceeding.

## Phase 3: Execution

Once the PRD is unambiguous and decisions are settled, execute:

1. Research the codebase and confirm you thoroughly understand the PRD, requirements, and any referenced docs/files. Convert the PRD's tasks/milestones into tasks using the TaskCreate tool.
2. The main agent acts as project manager — do not write code. Delegate each task to subagents via the Agent tool, providing rich context (relevant PRD section, files to modify, architectural decisions, constraints, relationship to other tasks) so each subagent can make aligned decisions independently.
3. Review each subagent's output. Iterate until the work meets quality standards and aligns with the PRD. Once all tasks are complete, delegate documentation updates across three tiers:
   - **Project documentation** (README.md, docs/, etc.): Update or create docs relevant to both human developers and AI coding agents — covering new features, functionality, architecture, usage, and any logic implemented.
   - **Global agent instructions** (CLAUDE.md, AGENTS.md): Only update if something is critical for ALL future coding agent sessions to have in context every time. This is expensive (loaded into every agent's context window on every session), so keep it to information that is universally required regardless of the task.
   - **Claude Skills** (.claude/skills/): Create or update topic-specific skill files for instructions only relevant to certain areas of work. Agents load skills on-demand based on the skill's description, so this is the token-efficient way to document specialized patterns, workflows, or conventions without bloating every session's context.
4. **Codex code review — iterative for large PRDs.** If the PRD spans multiple milestones or phases, do NOT wait until everything is complete to run a single massive Codex review. Run a focused Codex review after each milestone/phase (using the codex-reviewer skill), scoped to that milestone's changes. This keeps each review narrow, avoids overwhelming Codex's context window, and catches issues early so later milestones build on reviewed, corrected code. Only move to the next milestone once all Critical/Major findings from the current review are addressed and Codex has confirmed them resolved. For small PRDs (single phase or a handful of changes), a single final review is fine — use judgment based on scope. Regardless of strategy, after applying changes from Codex's findings you MUST send the updated code back to Codex for re-review — never assume your changes are correct. A review round is complete only when Codex has seen the final state. Iterate until Codex explicitly confirms no remaining issues. Use a single Codex session across milestones (resume, don't re-init) so Codex accumulates context; for each milestone review, tell Codex which files changed and the milestone's goals.

## Phase 4: Final Summary

When execution is complete, present a final summary to the user: what was implemented, any deviations from the PRD and why, Codex's review verdicts (per-milestone if iterative), and any remaining items or follow-ups.
