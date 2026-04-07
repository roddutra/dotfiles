---
name: codex-reviewer
description: "Runs the OpenAI Codex CLI as an independent reviewer for PRDs, plans, code, architecture, or any artifact where a second opinion from a different model adds value. MUST load EVERY TIME the user wants Codex to act on something — review, brainstorm, sanity check, second opinion. Triggers on phrasing like 'have Codex review X', 'ask Codex', 'bounce this off Codex'. Bare mentions with no action intent ('Codex is slow') do not trigger."
---

# Codex Reviewer

Use the OpenAI Codex CLI as an independent reviewer — a separate AI agent whose feedback is genuinely independent from yours.

## When to Use

- **PRD** — gaps, ambiguity, missing edge cases, flawed assumptions
- **Implementation plan** — feasibility, ordering, missed dependencies, over-engineering
- **Code changes** — bugs, security, performance, design concerns
- **Architecture decisions** — trade-offs, missed alternatives
- **Any artifact** where a second perspective adds value

## Safety: Read-Only Only

The Codex process is strictly **read-only** — it must NEVER modify files or change state. The wrapper scripts enforce this via `--sandbox read-only` at the code level, which cannot be overridden. Never construct raw `codex exec` commands manually. Always include "do NOT modify any files" in prompts as an additional safeguard.

Note: the wrapper scripts themselves perform small local setup — creating session files in `/tmp`, creating `.tmp/` in the project, and updating `.gitignore`. These are orchestration side effects, not Codex actions.

## Scripts

Located relative to this skill's directory. Determine the skill path at runtime.

### Step 1: Initialize a Session

```bash
python <skill-path>/scripts/init_session.py --project <project-name> --title <review-title>
```

Returns JSON with `session` (the only value you need to track) and `project_dir` (informational).

**How `project_dir` works:** `init_session.py` resolves the git root from cwd once and persists it in session metadata. All subsequent `run_review.py` calls read `project_dir` from that metadata — no need to pass `--cd`. The script also creates `.tmp/` at the git root and ensures it's in `.gitignore`. Pass `--cd <dir>` only to override the persisted value.

### Step 2: Write the Prompt File

Pipe prompt content via stdin using a heredoc:

```bash
cat <<'PROMPT' | python <skill-path>/scripts/write_prompt.py --session <session-path> [--force]
Your prompt content here...
PROMPT
```

Auto-increments the round number. Returns JSON with `prompt_path`, `output_path`, and `round`. Rejects overwrites and empty content.

**`--force`:** Skips the check requiring the previous round's output to exist. Use when the previous round was killed or timed out and produced no output file.

**Do not create prompt files manually with the Write tool.** Always use this script.

### Step 3: Run the Review

```bash
python <skill-path>/scripts/run_review.py --session <session-path> [--cd <project-dir>] [--timeout <seconds>]
```

Auto-detects initial vs follow-up based on session metadata:
- No `codex_session_id` → initial review (`codex exec`), `--cd` read from session metadata (set by `init_session.py`)
- Has `codex_session_id` → resume (`codex exec resume`), uses persisted `--cd`

Reads the current round from metadata to locate the correct files. Returns JSON with `session_id`, `prompt_file`, `output_file`, `round`, and `mode`.

**Timeout (opt-in):** No timeout by default — Codex can take as long as it needs. If the user asks you to set a timeout, pass `--timeout <seconds>` (e.g. `--timeout 1200` for 20 min). On timeout, the process is killed and the script exits with code 2. The session ID is preserved — you can resume with `--force`.

**Project directory and Codex file access:** The project directory **must be inside an initialized git repository** — Codex refuses to run otherwise. If the project directory is not a git repo, initialize one before running the review (`git init && git add -A && git commit -m "Initial commit"`).

The `--cd` directory is Codex's filesystem root — it cannot read anything outside it. This means Codex has NO access to `~/.claude/`, `/tmp/`, your home directory, or any path outside the `--cd` tree.

**Always choose the broadest useful `--cd`** so Codex can access the most files:

- **Monorepos:** Always use the **repository root** as `--cd`, not a subdirectory app. If the repo is at `/Users/you/project` and the app is at `apps/api/`, use `/Users/you/project` — this gives Codex access to PRDs in `apps/api/docs/`, shared configs at the root, and all other apps. Using `apps/api/` as `--cd` would cut off files outside that subtree.
- **Standard repos:** Use the git repository root.
- **Think about what Codex needs to read** — docs, specs, PRDs, source code, tests, configs. Pick the `--cd` that contains all of them. When in doubt, go broader (repo root), not narrower.

