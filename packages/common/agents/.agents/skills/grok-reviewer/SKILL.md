---
name: grok-reviewer
description: "Runs the xAI Grok CLI as an independent reviewer for PRDs, plans, code, architecture, or any artifact where a second opinion from a different model adds value. MUST load EVERY TIME the user wants Grok to act on something — review, brainstorm, sanity check, second opinion. Triggers on phrasing like 'have Grok review X', 'ask Grok', 'bounce this off Grok'. Bare mentions with no action intent ('Grok is slow') do not trigger."
---

# Grok Reviewer

Use the xAI Grok CLI (`grok`) as an independent reviewer — a separate AI agent whose feedback is genuinely independent from yours.

## When to Use

- **PRD** — gaps, ambiguity, missing edge cases, flawed assumptions
- **Implementation plan** — feasibility, ordering, missed dependencies, over-engineering
- **Code changes** — bugs, security, performance, design concerns
- **Architecture decisions** — trade-offs, missed alternatives
- **Any artifact** where a second perspective adds value

## Never Run `grok` Yourself

Do not invoke the `grok` binary from the shell — not `grok -p`, `grok --prompt-file`, `grok --resume`, not "just to check something". The **only** sanctioned interface is the scripts in this skill's `scripts/` directory. They are what enforce the read-only policy, session/round bookkeeping, timeouts and output capture; a raw call bypasses all of it and desynchronises the session state. If a script cannot do what you need, tell the user — do not work around it with a direct CLI call.

## Safety: Read-Only Only

The Grok process must NEVER modify files or change state. The wrapper hardcodes the following and none of it can be overridden:

- `--disallowed-tools` — strips every built-in tool except shell, `read_file`, `list_dir`, `grep` and subagents (no edit tools, schedulers, image/video generation, workflows). Grok may fan a large review out to its own subagents; they inherit the sandbox, deny rules and tool restrictions.
- `--deny MCPTool` — no MCP tool calls.
- `--deny Edit --deny Write` only when the kernel sandbox is unavailable: Grok applies these class rules to `spawn_subagent` too, so in that fallback subagents are disabled (`--no-subagents`) and the shell edit classifier (`touch`, `sed -i`, `> file` redirects…) is the write barrier instead.
- A `--deny Bash(...)` list covering git mutators, `ssh`/`scp`/`rsync`, package managers, interpreters (`python -c "open(..., 'w')"` bypasses the classifier), and process/filesystem mutators. Read-only git (`log`, `diff`, `status`, `show`, `blame`) still works.
- `--permission-mode auto` — a blocked call fails and is reported to Grok so the turn continues (`dontAsk` cancels the whole turn on the first non-read-only shell command).
- `--sandbox read-only` (kernel-enforced writes) whenever it can start. The wrapper screens known-invalid hook layouts, then treats Grok startup as the authoritative probe. If Grok rejects the profile before creating its session—for example, because a runtime socket deny path cannot be resolved—the wrapper automatically persists the policy-enforced fallback and retries the same UUID, prompt, round, and review directory. Invokers do not manage this fallback. `GROK_REVIEWER_SANDBOX=0|1` is a diagnostic override: it applies before a Grok session exists, and forcing `1` disables automatic downgrade.
- A `--rules` guardrail and `GROK_MEMORY=0` (no cross-session memory). Web search/fetch stay available so Grok can research while reviewing; shell `curl`/`wget` also work unless the kernel sandbox is active (it blocks child-process network on Linux).

Without the kernel sandbox this is policy-level enforcement, so always include "do NOT modify any files" in prompts as an additional safeguard. Never construct raw `grok` commands manually. A non-zero `denied_tool_calls` in the result means Grok tried something the policy blocked — the review is still valid.

**Reads are not restricted.** Unlike Codex's `--cd` jail, Grok can read any file on the machine regardless of `--cwd` or the `read-only` sandbox. The `.tmp/` copying convention below keeps review inputs alongside the project and matches the Codex skills; it is not a technical requirement.

