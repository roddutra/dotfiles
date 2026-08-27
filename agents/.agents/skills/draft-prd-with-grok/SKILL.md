---
name: draft-prd-with-grok
description: "Draft a new PRD from the user's requirements. Full workflow: deeply interrogate the problem and the why behind it, challenge weak or unconsidered areas, brainstorm solutions (with Grok when the problem is complex or unclear), present options with pros/cons and a recommendation, then draft the PRD and iterate with a fresh Grok review until no findings remain. On user approval, set the PRD status to Ready. Use when the user wants to create a PRD with Grok as the brainstorming partner and reviewer."
---

# Draft-PRD: Think It Through, Then Write It

End-to-end workflow: build a deep, shared understanding of the problem and the desired outcome, pressure-test the thinking, converge on the right solution (brainstorming with Grok when needed), then draft a PRD and harden it through Grok review.

## Phase 1: Understand the Problem and the Why

Extract enough from the user that you have a deep understanding before proposing anything. Interview them on:

- The problem itself, and the **why** behind it — what outcome they're really after, who it's for, what success looks like.
- The intended business logic, rules, and constraints.
- Nuance and edge cases, including failure modes and unhappy paths.
- The desired output and acceptance criteria.

Resolve what you can by exploring the codebase, existing docs, and any references the user provides — don't ask what the code or context already answers. Keep interviewing until the gaps that matter are filled.

## Phase 2: Challenge and Think It Through

Do not be a passive scribe. Help the user reach clarity before any implementation is decided:

- Challenge anything that doesn't seem well thought out, contradicts itself, or rests on an unstated assumption.
- Surface areas the user hasn't considered — edge cases, second-order effects, scope creep, simpler framings of the problem.
- Push on the why until the goal and its trade-offs are clear. If the problem itself is fuzzy, fix that before discussing solutions.

## Phase 3: Solutions and Recommendation

1. **If the best solution is complex or unclear, brainstorm with Grok first.** Load the `grok-reviewer` skill (if available) and use it to brainstorm approaches before presenting options to the user — follow its file access, session, and prompt rules, and give Grok the problem, the why, constraints, and which project files to read for context. For straightforward problems with an obvious approach, skip this.
2. Present the viable solution options to the user, each with its pros and cons, and give a clear recommendation with reasoning.
3. If a decision is needed, wait for the user to choose. If the path is unambiguous, confirm the recommendation with the user before drafting.

## Phase 4: Draft the PRD

1. Draft the PRD file capturing: problem statement and the why, goals, scope and out-of-scope, the chosen solution and key design decisions/trade-offs, business logic and rules, edge cases, desired output and acceptance criteria, and any risks.
2. Do not include estimated timelines (hours/days/weeks) unless the user explicitly asks for them.
3. Set the PRD's status to `Draft` (or equivalent) — not `Ready` yet.

## Phase 5: Grok Review — Iterate Until Clean

1. Start a **fresh** Grok review session and use the `grok-reviewer` skill (if available) to review the drafted PRD. Tell Grok which project files to read for codebase context, and provide the problem, the why, constraints, and decisions already made. Review focus: completeness, internal consistency, feasibility, missed edge cases, gaps, risks, over-engineering.
2. Critically assess Grok's findings — accept, reject with reasoning, or flag for discussion.
3. Update the PRD based on accepted findings, then send the updated PRD back to Grok for re-review (mandatory — never assume your edits are correct; a round is complete only when Grok has seen the final state).
4. Repeat until Grok reports no remaining findings.

## Phase 6: Approval and Finalize

1. Present the finalized PRD to the user with a summary of what Grok reviewed and any notable trade-offs resolved, plus any open questions.
2. On explicit user approval, set the PRD's status to `Ready`. If the user requests changes, update the PRD and re-run Grok review for any non-editorial change (scope, logic, architecture, risks); skip re-review only for wording fixes.
