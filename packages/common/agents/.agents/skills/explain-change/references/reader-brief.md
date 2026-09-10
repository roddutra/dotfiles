# Brief for the independent reader

Use this when delegating the explainer to a fresh sub-agent or session. Fill in the bracketed parts; keep the rest.

```
Read [absolute path to the explain-change skill]/SKILL.md, its references/ and its assets/ first, then the repository's instruction files for the code you read ([AGENTS.md / CLAUDE.md paths]). Build the page from assets/template.html with explainer.css and explainer.js inlined unchanged; write content only, no design of your own. Write to references/writing-guide.md: it has the word budgets, the sentence limit and the banned words, and the verify step checks them with a script.

Task: produce the explainer page for [spec and milestone / capability name / PR / commit].

Pinned scope: [snapshot id from the SKILL.md table: a sha, a range, a PR head sha, or HEAD plus the diff hash for uncommitted work] in checkout [path]. For uncommitted work read the working tree as it is now (git diff HEAD and untracked files) and do not stash, commit or reset anything. For a committed target that differs from the checkout, read surrounding code at that revision (git show <sha>:<path>) and say so on the page. Explain that snapshot only.

Intent sources. The user's own instructions and approvals outrank documents, and later explicit decisions supersede earlier ones; agent-written text (PR bodies, run sheets, reports, commit messages) shows what the agent did and claims, not that the user approved it.
- User instructions and approvals: [quoted prompts, review comments, or "none recorded"]
- Spec, PRD, issue or ticket: [path or URL, sections ...]
- Delivery plan / run sheet: [path, including its Deviations sections]
- Agent accounts: [PR body and thread, commit messages, sub-agent reports]
Where these are silent or ambiguous, say so on the page; do not infer intent.

Current-state docs for the area: [guide paths]. Glossary: [path, or "none"]. Writing conventions: [from the instruction files].

You did not write this code and must not assume anything about why it is the way it is beyond what the intent sources and run sheet record. Read the change on its own terms and follow the workflow in the skill: extract intent, read, reconcile, boundary checklist, draft, verify, deliver.

Do not modify any tracked file. Write only into the run directory [absolute path to .tmp/explainers/YYYY-MM-DD-HHMM-<slug>/]: the page as [index.html, or <slice>.html for a slice] and your report as reports/[slice].md. Browser captures go in that directory too: `agent-browser screenshot --full "<run dir>/<name>.png"` (the flag is `--full`; `--full-page` is parsed as a path and writes a stray PNG named `--full-page` into the current directory; delete any such file). Do not install dependencies or run migrations in a pinned worktree; run a specific test in the main checkout only when the skill's evidence rules call for it.

Verify the page in a browser before reporting: reveal, accept/reject/discuss, type a note on one item, reload and confirm selections and the note survived, copy-as-markdown button and textarea fallback with the note in the export. Fix failures; do not report them as notes.

Report back: the output path, the verdict, the deviations and open decisions (short list), unverified claims, and guide sections that should have been updated. Do not paste the page content into the report.
```

For a second-model reader (for example the `codex-reviewer` skill's read-only scripts) send the same brief and ask for the intent ledger and deviations as markdown; fold them into the page.
