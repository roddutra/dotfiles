#!/usr/bin/env python3
"""The tallies of an interview study, which analyze.py writes to analysis/quant.md and
analysis/quant.json: report(cfg, filters) joins the notes, the themes, the critique and the
turn logs.

Reads, all under the study directory:
    analysis/notes.csv      one row a note, and analysis/critique.csv, one row a mark of a
                            critic (extract_notes.py, which documents every column)
    analysis/themes.md      the themes job's groups, each in the fixed form of
                            assets/interview-themes-brief.md:

                                ### Theme TH1: Late timesheets from subcontractors
                                - Definition: <one line>
                                - Notes: P02-a/3, P02-b/2, P05-a/6

    interviews/<run id>.jsonl   the turn logs, for who was interviewed to the end and which
                            topics each interview opened (panel_lib.run_records())

A participant is one persona on one model entry and replicate: one interview, one run id.
Every count is a count of simulated participants (or, where a heading says so, of their
interviews or of a critic's marks), every heading says which, and nothing here is a frequency
or a prevalence. quant.json keeps, beside every count of participants or of interviews, the
run ids it counted, as {"n": 2, "runs": ["P01-a", "P02-a"]}, and beside every count of notes
their ids, as {"n": 2, "notes": ["P01-a/3", "P02-a/1"]} or a list of ids, so that a hand count
of any interviews can be set against it. A count of a critic's marks is a number alone, under
the interview and the kind it counts.

Three groups, which never overlap. Under a theme, and under a topic, a participant with a note
there is in exactly one of:
    raised it                  at least one note there that is not a NON-PROBLEM note, and no
                               NON-PROBLEM note ("raised")
    said it is not a problem   at least one NON-PROBLEM note there, and no other note
                               ("not_a_problem")
    both                       at least one NON-PROBLEM note there and at least one other note:
                               the participant said something there is not a problem for them,
                               and also told of something else there ("both"). That is whatever
                               the other note codes, a pain or as well a workaround, a person,
                               money or context: its Signal says which, and the group says
                               nothing of trouble
So the three add up to the participants with any note there, and nobody is counted twice. A
participant "told of" a theme with a note under it that is not a NON-PROBLEM note, which is
the first group and the third together: unprompted, with an incident and Effort are counted
over those, from those notes, and so is what a model key or a replicate is compared by. A
NON-PROBLEM note is about its own statement, which may be one part of a topic and not the
whole of it: the second group is the most that supports saying a topic or a theme did not
trouble a participant, and only with its notes read. No column says a topic did not matter.

Only interviews with an end record are in the tables. The others are listed last, under
"Incomplete interviews", with how far each got and how many notes were coded from it, and
those notes are counted nowhere else.

What is written, in this order:
  Key numbers      interviews finished, notes, themes, and everything that was left out of the
                   counts: unparsed notes and entries, quotes that could not be verified, what
                   is wrong with themes.md, and the interviews with a turn on record that no
                   analyst's file, or no critic's file, has a section for
                   (extract_notes.covered()), which are in no row of that kind. This part is
                   also what analyze.py prints
  Themes           for each theme, of the participants interviewed: the three groups, then, of
                   those who told of it, who did so unprompted, who gave a specific incident and
                   the furthest each had gone to deal with it (Effort), and how many of its
                   notes rest on a flagged question. Then each theme's definition and run ids
  Themes by segment, by model key and by persona
                   the same counts within each segment and model key, and for each persona how
                   many of its interviews are in each group. A variant ("variant_of") is a
                   persona of its own, listed under its parent
  Model agreement  for each persona interviewed on more than one model key, each theme any of
                   its interviews told of, and the group of each model key's interview: one
                   that a persona told of on one model and not on another is model taste
  Replicate spread only where a persona has more than one finished replicate on a model key:
                   how many of them told of each theme
  Coverage by topic
                   for each topic of the guide, how many interviews opened it (a question
                   counted for it, by the turn log), how many notes were coded under it (by the
                   first exchange a note names), and the participants of the second and the
                   third group
  Notes that rest on a flagged question
                   a note rests on one when a "flag" row of critique.csv for its run names an
                   exchange from the note's "turn_from" to its "turn_to". It can only do so in
                   an interview that has a critique: one that has none is named, and never
                   read as one in which nothing was flagged
  Critique         the critics' marks by kind and value, and by interview with the critic that
                   marked it, in the order of the critics. The critics split the interviews by
                   persona and one marks more readily than another, so marks by different
                   critics are not comparable, and the report says so
  Notes in no theme, and Problems in themes.md
  Verified quotes  every quote that was found in the transcript, by theme, written as the
                   synthesis must give it: "<quote>" (<run id>, <exchange>), with the one
                   exchange it was found in, so that nobody works one out of a range
  Incomplete interviews

Nothing is tallied from an input that no longer stands. notes.csv and critique.csv must be
what the analysts' and the critics' files give now (extract_notes.changed()), and the themes job
must have been launched after every analyst last was, from notes.csv as it is now
(interview.out_of_date(), from the attempts in runs.json and the fingerprint the themes job's
launch recorded): report() exits with one sentence that says what to run, and analyze.py then
writes nothing. A themes.md that names a note which notes.csv does not have is a file a model
got wrong, or one put there by hand, and is listed as below.

themes.md is held to its form as the notes are (extract_notes.read_form()), and nothing is
guessed. A theme that does not fit, whose id an earlier theme has, or that names a note
notes.csv does not have as a note, is in no table and is listed under "Problems in themes.md":
its notes then read as notes no theme took. A note that two themes list is counted under the
first that lists it, and listed there too.

quant.json keeps each of those problems as what is wrong and never as where ("themes_problems"),
one for a theme, or for a note listed twice: {"theme", "name", "kind", "notes"}. "theme" and
"name" are the id and the name of the theme's heading, None when the heading is not of the form,
and "kind" is one of:
    form            the theme does not fit the form: "heading" is its heading as written, without
                    the marks, and "why" what is wrong, as extract_notes.read_form() says it
                    (a line it numbers is counted from under the heading, not in the file)
    id_taken        an earlier theme has its id
    unknown_notes   "notes" are the ids it names that notes.csv does not have as notes
    listed_twice    "notes" is the one note, which "counted_under", the id of an earlier theme,
                    lists first
"notes" is empty for the first two. The line of themes.md a theme's heading is on is in the
sentence quant.md gives the lead (problem_line()) and nowhere in quant.json, which reads the same
from any folder and inside an archive: archive.py puts the notice into a themes.md that lacks
it, every line under it moves, and analyze.stale_tallies() would then take tallies that have not
changed for ones that have. For the same reason nothing in quant.json is a path or a line
number of a file: the study directory is named in quant.md alone.

The filters of analyze.py all work, by the run: --exclude-model, --exclude-persona and
--segment leave an interview out of everything, with its notes and its critique. A theme stays
in the tables with whatever notes the interviews that are left gave it.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_notes as forms  # noqa: E402
import interview  # noqa: E402
import panel_lib as pl  # noqa: E402
from panel_lib import plural  # noqa: E402

THEME_FORM = (re.compile(r"### Theme (?P<id>[A-Za-z0-9]+): (?P<name>\S.*)"), "### Theme <id>: <name>", [
    ("Definition", *forms.TEXT),
    ("Notes", r"[^\s,/]+/[1-9]\d*(?:,\s*[^\s,/]+/[1-9]\d*)*", "note ids separated by a comma and a space")])
EFFORT_RANK = {e: i for i, e in enumerate(("unknown", "none", "workaround", "searched", "paid"))}  # furthest last
KINDS = {"flag": ("flag", forms.FLAGS), "missed": ("missed signal", forms.MISSED), "good": ("good move", forms.GOOD)}
PARTICIPANTS = "simulated participants"
# The three groups of the participants with a note under a theme or a topic (module docstring), as quant.json keys
# them, with the heading of each one's column and what a cell calls an interview that is in it.
GROUPS = {"raised": ("Raised it", "raised"), "not_a_problem": ("Said it is not a problem", "not a problem"),
          "both": ("Both", "both")}
# An unfinished interview in one of these states is listed even with no exchange on record: it began and stopped.
LISTED_STATES = ("partial", "limited", "blocked", "failed")


def table(head: list[str], rows: list[list]) -> str:
    """A markdown table, with a line break or a bar in a cell made harmless."""
    def cell(x) -> str:
        return " ".join(str(x).split()).replace("|", "\\|")
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] +
                     ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows])


def rows_of(sd: Path, name: str) -> list[dict] | None:
    """The rows of analysis/<name>, None when there is no such file."""
    try:
        with open(sd / "analysis" / name, newline="") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return None


def read_themes(text: str, notes: set[str]) -> tuple[list[dict], list[tuple[int, dict]]]:
    """The themes of themes.md that can be counted, in its order, each {"id", "name",
    "definition", "notes"}, and what is wrong with the file: for each problem, (the line of
    themes.md the theme's heading is on, the problem as quant.json keeps it), which the module
    docstring sets out. The two are apart because only quant.md may say where (problem_line()):
    the line moves when one is put above it, and quant.json must not. notes are the ids
    notes.csv has as notes. A note is given to the first theme that lists it."""
    themes, wrong, taken = [], [], {}
    for line, _, block in forms.blocks(text, ("theme",)):
        got, why = forms.read_form(block, THEME_FORM)
        heading = block.split("\n")[0]
        named = THEME_FORM[0].fullmatch(heading)  # a theme whose lines do not fit may have a heading that does
        theme = {"theme": named["id"] if named else None, "name": named["name"] if named else None}
        ids = list(dict.fromkeys(x.strip() for x in got["notes"].split(","))) if got else []
        unknown = [i for i in ids if i not in notes]
        if not got:
            wrong.append((line, {**theme, "kind": "form", "notes": [], "heading": heading.lstrip("# "), "why": why}))
        elif got["id"] in {t["id"] for t in themes}:
            wrong.append((line, {**theme, "kind": "id_taken", "notes": []}))
        elif unknown:
            wrong.append((line, {**theme, "kind": "unknown_notes", "notes": unknown}))
        else:
            twice = [i for i in ids if i in taken]
            wrong += [(line, {**theme, "kind": "listed_twice", "notes": [i], "counted_under": taken[i]})
                      for i in twice]
            taken.update({i: got["id"] for i in ids if i not in taken})
            themes.append({"id": got["id"], "name": got["name"], "definition": got["definition"].rstrip("."),
                           "notes": [i for i in ids if i not in twice]})
    return themes, wrong


def problem_line(line: int, problem: dict) -> str:
    """A problem of themes.md as quant.md says it, in one sentence: what quant.json keeps of it
    (module docstring) and, for a theme that is in no table, the line of themes.md its heading
    is on, so that the lead finds it. The line is given here and kept nowhere: it is where the
    theme sits in the file as it is read now, which is not what is wrong with it. A note listed
    twice is named by its id and its two themes, and needs no line."""
    if problem["kind"] == "listed_twice":
        first = problem["counted_under"]
        return (f"{problem['notes'][0]} is listed under {first} and under {problem['theme']}: it is counted under "
                f"{first}, which lists it first.")
    if problem["kind"] == "form":  # the one kind whose heading may not give an id and a name
        heading, what = problem["heading"], f"its {problem['why']}"
    else:
        heading, unknown = f"Theme {problem['theme']}: {problem['name']}", problem["notes"]
        what = ("its id is taken by an earlier theme" if problem["kind"] == "id_taken" else
                f"it names {pl.listed(unknown)}, which notes.csv does not have as "
                f"{pl.agree(len(unknown), 'a note', 'notes')}")
    return f"Line {line}, {heading[:60]}: {what}. It is in no table."


def report(cfg: dict, filters: dict, held: bool | None = None) -> tuple[list[str], dict]:
    """The report of an interview study: (the lines of quant.md after its title, what goes into
    quant.json). filters is analyze.py's: {"models", "personas"}, the model keys and persona ids
    left out, and "segment", the segments kept, None for all. held is whether a launcher has
    the study, which decides how an interview marked as carried reads: asked of the study lock
    when it is not given.

    Exits, saying what to run, when the filters leave no interview and when an input is not
    there or no longer stands, since tallies of such inputs would be wrong and look right:
    notes.csv, critique.csv or themes.md is not there; a CSV file is not what the analysts' and
    the critics' files give now (extract_notes.changed()); or an analyst was run again after
    the themes job last was, or notes.csv is no longer the file the themes job was given, so
    that themes.md groups notes that are gone, under ids the new notes may carry too
    (interview.out_of_date_line(), from the attempts in runs.json)."""
    sd = cfg["_dir"]
    notes_file, marks_file = rows_of(sd, "notes.csv"), rows_of(sd, "critique.csv")
    if notes_file is None or marks_file is None:
        raise SystemExit(f"No analysis/{'notes.csv' if notes_file is None else 'critique.csv'}. Run extract_notes.py "
                         f"{sd} first, once the analysts and the critics have written their files.")
    try:
        themes_text = (sd / "analysis" / "themes.md").read_text(errors="replace")
    except FileNotFoundError:
        raise SystemExit(f"No analysis/themes.md. The themes job writes it from notes.csv: launch.py {sd} run --role "
                         f"themes, then analyze.py {sd} again.")
    if held is None:
        import launch  # for the study lock alone, which says whether an interview marked as carried is being carried
        held = bool(launch.Lock.holder(sd))
    records = pl.run_records(sd, cfg, held)
    stale = forms.changed(cfg, records)
    if stale:
        raise SystemExit(stale)
    on_record = pl.read_runs(sd) if (sd / "runs.json").exists() else []
    for job in (e for e in on_record if e["role"] == "themes"):
        stale = interview.out_of_date_line(cfg, job, on_record, records)
        if stale:
            raise SystemExit(f"{stale} Then analyze.py {sd} again.")
    kept = [r for r in records if r["model"] not in filters["models"] and r["pid"] not in filters["personas"]
            and (not filters["segment"] or r["segment"] in filters["segment"])]
    if not kept:
        raise SystemExit("No interview is left to analyse: check the filters.")
    order = [r["run"] for r in kept]
    done = [r for r in kept if r["progress"]["complete"]]
    finished = [r["run"] for r in done]
    names = {p["id"]: p["name"] for p in cfg["personas"]}
    variant_of = pl.variants(cfg)

    def count(runs) -> dict:
        """A count with the run ids it counted, in the study's order."""
        found = set(runs)
        return {"n": len(found), "runs": [run for run in order if run in found]}

    def split(under: list[dict]) -> dict:
        """The three groups of the participants with a note among under (module docstring), each a count.
        No participant is in two of them."""
        told = {n["run"] for n in under if n["signal"] != forms.NON_PROBLEM}
        said_not = {n["run"] for n in under if n["signal"] == forms.NON_PROBLEM}
        return {"raised": count(told - said_not), "not_a_problem": count(said_not - told),
                "both": count(told & said_not)}

    def who(pid: str) -> str:
        return f"{pid} {names.get(pid, '')}".strip() + (f" (variant of {variant_of[pid]})" if pid in variant_of else "")

    def ids(c: dict) -> str:  # a count with its run ids beside it, for a cell
        return f"{c['n']} ({', '.join(c['runs'])})" if c["n"] else "0"

    # The notes: the ones that are notes, of the interviews left by the filters. Those of an unfinished one apart.
    parsed = [n for n in notes_file if n["signal"] != forms.UNPARSED]
    for n in parsed:
        n["turn_from"], n["turn_to"] = int(n["turn_from"]), int(n["turn_to"])
    notes = [n for n in parsed if n["run"] in finished]
    by_id = {n["note"]: n for n in notes}
    early = [n for n in parsed if n["run"] in order and n["run"] not in finished]
    # An unparsed row that names no interview of the study is nobody's, and is counted under every filter.
    left_out = set(r["run"] for r in records) - set(order)
    unparsed_notes = [n for n in notes_file if n["signal"] == forms.UNPARSED and n["run"] not in left_out]
    marks = [m for m in marks_file if m["kind"] != forms.UNPARSED and m["run"] in finished]
    unparsed_marks = [m for m in marks_file if m["kind"] == forms.UNPARSED and m["run"] not in left_out]
    unverified = [n["note"] for n in notes if n["quote_verified"] != "1"]
    flags = {}  # (run, exchange) -> the flags on its question
    for m in marks:
        if m["kind"] == "flag":
            flags.setdefault((m["run"], int(m["turn"])), []).append(m["value"])

    def flagged(n: dict) -> list[tuple[int, str]]:
        """The flags a note rests on: (exchange, flag) for each flagged question among its exchanges."""
        return [(turn, flag) for turn in range(n["turn_from"], n["turn_to"] + 1)
                for flag in flags.get((n["run"], turn), [])]

    # What the jobs' files cover (extract_notes.covered()): an interview no critic's file has a section for has no
    # critique, which is not the same as one its critic marked nothing in.
    cover = {stem: forms.covered(cfg, stem, records) for stem in forms.JOBS}
    held = [r["run"] for r in kept if any(turn["t"] in pl.SPOKEN for turn in r["turns"])]
    bare = {stem: [run for run in cover[stem]["missing"] if run in held] for stem in forms.JOBS}
    critic_of = {run: f"critic-{n}" for run, n in cover["critique"]["by"].items() if run in finished}
    uncritiqued = [run for run in finished if run not in critic_of]

    themes, wrong = read_themes(themes_text, {n["note"] for n in parsed})
    for t in themes:  # as read, a theme has every note it lists: here, the ones of the finished interviews left
        t["notes"] = [i for i in t["notes"] if i in by_id]
    themed = {i for t in themes for i in t["notes"]}
    loose = [n for n in notes if n["note"] not in themed]

    def tally(theme: dict, pool: list[str]) -> dict:
        """A theme's counts among the participants of pool (run ids)."""
        mine = [by_id[i] for i in theme["notes"] if by_id[i]["run"] in pool]
        raising = [n for n in mine if n["signal"] != forms.NON_PROBLEM]
        furthest = {}  # participant -> the furthest Effort among its notes that raise the theme
        for n in raising:
            furthest[n["run"]] = max(furthest.get(n["run"], "unknown"), n["effort"], key=EFFORT_RANK.get)
        judged = [n for n in raising if n["run"] in critic_of]  # only a critiqued interview has a flagged question
        on_flag = [n["note"] for n in judged if flagged(n)]
        return {"interviewed": count(pool), **split(mine),
                "unprompted": count(n["run"] for n in raising if n["raised"] == "unprompted"),
                "incident": count(n["run"] for n in raising if n["evidence"] == "incident"),
                "effort": {e: count(run for run, x in furthest.items() if x == e) for e in forms.EFFORT
                           if e in furthest.values()},
                "raising_notes": [n["note"] for n in raising],
                "flagged": {"n": len(on_flag), "of": len(judged), "notes": on_flag,
                            "not_critiqued": [n["note"] for n in raising if n["run"] not in critic_of]}}

    def cells(c: dict) -> list:  # a tally as the cells of a row, after its name
        return [f"{c['raised']['n']} of {c['interviewed']['n']}", c["not_a_problem"]["n"], c["both"]["n"],
                c["unprompted"]["n"], c["incident"]["n"],
                ", ".join(f"{e} {x['n']}" for e, x in c["effort"].items()) or "-"]

    def flag_cell(c: dict) -> str:  # the last cell of a theme: its notes on a flagged question, of those critiqued
        f, without = c["flagged"], len(c["flagged"]["not_critiqued"])
        return ("no critique" if without and not f["of"] else
                f"{f['n']} of {f['of']}" + (f", {without} with no critique" if without else ""))

    def told(c: dict) -> list[str]:  # the participants who told of a theme: the first group and the third
        return count(c["raised"]["runs"] + c["both"]["runs"])["runs"]

    def label(t: dict) -> str:
        return f"{t['id']} {t['name']}"

    groups = {"segment": list(dict.fromkeys(r["segment"] for r in done)),
              "model": [m for m in pl.model_keys(cfg) if any(r["model"] == m for r in done)]}
    segment_names = cfg.get("segments") if isinstance(cfg.get("segments"), dict) else {}
    for t in themes:
        t.update(tally(t, finished))
        t["by_segment"] = {s: tally(t, [r["run"] for r in done if r["segment"] == s]) for s in groups["segment"]}
        t["by_model"] = {m: tally(t, [r["run"] for r in done if r["model"] == m]) for m in groups["model"]}

    res = {"runs": {"complete": len(done), "expected": len(kept), "interviewed": finished,
                    "no_notes": count(bare["qual"]), "no_critique": count(bare["critique"])},
           "notes": {"counted": len(notes), "in_themes": len(themed), "unparsed": len(unparsed_notes),
                     "unverified": unverified, "from_incomplete": [n["note"] for n in early]},
           "themes": themes, "themes_problems": [problem for _, problem in wrong],  # what, and never where
           "no_theme": [n["note"] for n in loose]}
    said = [problem_line(line, problem) for line, problem in wrong]  # with the line, which only the report gives
    head = [*(column for column, _ in GROUPS.values()), "Unprompted", "With an incident", "Effort"]
    analysts = sorted({n["analyst"] for n in notes})
    md = ["## Key numbers", "",
          f"- {len(done)} of {plural(len(kept), 'interview')} finished"
          + (f", and only {pl.agree(len(done), 'that one is', 'those are')} in the tables: the rest are under "
             '"Incomplete interviews".' if len(done) < len(kept) else "."),
          f"- Every count is of {PARTICIPANTS}, each one persona on one model entry and replicate, with a history "
          "a model made up. No count says how common anything is among real people.",
          f"- {plural(len(notes), 'note')} from {plural(len(analysts), 'analyst')}, {len(themed)} of them in "
          f"{plural(len(themes), 'theme')} and {len(loose)} in none."]
    if unparsed_notes or unparsed_marks:
        md.append(f"- In no count: {plural(len(unparsed_notes), 'note')} and "
                  f"{plural(len(unparsed_marks), 'critique entry', 'critique entries')} that could not be parsed. "
                  f"extract_notes.py {sd} lists them and says why.")
    if unverified:
        md.append(f"- {plural(len(unverified), 'quote')} could not be found in the transcript and "
                  f"{pl.agree(len(unverified), 'is', 'are')} left out of \"Verified quotes\": {', '.join(unverified)}. "
                  f"{pl.agree(len(unverified), 'Its note is', 'Their notes are')} counted.")
    if wrong:
        md += [f"- themes.md has {plural(len(wrong), 'problem')}. Put the file right by hand, or delete it and run the "
               f"themes job again (launch.py {sd} run --role themes), then analyze.py again:",
               *(f"  - {problem}" for problem in said)]
    for stem, lacks in (
            ("qual", "notes: no analyst's file has a section for {them}, so nothing {they} said is coded"),
            ("critique", "critique: no critic's file has a section for {them}, so no mark is counted for {them} and "
             "none of {their} notes can be marked as resting on a flagged question")):
        if bare[stem]:
            n = len(bare[stem])
            kind, why = lacks.format(them=pl.agree(n, "it", "them"), they=pl.agree(n, "it", "they"),
                                     their=pl.agree(n, "its", "their")).split(": ")
            md.append(f"- {n} of the {plural(len(held), 'interview')} with a turn on record "
                      f"{pl.agree(n, 'has', 'have')} no {kind} ({', '.join(bare[stem])}): {why}. extract_notes.py "
                      f"{sd} names the file and says what to run.")
    if not done:
        md.append("- No interview is finished, so there is nothing to count.")
    md.append("")

    if themes and done:
        md += [f"## Themes ({PARTICIPANTS})", "",
               f"Of the {plural(len(done), 'participant')} interviewed to the end. A participant with a note under a "
               "theme is in exactly one of the first three columns, which never overlap, so nobody is counted in two "
               "of them:", "",
               "- **Raised it:** at least one note under the theme that is not a NON-PROBLEM note, and no NON-PROBLEM "
               "note.",
               "- **Said it is not a problem:** at least one NON-PROBLEM note under the theme, and no other note.",
               "- **Both:** at least one NON-PROBLEM note under the theme and at least one other note. The "
               "participant said something there is not a problem for them, and also told of something else there, "
               "which need not be trouble: the other note may be a workaround, a person, money or context as well as "
               "a pain. Its Signal says which, so this column alone never shows that the theme troubled a "
               "participant.", "",
               "Unprompted, With an incident and Effort are counted over the participants of the first and the third "
               "column together, from their notes that are not NON-PROBLEM notes: a participant is unprompted, or "
               "with an incident, when at least one of those notes is, and Effort is the furthest each had gone to "
               "deal with it. The last column counts the theme's notes, other than NON-PROBLEM notes, that rest on a "
               "question the critique flagged"
               + (", of those from an interview that has a critique." if uncritiqued else "."), "",
               table(["Theme", *head, "Notes on a flagged question"],
                     [[label(t), *cells(t), flag_cell(t)] for t in themes]), "",
               "Each theme, and the participants counted:", ""]
        for t in themes:
            md.append(f"- **{label(t)}.** {t['definition']}."
                      + "".join(f" {column}: {', '.join(t[group]['runs'])}." for group, (column, _) in GROUPS.items()
                                if t[group]["n"])
                      + ("" if any(t[group]["n"] for group in GROUPS) else " No participant has a note under it.")
                      + (f" Unprompted: {', '.join(t['unprompted']['runs'])}." if t["unprompted"]["n"] else "")
                      + (f" With an incident: {', '.join(t['incident']['runs'])}." if t["incident"]["n"] else ""))
        md.append("")
        for title, first, key, shown in (
                ("Themes by segment", "Segment", "by_segment", lambda s: segment_names.get(s, s) or "(none)"),
                ("Themes by model key", "Model key", "by_model", str)):
            md += [f"## {title} ({PARTICIPANTS})", "",
                   f"The same columns within each {first.lower()}: \"2 of 3\" under Raised it is 2 of the 3 "
                   f"participants of that {first.lower()} who were interviewed to the end.", "",
                   table(["Theme", first, *head], [[label(t), shown(g), *cells(c)] for t in themes
                                                    for g, c in t[key].items()]), ""]

        # By persona, a variant under its parent: how many of a persona's interviews are in each group of a theme.
        pids = [p["id"] for p in cfg["personas"] if any(r["pid"] == p["id"] for r in done)]
        pids = [x for p in pids if p not in variant_of or variant_of[p] not in pids
                for x in [p, *[v for v in pids if variant_of.get(v) == p]]]
        personas = []
        for pid in pids:
            own = [r["run"] for r in done if r["pid"] == pid]
            personas.append({"persona": pid, "variant_of": variant_of.get(pid), "interviews": count(own),
                             "themes": {t["id"]: {k: v for k, v in tally(t, own).items() if k in GROUPS}
                                        for t in themes}})
        res["personas"] = personas
        md += [f"## Themes by persona ({PARTICIPANTS})", "",
               "For each persona, how many of its finished interviews are in each of the three groups of the Themes "
               "table, of the number under Interviews: one interview for each model key and replicate. A dash is no "
               "note under the theme. A variant is a persona of its own and is listed under the persona it is a "
               "variant of.", "",
               table(["Persona", "Interviews", *[t["id"] for t in themes]],
                     [[who(d["persona"]), d["interviews"]["n"],
                       *[", ".join(f"{c[group]['n']} {word}" for group, (_, word) in GROUPS.items() if c[group]["n"])
                         or "-" for c in d["themes"].values()]] for d in personas]), ""]

        # Model agreement: what a persona told of on one model key and not on another.
        agreement, spread = [], []
        for pid in pids:
            on = {m: [r["run"] for r in done if r["pid"] == pid and r["model"] == m] for m in groups["model"]}
            on = {m: runs for m, runs in on.items() if runs}
            for t in themes:
                telling = {m: count(run for run in runs if run in told(t)) for m, runs in on.items()}
                if len(on) > 1 and any(c["n"] for c in telling.values()):
                    agreement.append({"persona": pid, "theme": t["id"], "models": telling,
                                      "interviews": {m: count(runs) for m, runs in on.items()},
                                      "agree": all(c["n"] for c in telling.values())})
                spread += [{"persona": pid, "model": m, "theme": t["id"], "replicates": count(runs),
                            "told": telling[m]} for m, runs in on.items() if len(runs) > 1 and telling[m]["n"]]
        res["model_agreement"] = agreement
        md += [f"## Model agreement ({PARTICIPANTS})", "",
               "For each persona interviewed on more than one model key, each theme that any of its interviews told "
               "of (it is under Raised it or under Both in the Themes table), and where each model key's interview "
               "is in that table: raised, both, not a problem, or no note under the theme. The last column says yes "
               "when the persona told of the theme on every model key. A theme a persona told of on one model and "
               "not on another is model taste, not a finding about the persona."
               + (" Where a persona has replicates on a model key, the cell counts the replicates that told of the "
                  "theme." if any(len(c["runs"]) > 1 for d in agreement for c in d["interviews"].values()) else ""),
               ""]
        if agreement:
            theme_by = {t["id"]: t for t in themes}

            def on_model(d: dict, m: str) -> str:
                if m not in d["models"]:
                    return "-"
                runs, theme = d["interviews"][m]["runs"], theme_by[d["theme"]]
                if len(runs) > 1:
                    return f"{d['models'][m]['n']} of {len(runs)} replicates"
                return next((word for group, (_, word) in GROUPS.items() if runs[0] in theme[group]["runs"]), "no note")

            same = sum(d["agree"] for d in agreement)
            md += [table(["Persona", "Theme", *groups["model"], "Told of it on every model key"],
                         [[who(d["persona"]), d["theme"], *[on_model(d, m) for m in groups["model"]],
                           "yes" if d["agree"] else "no"] for d in agreement]), "",
                   f"{same} of the {plural(len(agreement), 'pair')} of a persona and a theme above "
                   f"{pl.agree(same, 'was', 'were')} told of on every model key the persona was interviewed on.", ""]
        else:
            md += ["Nothing to compare: no persona has finished interviews on more than one model key and told of a "
                   "theme in one of them.", ""]
        if spread:
            res["replicates"] = spread
            md += [f"## Replicate spread ({PARTICIPANTS})", "",
                   "Where a persona has more than one finished replicate on a model key: how many of them told of "
                   "each theme (under Raised it or under Both). A theme that only some replicates of one persona on "
                   "one model told of is not stable.", "",
                   table(["Persona", "Model key", "Theme", "Replicates that told of it"],
                         [[who(d["persona"]), d["model"], d["theme"],
                           f"{d['told']['n']} of {d['replicates']['n']} ({', '.join(d['told']['runs'])})"]
                          for d in spread]), ""]

    if done:
        # Coverage: who opened each topic, by the turn logs, and the three groups under it, by the notes.
        coverage = []
        for topic in cfg["interview"]["topics"]:
            has = [r["run"] for r in done if topic["id"] in r["progress"]["units"]]
            under = [n for n in notes if n["topic"] == topic["id"]]
            coverage.append({"topic": topic["id"], "area": topic["area"], "interviews": count(has),
                             "opened": count(r["run"] for r in done if topic["id"] in r["progress"]["written"]),
                             "notes": {"n": len(under), "notes": [n["note"] for n in under]}, **split(under)})
        nowhere = [n["note"] for n in notes if n["topic"] not in {t["id"] for t in cfg["interview"]["topics"]}]
        res["coverage"] = {"topics": coverage, "no_topic": nowhere}
        md += ["## Coverage by topic (simulated interviews and participants)", "",
               "An interview opened a topic when one of its questions counted for it, by its turn log, and is set "
               "against the finished interviews whose guide has the topic. A note is coded under the topic of the "
               "first exchange it names. The last two columns are the participants with a NON-PROBLEM note under the "
               "topic, and no participant is in both: those with no other note under it, and those with at least one "
               "other note under it (as under Both in the Themes table). A NON-PROBLEM note is about its own "
               "statement, which may be one part of the topic and not the whole of it. So only the first of the two "
               "columns can support saying that a topic did not trouble a participant, and only once its notes are "
               "read. A participant in the second also told of something under it, which need not be trouble: the "
               "Signal of each other note says whether it is a pain, or a workaround, a person, money or context.",
               "",
               table(["Topic", "Area", "Interviews that opened it", "Notes coded under it",
                      "Participants who said it is not a problem", "Participants with both"],
                     [[c["topic"], c["area"], f"{c['opened']['n']} of {c['interviews']['n']}", c["notes"]["n"],
                       ids(c["not_a_problem"]), ids(c["both"])] for c in coverage]), ""]
        if nowhere:
            md += [f"{plural(len(nowhere), 'note')} {pl.agree(len(nowhere), 'is', 'are')} under no topic, because the "
                   f"first exchange {pl.agree(len(nowhere), 'it names', 'they name')} was an opening or a closing "
                   f"question: {', '.join(nowhere)}.", ""]

        # The notes that rest on a flagged question, NON-PROBLEM notes too.
        theme_of = {i: t["id"] for t in themes for i in t["notes"]}
        resting = [{"note": n["note"], "theme": theme_of.get(n["note"]), "signal": n["signal"],
                    "flags": [{"exchange": turn, "flag": flag} for turn, flag in flagged(n)]}
                   for n in notes if flagged(n)]
        res["flagged_notes"] = resting
        md += ["## Notes that rest on a flagged question", "",
               "A note rests on a flagged question when the critique flagged the question of an exchange the note "
               "names. What such a note says may be the question's doing.", ""]
        md += ([f"- {d['note']} ({d['theme'] or 'no theme'}, {d['signal']}): "
                + "; ".join("exchange {} flagged {}".format(
                    turn, pl.listed([f["flag"] for f in d["flags"] if f["exchange"] == turn]))
                    for turn in dict.fromkeys(f["exchange"] for f in d["flags"])) + "."
                for d in resting] if resting else
               ["None." if not uncritiqued else "None in the interviews that have a critique."]
               if len(uncritiqued) < len(finished) else [])
        if uncritiqued:  # no critique is not the same as a critique that flagged nothing
            md += ([""] if len(uncritiqued) < len(finished) else []) + [
                f"Not known for {pl.listed(uncritiqued)}: {pl.agree(len(uncritiqued), 'it has', 'they have')} no "
                "critique."]
        md.append("")

        # The critique's own counts, of marks and not of participants. Each interview has the critic that marked it.
        by_kind = {kind: {v: {"marks": sum(1 for m in marks if m["kind"] == kind and m["value"] == v),
                              "interviews": count(m["run"] for m in marks if m["kind"] == kind and m["value"] == v)}
                          for v in values} for kind, (_, values) in KINDS.items()}
        by_run = {run: {"critic": critic_of.get(run),
                        **{kind: sum(1 for m in marks if m["run"] == run and m["kind"] == kind) for kind in KINDS}}
                  for run in finished}
        critics = list(dict.fromkeys(sorted(critic_of.values(), key=lambda name: int(name.split("-")[1]))))
        res["critique"] = {"by_kind": by_kind, "by_interview": by_run,
                           "critics": {c: count(run for run in finished if critic_of.get(run) == c) for c in critics},
                           "unparsed": len(unparsed_marks)}
        if critic_of:
            ordered = sorted(by_run.items(), key=lambda item: (critics + [None]).index(item[1]["critic"]))
            md += [f"## Critique (marks on the interviewer's questions, in "
                   f"{plural(len(critic_of), 'simulated interview')})", "",
                   "A count here is of a critic's marks, each one model's opinion of another's question."
                   + (" The critics split the interviews between them, and each interview was marked by the one "
                      "critic named beside it. Marks by different critics are not comparable: one critic marks more "
                      "readily than another, so a difference between interviews that different critics marked may be "
                      "the critics' and not the interviews'." if len(critics) > 1 else ""), ""]
            md += ([table(["Kind", "Value", "Marks", "Interviews"],
                          [[KINDS[kind][0], v, d["marks"], ids(d["interviews"])]
                           for kind, found in by_kind.items() for v, d in found.items() if d["marks"]]), ""]
                   if marks else ["The critics marked nothing: no flag, no missed signal and no good move.", ""])
            md += [table(["Interview", "Critic", "Flags", "Missed signals", "Good moves"],
                         [[run, d["critic"] or "no critique",
                           *[d[kind] if d["critic"] else "-" for kind in KINDS]] for run, d in ordered]), ""]

        md += ["## Notes in no theme", ""]
        md += ([f"- {n['note']}, {n['signal']}: {n['statement']}" for n in loose] if loose else
               ["None: every note is in a theme."])
        md.append("")
        if wrong:
            md += ["## Problems in themes.md", "", *(f"- {problem}" for problem in said), ""]

        # Every verified quote, ready to use. One with a double quotation mark inside cannot be given in the form.
        usable = [n for n in notes if n["quote_verified"] == "1"]
        nested = [n["note"] for n in usable if '"' in n["quote"].translate(interview.DOUBLE_MARKS)]
        usable = [n for n in usable if n["note"] not in nested]
        res["quotes"] = [{"note": n["note"], "theme": theme_of.get(n["note"]), "run": n["run"],
                          "exchange": int(n["quote_turn"]), "signal": n["signal"], "quote": n["quote"]} for n in usable]
        md += ["## Verified quotes", "",
               "Each is in the answer of the exchange it names, word for word, and is written as the synthesis must "
               "give it: the words, then the run and the one exchange. After it, the signal and the note it is from.",
               ""]
        for name, own in [*((label(t), [n for n in usable if theme_of.get(n["note"]) == t["id"]]) for t in themes),
                          ("In no theme", [n for n in usable if n["note"] not in theme_of])]:
            if own:
                md += [f"**{name}**", "", *(f"- \"{n['quote']}\" ({n['run']}, {n['quote_turn']}). {n['signal']}, "
                                            f"note {n['note']}." for n in own), ""]
        if not usable:
            md += ["None.", ""]
        if nested:
            md += [f"{plural(len(nested), 'verified quote')} {pl.agree(len(nested), 'has', 'have')} a double quotation "
                   f"mark inside, which the form cannot carry: paraphrase {pl.agree(len(nested), 'it', 'them')} "
                   f"({', '.join(nested)}).", ""]

    unfinished = [r for r in kept if not r["progress"]["complete"]]
    listed = [{"run": r["run"], "persona": r["pid"], "model": r["model"], "replicate": r["replicate"],
               "segment": r["segment"], "state": r["state"], "exchanges": r["progress"]["exchanges"],
               "cap": r["progress"]["cap"], "opened": r["progress"]["written"], "topics": r["progress"]["units"],
               "notes": [n["note"] for n in early if n["run"] == r["run"]]}
              for r in unfinished if r["progress"]["exchanges"] or r["state"] in LISTED_STATES]
    idle = count(r["run"] for r in unfinished if r["run"] not in {d["run"] for d in listed})
    res["runs"].update(incomplete=listed, not_started=idle)
    if unfinished:
        md += ["## Incomplete interviews", "",
               "These interviews have no end record and are in no table above. Notes coded from one are counted "
               "nowhere: read them in the analyst's file, as what a participant said before the interview stopped.", ""]
        if listed:
            md += [table(["Interview", "Persona", "State", "Exchanges", "Topics opened", "Notes coded"],
                         [[d["run"], names.get(d["persona"], ""), d["state"], f"{d['exchanges']} of {d['cap']}",
                           f"{len(d['opened'])} of {len(d['topics'])}", len(d["notes"])] for d in listed]), ""]
        if idle["n"]:
            md += [f"Interviews not started, or carried with no exchange yet: {idle['n']} "
                   f"({', '.join(idle['runs'])}).", ""]
    return md, res