Before running, audit every file path in your prompt:

- **File is inside `--cd`** → Codex can read it. Tell it the path relative to `--cd`.
- **File is outside `--cd`** → Codex cannot read it. **Copy it** into `.tmp/` within the project so Codex can read the original file from disk. The `init_session.py` script already created `.tmp/` and added it to `.gitignore`. **Do NOT inline the content into the prompt** — you will truncate or summarize large files, losing critical context.

Never tell Codex to "read the file at [path]" if that path is outside `--cd` — the review will fail silently.

**You MUST set `run_in_background: true` on the Bash tool call.** This is not optional. The script blocks for 10-20+ minutes while Codex works — running it in the foreground will time out. After launching, **stop and wait** for the background completion notification before doing anything else. See "Handling Long-Running Reviews" below for the full lifecycle.

### Step 4: Clean Up (User-Initiated Only)

```bash
python <skill-path>/scripts/cleanup_session.py --session <session-path>
```

Deletes all prompt, output, and metadata files for the session, removes the session directory, and prunes empty parent directories.

**Never clean up unless the user explicitly asks you to.** Session files live in `/tmp` and are harmless to keep. Do not clean up after reaching consensus with Codex, after committing, after pushing, or after merging. The user may need to reference these files in a future conversation. Only run this script when the user directly instructs you to clean up.

### Discovering Past Sessions

```bash
python <skill-path>/scripts/list_sessions.py [options]
```

Returns JSON with matching sessions, their metadata, and associated files (prompts + outputs). Use this from a fresh conversation to find and reference prior review history.

**Filter options:**

- `--project <name>` — filter by project name (auto-slugified to match directory)
- `--date today` / `--date yesterday` / `--date 2026-03-25` — specific date
- `--from 2026-03-01 --to 2026-03-25` — date range
- `--week` — current week
- `--month` — current month

All filters are combinable (e.g., `--project my-app --week`).

**When to use:** At the start of a new conversation when the user references a prior review, or when you need context from an earlier session on the same project. Read the returned prompt/output files to recover the full review history.

### Handling Long-Running Reviews

Codex reviews take 10-20+ minutes. The `run_review.py` script blocks internally (`process.wait()`) until Codex finishes, then prints JSON with the results. **It produces zero output while Codex is working.** The Bash tool's 10-minute timeout is shorter than most reviews, so you must run in the background.

**Mandatory workflow:**

1. Run `run_review.py` with `run_in_background: true`.
2. The Bash tool immediately returns a confirmation like `"Running in the background (↓ to manage)"`. **This is NOT the result. The review has NOT completed.** Codex is still working.
3. Tell the user the review is running and **end your turn**. Your response must contain zero tool calls after the message to the user. Do not call Bash, Read, or any other tool. Do not "wait" by polling. Simply stop.
4. You will be **automatically notified** when the background task completes. The notification will contain the script's JSON output (`session_id`, `output_file`, etc.) or an error message. You do not need to do anything to receive this notification — it arrives on its own.
5. **Only after receiving the completion notification**, read the `output_file` with the Read tool.

**CRITICAL — do not run ANY Bash commands to monitor the review.** Patterns like `while ! test -s <output_file>; do sleep N; done`, `ls` on the output directory, `cat` on the output file, `tail -f`, or any other form of polling are strictly forbidden. The background notification system handles this automatically. Running poll loops wastes resources, can hit the Bash timeout, and produces truncated or partial results.

**Never do any of the following while waiting for a review:**

- Run ANY Bash command related to the review — no polling, no checking, no reading, no monitoring
- Interpret the "Running in the background" Bash confirmation as task completion — it is not
- Run additional `run_review.py` calls for the same round — this spawns duplicate Codex processes that pile up
- Run raw `codex exec` commands directly — always use the scripts
- Attempt to "debug" or re-run because you haven't seen a result yet — you simply haven't waited long enough

**Interpreting background task results:**

