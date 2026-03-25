---
name: codex-reviewer
description: Invoke OpenAI Codex CLI as an independent reviewer to get a second opinion on your work. Use when you want Codex to review a PRD, implementation plan, code changes, architectural decisions, or any artifact you have drafted. Also use when the user asks you to "get Codex's opinion", "have Codex review this", "ask Codex", "check with Codex", or "bounce this off Codex".
---

# Codex Reviewer

You have access to the OpenAI Codex CLI installed on this machine. Use it as an independent reviewer — a second set of eyes that brings a different perspective to your work. Codex runs as a separate AI agent with its own reasoning, so its feedback is genuinely independent from yours.

## When to Use This Skill

Invoke Codex when you need an independent review of something you have produced:

- **PRD review** — after drafting a PRD, have Codex review it for gaps, ambiguity, missing edge cases, or flawed assumptions
- **Plan review** — after creating an implementation plan, have Codex assess feasibility, ordering, missed dependencies, or over-engineering
- **Code review** — after writing or modifying code, have Codex review the diff or files for bugs, security issues, performance problems, or design concerns
- **Architecture review** — after proposing an architectural decision, have Codex evaluate trade-offs you may have missed
- **General review** — any artifact where a second perspective adds value

## How to Invoke Codex

Use the `codex exec` subcommand for non-interactive execution. Codex runs, writes its final response to a file via `-o`, and exits. Always suppress stdout to keep Codex's execution trace out of your context window.

### Safety: Read-Only Mode Is Mandatory

This skill is strictly for **review only**. Codex must NEVER modify files, create files, or run commands that change state. A separate skill may exist in the future for delegating work to Codex — this is not that skill.

**Every `codex exec` command you construct MUST include `--sandbox read-only`.** No exceptions. This flag enforces read-only mode at the Codex sandbox level, technically preventing Codex from making any modifications regardless of what its prompt says.

**FORBIDDEN FLAGS — never use any of these in this skill:**

| Flag | Why it's forbidden |
|------|--------------------|
| `--sandbox workspace-write` | Allows Codex to modify files in the working directory. |
| `--sandbox danger-full-access` | Allows Codex to modify files anywhere on the machine. |
| `--full-auto` | Sets `workspace-write` sandbox and reduces approval requirements. |
| `--dangerously-bypass-approvals-and-sandbox` / `--yolo` | Disables all sandboxing and approvals entirely. |
| `--ask-for-approval never` (without `--sandbox read-only`) | Could allow commands to run without confirmation. Only safe when paired with `--sandbox read-only`. |

**If `--sandbox read-only` is omitted**, Codex may default to a permissive sandbox mode that allows file modifications. Treat a missing `--sandbox read-only` flag as a bug — never construct a command without it.

**Self-check before executing any `codex exec` command:** scan the command you are about to run and verify:
1. `--sandbox read-only` is present
2. None of the forbidden flags above are present
3. The prompt includes explicit "do NOT modify any files" instructions

If any check fails, fix the command before executing it.

### Scripts — Use These Instead of Raw CLI Commands

This skill includes Python scripts in the `scripts/` directory that handle all Codex CLI invocations. **Always use these scripts** instead of constructing `codex exec` commands manually. The scripts enforce safety constraints (read-only sandbox, stdout suppression, session ID tracking, file naming) at the code level, so they cannot be forgotten or mistyped.

The scripts are located relative to this skill's directory. Determine the skill path at runtime and reference scripts from there.

### Step 1: Initialize a Session

Before the first review, initialize a session to create the reviews directory and generate the session metadata:

```bash
python <skill-path>/scripts/init_session.py --project <project-name> --title <review-title>
```

Returns JSON with a single `session` path. **This is the only value you need to track** — all other scripts take `--session` and read what they need from the metadata file internally.

**Example:**
```bash
python <skill-path>/scripts/init_session.py --project my-api --title prd-review
```
```json
{"session": "/tmp/codex-reviews/my-api-20260325-141500-prd-review-session.json"}
```

### Step 2: Generate File Paths

```bash
python <skill-path>/scripts/generate_path.py --session <session-path> --round <N>
```

Returns JSON with `prompt_path` and `output_path`. Use these paths when writing prompt files and passing output paths to the review scripts.

### Step 3: Write the Prompt File

Use the Write tool to create the prompt file at the `prompt_path` from Step 2. See the "Constructing the Review Prompt" section below for prompt templates.

### Step 4: Run the Initial Review

