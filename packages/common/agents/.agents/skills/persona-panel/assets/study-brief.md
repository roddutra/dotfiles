# Study brief

Lead only. Copy this file to `<study>/study-brief.md`, beside `study.json`, and fill it in with the user before writing `study.json`. Never put it, or a copy of it, under `panel/`: it holds the team's hypotheses, and `init_study.py` refuses to scaffold while one is there. It cannot be a `synthesis.context_files` entry either, under any name: an analyst who knows the hypotheses tends to find them, so the scripts refuse it.

## Decision

What is being decided, who decides, and what each result would change. Which concepts are compared.

## Audience

The target reader, the people whose approval the sale depends on, and who is out of scope.

## What is fictitious

Everything in the concepts that is invented or a placeholder: demo companies, names, prices, claims not yet confirmed. Each one needs a `context_notes` line in `study.json`.

## Hypotheses

What the team expects or hopes to see, and what result would change its mind.

## What must stay local

What may not leave this machine or be committed: which providers may receive the materials, and what the archive may keep.

## Scale

The personas, models and replicates agreed, and the cost ceiling the user accepted.
