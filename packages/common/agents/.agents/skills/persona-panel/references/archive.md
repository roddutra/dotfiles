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
        study.json  key.md  runs.json  panel-instructions.md
        personas/  prompts/  analysis/  scripts/ (only if the round used one-off scripts)
```

Dropped because they regenerate: `panel/sites` (from `concepts/` + `key.md`), `panel/materials` (`capture.py`), scratch screenshots, designer verification shots.

## Steps

1. `archive.py <study-dir> --dest <repo>/customer-research/<date-topic>/panel/round-<n> --concepts` for each round (use `--concepts` once).
2. Write the study card README and copy the synthesis into `findings/`.
3. Copy the report source into `report/`. A published artifact link is account-private; keep the HTML in the repo.
4. Add a line to the repo README index.
5. Mark anything invented for the concepts (placeholder prices, unconfirmed claims) as unconfirmed in the study card, so later readers don't treat it as fact.
6. Check size before committing: `du -sh`. Screenshots at 50% JPEG are about 100 to 700 KB per page; use Git LFS only if a study exceeds ~100 MB.
