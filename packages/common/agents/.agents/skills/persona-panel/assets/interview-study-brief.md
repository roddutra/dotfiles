# Interview study brief

Lead only. Copy this file to `<study>/study-brief.md`, beside `study.json`, and fill it in with the user before writing `study.json`. It holds the team's hypotheses, so it stays there and is never given to an interviewer, a participant, an analyst, a critic or the writer. Never put it, or a copy of it, under `panel/` or `interviewer/`: `init_study.py` refuses to scaffold while one is there. It cannot be a `synthesis.context_files` entry either, under any name.

The headings follow the preparation the book The Mom Test asks for before any conversation, in this skill's own words. "Leak terms", "What must stay local", "Scale" and everything said of a simulation are this skill's.

## Decision

What the round informs: the decision, who makes it, and what each outcome would change. A round that could change nothing is not worth running.

## Hypotheses

What the team believes now, each written as unproven: the problem it expects to find, who has it, and the idea or product it has in mind. Apart from `leak_terms`, this file is the only place in the study where the idea is named.

## What would change the decision

The findings that would make the team stop, narrow or change course. Write them before the round, so that a disappointing result cannot be explained away afterwards.

## Segment

Who is interviewed: the role, the situation in which the work comes up, who is in and who is out. Name the person who does the work, the person who pays for it and anyone who can refuse, where they differ: each is a persona, and a `segment` of its own if its topics differ. List the roles the round leaves out.

## Learning goals

Three for each type of person, each written as something to find out, never something to prove. One of them is the uncomfortable one: the question whose answer could end the idea. Each becomes a `goals[].learn`, and none may name the idea.

## Topics

For each topic:
- its neutral `area`, which the interviewer may say aloud
- its `opener`, a question about a recent real event that names no problem
- the goals it serves
- its cap in exchanges
- the segments it is kept to, if any

Put a broad topic first, one that names no area, so that what a participant raises unprompted can be told from what was put to them. Test each opener three ways: could a polite yes answer it, does it ask about something that has not happened, and does it carry the answer the team hopes for?

## Leak terms

Every word that would tell a participant what the team hopes to hear, for `leak_terms`:
- the product's name and any working title or code name
- the team's own words for its idea, and the names of its features
- any phrase from "Hypotheses" that a participant would not use unprompted

The launcher holds back a question that contains one, and `init_study.py` refuses a goal, an opener, an `area` or `interview.about` that does. `interview.about` names an area of work, never the idea. The interviewer states it to the participant as the purpose when it opens every interview, so it must name the subject area without the user's product or the team's hypothesis.

## What this round cannot prove

Say it before the results arrive. The participants are models with invented histories, so the round shows nothing about how often a problem happens, what it costs, or whether anyone would pay. It gives hypotheses and a rehearsed guide. Four conclusions stay apart: a problem exists, this segment puts it first, a solution delivers, a buyer pays. This round offers guesses about the first two. Name the step with real people that follows it.

## What must stay local

What may not leave this machine or be committed: which providers may receive the personas and the guide, and what the archive may keep.

## Scale

The personas, models and replicates agreed, the caps on an interview and on each topic, and the cost ceiling the user accepted.