Note: the wrapper scripts themselves perform small local setup — creating session files in `~/.grok-reviews/`, creating `.tmp/` in the project, and updating `.gitignore`. These are orchestration side effects, not Grok actions.

## Scripts

Located relative to this skill's directory. Determine the skill path at runtime.

### Step 1: Initialize a Session

```bash
python <skill-path>/scripts/init_session.py --title <review-title> [--project <name>] [--force-project <name>] [--model <name>] [--reasoning-effort <level>]
```

Returns JSON with `session` (the only value you need to track) and `project_dir` (informational).

**Normal path: inside a git repo, run only `init_session.py --title <title>`.** The project name is derived automatically from the repository, so **omit `--project`**.

**How the project name is derived (and why worktrees stay unified):** The name is the **main working tree's** directory basename (first entry of `git worktree list`), so a review started from a linked worktree (e.g. `tomobroker-prd025/`) groups under the main repo (`tomobroker`). Submodules resolve to the submodule's own name.

**`--project` vs `--force-project`:**

- **`--project <name>`** is **ignored inside a git work tree** (the script prints a note). It is **required only in a non-git directory**. A **bare repository is always rejected**.
- **`--force-project <name>`** overrides the git-derived name **anywhere**. Use it **only** for deliberate custom grouping (e.g. `tomobroker-frontend` / `tomobroker-backend`).
- If both are supplied, **`--force-project` wins**.

**Project name vs `project_dir`/`--cd`:** The project name affects **only** the grouping path `~/.grok-reviews/<project>/`. `project_dir` is resolved separately from the worktree's own root (`git rev-parse --show-toplevel`), persisted, and used as Grok's `--cwd` on every round (no need to pass `--cd`). The script creates `.tmp/` there and gitignores it. Pass `--cd <dir>` only to override.

**Model is set once, here, and locked — only if you pass `--model`.** With `--model <name>` (see `grok models`), the value is persisted and used on every round; start a fresh session to change it. Without it, each round uses whatever the local Grok CLI defaults to (`~/.grok/config.toml`).

**Reasoning effort is seeded here and may be adjusted per round.** `--reasoning-effort <level>` (`low`, `medium`, `high`, `xhigh`, `max`, ...; a model only accepts the levels it advertises) is persisted; `run_review.py --reasoning-effort` changes it later (see Step 3).

### Step 2: Write the Prompt File

Pipe prompt content via stdin using a heredoc:

```bash
cat <<'PROMPT' | python <skill-path>/scripts/write_prompt.py --session <session-path> [--force]
Your prompt content here...
PROMPT
```

Auto-increments the round number. Returns JSON with `prompt_path`, `output_path`, and `round`. Rejects overwrites and empty content.

**`--force`:** Skips the check requiring the previous round's output to exist. Use when the previous round was killed, timed out, or produced no output.

**Do not create prompt files manually with the Write tool.** Always use this script.

### Step 3: Run the Review

```bash
python <skill-path>/scripts/run_review.py --session <session-path> [--cd <project-dir>] [--timeout <seconds>] [--stall <seconds>] [--reasoning-effort <level>] [--keep-stream]
```

Auto-detects initial vs follow-up from session metadata:
- No `grok_session_id` → initial review: the script generates a UUID, persists it, and starts Grok with `--session-id`, so a killed round 1 resumes correctly (if Grok never created the session, the retry starts it fresh with the same id)
- Has `grok_session_id` → resume (`grok --resume <id>`), Grok keeps the prior rounds' context

Returns JSON with `session_id`, `prompt_file`, `output_file`, `stream_file` (raw `streaming-json` events — `null` on success unless `--keep-stream`/`GROK_REVIEWER_KEEP_STREAM=1`; kept automatically when a round fails, since it is the diagnostic for timeouts/stalls and ~100x the output size), `round`, `mode`, `stop_reason`, `denied_tool_calls`, `sandbox` (whether the kernel sandbox was active), `sandbox_source` (`auto`, `forced`, or `fallback`), and `sandbox_fallback` (whether this invocation automatically retried without the kernel sandbox). Success requires an `end` event with `stop_reason: end_turn`; anything else exits 3 (a `max_tokens` truncation keeps the partial output on disk).

