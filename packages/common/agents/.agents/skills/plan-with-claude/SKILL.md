---
name: plan-with-claude
description: "Plan a feature or task with Claude Code as an independent co-planner, then execute as project manager delegating to subagents. Full workflow: gather requirements, draft a durable plan, iterate through claude-reviewer until consensus, obtain user approval, execute through task delegation, and use Claude for milestone or final code review. Use when the user wants to plan and build something end-to-end with Claude as co-planner and reviewer. Claude reviews and brainstorms but does not implement."
---

# Plan with Claude, Execute as Project Manager

Plan with an independent Claude Code session, obtain user approval, then execute by delegating implementation to the invoking harness's subagents.

## Prerequisite: Planning Mode

If the harness has a planning mode, enter it before changing project files. Otherwise, do not implement until Phase 5. Store the plan as a markdown file and treat it as the source of truth.

## Phase 1: Understand the Requirements

Handle both input forms:

- Reference files: read the PRDs, specs, docs, and everything they reference.
- Freeform description: use the user's description as the starting requirements.

Then:

1. Explore relevant code, architecture, patterns, conventions, tests, and documentation.
2. Resolve questions from repository evidence before asking the user.
3. Interview the user only for genuine open decisions.
4. Capture goals, constraints, scope, non-goals, edge cases, and acceptance criteria.

## Phase 2: Draft a Durable Plan

1. Use the harness's plan location when available. Otherwise write `.tmp/plans/<slug>.md` inside the repository.
2. Cover:
   - problem and goals
   - scope and non-goals
   - ordered implementation tasks
   - dependencies and parallelizable work
   - design decisions and trade-offs
   - exact files and contracts to create or modify
   - migrations and compatibility concerns
   - testing and behavioral verification
   - risks and mitigations
3. Make each task precise enough to delegate independently.
4. Do not include estimated timelines unless requested.
5. Add a persistent `Execution Instructions` section to the plan:

```text
## Execution Instructions

1. Re-read this plan, referenced files, and relevant repository code. Convert every plan task into the harness's task or todo system.
2. The main agent acts as project manager. It does not implement code. Delegate each implementation task to a fresh subagent with its plan section, paths, contracts, constraints, dependencies, and acceptance criteria.
3. Review each subagent's real changes and verification. Iterate until each task matches the plan.
4. For a large plan, run a focused Claude review after each milestone through claude-reviewer. Address every Critical and Major finding, then send the corrected code back to the same Claude session before starting the next milestone. For a small plan, one final Claude review is sufficient.
5. After implementation, update project documentation where behavior changed. Update global agent instructions only for universally required context. Put topic-specific guidance in the project's on-demand skills.
```

## Phase 3: Claude Co-Planning Until Consensus

1. Load `claude-reviewer`. Never invoke `claude` directly.
2. Initialize a fresh review session and follow all reviewer steps.
3. If the plan is outside the repository, copy it into `.tmp/` without reading it into the invoker's context first. Recopy it after each revision.
4. Give Claude the user's goals, constraints, settled decisions, non-goals, and relevant files to inspect.
5. Ask Claude to review feasibility, task ordering, dependencies, simpler alternatives, risk, gaps, test strategy, and unnecessary complexity.
6. Read Claude's `output_file` and critically assess each finding.
7. Update the actual plan for accepted findings.
8. Explain rejected findings with evidence in a follow-up prompt.
9. Send the updated plan back through the same Claude session for re-review.
10. Repeat until:
    - no Critical or Major finding remains
    - the plan is complete, feasible, and correctly ordered
    - disagreements have been explicitly resolved
    - Claude has reviewed the final plan state

Do not present the plan for approval before this review loop is complete.

If a later invoker session needs the review history, use `review.py list` from `claude-reviewer` and recover the saved prompt and output files instead of starting from assumptions.

## Phase 4: User Approval

1. Present the finalized plan.
2. Summarize what Claude reviewed, notable corrections, rejected findings, and resolved trade-offs.
3. Surface remaining user decisions.
4. Wait for explicit approval before execution.
5. If the user requests a material change, revise the plan and repeat the Claude review loop. Skip re-review only for editorial changes.

## Phase 5: Execute as Project Manager

After approval:

1. Leave planning mode if applicable.
2. Re-read the plan from disk.
3. Initialize the harness's task list from every plan task.
4. Delegate implementation to fresh subagents. Do not ask Claude reviewer to implement.
5. Run independent tasks in parallel only when ownership and contracts are explicit. Keep dependent tasks ordered.
6. Review every subagent's changed files and checks.
7. For large work, use milestone review gates:
   - complete one milestone
   - run a focused review through the existing `claude-reviewer` session
   - address all Critical and Major findings
   - re-review the corrected code
   - proceed only after Claude confirms the final milestone state
8. For small work, run one final Claude code review and the same correction and re-review loop.
9. Verify the actual end-to-end behavior after integration.
10. Complete documentation and cleanup required by the plan.

## Phase 6: Final Report

Tell the user:

- what was implemented
- deviations from the approved plan and why
- verification evidence
- Claude's milestone or final review verdicts
- accepted and rejected review findings
- remaining items
- the saved Claude review session path

Do not clean Claude session artifacts unless the user explicitly asks.
