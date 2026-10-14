You are writing the final summary of a simulated round of discovery interviews for <DECISION_MAKER>. They should be able to read it in about 10 minutes, and use it to prepare interviews with real people.

<PERSONAS> were interviewed about <ABOUT>, each on <MODELS>, in <RUNS>. The interviewer named no product and asked about the participants' work. Every participant was a model playing a persona, and the interviewer was a model too.

## The guide the interviewer had
**Learning goals:**
<GOALS>

**Topics:**
<TOPICS>

## Inputs (all under `<STUDY_DIR>/`)
- `<TALLIES>` and `<FIGURES>`: the tallies for each theme and for the round, the incomplete interviews, and every verified quote of the notes with the run and the exchange it was found in.
- `<THEMES>`: each theme's name, definition and notes.
- `<QUAL>`: the analysts' account of each interview and their evidence notes.
- `<CRITIQUE>`: the critics' marks on the interviewer's questions, a final check of each interview, and what each participant's private situation card held that the interview found or missed.
- `<CHECKS>`: data-quality notes on the interviews.
<EXTRA_CONTEXT_FILES>

Open nothing else: not the transcripts (`interviews/`, `analysis/transcripts/`), `prompts/`, `study.json` nor a study brief. The summary rests on the coded notes and the tallies.

## Output: `<STUDY_DIR>/analysis/SYNTHESIS.md`
Open the file with a `#` title and, directly under it, this line on its own, word for word:

<NOTICE>

Then these ten sections, in this order:

1. **What this is.** Two or three sentences on what was run, then every limit below, in plain words of your own:
   - The participants' histories are invented. A persona has no past, so a model made up each incident, figure and date, and each deeper question made up more.
   - A model is more articulate, more cooperative and more self-aware than a busy person. Nothing here shows what real people would say.
   - What one model's version of a persona said and another's did not is model taste.
   - An interviewer and a participant on the same model agree with each other more readily.<SAME_MODEL_NOTE>
   - The critique is one model's opinion of another's questions. It teaches the method and certifies no interview.
   - Every count is of simulated participants. None says how common a problem is or what it costs.
   - So the output is hypotheses and a rehearsed guide, never evidence about real customers.
2. **Each learning goal.** What was heard, how strongly (how many simulated participants, how many unprompted, how many with an incident, what they had done about it), and what was heard against it.
3. **Problem themes.** One table from `quant.md`, then a line or two on each theme. Lead with the themes that have unprompted incidents and effort behind them, not the ones most mentioned, and name each theme whose notes rest on a flagged question.
4. **What was not a problem.** What participants said does not trouble them, each as narrowly as its note states it, and the topics they did not care about, by the rule on `NON-PROBLEM` notes below. Give it the room section 3 gets: a problem that is not there is the cheapest thing this round can find.
5. **How they cope now.** Workarounds, tools, what is spent and who decides, as told.
6. **Where segments differ, and where models disagree.** A theme a persona raised on one model and not on another is model taste: say so, and lean on it less.
7. **Quotes.** Eight to twelve that carry the findings, grouped by theme, each in the form under Quotations, below.
8. **How the interviews went.** The critique's counts by kind. The two or three most instructive exchanges, good and bad, with the better question beside each bad one. The findings that rest on a flagged question. What the situation cards held that no interview found. The tallies say which critic marked each interview. Critics do not mark alike, so the marks of different critics are not comparable: a difference in marks between interviews that different critics read is no finding about the interviews, the personas or the segments, and is never reported as one.
9. **For the real interviews.**
   - The hypotheses worth testing, each a statement that a real conversation could contradict.
   - A revised guide: the topics to keep, drop, add or reword, each with its opener and the reason. Hold every question you propose to the method section 8 reports on: one question, about a specific past event, that presumes no problem. *What do you chase subcontractors for each week?* presumes the chasing. *Take me through the last pay run.* does not.
   - The next three learning goals, written as things to find out. One is the uncomfortable one: the answer that could end the idea.
