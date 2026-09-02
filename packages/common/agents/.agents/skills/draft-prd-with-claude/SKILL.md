---
name: draft-prd-with-claude
description: "Draft a new PRD from the user's requirements with Claude Code as the brainstorming partner and independent reviewer. Full workflow: deeply interrogate the problem and why, challenge weak areas, present solution options, draft the PRD, and iterate with a fresh Claude review until no findings remain. On explicit user approval, set the PRD status to Ready. Use whenever the user wants to create a PRD with Claude."
---

# Draft PRD with Claude

Build a shared understanding of the problem, pressure-test the thinking, choose a solution, draft the PRD, and harden it through the `claude-reviewer` workflow.

## Phase 1: Understand the Problem and Why

Extract enough information to understand:

- the problem and the outcome the user wants
- who the change serves
- business logic, rules, and constraints
- success criteria
- edge cases, failures, and unhappy paths
- required output and acceptance criteria

Read the codebase, existing docs, and referenced material before asking questions. Interview the user only for gaps the available evidence cannot answer. Continue until the material decisions are clear.

## Phase 2: Challenge the Requirements

Do not act as a passive scribe:

1. Identify contradictions, unstated assumptions, and requirements that do not serve the stated goal.
2. Surface missing edge cases, second-order effects, scope growth, and simpler problem framings.
3. Push on the reason for the work until its goal and trade-offs are explicit.
4. Resolve a fuzzy problem before proposing implementation details.

## Phase 3: Develop Solutions and Recommend One

1. If the best solution is complex or unclear, load `claude-reviewer` and use a fresh read-only Claude session to brainstorm approaches. Follow every `claude-reviewer` process rule. Give Claude the problem, goals, constraints, settled decisions, out-of-scope items, and repository-relative files to read.
2. Critically evaluate Claude's suggestions. Do not present them as authoritative.
3. Present viable solution options with concrete pros and cons.
4. Give a clear recommendation and explain its trade-offs.
5. If options have materially different consequences, wait for the user to choose. If one path is unambiguous, confirm it with the user before drafting.

## Phase 4: Draft the PRD

Write the PRD to the repository's established location and format. Include:

- status: `Draft`
- problem statement and why it matters
- goals and success criteria
- scope and explicit non-goals
- chosen solution
- key design decisions and trade-offs
- business logic and rules
- user-visible behavior
- edge cases and failure behavior
- risks and mitigations
- observable acceptance criteria
- unresolved questions, if any

Do not include estimated timelines unless the user explicitly requests them.

## Phase 5: Claude Review Until Clean

1. Start a fresh Claude review session through `claude-reviewer`. Never run `claude` directly.
2. Tell Claude to read the PRD and relevant project files from disk. Include the problem, goals, constraints, and decisions already made.
3. Ask Claude to review completeness, internal consistency, feasibility, missed edge cases, risk, and unnecessary complexity.
4. Read Claude's `output_file` and critically assess every finding.
5. Accept valid findings, reject invalid findings with evidence, and surface user decisions when needed.
6. Update the actual PRD.
7. Write a follow-up round through the same Claude review session and have Claude read the updated PRD.
8. Repeat until Claude has seen the final PRD and reports no remaining material findings.

Re-review is mandatory after any change to scope, logic, architecture, risks, or acceptance criteria. Skip it only for wording or formatting changes that cannot alter meaning.

## Phase 6: User Approval and Finalization

1. Present the final PRD with Claude's final verdict, notable findings resolved, rejected findings, trade-offs, and remaining open questions.
2. Wait for explicit user approval.
3. If the user requests a material change, update the PRD and repeat the Claude review loop.
4. Set the status to `Ready` only after explicit approval.

Keep the Claude review session artifacts. Do not run cleanup unless the user asks.
