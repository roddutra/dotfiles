# Archiving a study

Keep two tiers:

1. **Distilled findings in the product repo** (for example `docs/research/<topic>-<yyyy-mm>/README.md`): the headline results, ICP signal, recommendations, decisions and a link to the archive. This is what future agents working on the product will find.
2. **The full study in a separate research repo**, laid out as below. Bulk that can be regenerated is dropped.

## Research repo layout

```
<research-repo>/
  README.md                          index of studies, newest first
  customer-research/
    <yyyy-mm-dd>-<topic>/            date the study finished + short topic slug
      README.md                      study card: question, rounds, method, headline, links
      report/index.html              the visual report (source of any published page)
      findings/                      synthesis per round (round-1.md, round-2.md) and the ICP
      inputs/                        briefs, decisions and constraints given to designers
      concepts/<id>/                 each concept's source, once, with its gallery index
      screenshots/<id>--<page>.jpg   one full-page screenshot per page (snapshot.py)
      panel/round-<n>/               one folder per panel round (archive.py)
        study.json  study-brief.md  key.md  runs.json  followups.json  panel-instructions.md
        personas/  prompts/  analysis/  scripts/ (only if the round used one-off scripts)
```

Dropped because they regenerate: `panel/sites`, or `sites/` in a text-only study (from `concepts/` + `key.md`), `panel/materials` (`capture.py`), scratch screenshots, designer verification shots.

Not archived either:

- `logs/`: the raw harness output of every process, which contains everything a panellist read and wrote. It also holds `earlier-sessions.json`, the only note of the sessions that runs replaced by `init_study.py --force` left with their harnesses: run `launch.py <study> purge-sessions` before deleting the study directory if those sessions should go.
- `.launch.lock`

What travels with a round besides the persona files:

- `analysis/`, whole: `usage.md`, `runs.csv`, `answers.csv` and `lines.csv` with it. An archived round still analyses.
- `study-brief.md`: what was agreed with the user, hypotheses included.
- `followups.json`: the follow-up questions asked and how each run answered. The answers themselves are in the persona files. `archive.py` refuses a study with a follow-up that is not settled: its persona file may hold what settling will reject, and an archive has no `logs/` to put it back from. It also refuses a study that a launcher has, and holds the study lock while it copies the round, so no follow-up starts under the copy.

## Synthetic panel notice

Everything archived carries the notice, word for word (`references/communicating.md`), so a file opened on its own is never taken for research with real people.

- **`archive.py` adds it to every markdown file it copies that lacks it:** under the heading the file opens with, or at the very top when it opens with anything else. A file that has the line anywhere is left alone, so archiving twice changes nothing.
- **CSV, JSON and every other kind of file are copied byte for byte,** as is everything `--concepts` copies.
- **The lead adds it to what the script does not write:** under the title of the study card README, of each file in `findings/`, of the product repo's findings README and of the report page. A synthesis copied into `findings/` already has it. Check it survived any editing.

## Steps

1. `archive.py <study-dir> --dest <repo>/customer-research/<date-topic>/panel/round-<n> --concepts` for each round (use `--concepts` once).
2. Write the study card README and copy the synthesis into `findings/`. Each carries the synthetic panel notice under its title.
3. Copy the report source into `report/`. A published artifact link is account-private; keep the HTML in the repo.
4. Add a line to the repo README index.
5. Mark anything invented for the concepts (placeholder prices, unconfirmed claims) as unconfirmed in the study card, so later readers don't treat it as fact.
6. Check size before committing: `du -sh`. Screenshots at 50% JPEG are about 100 to 700 KB per page; use Git LFS only if a study exceeds ~100 MB.
