#!/usr/bin/env python3
"""Extract the analysts' notes and the critics' marks of an interview study into
analysis/notes.csv and analysis/critique.csv.

notes.csv: one row per evidence note of analysis/qual-<n>.md
    run, persona_id, persona, model, replicate, complete, segment, analyst, note,
    turn_from, turn_to, topic, signal, statement, raised, evidence, effort, quote,
    quote_verified, quote_turn, raw
critique.csv: one row per entry of analysis/critique-<n>.md
    run, turn, kind, value, better, note, raw

Both are read from fixed forms, the ones the analysts' and the critics' briefs give
(assets/interview-qual-brief.md, assets/interview-critique-brief.md). A note:

    ### Note P02-a/3
    - Turns: 7-8
    - Signal: PAIN
    - Statement: Rings subcontractors for late timesheets most weeks
    - Raised: unprompted
    - Evidence: incident
    - Effort: workaround
    - Quote: "I rang him on the Thursday and I was still waiting on the Monday."

A critique entry, in one of three kinds:

    ### Flag P02-a/6            ### Missed P02-a/9           ### Good P02-a/4
    - Flag: leading             - Signal: generality         - Move: anchored
    - Better: <a question>      - Note: <one line>           - Note: <one line>

A note or an entry is a heading and the lines under it, up to the next blank line or heading.
Blank lines between the heading and its first line are passed over, and so is a code fence
around it. Nothing else is forgiven: the heading, the names of the lines, their order and
their number are the form's, each line is one line, and each value is one of its list (SIGNALS,
RAISED, EVIDENCE, EFFORT, FLAGS, MISSED, GOOD), spelt as it is there. Any heading whose first
word is Note, Flag, Missed or Good is read as one, whatever its level or case, so that one
written another way is listed and not passed over in silence.

notes.csv. The first seven columns say whose row it is, as in scores.csv: "run" is the run id,
"persona" the persona's slug, "model" the model key, and "complete" 1 when the interview has
its end record. "analyst" is the <n> of the file, "note" the whole id, <run id>/<k>, and
"turn_from" and "turn_to" the exchanges of "Turns" (the same number for one exchange). "topic"
is the topic that question "turn_from" counts for in the turn log (its "topic", never the label
the interviewer wrote: panel_lib.py, "The turn log"), which is a topic id, or "open" or "close",
under which a note counts for no topic. An analyst never sees a topic id, so this is the only
place a note gets one.

"quote_verified" is 1 when the quote is in the answer of one of the exchanges the note names,
word for word by the one rule for a quotation (interview.said_in(): quotation marks made
straight, white space single, case folded, one closing full stop dropped and an ellipsis kept,
and the words found as words of their own). "quote_turn" is then that exchange, the first when several hold it, which
is the exchange a quotation of it names. Otherwise 0 and empty: the note is still a note, and
its quote is offered to nobody.

critique.csv. "turn" is the exchange after the slash, "kind" flag, missed or good, "value" the
flag, the missed signal or the move, "better" the question a flag proposes and "note" the line
a missed signal or a good move has. Two flags on one exchange are two entries with one
heading, and two rows.

Nothing is guessed. A note or an entry that does not fit its form, holds a value outside its
list, names a run the study does not have or an exchange its turn log does not have, or is a
note whose id an earlier note has, is a row whose "signal" (or "kind") is "unparsed", with
what was written in "raw" and no other field of it filled in but what its heading gave, when
that could be read: in notes.csv "note", and the first seven columns when the run is one of the
study's, and in critique.csv "run" and "turn" as written. Such a row is counted in no tally.
An exchange number is looked up in the turn log before anything is counted from it: one the
log does not have, of any length, is named, and a range is walked only between two exchanges
the log has. The script prints how many of each it read, lists every unparsed row with what is
wrong with it and every quote it could not verify, and says what the lead does about them.

Works on a live study and on an archived one. Run it after the analysts and the critics
(launch.py <study> run --role analyst, run --role critic), before the themes job, which reads
notes.csv alone, and before analyze.py. The two kinds of job run in either order, and the
script reads whatever is there: with the files of one kind alone it writes the other CSV file
with its header and no row, names the jobs that have not written and says what to run. With
no file of either kind it writes nothing and exits with 1.

It also says what a file that is there leaves out (covered()). A job is given every interview
of its personas that has a turn on record, and its file has a "## <run id>" section for each.
Any markdown heading that holds the run id as a word of its own names the interview, whatever
stands around it (names()): a job that writes the id in code marks or in bold, or the persona's
name after it, has still written the section. Only the heading of a note or an entry is held to
its form. A file with no heading that names such an interview was written before the interview
ended, or the job left it out. Each is
named, with the file to delete and the command that writes it again. analyze.py counts the
interviews no file covers in its key numbers, and tells an interview with no critique from
one its critic marked nothing in.

Whether the two CSV files still stand (changed()). Nothing records when this script ran, and
no file's time is compared, so analyze.py, and the launcher before it starts the themes job,
ask this module what the jobs' files give now (gather()) and set it against what the CSV files
hold: when an analyst or a critic was run again, a file was put right by hand, or an interview
went on, they differ, and one sentence says to run this script again.

A review or a usability study has no notes of this form, and is refused in one line.

Where the system refuses one of the two files (a sandboxed shell tool, a study directory that is
not yours to write), one sentence names the file and the reason, and the exit code is 1.

Usage: extract_notes.py <study-dir>
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import interview  # noqa: E402
import panel_lib as pl  # noqa: E402

SIGNALS = ("PAIN", "GOAL", "OBSTACLE", "WORKAROUND", "REQUEST", "BUYING-CRITERION", "MONEY", "PERSON", "CONTEXT",
           "NON-PROBLEM")
NON_PROBLEM = "NON-PROBLEM"  # the signal that counts against a theme and under its topic's "did not matter"
RAISED = ("unprompted", "prompted")
EVIDENCE = ("incident", "general", "opinion", "future", "request")
EFFORT = ("none", "workaround", "searched", "paid", "unknown")
FLAGS = ("pitch", "hypothetical", "leading", "opinion", "generic", "price-guess", "wishlist", "zoom", "talking",
         "rescue", "compound")
MISSED = ("praise-taken", "generality", "feature-request", "feeling", "contradiction", "payer", "pushed-no-problem",
          "surface")
GOOD = ("anchored", "consequence", "accepted", "deflected", "dug", "priority", "spend", "rooted")
UNPARSED = "unparsed"
DIGITS = 9  # an exchange number is written in this many digits at most: a longer one is in no turn log
# The files of the two kinds of job this script reads, analysis/<stem>-<n>.md, and the role that writes each.
JOBS = {"qual": "analyst", "critique": "critic"}

NOTE_COLUMNS = ["run", "persona_id", "persona", "model", "replicate", "complete", "segment", "analyst", "note",
                "turn_from", "turn_to", "topic", "signal", "statement", "raised", "evidence", "effort", "quote",
                "quote_verified", "quote_turn", "raw"]
CRITIQUE_COLUMNS = ["run", "turn", "kind", "value", "better", "note", "raw"]
CSVS = {"qual": ("notes.csv", NOTE_COLUMNS), "critique": ("critique.csv", CRITIQUE_COLUMNS)}  # what each kind gives

HEADING = re.compile(r"\s{0,3}#{1,6}\s*(\w+)\b.*")  # a markdown heading that opens with a word, and that word
ANY_HEADING = re.compile(r"\s{0,3}#{1,6}(?!#).*")    # a markdown heading of any level, whatever it opens with
FENCE = re.compile(r"\s*(```|~~~)")                  # a line that opens or closes a code fence
ID = r"(?P<run>[^\s/]+)/(?P<k>[1-9]\d*)"             # <run id>/<number>: a note's id, or a run and its exchange
TEXT = (r"\S.*", "one line of text")                 # the value of a line that is free text
# Each form: the heading as a pattern and as the lead is shown it, then its lines in order, each with the pattern
# of its value and what that value is, in words.
NOTE_FORM = (re.compile(rf"### Note {ID}"), "### Note <run id>/<number>", [
    ("Turns", r"(?P<a>[1-9]\d*)(?:-(?P<b>[1-9]\d*))?", "one exchange number, or a range such as 7-9"),
    ("Signal", *TEXT), ("Statement", *TEXT), ("Raised", *TEXT), ("Evidence", *TEXT), ("Effort", *TEXT),
    ("Quote", r"[\"“](?P<quote>.+)[\"”]", "words between double quotation marks")])
CRITIQUE_FORMS = {  # by the first word of the heading, in lower case: the kind
    "flag": (re.compile(rf"### Flag {ID}"), "### Flag <run id>/<exchange>", [("Flag", *TEXT), ("Better", *TEXT)]),
    "missed": (re.compile(rf"### Missed {ID}"), "### Missed <run id>/<exchange>", [("Signal", *TEXT), ("Note", *TEXT)]),
    "good": (re.compile(rf"### Good {ID}"), "### Good <run id>/<exchange>", [("Move", *TEXT), ("Note", *TEXT)])}
CRITIQUE_VALUES = {"flag": ("Flag", FLAGS), "missed": ("Signal", MISSED), "good": ("Move", GOOD)}


def blocks(text: str, words: tuple[str, ...]) -> list[tuple[int, str, str]]:
    """Every heading of a markdown text whose first word is one of words, ignoring case, with
    the lines under it: (its line number, that word in lower case, the block). The block is the
    heading and the unbroken run of lines that follows it, each without the white space around
    it, joined by line breaks. Blank lines and a code fence between the heading and that run
    are passed over, and the run ends at a blank line, a fence, another heading or the end of
    the text. That other heading is any markdown heading (ANY_HEADING), so the section of the
    next interview ends a note whatever marks its run id is written in. A heading inside a
    fence is read like any other: a model that wraps its notes in one has still written them."""
    lines, out = text.replace("\r\n", "\n").split("\n"), []
    for i, line in enumerate(lines):
        head = HEADING.fullmatch(line)
        if not (head and head.group(1).lower() in words):
            continue
        block, j = [line.strip()], i + 1
        while j < len(lines) and (not lines[j].strip() or FENCE.match(lines[j])):
            j += 1
        while j < len(lines) and lines[j].strip() and not FENCE.match(lines[j]) and not ANY_HEADING.fullmatch(lines[j]):
            block.append(lines[j].strip())
            j += 1
        out.append((i + 1, head.group(1).lower(), "\n".join(block)))
    return out


def read_form(block: str, form: tuple) -> tuple[dict | None, str]:
    """A block against its form (NOTE_FORM, CRITIQUE_FORMS, and the theme form of
    interview_report.py): (what was read, "") when it fits, else (None, what is wrong with it,
    as the words after "it" or "its" in a sentence). What was read has the named groups of the
    heading and of each line's pattern, and each line's whole value under its name in lower
    case. The lines are held to their names, their order and their number."""
    heading, shown, fields = form
    first, *lines = block.split("\n")
    head = heading.fullmatch(first)
    if not head:
        return None, f"heading is not of the form {shown}"
    got = head.groupdict()
    for i, (name, pattern, what) in enumerate(fields):
        if i >= len(lines):
            return None, f'"- {name}:" line is missing'
        line = re.fullmatch(rf"- {name}:(?: (?P<value>.*))?", lines[i])
        if not line:
            return None, (f'line {i + 1} is "{lines[i][:60]}", where the form has "- {name}: ..." (the lines are '
                          f"{', '.join(n for n, _, _ in fields)}, in that order)")
        value = re.fullmatch(pattern, (line["value"] or "").strip())
        if not value:
            return None, f'{name} is "{(line["value"] or "").strip()[:60]}", which is not {what}'
        got.update({name.lower(): value.group(0), **value.groupdict()})  # a group of the line's own name wins
    if len(lines) > len(fields):
        return None, (f'form has {pl.plural(len(fields), "line")} under the heading and this has {len(lines)}: the '
                      f'first one too many is "{lines[len(fields)][:60]}"')
    return got, ""


def outside(name: str, value: str, allowed: tuple[str, ...]) -> str:
    """What is wrong with a value that is none of its list, "" when it is one."""
    return "" if value in allowed else f'{name} is "{value[:60]}", which is none of {", ".join(allowed)}'


def number(text: str | None) -> int | None:
    """An exchange number as it was written, None for one of more than DIGITS digits, or for
    nothing: no turn log has such an exchange, so it is never made a number, and never counted
    up to."""
    return int(text) if text and len(text) <= DIGITS else None


def read_note(block: str, logs: dict[str, dict], seen: set[str]) -> tuple[dict | None, str, dict]:
    """One note: (its fields for notes.csv, "", what its heading gave) when it can be counted,
    else (None, what is wrong with it, what its heading gave). logs has the exchanges of each
    interview of the study by run id (interview.exchanges()), and seen the ids of the notes read
    before it."""
    got, why = read_form(block, NOTE_FORM)
    if not got:
        head = NOTE_FORM[0].fullmatch(block.split("\n")[0])
        return None, why, ({"run": head["run"], "note": f"{head['run']}/{head['k']}"} if head else {})
    run, note = got["run"], f"{got['run']}/{got['k']}"
    named = {"run": run, "note": note}
    if run not in logs:
        return None, f"heading names {run}, which is no interview of this study", {"note": note}
    # The two ends are looked up before anything is counted from one to the other: a range is only walked once
    # both are exchanges of the log, so "Turns: 1-1000000000" costs nothing and is named by its end.
    ends = [(text, number(text)) for text in (got["a"], got["b"] or got["a"])]
    (_, first), (_, last) = ends
    answered = {n for n, x in logs[run].items() if x["answer"] is not None}
    absent = next((text for text, n in ends if n not in answered), None)
    backwards = None not in (first, last) and last < first
    if not backwards and absent is None:  # an exchange between the two with no answer on record
        absent = next((n for n in range(first, last + 1) if n not in answered), None)
    why = (f"Turns run backwards, from {first} to {last}" if backwards else
           f"Turns name exchange {absent}, which the turn log of {run} does not have with an answer: it has "
           f"{len(answered)}" if absent is not None else
           outside("Signal", got["signal"], SIGNALS) or outside("Raised", got["raised"], RAISED)
           or outside("Evidence", got["evidence"], EVIDENCE) or outside("Effort", got["effort"], EFFORT)
           or ("id is taken by an earlier note. Give it a number of its own" if note in seen else ""))
    if why:
        return None, why, named
    held = [n for n in range(first, last + 1) if interview.said_in(got["quote"], logs[run][n]["answer"])]
    return ({**named, "turn_from": first, "turn_to": last, "topic": logs[run][first]["topic"], "signal": got["signal"],
             "statement": got["statement"], "raised": got["raised"], "evidence": got["evidence"],
             "effort": got["effort"], "quote": got["quote"], "quote_verified": int(bool(held)),
             "quote_turn": held[0] if held else ""}, "", named)


def read_entry(kind: str, block: str, logs: dict[str, dict]) -> tuple[dict | None, str, dict]:
    """One critique entry of the kind its heading opens with: (its fields for critique.csv, "",
    what its heading gave) when it can be counted, else (None, what is wrong with it, what its
    heading gave). A flag and a good move name the exchange of a question, and a missed signal
    the exchange of an answer."""
    form, (line, allowed) = CRITIQUE_FORMS[kind], CRITIQUE_VALUES[kind]
    got, why = read_form(block, form)
    if not got:
        head = form[0].fullmatch(block.split("\n")[0])
        return None, why, ({"run": head["run"], "turn": head["k"]} if head else {})
    run, turn = got["run"], number(got["k"])
    named = {"run": run, "turn": got["k"] if turn is None else turn}  # as written, where it is no number of a log
    if run not in logs:
        return None, f"heading names {run}, which is no interview of this study", named
    has = [n for n, x in logs[run].items() if kind != "missed" or x["answer"] is not None]
    why = (f"heading names exchange {got['k']}, which the turn log of {run} does not have: it has {len(has)}"
           + (" with an answer" if kind == "missed" else "") if turn not in has else
           outside(line, got[line.lower()], allowed))
    if why:
        return None, why, named
    return {**named, "kind": kind, "value": got[line.lower()], "better": got.get("better", ""),
            "note": got.get("note", "")}, "", named


def files(sd: Path, stem: str) -> list[tuple[int, Path]]:
    """analysis/<stem>-<n>.md of the study, in the order of n, each with its n."""
    found = [(int(m.group(1)), f) for f in (sd / "analysis").glob(f"{stem}-*.md")
             for m in [re.fullmatch(rf"{stem}-(\d+)\.md", f.name)] if m]
    return sorted(found)


def names(heading: str, run: str) -> bool:
    """Whether a heading names an interview: its run id stands in it as a whole word of its own,
    with no letter, digit, underscore or hyphen against it on either side. So "## `P01-a`",
    "## **P01-a**", "## P01-a (Dana Whitlock)" and "### Note P01-a/3" all name
    P01-a, and "## P01-a-r2", which is another interview, does not."""
    return bool(re.search(rf"(?<![\w-]){re.escape(run)}(?![\w-])", heading))


def covered(cfg: dict, stem: str, records: list[dict]) -> dict:
    """What the files of one kind of job say of the interviews, and what they leave out. stem is
    "qual" or "critique" (JOBS), and records the study's (pl.run_records()).

        "files"      the files that are there, [(n, path)], as files() gives them
        "by"         {run id: n}: the file that covers each interview, the first that does. A
                     file covers an interview when a heading of it names the run id: the
                     "## <run id>" section the brief asks for, or a note or an entry of it.
                     Any markdown heading counts (ANY_HEADING), and the run id is looked for in
                     it as a whole word of its own (names()), whatever stands around it: in code
                     marks, in bold, or with the persona's name after it
        "silent"     [(file name, the job's id, [run ids])]: for each file that is there, the
                     interviews it should cover and does not. A file should cover every
                     interview of its job's personas that has a turn on record (pl.SPOKEN),
                     finished or not, since each was given to the job with its transcript. Such
                     a file was written before the interview was held, or the job left it out
        "unwritten"  [(the job's id, its file as study.json names it, [run ids])]: each job of
                     the kind whose file is not there, with the interviews it is to cover
        "missing"    the run ids of both, in the study's order: the interviews with a turn on
                     record that no file of the kind covers

    Which personas a job has is on its runs.json entry ("personas"), and for a job no launcher
    has planned yet it is what study.json plans (pl.synthesis_jobs()), which is the same split.
    A file that is no job's (qual-3.md in a study of two analysts) is read like any other and
    is expected to cover nothing."""
    sd, role = cfg["_dir"], JOBS[stem]
    on_record = pl.read_runs(sd) if (sd / "runs.json").exists() else []
    jobs = {j["file"]: j for found in (pl.synthesis_jobs(cfg), on_record) for j in found
            if j.get("role") == role and j.get("file")}
    held = [r for r in records if any(t["t"] in pl.SPOKEN for t in r["turns"])]
    there, by, silent = files(sd, stem), {}, []
    for n, path in there:
        heads = [line for line in path.read_text(errors="replace").splitlines() if ANY_HEADING.fullmatch(line)]
        named = [r["run"] for r in records if any(names(line, r["run"]) for line in heads)]
        for run in named:
            by.setdefault(run, n)
        job = jobs.get(f"analysis/{path.name}")
        own = [r["run"] for r in held if job and r["pid"] in (job.get("personas") or []) and r["run"] not in named]
        if own:
            silent.append((path.name, job["run"], own))
    unwritten = [(j["run"], file, [r["run"] for r in held if r["pid"] in (j.get("personas") or [])])
                 for file, j in jobs.items() if not (sd / file).exists()]
    return {"files": there, "by": by, "silent": silent, "unwritten": unwritten,
            "missing": [r["run"] for r in held if r["run"] not in by]}


def gather(cfg: dict, records: list[dict]) -> dict:
    """What the jobs' files give now, with nothing written: every row of the two CSV files and
    what main() says of them. records are the study's (pl.run_records()).

        "files"       {"qual": [(n, path)], "critique": [(n, path)]}, as files() gives them
        "rows"        {"qual": the rows of notes.csv, "critique": the rows of critique.csv}, each
                      a dict by column, in the order the files hold them
        "cover"       {"qual": covered(), "critique": covered()}
        "who"         {run id: the first seven columns of a row of that interview, after "run"}
        "logs"        {run id: its exchanges (interview.exchanges())}
        "read", "unread"   the notes that were read as notes, and the ones that could not be
        "per_run"     a Counter of the notes read, by run id
        "kinds"       a Counter of the critique entries by kind, UNPARSED among them
        "unparsed"    a line for each note and entry that could not be read, with why
        "unverified"  a line for each note whose quote is not in the answers it names

    main() writes the rows, and changed() sets them against what the CSV files hold, so the one
    reading decides both what is written and whether what was written still stands."""
    sd = cfg["_dir"]
    found = {stem: files(sd, stem) for stem in JOBS}
    slugs = {p["id"]: pl.persona_slug(p) for p in cfg["personas"]}
    who = {r["run"]: [r["pid"], slugs.get(r["pid"], ""), r["model"], r["replicate"], int(r["progress"]["complete"]),
                      r["segment"]] for r in records}
    logs = {r["run"]: interview.exchanges(r["turns"]) for r in records}
    rows, unparsed, unverified, per_run, kinds, seen = {stem: [] for stem in JOBS}, [], [], Counter(), Counter(), set()
    read = unread = 0
    for analyst, path in found["qual"]:
        for line, _, block in blocks(path.read_text(errors="replace"), ("note",)):
            note, why, named = read_note(block, logs, seen)
            run = named.get("run") if named.get("run") in who else None
            whose = dict(zip(NOTE_COLUMNS[1:7], who[run])) if run else {}
            at = f"{path.name} line {line}, {block.splitlines()[0].lstrip('# ')[:60]}"
            if note is None:
                rows["qual"].append({**named, **whose, "analyst": analyst, "signal": UNPARSED, "raw": block})
                unparsed.append(f"{at}: its {why}.")
                unread += 1
                continue
            rows["qual"].append({**note, **whose, "analyst": analyst, "raw": block})
            seen.add(note["note"])
            read += 1
            per_run[note["run"]] += 1
            if not note["quote_verified"]:
                span = (f"exchange {note['turn_from']}" if note["turn_from"] == note["turn_to"] else
                        f"exchanges {note['turn_from']}-{note['turn_to']}")
                other = [str(n) for n, x in logs[note["run"]].items()
                         if interview.said_in(note["quote"], x["answer"])]
                unverified.append(f"{at}: \"{note['quote']}\" is not in the answer of {span}"
                                  + (f". Those words are in the answer of exchange {pl.listed(other)}: put its "
                                     "Turns right" if other else "") + ".")
    for _, path in found["critique"]:
        for line, kind, block in blocks(path.read_text(errors="replace"), tuple(CRITIQUE_FORMS)):
            entry, why, named = read_entry(kind, block, logs)
            if entry is None:
                rows["critique"].append({**named, "kind": UNPARSED, "raw": block})
                unparsed.append(f"{path.name} line {line}, {block.splitlines()[0].lstrip('# ')[:60]}: its {why}.")
                kinds[UNPARSED] += 1
                continue
            rows["critique"].append({**entry, "raw": block})
            kinds[kind] += 1
    return {"files": found, "rows": rows, "cover": {stem: covered(cfg, stem, records) for stem in JOBS},
            "who": who, "logs": logs, "read": read, "unread": unread, "per_run": per_run, "kinds": kinds,
            "unparsed": unparsed, "unverified": unverified}


def as_csv(stem: str, rows: list[dict]) -> str:
    """The text of the CSV file of one kind of job (CSVS), as this script writes it: the header,
    then a line for each row, a column a row lacks left empty."""
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, CSVS[stem][1], restval="")
    writer.writeheader()
    writer.writerows(rows)
    return text.getvalue()


def changed(cfg: dict, records: list[dict], stems: tuple[str, ...] = tuple(JOBS)) -> str | None:
    """Why analysis/notes.csv or analysis/critique.csv no longer stands, None when each holds
    what its jobs' files give now. stems says which is asked: "qual" for notes.csv, "critique"
    for critique.csv, both when not given. The sentence names the CSV files that differ and
    the files they are read from, and the script that writes them again.

    The files are read again, as main() reads them (gather()), and the text they give is set
    against the text on disk, character for character. No time of a file is compared: an
    archive copies files in any order, and a job run again may write the same notes. So a CSV
    file stands for as long as the script would write it as it is: an analyst or a critic run
    again, a file put right by hand, a file deleted and an interview that has gone on since
    (the "complete" column, a note's topic and whether its quote is verified come from the turn
    log) each make it differ, and nothing else does. A CSV file that is not there, or cannot
    be read, differs."""
    sd, now = cfg["_dir"], gather(cfg, records)
    stale = []
    for stem in stems:
        try:
            with open(sd / "analysis" / CSVS[stem][0], newline="") as f:
                same = f.read() == as_csv(stem, now["rows"][stem])
        except (OSError, UnicodeDecodeError):
            same = False
        if not same:
            stale.append(stem)
    if not stale:
        return None
    sources = [f"analysis/{path.name}" for stem in stale for _, path in now["files"][stem]]
    gone = [f"the {JOBS[stem]}s' files, of which none is there," for stem in stale if not now["files"][stem]]
    return (pl.listed([f"analysis/{CSVS[stem][0]}" for stem in stale]) + f" {pl.agree(len(stale), 'is', 'are')} not "
            f"what {pl.listed([*sources, *gone])} now {'gives' if len(sources) == 1 and not gone else 'give'}: run "
            f"extract_notes.py {sd} again.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    cfg = pl.load_study(ap.parse_args().study_dir)
    sd = cfg["_dir"]
    if cfg["type"] != "interview":
        raise SystemExit(f"extract_notes.py reads the evidence notes and the critique of an interview study, and a "
                         f"{cfg['type']} study has neither: its persona files are read by extract_scores.py {sd}.")
    if not files(sd, "qual") and not files(sd, "critique"):
        raise SystemExit(f"No analysis/qual-<n>.md and no analysis/critique-<n>.md yet, so there is nothing to "
                         f"extract. The analysts write the first and the critics the second, in either order: "
                         f"launch.py {sd} run --role analyst, launch.py {sd} run --role critic, then extract_notes.py "
                         f"{sd}.")
    now = gather(cfg, pl.run_records(sd, cfg))
    quals, critiques, cover, who = now["files"]["qual"], now["files"]["critique"], now["cover"], now["who"]
    read, unread, per_run, kinds = now["read"], now["unread"], now["per_run"], now["kinds"]
    unparsed, unverified = now["unparsed"], now["unverified"]
    # Both files are written whatever was found: the one whose jobs have not written yet has its header alone.
    with pl.output(sd / "analysis" / CSVS["qual"][0], newline="") as f, \
            pl.output(sd / "analysis" / CSVS["critique"][0], newline="") as g:
        f.write(as_csv("qual", now["rows"]["qual"]))
        g.write(as_csv("critique", now["rows"]["critique"]))

    def named_files(found: list) -> str:
        return pl.listed([f"analysis/{path.name}" for _, path in found])

    if quals:
        print(f"{pl.plural(read + unread, 'note')} in {named_files(quals)}: {read} read"
              + (f" ({', '.join(f'{run} {per_run[run]}' for run in who if per_run[run])})" if read else "")
              + f", {unread} unparsed. {pl.plural(len(unverified), 'quote')} of the {read} could not be verified.")
        # An interview its analyst has a section for, with no note that could be read: said apart from one left out.
        bare = [run for run in cover["qual"]["by"] if not per_run[run]]
        if bare:
            print(f"No note was read for {pl.listed(bare)}, which {pl.agree(len(bare), 'has', 'have')} a section in an "
                  f"analyst's file: the analyst coded none, or every note of "
                  f"{pl.agree(len(bare), 'it', 'them')} is unparsed.")
    if critiques:
        entries = sum(kinds.values())
        print(f"{pl.plural(entries, 'critique entry', 'critique entries')} in {named_files(critiques)}: "
              f"{pl.plural(kinds['flag'], 'flag')}, {pl.plural(kinds['missed'], 'missed signal')}, "
              f"{pl.plural(kinds['good'], 'good move')}, {kinds[UNPARSED]} unparsed.")
    # What a file that is there leaves out, and the jobs that have not written. Either way the interviews named
    # are in no row of the kind, and analyze.py counts them in its key numbers.
    gaps = [f"{name} says nothing of {pl.listed(left)}: it was written before "
            f"{pl.agree(len(left), 'that interview', 'those interviews')} ended, or the {JOBS[stem]} left "
            f"{pl.agree(len(left), 'it', 'them')} out. To redo it, delete the file and run launch.py {sd} run --role "
            f"{JOBS[stem]}." for stem in JOBS for name, _, left in cover[stem]["silent"]]
    for stem, role in JOBS.items():
        waiting = cover[stem]["unwritten"]
        if waiting:
            csv_name = CSVS[stem][0]
            gaps.append(f"Not written yet: {pl.listed([f'{file} ({job})' for job, file, _ in waiting])}. So "
                        + (f"{csv_name} has its header and no row" if not cover[stem]["files"] else
                           f"{csv_name} has no row for {pl.listed([run for _, _, own in waiting for run in own])}"
                           if any(own for _, _, own in waiting) else f"{csv_name} lacks nothing yet: no interview of "
                           f"{pl.agree(len(waiting), 'that job', 'those jobs')} has a turn on record")
                        + (", and no note can be marked as resting on a flagged question for want of a critique"
                           if stem == "critique" and any(own for _, _, own in waiting) else "")
                        + f". The {role}s write {pl.agree(len(waiting), 'it', 'them')}: launch.py {sd} run --role "
                        f"{role}, then this again.")
    if gaps:
        print("", *gaps, sep="\n")
    if unparsed:
        print("", 'Unparsed, and counted in no tally. What was written is in the "raw" column:',
              *(f"  {line}" for line in unparsed), sep="\n")
    if unverified:
        print("", "Quotes that could not be verified. The note is counted, and its quote is listed for nobody to use:",
              *(f"  {line}" for line in unverified), sep="\n")
    if unparsed or unverified:
        print("", "What to do: read each against the transcript, interviews/<run id>.md. Put it right by hand in its "
              "qual or critique file (the form, the value, the exchange, the words of the quote), note the edit in "
              "analysis/lead-notes.md and run this again. Or leave it: it then stays out, as said above, and the "
              "report of analyze.py counts how many did.", sep="\n")
    unwritten = [role for stem, role in JOBS.items() if cover[stem]["unwritten"]]
    print("", "Wrote analysis/notes.csv and analysis/critique.csv. Next: "
          + (" and ".join(f"launch.py {sd} run --role {role}" for role in unwritten)
             + f", then extract_notes.py {sd} again." if unwritten else
             f"launch.py {sd} run --role themes, which reads notes.csv alone, then analyze.py {sd}."), sep="\n")


if __name__ == "__main__":
    main()