**Stream file (`rN-stream.jsonl`):** while Grok works, the wrapper records the raw `streaming-json` event stream (every thought, tool call, and tool result) next to the round's files. It is typically 50-100x larger than the review itself and duplicates what Grok already persists under `~/.grok/sessions/<id>/`, so:

- **On success it is deleted** and the result reports `"stream_file": null`. Do not look for it.
- **On failure it is kept** (exit 2/3/4, early-ended turn, CLI error) — the error message names the path. Use it to diagnose: `tail` it for the last events, grep `"type":"tool_call"` to see what Grok was doing, `"type":"error"` for CLI errors, and the `end` event's `stopReason`. Do not read the whole file into your context — it can be megabytes.
- Pass `--keep-stream` (or set `GROK_REVIEWER_KEEP_STREAM=1`) only when the user asks to debug a successful round. Retained streams are removed by `cleanup_session.py` like any other round file.

**Wall-clock timeout (default 1800s / 30 min):** On timeout Grok is killed and the script exits 2. Override with `--timeout <seconds>`; `--timeout 0` disables.

**Stall watchdog (default 300s / 5 min):** Grok streams thought/text/tool events on stdout continuously, so 5 min of stdout silence (stderr does not count) means the model stream dropped. On stall the script exits 4. Override with `--stall <seconds>`; `--stall 0` disables.

**Reasoning-effort override (optional):** Pass `--reasoning-effort <level>` to use that value for the run; on success it is persisted so later rounds inherit it (failed runs do not persist). Omit to use the persisted value; if none, Grok uses its local default. The model is locked at init and not overridable here.

**When NOT to change `--reasoning-effort`:** Do not change it on your own initiative. Only when (a) the user tells you to, or (b) a round's output quality looks materially poor — then surface the suggestion and ask before passing the flag.

**Project directory:** `--cwd` is Grok's working directory (persisted at init as `project_dir`), used for relative paths and project discovery (AGENTS.md, skills, git). Prefer the repository root so relative paths in prompts are unambiguous. `init_session.py` derives the project name from git; outside a git repo pass `--project`.

**File paths in prompts:** Grok can read files anywhere, so absolute paths work. For consistency with the Codex skills and to keep review inputs with the project, copy files that live outside the repo (plan files, prior session artifacts) into `.tmp/` and reference them by root-relative path. `run_review.py` warns about absolute paths outside the project — it is a reminder, not an error. **Never inline file content into the prompt** — have Grok read files from disk.

**You MUST run this as a background task** using your harness's background mechanism (e.g. `run_in_background: true` on the Bash tool in Claude Code; the background-task feature in Grok or Codex). The script blocks while Grok works — running it in the foreground will hit the shell tool's timeout. If your harness has no background mechanism, run it in the foreground with the shell timeout raised to at least 40 minutes. After launching, **stop and wait** for the completion notification. See "Handling Long-Running Reviews".

### Step 4: Clean Up (User-Initiated Only)

```bash
python <skill-path>/scripts/cleanup_session.py --session <session-path>
```

Deletes all prompt, output, stream, and metadata files for the session, removes the session directory, and prunes empty parents.

**Never clean up unless the user explicitly asks you to.** Session files live in `~/.grok-reviews/` and are harmless to keep. Do not clean up after reaching consensus, after committing, after pushing, or after merging.

### Discovering Past Sessions

```bash
python <skill-path>/scripts/list_sessions.py [options]
```

Returns JSON with matching sessions, their metadata, and associated files (prompts, outputs, and any retained failure streams).

**Filter options (combinable):**

