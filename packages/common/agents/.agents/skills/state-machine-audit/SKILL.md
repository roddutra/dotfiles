---
name: state-machine-audit
description: "Finds the implicit state machines in a codebase (lifecycles hidden in status strings, boolean flags, nullable timestamps and scattered conditionals), proves which invalid states and races the code can reach, model-checks them with TLA+ and TLC, and refactors them into explicit state machines. MUST load when the user asks to find implicit or hidden state machines, audit state or lifecycle handling, write a TLA+ ('TLA') spec or model, formally verify or model-check a workflow, find impossible states, or make state explicit. MUST also load before running TLC or SANY on any .tla file, even one the user already wrote: it bundles the runner script and pinned tools, so never look for Java or tla2tools.jar by hand. Also load for bugs that smell like state: an entity stuck in a status, flags that contradict each other, a webhook, job or payment processed twice, a race between two handlers on one record, or 'this should never happen' states in orders, subscriptions, payments, jobs and UI flows."
---

# State Machine Audit

An implicit state machine is a lifecycle nobody wrote down. The states live in flags, timestamps and status strings spread across files, so the code can reach combinations nobody planned, such as a cancelled order that was charged.

This skill finds those machines, proves which bad states are reachable, and stops there unless the user asked for more.

## How far to go

| Stage | Runs when |
| --- | --- |
| Inventory and defect hunt (sections 1 to 5) | Always |
| TLA+ model check (section 6) | The user asks, or after they accept a recommendation from the report |
| Make explicit (section 7) | The user asks for the refactor |

Sections 1 to 6 never edit application code. They may add spec files and a report.

"Find all implicit state machines" means the inventory. "Then make a TLA model" or "verify it" adds section 6. "Make them explicit" or "fix them" adds section 7.

## 1. Scope

- Small repository: audit all of it.
- Large repository: ask which area matters, or take the areas that handle money, access and long-running work first. Say what was left out.
- With subagents available, give each a domain area and the brief from sections 2 to 4, read-only. Merge machines that two agents found from different ends: same holder, one machine.

Read the persistence schema first (migrations, models, ORM schema). Status columns, groups of booleans and nullable timestamps on one table are the densest signal. Then follow each into the code.

## 2. Find candidates

A candidate is a holder (a variable, a group of flags, a set of columns) with at least two transitions, where at least one is guarded by the current state.

Signals:

- A `status`, `state`, `phase` or `step` field compared in several files.
- Booleans on one entity that cannot all vary independently (`is_draft`, `is_published`, `is_archived`).
- Nullable timestamps used as state (`cancelled_at`, `verified_at`), and fields that only mean something in one state.
- The same question answered by different conditions in different places, such as two handlers that disagree about what "active" means.
- Async flows where two actors write one holder: webhooks, queued jobs, retries, timeouts, scheduled tasks, a double click.
- UI state held in separate variables (`isLoading`, `error`, `data`), wizard steps, connection and upload flows.
- Sentinel values, leases and "in progress" markers. Methods that only work when called in order.

Not candidates:

- Booleans that really are independent, such as preferences and feature flags.
- One-way lazy initialisation.
- Values derived from other state.

Code that already has a declared transition table or a state machine library is explicit. List it, and still search for writes that bypass the table.

## 3. Document each machine

- **Holder**: the fields that carry the state, each with `path:line`.
- **States**: the ones the code distinguishes, including combinations that have no name.
- **Initial states**: every state the code creates the holder in.
- **Transitions**: from, to, trigger, guard, side effects, `path:line`.
- **Intended rules**: what must always hold, each with its evidence.

Find every transition write. Search the whole repository for writes to the holder, including raw SQL, bulk updates, admin screens, console commands and other services. Writes outside the main path are where machines break. Constructor defaults, hydration from storage, migrations and test setup are not transitions.

Rules need evidence: a test, a validation rule, a comment, documentation, product copy, an issue or a commit message. A guard in the code is evidence of the rule it enforces. Mark a rule with no evidence as assumed. The audit cannot supply missing product rules, so ask the user what "completed" means when the code disagrees with itself.

## 4. Hunt defects

Check each machine for:

- **Contradictory combinations** the fields allow and the code can reach.
- **Skipped steps**: a write that reaches a state without passing its guard, often a bulk update or an admin path.
- **Stuck states**: a state with no exit, or an event the code ignores in some state.
- **Check-then-act races**: the code reads the state, decides, then writes later with no transaction, row lock or conditional update between them.
- **Duplicates and reordering**: a webhook delivered twice or out of order, a retry after a partial failure, a double submit.
- **Torn updates**: writes that belong together (status, timestamp, charge, email) with a failure point between them.
- **Unhandled values**: a `switch` or `match` missing a state, or a default branch that swallows one.

