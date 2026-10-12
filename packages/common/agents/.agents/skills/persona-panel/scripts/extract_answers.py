#!/usr/bin/env python3
"""Extract what every run answered and quoted into analysis/answers.csv and analysis/lines.csv.

answers.csv: one row per run, concept and study.json "find_the_answer" question
    run, persona_id, persona, model, replicate, complete, segment, concept,
    question, question_text, verdict, where, raw
lines.csv:   four rows per run and concept, one per entry
    run, persona_id, persona, model, replicate, complete, segment, concept,
    entry, status, text, forward_to, note, raw

Both files start with the same eight columns, which say whose row it is. "run" is the run id,
"persona" the persona's slug, "model" the model key, and "complete" 1 when
panel_lib.run_progress says the run is complete. The other four mean what they mean in
scores.csv. analyze.py tallies complete runs only. A run has rows for the concepts it wrote a
section for, so a run with no file has none.

answers.csv. "question" is the question's place in "find_the_answer", from 1. "verdict" is Found,
Partly or Not found, "where" what the panellist wrote after it, and "raw" the entry as written.
Only an answer that starts with Found, Partly, Partially or Not found is a verdict; the rules for
that, and for telling which question an entry answers when the panellist reworded or reordered
them, are panel_lib.read_verdict and panel_lib.parse_answers.

lines.csv. "entry" is keep, cut or not_believed (the line to keep, to cut, and the one the
panellist does not believe) or forward (would they forward it). For a line, "status" is quoted
(the field opens with a line in double quotes: "text" is the line and "note" what followed it),
unquoted (no quotes: "text" is the whole field) or none (the panellist wrote none). For forward,
"status" is yes, no or maybe, "forward_to" is who it would go to and "text" the message they
would send. The rules are panel_lib.read_line and panel_lib.read_forward.

Nothing is guessed. In both files an entry that is not written the way its rule says is
"unparsed", with what the panellist wrote kept in "raw", and one the panellist left out is
"missing". Read the unparsed ones yourself: the summary line counts them.

A run whose latest follow-up question is not settled yet is read as it stood before the question
(panel_lib.read_persona), and one line names each such run.

Works on a live study and on an archived one. Run it after extract_scores.py, before analyze.py.

Usage: extract_answers.py <study-dir>
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402

WHO = ["run", "persona_id", "persona", "model", "replicate", "complete", "segment", "concept"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    cfg = pl.load_study(ap.parse_args().study_dir)
    sd = cfg["_dir"]
    questions = cfg["find_the_answer"]
    runs = pl.run_records(sd, cfg)
    (sd / "analysis").mkdir(exist_ok=True)
    verdicts, entries = Counter(), Counter()
    with open(sd / "analysis" / "answers.csv", "w", newline="") as f, \
            open(sd / "analysis" / "lines.csv", "w", newline="") as g:
        aw, lw = csv.writer(f), csv.writer(g)
        aw.writerow([*WHO, "question", "question_text", "verdict", "where", "raw"])
        lw.writerow([*WHO, "entry", "status", "text", "forward_to", "note", "raw"])
        for run in runs:
            r = run["parsed"]
            if not r:
                continue
            for label in run["progress"]["written"]:
                who = [run["run"], run["pid"], r["slug"], run["model"], run["replicate"],
                       int(run["progress"]["complete"]), run["segment"], label]
                for n, (q, a) in enumerate(zip(questions, pl.parse_answers(r["sections"][label], questions)), 1):
                    aw.writerow([*who, n, q, a["verdict"], a["where"], a["raw"]])
                    verdicts[a["verdict"]] += 1
                for entry, e in pl.parse_lines(r["sections"][label]).items():
                    lw.writerow([*who, entry, e["status"], e["text"], e["to"], e["note"], e["raw"]])
                    entries[e["status"]] += 1
    said = ", ".join(f"{verdicts[v]} {v}" for v in dict.fromkeys(pl.VERDICTS.values()))
    wrote = sum(1 for r in runs if r["progress"]["written"])
    print(*pl.unsettled_lines(runs), f"{sum(verdicts.values())} answers ({said}, {verdicts['missing']} missing, "
          f"{verdicts['unparsed']} unparsed) and {sum(entries.values())} line and forward entries "
          f"({entries['missing']} missing, {entries['unparsed']} unparsed) from {wrote} of {pl.plural(len(runs), 'run')}", sep="\n")


if __name__ == "__main__":
    main()
