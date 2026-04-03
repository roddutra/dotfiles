---
name: plan-codex
description: "Plan a feature or task with Codex as co-planner, then execute as PM delegating to subagents. Full workflow: gather requirements, draft plan, iterate with Codex review until consensus, present for user approval, then execute via task delegation with a final Codex code review. Use when user wants to plan and build something end-to-end with Codex collaboration."
---

# Plan-Codex: Plan with Codex, Execute as PM

End-to-end workflow: collaboratively plan with Codex as an independent co-planner, get user approval, then execute the plan as a project manager delegating to subagents.

## Prerequisites

**Ensure Plan Mode is active.** If you are not already in Plan Mode, enter it immediately using the EnterPlanMode tool before doing anything else.

## Phase 1: Understand the Requirements

The user may provide input in one of two ways — handle both:

- **Reference files provided** (PRDs, specs, docs, or file references alongside the command): Read and digest them thoroughly. These are your primary requirements source.
- **Freeform description**: The user described what they want inline. Use that as the starting point.

Then:

1. Explore the codebase thoroughly — understand the relevant code, architecture, patterns, and conventions. Read files, search for related code, check existing tests and docs.
2. Interview the user only to fill genuine gaps. If a question can be answered by reading the codebase or the provided references, do that instead of asking.

## Phase 2: Draft the Plan

1. Enter Plan Mode using the EnterPlanMode tool.
2. Draft a comprehensive implementation plan covering:
   - Problem statement and goals
   - Scope and out-of-scope items
   - Implementation approach broken into clear, ordered tasks
   - Key design decisions and trade-offs
   - Files to create/modify
   - Testing strategy
   - Risks and mitigations
3. The plan should be detailed enough that each task can be delegated to a subagent with sufficient context to execute independently.
4. **Include an "Execution Instructions" section at the end of the plan document.** This section must be written into the plan file itself so it persists across session compaction. Write the following (reword for token efficiency):

   > **Execution Instructions**
   >
   > 1. Research the codebase and thoroughly understand the plan, requirements, and any referenced docs/files. Once you have the necessary knowledge, convert the plan's tasks into tasks using the TaskCreate tool.
   > 2. The main agent acts as project manager — do not write code. Delegate each task to subagents via the Agent tool, providing rich context (relevant plan section, files to modify, architectural decisions, constraints, relationship to other tasks) so each subagent can make aligned decisions independently.
   > 3. Review each subagent's output. Iterate until the work meets quality standards and aligns with the plan. Once all tasks are complete, delegate documentation updates across three tiers:
   >    - **Project documentation** (README.md, docs/, etc.): Update or create docs relevant to both human developers and AI coding agents — covering new features, functionality, architecture, usage, and any logic implemented during the plan.
   >    - **Global agent instructions** (CLAUDE.md, AGENTS.md): Only update if something is critical for ALL future coding agent sessions to have in context every time. This is expensive (loaded into every agent's context window on every session), so keep it to information that is universally required regardless of what task an agent is working on.
   >    - **Claude Skills** (.claude/skills/): Create or update topic-specific skill files for instructions that are only relevant to certain areas of work. Agents load skills on-demand based on the skill's description, so this is the token-efficient way to document specialized patterns, workflows, or conventions without bloating every session's context.
   > 4. Use the codex-reviewer skill to have Codex perform a code review of all changes. After applying any changes based on Codex's findings, you MUST send the updated code back to Codex for re-review — never assume your changes are correct. A review round is only complete when Codex has seen the final state. Iterate until Codex explicitly confirms no remaining issues.

## Phase 3: Codex Co-Planning — Iterate Until Consensus

1. Use the `codex-reviewer` skill to have Codex review the draft plan. Provide Codex with:
   - The full plan text (inlined in the prompt — plans live outside `--cd`)
   - The user's goals, constraints, and any decisions already made
   - Relevant codebase context (tell Codex which files to read via `--cd`)
   - Review focus: feasibility, ordering, missed dependencies, over-engineering, simpler alternatives, gaps, risks
2. Critically assess Codex's findings. Accept, reject with reasoning, or flag for discussion.
3. Update the plan based on accepted findings.
4. Send the updated plan back to Codex for re-review (mandatory — see codex-reviewer skill).
5. Repeat until both you and Codex are satisfied the plan is solid. Consensus means:
   - No Critical or Major findings remain unresolved
   - Both sides agree the plan is complete, correctly ordered, and feasible
   - Any disagreements have been debated and resolved

**Do NOT present the plan to the user until you and Codex have reached consensus.**

## Phase 4: User Approval

1. Present the finalized plan to the user with:
   - The plan itself
   - A summary of what Codex reviewed and any notable debates or trade-offs that were resolved
   - Any open questions that need the user's input
2. Wait for explicit user approval before proceeding to execution.
3. If the user requests changes, update the plan and re-run Codex review if the changes are substantial.

## Phase 5: Execution

Once the plan is approved:

1. Exit Plan Mode using the ExitPlanMode tool.
2. Re-read the plan file from disk and follow the **Execution Instructions** section written in the plan. The plan file is the source of truth — it contains all the context needed to execute.
3. When execution is complete, present a final summary to the user: what was implemented, any deviations from the plan and why, Codex's final review verdict, and any remaining items or follow-ups.