- `--project <name>` — auto-slugified to match the directory
- `--date today` / `--date yesterday` / `--date 2026-03-25`
- `--from 2026-03-01 --to 2026-03-25`
- `--week`
- `--month`

**When to use:** At the start of a new conversation when the user references a prior review, or when you need context from an earlier session on the same project. Read the returned prompt/output files to recover the review history.

### Handling Long-Running Reviews

`run_review.py` blocks until Grok finishes, then prints JSON. **It produces zero output while Grok is working.** Shell-tool timeouts (typically 2-10 minutes) are shorter than many reviews, so run in the background.

**Mandatory workflow:**

1. Run `run_review.py` as a background task.
2. The shell tool immediately returns a "running in the background" confirmation. **This is NOT the result.**
3. Tell the user the review is running and **end your turn** — zero tool calls after that message. Do not poll.
4. You will be **automatically notified** when the background task completes, with the script's JSON output or an error message.
5. **Only after the completion notification**, read the `output_file`.

**CRITICAL — do not run ANY shell commands to monitor the review.** No `while ! test -s`, no `ls`, no `cat`, no `tail -f`. No additional `run_review.py` calls for the same round. No raw `grok` commands.

**Interpreting background task results:**

- **JSON with `session_id` and `output_file`** → success. Read the `output_file`.
- **Exit code 1** → CLI error (non-zero Grok exit or an `error` event). The message is in the error output. A `no longer exists` error on round 2+ means the Grok session dir was deleted from `~/.grok/sessions/` — start a fresh session and carry context forward via `.tmp/` (a round-1 retry restarts automatically with the same id). Retry if the cause looks transient.
- **Exit code 2** → wall-clock timeout. **Re-run `run_review.py` with the same `--session`**; do NOT call `write_prompt.py` again. Repeated timeouts mean the scope is too large — split it into smaller rounds.
- **Exit code 3** → Grok exited cleanly but produced no review, or the turn ended early (`stop_reason` other than `end_turn`, e.g. `cancelled`, `max_turns`, `refusal` — partial text is discarded as intermediate narration, except `max_tokens`, where the truncated review is kept on disk). Re-run with the same `--session` first; only if that also fails, pipe a fresh prompt to `write_prompt.py --force` (this advances the round, it does not retry the current one) or start a fresh session (see "Empty Output").
- **Exit code 4** → stall. **Re-run `run_review.py` with the same `--session`**; do NOT call `write_prompt.py` again.
- **Exit code 128+signal (e.g. 137, 143)** → the Grok process was killed externally, not a Grok failure. Check with the user before retrying, then re-run with the same `--session`.
- **`<status>killed</status>` with empty output and no exit code** → the harness killed the task; see "Externally Killed Tasks".

**Retry mechanics in one rule:** when the error says "the round N prompt file is still on disk", just re-run `run_review.py` with the same `--session`. Only call `write_prompt.py --force` when the error explicitly says so.

**Sandbox startup is self-healing:** never create a second `-fallback` session, copy the prompt, or retry with `GROK_REVIEWER_SANDBOX=0` when the kernel sandbox cannot start. `run_review.py` automatically retries the same round in the same review directory with the policy-enforced read-only profile. If both attempts fail, report the final diagnostic; it includes the original sandbox startup error.

### Externally Killed Tasks

A `<status>killed</status>` notification with a completely empty output is not a Grok failure — every `run_review.py` failure path prints a diagnostic and a non-zero exit code, so zero output means the wrapper was killed before it could report. The usual cause is the harness reaping idle background tasks under memory pressure. (In Claude Code, `CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP=1` in the `env` block of `~/.claude/settings.json` disables it.)

**Recovery:** re-run `run_review.py` with the same `--session`. Do NOT call `write_prompt.py`. Kills arrive in bursts, so a second kill on the retry is expected and the third attempt usually succeeds.

### Empty Output

If Grok repeatedly exits 3 on a resumed session, carry the context into a fresh session:

