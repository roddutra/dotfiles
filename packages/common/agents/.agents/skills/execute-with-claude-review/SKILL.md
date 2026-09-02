---
name: execute-with-claude-review
description: "Execute an already-defined task, requirement, plan, or PRD as project manager delegating implementation to subagents, with Claude Code acting only as an independent reviewer or brainstorming partner. Full workflow: digest the work, create ordered tasks, delegate execution, and use claude-reviewer at milestone gates for large work or once at the end for small work. Use whenever the user wants end-to-end implementation with Claude reviewing the result."
---

# Execute with Claude Review

Execute defined work through implementation subagents. Claude reviews or brainstorms but does not implement in this workflow.

## Phase 1: Understand the Work

Handle both forms:

- Reference files: read the PRD, plan, spec, and everything they reference.
- Freeform description: use the inline task as the requirements source.

Then:

1. Explore relevant code, architecture, patterns, conventions, tests, and docs.
2. Resolve gaps from available evidence before asking the user.
3. Present concrete options for genuine open decisions.
4. Do not execute until behavior, scope, constraints, and acceptance criteria are unambiguous.

## Phase 2: Set Up Tasks and Dependencies

1. Break the work into ordered tasks in the harness's task or todo system.
2. Give each task enough context for independent execution:
   - requirement or plan section
   - files and contracts
   - architecture decisions
   - constraints and non-goals
   - dependencies
   - acceptance criteria
   - targeted verification
3. Mark independent work and dependency edges.
4. Group large work into milestones. These define Claude review cadence.

## Phase 3: Execute as Project Manager

1. The main agent acts as project manager and does not write implementation code.
2. Delegate each task to a fresh subagent with the context captured in Phase 2.
3. Run independent tasks in parallel only when ownership and integration contracts are explicit.
4. Resume a subagent only to continue the same focused task. Never reuse it for another task or milestone.
5. Review real changed files and verification after every task.
6. Iterate until each task satisfies its acceptance criteria.

## Phase 4: Collaborate with Claude at the Right Points

Never invoke `claude` directly. Load `claude-reviewer` and use only its scripts and process.

Use Claude for:

- Code review by default: bugs, security, performance, design, missing tests, and requirement divergence.
- Brainstorming when a real design decision, blocker, or trade-off needs an independent perspective.

Cadence:

- Large work: review after every milestone.
- Small work: one final review.

Milestone review process:

1. Complete and verify the milestone.
2. Initialize or resume the Claude review session.
3. Give Claude the milestone goal, requirements, constraints, changed files, and tests to inspect.
4. Read Claude's `output_file` and critically assess every finding.
5. Delegate accepted corrections.
6. Verify the corrections.
7. Send the updated code back through the same Claude session.
8. Repeat until Claude has seen the final milestone state and no Critical or Major finding remains.
9. Proceed to the next milestone only after the gate is clean.

Use one Claude review session across related milestones so review context accumulates. Keep implementation subagents fresh per task. These are different policies because the reviewer is read-only and focused on the evolving whole, while implementers accumulate task-specific working context.

Do not ask Claude to pre-approve planned corrections. Apply the changes first, then re-review the actual code. Re-review is mandatory after material corrections.

## Phase 5: Milestone Checkpoints

For large work, create a checkpoint commit only after:

1. milestone implementation is complete
2. task-level and integration checks pass
3. all Critical and Major Claude findings are addressed
4. Claude has reviewed the corrected final state

Stage only files belonging to that milestone. Never add attribution lines to commits. For small work, do not create an unsolicited checkpoint commit.

## Phase 6: Documentation and Cleanup

After all reviewed implementation tasks:

1. Update project documentation for behavior, architecture, and usage changes.
2. Update global agent instructions only when context is universally required for all future sessions.
3. Put specialized conventions in on-demand project skills.
4. Remove obsolete scaffolding and temporary implementation artifacts.
5. Run the actual end-to-end behavior and final integration checks.

## Phase 7: Final Report

Tell the user:

- what was implemented
- deviations from the requirement, plan, or PRD and why
- verification evidence
- Claude's milestone or final review verdicts
- findings accepted, rejected, and corrected
- remaining items
- the saved Claude review session path

Do not clean the Claude review session unless the user explicitly asks.