- **JSON output with `session_id` and `output_file`** → success. Read the `output_file`.
- **Exit code 2** → timeout. Codex hung and was killed after `--timeout` seconds. The session is recoverable.
- **Exit code 143 (SIGTERM) or 137 (SIGKILL)** → the process was killed externally (e.g., by the user or system), not a Codex failure. Check with the user before retrying.
- **Non-zero exit code with an error message from the script** → genuine failure. Report the error to the user.

**If a review is interrupted (timeout or kill):** the session is usually recoverable — the session ID is captured to metadata early. Use `write_prompt.py --force` to skip the missing-output check, then run `run_review.py` again — it auto-resumes if the session ID was captured. If not, it starts a fresh review.

## Critical Thinking — Do Not Follow Codex Blindly

Critically evaluate each finding before acting on it:

1. **Assess validity** — is this accurate given the full context, or is Codex misunderstanding something?
2. **Research if unsure** — read code, check docs, verify assumptions before deciding
3. **Push back when warranted** — note your objection with reasoning; communicate it in the follow-up so Codex can accept or counter-argue
4. **Use your judgment** — you have context Codex may not (user goals, codebase history, project constraints)

## Constructing the Review Prompt

### Context Bridging

Codex is a separate session with zero knowledge of your conversation with the user. Without context, it may produce recommendations that are technically valid but misaligned — e.g., recommending heavy architecture when the user explicitly asked for a quick fix.

**Before every prompt, include relevant context:**

- User's goals and the problem being solved
- Constraints: scope, simplicity preferences, timeline, technical limitations
- Decisions already made that Codex should not re-litigate
- What's explicitly out of scope
- Direction: prototype, MVP, production, learning exercise

Skip context when the review is genuinely open-ended with no prior constraints.

### File Access Audit (Mandatory)

**Do this BEFORE writing every prompt.** Codex can ONLY read files inside the `--cd` directory. It has zero access to anything else — no `~/.claude/`, no `/tmp/`, no other projects, no home directory. If your prompt tells Codex to read a file outside `--cd`, Codex will silently skip it and review based on assumptions instead of the actual artifact. This produces unreliable reviews that waste time.

**Never inline file content into the prompt.** Always have Codex read files from disk. Inlining is harmful — you will inevitably truncate or summarize the content, losing critical context. Codex reading the actual file gets the full, unmodified content.

**Checklist — run through this for every file reference in your prompt:**

1. List every file you want Codex to read or that you reference by path
2. For each file, answer: is this path physically inside the `--cd` directory?
3. If YES → tell Codex to read it at its path relative to `--cd`
4. If NO → copy it into `.tmp/` within the project (see below), then tell Codex to read it from `.tmp/`

**Common offenders that are NEVER inside `--cd`:**

- **Claude Code plans** (`~/.claude/plans/`) — copy into `.tmp/` within the project
- **Session/temp files** (`/tmp/codex-reviews/...`) — copy into `.tmp/` within the project
- **Files from other projects** — copy into `.tmp/` within the project

**Files that ARE typically inside `--cd` — do NOT inline these:**

- **PRDs, specs, and docs** in the project (e.g., `docs/`, `specs/`, `apps/*/docs/`) — tell Codex to read them from disk
- **Source code, tests, configs** — always read from disk
- **Any file committed to the repo** — always read from disk

**Never write "read the file at [path]" unless you have verified that path exists inside `--cd`.** Never inline content into the prompt — always ensure Codex reads files from disk, copying them into `.tmp/` within the project if they originate outside `--cd`.

### Controlling Codex's Output

Codex's response enters your context window. Always tell Codex how to shape its output — scale to the task:

- **Large reviews**: "Be concise. Numbered findings with severity. 2-3 sentences each. Skip minor stylistic issues."
- **Focused reviews**: "Be thorough and detailed for this specific area."
- **Follow-ups**: "One sentence per point. Accept or reject my reasoning."

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
[Instruct Codex to read specific files from disk. For files originally outside --cd, tell Codex to read the copy in .tmp/. Never paste file contents here.]

REVIEW FOCUS:
[Specific areas to evaluate]
Your recommendations should be appropriate given the background and goals above.

OUTPUT INSTRUCTIONS:
[Scale to the task — see "Controlling Codex's Output" above]

Provide your review in this format:

## Summary
A 2-3 sentence overall assessment.

## Findings
Numbered list. For each: what, why it matters, severity (Critical/Major/Minor/Suggestion).

## Recommendations
Specific, actionable.