```bash
python <skill-path>/scripts/run_review.py --session <session-path> --prompt-file <prompt-path> --output-file <output-path> --cd <project-dir>
```

This script:
- Enforces `--sandbox read-only` (hardcoded, cannot be overridden)
- Suppresses Codex's execution trace from your context window
- Captures the Codex session ID **immediately** when it appears in stderr (before Codex finishes), writing it to the metadata file right away — so the session can be recovered even if the process is interrupted
- Returns JSON with `session_id` and `output_file`

Then use the Read tool to read only the output file — this is the only part of Codex's response you need.

### Step 5: Resume for Follow-Up Rounds

```bash
python <skill-path>/scripts/resume_review.py --session <session-path> --prompt-file <prompt-path> --output-file <output-path> --round <N>
```

This script:
- Enforces `--sandbox read-only` (hardcoded)
- Reads the session ID from the metadata file (rejects `--last` to prevent cross-project conflicts)
- Suppresses all stdout
- Updates the session metadata with the current round number

Returns JSON with `output_file` and `round`. Read the output file with the Read tool.

**Always resume** rather than starting a new session when continuing a review. Only start a new session when the topic is entirely different.

### Step 6: Clean Up

After the review loop is complete:

```bash
python <skill-path>/scripts/cleanup_session.py --session <session-path>
```

Deletes all prompt, output, and metadata files for the session.

### Handling Long-Running Reviews

Codex can take a long time for complex reviews (10-20+ minutes for large code reviews or architecture assessments). The Bash tool has a default timeout of 2 minutes and a maximum of 10 minutes. To handle this:

**Always run `run_review.py` and `resume_review.py` in the background** using the Bash tool's `run_in_background: true` parameter. This avoids the timeout ceiling and lets Codex run to completion. You will be notified when the command finishes, at which point you can read the output file.

**If a review is interrupted** (timeout, crash, etc.), the session is NOT lost. The session ID is written to the metadata file as soon as Codex starts (before it does any work), so you can always resume via `resume_review.py`. Check the metadata file — if `codex_session_id` is populated, the session exists on Codex's side and can be continued.

### Why Scripts Instead of Raw Commands

The scripts enforce safety at the code level rather than relying on instructions:
- `--sandbox read-only` is hardcoded — cannot be omitted or overridden
- `--last` is explicitly rejected — session ID is read from the metadata file
- Stdout is suppressed via `subprocess` — execution trace never reaches your context
- File naming convention is generated by code — no manual path construction
- Session metadata is the single source of truth — you only track one value (the session path)
- Session ID is captured early via `Popen` streaming — survives timeouts and interruptions

## Critical Thinking — Do Not Follow Codex Blindly

**This is essential.** When you receive Codex's findings and recommendations, you MUST reflect on and critically evaluate each one before acting on it. Codex is a valuable second opinion, but it is not an authority. It can be wrong, it can misunderstand context, and it can make recommendations that don't fit the specific situation.

For each finding from Codex:

1. **Assess validity** — Is this finding accurate? Does it reflect a real issue, or is Codex misunderstanding something about the context, requirements, or constraints?
2. **Research if unsure** — If a finding touches on something you're uncertain about, investigate further. Read relevant code, check documentation, or verify assumptions before accepting or rejecting the finding.
3. **Push back when warranted** — If you believe a finding is incorrect, don't implement it. Instead, note your objection with a clear reason. You will communicate this objection back to Codex in the follow-up round so it can understand your reasoning and either accept it or provide a stronger argument.
4. **Use your judgment** — You have context that Codex may not. Trust your understanding of the user's goals, the codebase history, and the broader project constraints.

The goal is a productive peer review, not blind compliance. Sometimes you'll accept all of Codex's findings. Sometimes you'll reject half of them. Both outcomes are fine as long as you've thought critically about each one.

## Constructing the Review Prompt

### Codex Has No Context — You Must Provide It

**This is critical.** Codex is a completely separate session. It has zero knowledge of your conversation with the user. It doesn't know:

- What the user's goals are
- What constraints or trade-offs have been discussed
- Whether the user wants a quick pragmatic fix or a long-term architectural solution
- What has already been considered and rejected
- What the timeline, scope, or priorities are

Without this context, Codex will review in a vacuum and may produce recommendations that are technically valid but completely misaligned with what the user actually needs. For example, Codex might recommend a complex, architecturally heavy solution when the user explicitly asked for a simple short-term fix — simply because Codex doesn't know that constraint exists.

**Before constructing every review prompt, ask yourself:** what context from my conversation with the user would change how a reviewer approaches this? Then include it.

