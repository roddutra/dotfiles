You are writing the final synthesis of a simulated usability study for <DECISION_MAKER>. They should be able to read it in about 10 minutes and act on it.

<PERSONAS> attempted <TASKS> in <PRODUCT>, running at `<TARGET>`, on <MODELS>, in <RUNS>. Each panellist drove a browser, thinking aloud, and logged every step with a screenshot.

## Inputs (all under `<STUDY_DIR>/`)
- `panel/_panel-instructions.md`: what panellists were asked, the tasks and their step limits.
- `analysis/quant.md` and `analysis/quant.json`: completion claimed and checked, every mismatch, steps taken, where runs stopped, stuck points and scores.
- `analysis/checks.md` and `analysis/lead-notes.md`: data-quality flags, and the claims the lead checked.
- `analysis/qual-*.md`: the analysts' findings, each with the steps it cites.
<EXTRA_CONTEXT_FILES>
- You may spot-check a persona file in `panel/personas/`, and a step log (`steps.jsonl`) or a screenshot in `panel/evidence/<run id>/`, to confirm a finding.
<FOLLOWUPS>
<DEBRIEFS>

## Output: `<STUDY_DIR>/analysis/SYNTHESIS.md`
Open the file with a `#` title and, directly under it, this line on its own, word for word:

<NOTICE>

1. **The answer in one screen.** Eight to ten bullets: which tasks people could complete and which they could not, the worst stuck points, and what to fix first.
2. **Method and how much to trust it.** Personas, models, tasks and step limits in brief. Both standing cautions, in full (see the rules). What held across models, what was model-dependent, and the known limitations: runs that did not finish, checks that failed to run, tasks with no success check, flagged runs.
3. **Completion by task.** One table: for each task, completed as claimed beside completed as checked, with the counts from `quant.md`. Then every mismatch, and what it shows.
4. **Stuck points, ranked by how many runs hit them.** For each: the task and the screen, what panellists saw and expected, what happened, and the fix it suggests.
5. **Per task.** Two to five lines each: how runs went about it, steps taken against the limit, and where they stopped.
6. **Who struggled.** By persona and by model: which differences follow from the person, and which from the model.
7. **Language.** The words panellists looked for beside the words the product uses, quoted exactly.
8. **What already works,** and should stay as it is.
9. **Recommendations.** A prioritised list, each tied to its stuck point or mismatch and to the steps that show it.
10. **To test with real people.** Each main finding restated as a hypothesis, with the cheapest way to test it.
11. **Decisions for <DECISION_MAKER>.** Only what needs a human call.

## Rules
- Cite the step for every finding: run id, task, step number and screenshot file name, for example "P04-opus, T1 step 9, `T1-9.png`". Leave out a finding that has no step to cite.
- Report claimed completion beside checked completion wherever you give either. Never give one figure as "completion".
- A check that failed to run is no verdict. Never count it as a task that was not completed.
- A test account's name that is not the persona's comes from the test. Never report it as a finding about the product.
- The standing cautions, in section 2 and wherever a result could be read as a fact:
  - An agent reads a page more thoroughly than a person and does not get bored, so real people will do worse wherever a task takes patience or close reading.
  - Every result is a hypothesis to test with real people, not a measurement of them.
- Never write a password, a code or a token. If an input holds one, don't quote it: name the file and the line for the lead.
- Concise and concrete; prefer tables and bullets. Every claim traces to the inputs.
- Quote exactly, with its run.
- No em or en dashes.
- Write only SYNTHESIS.md, and never use git.
- If you are blocked from writing the file, return the complete document as your reply instead.

When done, reply with section 1 verbatim.