## What Works Well
Strong aspects to preserve.
```

### Prompt Template — Follow-Up Round (via Resume)

Codex already has context from the prior round. Focus on what changed and explain objections in detail.

```
I've reviewed your findings and critically assessed each one:

FINDINGS ACCEPTED — CHANGES MADE:
- [Finding #N]: [What you changed and why]

FINDINGS REJECTED — WITH REASONING:
- [Finding #N]: [Why you disagree — be specific, e.g., "This assumes X, but in our case Y applies because Z. The current approach is intentional because..."]

FINDINGS NEEDING DISCUSSION:
- [Finding #N]: [What you're unsure about — ask a specific question]

UPDATED ARTIFACT:
[Tell Codex which files to re-read from disk. Never paste file contents here.]

For each rejection: accept my reasoning, or explain why it's flawed.
Review changes for: adequacy, new issues, remaining concerns.
Do NOT modify any files. Text output only.
Keep concise — one sentence per point.
```

### Review-Type Tips

- **PRD/Specs/Docs in the project**: Tell Codex to read from disk — these files are inside `--cd`. Never paste project file contents into the prompt.
- **Code**: Tell Codex which files to read. For diffs, save the diff to a file in `.tmp/` and tell Codex to read it. Use `--cd` for full codebase context.
- **Plan/Architecture** (from `~/.claude/plans/`): These are outside `--cd` — copy the plan file into `.tmp/` within the project so Codex can read the original. If the plan changes between rounds, recopy the updated file before the next review. Focus Codex on ordering, dependencies, risks, and simpler alternatives.

## The Review Loop

### Apply First, Then Re-Review

**Never ask Codex to pre-approve planned changes.** When Codex gives feedback:

1. Apply accepted changes to the actual files
2. Then resume the session so Codex can review the real result

Asking Codex "I plan to do X, Y, Z — does that sound right?" produces a rubber-stamp agreement, not a real review. Codex needs to see actual code/artifacts to give meaningful feedback.

### Re-Review Is Mandatory — No Exceptions

**Every time you apply changes based on Codex's findings, you MUST send those changes back to Codex for re-review.** This rule applies with equal force on round 1 and round 10. Do not assume your implementation is correct just because you understood the finding. Implementations can introduce new bugs, miss edge cases, or misinterpret the finding's intent. Only Codex reviewing the actual result can confirm the fix is sound.

**Watch for discipline erosion across rounds.** After several rounds of back-and-forth, it is tempting to think "these are minor changes, surely they're fine" and skip the re-review. This is the most common failure mode — do not fall into it. The size or apparent simplicity of a change does not exempt it from re-review. One line can introduce a bug.

A review is not complete until Codex has reviewed the final state of the code and explicitly confirmed there are no remaining issues. If you accepted findings and made changes, the next step is **always** a follow-up round — never presenting results to the user.

### Workflow

1. **Draft** your artifact
2. **Init** — `init_session.py --project <name> --title <title>`. Store the returned `session` path. The script auto-detects the git root from cwd, persists it in session metadata, creates `.tmp/`, and gitignores it.
3. **Write prompt** — pipe content to `write_prompt.py --session <s>`. Round auto-increments.
4. **Run review** — `run_review.py --session <s>` with `run_in_background: true`. Read `output_file` when done. The script reads `project_dir` from session metadata; pass `--cd` only to override.
5. **Critically assess** each finding — accept, reject with reasoning, or flag for discussion
6. **Apply changes** — modify the actual files for accepted findings
7. **Re-review (mandatory)** — pipe follow-up prompt to `write_prompt.py --session <s>`, then `run_review.py --session <s>` (auto-resumes). Codex re-reviews the actual updated code. Do NOT skip this step.
8. **Iterate** — repeat steps 5-7 until Codex explicitly confirms no remaining issues. The exit condition is Codex's confirmation, not your own judgment that changes are minor or correct. If you made changes, Codex must see them — no exceptions regardless of round count
9. **Do NOT clean up** — never run cleanup unless the user explicitly asks

### Presenting Results to the User

Present a clear breakdown:

- **Summary** — what was reviewed, overall assessment
- **Findings accepted** — what you changed and why
- **Findings rejected** — your reasoning for each
- **Findings debated** — back-and-forth across rounds, final resolution
- **Open questions** — unresolved items needing the user's input

Be transparent — don't silently incorporate or reject feedback. The user should see where you and Codex disagreed.