### What Context to Include

**Always include (when applicable):**

- **User's goals** — what are they trying to achieve? What problem are they solving?
- **Constraints discussed** — timeline, scope boundaries, simplicity preferences, "just make it work for now" vs "build it properly", budget, team size, technical limitations
- **Decisions already made** — architectural choices, technology selections, trade-offs the user has already committed to. Codex should not re-litigate these unless they are the subject of the review.
- **What's out of scope** — things the user explicitly said they don't want to address right now
- **Direction and tone** — is this a quick prototype, an MVP, a production system, a learning exercise?

**Skip context when:** the review is genuinely open-ended with no prior constraints discussed. In that case, let Codex review freely without artificial boundaries.

### Prompt Requirements

The prompt must be:

1. **Explicit about the read-only constraint** — tell Codex it must NOT modify any files
2. **Rich with conversation context** — include relevant goals, constraints, and decisions from your conversation with the user so Codex reviews under the same light
3. **Clear about what to review** — include the full artifact or tell Codex where to find it
4. **Specific about what feedback you want** — generic "review this" produces generic feedback
5. **Structured** — ask for findings in a format you can easily process
6. **Clear about desired output length and detail level** — tell Codex how concise or detailed its response should be

### Controlling Codex's Output

Codex's response will be read back into your context window. A verbose, sprawling review wastes tokens and buries the signal in noise. **Always tell Codex how you want its output shaped** — be explicit about length, detail level, and what to focus on.

**Scale output instructions to the task:**

- **Large or complex reviews** (full PRD, multi-file code review, architecture assessment): Tell Codex to summarize its findings concisely. Focus on what matters most. Example: *"Keep your response concise. Provide a brief summary, then a numbered list of findings with severity ratings. No more than 2-3 sentences per finding. Skip minor stylistic issues — focus on substantive problems."*

- **Focused reviews** (single file, specific concern, narrow question): Codex can be more detailed since the scope is small. Example: *"Be thorough in your analysis of this specific function. Include code-level detail where relevant."*

- **Follow-up rounds**: These should always be concise since Codex is only responding to specific points. Example: *"Keep your response brief. For each of my points, reply with whether you accept my reasoning or still disagree (and why, in 1-2 sentences)."*

**What to tell Codex about output format:**

- Whether you want a summary or detailed analysis
- Maximum length guidance (e.g., "keep findings to one sentence each", "no more than 10 findings")
- What to skip (e.g., "skip minor stylistic suggestions", "don't comment on formatting", "focus only on logic errors and security")
- What to prioritize (e.g., "only flag Critical and Major issues", "focus on feasibility, not polish")

### Prompt Template — Initial Review

Use this structure as your base for the first round. Adapt it for the specific review type.

```
You are acting as an independent reviewer. Your job is to review the artifact below and provide your findings and recommendations.

IMPORTANT CONSTRAINTS:
- Do NOT modify any files. This is a read-only review.
- Do NOT create any files. Only provide your analysis as text output.
- Do NOT run any commands that modify state.

CONTEXT:
[Explain what this artifact is, who created it, and what problem it solves]

BACKGROUND AND GOALS:
[Summarize the relevant context from your conversation with the user. Include:
- What the user is trying to achieve and why
- Any constraints they've set (e.g., "keep it simple", "short-term fix", "production-grade", "MVP only")
- Decisions already made that should not be re-litigated
- What is explicitly out of scope
- Any other context that should shape the review
If there are no specific constraints and this is open-ended, state: "No specific constraints — review freely."]

ARTIFACT TO REVIEW:
[Include the full text of the PRD/plan/code/etc., or instruct Codex to read specific files]

REVIEW FOCUS:
[List specific areas to evaluate — e.g., completeness, feasibility, edge cases, security, performance]
Your recommendations should be appropriate given the background and goals above. Do not recommend approaches that conflict with the stated constraints or goals.

OUTPUT INSTRUCTIONS:
[Adjust based on the scope and complexity of the review. Examples:
- For large reviews: "Be concise. No more than 2-3 sentences per finding. Focus on Critical and Major issues only. Skip minor stylistic suggestions."
- For focused reviews: "Be thorough and detailed for this specific area."
- For follow-ups: "Keep it brief — one sentence per point."
Choose the appropriate level for this review.]

Please provide your review in the following format:

## Summary
A 2-3 sentence overall assessment.

## Findings
A numbered list of specific issues, gaps, or concerns. For each finding:
- What the issue is
- Why it matters
- Severity: Critical / Major / Minor / Suggestion

## Recommendations
Specific, actionable recommendations to address the findings.

## What Works Well
Aspects of the artifact that are strong and should be preserved.
```