10. **What remains unproven.** Keep four conclusions apart: a problem exists, this segment puts it first, a solution delivers, a buyer pays. This round proves none. It offers guesses about the first two, and nothing on the last two: no solution was shown and nobody was asked to pay. For each, say what would test it with real people.

## Quotations
A script checks every quotation in the file against the transcripts and lists each one it cannot find. Nothing is sent back to you.

- **The form:** the words between double quotation marks, then at once the run and the exchange in brackets, as in `"I was still waiting on the Monday." (P02-a, 7)` (an invented example).
- **One exchange, one unbroken stretch** of its question or its answer, character for character: nothing left out, nothing added, no ellipsis, no square brackets, no corrected spelling. Punctuation of yours goes outside the marks.
- **A participant's words come from one list:** the verified quotes of `analysis/quant.md`, each in this form already, with the run and the one exchange a script found it in. Copy the words and the attribution from there, and never work an exchange out from the range in a note's `Turns`. Paraphrase everything else without marks: a quotation in an analyst's prose, which no script has checked, a quote an input marks as unverified, and words you would have to reconstruct.
- **A question's words,** with the run and the exchange, come from a critic's file, under *Worth learning from*.
- **The bracket `(run id, exchange)` is a quotation's attribution and stands nowhere else.** The script lists every such bracket that does not come at once after a closing double quotation mark: after a paraphrase, after words in single quotation marks or guillemets, in a code span or a fenced block. Point to an exchange you do not quote in words, as in *exchange 7 of P02-a*. A summary in which the script can verify no quotation fails the check.
- **Quotation marks are for attributed quotations and nothing else.** Any other text between double marks is listed as a quotation with no attribution, whatever its length. A term, a label (a flag, a signal, a move), a title, a theme's name and a question you propose for the real interviews go in italics, never in quotation marks of any kind: none is anybody's words.

## Rules
- Give every count as simulated participants, as in *4 of 12 simulated participants*, and take it from `quant.md`. Never recount, never turn a count into a percentage, and never write *frequency*, *prevalence*, *most* or *common* of anyone outside this panel.
- Say what kind of evidence stands behind a claim: an incident or a generality, unprompted or prompted, effort or none. Never report an opinion, a promise or a feature request as a problem found.
- A `NON-PROBLEM` note is about its own statement, not about the theme or the topic it sits under. For each theme and each topic the tallies put a participant in exactly one of three groups: raised it, said it is not a problem (a `NON-PROBLEM` note there and no other note), or both. Only the second group supports a sentence that a theme or a topic did not trouble someone. The third holds a `NON-PROBLEM` note and at least one other note, and that other note need not be trouble: it may be a workaround, a person, money or context as well as a pain, and its `Signal` says which. So report a participant in the third from their notes: the part they said is fine, and what else they told of there, called trouble only where that note is a `PAIN` or an `OBSTACLE`. Being in the third group never shows, by itself, that a theme or a topic troubled someone. Never add the groups into one total of people.
- Say of the guide only what it says, above. It names areas to ask about and claims nothing about them, so never write that it assumed, expected or hoped for an answer.
- Report from an incomplete interview only with a note that it was cut short. It is in no headline table.
- At most 2,500 words, tables and quotes included: it is read in one sitting, and a longer summary is skimmed. Cut a sentence before a finding. Prefer tables and bullets. Every claim traces to the inputs.
- No em or en dashes in your own words.
- Write only `SYNTHESIS.md`, and never use git.
- If you are blocked from writing the file, return the complete document as your reply instead.

**Sources.** The weight given to incidents, effort and unprompted mentions, the three learning goals with an uncomfortable one, and the four conclusions kept apart are the method of the book The Mom Test, in this skill's own words. The ten sections, the limits, the reading of model against model, the rule on counts and the quotation form are adaptations for a simulation.

When done, reply with section 2 verbatim.
