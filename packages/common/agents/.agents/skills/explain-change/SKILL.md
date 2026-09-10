---
name: explain-change
description: Builds an intent-checked explainer page for a change of any size and shape (uncommitted work, a commit, a branch, a PR, a milestone of a spec) so the product owner can confirm it matches what they meant, understand it well enough to challenge it, and pass a learning check. Pass the target as the argument, e.g. /explain-change PR 176, /explain-change HEAD~3..HEAD, /explain-change unstaged, /explain-change "spec 052 milestone 4".
disable-model-invocation: true
---

# Explain Change

An explainer that answers two questions in order: does what was built match what the product owner asked for, and do they understand it well enough to challenge it. Explaining what exists is not enough; a convincing explanation can make an unintended design feel inevitable, so the intent comparison comes first and the walkthrough serves it.

Output is one self-contained HTML page kept out of version control. It is a review artefact tied to one snapshot, never a durable doc: lasting understanding goes into the repository's own guides, and intent drift goes back to the implementation as findings.

Only the user invokes this skill (`disable-model-invocation`). Never suggest running it as part of another workflow; the user decides when they need an explainer.

The skill is repository-agnostic. Everything project-specific (where specs live, the glossary, architecture rules, writing conventions, safe test commands) comes from the repository's own instruction files (`AGENTS.md`, `CLAUDE.md`, or equivalents) and docs, discovered at run time; never assume a layout.

## Resolving the target

The argument names the change. It is not tied to a pull request; resolve whatever the user gave and record it as the pinned snapshot:

| Argument | Resolve as | Snapshot id |
|---|---|---|
| `uncommitted`, `working tree`, or nothing with a dirty tree | `git diff HEAD` (staged and unstaged together) plus the contents of untracked files (`git ls-files --others --exclude-standard`) | `HEAD` sha plus a hash over the diff and the untracked contents together |
| `unstaged` | `git diff` (working tree against the index only) | as above, over that diff |
| `staged` | `git diff --cached` | as above, over the cached diff |
| a commit (`HEAD`, `abc123`) | `git show <sha>` | the sha |
| a range (`main..HEAD`, `HEAD~3..HEAD`) | `git diff <range>` and `git log <range>` | both end shas |
| a branch name | `git diff <default branch>...<branch>` | the merge base sha and the branch head sha |
| `PR <n>` or a PR URL | `gh pr view <n> --json baseRefName,headRefOid,body,title` and `gh pr diff <n>` (or the equivalent for the host) | the merge base sha and the head sha |
| a spec or milestone name | the branches, PRs or commits the spec's delivery notes name for that milestone | each range |
| a path or feature name with no ref | the recent history of that path (`git log --oneline -- <path>`); ask which range if unclear | the range |

If nothing was given and the tree is clean, ask what to explain rather than guessing. If the repository uses worktrees with their own environments, resolve against the worktree the session runs in.

Read surrounding code at the snapshot, not at whatever is checked out today. For a committed target whose head differs from the checkout, read files with `git show <sha>:<path>` or check the target out in a temporary detached worktree; otherwise the page can describe a mixture of versions. State on the page which revision the surrounding code was read from.

## Scaling the page

The user chose to invoke, so always produce a page; scale it to the change:

- **Small change** (a fix, one capability, a few files): a short page. Deviations and decisions, a compact intent ledger, one scenario, a brief walkthrough, two to four learning-check questions. Aim for something read in ten minutes.
- **Material change** (a milestone, a new capability, a state machine, a migration band, locking or ordering, any boundary in the checklist below): the full structure with a learning check.
- **Time-varying state that a diff cannot convey** (lifecycle transitions, commit protocols, rate or quota windows, migration replays, scheduling ladders): add a microworld, a small interactive model of that state. Only when manipulating it would change a decision, and validate it against real examples from the code first.

A whole multi-milestone spec, or a PR of hundreds of files, is too big for one page. Split it into slices by milestone or capability, one page each, plus an index page that a reader opens first: it ranks the slices by consequence, carries the deviations and open decisions that cross slices, and links each slice with a one-line verdict. Slices can be read in parallel by separate readers; the index is written last, from their reports. When explaining an open milestone, prefer to do it before the PR merges: corrections are cheap then.

## Independence

The session that wrote the code must not write the explainer. It will describe what it intended and inherit its own blind spots, which is exactly what the page exists to catch. Delegate the reading and drafting to a fresh sub-agent with the brief in `references/reader-brief.md`, or run it in a new session. Where an independent second model is available (for example a read-only reviewer skill such as `codex-reviewer`), use it for the intent ledger and deviations at minimum. If the current session did not implement the change and has not read the diff yet, it may act as the reader itself.

