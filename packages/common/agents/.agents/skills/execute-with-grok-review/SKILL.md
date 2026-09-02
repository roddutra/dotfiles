---
name: execute-with-grok-review
description: "YOU (the agent) execute a task, requirement, plan, or PRD as a PM delegating to subagents, and Grok acts as an independent reviewer along the way — Grok does NOT do the work. Full workflow: digest the work and codebase, create tasks and dependencies, delegate to subagents as project manager, then use Grok (via grok-reviewer) to code-review or brainstorm solutions at the right points (per milestone for large scope, once at the end for small). Use when the user has already defined what to build and wants it implemented end-to-end with Grok reviewing the result (per milestone for large scope, once at the end for small)."
disable-model-invocation: true
---

# Execute-with-Grok-Review: Implement as PM, Grok Reviews Along the Way

End-to-end execution workflow: digest an already-defined task, requirement, plan, or PRD, set up tasks and dependencies, execute as a project manager delegating to subagents, and pull in Grok (via the `grok-reviewer` skill) to code-review or brainstorm at the appropriate points.

## Phase 1: Understand the Work

The user provides the work in one of two ways - handle both:

- **Reference files** (PRD, plan, spec, or file references): read and digest them thoroughly. These are the primary requirements source. Read anything they reference.
- **Freeform description**: the task described inline. Use that as the starting point.

Then explore the codebase thoroughly - relevant code, architecture, patterns, conventions, existing tests and docs. Resolve gaps by reading the code or referenced material before asking the user. Interview the user only for genuine open decisions that the code and references cannot answer; present concrete options with trade-offs rather than open-ended questions. Do not begin execution until the work is unambiguous.

## Phase 2: Set Up Tasks and Dependencies

1. Break the work into clear, ordered tasks using your harness's task/todo tool (if it has none, keep an ordered checklist in a plan file). Each task must carry enough context to be delegated and executed independently: the relevant requirement/plan section, files to modify, architectural decisions, constraints, and acceptance criteria.
2. Capture dependencies and ordering between tasks so independent work can run in parallel and dependent work waits for its prerequisites.
3. Group tasks into milestones/phases when the scope is large - this defines the Grok review cadence in Phase 3.

## Phase 3: Execute as PM

1. The main agent acts as project manager - **do not write code**. Delegate each task to subagents via your harness's subagent mechanism, passing the rich context captured in Phase 2 so each subagent makes aligned decisions independently. Run independent tasks in parallel.
   - **Spawn a fresh subagent for each separate task or milestone - never reuse one subagent across different tasks/milestones.** It is tempting to resume a prior subagent because it already "has context", but that is a false economy: (a) its context window gets polluted with prior-task detail that degrades focus, and (b) cost scales super-linearly with conversation length - once a subagent session passes ~300k tokens, every further turn re-bills that entire bloated history, burning the user's subscription quota far faster. A clean subagent briefed with the Phase 2 context is cheaper and sharper. Reserve resuming a subagent strictly for continuing the SAME task with a subagent that is still small; if a subagent is already large (roughly >300k tokens), finish its current task and start a new subagent for the next one. (This fresh-per-task rule is the opposite of the Grok reviewer policy below, where resuming the same review session within a milestone is correct - the difference is that Grok review sessions are read-only and short-lived, while implementation subagents accumulate heavy working context.)
2. Review each subagent's output. Iterate until the work meets quality standards and aligns with the requirements.
3. **Grok collaboration - scale to scope.** Use the `grok-reviewer` skill to bring in Grok at the appropriate points:
   - **Code review** is the default - have Grok review the implemented code for bugs, security, performance, and design concerns.
   - **Brainstorming** is the alternative - when a subagent hits a hard design decision, an ambiguous trade-off, or a blocker, bounce the problem off Grok for a second perspective before committing to an approach.
   - **Cadence by scope:** for **large** work (multiple milestones/phases), run a focused Grok code review after each milestone, scoped to that milestone's changes. This keeps each review narrow, avoids overwhelming Grok's context window, and ensures later milestones build on reviewed, corrected code. Only move to the next milestone once all Critical/Major findings are addressed and Grok has confirmed them resolved. For **small** work (single phase or a handful of changes), skip milestone gates and do one final review when the work is ready.
   - Use a single Grok session across milestones (resume, don't re-init) so Grok accumulates context. For each milestone review, tell Grok which files changed and the milestone's goals.
   - **Re-review is mandatory.** After applying changes from Grok's findings, send the updated code back to Grok - never assume your changes are correct. A round is complete only when Grok has seen the final state and explicitly confirmed no remaining issues.
   - **Milestone checkpoint commits.** For **large** work with multiple milestones, create an incremental commit at the end of each milestone as a checkpoint, but only once all code reviews, review rounds, and iterations for that milestone are fully complete (Grok has confirmed no remaining Critical/Major findings). Stage your changes and commit the milestone's changes before proceeding to the next milestone (be selective about what you stage - other agents may be working in the same codebase, so only commit work belonging to this milestone). Keep commit messages free of attribution lines (no "Co-Authored-By", "Generated with <agent>", etc.). For **small** work without milestone gates, skip per-milestone commits and let the user decide when to commit.
4. Once all tasks are complete and Grok-reviewed, delegate documentation updates across three tiers:
   - **Project documentation** (README.md, docs/, etc.): update or create docs relevant to both human developers and AI coding agents - new features, functionality, architecture, usage, and logic implemented during the work.
   - **Global agent instructions** (CLAUDE.md, AGENTS.md): update only if something is critical for ALL future coding agent sessions to have in context every time. This is loaded into every agent's context window on every session, so keep it to universally required information.
   - **Agent skills** (the project's skills directory — e.g. `.agents/skills/`, `.claude/skills/`, `.grok/skills/`, whichever the project uses): create or update topic-specific skill files for instructions relevant only to certain areas of work. Agents load skills on-demand by description, so this is the token-efficient way to document specialized patterns and conventions.

## Phase 4: Final Summary

When execution is complete, present a final summary to the user: what was implemented, any deviations from the original task/plan/PRD and why, Grok's review verdicts (per-milestone if iterative), and any remaining items or follow-ups.