### Prompt Template — Follow-Up Round (via Resume)

When resuming a session for a follow-up review, you don't need to repeat the full context. Codex already has it. Focus on what changed — and critically, explain your objections in detail so Codex can understand your reasoning and either accept it or provide a stronger counterargument.

```
I've reviewed your findings and critically assessed each one. Here is my response:

FINDINGS ACCEPTED — CHANGES MADE:
- [Finding #1]: [What you changed and why you agree this was an issue]
- [Finding #3]: [What you changed and why you agree this was an issue]

FINDINGS REJECTED — WITH REASONING:
- [Finding #2]: I disagree with this finding. [Detailed explanation of why — e.g., "This recommendation assumes X, but in our case Y applies because Z. The current approach is intentional because..."]
- [Finding #5]: I considered this but chose not to implement it because [specific reason — e.g., "this would break backwards compatibility with...", "the user explicitly requested this trade-off", "after researching this further I found that..."]

FINDINGS NEEDING DISCUSSION:
- [Finding #4]: I'm uncertain about this. [Explain what you're unsure about and ask Codex a specific follow-up question]

UPDATED ARTIFACT:
[Include the updated text, or tell Codex which files to re-read]

Please review the updated version and my reasoning for rejected findings. For each rejection:
- If you accept my reasoning, acknowledge it
- If you still believe the finding is valid, explain why my reasoning is flawed — provide a stronger argument

Also review the changes I made for:
1. Whether they adequately address your original findings
2. Any new issues introduced by the changes
3. Any remaining concerns

Same constraints apply: do NOT modify any files. Provide your analysis as text output only.
Keep your response concise — one sentence per point where possible. Focus on whether you accept or reject my reasoning, and flag only new or remaining issues.
```

This back-and-forth on objections is where the real value emerges. It forces both sides to sharpen their arguments and often surfaces the correct answer through debate.

### Review-Type-Specific Prompts

#### PRD Review

When reviewing a PRD, ask Codex to focus on:

- Are the requirements complete and unambiguous?
- Are there missing user stories or edge cases?
- Are the assumptions valid?
- Is the scope clearly defined? Is anything critical missing from "out of scope"?
- Are the success criteria measurable?
- Are there implementation risks not addressed?
- Would a developer have enough information to implement this?

Include the full PRD text in the prompt. Also use `--cd` to point at the project so Codex can cross-reference with the actual codebase.

#### Code Review

When reviewing code changes, ask Codex to focus on:

- Bugs or logic errors
- Security vulnerabilities
- Performance issues
- Error handling gaps
- API contract violations
- Test coverage gaps
- Readability and maintainability

Provide the diff or tell Codex which files to read. Use `--cd` so Codex has access to the full codebase for context.

#### Plan / Architecture Review

When reviewing a plan, ask Codex to focus on:

- Are the steps in the right order? Are there missing dependencies?
- Is the approach over-engineered or under-engineered?
- Are there simpler alternatives?
- What could go wrong? What are the risks?
- Are there migration or backwards-compatibility concerns?

## The Review Loop

The real power of this skill is the iterative review loop — bouncing work between yourself and Codex until both are satisfied. **Session resumption is what makes this efficient.**

### Workflow

1. **Draft your artifact** (PRD, plan, code, etc.)

2. **Initialize a session** — run `init_session.py`. Store the returned `session` path — this is the only value you need.

3. **Generate file paths** — run `generate_path.py --session <session> --round 1`.

4. **Write the prompt** — use the Write tool to create the prompt file at `prompt_path` (see prompt templates below).

5. **Run the initial review** — run `run_review.py` with `run_in_background: true` for long reviews. When it completes, read the output file.

6. **Critically assess each finding** — do NOT blindly follow Codex's recommendations:
   - **Validate each finding** — is it accurate? Does Codex have the full picture?
   - **Research if uncertain** — read code, check docs, verify assumptions before deciding
   - **Accept and implement** findings you agree with
   - **Reject with reasoning** findings you disagree with — document exactly why
   - **Flag for discussion** findings you're unsure about — ask Codex a follow-up

7. **Send follow-ups** — generate r2 paths, write the follow-up prompt, run `resume_review.py`. Read the output file. Repeat for r3, r4, etc.

8. **Converge** when Codex's findings are minor/stylistic or when you've addressed all substantive feedback.

