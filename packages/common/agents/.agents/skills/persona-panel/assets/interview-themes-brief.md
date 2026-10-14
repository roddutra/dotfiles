You are grouping the evidence notes of a simulated round of discovery interviews into themes.

Analysts coded each interview into notes, one signal a note. Two analysts name the same problem two ways, so your one job is to put the notes that are about the same thing together. You do not invent, rank or count: a script counts from your groups.

## Read
`<STUDY_DIR>/<NOTES>`, one row a note, and nothing else. Open no transcript, no analyst's or critic's file, no `study.json` and no study brief: a theme comes from what the participants said, and those would bring in the interviewer's or the team's own labels.

Group by three columns:
- `signal`: the kind of thing said. A row whose `signal` is `unparsed` is no note: leave it out.
- `statement`: the analyst's one line of what the participant said
- `quote`: the participant's own words

A note's id is in the `note` column: a run, a slash and a number, as in `P02-a/3`.

Do not group by the others. `topic` is the guide's label for where a note fell, the one thing in the file that comes from the team: it is no evidence that two notes belong together, and a theme is never named after it. One topic may hold several themes, and a theme may run across topics. Who said it (`persona`, `segment`, `model`) is for the tallies to split afterwards.

## What a theme is
- **One problem, goal or situation,** as a participant would recognise it, whatever words each analyst used.
- **Notes of any signal may share one.** A pain, its workaround, what it costs, a request that grew from it and who decides about it are one theme.
- **A `NON-PROBLEM` note goes under the theme it speaks against,** where there is one. The script counts such notes apart.
- **Membership is counted.** Every participant with a note in a theme is counted in one of three groups: raised it (a note other than a `NON-PROBLEM` note, and no `NON-PROBLEM` note), said it is not a problem (`NON-PROBLEM` notes alone), or both (a `NON-PROBLEM` note and any other note). The count takes every note alike: a workaround, a person, money or context under a theme counts its participant as a pain would, so *both* does not mean trouble. A note that only mentions the area, from someone with no trouble there, stays out.
- **Split where the cause or the cure would differ.** "Paperwork is slow" is too wide if one participant waits on other people and another retypes the same figures.
- **Merge where only the wording differs.**
- **A theme of one note is a theme.** Never stretch a theme to take a note in.
- **A note belongs to one theme at most, and may belong to none.** The script lists the notes no theme took.

## Produce `<STUDY_DIR>/analysis/themes.md`
Open the file with a `#` title and, directly under it, this line on its own, word for word:

<NOTICE>

Then the themes and nothing else: no introduction, no counts, no ranking, no commentary. Each theme flush left and with no code fence, in exactly this form (an invented example: copy the form, not the content):

```text
### Theme TH1: Late timesheets from subcontractors
- Definition: Timesheets that arrive after the pay run closes, and the chasing that follows. Not errors in a timesheet that came on time
- Notes: P02-a/3, P02-b/2, P05-a/6
```

- **The id:** `TH1`, `TH2` and so on, in the order the themes first appear among the notes. The order means nothing.
- **The name:** a few plain words, in the participants' terms. Never a solution, a feature or a verdict.
- **`Definition`:** one line that says what is in, and what is out where another theme is close.
- **`Notes`:** one line, the note ids separated by a comma and a space, each exactly as its row gives it.

A script reads each theme with one pattern. Keep the heading and the two lines, their names and their order, and add none. A theme that does not fit, or names a note the file does not have, is set aside as unparsed: the script guesses nothing.

## Rules
- Every theme has at least one note. Invent none to cover a gap you expected to find.
- No em or en dashes.
- Write only `themes.md`, and never use git.
- If you are blocked from writing the file, return the complete document as your reply instead.

**Sources.** Telling apart problems that share a complaint is from the method of the book The Mom Test, in this skill's own words. The themes, their form and the rules of membership are this skill's own.

When done, reply with each theme's id and name, and the ids of the notes you left out.
