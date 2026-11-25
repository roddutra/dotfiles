# Modelling application state machines in TLA+

## Contents

- [What to model](#what-to-model)
- [Mapping code to TLA+](#mapping-code-to-tla)
- [Skeleton](#skeleton)
- [Properties](#properties)
- [Keeping the model small](#keeping-the-model-small)
- [Syntax traps](#syntax-traps)
- [Running TLC](#running-tlc)
- [Triage](#triage)
- [Trusting a pass](#trusting-a-pass)
- [Conformance](#conformance)

## What to model

The bugs TLC finds in application code come from the environment, not from the transition table. Model the things the code's author did not picture happening together:

- Two requests for the same entity at once.
- A webhook, job or timer firing while a user acts.
- The same event delivered twice, or two events in the wrong order.
- A retry after the first attempt half finished.
- A failure between two writes that belong together.

Model one slice: one entity and the handlers that write it. Leave out anything no rule depends on. Add a variable only when a rule or a guard reads it, because each one multiplies the state space.

Write TLA+ directly, not PlusCal. One guarded action per handler step maps onto request handlers better than sequential pseudocode does.

## Mapping code to TLA+

| In the code | In the spec |
| --- | --- |
| Status column or enum | A variable ranging over a set of strings |
| Nullable timestamp or foreign key | A `BOOLEAN` (set or not). Model the value only if a guard compares it. |
| Group of flags | One variable per flag, so contradictory combinations stay representable |
| Counter, balance, attempts | A natural number bounded by a `CONSTRAINT` in the cfg |
| Handler that reads, then writes with no lock or transaction | Two actions: one copies the state into a per-request variable, the next decides on that copy and writes |
| Save that writes the whole loaded object back (most ORMs' `save()` without dirty tracking) | Keep the row as one record and a record copy per request, and write `row' = [seen[r] EXCEPT !.status = "paid"]`. Field-by-field assignment models a column-level update and misses stale saves that erase another handler's fields. |
| Handler inside a transaction with a row lock, or one conditional `UPDATE ... WHERE` | One atomic action that guards on the live state |
| Concurrent requests | A `CONSTANT` set of model values, with `\E r \in Requests` in `Next` |
| Queue or webhook delivery | A set of pending messages (unordered, redelivery possible). Use a sequence only when the transport guarantees order. |
| Retry or repeat delivery | Let a finished request return to `idle` so it can run any handler again, and bound the repeats with counters. Drop the "every request finishes" liveness rule in that model. |
| External side effect (charge, email, refund) | A counter the action increments, so a rule can say "at most once" |
| Crash or timeout between two writes | Split the writes into two actions and add an action that abandons the request between them |

Granularity is the decision that matters most. An action is atomic: TLC never interleaves anything inside it. Merging a read and a write that the code does separately hides exactly the race the model exists to find. Splitting what the database does atomically reports races that cannot happen. Check each handler for a transaction, a lock or a conditional write before choosing.

Each action may read only what its real counterpart can see at that moment. A handler holding a stale copy must decide on the copy, not on the live variable.

## Skeleton

Checked with TLC: `CancelledNeverPaid` fails in five states, with both requests reading `pending` before either writes.

```tla
---- MODULE OrderLifecycle ----
\* Source: app/Orders/PaymentWebhook.php:41-58, app/Orders/CancelOrder.php:22-35 at <commit>
\* Models the code as it is. Each handler reads status, then writes in a later step,
\* because the code does both outside a transaction or row lock.
EXTENDS Naturals

CONSTANTS Requests   \* concurrent handler invocations, model values

VARIABLES
    status,   \* orders.status
    paidAt,   \* orders.paid_at IS NOT NULL
    pc,       \* where each request is
    seen      \* status each request read before it writes

vars == <<status, paidAt, pc, seen>>

States == {"pending", "paid", "cancelled"}

TypeOK ==
    /\ status \in States
    /\ paidAt \in BOOLEAN
    /\ pc \in [Requests -> {"idle", "pay_read", "cancel_read", "done"}]
    /\ seen \in [Requests -> States]

Init ==
    /\ status = "pending"
    /\ paidAt = FALSE
    /\ pc = [r \in Requests |-> "idle"]
    /\ seen = [r \in Requests |-> "pending"]

\* PaymentWebhook.php:41 loads the order
PayRead(r) ==
    /\ pc[r] = "idle"
    /\ seen' = [seen EXCEPT ![r] = status]
    /\ pc' = [pc EXCEPT ![r] = "pay_read"]
    /\ UNCHANGED <<status, paidAt>>

\* PaymentWebhook.php:47-52 guards on the value it loaded, then saves
PayWrite(r) ==
    /\ pc[r] = "pay_read"
    /\ IF seen[r] = "pending"
          THEN status' = "paid" /\ paidAt' = TRUE
          ELSE UNCHANGED <<status, paidAt>>
    /\ pc' = [pc EXCEPT ![r] = "done"]
    /\ UNCHANGED seen

\* CancelOrder.php:22 loads the order
CancelRead(r) ==
    /\ pc[r] = "idle"
    /\ seen' = [seen EXCEPT ![r] = status]
    /\ pc' = [pc EXCEPT ![r] = "cancel_read"]
    /\ UNCHANGED <<status, paidAt>>

\* CancelOrder.php:27-31
CancelWrite(r) ==
    /\ pc[r] = "cancel_read"
    /\ IF seen[r] = "pending"
          THEN status' = "cancelled"
          ELSE UNCHANGED status
    /\ pc' = [pc EXCEPT ![r] = "done"]
    /\ UNCHANGED <<paidAt, seen>>

Next ==
    \E r \in Requests :
        PayRead(r) \/ PayWrite(r) \/ CancelRead(r) \/ CancelWrite(r)

Spec == Init /\ [][Next]_vars /\ WF_vars(Next)

\* Rule (docs/refunds.md:12): a cancelled order was never charged.
CancelledNeverPaid == status = "cancelled" => ~paidAt

\* Rule (tests/OrderTest.php:88): a paid order stays paid.
PaidIsFinal == [][status = "paid" => status' = "paid"]_vars

\* Rule (docs/refunds.md:14): a cancelled order stays cancelled.
CancelledIsFinal == [][status = "cancelled" => status' = "cancelled"]_vars

\* Every request finishes.
AllDone == <>(\A r \in Requests : pc[r] = "done")
====
```

`OrderLifecycle.cfg`:

```
SPECIFICATION Spec
CONSTANTS
    Requests = {r1, r2}
INVARIANTS
    TypeOK
    CancelledNeverPaid
PROPERTIES
    PaidIsFinal
    CancelledIsFinal
    AllDone
CHECK_DEADLOCK FALSE
```

`PaidIsFinal` fails on the same interleaving. `CancelledIsFinal` fails on the mirror image, where the stale payment write lands last and the order ends up `paid`: no state invariant here catches that one, because the final state looks healthy. A model only finds what its rules say. To model the fix, change the write guards from `seen[r]` to the live `status`, which is what a conditional update does. All five checks then pass.

The skeleton writes fields one at a time and runs each request once. Check both against the code: see the whole-object save and repeat delivery rows above.

## Properties

- **`TypeOK`** names every variable and the values it may hold, nothing more. It catches spec typos early. Correctness rules go in their own invariants.
- **State invariants** relate fields in one state: `status = "cancelled" => ~paidAt`, `refunds <= 1`. List them under `INVARIANTS`.
- **Action properties** forbid a step: `[][status = "paid" => status' = "paid"]_vars`. List them under `PROPERTIES`. A state invariant on a single status variable cannot reject an illegal step, because every value is already in the type set. Use an action property for those rules.
- **Liveness** says something eventually happens: `<>(done)`, or `P ~> Q` for "every P leads to Q". It needs fairness in `Spec` (`WF_vars(Next)` or weak fairness per action), or stuttering forever is a valid counterexample. Strong fairness on a combined action does not give fairness to each of its parts.
- **Deadlock** means no action is enabled. A machine with terminal states deadlocks by design, so set `CHECK_DEADLOCK FALSE` and state the rule you care about as liveness: every request finishes, no order stays `processing` forever.

Each rule cites its evidence in a comment. Prefer rules about what the user or the business would notice over rules that restate one function.

A rule that reads a field a stale write can erase passes when it should fail: "a cancelled order never ships" holds trivially once a stale save has wiped `shipped_at`. State "never X after Y" rules over a side-effect counter the handlers only ever increment, or as an action property.

## Keeping the model small

- Two concurrent requests find nearly every interleaving bug. Use three only when a rule involves three parties.
- One entity. Two when a rule relates them.
- Bound counters in the cfg with `CONSTRAINT`, naming an operator defined in the spec, so the spec stays readable.
- Check liveness in a second cfg with smaller constants when the first run is slow.
- A run that will not finish: `tlc.sh <Spec.tla> --simulate 10000` explores random behaviours. Report it as simulation, not as a proof.

An unguarded writer, such as an admin bulk update, gives the shortest counterexample for most rules and hides the races behind it. Add a constant set of enabled handlers (`Kinds = {"pay", "cancel", "ship"}` in the cfg, a string set is allowed) and guard each action on membership. Run once with every handler and once with only the guarded ones, and report which rules break in each. A run with a single request does the same for concurrency: a rule that breaks there needs no race, only the wrong sequence of calls.

## Syntax traps

Model-written TLA+ fails in the same places:

- ASCII operators only: `/\`, `\/`, `\in`, `|->`, `=>`, `~`, `#` or `/=` for not-equal. No Unicode symbols, no `!=`, no `&&`.
- `==` defines, `=` compares. `x' = v` assigns the next value.
- No semicolons, no `end`. The module opens with `---- MODULE Name ----`, closes with `====`, and `Name` matches the file name.
- Every action says what happens to every variable: each is primed or listed in `UNCHANGED`. TLC stops with "successor state is not completely specified" when one is missing.
- `IF` always has an `ELSE`.
- Indentation of `/\` and `\/` lists is significant. Align the bullets.
- A set holds one kind of value. Do not mix strings and numbers.
- Update functions and records with `[f EXCEPT ![k] = v]`.
- Comments are `\*` to the end of the line, or `(* ... *)`.
- The cfg takes names, not expressions: define an operator in the spec and name it. Write model values as bare identifiers (`{r1, r2}`). String and number constants are allowed too, negative numbers are not.

## Running TLC

```sh
<skill-dir>/scripts/tlc.sh <Spec.tla>                      # uses <Spec>.cfg beside the spec
<skill-dir>/scripts/tlc.sh <Spec.tla> --each               # every rule on its own, one verdict and trace each
<skill-dir>/scripts/tlc.sh <Spec.tla> --only RuleName      # one rule from the cfg
<skill-dir>/scripts/tlc.sh <Spec.tla> --config Other.cfg
<skill-dir>/scripts/tlc.sh <Spec.tla> --simulate 10000
<skill-dir>/scripts/tlc.sh <Spec.tla> -- -coverage 1       # extra TLC flags after --
```

The script parses with SANY, runs TLC with all cores, keeps TLC's working files out of the repository and ends with one line: `RESULT: <verdict> (exit <n>)`. The first run downloads a pinned, checksum-verified `tla2tools.jar` to the user cache.

| Verdict | Exit | Meaning |
| --- | --- | --- |
| `pass` | 0 | Every reachable state checked, nothing violated |
| `pass-simulation-only` | 0 | Random behaviours only, not exhaustive |
| `assumption-failed` | 10 | An `ASSUME` is false for these constants |
| `deadlock` | 11 | A state with no enabled action |
| `invariant-violation` | 12 | A state breaks an invariant |
| `property-violation` | 13 | An action property or a liveness property fails |
| `parse-error` | 150 | SANY rejected the spec |
| `config-error` | 151 | The cfg names something the spec lacks |
| `not-run` | 2 | No Java, no spec or no cfg |

`--each` ends with a summary of verdicts and exits 0 when every rule holds, 1 otherwise. Use it once the model parses: TLC alone stops at the first broken rule, and a report needs the shortest trace for each.

A counterexample is a numbered list of states. Each names the action that produced it and gives every variable's value. Read down it for the first step the code's author did not expect. `-- -difftrace` shortens the middle states to the variables that changed.

Keep extra cfg files and planted-bug copies outside the repository.

## Triage

Every non-pass result is one of three things. Decide which before touching anything.

1. **The model is wrong.** A step in the trace cannot happen in the code: the real handler holds a lock, or a guard was left out. Fix the model and cite the line that proves it.
2. **The code is wrong.** Every step maps to a cited line. This is a finding. Keep the trace, translate it into entry points ("request A loads the order, request B cancels it, A saves") and report it.
3. **The rule is wrong.** The code deliberately allows the state. Change the rule only with evidence, and say so in the report. Ask the user when the evidence is thin.

Expect most early failures to be model errors. Parse errors and config errors are spec repairs: fix and rerun.

Editing a rule or a guard because it is the fastest way to a pass hides the defect the model was written to find.

## Trusting a pass

A pass is only as good as the model. Do this for every rule that holds, including when other rules fail:

- **Look at the state count.** A handful of states means the model is over-constrained or an action never fires.
- **Check coverage** with `-- -coverage 1`. An action with a zero count is never enabled, so its guard is wrong or `Init` is too narrow. Actions built from one shared helper report as one line, so check those through the actions that depend on them.
- **Plant a bug** in a copy of the spec: remove a guard or merge two states, and confirm the rule fails. The module name must match the file name, so give each copy its own directory. If nothing fails, the rule is too weak.
- **Check the invariants could fail.** At least one besides `TypeOK` must be false in some state the types allow.

## Conformance

A model that does not match the code proves nothing about the code.

- Every action cites the `path:line` it models, and the header names the commit.
- Every transition write found in the audit has an action. An action with no cited source comes out.
- `Init` holds every state the code can create the holder in.
- Review the spec against the cited files by trying to refute three claims: each action has the same guard as its code, each transition write has an action, and the read and write granularity matches the locking the code does. Hand this to a fresh subagent when one is available, since the author of a spec reads it charitably.
- A counterexample becomes a confirmed defect when a script drives the real code through the same steps using public entry points only. To hold a handler between its read and its write, hook a collaborator it calls in between (the mailer, the payment client, the store's save) and run the other handler from the hook. Use two threads with events when the steps interleave without nesting. Do not preload an invalid state or call private functions to force it.

Mark a spec that never reached `pass` or a real violation with a first line `\* UNCHECKED: <reason>`.