1. **Leave the broken session in place** (no `cleanup_session.py`). It lives at `~/.grok-reviews/<project>/<date>/<HHMMSS-title>/`.
2. **Init a fresh session** with `init_session.py` for the same project.
3. **Copy the artifacts to carry forward into the new project's `.tmp/` using `cp`** — do NOT read them into your context first:
   ```bash
   cp ~/.grok-reviews/<project>/<date>/<HHMMSS-title>/r1-prompt.md <project_dir>/.tmp/prior-grok-r1-prompt.md
   cp ~/.grok-reviews/<project>/<date>/<HHMMSS-title>/r1-output.md <project_dir>/.tmp/prior-grok-r1-output.md
   ```
4. **Write a new initial-round prompt** telling Grok to read those `.tmp/` files from disk, then state the follow-up question. Do NOT inline their contents.
5. **Run `run_review.py`** on the fresh session (initial mode, since there is no `grok_session_id` yet).

## Critical Thinking — Do Not Follow Grok Blindly

Critically evaluate each finding before acting on it:

1. **Assess validity** — is this accurate given the full context, or is Grok misunderstanding something?
2. **Research if unsure** — read code, check docs, verify assumptions before deciding
3. **Push back when warranted** — note your objection with reasoning; communicate it in the follow-up so Grok can accept or counter-argue
4. **Use your judgment** — you have context Grok may not (user goals, codebase history, project constraints)

## Burden of Proof

Asking a reviewer to find problems rewards it for finding something whether or not a defect exists. The scripts counter that pressure by injecting a fixed review standard into every round, so the reviewer is held to it even if a prompt forgets to say so.

**Injected reviewer rules.** `run_review.py` passes it via `--rules` (system prompt) every round. You do not need to repeat these in your prompt, but your prompt must not contradict them (for example, do not ask for "all possible issues" or "a thorough list of concerns"). This is the text Grok receives, condensed:

```
REVIEW STANDARD (applies to every round):
- Report only what is wrong. Do not report things in order to have something to report. Zero findings is a correct and expected result when the artifact meets its goals.
- Every finding must cite (a) the exact requirement, goal, or invariant being violated and (b) the exact code or text that violates it, by file and line or quoted passage. If you cannot cite both, do not report it.
- Classify each finding as CONFIRMED DEFECT, AMBIGUOUS REQUIREMENT, or OPTIONAL IMPROVEMENT. Findings with no evidence are dropped, not listed.
- Give each finding a confidence (High, Medium, Low) and an impact (Blocking, Should fix, Nice to have). Blocking means the artifact fails its stated purpose, loses data, or is insecure. Style, naming, preferences, and hypothetical future requirements are never blocking.
- Propose a fix only for a CONFIRMED DEFECT.
- On follow-up rounds, re-check only what changed and whether prior findings are resolved. Do not widen scope to areas you already approved.
- End every response with a verdict line: APPROVE, APPROVE WITH NOTES, or CHANGES REQUIRED.
```

The prompt templates below add the output format that goes with these rules. Give Grok the goals and constraints it needs to judge "requirement violated" against; without them it has nothing to cite and will either report nothing or fall back to preferences.

**Invoker rules (how you use the output):**

- Only `CONFIRMED DEFECT` findings with `Blocking` or `Should fix` impact drive changes. Verify them yourself before acting; a cited line that does not say what the reviewer claims is a rejected finding.
- `AMBIGUOUS REQUIREMENT` findings are questions for the user, not code changes. Do not guess at a fix and send it back for another round.
- `OPTIONAL IMPROVEMENT` findings go in your report to the user as a list. Apply them only if they are trivial and clearly in scope. They never trigger a re-review on their own.
- Under `APPROVE WITH NOTES`, apply the notes and treat the review as complete. Re-review only if applying a note changed behaviour.
- Low-confidence findings are not actionable without your own independent verification.
- Watch the round count. If a round produces no confirmed defects, the loop is done regardless of how many optional items appear. If you are past round 3 and still receiving new `CONFIRMED DEFECT`s, stop and tell the user: either the artifact has real depth problems or the reviewer is generating work. Both are the user's call.