## Inputs

Gather before reading the change, and pin them:

- The pinned snapshot from the table above.
- The intent sources, whichever exist: the user's prompts, review comments and explicit approvals; the spec, PRD, issue or ticket; its delivery plan or run sheet; the PR body and thread; the commit messages. A small direct commit may have only a commit message and the user's prompt; that is still the intent source. Note where the intent is missing or ambiguous rather than inferring it.
- Sub-agent reports and any "Deviations" sections in delivery notes: agents record obstacle-driven scope changes there.
- The repository's current-state docs for the area (guides, architecture docs) and its glossary or ubiquitous-language file if it has one.
- The repository's instruction files, for its architecture rules, safe commands, and writing conventions.

Intent precedence: the user's own instructions and approvals outrank documents, and a later explicit decision supersedes an earlier one, so a mid-implementation change of direction the user asked for is not a deviation. Agent-written text (PR bodies, run sheets, sub-agent reports, commit messages) is evidence of what the agent did and claims, never evidence that the user approved it unless the user's approval is itself recorded. Say which source each requirement came from.

## Workflow

1. **Pin scope.** Record the snapshot id, the spec and milestone if any, and the intent sources. State what is out of scope. For uncommitted work, warn on the page that the snapshot cannot be re-checked out later.
2. **Extract intent.** List the requirements, constraints and explicit non-goals from the intent sources in their own words. Flag anything ambiguous or unstated; the page must not paper over it.
3. **Read the change on its own terms.** Follow real user, operator and external-system actions through the code, including at least one failure or exception path, before cataloguing classes. Read surrounding code the change depends on.
4. **Reconcile.** For each requirement: matched, changed, deferred, or missing, with evidence. Then list everything the change does that no intent source asked for, and every judgment call made where the intent was silent. These two lists are the most valuable part of the page.
5. **Run the boundary checklist** (below) and record for each boundary the change touches what it does and whether that was a stated decision.
6. **Draft the page** to the structure in `references/page-spec.md`. Deviations and decisions come first, then the intent ledger, then the teaching sections.
7. **Verify the page.** Every item below is checked, not assumed, and the provenance section records the result:
   - every material claim cites a file and line or a test at the pinned snapshot;
   - each learning-check answer re-checked against the code, not against the draft;
   - the page is the template with the assets inlined unchanged (`grep -c "explain-change page stylesheet"` and `"explain-change page script"` both return 1), and no page-specific `<style>` beyond it;
   - the page is within the word budget for its type and no sentence exceeds 26 words (run `python3 <skill dir>/assets/check-writing.py <page> small|material|index`; it also checks the banned words, the block, the dashes and the asset markers), the "Read this first" block is present, and the filler and time-anchor words listed there do not appear;
   - every code block preserves whitespace; no en or em dashes; no external requests;
   - in a browser (the `agent-browser` skill, or any headless browser): reveal each answer, use accept, reject and discuss, type a note on one item, reload and confirm the selections and the note survived, and use the copy-as-markdown button and the textarea fallback and confirm the note is in the export. Selections that vanish on reload, or a missing copy button, are failures to fix, not notes.
   Browser captures go inside the run directory (below) with an absolute output path: `agent-browser screenshot --full "<run dir>/<name>.png"`. The flag is `--full`; `--full-page` is not a flag, it is taken as a path and silently writes a PNG named `--full-page` into the current directory. Delete any such stray file before finishing.
8. **Deliver and follow up.** The deliverable is complete only when every slice page and the index exist and have passed step 7. If readers run in the background, the turn is not finished until their reports are gathered and the index is written; if something is missing, the reply says which slices are absent and why rather than presenting a partial set as done. Report the verdict, the deviations and open questions, unverified claims, and guide sections the change should have updated. Findings the user rejects go back to the implementation as work items, not into the page.

## Boundary checklist

Small implementation choices at these boundaries change the product. For each one the change touches, the page says what the code does, and whether the spec decided it or the agent did. Extend the list with the repository's own architecture rules from its instruction files; those rules are usually where the costly silent decisions hide.

- Data isolation: tenancy, per-customer or per-environment separation, cross-store references.
- Domain variability: for every new field, rule or constraint, whether it is universal or varies by region, product line, plan, tenant or configuration, and who owns the variant.
- Permissions, authorisation, approvals and human-in-the-loop points.
- Audit history, snapshots and immutability.
- Limits, quotas, metering and billing.
- Retries, idempotency, locking and ordering.
- Effect on existing records: migrations, backfills, defaults, feature flags, rollout and repair paths.
- External providers and their failure modes.
- Security and privacy: secrets, PII, disclosure to third parties.

