---
name: write-markdown
description: MUST use when writing or editing any markdown content — including .md files, skill SKILL.md files, CLAUDE.md, AGENTS.md, READMEs, PRDs, plans, docs, and any other markdown.
---

# Writing Markdown Files

Follow these rules whenever you create or edit any `.md` file — documentation, plans, READMEs, guides, notes, or any other markdown content.

## Core Principle: Concise is Key

Say what needs to be said, then stop. Every sentence should earn its place. If removing a sentence doesn't reduce the reader's understanding, remove it.

**But concise does not mean aggressive trimming.** Short, useful details (e.g. "Requires `Mail.Read` permission") cost almost nothing to include and help readers who are new to the project. Only cut content that is genuinely redundant, verbose, or explains things the audience already knows. When in doubt, keep it.

## Know Your Audience

Before writing, determine who will read this file: **humans** or **AI agents/LLMs**.

### For AI agent / LLM readers

AI agents already understand general programming concepts, common APIs, standard patterns, and well-known tools. Do not explain things they already know.

- **Skip broad concept explanations.** Don't explain what OAuth is, how cron expressions work, what REST APIs are, etc. Just state the project-specific details.
- **Minimize examples.** A short sentence describing expected format or behaviour is better than a multi-line example block — unless the format is truly non-obvious or unique to this project.
- **Focus on what's unique.** Document project-specific conventions, non-obvious decisions, custom patterns, gotchas, and things that can't be inferred from reading the code alone.
- **State facts, not tutorials.** Use declarative statements ("State is saved after each dispatch") rather than instructional prose ("In order to understand how state works, let's walk through...").

### For human readers

Humans may not be familiar with every tool or concept. Be concise but not cryptic.

- **Explain non-obvious concepts briefly** — a sentence or two, not a paragraph. Link to external docs for deep dives rather than inlining explanations.
- **Provide examples when the format isn't self-evident** — e.g. an OData filter string, a cron expression, a config structure. One example is usually enough.
- **Use step-by-step instructions** for operational procedures (setup, deployment, testing) where the reader needs to perform actions.

### When the audience is mixed or unclear

Default to writing for a technical human who is familiar with the tech stack but new to the project. This hits the right balance — concise enough for AI, clear enough for humans.

## File Paths

- **Always use relative paths** from the repository root. Never use absolute paths containing machine-specific directories (e.g. `/Users/someone/...`).
- When referencing files, use the repo-relative path: `app/`, not the full filesystem path.

## Readability

Readability matters as much as brevity. A document that's hard to scan is not concise — it's just short.

- **One item per line in lists.** When listing parameters, fields, or options, put each on its own bullet. Never combine multiple items onto one line (e.g. don't write `include_attachments / include_body: control payload size`). Each item gets its own bullet for easy scanning, even if the descriptions are short.
- **Descriptions only where they add value.** Self-explanatory items (e.g. `user_id`) don't need a description. Non-obvious items do. It's fine for some bullets to have descriptions and others not.

## Structure

- **Front-load the most important information.** Lead with what the thing does and why it exists, not background context.
- **Use headings to enable scanning.** A reader should be able to skim headings and understand the document's structure without reading body text.
- **Avoid redundancy.** Don't repeat information that appears elsewhere in the same document or in referenced files. Say it once, in the right place.
- **Keep sections short.** If a section exceeds ~20 lines, consider whether it can be split or trimmed.

## What to Include vs. Omit

**Include:**

- Purpose and high-level behaviour
- Project-specific conventions and decisions
- Gotchas, edge cases, and non-obvious behaviour
- Relationships between components (what calls what, data flow)
- Operational steps the reader needs to perform

**Omit:**

- Generic explanations of well-known technologies
- Extensive type definitions that can be read directly from source code
- Multiple examples when one (or a sentence) suffices
- Attribution lines, generation timestamps, or author metadata — unless the user requests them