## Constructing the Review Prompt

### Context Bridging

Grok is a separate session with zero knowledge of your conversation with the user. Without context, it may produce recommendations that are technically valid but misaligned — e.g., heavy architecture when the user asked for a quick fix.

**Before every prompt, include relevant context:**

- User's goals and the problem being solved
- Constraints: scope, simplicity preferences, timeline, technical limitations
- Decisions already made that Grok should not re-litigate
- What's explicitly out of scope
- Direction: prototype, MVP, production, learning exercise

Skip context when the review is genuinely open-ended with no prior constraints.

### File Access Audit

Grok can read any path on the machine, so a wrong or external path is not fatal — but a **non-existent** path makes Grok review from assumptions. Before every prompt, verify each referenced file exists, prefer root-relative paths, and copy external inputs into `.tmp/` with `cp`/`mv` (do NOT read them into your context first — that wastes tokens and risks truncation).

**Never inline file content into the prompt.** Always have Grok read files from disk.

### Controlling Grok's Output

Grok's response enters your context window. Always tell Grok how to shape its output — scale to the task:

- **Large reviews**: "Be concise. 2-3 sentences per finding. Skip style and naming."
- **Focused reviews**: "Be thorough and detailed for this specific area."
- **Follow-ups**: "One sentence per point. Accept or reject my reasoning, then give a verdict."

### Prompt Template — Initial Review

Adapt this structure for each review type:

```
You are acting as an independent reviewer. Your job is to review the artifact below and provide your findings and recommendations.

IMPORTANT CONSTRAINTS:
- Do NOT modify any files. This is a read-only review.
- Do NOT create any files. Only provide your analysis as text output.
- Do NOT run any commands that modify state.

CONTEXT:
[What this artifact is, who created it, what problem it solves]

BACKGROUND AND GOALS:
[Relevant context from your conversation with the user:
- What the user is trying to achieve and why
- Constraints (e.g., "keep it simple", "short-term fix", "production-grade")
- Decisions already made that should not be re-litigated
- What is explicitly out of scope
If open-ended: "No specific constraints — review freely."]

ARTIFACT TO REVIEW:
[Instruct Grok to read specific files from disk. For files originally outside the project, tell Grok to read the copy in .tmp/. Never paste file contents here.]

REVIEW FOCUS:
[Specific areas to evaluate]
Your recommendations should be appropriate given the background and goals above.

OUTPUT INSTRUCTIONS:
[Scale to the task - see "Controlling Grok's Output" above]

Report only what is wrong. Finding nothing is a correct result when the artifact meets its goals; do not invent findings to fill the list. Style, naming and hypothetical future needs are not defects.

Provide your review in this format:

## Summary
2-3 sentences: does the artifact meet the goals above, and what is the single most important thing the author should know?

## Findings
Numbered. Omit anything you cannot back with evidence. For each:
- Violates: the exact requirement, goal or invariant (quote it)
- Evidence: file and line, or quoted text, showing the violation
- Class: CONFIRMED DEFECT | AMBIGUOUS REQUIREMENT | OPTIONAL IMPROVEMENT
- Confidence: High | Medium | Low
- Impact: Blocking | Should fix | Nice to have
- Fix: concrete change (CONFIRMED DEFECT only)

## Verdict
APPROVE | APPROVE WITH NOTES | CHANGES REQUIRED, with one sentence of justification. Use CHANGES REQUIRED only when a Blocking CONFIRMED DEFECT exists.

## What Works Well
Strong aspects to preserve. One line each.
```

### Prompt Template — Follow-Up Round (via Resume)

Grok already has context from the prior round. Focus on what changed and explain objections in detail.

