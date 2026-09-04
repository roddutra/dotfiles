---
name: codex-delegation-policy
disable-model-invocation: true
description: "Turns the session model into an orchestrator that delegates almost all work to subagents, choosing the cheapest model tier that can do each job well. User-invoked only, via $codex-delegation-policy. Accepts override arguments that remap the tiers, e.g. 'use gpt-5.6-terra as the default worker and gpt-5.4-mini as the low-stakes worker'."
---

# Delegation Policy

The session model (GPT-5.6-Sol) is the orchestrator, not the worker. Sol is the most expensive tier. Spend its tokens only on decomposition, judgment calls, synthesis, and talking to the user. Everything else goes to subagents through `spawn_agent`, on the cheapest tier that can do the job well.

This skill is the user's explicit instruction to set the `model` field on `spawn_agent`. Do not fall back to inheriting the session model.

## Tiers

| Tier | Default | Use for |
| --- | --- | --- |
| Orchestrator | GPT-5.6-Sol (the session) | Decomposition, briefs, judgment, synthesis, user communication |
| Worker | `model: "gpt-5.6-terra"` | Anything needing real judgment: implementation, debugging, architecture-aware exploration, adversarial review |
| Low-stakes | `model: "gpt-5.6-luna"` | Mechanical work: running tests and reporting output, greps with a known target, rote refactors from an exact spec, formatting, screenshot capture, admin chores |

If getting it slightly wrong is cheap to catch, use the low-stakes tier.

## Overrides

Arguments passed with the skill remap tiers for the rest of the session. Parse phrases such as "use X as the default worker", "use Y as the low-stakes worker", or "worker=X low-stakes=Y". Accept any model slug the `spawn_agent` tool lists as available (for example `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`, `gpt-5.4-mini`); short names such as "terra" or "luna" map to their `gpt-5.6-` slug. Confirm the active mapping in one line, then apply it everywhere below in place of the defaults. Without arguments, use the defaults.

## Spawning

- `spawn_agent` with `task_name`, `message`, `model`, and an `agent_type` (`explorer`, `worker`, or `reviewer`). Leave `fork_context` off so the agent starts from the brief only.
- Set `reasoning_effort` per task: `high` for worker-tier judgment work, `medium` or `low` for low-stakes chores.
- Collect results with `wait_agent`, then `close_agent`. Completed agents count toward the concurrency limit until closed.
- Use `send_input` to continue an agent only when the follow-up depends heavily on that agent's context.
- If the `spawn_agent` schema shows no `model` or `reasoning_effort` field, the harness is hiding them (`hide_spawn_agent_metadata` under `[features.multi_agent_v2]`). Pass them anyway; the handler still applies them. As a fallback, `agents.default_subagent_model` and `agents.default_subagent_reasoning_effort` in `config.toml` set session-wide defaults.

## Routing

- **Exploration and research:** never read broadly yourself. Spawn `explorer` agents on the worker tier with tightly scoped questions and consume their synthesized reports, not raw files. Trivial "find the file that defines X" lookups go to the low-stakes tier.
- **Implementation:** for any multi-file change, spawn `worker` agents on the worker tier with exact file paths, the relevant project doctrine, and a definition of done (tests to run). Independent changes get parallel agents spawned in one turn.
- **Verification and review:** adversarial review and blast-radius checks go to `reviewer` agents on the worker tier. Plain test runs and lint passes go to the low-stakes tier.
- **Direct edits:** the orchestrator edits only when the change is small (one or two files at already-known locations).

## Tripwire

Before the first `apply_patch`, count the files the change will touch. Three or more, or any screenshot or browser-proof chore: stop and spawn agents instead. Inline orchestrator work is only sequential diagnosis (each command depends on the previous answer) and one or two file edits.

## Token Rules

- Spawn independent agents in a single turn so they run concurrently.
- Give agents file paths and constraints up front so they do not rediscover project instructions. Paste the relevant doctrine into the brief.
- Never re-read files an agent already summarized. Trust the report and spot-check only what you will edit.
- Read only the line ranges you need from large files.
- Do not echo file contents or long diffs back to the user. Report conclusions.
