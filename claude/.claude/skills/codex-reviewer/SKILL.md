---
name: codex-reviewer
description: Invoke OpenAI Codex CLI as an independent reviewer to get a second opinion on your work. Use when you want Codex to review a PRD, implementation plan, code changes, architectural decisions, or any artifact you have drafted. Also use when the user asks you to "get Codex's opinion", "have Codex review this", "ask Codex", "check with Codex", or "bounce this off Codex".
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

This skill is strictly for **review only**. Codex must NEVER modify files or change state.

**Always use the Python scripts** in `scripts/` — they hardcode `--sandbox read-only` at the code level, which cannot be overridden. Never construct raw `codex exec` commands manually. Always include "do NOT modify any files" in prompts as an additional safeguard.

## Scripts

Located relative to this skill's directory. Determine the skill path at runtime.

### Step 1: Initialize a Session

```bash
python <skill-path>/scripts/init_session.py --project <project-name> --title <review-title>
```

Returns JSON with a single `session` path — **the only value you need to track**. All other scripts take `--session` and read what they need from the metadata file.

### Step 2: Generate File Paths

```bash
python <skill-path>/scripts/generate_path.py --session <session-path> --round <N>
```

Returns JSON with `prompt_path` and `output_path`.

### Step 3: Write the Prompt File

Write tool → create the prompt file at `prompt_path`. See prompt templates below.

### Step 4: Run the Initial Review

```bash
python <skill-path>/scripts/run_review.py --session <session-path> --prompt-file <prompt-path> --output-file <output-path> --cd <project-dir>
```

- Hardcodes `--sandbox read-only`
- Suppresses Codex's execution trace from your context
- Captures the session ID **immediately** via stderr streaming, writing it to metadata before the review finishes — survives timeouts
- Returns JSON with `session_id` and `output_file`

Use `run_in_background: true` for anything beyond a trivial review (see "Handling Long-Running Reviews" below). Read only the output file with the Read tool — this is the only part of Codex's response you need.

### Step 5: Resume for Follow-Up Rounds

```bash
python <skill-path>/scripts/resume_review.py --session <session-path> --prompt-file <prompt-path> --output-file <output-path> --round <N>
```

- Hardcodes `--sandbox read-only`
- Reads session ID from metadata (rejects `--last` to prevent cross-project conflicts)
- Suppresses all stdout

Use `run_in_background: true` for long reviews. Read the output file with the Read tool when done.

Always resume rather than starting a new session when continuing a review.

### Step 6: Clean Up (User-Initiated Only)

```bash
python <skill-path>/scripts/cleanup_session.py --session <session-path>
```

Deletes all prompt, output, and metadata files for the session.

**Do NOT clean up automatically.** Session files live in `/tmp` and are harmless to keep. Only clean up when the user explicitly asks, or when you are 100% certain the work is fully complete (e.g., committed to main, feature branch merged, and the user has moved on to a different topic). When in doubt, leave the files — losing review history mid-flow is far worse than a few temp files.

### Discovering Past Sessions

```bash
python <skill-path>/scripts/list_sessions.py [options]
```

Returns JSON with matching sessions, their metadata, and associated files (prompts + outputs). Use this from a fresh conversation to find and reference prior review history.

**Filter options:**

- `--project <name>` — filter by project name
- `--date today` / `--date yesterday` / `--date 2026-03-25` — specific date
- `--from 2026-03-01 --to 2026-03-25` — date range
- `--week` — current week
- `--month` — current month

All filters are combinable (e.g., `--project my-app --week`).

**When to use:** At the start of a new conversation when the user references a prior review, or when you need context from an earlier session on the same project. Read the returned prompt/output files to recover the full review history.

### Handling Long-Running Reviews

Codex can take 10-20+ minutes for complex reviews. The Bash tool has a max timeout of 10 minutes.

**Always run `run_review.py` and `resume_review.py` with `run_in_background: true`** to avoid the timeout ceiling.

**If a review is interrupted**, the session is NOT lost — the session ID is already in the metadata file. Resume via `resume_review.py`.

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
[Full text, or instruct Codex to read specific files]

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
[Updated text, or tell Codex which files to re-read]

For each rejection: accept my reasoning, or explain why it's flawed.
Review changes for: adequacy, new issues, remaining concerns.
Do NOT modify any files. Text output only.
Keep concise — one sentence per point.
```

### Review-Type Tips

- **PRD**: Include full PRD text. Use `--cd` so Codex can cross-reference the codebase.
- **Code**: Provide the diff or tell Codex which files to read. Use `--cd` for full codebase context.
- **Plan/Architecture**: Include the plan. Focus Codex on ordering, dependencies, risks, and simpler alternatives.

## The Review Loop

### Apply First, Then Re-Review

**Never ask Codex to pre-approve planned changes.** When Codex gives feedback:

1. Apply accepted changes to the actual files
2. Then resume the session so Codex can review the real result

Asking Codex "I plan to do X, Y, Z — does that sound right?" produces a rubber-stamp agreement, not a real review. Codex needs to see actual code/artifacts to give meaningful feedback.

### Workflow

1. **Draft** your artifact
2. **Init** — `init_session.py`. Store the `session` path.
3. **Generate paths** — `generate_path.py --session <s> --round 1`
4. **Write prompt** at `prompt_path`
5. **Run review** — `run_review.py` with `run_in_background: true`. Read output when done.
6. **Critically assess** each finding — accept, reject with reasoning, or flag for discussion
7. **Apply changes** — modify the actual files for accepted findings before contacting Codex again
8. **Follow up** — generate next round paths, write follow-up prompt listing what changed and what was rejected with reasoning, `resume_review.py`. Codex re-reviews the actual updated artifacts.
9. **Iterate** — repeat steps 6-8 until both sides converge: Codex raises no new substantive findings, and all accepted changes are applied
10. **Clean up** — only when the user asks, or work is fully complete and merged. Do NOT clean up proactively.

### Presenting Results to the User

Present a clear breakdown:

- **Summary** — what was reviewed, overall assessment
- **Findings accepted** — what you changed and why
- **Findings rejected** — your reasoning for each
- **Findings debated** — back-and-forth across rounds, final resolution
- **Open questions** — unresolved items needing the user's input

Be transparent — don't silently incorporate or reject feedback. The user should see where you and Codex disagreed.
