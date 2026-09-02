---
name: implement-prd-with-claude
description: "Implement an existing PRD end-to-end as project manager delegating to subagents, with Claude Code providing independent code review. Full workflow: digest the PRD and codebase, resolve every ambiguity with the user, create ordered tasks, delegate implementation, and iterate through Claude milestone or final review until clean. Use whenever the user wants to build an existing PRD with Claude reviewing the code. Claude does not implement in this workflow."
---

# Implement a PRD with Claude Review

Digest the PRD, resolve ambiguity, execute through subagents, and use `claude-reviewer` as the independent reviewer.

## Phase 1: Understand the PRD

1. Read the entire PRD and everything it references.
2. Treat it as the primary requirements source.
3. Explore relevant code, architecture, patterns, conventions, tests, and docs.
4. Identify the real end-to-end verification path for each user-visible behavior.

## Phase 2: Resolve Ambiguity and Decisions

1. Identify every gap, contradiction, unresolved decision, undefined edge case, missing acceptance criterion, and open technical choice that would force an implementer to guess.
2. Resolve what repository code and referenced material answer.
3. For genuine user decisions, present concrete options with trade-offs.
4. Do not begin execution until the PRD is unambiguous.
5. Confirm the resolved understanding with the user.

## Phase 3: Create Tasks and Dependencies

1. Convert every PRD task and milestone into the harness's task or todo system.
2. Each task must include:
   - relevant PRD section
   - exact files and contracts
   - settled architecture decisions
   - constraints and non-goals
   - dependencies
   - observable acceptance criteria
   - targeted verification
3. Mark dependency order. Run only truly independent work in parallel.
4. Define milestones for large PRDs. These become Claude review gates.

## Phase 4: Execute as Project Manager

1. The main agent acts as project manager and does not write implementation code.
2. Delegate each task to a fresh subagent with complete task-local context.
3. Never reuse one implementation subagent for a different task or milestone. Resume only to correct or complete the same task while its context remains focused.
4. Review every subagent's real changes, not only its report.
5. Run task-level verification and iterate until the task meets the PRD.
6. Keep dependent work ordered and coordinate shared-file ownership.

## Phase 5: Claude Review Gates

Never invoke `claude` directly. Load `claude-reviewer` and follow its complete step-by-step process.

For a large PRD:

1. Complete one milestone.
2. Start or resume one Claude review session for the PRD.
3. Give Claude the milestone goal, changed files, PRD sections, constraints, and tests to inspect.
4. Ask for bugs, security issues, performance problems, design flaws, missing behavior, and PRD divergence.
5. Critically assess each finding.
6. Delegate accepted corrections.
7. Verify the corrected behavior.
8. Send the updated code back to the same Claude session.
9. Repeat until Claude has reviewed the final milestone state and no Critical or Major finding remains.
10. Only then proceed to the next milestone.

For a small PRD, run one final review using the same correction and mandatory re-review loop.

Do not ask Claude to pre-approve intended fixes. Apply the corrections first, then have Claude inspect the actual state.

## Phase 6: Documentation and Integration

After implementation and Claude review:

1. Run the actual end-to-end behavior.
2. Run applicable contract tests, lint, build, type checks, and migration checks once at integration level.
3. Update project documentation for new behavior, architecture, and usage.
4. Update global agent instructions only for universally required context.
5. Put specialized conventions in the project's on-demand skills rather than global instructions.
6. Resolve scaffold, temporary files, and obsolete paths created by the implementation.

## Phase 7: Final Report

Tell the user:

- what was implemented
- deviations from the PRD and why
- resolved ambiguities and user decisions
- verification evidence
- Claude's verdict for each milestone or the final review
- accepted and rejected findings
- remaining items
- the saved Claude review session path

Keep Claude session artifacts. Run cleanup only when the user explicitly asks.