Verify every finding before reporting it. A request to find everything pulls towards over-reporting: independent booleans, unreachable states and transitions that are not in the code. Open the files and trace a path of real entry points to the bad state.

| Class | Meaning |
| --- | --- |
| Confirmed | Every step of the path is cited. Better still, a test or a model reproduces it. |
| Plausible | The path exists but depends on a condition not confirmed. Name the condition. |
| Rejected | Drop it. |

## 5. Report

Reply in the conversation by default. Write a file when the user asks for one or the inventory is too long to read in a reply: follow the repository's docs convention, else `docs/state-machines.md`.

Order findings by real risk (money, data loss, access, a user left stuck), not by count. Lead with the confirmed ones.

```markdown
# State machine audit: <scope>

## Summary
<machines found, confirmed defects, what was not audited>

## Findings
### 1. <defect in one line> (confirmed | plausible)
- Machine: <name>
- Path: <entry point> at `path:line`, then <entry point> at `path:line`
- Result: <the bad state and what the user or the business sees>
- Fix: <one line>

## Machines
### <Name>
- Holder: `path:line`
- States: ...
- Initial: ...
- Rules: <rule> (evidence: `path:line` | assumed)

| From | To | Trigger | Guard | Where |
| --- | --- | --- | --- | --- |

Recommendation: <make explicit | model-check first | leave as conditionals>, with the reason.

## Model check
<only when section 6 ran: spec path, scope and bounds, what the model leaves out>

| Rule | Evidence | Result | Shortest counterexample |
| --- | --- | --- | --- |
```

Give each machine a recommendation. A two-state toggle with one writer is fine as a conditional, and saying so is part of the audit.

## 6. Model check with TLA+

A model earns its cost when at least one holds:

- Two or more actors can write the holder concurrently.
- Several fields must agree with each other.
- Events can arrive twice, late or out of order.
- The machine guards money, access or data that cannot be rebuilt.

For one writer and one field, the transition table already shows every path, and a model would only restate it.

Read [references/tla-modelling.md](references/tla-modelling.md) before writing a spec. It has the mapping from code to TLA+, a checked skeleton, the syntax traps and how to read results.

The loop:

1. **Model the code as it is.** One action per cited transition, with the guard the code has, split wherever the code reads and writes in separate steps. A spec of how the code should behave finds nothing.
2. **Write the rules as invariants and properties before the first run**, from the evidence in section 3.
3. **Run it**: `<skill-dir>/scripts/tlc.sh <Spec.tla> --each` checks every rule on its own and gives each its shortest counterexample. Without `--each`, TLC stops at the first rule that breaks. It needs Java 11 or newer. If Java is missing, ask the user before installing anything.
4. **Triage every result three ways.** The model is wrong (fix the model, citing the code). The code is wrong (a finding: keep the trace). The rule is wrong (change it only with evidence).
5. **Distrust every rule that holds**, even when others fail. In a copy of the spec, break a guard on purpose and confirm the checker fails. A rule that survives a planted bug is checking nothing.
6. **Confirm against the code.** Translate each counterexample into real entry points and replay it on the real code with a throwaway script kept outside the repository. A replayed trace is a confirmed defect. A permanent test for it belongs to section 7, because it fails until the fix lands.

Never weaken an invariant, tighten a guard or narrow `Init` to get a pass. A counterexample stands unless a cited line contradicts it.

Put specs in the directory that already holds `.tla` files, else `specs/tla/`. Never overwrite an existing spec. Add each checked machine's spec path and result to the report.

## 7. Make explicit

Work on one machine at a time, highest risk first, from a clean working tree.

1. **Pin current behaviour with tests** before changing structure: each transition, each refused transition and each confirmed defect. Follow the repository's testing rules.
2. **Build the explicit shape** in the language the code already uses:
   - One state type: an enum, a discriminated union or a sum type. Data that exists in only one state lives inside that state's variant, so the invalid combination cannot be built.
   - One transition table.
   - One function that applies it. Every transition write goes through it.
3. **Close races where the state is stored**: a conditional update (`UPDATE ... WHERE status = :expected`), a row lock or a transaction around the read and the write. Add a database constraint for rules across columns where the database supports one.
4. **Keep the refactor and the fixes separate.** The refactor keeps stored values, public names and side effect order. A fix, or newly refusing a transition the code used to ignore, is a behaviour change: name it and get the user's agreement.
5. **Recheck.** Run the tests. When a spec exists, match its state and action names, model the fix, and run TLC again: the invariant that failed should now pass.

Add no dependency for this. Reach for a state machine library only when the machine has nested or parallel states, or when the repository already uses one.

To keep new ones out, offer a rule for the repository's agent instructions: when a feature has more than two modes, hold them in one explicit state value with named transitions.
