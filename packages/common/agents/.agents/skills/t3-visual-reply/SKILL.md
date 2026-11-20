---
name: t3-visual-reply
description: Shows a decision, task status, explanation or summary as an inline HTML visual reply in a T3 Code thread, built from JSON blocks by a bundled renderer so every page looks consistent. Use only when an `html_render` tool (any MCP prefix, possibly deferred) is available, and when asking the user to choose between options, reporting progress on multi-step work, or when the user asks to see something inline or visually in the chat. Not for PRDs, plans or HTML artifacts the user wants saved as files.
---

# T3 Visual Reply

Publishes a self-contained page into the current T3 Code thread with T3's `html_preview` and `html_render` tools. The agent writes content as JSON blocks; `scripts/render.mjs` (next to this file) owns layout, theming and escaping.

## Pick the output

- **Plain text:** short answers, confirmations, anything readable in a few lines.
- **Visual reply:** a decision the user must make, status of multi-step work, or an explanation, comparison or summary the user wants inline. Visual replies are deleted with the thread, so treat them as disposable.
- **Repo artifact:** the user asks for an artifact, file or page to keep, or the content is a PRD, plan or ADR. Follow the project's existing convention for these. The Markdown PRD remains the implementer's source of truth. A short visual reply that summarises the artifact and gives its repo path is optional.

Never make a visual reply the only copy of anything durable.

## Requirements

Find `html_render` and `html_preview` in the live tool list (any MCP prefix; load them first if deferred). If they are missing, reply in Markdown. When the user explicitly asked for a visual reply, say the T3 tools are unavailable. Never present a saved `.html` file as having been shown inline.

## Workflow

1. Write the payload to a scratch or temp file outside the repo. Block reference: [references/blocks.md](references/blocks.md).
2. Run `node <skill-dir>/scripts/render.mjs payload.json > page.html`. On exit 1, fix every problem it lists on stderr and rerun.
3. Pass the exact contents of `page.html` to `html_preview` (default width 728). Also preview at width 390 when the page has options, cards, steps, tables or an `html` block. Fix overflow, cramped text and console errors through the payload. Do not hand-edit the output.
4. Call `html_render` with the same HTML, the payload `title`, and `height` set to the 728-wide `contentHeight` clamped to 80-2000.
5. Write a short text reply that adds only what the page does not say. Do not restate or announce the page.
6. If `html_render` fails, say so and give the content in Markdown.

## Decisions

- One decision per page where possible. Ask a plain question; put background in `context` or a `details` block.
- 2-4 options. Each `id` is the reply token the user types, so keep it short and lowercase (`brew`, `add + clean`).
- Set `recommended` only when there is a real recommendation. Use `"required": false` for optional suggestions.
- A reply token or a free-form answer chooses an option. It does not approve side effects; ask for approval as usual.

## Status

The skill is project-agnostic. Read progress from the project's own source of truth (its tracker, a PRD checklist, the agent's task list) at render time, never from memory. `source` names where it came from and `as_of` gives a local timestamp. Do not estimate or invent counts.

## Explanations and summaries

- Open with a `lede` that states the answer or main point.
- Prefer kit blocks; hide long background in `details`.
- Aim for a page under about 1200 px tall at 728 wide. Split or trim anything longer.

## The `html` block

Use it only when no kit block fits, for example a custom diagram, inline SVG or a small chart.

- A fragment only, styled with T3 theme variables (`--foreground`, `--card`, `--border`, `--primary`, `--success`, `--warning`, `--destructive`, `--info`, `--chart-1` to `--chart-6`, `--radius`, `--font-mono`).
- Prefix custom classes (for example `d-`) so they cannot collide with the kit's `v-` classes.
- No remote resources, no `vh` units and no full-page backgrounds. The renderer rejects the first two.
- JavaScript only when the content needs it, never for network calls or sending messages.
- If the same custom block is needed repeatedly, suggest adding it to the kit.

## Writing

Follow the user's global writing rules. The renderer rejects en and em dashes.