9. **Clean up** — run `cleanup_session.py --session <session>` to delete all review files.

### Why Session Resume Matters

- **Context preservation** — Codex remembers the original artifact, all its prior findings, and your responses. It doesn't need to re-read or re-analyze from scratch.
- **Coherent conversation** — follow-up rounds build on prior discussion rather than starting cold. Codex can say "my concern about X from round 1 is now addressed" or "the change you made to address finding #3 introduced a new issue."
- **Efficiency** — shorter prompts in follow-up rounds because you only describe what changed, not the entire context.
- **Accountability** — Codex can track which of its findings were addressed and which were not.

### Presenting Results to the User

After processing Codex's review, present the user with a clear breakdown:

- **Summary** — what Codex reviewed and its overall assessment
- **Findings accepted** — which findings you agree with, what changes you made, and why
- **Findings rejected** — which findings you disagree with, your specific reasoning for each rejection, and any research you did to reach that conclusion
- **Findings debated** — any findings where you and Codex went back and forth across rounds, what the final resolution was, and why
- **Open questions** — any unresolved items that need the user's input to decide

Be transparent. Don't silently incorporate or reject Codex's feedback — the user should see the full picture, including where you and Codex disagreed. The user may side with Codex on a point you rejected, or may agree with your objection. Either way, they need visibility into the debate.

## Practical Examples

### Example 1: PRD Review with Follow-Up

```bash
# Initialize session — store the session path (the only value you track)
python <skill-path>/scripts/init_session.py --project my-api --title prd-review
# → {"session": "/tmp/codex-reviews/my-api-20260325-141500-prd-review-session.json"}

# Generate r1 paths
python <skill-path>/scripts/generate_path.py --session /tmp/codex-reviews/my-api-20260325-141500-prd-review-session.json --round 1
# → {"prompt_path": "...-r1-prompt.txt", "output_path": "...-r1-output.md"}

# Write prompt file (via Write tool), then run initial review (use run_in_background for large reviews)
python <skill-path>/scripts/run_review.py --session /tmp/codex-reviews/my-api-20260325-141500-prd-review-session.json --prompt-file <prompt_path> --output-file <output_path> --cd /path/to/project
# → {"session_id": "...", "output_file": "..."}. Read the output file via Read tool.

# Round 2: Generate r2 paths, write follow-up prompt, resume
python <skill-path>/scripts/generate_path.py --session /tmp/codex-reviews/my-api-20260325-141500-prd-review-session.json --round 2
python <skill-path>/scripts/resume_review.py --session /tmp/codex-reviews/my-api-20260325-141500-prd-review-session.json --prompt-file <r2_prompt_path> --output-file <r2_output_path> --round 2
# Read the r2 output file, continue iterating until converged

# Clean up when done
python <skill-path>/scripts/cleanup_session.py --session /tmp/codex-reviews/my-api-20260325-141500-prd-review-session.json
```

### Example 2: Quick Sanity Check

Even for a one-off review, use the scripts — they're just as easy and enforce all safety constraints:

```bash
python <skill-path>/scripts/init_session.py --project my-api --title cache-approach
# Store session path, generate paths, write prompt, run review, read output, clean up
```

## Important Notes

### Safety (enforced by scripts)
- **`--sandbox read-only` is hardcoded** in `run_review.py` and `resume_review.py` — it cannot be omitted or overridden. The scripts construct the command internally with no mechanism to inject other sandbox flags.
- **`--last` is blocked** in `resume_review.py` — the session ID is read from the metadata file, never from `--last`.
- **Stdout is suppressed** via `subprocess` — Codex's execution trace never reaches your context window.
- **Always include the no-modification instruction in the prompt** — belt and suspenders. The sandbox enforces it technically, but the prompt instruction prevents Codex from even attempting modifications.

### Workflow
- **Always use the scripts** — never construct raw `codex exec` commands manually. The scripts exist to enforce constraints you might otherwise forget.
- **Codex is not infallible — think critically** — treat its findings as suggestions to evaluate, not commands to follow. Reflect on and validate each finding before acting on it. Research topics you're uncertain about. Push back on findings you believe are wrong and explain your reasoning in the follow-up prompt so Codex can respond to your objections.
- **Provide conversation context** — Codex has no knowledge of your discussion with the user. Include relevant goals, constraints, and decisions so Codex reviews under the same conditions.
- **Be specific in your prompts** — the more context and focus you provide, the better the review.
- **Clean up** — run `cleanup_session.py` when the review loop is complete.
