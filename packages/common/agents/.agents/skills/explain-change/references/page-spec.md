# Explainer page spec

One long page, section headers, a table of contents, no top-level tabs. Self-contained HTML built from `assets/template.html` with `assets/explainer.css` and `assets/explainer.js` inlined unchanged; the template shows every component with its classes and data attributes, and this file says what goes in each section. Deviations sit above the fold on every page; the reader must see them before any teaching.

## Index page for a sliced run

When the change was split into slices, `index.html` is the page the reader opens first. It carries: the pinned snapshot and intent sources once; the overall verdict; a ranked list of slices by consequence, each with its verdict, its two or three most consequential deviations or decisions, and a link; the deviations and decisions that cross slices, with the same accept, reject and discuss controls; a combined findings list that merges the slice lists (read from each slice's `localStorage` key when available); and the guide-gap follow-ups. It has no walkthrough or learning check of its own.

## Sections, in order

1. **Header.** Title, then the "Read this first" block: three sentences, what the change does for users, the most consequential decision made without the owner, what to do with this page. Then the meta list: spec and milestone if any, pinned commit or range, date, intent sources used, the revision surrounding code was read from, evidence legend (code inspected, test inspected, test executed, inferred, unverified), and a one-paragraph verdict: matches intent, matches with noted deviations, diverges, or cannot determine (intent missing or contradictory; say which).
2. **Deviations and decisions.** Two lists, consequential items first. Each card is written for someone who will not read the code, and answers "so what?" before anything else:
   - Title: the choice as behaviour a user or operator would notice, in plain words. Never a flag, class or method name in a title.
   - You asked for / What shipped (deviations only): both in plain words.
   - In practice: one concrete moment played out step by step with example inputs, so the reader can picture it happening live.
   - Users experience: what the end user or operator sees, hears or waits for.
   - Your options: the shipped behaviour plus two or three alternatives, each stated as what users would experience and what it costs. This is what accept, reject and discuss are choosing between.
   - Decided by, and why if recorded.
   - Evidence: one muted line at the end with the citation and tier. It is there for spot-checks, not for reading.
   Each item carries a control: accept, reject, or discuss. Rejected and discuss items are collected into the findings list at the end.
3. **Intent ledger.** A table of every requirement, constraint and non-goal from the intent sources: source (user instruction, spec, plan, agent account), status (matched, changed, deferred, missing), where it landed, evidence. Additions with no intent source get their own rows marked "unrequested". Where a later user decision superseded the spec, the row cites both and counts the later one.
4. **What to remember from the surrounding system.** Not a beginner tutorial. The three to six facts about the existing system the change relies on, one or two sentences each, each linking the guide section that owns it.
5. **Intuition through scenarios.** Two to four real journeys (an end user, an operator, an external system) with toy data, one of them a failure or exception path. Diagrams here: a simplified UI sketch for surface changes, a data-flow figure with example payloads for system changes. Pick a small number of diagram families and reuse them.
6. **Walkthrough.** The change in conceptual order, grouped by concept, not by file. Each concept: what it does in one paragraph, then the citation. Code excerpts only where the shape matters; otherwise describe and cite.
7. **Boundary checklist.** One row per boundary the change touches: what the code does, spec-decided or agent-decided, evidence.
8. **Microworld** (only when warranted). An interactive model of the time-varying state, seeded with real examples from tests, with a note on what was validated.
9. **Learning check.** Rules below.
10. **Findings and follow-ups.** Everything rejected or marked discuss above; guide sections the change should have updated; unverified claims that need a test or a look.
11. **Provenance.** Commit, files read, tests run, and what was not checked.

## Learning check rules

- Five to eight questions for a milestone; fewer for a smaller capability. Mix:
  - Scenario prediction (majority): the reader writes or picks a prediction before the answer reveals.
  - "Spec or agent?": for judgment calls from section 2.
  - Variability: which part would change for another region, product line, tenant or configuration.
  - At most two multiple-choice; multiple-choice with fewer than four plausible options is guessable.
- Medium difficulty: answerable only with the substance of the change, never a gotcha.
- Each answer has these parts: what happens (plain words), what users experience, why it matters, a muted evidence line, and a control asking "is that what you intended?" with accept, reject, or discuss. Reject and discuss feed the findings list.
- Free-recall questions reveal a model answer for self-grading rather than being auto-graded.
- The bundled script handles persistence (`localStorage` keyed by snapshot id and page path, try/catch, status line in the header), the accept, reject and discuss controls with an optional note per item (shown once a choice is made, exported under the item in the markdown), reveal, the findings list, and copy as markdown with the textarea fallback. Accepted items appear in the export only when they carry a note. Use its ids and attributes exactly; do not reimplement any of it. Never rely on a download link.
- No external requests: no CDN scripts, fonts, or fetches.

## Diagrams and code

- No ASCII diagrams. Use the template's figure families: `.flow` steps for a journey (with `is-human`, `is-agent`, `is-fail` variants), `.lanes` for parallel actors, `.ui` for a simplified screen, `svg.diagram` for data flow with example payloads. Pick a small number of families and reuse them; pills carry the same colour meaning on every page.
- Code blocks use `<pre>`; a styled `div` must set `white-space: pre` or `pre-wrap`. Check every code block before saving.
- Callouts for key definitions, edge cases and the repository's canonical term for anything named.
- Writing: `writing-guide.md` governs voice, words, budgets and layout. No rationale recaps, no transitions that restate the previous section.
