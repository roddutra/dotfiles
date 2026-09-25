You are writing the final synthesis of a simulated customer research study for <DECISION_MAKER>. They should be able to read it in about 10 minutes and act on it.

<N_PERSONAS> personas reviewed <N_CONCEPTS> concepts (<LABELS>) of <WHAT_WAS_REVIEWED> for <PRODUCT>, on <MODELS> (<N_RUNS> runs). Panellists saw only neutral labels. The key is in `<STUDY_DIR>/key.md`: use the real concept names in the synthesis.

## Inputs (all under `<STUDY_DIR>/`)
- `panel/_panel-instructions.md`: what panellists were asked.
- `analysis/quant.md` and `analysis/quant.json`: the numbers. Segment and model-exclusion variants may sit beside them.
- `analysis/checks.md`: data-quality flags.
- `analysis/qual-*.md`: themes, quotes and per-concept findings.
<EXTRA_CONTEXT_FILES>
- You may spot-check persona files in `panel/personas/` to confirm a quote.

## Output: `<STUDY_DIR>/analysis/SYNTHESIS.md`
1. **The answer in one screen.** Eight to ten bullets: what won and for whom, why, what failed, what is still missing, and what to do next.
2. **Method and how much to trust it.** Personas, models and method in brief. What is robust across models, what is model-dependent, and known limitations (static screenshots, capture artefacts, repetition across similar concepts, flagged runs, background leakage).
3. **Leaderboard.** Overall, the headline segment, a compact per-segment view, and a short model-skew note.
4. **Per concept.** Two to five lines each: what to keep and what to drop.
5. **What the target reader needs.** The questions a page must answer, the asks, and the objections and deal-breakers, ranked by how often they came up.
6. **Trust and risk.** Demo or copy lines that contradicted the page's own promises (never repeat these), and the trust lines that landed.
7. **Language.** Lines to reuse and words to drop, quoted exactly.
8. **Structure and design lessons.**
9. **Who it resonated with (ICP signal).** Use the persona-fit table in quant.md plus what each persona said they'd need to say yes. Separate ideal, strong, not-yet, gatekeeper and out-of-scope profiles, with the reason for each.
10. **Recommendations.** A prioritised list tied to evidence, including the best blocks to borrow from specific concepts.
11. **Decisions for <DECISION_MAKER>.** Only what needs a human call, including any claims the concepts invented that need confirming.

## Rules
- Concise and concrete; prefer tables and bullets. Every claim traces to the inputs.
- Quote exactly, with a run citation (for example "P04-opus").
- No em or en dashes.
- Write only SYNTHESIS.md, and never use git.
- If you are blocked from writing the file, return the complete document as your reply instead.

When done, reply with section 1 verbatim.
