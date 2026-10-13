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

- `id`: P01, P02, ... Keep ids stable across rounds and studies so results compare. No hyphens: file names split on them.
- `name`: a plausible local name. Check it doesn't collide with names or places used in the concepts (a collision reads as flattery and biases the score).
- `role`: one line with role, business size and tenure.
- `personality`: the type plus one clause on how it shows.
- `segment`: a short key used for segment tables (see `segments` in study.json).
- `slug`: optional, the name as it appears in file names. Default: the name in lower case with hyphens.
- `variant_of`: optional, the id of the persona this one is a variant of (below).
- `bio`: 4 to 7 bullets. Include:
  - age, location, business size and volume
  - tools they use today and what they dislike about them
  - a specific past bad experience relevant to the product
  - how they read (skims on phone, reads fine print, forwards to the boss)
  - the 2 or 3 questions that decide whether they act

Write bios in second person ("You are ...") in the persona file header, as `init_study.py` does. Use they/them unless the persona's pronouns are part of the design.

## Roster grid

`roster.py <study> grid` writes skeleton personas into `study.json` from its `roster` block, so the grid is covered before any bio is written.

```json
"roster": {
  "roles": ["Staff", {"role": "Owner of a 2-site cafe", "segment": "owner"}],
  "personalities": ["Curious sceptic: burned before, needs proof", "Time-poor skimmer"],
  "stages": ["new to the industry", "20 years in"],
  "caps": {"personas": 8, "runs": 48}
}
```

- `roles`: at least one. A string is the role line, and its segment is the same words as a key ("Staff" gives `staff`). An object gives both.
- `personalities`: at least one string.
- `stages`: optional. A stage is added to the role line after a comma, so write it as it should read there.
- `caps.personas`: optional, the most personas the study may have.
- `caps.runs`: optional, the most runs (personas x model entries x replicates). It needs `models` in `study.json`. A roster over it is refused, with the arithmetic.

What the grid guarantees when `caps.personas` is below roles x personalities x stages:

- Every role and every personality appears at least once. A cap too small for that is refused, with the least that would do, and nothing is written.
- Every stage appears too when the cap is at least the number of stages. Otherwise the stages left out are named.
- The rest of the cap goes to the combinations whose role, personality and stage have been used least.
- The selection is the same for the same `seed` and roster.

Then write the personas:

1. Each skeleton has an id, the name `TODO`, a role line, a personality, a segment and an empty bio. Give each a name and a bio as above. `init_study.py` refuses a study while a persona is named `TODO` or has no name.
2. Sharpen the role line and personality where the grid's words are too generic. The grid is a coverage check, not the persona.
3. Add the adjacent or out-of-scope personas by hand. The `roster` block can stay: no other script reads it.

Running `grid` again never changes a written persona:

- Skeletons nobody has touched are replaced.
- With written personas in `study.json` it stops, unless `--append`: they stay, the new skeletons follow them with the next ids, and the caps count both.
- A written persona whose role line and personality are still the grid's words counts as that combination, and towards its role, personality and stage appearing. One whose role line was rewritten is not recognised: it takes a place under the cap and covers nothing, so check for a double.
- `--append` is refused, with the least cap that would do, when the places left beside the written personas cannot cover every role and personality, and every stage where the cap is at least the number of stages.

## Reusable rosters

A roster file is a JSON file, `{"personas": [...]}`, kept in the project's own repository. It lets later studies use the same people under the same ids, so a persona's results compare across studies and rounds.

| Command | Does |
|---|---|
| `roster.py <study> export --to <file>` | Copies every persona of the study into the file, merging by id |
| `roster.py <study> import --from <file> [--ids P01,P03]` | Copies personas from the file into `study.json`, all of them or the ones named |

- **An id means one person across studies.** Export stops when the file holds a persona with the same id and different content. Give the study's persona a new id, or pass `--update` to replace the file's.
- **Import never changes a persona in a study.** One already there with the same content is skipped, and one with the same id and different content stops the import.
- **Only the persona card moves:** `id`, `name`, `slug`, `role`, `personality`, `segment`, `bio` and `variant_of`. No concepts, notes, hypotheses or results.
- **A variant travels with its parent.** Importing one needs its parent in the study or in the same import.
- **Export stops while the study has a skeleton,** and refuses a file under the study's `panel/`.
- **To extend an imported roster with a grid,** import first, then `roster.py <study> grid --append`.
- **After a study is scaffolded,** a changed roster takes effect only with `init_study.py --force`, which resets every run.

A persona that keeps its id must stay the same person. Give a persona whose bio you rewrite for a new study a new id, or its results will be compared with someone else's.

## Variants

A variant is a persona with `"variant_of": "<id>"`: a copy of that persona with one trait changed, to test what the trait does. Example: the same cafe owner, as a curious sceptic and as an early adopter.

- Copy the parent's card, give it a new id, and change one of `role`, `personality`, `segment` or `bio`. The analysis lists which of the four differ, so a second change shows.
- Keep the name. The id tells the two apart, and the tables mark the variant "(variant of P01)".
- `variant_of` must name another persona in the study that is not itself a variant.
- A variant has its own runs, so each one adds a persona's worth of cost.
- A variant reviews the concepts in its parent's order, so the two differ in the trait and not in what they read first.
- Reading the result, and keeping a variant out of the headline (`analyze.py --exclude-persona <id>`): `references/method.md`, Replicates and variants.

## What not to put in a persona

- Anything from the product's internal docs or roadmap. Panellists must only know what a real prospect knows.
- The study's hypotheses, or which concept the team prefers.
- Results from earlier rounds. Each round starts cold so the scores aren't anchored.
