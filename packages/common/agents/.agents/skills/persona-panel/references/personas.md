# Designing the persona roster

A roster is useful when it spans the people who decide, use, block and champion, not just the obvious buyer. Build it on three axes and check the grid has no empty rows that matter.

## Axes

- **Role:** buyer or owner, day-to-day user, manager or ops, specialist user (the person whose job the product touches, e.g. a processor), gatekeeper (compliance, IT, a channel partner), champion (the person who forwards the page internally).
- **Experience or stage:** new to the industry, starting their own business, established solo, senior veteran, owner of a large firm, successor taking over.
- **Personality:** early adopter, curious sceptic (burned before), senior know-it-all, critic (picks apart copy and UI), time-poor skimmer, anxious about automation, brand-protective, relationship-driven, impatient phone-first.

Add 2 to 4 **adjacent or out-of-scope** personas (a neighbouring vertical, another country, a partner). They show where the message leaks and whether "not for me yet" is communicated honestly.

## Size

| Round | Personas | Models per persona | Runs |
|---|---|---|---|
| Wide first round, many concepts | 10 to 14 | 3 or 4 | 40 to 56 |
| Focused follow-up, 2 to 4 concepts | 6 to 9 target personas | 2 | 12 to 18 |

For a follow-up, keep only the personas closest to the target audience plus the gatekeeper whose approval the sale depends on.

## Persona card fields (study.json)

- `id`: P01, P02, ... Keep ids stable across rounds so results compare.
- `name`: a plausible local name. Check it doesn't collide with names or places used in the concepts (a collision reads as flattery and biases the score).
- `role`: one line with role, business size and tenure.
- `personality`: the type plus one clause on how it shows.
- `segment`: a short key used for segment tables (see `segments` in study.json).
- `bio`: 4 to 7 bullets. Include:
  - age, location, business size and volume
  - tools they use today and what they dislike about them
  - a specific past bad experience relevant to the product
  - how they read (skims on phone, reads fine print, forwards to the boss)
  - the 2 or 3 questions that decide whether they act

Write bios in second person ("You are ...") in the persona file header, as `init_study.py` does. Use they/them unless the persona's pronouns are part of the design.

## What not to put in a persona

- Anything from the product's internal docs or roadmap. Panellists must only know what a real prospect knows.
- The study's hypotheses, or which concept the team prefers.
- Results from earlier rounds. Each round starts cold so the scores aren't anchored.
