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

Use the `codex exec` subcommand for non-interactive execution. Codex runs, streams its response to stdout, and exits.

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

### Command Pattern — Initial Review

For short prompts:

```bash
codex exec --sandbox read-only "Your prompt here"
```

For longer prompts (which reviews typically require), write the prompt to a temporary file and pipe it:

```bash
codex exec --sandbox read-only --cd /path/to/project -o /tmp/codex-review-output.md - < /tmp/codex-review-prompt.txt
```

### Command Pattern — Follow-Up Rounds (Session Resume)

**This is critical.** After the initial review, all subsequent interactions with Codex on the same topic MUST use `codex exec resume` to continue the existing conversation. This preserves Codex's full context — the original artifact, its prior findings, and the discussion history — so it doesn't need to re-read everything or lose track of what was already discussed.

Resume the most recent session:

```bash
codex exec resume --last --sandbox read-only -o /tmp/codex-review-round2.md "Your follow-up prompt here"
```

Resume a specific session by ID:

```bash
codex exec resume <SESSION_ID> --sandbox read-only -o /tmp/codex-review-round2.md "Your follow-up prompt here"
```

For longer follow-up prompts, pipe from a file:

```bash
codex exec resume --last --sandbox read-only -o /tmp/codex-review-round2.md - < /tmp/codex-followup-prompt.txt
```

**Always prefer resuming over starting a new session** when continuing a review. Only start a new session when the topic is entirely different or unrelated to any prior review.

### Key Flags

| Flag | Purpose |
|------|---------|
| `--sandbox read-only` | **Required.** Prevents Codex from modifying files. |
| `--cd <path>` | Sets the working directory so Codex can read the relevant codebase. Only needed on the initial invocation — resumed sessions inherit the working directory. |
| `-o <path>` | Writes Codex's final response to a file (useful for capturing long reviews). |
| `--model <model>` | Override the model if needed. |
| `resume --last` | Continue the most recent Codex session. Use for follow-up rounds. |
| `resume <SESSION_ID>` | Continue a specific Codex session by ID. |

### Capturing Output

For reviews that may be long, capture the output to a file so you can read it reliably:

```bash
codex exec --sandbox read-only --cd /path/to/project -o /tmp/codex-review-output.md - < /tmp/codex-review-prompt.txt
```

Then read `/tmp/codex-review-output.md` to process the findings.

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

2. **Send it to Codex for initial review** — start a new `codex exec` session:
   ```bash
   codex exec --sandbox read-only --cd /path/to/project -o /tmp/codex-review-r1.md - < /tmp/codex-review-prompt.txt
   ```

3. **Critically assess each finding** — do NOT blindly follow Codex's recommendations:
   - **Validate each finding** — is it accurate? Does Codex have the full picture?
   - **Research if uncertain** — read code, check docs, verify assumptions before deciding
   - **Accept and implement** findings you agree with
   - **Reject with reasoning** findings you disagree with — document exactly why
   - **Flag for discussion** findings you're unsure about — ask Codex a follow-up

4. **Send the updated artifact back for another round** — **resume the same session**:
   ```bash
   codex exec resume --last --sandbox read-only -o /tmp/codex-review-r2.md - < /tmp/codex-followup-prompt.txt
   ```
   Codex retains the full context of its original review, your changes, and can assess whether its findings were properly addressed.

5. **Continue resuming** for as many rounds as needed:
   ```bash
   codex exec resume --last --sandbox read-only -o /tmp/codex-review-r3.md "I've addressed your remaining concerns about X and Y. The updated PRD now includes Z. Please do a final review and confirm if you're satisfied."
   ```

6. **Converge** when Codex's findings are minor/stylistic or when you've addressed all substantive feedback.

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
# Round 1: Initial review
# Write the review prompt including the full PRD to a temp file, then:
codex exec --sandbox read-only --cd /path/to/project -o /tmp/codex-prd-review-r1.md - < /tmp/codex-prd-prompt.txt

# Read /tmp/codex-prd-review-r1.md, assess findings, update the PRD

# Round 2: Resume the session with changes
codex exec resume --last --sandbox read-only -o /tmp/codex-prd-review-r2.md - < /tmp/codex-prd-followup.txt

# Read /tmp/codex-prd-review-r2.md, continue iterating until converged
```

### Example 2: Code Review of Recent Changes

```bash
# Round 1: Initial code review
codex exec --sandbox read-only --cd /path/to/project -o /tmp/codex-code-review-r1.md "You are an independent code reviewer. Do NOT modify any files. Read the files [list files] and review them for bugs, security issues, and design problems. Provide findings as a numbered list with severity ratings."

# Address findings, then resume for verification
codex exec resume --last --sandbox read-only -o /tmp/codex-code-review-r2.md "I've fixed the issues you identified in findings #1, #2, and #4. Please re-read the updated files and verify the fixes. Flag any remaining or new issues."
```

### Example 3: Quick Sanity Check (No Follow-Up Needed)

For a one-off check where you don't expect iteration, a single invocation is fine:

```bash
codex exec --sandbox read-only --cd /path/to/project "Do NOT modify any files. Review the approach in [file] for [specific concern]. Reply with your assessment in 2-3 paragraphs."
```

## Important Notes

### Safety (non-negotiable)
- **`--sandbox read-only` on EVERY command** — both initial invocations and resumed sessions. Never omit it. Never substitute it with a different sandbox mode.
- **NEVER use `--full-auto`, `--sandbox workspace-write`, `--sandbox danger-full-access`, or `--yolo`** — these flags allow Codex to modify files. They are forbidden in this skill. This skill is review-only.
- **Always include the no-modification instruction in the prompt** — belt and suspenders. The sandbox enforces it technically, but the prompt instruction prevents Codex from even attempting modifications that would be blocked.
- **Self-check every command** — before executing, visually confirm `--sandbox read-only` is present and no forbidden flags snuck in.

### Workflow
- **Always resume sessions for follow-up rounds** — never start a new session to continue an existing review. Use `codex exec resume --last` or `codex exec resume <SESSION_ID>`.
- **Codex is not infallible — think critically** — treat its findings as suggestions to evaluate, not commands to follow. Reflect on and validate each finding before acting on it. Research topics you're uncertain about. Push back on findings you believe are wrong and explain your reasoning in the follow-up prompt so Codex can respond to your objections.
- **Provide conversation context** — Codex has no knowledge of your discussion with the user. Include relevant goals, constraints, and decisions so Codex reviews under the same conditions.
- **Be specific in your prompts** — the more context and focus you provide, the better the review.
- **Use `--cd`** on the initial invocation to point Codex at the project directory so it can read relevant code for context.
- **For long artifacts**, write the prompt (including the artifact) to a temp file and pipe it in, rather than trying to fit everything in a CLI argument.
- **Clean up temp files** after the review loop is complete.
