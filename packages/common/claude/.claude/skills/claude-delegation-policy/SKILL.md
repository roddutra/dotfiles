---
name: claude-delegation-policy
disable-model-invocation: true
description: "Turns the session model into an orchestrator that delegates almost all work to subagents, choosing the cheapest model tier that can do each job well. User-invoked only, via /claude-delegation-policy. Accepts override arguments that remap the tiers, e.g. 'use sonnet as the default worker and haiku as the low-stakes worker'."
---

# Delegation Policy

The session model (Fable) is the orchestrator, not the worker. Fable is the most expensive tier. Spend its tokens only on decomposition, judgment calls, synthesis, and talking to the user. Everything else goes to subagents through the Agent tool, on the cheapest tier that can do the job well.

## Tiers

| Tier | Default | Use for |
| --- | --- | --- |
| Orchestrator | Fable (the session) | Decomposition, briefs, judgment, synthesis, user communication |
| Worker | `model: "opus"` | Anything needing real judgment: implementation, debugging, architecture-aware exploration, adversarial review |
| Low-stakes | `model: "sonnet"` | Mechanical work: running tests and reporting output, greps with a known target, rote refactors from an exact spec, formatting, screenshot capture, admin chores |

If getting it slightly wrong is cheap to catch, use the low-stakes tier.

The Agent tool takes `model` per call but not effort. Effort comes from the subagent definition's `effort` frontmatter or the session setting, so pick the tier by model only.

## Overrides

Arguments passed with the skill remap tiers for the rest of the session. Parse phrases such as "use X as the default worker", "use Y as the low-stakes worker", or "worker=X low-stakes=Y". Accepted model values are those the Agent tool accepts: `fable`, `opus`, `sonnet`, `haiku`. Confirm the active mapping in one line, then apply it everywhere below in place of the defaults. Without arguments, use the defaults.

## Routing

- **Exploration and research:** never read broadly yourself. Spawn `Explore` agents on the worker tier with tightly scoped questions and consume their synthesized reports, not raw files. Trivial "find the file that defines X" lookups go to the low-stakes tier.
- **Implementation:** for any multi-file change, spawn `general-purpose` agents on the worker tier with exact file paths, the relevant project doctrine, and a definition of done (tests to run). Independent changes get parallel agents in one message.
- **Verification and review:** adversarial review and blast-radius checks go to the worker tier. Plain test runs and lint passes go to the low-stakes tier.
- **Direct edits:** the orchestrator edits only when the change is small (one or two files at already-known locations).

## Tripwire

Before the first Edit or Write, count the files the change will touch. Three or more, or any screenshot or browser-proof chore: stop and spawn agents instead. Inline orchestrator work is only sequential diagnosis (each command depends on the previous answer) and one or two file edits.

## Token Rules

- Batch independent agent launches in a single message so they run concurrently.
- Give agents file paths and constraints up front so they do not rediscover project instructions. Paste the relevant doctrine into the prompt.
- Never re-read files an agent already summarized. Trust the report and spot-check only what you will edit.
- Read only the line ranges you need from large files.
- Do not echo file contents or long diffs back to the user. Report conclusions.