```
I've reviewed your findings and critically assessed each one:

FINDINGS ACCEPTED — CHANGES MADE:
- [Finding #N]: [What you changed and why]

FINDINGS REJECTED — WITH REASONING:
- [Finding #N]: [Why you disagree — be specific, e.g., "This assumes X, but in our case Y applies because Z. The current approach is intentional because..."]

FINDINGS NEEDING DISCUSSION:
- [Finding #N]: [What you're unsure about — ask a specific question]

UPDATED ARTIFACT:
[Tell Grok which files to re-read from disk. Never paste file contents here.]

For each rejection: accept my reasoning, or show the evidence that it is wrong.
Re-check only the changed areas and whether each accepted finding is resolved. Report a new finding only if it meets the same burden of proof as round 1 (requirement violated, evidence, class, confidence, impact). Do not widen scope to areas you already approved.
End with a verdict: APPROVE, APPROVE WITH NOTES, or CHANGES REQUIRED.
Do NOT modify any files. Text output only.
Keep concise - one sentence per point.
```

### Review-Type Tips

- **PRD/Specs/Docs in the project**: Tell Grok to read from disk. Never paste project file contents into the prompt.
- **Code**: Tell Grok which files to read. For diffs, save the diff to a file in `.tmp/` and tell Grok to read it.
- **Plan/Architecture** (plan files stored outside the project, e.g. `~/.claude/plans/`): copy the plan file into `.tmp/`; recopy if it changes between rounds. Focus Grok on ordering, dependencies, risks, and simpler alternatives.

## The Review Loop

### Apply First, Then Re-Review

**Never ask Grok to pre-approve planned changes.** Apply accepted changes to the actual files, then resume the session so Grok reviews the real result. "I plan to do X — does that sound right?" produces a rubber stamp, not a review.

### Re-Review Is Mandatory — No Exceptions

**Every fix for a `CONFIRMED DEFECT` MUST go back to Grok for re-review.** This applies on round 1 and round 10. Implementations can introduce new bugs, miss edge cases, or misinterpret the finding's intent.

**Watch for discipline erosion across rounds.** "These are minor changes, surely they're fine" is the most common failure mode. One line can introduce a bug.

A review is complete when Grok has seen the final state and returned `APPROVE`, or returned `APPROVE WITH NOTES` and you have applied the notes. A fix for a `CONFIRMED DEFECT` always goes back for re-review before you present results. Optional improvements and ambiguous-requirement questions do not reopen the loop (see Burden of Proof).

### Workflow

1. **Draft** your artifact
2. **Init** — `init_session.py --title <title>` (omit `--project` inside a git repo). Store the returned `session` path.
3. **Write prompt** — pipe content to `write_prompt.py --session <s>`. Round auto-increments.
4. **Run review** — `run_review.py --session <s>` as a background task. Read `output_file` when done.
5. **Triage** each finding per Burden of Proof: verify confirmed defects yourself, route ambiguous requirements to the user, list optional improvements
6. **Apply changes** - fix verified confirmed defects in the actual files (and trivial in-scope notes)
7. **Re-review (mandatory)** — pipe follow-up prompt to `write_prompt.py --session <s>`, then `run_review.py --session <s>` (auto-resumes)
8. **Iterate** - repeat 5-7 until the verdict is `APPROVE`, or `APPROVE WITH NOTES` with notes applied. Past round 3 with new confirmed defects still arriving, stop and report to the user
9. **Do NOT clean up** — never run cleanup unless the user explicitly asks

### Presenting Results to the User

- **Summary** - what was reviewed, Grok's final verdict, round count
- **Findings accepted** — what you changed and why
- **Findings rejected** — your reasoning for each
- **Findings debated** — back-and-forth across rounds, final resolution
- **Optional improvements** - items the reviewer flagged as non-blocking that you did not apply
- **Open questions** - ambiguous requirements and unresolved items needing the user's input

Be transparent — don't silently incorporate or reject feedback. The user should see where you and Grok disagreed.