## Evidence rules

Label every material claim with how it was established:

- **code inspected**: read at the pinned snapshot, cited by file and line.
- **test inspected**: a test asserts it, cited. Reading a test shows what it asserts, not that it passes.
- **test executed**: the test was run against the snapshot; record the command and result.
- **inferred**: follows from inspected behaviour; the reasoning is stated.
- **unverified**: not checked; say so.

Say plainly when no test covers a behaviour. A detached worktree pinned at the snapshot usually has no dependencies installed, which is a reason to read tests there, not a reason to skip running them: for a load-bearing claim (a locking, ordering, permission or isolation invariant), run the specific test in the main checkout when its HEAD contains the snapshot, using the command form the repository's instruction files mark as safe, and record it as "test executed". Never install dependencies, start services or run migrations for this. The overall verdict may be "cannot determine" when the intent sources are missing or contradict each other; do not force a conclusion. The page is itself an agent-generated interpretation; citations are what let the reader spot-check it, and it never replaces tests or targeted review of important invariants.

## Learning check

The check is a speed regulator, not an exam, and it must let the reader reject the implemented behaviour after understanding it. Rules in `references/page-spec.md`; the essentials:

- Prediction before reveal: scenario questions ("a user in another timezone replies after the cut-off; what happens on the next run?") where the reader commits to an answer first.
- "Spec or agent?" questions on the judgment calls from the reconciliation.
- "Which part changes for another region, product line or configuration?" for domain rules.
- Every answer separates "what the code does" from "is that what you intended", cites its evidence, and offers an "I understand this and I do not want it" outcome that lands in a findings list at the end of the page.

## Writing

The pages are read by a product owner, once, often on a phone. Write to `references/writing-guide.md`: lead with the point everywhere, explain behaviour rather than code, one idea per paragraph, short sentences, plain words, second person for the reader and present tense for the software. It carries word budgets per page type and per card, and the verify step checks them. The first thing on every page is a "Read this first" block of three sentences: what the change does for users, the most consequential decision made without the owner, and what the owner should do with the page.

## Look and structure

Every page, including the index, is built from `assets/template.html` with `assets/explainer.css` and `assets/explainer.js` inlined verbatim. Readers write content, not design: no new stylesheet, no palette, no layout, no rewritten script. One PR explained by seven readers once produced seven unrelated designs, some dark and some light, and the reader could not move between pages; the template exists so that never happens again. The script provides persistence, the controls, the findings list and the copy button, so those never have to be reimplemented. A component the template lacks is a reason to extend the assets in the skill, not to improvise on one page.

## Output

- One directory per run under `.tmp/explainers/` at the repository root (or under `.tmp/explainers/` in the current directory outside a repository), timestamped so runs sort and never collide: `.tmp/explainers/YYYY-MM-DD-HHMM-<slug>/`, where the slug is the spec and milestone, the PR number, or a short name for the change. Everything the run produces lives there: `index.html` (the page itself for a single-page run, the index for a sliced run), one `<slice>.html` per slice, reader reports as `reports/<slice>.md`, and any browser captures. Nothing from a run goes anywhere else in the repository.
- Create the directory; do not assume `.tmp/` exists. Then make sure `.tmp/` is ignored: if `git check-ignore -q .tmp` fails, append `.tmp/` to `.git/info/exclude` (per-clone, touches no tracked file) and tell the user, who may prefer a `.gitignore` entry. Never commit a run.
- A reader report is written for the orchestrating session, not the user: it carries the verdict, open decisions, unverified claims, guide gaps and verification results so the orchestrator can write the index page and its final reply without reading the HTML, and it lives on disk because readers often outlive the turn that launched them. Keep it short and factual; the page is the deliverable.
- In Claude Code, also publish the page as a private Artifact when the user wants a link to revisit.
- Follow the repository's writing conventions (spelling, glossary terms, anything its instruction files forbid in copy). Hyphen-minus only, no en or em dashes. Do not quote verbatim any content the repository's docs say must not be reproduced.

## Success test

The page works if the user can explain the behaviour back, say which decisions were theirs and which were the agent's, and describe a consequence of changing one. Finding a disagreement is not required; a faithful implementation may contain no surprises. An impressive page that fails that test is a failure.
