#!/usr/bin/env python3
"""The rules of an interview: what each side is told, and how a turn is read and answered.

An interview study ("type": "interview", panel_lib.py "Interview studies") is a conversation
between two sessions, a participant and an interviewer, which a launcher carries turn by turn.
Three modules divide the work. panel_lib.py owns the formats: the study.json keys, the
runs.json entries, the turn log and the state read from it. This module owns the rules.
launch.py owns the processes, and asks this module what to do with each reply.

Imports. This module imports panel_lib and runners at the top, and nothing else of the skill:
launch.py imports it, so anything it needs from launch.py or followup.py is imported inside the
function that needs it. It keeps no state of its own between calls.

The prompts. Each side is launched with one prompt, written by init_study.py into prompts/ and
sent verbatim:

    participant   assets/participant-run-prompt.md (participant_prompt()): the participant brief,
                  the persona (name, role, personality, segment, bio), the study's
                  "context_notes" and the request for its first reply, a situation card
                  (assets/participant-card-request.md) or the word "Ready"
                  (assets/participant-ready-request.md). The brief is
                  assets/participant-brief.md up to the line that starts with PROVENANCE: what
                  follows it is for maintainers, names the book the method is from, and would
                  tell a participant what the interview is after
    interviewer   assets/interviewer-brief.md (interviewer_prompt()): the method, the reply
                  format, the guide as this persona's interview has it (panel_lib.guide()), what
                  a recruiter would know of the participant (name, role, segment) and the text
                  of the seven reference notes of assets/interview-reference/, in name order,
                  each under its file name. Nothing of the persona's bio or personality, and
                  nothing of the study brief

Neither side has a tool (tools()), so nothing either is given can be in a file: the reference
notes are in the interviewer's prompt, and both working folders stay empty.

The notices. assets/interview-notices.md holds the fixed sentences a launcher sends to an
interviewer, one to a line as "key: sentence" (notices(), notice()).

The loop. A launcher carries an interview with three functions over its turn log
(panel_lib.py, "The turn log"), and holds no rule of its own:

    fold(records)                  where the conversation stands: the position
    next_step(position, guide, at) what to do now: a step
    taken(position, guide, side, attempt, result, leak_terms, at)
                                   the records an ended process adds to the log

All three are pure, so a launcher that takes over from one that was killed reads the same log
and decides the same. A step is one of:

    {"do": "send", "side", "how", "frame"}   start one process of that side: "how" is "launch"
                                             (the side's prompt in prompts/, sent as it is,
                                             frame "prompt") or "resume" (its session, with
                                             message() of the step)
    {"do": "append", "record"}               add the record to the log, and ask again
    {"do": "stop", "state", "reason"}        put the interview down: the state its log reads
                                             as, and why, None when it is done

next_step(), first match first: an "end" stops as done; a "halt" in force stops with its state;
a "lost" record that stands stops as partial (pending with no turn yet); an answer to the last
exchange the cap allows appends the "end"; a participant with no card or "Ready" is launched; a
participant that replied with nothing twice stops as partial, and otherwise gets the question
(frame "say"), or the question again (frame "again"); an interviewer whose reply could not be
used twice in one slot stops as partial, or at the last exchange has the "end" appended, one
exchange short; an interviewer whose reply was sent back gets the repair (frame "repair"); one
that ended with topics unopened is asked once whether it means it (frame "end-check"); an
interviewer with no reply on record is launched; and otherwise it gets the answer (frame
"turn").

So three things go on unasked after a reply that cannot be used, each bounded by a count in the
position: one repair for each slot of the interviewer (a slot is its turn between two accepted
records), the end check once an interview, and one empty answer put again. Everything else
waits for the lead: a "halt", a "lost" record whose "why" is not "empty", and a count that is
used up all stand until a "resume" record follows, which only a command writes. After it the
turn is put again, a participant's with assets/participant-again.md and an interviewer's with
the "again" notice above its frame.

The reply grammar (parse_reply()). An interviewer's reply is a question,

    TOPIC: <a topic id of this persona's guide, open or close>
    MOVE: <one of MOVES>
    WHY: <one sentence, for the researcher>
    SAY:
    <the words for the participant: everything to the end of the reply>

or an end, "END: <reason>" in place of TOPIC, MOVE and WHY, with a closing line under "SAY:"
that is recorded and never sent, and may be left out. Keys are upper case, at the start of a
line, each once. A line before "SAY:" that opens with no key continues the key above it. Two
things are forgiven (_plain()): one code fence around the whole reply, and blank space around
it, a margin that every line shares included, since the brief shows its examples indented.
Nothing else is: a key in another case, markdown around a key, words on the "SAY:" line, text
before the first key and a code fence around a part of the reply each make it unusable. Every
problem is found in one pass and named by a key of the notices ("repair-<key>"): format,
missing, topic, move, say. taken() adds the two gates in the same pass: leak, a "leak_terms"
entry in the words of a question (never in the closing line of an end, which is not sent), and
last-exchange, a question for the last exchange the cap allows that is no close. So one
"rejected" record, and the one repair message made from it, names all of them.

The topic of a question (opened_by()). A question counts for the topic its record names, and
its words decide that before its label does: where the words under SAY hold, word for word, the
opener of a topic of this persona's guide that no question has carried yet, the question is
that topic's, whatever TOPIC the interviewer wrote, "open" and "close" included. Case, white
space, curly quotation marks and a closing full stop are not looked at (pl.same_line()). The
opener is held only as words of its own, with no letter or digit against it on either side:
"Walk me through the last order." is not held by a question about "the last ordering mistake",
and an opener that ends in a question mark is held with a space, a quotation mark or the end of
the words after it. An
interviewer that takes leave of one topic and opens the next in one reply tends to label it
with the topic it is leaving, and the answer would then be filed under the wrong topic and the
new topic read as unopened. Nothing is sent back for it: the record's "topic" is the topic
opened, and "labelled" keeps what the interviewer wrote when that differs. With the openers of
two unopened topics in one reply the question is the one its label names, else the one whose
opener comes first in its words, and the other stays unopened. A topic that a question has
carried is never opened a second time by its opener, and a reply with no opener in it counts
for its label. The gates read the label, since that is what the interviewer is told to write:
at the last exchange a reply labelled "close" passes, and when its words open a topic the
record says so, and the interview ends with no close. Everything that counts by topic reads
the record: the status line, the caps, the end check, the checks and the transcripts.

A participant's first reply (in_role()) must be its situation card, known by at least
CARD_ENOUGH of the labels assets/participant-card-request.md gives its parts (card_parts()), or
with the card off the word "Ready". Any other reply leaves the interview failed before an
interviewer is started: a model that will not hold the role is refused by what it did, and no
model is named or matched anywhere.

The transcripts (render(), write_transcripts()). interviews/<run id>.md is the whole of an
interview for the user, the lead and the critic: the recruitment facts, the situation card
under a heading that says the interviewer never saw it, each exchange with its topic (and the
label the interviewer gave it, where its words opened another), move and reason, and a line in
brackets wherever a reply was sent back or lost, the end check was asked
and the interview ended. analysis/transcripts/<run id>.md is the analysts' copy: the
recruitment facts and the numbered questions and answers, and nothing else. Both carry the
synthetic panel notice. A launcher writes them when an interview ends, and the render command
writes them again for every interview with a turn on record, finished or not.

The checks (problems(), advice()). check_runs.py asks problems() of every interview and writes
what it returns in its table. Blocking, each of which keeps an interview out of the analysis:

    no "end" record                  the interview is not finished, or was never held. The row
                                     says what it reads as and how far it got
    a turn log of the wrong form     each sentence of panel_lib.turn_problems(): a record of no
                                     known type, one that lacks a field every launcher writes or
                                     one with a value of another kind than a launcher writes,
                                     and nothing else of such a log is checked; a log that does
                                     not begin with "start", turns that do not alternate or that
                                     skip a number, a second card, anything after the "end"
    a leak term in a question        a "leak_terms" entry in the words of a "question" record,
                                     which was delivered. taken() lets none through, so the term
                                     was added to study.json later, or the log was changed

Notes, none of which blocks: topics never opened and a capped interview that ended with no
close, both of a finished interview; exchanges past a topic's cap; a question that its words
put under another topic than its label; a leak term in the card or
an answer, which is background leaking in from the harness, as it is in a review; an answer
that speaks of being an AI, a model or a persona (AI_TALK, which is phrases and never the bare
word "model": a participant may well talk about a pricing model); a question with more than
QUESTION_MARKS question marks; answers whose median length is over LONG_ANSWER words; a reply of
the interviewer that was sent back; a turn that left no reply; and a turn log that ends in a
write a killed launcher never finished, which no reading of the log counts.

advice() is what the lead does about the blocking rows, as the lines check_runs.py prints
under its table: the command that goes on with each unfinished interview, by the state it
reads as (one that reads pending has not started, and is said so: only of one that stopped is
"status" named for the reason), and for a leak term that was delivered, which nothing can take
back, how to discard the interview or keep it and report the leak. Only the turn log interviews/<run id>.jsonl is
an interview of the study: one that a fresh start or a new scaffold moved into logs/ is not
read.

What a finished interview measured (measured()). The plan divides what each side of the
finished interviews used by their exchanges, for a figure an exchange that an interview of
another length can be judged by.

Usage:
  interview.py <study-dir> render [--runs <ids>]   # write both transcripts again

render takes the study while it writes. When a launcher has it, render says so and writes
all the same: a transcript is made from the turns on record at that moment, and the launcher
writes it again when its interview ends.
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402
import runners  # noqa: E402

# The moves an interviewer names in its reply, one for each: assets/interviewer-brief.md says what each is.
MOVES = ("open", "priority", "raise", "anchor", "sequence", "consequence", "coping", "alternatives",
         "frequency", "constraint", "money", "deflect", "dig", "clarify", "accept", "close")
PARTICIPANT_TOOLS, INTERVIEWER_TOOLS = "none", "none"  # run["tools"] of each side: neither has a tool (tools())
PROVENANCE = "Provenance, for maintainers:"            # where the participant brief is cut
REFERENCES = "interview-reference"                     # the folder of the reference notes, in assets/
NOTICES = "interview-notices.md"                       # the fixed sentences, in assets/
NOTICE_LINE = re.compile(r"([a-z][a-z0-9-]*): (.+)")   # an entry of it: a key, a colon and a space, the sentence
TURN_POLL = 0.2                                        # seconds between looks while an interview is carried
KEY_LINE = re.compile(r"(TOPIC|MOVE|WHY|SAY|END):[ \t]*(.*)")     # a line of a reply that opens with a key
FENCE = re.compile(r"```[A-Za-z0-9_+-]*[ \t]*\n(.*)\n[ \t]*```", re.S)  # a reply inside one code fence
CARD_REQUEST = "participant-card-request.md"           # what asks for the situation card, in assets/
CARD_PART = re.compile(r"\d+\.\s+\*\*(.+?):?\*\*")      # a numbered line of it opens with a part's label, in bold
CARD_PARTS, CARD_ENOUGH = 4, 3                         # the parts of a card, and how many a first reply must name
MARKS = re.compile(r"[*_#`]")                          # the markdown marks in_role() reads past
REPLIES = ("card", "ready", "question", "answer", "rejected", "end-offered")  # records of a reply that was read
SPEAKS = {"card": "participant", "answer": "participant", "opening": "interviewer", "question": "interviewer"}
# How a turn that left no reply ended, by the "why" of its "lost" record: what follows "the <side>'s turn".
ENDED = {"empty": "ended with an empty reply", "role": "ended with a first reply that is not the one asked for",
         "stop": "was stopped by the stop command", "time": "was stopped at limits.turn",
         "limit": "used the last of its side's time", "budget": "used the last of its side's budget",
         "usage_limit": "was turned away by its harness", "error": "ended with an error",
         "killed": "ended with its watchdog killed, so how it ended is not on record"}
TOO_SMALL = "this model may be too small to hold the role. Use a larger one"  # of a first reply out of role
# An answer that speaks of being an AI, a model or a persona, for a note of the checks. Phrases, and never the
# bare word "model", which a participant uses of a pricing model or a car.
AI_TALK = re.compile(
    r"\b(?:an AI|AI (?:assistant|model|system)|artificial intelligence|language model|chatbot"
    r"|as a persona|my persona|the persona I|play(?:ing)? (?:a|the|this) (?:persona|role|character)"
    r"|role-?play(?:ing)?|simulat(?:ion|ed)|in character|out of character|system prompt)\b", re.I)
QUESTION_MARKS = 2   # a question with more than this many question marks is noted: it asks several things at once
LONG_ANSWER = 120    # words: a median answer longer than this is noted, since a person in an interview says less
# How each blocking problem of problems() opens, which is what advice() knows it by.
NO_END, MALFORMED, LEAKED = "no end record", "turn log of the wrong form", "leak term"
# The command that goes on with an interview that has no "end" record, by the state it reads as. None: a launcher
# is carrying it, and no command is needed. It reads running only while a launcher has the study (pl.carried()).
CONTINUES = {"pending": "run", "failed": "run", "partial": "resume", "blocked": "resume",
             "limited": "resume --runs <ids> --extend", "running": None}
STOPPED = ("partial", "limited", "blocked", "failed")  # of those, the states of an interview that began and stopped


def notices() -> dict[str, str]:
    """{key: sentence} of assets/interview-notices.md: every line that is a lower-case key, a
    colon, a space and a sentence. Every other line is the asset's own account of itself."""
    found = (NOTICE_LINE.fullmatch(line.strip()) for line in (pl.ASSETS / NOTICES).read_text().splitlines())
    return {m.group(1): m.group(2) for m in found if m}


def notice(key: str, **values) -> str:
    """One sentence of the notices with its placeholders filled: notice("topic-cap", topic="T2"),
    each value named by its token in lower case. Only the sentence is searched for tokens, never
    a value, so a value that holds one is sent as written. Exits when the asset has no such key,
    or the sentence has a token that was given no value: a sentence is never sent with one left
    in it."""
    sentences, given = notices(), {name.upper(): str(value) for name, value in values.items()}
    if key not in sentences:
        raise SystemExit(f'assets/{NOTICES} has no line "{key}: ...". The launcher sends that sentence to an '
                         "interviewer: put the line back.")
    unfilled = sorted(set(pl.PLACEHOLDER.findall(sentences[key])) - set(given))
    if unfilled:
        raise SystemExit(f'assets/{NOTICES}: the sentence "{key}" has placeholders with no value to fill them: '
                         f"{', '.join(f'<{t}>' for t in unfilled)}. Take them out of the sentence.")
    return pl.PLACEHOLDER.sub(lambda m: given[m.group(1)], sentences[key])


def participant_brief() -> str:
    """assets/participant-brief.md as a participant gets it: everything above the line that
    starts with PROVENANCE. What follows that line is for maintainers and names the book the
    rules are written from, which would tell a participant what its interviewer is after. Exits
    when the asset has no such line: a brief whose last paragraph was reworded would otherwise
    reach every participant whole."""
    lines = (pl.ASSETS / "participant-brief.md").read_text().split("\n")
    cut = next((i for i, line in enumerate(lines) if line.startswith(PROVENANCE)), None)
    if cut is None:
        raise SystemExit(f'assets/participant-brief.md has no line that starts "{PROVENANCE}". A participant is '
                         "given the brief up to that line and nothing after it: end the brief with a paragraph "
                         "that starts with those words.")
    return "\n".join(lines[:cut]).strip()


def _bullets(lines) -> str:
    """Lines as a list, one "- " line each, with any line break inside one closed up."""
    return "\n".join(f"- {' '.join(str(line).split())}" for line in lines)


def _segment_line(cfg: dict, persona: dict) -> str:
    """The line of a prompt that gives a persona's segment, by its name in study.json "segments"
    where it has one. Empty for a persona with no segment, and the line then goes."""
    segment, names = persona.get("segment"), cfg.get("segments")
    return f"- Segment: {names.get(segment, segment) if isinstance(names, dict) else segment}" if segment else ""


def participant_prompt(cfg: dict, persona: dict) -> str:
    """The whole launch prompt of a participant, assets/participant-run-prompt.md filled: the
    brief (participant_brief()), who the persona is, the study's "context_notes" as facts about
    where it works, and what its first reply is to be, its situation card or the word "Ready".
    The same for every model entry and replicate of a persona. It holds nothing of the guide."""
    first = "participant-card-request.md" if cfg["interview"]["situation_card"] else "participant-ready-request.md"
    return pl.fill_brief("participant-run-prompt.md", {
        "PARTICIPANT_BRIEF": participant_brief(), "NAME": persona["name"], "ROLE": persona["role"],
        "PERSONALITY": persona["personality"], "SEGMENT_LINE": _segment_line(cfg, persona),
        "BIO": _bullets(persona.get("bio") or []), "CONTEXT_NOTES": _bullets(cfg["context_notes"]),
        "FIRST_REPLY": (pl.ASSETS / first).read_text().strip()})


def references() -> str:
    """The text of every reference note of assets/interview-reference/, in name order, each
    whole under a heading that is its file name, which is how the brief and the notes refer to
    one another. The files stay the source: they are copied nowhere."""
    notes = sorted((pl.ASSETS / REFERENCES).glob("*.md"))
    return "\n\n".join(f"## {note.name}\n\n{note.read_text().strip()}" for note in notes)


def interviewer_prompt(cfg: dict, persona: dict, block: str = "interview") -> str:
    """The whole launch prompt of the interviewer of one persona, assets/interviewer-brief.md
    filled: the guide as that persona's interview has it (pl.guide(): its topics, with the goals
    they leave), what a recruiter would know of the participant, and the reference notes
    (references()). The same for every model entry and replicate of the persona. block is the
    study.json key the guide is read from.

    Every topic id the brief shows is one of this guide's, so that no example gives the
    interviewer an id to copy that its guide does not have: <FIRST_TOPIC> is the first topic's,
    which its first reply is to carry, <EXAMPLE_TOPIC> the one in the example of a reply (the
    second topic's, or the only one's) and <EXAMPLE_STATUS> a status line as status_line()
    writes one for this guide (_example_status())."""
    held = pl.guide(cfg, persona["id"], block)
    shown = held["topics"][min(1, len(held["topics"]) - 1)]
    topics = [f"{i}. {t['id']}, {t['area']}. "
              f"Serves {pl.listed(t['goals']) if t['goals'] else 'no goal in particular'}. "
              f"Cap: {pl.plural(t['turns'], 'exchange')}. Opener: \"{' '.join(t['opener'].split())}\""
              for i, t in enumerate(held["topics"], start=1)]
    return pl.fill_brief("interviewer-brief.md", {
        "ABOUT": held["about"], "NAME": persona["name"], "ROLE": persona["role"],
        "SEGMENT_LINE": _segment_line(cfg, persona),
        "GOALS": "\n".join(f"- {g['id']}: {' '.join(g['learn'].split())}" for g in held["goals"]),
        "TOPICS": "\n".join(topics), "TURNS": held["turns"], "REFERENCES": references(),
        "FIRST_TOPIC": held["topics"][0]["id"], "EXAMPLE_TOPIC": shown["id"],
        "EXAMPLE_STATUS": _example_status(held, shown)})


def _example_status(guide: dict, shown: dict) -> str:
    """A status line for the brief to show, made by status_line() from a position this guide can
    reach, so that its form, its topic ids and its caps are the ones the interviewer will see:
    part-way through the topic shown, with the topics before it carried and the ones after it
    not opened, which the line then names. A guide of one topic has none to name."""
    ids = [t["id"] for t in guide["topics"]]
    before, here = ids.index(shown["id"]), max(1, min(4, shown["turns"] - 1))
    here = max(1, min(here, guide["turns"] - before - 2))
    pos = {"answers": [None] * (before + here), "questions": [{"topic": shown["id"]}],
           "per_topic": {**dict.fromkeys(ids[:before], 1), shown["id"]: here}}
    return status_line(pos, guide)


def tools(side: str, runner) -> str:
    """run["tools"] for a process of one side of an interview (pl.SIDES), on a runner module:
    "none" where the runner can start a process with no tool (runners.can(): "no_tools"), and
    "files", what every other run has, only where it cannot. No model is an exception, and a
    side that will not hold its role without tools is not given them back."""
    wanted = {"participant": PARTICIPANT_TOOLS, "interviewer": INTERVIEWER_TOOLS}[side]
    return wanted if runners.can(runner, "no_tools") else "files"


# ---------------------------------------------------------------- reading a reply

def _plain(text: str) -> str:
    """An interviewer's reply with what is forgiven taken off: blank space and blank lines
    around it, a margin that every line shares, and one code fence around the whole of it, with
    or without a language word. Discovery found one unusable reply in 375, a reply wrapped in
    the fence the brief's own example had then, and the brief now shows its examples indented.
    Nothing else is put right here, and a reply with a fence inside it is left as it is."""
    bare = textwrap.dedent((text or "").replace("\r\n", "\n")).strip()
    fenced = FENCE.fullmatch(bare)
    if fenced and not any(line.lstrip().startswith("```") for line in fenced.group(1).split("\n")):
        bare = textwrap.dedent(fenced.group(1)).strip()
    return bare


def parse_reply(text: str, topic_ids: list[str]) -> dict:
    """An interviewer's reply against the reply grammar (module docstring): {"form", "topic",
    "move", "why", "say", "reason", "problems"}.

    "form" is "question" or "end", None when the reply has the keys of neither or of both.
    "reason" is what follows END. Each of the five is None when it was not read or is empty.
    "problems" lists everything wrong with the reply, not the first thing, as [key, detail]:
    format (text before the first key, a key twice, words on the SAY: line, END beside the keys
    of a question, a code fence that is not around the whole reply), missing (the fields, as
    the repair names them), topic and move (the value that is none of those allowed) and say (a
    question with nothing under SAY:). The reply is usable when the list is empty. The first
    reply is not held to MOVE: open or to the first topic: that is the brief's to ask and the
    critique's to mark.
    """
    fields, wrong, current, lines = {}, [], None, _plain(text).split("\n")
    if any(line.lstrip().startswith("```") for line in lines):  # in what is left once _plain() has had its one
        wrong.append("a code fence inside the reply")
    for i, line in enumerate(lines):
        key = KEY_LINE.fullmatch(line)
        if key and key.group(1) == "SAY":  # everything under it is for the participant, whatever it looks like
            if key.group(2).strip():
                wrong.append("words on the SAY: line")
            fields["SAY"] = "\n".join([key.group(2), *lines[i + 1:]]).strip()
            break
        if key:
            current = key.group(1)
            if current in fields:
                wrong.append(f"{current} twice")
            fields[current] = key.group(2).strip()
        elif line.strip() and current is None:
            if "text before the first key" not in wrong:
                wrong.append("text before the first key")
        elif line.strip():
            fields[current] = f"{fields[current]} {line.strip()}".strip()
    asked, ended = [k for k in ("TOPIC", "MOVE", "WHY") if k in fields], "END" in fields
    missing, problems = [], []
    if ended and asked:
        wrong.append(f"END beside {pl.listed(asked)}")
    elif ended and not fields["END"]:
        missing.append("the reason after END")
    elif not ended:
        missing = [k for k in ("TOPIC", "MOVE", "WHY") if not fields.get(k)] + ["SAY"] * ("SAY" not in fields)
    if wrong:
        problems.append(["format", "; ".join(wrong)])
    if missing:
        problems.append(["missing", ", ".join(missing)])
    if not ended:
        if fields.get("TOPIC") and fields["TOPIC"] not in (*topic_ids, "open", "close"):
            problems.append(["topic", fields["TOPIC"]])
        if fields.get("MOVE") and fields["MOVE"] not in MOVES:
            problems.append(["move", fields["MOVE"]])
        if "SAY" in fields and not fields["SAY"]:
            problems.append(["say", ""])
    return {"form": None if ended == bool(asked) else "end" if ended else "question",
            "topic": fields.get("TOPIC") or None, "move": fields.get("MOVE") or None,
            "why": fields.get("WHY") or None, "say": fields.get("SAY") or None,
            "reason": fields.get("END") or None, "problems": problems}


def leak(say: str, terms: list[str]) -> str | None:
    """The first "leak_terms" entry found in the words of a question, as study.json writes it,
    None when it holds none: the search check_runs.py makes of a review, ignoring case. A
    question that holds one is never delivered. No term is empty (pl.check_interview())."""
    low = (say or "").lower()
    return next((term for term in terms if term.lower() in low), None)


def card_parts() -> list[str]:
    """The labels of the four parts of a situation card, read from the asset that asks for it:
    the bold words that open each numbered line of assets/participant-card-request.md. Read
    there and written nowhere else, so that a reworded asset cannot leave in_role() behind.
    Exits when the asset does not name four."""
    lines = (pl.ASSETS / CARD_REQUEST).read_text().splitlines()
    parts = [m.group(1).strip() for m in map(CARD_PART.match, lines) if m]
    if len(parts) != CARD_PARTS:
        raise SystemExit(f"assets/{CARD_REQUEST} must name the {CARD_PARTS} parts of a situation card, each on a "
                         f'numbered line that opens with its label in bold, as "1. **On my mind:**". It names '
                         f"{len(parts)}. A participant's first reply is known for a card by those labels.")
    return parts


def _bare(text: str) -> str:
    """Text as in_role() compares it: lower case, no markdown mark, each run of white space one
    space."""
    return " ".join(MARKS.sub("", text or "").lower().split())


def in_role(text: str, card: bool) -> bool:
    """Whether a participant's first reply is the one its prompt asked for. card: a situation
    card, which names at least CARD_ENOUGH of the CARD_PARTS labels of card_parts(), so that a
    card with one heading reworded is not refused. Otherwise the word "Ready", with or without a
    full stop. Case, markdown marks and the amount of white space are not looked at. A reply
    that is neither is a refusal of the role or a model that lost its instructions, and its
    interviewer would go on to interview that."""
    said = _bare(text)
    if not card:
        return said in ("ready", "ready.")
    return sum(_bare(part) in said for part in card_parts()) >= CARD_ENOUGH


# ---------------------------------------------------------------- the position and the next step

def fold(records: list[dict]) -> dict:
    """Where a conversation stands, from the records of its turn log (pl.read_turns()):

        kind         "interview" or "debrief", from the "start" record
        ready        a card or a "Ready" is on record. Always true in a debrief, which has none
        questions, answers   those records, in order
        awaiting     "card" until ready; then "opening" until the interviewer has a question or
                     an "end-offered" on record; then "answer" after a question and "question"
                     after an answer. None once there is an "end"
        rejected     the "rejected" record of the interviewer's last reply, while nothing has
                     replaced it, else None
        sendbacks    the "rejected" records since the last question, "end-offered", answer or
                     "resume": the send-backs of this slot
        empties      the "lost" records with "why": "empty" since the last reply or "resume"
        lost         the last "lost" record for the awaited step whose "why" is not "empty",
                     while no "resume" follows it, else None: the interview waits for the lead
        again        a "lost" record for the awaited step, with a "resume" after it or not: the
                     message was sent before, and is put again
        offered      an "end-offered" with no question or "end" after it, else None. A reply
                     that is sent back leaves it standing
        end_checked  an "end-offered" is on record anywhere: the check is asked once
        spoke        {"participant", "interviewer"}: the side has a reply on record, so it has
                     a session. A debrief's participant has one from the start
        halt         the last "halt" while no "resume" follows it, else None
        end          the "end" record, else None
        per_topic    {topic id: the questions that carried it}. "open" and "close" are no topic

    "For the awaited step" means since the last record of a reply that was read (REPLIES). A
    "halt" or a "lost" that stands, and a count that is used up, are cleared by a "resume"
    record and by nothing else. A record of a type this does not know is passed over, as the
    line pl.read_turns() could not read is.
    """
    kind = next((r.get("kind") for r in records if r["t"] == "start"), None) or "interview"
    pos = {"kind": kind, "ready": kind == "debrief", "questions": [], "answers": [], "awaiting": None,
           "rejected": None, "sendbacks": 0, "empties": 0, "lost": None, "again": False, "offered": None,
           "end_checked": False, "spoke": {"participant": kind == "debrief", "interviewer": False},
           "halt": None, "end": None, "per_topic": {}}
    for r in records:
        t = r["t"]
        if t in REPLIES:  # a reply was read: what was lost on the way to it is behind it
            pos.update(lost=None, again=False, empties=0)
            pos["spoke"]["participant" if t in ("card", "ready", "answer") else "interviewer"] = True
        if t in ("card", "ready"):
            pos["ready"] = True
        elif t == "question":
            pos["questions"].append(r)
            pos.update(rejected=None, sendbacks=0, offered=None)
            if r["topic"] not in pl.NOT_TOPIC:
                pos["per_topic"][r["topic"]] = pos["per_topic"].get(r["topic"], 0) + 1
        elif t == "answer":
            pos["answers"].append(r)
            pos["sendbacks"] = 0
        elif t == "rejected":
            pos.update(rejected=r, sendbacks=pos["sendbacks"] + 1)
        elif t == "end-offered":
            pos.update(offered=r, end_checked=True, rejected=None, sendbacks=0)
        elif t == "end":
            pos.update(end=r, offered=None, rejected=None)
        elif t == "lost":
            pos["again"] = True
            if r.get("why") == "empty":
                pos["empties"] += 1
            else:
                pos["lost"] = r
        elif t == "halt":
            pos["halt"] = r
        elif t == "resume":
            pos.update(halt=None, lost=None, sendbacks=0, empties=0)
    opened = bool(pos["questions"]) or pos["end_checked"]
    pos["awaiting"] = (None if pos["end"] else "card" if not pos["ready"] else "opening" if not opened
                       else "answer" if len(pos["questions"]) > len(pos["answers"]) else "question")
    return pos


def _unopened(pos: dict, guide: dict) -> list[str]:
    """The ids of the persona's topics that no question has carried, in the guide's order."""
    return [t["id"] for t in guide["topics"] if not pos["per_topic"].get(t["id"])]


def _closed(pos: dict) -> bool:
    """Whether the last exchange on record was a close: its question carried TOPIC: close."""
    return bool(pos["questions"]) and pos["questions"][-1]["topic"] == "close"


def _holds(said: str, words: str) -> int:
    """Where said holds words as words of their own, -1 when it does not: the first place they
    stand with no letter or digit against them, before or after, in any script (str.isalnum()).
    So an opener is not found where its first or last word is a part of a longer one ("the last
    order" in "the last ordering mistake"), and is found with anything else beside it: a space,
    a comma, a quotation mark, or the full stop that pl.same_line() leaves inside a reply."""
    at = said.find(words)
    while at >= 0 and (said[max(at - 1, 0):at].isalnum() or said[at + len(words):at + len(words) + 1].isalnum()):
        at = said.find(words, at + 1)
    return at


def opened_by(say: str, label: str | None, pos: dict, guide: dict) -> str | None:
    """The topic a question opens by its words, None when they open none: a topic of the guide
    that no question has carried yet (pos["per_topic"]) and whose opener the words under SAY
    hold, word for word once case, white space, curly quotation marks and a closing full stop
    are put aside (pl.same_line()), and as words of their own (_holds()). label is the TOPIC
    the interviewer wrote. With the openers of two such topics in the words it is the one the
    label names, else the one whose opener comes first, and the other stays unopened. This is
    the rule of the module docstring, "The topic of a question": taken() records the topic it
    gives, and keeps the label beside it."""
    said = pl.same_line(say or "")
    openers = {t["id"]: pl.same_line(t["opener"]) for t in guide["topics"] if not pos["per_topic"].get(t["id"])}
    at = {topic: _holds(said, words) for topic, words in openers.items() if words}  # one that is all full stops is none
    held = [topic for topic, where in at.items() if where >= 0]
    if not held:
        return None
    return label if label in held else min(held, key=at.get)


def _reads(pos: dict) -> str:
    """The state an interview that was put down reads as with no "end" and no "halt" in force
    (pl.interview_state()): partial with a turn on record, else pending."""
    return "partial" if pos["questions"] or (pos["ready"] and pos["kind"] != "debrief") else "pending"


def _ended(lost: dict) -> str:
    """Why a "lost" record says its turn left no reply, in words, with what its harness said."""
    return (f"the {lost['side']}'s turn {ENDED.get(lost.get('why'), 'left no reply')}"
            + (f": {lost['reason']}" if lost.get("reason") else ""))


def _step(pos: dict, guide: dict) -> dict:
    """next_step() with no time: the record of an "append" step has no "at" yet."""
    cap, sent, answers = guide["turns"], pos["awaiting"], len(pos["answers"])
    last = answers == cap - 1  # the next question would be the last the cap allows

    def send(side: str, how: str, frame: str) -> dict:
        return {"do": "send", "side": side, "how": how, "frame": frame}

    def stop(state: str, reason: str | None) -> dict:
        return {"do": "stop", "state": state, "reason": reason}

    def end(reason: str, **more) -> dict:
        return {"do": "append", "record": {"t": "end", "by": "cap", "reason": reason, "say": "",
                                           "exchanges": answers, "unopened": _unopened(pos, guide), **more}}

    if pos["end"]:
        return stop("done", None)
    if pos["halt"]:
        return stop(pos["halt"]["state"], pos["halt"].get("reason"))
    if pos["lost"]:
        return stop(_reads(pos), _ended(pos["lost"]))
    if answers >= cap:
        return end(f"the interview reached its cap of {pl.plural(cap, 'exchange')}", close=_closed(pos))
    if sent == "card":
        return send("participant", "launch", "prompt")
    if sent == "answer":
        if pos["empties"] >= 2:
            return stop("partial", "the participant replied with nothing twice")
        return send("participant", "resume", "again" if pos["again"] else "say")
    if pos["sendbacks"] >= 2:  # one send-back for each slot, whatever the reasons
        if last:
            return end(f"the interviewer's question for the last exchange could not be used, so the interview "
                       f"ended one exchange short of its cap of {cap}", close=False, short=True)
        return stop("partial", "the interviewer's reply could not be used twice")
    if pos["rejected"]:
        return send("interviewer", "resume", "repair")
    if pos["offered"]:
        return send("interviewer", "resume", "end-check")
    if sent == "opening":
        return send("interviewer", "launch", "prompt")
    return send("interviewer", "resume", "turn")


def next_step(pos: dict, guide: dict, at: float) -> dict:
    """What a launcher does next with a conversation at position pos (fold()), whose persona has
    that guide (pl.guide()): a step, as the module docstring has them and in the order it gives.
    at is the time now, which the record of an "append" step is stamped with. Pure: the same
    log gives the same step to whichever launcher asks, at the moment of a loss or after a
    later "resume" record, which is what clears a "halt", a "lost" and a count that is used up.

    A side with no reply on record is always launched afresh, whatever became of an earlier
    process of it: it has no session worth resuming. The last exchange is the one whose
    question would be number guide["turns"].
    """
    step = _step(pos, guide)
    if step["do"] == "append":
        step["record"] = {"t": step["record"]["t"], "at": round(at, 3), **step["record"]}
    return step


def malformed(records: list[dict]) -> str | None:
    """What stands in the way of a conversation whose turn log is not as a launcher writes one,
    in words that name each record (pl.turn_lacking()), None for a log that is: 'its turn log
    is of the wrong form (Record 5 (question) lacks "topic", which a launcher always writes)'.
    records are as pl.read_turns() gives them, which sets such a record aside, so that fold(),
    standing() and render() read the well-formed ones alone and none fails on a damaged log.
    What they then give is no account of the interview: whatever acts on a log asks this
    first. "run" and "resume" leave such an interview alone (launch.launch())."""
    wrong = pl.turn_lacking(records)
    return f"its turn log is of the wrong form ({' '.join(wrong).rstrip('.')})" if wrong else None


def standing(records: list[dict], guide: dict) -> dict:
    """How an interview that no launcher carries stands, for "status", the plan and the line said
    when it is put down: {"awaiting", "side", "reason", "reset_at", "limited_by"}.

    "awaiting" is fold()'s. "reason" is why next_step() stops, in words: the "halt" in force,
    else the "lost" record that stands, else the count that is used up. None when nothing on
    the log stops it (it was put down by a stop between two turns, a runner that closed or a
    session that is gone, and the command that put it down said why), and None when it is done.
    A log that is not as a launcher writes one comes before all of those, done or not
    (malformed()): no command goes on with it, and the rest is read from what is left of it.
    "side" is the side the reason is about, the one a "resume --extend" extends: the "halt"'s,
    else the "lost" record's, else the side that speaks next. "reset_at" and "limited_by" are
    the "halt"'s, None when it has none. Nothing of this is written to runs.json."""
    pos = fold(records)
    step, held = _step(pos, guide), ({} if pos["end"] else pos["halt"] or {})
    return {"awaiting": pos["awaiting"],
            "side": held.get("side") or (pos["lost"] or {}).get("side") or SPEAKS.get(pos["awaiting"]),
            "reason": malformed(records) or (step["reason"] if step["do"] == "stop" else None),
            "reset_at": held.get("reset_at"), "limited_by": held.get("limited_by")}


def remark(record: dict) -> str | None:
    """What a launcher says, in a line, of a record it has just added that is no part of an
    interview's usual course and does not stop it by itself: a reply of the interviewer that
    could not be used, an end that was offered with topics unopened, an empty answer. None for
    any other record: a turn that goes as it should is not said, and what stops an interview
    is said by the line that puts it down (standing())."""
    if record["t"] == "rejected":
        return f"a reply of the interviewer could not be used ({', '.join(key for key, _ in record['problems'])})"
    if record["t"] == "end-offered":
        return (f"the interviewer ended with {pl.listed(record['unopened'])} not opened, and is asked once whether "
                "it means it")
    if record["t"] == "lost" and record.get("why") == "empty":
        return _ended(record)
    return None


def taken(pos: dict, guide: dict, side: str, attempt: int, result: dict, leak_terms: list[str],
          at: float) -> list[dict]:
    """The records an attempt that has ended adds to the turn log. pos is the position its
    process was started at (the log has not moved since), side the one that spoke, attempt that
    side's attempt number, at the time now. result is what the launcher made of the process:

        reply     the text it ended with, None when it left none
        ending    None for a process that replied, else why it left no reply: "stop", "time"
                  (limits.turn), "limit" (the side's time), "budget", "usage_limit", "error" or
                  "killed" (its watchdog)
        reason    what its harness said of an ending, when it said anything
        reset_at  when a usage limit lifts, when the harness said
        seconds   how long the process ran, when known: each record made from it has it

    No reply: a "lost" record with that "why", and a "halt" after it wherever "resume" alone is
    not what the lead does next: limited for the side's time or budget ("resume --extend"),
    blocked for a harness that is turning requests away ("resume", later), and failed for an
    error, a killed watchdog or limits.turn on a side that has not spoken yet ("run", which
    launches it afresh). A stop, and any of those three on a side that has spoken, leave the
    "lost" record alone, which stops the interview by itself: nothing puts a turn that hung or
    failed again before the lead has looked.

    A participant's first reply is a "card" or a "ready" only when in_role() knows it for one.
    Otherwise it is "lost" with "why": "role" and the reply, or "empty", and a "halt" failed. A
    later reply is an "answer", or "lost" with "why": "empty" when it holds nothing.

    An interviewer's reply is parsed and put to both gates in one pass. With any problem it is
    "rejected", every problem named. An END is "end-offered" the first time it comes with
    topics unopened and exchanges left, and an "end" otherwise: a confirmed end stands. A
    question is a "question", after an "end-offered" too, which is the interviewer opening a
    topic after all. Its "topic" is the topic its words open, when they hold the opener of one
    that no question has carried (opened_by()), and otherwise the TOPIC it was labelled with.
    Where the two differ, "labelled" keeps the label. The gates above read the label.

    A "halt" has the side and no attempt, so no two records of one settlement share a side and
    attempt (pl.turn_problems()).
    """
    now = round(at, 3)
    made = {"at": now, "side": side, "attempt": attempt,
            **({"seconds": result["seconds"]} if result.get("seconds") is not None else {})}
    reply, said = result.get("reply") or "", ({"reason": result["reason"]} if result.get("reason") else {})

    def halt(state: str, reason: str, **more) -> dict:
        return {"t": "halt", "at": now, "state": state, "side": side, "reason": reason,
                **{k: v for k, v in more.items() if v is not None}}

    why = result.get("ending")
    if why:
        lost = {"t": "lost", **made, "why": why, **said}
        if why in ("limit", "budget"):
            return [lost, halt("limited", _ended(lost), limited_by="time" if why == "limit" else "budget")]
        if why == "usage_limit":
            return [lost, halt("blocked", _ended(lost), reset_at=result.get("reset_at"))]
        if why in ("error", "killed", "time") and not pos["spoke"][side]:
            return [lost, halt("failed", _ended(lost))]
        return [lost]

    if side == "participant" and pos["awaiting"] == "card":
        if in_role(reply, guide["card"]):
            return [{"t": "card" if guide["card"] else "ready", **made, "text": reply.strip()}]
        asked = "did not write its situation card" if guide["card"] else 'did not reply "Ready"'
        lost = {"t": "lost", **made, **({"why": "role", "reply": reply} if reply.strip() else {"why": "empty"})}
        return [lost, halt("failed", f"the participant {asked}: {TOO_SMALL}")]
    if side == "participant":
        if not reply.strip():
            return [{"t": "lost", **made, "why": "empty"}]
        return [{"t": "answer", **made, "n": len(pos["questions"]), "text": reply.strip()}]

    answers, unopened = len(pos["answers"]), _unopened(pos, guide)
    parsed = parse_reply(reply, [t["id"] for t in guide["topics"]])
    problems = list(parsed["problems"])
    found = leak(parsed["say"], leak_terms) if parsed["form"] != "end" else None
    if found:
        problems.append(["leak", found])
    if answers == guide["turns"] - 1 and parsed["topic"] not in (None, "close"):
        problems.append(["last-exchange", ""])
    if problems:
        return [{"t": "rejected", **made, "problems": problems, "reply": reply}]
    if parsed["form"] == "question":
        topic = opened_by(parsed["say"], parsed["topic"], pos, guide) or parsed["topic"]
        return [{"t": "question", **made, "n": answers + 1, "topic": topic,
                 **({"labelled": parsed["topic"]} if topic != parsed["topic"] else {}), "move": parsed["move"],
                 "why": parsed["why"], "say": parsed["say"]}]
    words = {"reason": parsed["reason"], "say": parsed["say"] or ""}
    if unopened and answers < guide["turns"] and not pos["end_checked"]:
        return [{"t": "end-offered", **made, **words, "unopened": unopened}]
    return [{"t": "end", **made, "by": "interviewer", **words, "exchanges": answers, "unopened": unopened,
             "close": _closed(pos)}]


# ---------------------------------------------------------------- the messages

def status_line(pos: dict, guide: dict) -> str:
    """The line an interviewer gets under each answer: "Exchange 9 of 30. T2: 4 of 8. Not
    opened: T3." The answers on record of the interview's cap; the topic of the last question
    and the questions that have carried it, of its cap, left out when that topic is "open" or
    "close"; and the persona's topics no question has carried, left out when there is none."""
    caps = {t["id"]: t["turns"] for t in guide["topics"]}
    topic, unopened = (pos["questions"][-1]["topic"] if pos["questions"] else None), _unopened(pos, guide)
    return " ".join([f"Exchange {len(pos['answers'])} of {guide['turns']}.",
                     *([f"{topic}: {pos['per_topic'][topic]} of {caps[topic]}."] if topic in caps else []),
                     *([f"Not opened: {', '.join(unopened)}."] if unopened else [])])


def cap_notices(pos: dict, guide: dict) -> str:
    """The notices that ride under the status line, each on a line, "" when none applies:
    "topic-cap" when the topic of the last question has had as many questions as its cap, then
    "last-question" when one exchange is left of the interview's cap."""
    caps = {t["id"]: t["turns"] for t in guide["topics"]}
    topic = pos["questions"][-1]["topic"] if pos["questions"] else None
    return "\n".join([*([notice("topic-cap", topic=topic)] if topic in caps and pos["per_topic"][topic] >= caps[topic]
                        else []),
                      *([notice("last-question")] if guide["turns"] - len(pos["answers"]) == 1 else [])])


def _said(problems: list) -> list[str]:
    """One sentence of the notices for each problem of a "rejected" record, in its order."""
    return [notice(f"repair-{key}", fields=detail, term=detail) for key, detail in problems]


def message(step: dict, pos: dict, guide: dict) -> str:
    """What a "send" step with "how": "resume" sends, by its frame. Each frame but "say" is an
    asset, filled by pl.fill_brief(), which looks for placeholders in the asset and never in a
    value: an answer that holds one is delivered as written.

        say        the words of the last question, and nothing else
        again      assets/participant-again.md around the same words
        turn       assets/interviewer-turn.md: the last answer, status_line() and cap_notices()
        repair     assets/interviewer-repair.md: a sentence a line for each problem of the
                   reply that was sent back
        end-check  assets/interviewer-end-check.md: the topics that were not opened

    An interviewer's frame that is put again (pos["again"]) has the "again" notice above it. A
    "launch" step sends the side's prompt in prompts/ as it is, which the launcher reads: this
    is not asked for the frame "prompt".
    """
    frame = step["frame"]
    if frame == "say":
        return pos["questions"][-1]["say"]
    if frame == "again":
        return pl.fill_brief("participant-again.md", {"QUESTION": pos["questions"][-1]["say"]}).strip()
    if frame == "turn":
        text = pl.fill_brief("interviewer-turn.md", {"ANSWER": pos["answers"][-1]["text"],
                                                     "STATUS": status_line(pos, guide),
                                                     "CAP_NOTICE": cap_notices(pos, guide)})
    elif frame == "repair":
        text = pl.fill_brief("interviewer-repair.md", {"PROBLEM": "\n".join(_said(pos["rejected"]["problems"]))})
    elif frame == "end-check":
        left = pos["offered"]["unopened"]
        text = pl.fill_brief("interviewer-end-check.md", {"UNOPENED": notice(
            "end-check-one" if len(left) == 1 else "end-check-many", topics=pl.listed(left))})
    else:
        raise ValueError(f'no message is made for the frame "{frame}"')
    return f"{notice('again')}\n\n{text.strip()}" if pos["again"] else text.strip()


# ---------------------------------------------------------------- the transcripts

def _facts(cfg: dict, entry: dict) -> list[str]:
    """The recruitment facts of a participant, a line each: name, role, segment, model key."""
    persona = next((p for p in cfg["personas"] if p["id"] == entry["persona"]), {})
    return [line for line in (f"- Participant: {entry['name']}",
                              f"- Role: {persona['role']}" if persona.get("role") else "",
                              _segment_line(cfg, persona or entry), f"- Model: {entry['key']}") if line]


def _quoted(text: str) -> list[str]:
    """Text as a markdown quotation, so that a heading inside it is none of the transcript's."""
    return [f"> {line}".rstrip() for line in text.strip().split("\n")]


def _end_line(end: dict, guide: dict) -> list[str]:
    """How an interview ended, in brackets: by whom, after how many exchanges, with which topics
    never opened, and the closing line of an interviewer's END, which was not sent."""
    after = pl.plural(end["exchanges"], "exchange")
    if end["by"] == "interviewer":
        said = f"[Ended by the interviewer after {after}: {end['reason']}"
    elif end.get("short"):
        said = (f"[Ended after {after}, one short of the cap of {guide['turns']}: the interviewer's question for the "
                "last exchange could not be used. There was no close")
    else:
        said = f"[Ended at the cap of {after}" + ("" if end.get("close") else ". The last exchange was not a close")
    unopened = f" Not opened: {', '.join(end['unopened'])}." if end.get("unopened") else ""
    closing = [f"[The interviewer's closing line, which was not sent: {end['say']}]"] if end.get("say") else []
    return [f"{said.rstrip('.')}.{unopened}]", *closing]


def render(cfg: dict, entry: dict, records: list[dict], analysts: bool = False) -> str:
    """The transcript of one conversation, as markdown under the synthetic panel notice
    (pl.NOTICE), from the records of its turn log. entry is the participant's runs.json entry.

    The full transcript, interviews/<run id>.md: the recruitment facts; the situation card,
    quoted, under a heading that says the interviewer never saw it; each exchange as "### <n>"
    with its topic (and the label the interviewer gave it, where its words opened another topic:
    "labelled"), move and reason, "**Q:**" and "**A:**"; and a line in brackets where a
    reply of the interviewer was sent back, a turn left no reply, the end check was asked, and
    at the end how the interview ended, or that it has not and why (standing()). A log that
    is not as a launcher writes one is named there too (malformed()): what a record of it that
    was set aside held is in neither transcript.

    analysts: the analysts' copy, analysis/transcripts/<run id>.md. The recruitment facts and
    every exchange that has its answer, as "### <n>", "**Q:**", "**A:**", and nothing else: no
    card, no topic, move or reason, and no line in brackets, so nothing of the interviewer's
    notes or of the launcher's reaches an analyst.
    """
    pos = fold(records)
    debrief = pos["kind"] == "debrief"
    guide = pl.guide(cfg, entry["persona"], "debrief" if debrief else "interview")
    areas = {t["id"]: t["area"] for t in guide["topics"]}
    answers = {r["n"]: r for r in pos["answers"]}
    out = [f"# {'Debrief' if debrief else 'Interview'} {entry['run']}: {entry['name']}", "", *_facts(cfg, entry)]
    if analysts:
        out += ["", "## Exchanges"]
        for q in (q for q in pos["questions"] if q["n"] in answers):
            out += ["", f"### {q['n']}", "", f"**Q:** {q['say']}", "", f"**A:** {answers[q['n']]['text']}"]
        return pl.with_notice("\n".join(out) + "\n")

    notes = []  # the lines in brackets that wait for the place they belong: under the next heading, or an answer

    def noted() -> list[str]:
        waiting = [line for note in notes for line in (note, "")]
        notes.clear()
        return waiting

    for r in records:
        t = r["t"]
        if t == "card":
            out += ["", "## Situation card (private: the interviewer never saw it)", "", *_quoted(r["text"]),
                    "", "## Exchanges"]
        elif t == "ready" or (t == "start" and debrief):
            out += ["", "## Exchanges"]
        elif t == "question":
            topic = f"{r['topic']}, {areas[r['topic']]}" if r["topic"] in areas else r["topic"]
            topic += f" (the interviewer labelled it {r['labelled']})" if r.get("labelled") else ""
            out += ["", f"### {r['n']}", "", *noted(), f"- Topic: {topic}", f"- Move: {r['move']}",
                    f"- Why: {r['why']}", "", f"**Q:** {r['say']}"]
        elif t == "answer":
            out += ["", *noted(), f"**A:** {r['text']}"]
        elif t == "rejected":
            notes.append("[A reply of the interviewer could not be used and was sent back. "
                         f"{' '.join(_said(r['problems']))}]")
        elif t == "lost":
            notes.append(f"[A turn left no reply: {_ended(r)}.]")
        elif t == "end-offered":
            notes.append(f"[The interviewer ended the interview with {pl.listed(r['unopened'])} not opened "
                         f"({r['reason']}), and was asked once whether it meant it.]")
    if pos["end"]:
        wrong = malformed(records)
        notes += _end_line(pos["end"], guide)
        notes += [f"[{wrong[0].upper()}{wrong[1:]}: what such a record held is not shown.]"] if wrong else []
    else:
        stands = standing(records, guide)
        waits = {"card": "the participant has not written its first reply",
                 "opening": "the interviewer has not asked its first question",
                 "answer": f"question {len(pos['questions'])} has no answer on record",
                 "question": "the interviewer has not replied to the last answer"}[pos["awaiting"]]
        notes.append(f"[Not finished: {waits}" + (f", and {stands['reason']}" if stands["reason"] else "") + ".]")
    out += ["", "## End", "", *noted()]
    return pl.with_notice("\n".join(out).rstrip("\n") + "\n")


def write_transcripts(cfg: dict, run: str) -> list[Path]:
    """Write both transcripts of an interview from its turn log, interviews/<run id>.md and the
    analysts' copy analysis/transcripts/<run id>.md, each in one step, and return the two
    paths. An interview with no turn on record (pl.SPOKEN) has nothing to show: nothing is
    written, and [] is returned.

    The log is read again once the files are written, and they are written again when it has
    grown meanwhile: a render that runs beside a launcher can then never leave an older
    transcript over the one the launcher writes when the interview ends, whichever writes
    last. Under the study lock the second look finds nothing new.
    """
    sd = cfg["_dir"]
    entries = pl.read_runs(sd) if (sd / "runs.json").exists() else pl.planned_runs(cfg)
    entry = next((e for e in entries if e["run"] == run and e["role"] == "panellist"), None)
    if entry is None:
        raise SystemExit(f"{run} is not a run of this study, so it has no transcript to write.")
    paths, written = [sd / pl.INTERVIEWS / f"{run}.md", sd / pl.TRANSCRIPTS / f"{run}.md"], None
    while True:
        records = pl.read_turns(sd, run)
        if records == written:
            return paths
        if not any(r["t"] in pl.SPOKEN for r in records):
            return []
        for path, analysts in zip(paths, (False, True)):
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                pl.write_atomic(path, render(cfg, entry, records, analysts))
            except OSError as err:
                raise SystemExit(pl.not_written(path, err))
        written = records


# ---------------------------------------------------------------- the checks

def _exchanges(numbers: list[int]) -> str:
    """Exchange numbers as a note names them: "exchange 4", "exchanges 4, 7 and 9"."""
    return f"{pl.agree(len(numbers), 'exchange')} {pl.listed([str(n) for n in numbers])}"


def _leaked(text: str, terms: list[str]) -> list[str]:
    """Every "leak_terms" entry a text holds, ignoring case, as study.json writes it."""
    low = (text or "").lower()
    return [term for term in terms if term.lower() in low]


def _form(sentences: list[str]) -> str:
    """What is wrong with the form of a turn log, as one blocking problem of the table."""
    return f"{MALFORMED}: {' '.join(sentences).rstrip('.')}"


def problems(cfg: dict, entry: dict, records: list[dict], state: str) -> tuple[list[str], list[str]]:
    """What check_runs.py says of one interview: (blocking, notes), as the module docstring lists
    them ("The checks"). entry is the participant's runs.json entry, records its turn log as
    pl.read_turns() gives it, [] for an interview that was never started, and state what the
    interview reads as (pl.run_records(), which is told whether a launcher has the study). Each
    is a phrase for a cell of the table, with no full stop. A blocking problem opens with
    NO_END, MALFORMED or LEAKED, which is how advice() knows it.

    The form of the log is looked at first. A log with a record of no known type, or one that
    lacks a field every launcher writes or holds another kind of value than one writes
    (pl.turn_lacking()), has that one blocking problem and nothing else of it is checked:
    pl.read_turns() has set that record aside, so every check below would be of a log without
    it, and would find nothing wrong with what it cannot see."""
    wrong = pl.turn_problems(records)
    if pl.turn_lacking(records):
        return [_form(wrong)], []
    sd, run, terms = cfg["_dir"], entry["run"], cfg["leak_terms"]
    pos, guide = fold(records), pl.guide(cfg, entry["persona"])
    questions, answers, end = pos["questions"], pos["answers"], pos["end"]
    blocking, notes = [], []
    if not end:
        far = (f"after {len(answers)} of {guide['turns']} exchanges" if any(r["t"] in pl.SPOKEN for r in records)
               else "with no turn on record")
        blocking.append(f"{NO_END}: it reads {state}, {far}")
    blocking += [_form(wrong)] if wrong else []
    for term in dict.fromkeys(t for q in questions for t in _leaked(q["say"], terms)):
        held = [q["n"] for q in questions if term in _leaked(q["say"], terms)]
        blocking.append(f'{LEAKED} "{term}" in {pl.agree(len(held), "question")} '
                        f"{pl.listed([str(n) for n in held])}, which {pl.agree(len(held), 'was', 'were')} delivered")

    caps = {t["id"]: t["turns"] for t in guide["topics"]}
    if end:
        unopened = [t for t in caps if not pos["per_topic"].get(t)]
        if unopened:
            notes.append(f"{pl.agree(len(unopened), 'topic', 'topics')} never opened: {', '.join(unopened)}")
        if end.get("by") == "cap" and not end.get("close"):
            notes.append(f"ended at its cap of {pl.plural(guide['turns'], 'exchange')} with no close"
                         + (", one exchange short" if end.get("short") else ""))
    notes += [f"{topic} had {pos['per_topic'][topic]} exchanges, {pos['per_topic'][topic] - cap} past its cap of {cap}"
              for topic, cap in caps.items() if pos["per_topic"].get(topic, 0) > cap]
    notes += [f"question {q['n']} holds the opener of {q['topic']} and was labelled {q['labelled']}: it is counted "
              f"under {q['topic']}" for q in questions if q.get("labelled")]
    said = [("its card", r["text"]) for r in records if r["t"] == "card"]
    said += [(f"answer {a['n']}", a["text"]) for a in answers]
    for term in dict.fromkeys(t for _, text in said for t in _leaked(text, terms)):
        held = [where for where, text in said if term in _leaked(text, terms)]
        notes.append(f'leak term "{term}" in {pl.listed(held)}')
    out_of_role = [(a["n"], AI_TALK.search(a["text"])) for a in answers]
    out_of_role = [f'{n} ("{found.group(0)}")' for n, found in out_of_role if found]
    if out_of_role:
        notes.append(f"speaks of being an AI, a model or a persona in {pl.agree(len(out_of_role), 'answer')} "
                     f"{pl.listed(out_of_role)}")
    crowded = [q["n"] for q in questions if q["say"].count("?") > QUESTION_MARKS]
    if crowded:
        notes.append(f"more than {QUESTION_MARKS} question marks in {pl.agree(len(crowded), 'question')} "
                     f"{pl.listed([str(n) for n in crowded])}")
    lengths = [len(a["text"].split()) for a in answers]
    if lengths and statistics.median(lengths) > LONG_ANSWER:
        notes.append(f"long answers: a median of {statistics.median(lengths):g} words, over {LONG_ANSWER}")
    repairs = sum(r["t"] == "rejected" for r in records)
    if repairs:
        notes.append(f"{pl.plural(repairs, 'reply', 'replies')} of the interviewer sent back for repair")
    lost = [r for r in records if r["t"] == "lost"]
    if lost:
        sides = [f"{pl.plural(n, 'turn')} of the {side}" for side in pl.SIDES
                 for n in [sum(r["side"] == side for r in lost)] if n]
        notes.append(f"{pl.listed(sides)} left no reply"
                     + (f" and {pl.agree(len(lost), 'was', 'were')} put again" if end else ""))
    if pl.turn_torn(sd, run):
        notes.append("its turn log ends in a write that a killed launcher never finished, which is not read")
    return blocking, notes


def advice(cfg: dict, found: list[tuple[str, str, list[str]]]) -> list[str]:
    """What the lead does about the blocking rows of check_runs.py, as the lines it prints under
    its table: [] when no interview has one. found has (run id, state, blocking) for every
    interview, with blocking as problems() returns it."""
    sd, out = cfg["_dir"], []
    open_ = [(run, state) for run, state, blocking in found if any(b.startswith(NO_END) for b in blocking)]
    if open_:
        def way(state: str) -> tuple:  # what is said of it: its command, and apart from that whether it ever started
            return CONTINUES[state], state == "pending"

        ways = []
        for command, unstarted in dict.fromkeys(way(state) for _, state in open_):
            ids = [run for run, state in open_ if way(state) == (command, unstarted)]
            states = pl.listed(list(dict.fromkeys(state for _, state in open_ if way(state) == (command, unstarted))),
                               "or")
            ways.append(f"{', '.join(ids)}: a launcher is carrying {pl.agree(len(ids), 'it', 'them')}. Check "
                        "again when it has finished." if command is None else
                        f"{', '.join(ids)} ({states}): {pl.agree(len(ids), 'it has', 'they have')} not started. "
                        f"Start {pl.agree(len(ids), 'it', 'them')} with launch.py {sd} {command}" if unstarted else
                        f"{', '.join(ids)} ({states}): launch.py {sd} {command.replace('<ids>', ','.join(ids))}")
        stopped = [run for run, state in open_ if state in STOPPED]
        out += ["No end record: an interview that has not ended is not analysed. Go on with each by the command "
                "for the state it reads as."
                + (f" launch.py {sd} status says why {'each' if len(stopped) == len(open_) else ', '.join(stopped)} "
                   "stopped." if stopped else ""),
                *(f"  {way}" for way in ways)]
        if any(state == "blocked" for _, state in open_):
            out.append("  A blocked interview goes on once its harness takes requests again: status says when its "
                       "limit lifts, where the harness said.")
    odd = [run for run, _, blocking in found if any(b.startswith(MALFORMED) for b in blocking)]
    if odd:
        out.append(f"Turn log of the wrong form ({', '.join(odd)}): a launcher writes none like it, so the log was "
                   "changed by hand or damaged. Put back what was changed, or discard the interview.")
    leaked = [run for run, _, blocking in found if any(b.startswith(LEAKED) for b in blocking)]
    if leaked:
        out.append(f"Leak term in a delivered question ({', '.join(leaked)}): it cannot be undone, the participant "
                   "has read it. Discard the interview, or keep it and report the leak with whatever is drawn "
                   "from it.")
    if leaked or odd:
        out.append(f"  To discard an interview and hold it again: move {pl.INTERVIEWS}/<run id>.jsonl into logs/, then "
                   f"launch.py {sd} run --runs <run id>, which launches both sides anew.")
    return out


def measured(done: list[dict]) -> dict | None:
    """What one side of the finished interviews of a model entry used for each exchange, for the
    plan's estimate. done has one {"exchanges", "tokens", "seconds"} for each finished interview:
    its answers on record, the input and output tokens that side's sessions reported (None when
    its harness reported none, or what it reported is known to be short) and that side's own
    process time. Returns {"interviews", "exchanges", "tokens", "seconds"}: how many there are,
    their mean length in exchanges, and tokens and seconds an exchange, each None when no
    interview that has the figure had an exchange. None for no finished interview. The card,
    a repair and the turn that ends an interview are processes too, and are in the figures: an
    exchange costs what the interview cost, divided by its exchanges."""
    if not done:
        return None

    def each(figure: str):
        known = [d for d in done if d[figure] is not None and d["exchanges"]]
        return sum(d[figure] for d in known) / sum(d["exchanges"] for d in known) if known else None

    return {"interviews": len(done), "exchanges": sum(d["exchanges"] for d in done) / len(done),
            "tokens": each("tokens"), "seconds": each("seconds")}


# ---------------------------------------------------------------- the commands

def conversations(runs: list[dict]) -> list[str]:
    """The run id of every conversation runs.json has, in its order: one for each interviewer's
    entry, which an interview has and a debrief too."""
    return [e["interview"] for e in runs if e["role"] == "interviewer" and "interview" in e]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    ap.add_argument("cmd", choices=["render"])
    ap.add_argument("--runs", help="render: comma-separated run ids (default: every interview with a turn on record)")
    args = ap.parse_args()
    import launch  # here and never at the top: launch.py imports this module
    cfg = pl.load_study(args.study_dir)
    sd, held = cfg["_dir"], conversations(pl.read_runs(cfg["_dir"]))
    if not held:
        raise SystemExit("This study has no interview, so it has no transcript to write.")
    wanted = [r.strip() for r in args.runs.split(",") if r.strip()] if args.runs else held
    unknown = [r for r in wanted if r not in held]
    if unknown:
        raise SystemExit(f"No interview of this study has the run id {pl.listed(unknown, 'or')}. Its interviews: "
                         f"{', '.join(held)}.")
    lock = launch.Lock(sd)
    mine = lock.acquire("interview render", 0, must=False)
    try:
        if not mine:
            launch.say("A launcher has this study." if launch.Lock.holder(sd) else
                       "This study could not be taken from this shell.",
                       "The transcripts are written all the same, from the turns on record now. A launcher writes "
                       "an interview's again when it ends.")
        written = {run: write_transcripts(cfg, run) for run in wanted}
    finally:
        lock.release()
    for run, paths in written.items():
        if not paths and args.runs:
            launch.say(f"{run}: no turn on record yet, so no transcript was written.")
    done = [run for run, paths in written.items() if paths]
    launch.say(f"Wrote the transcripts of {pl.plural(len(done), 'interview')} to {sd / pl.INTERVIEWS}/ and the "
               f"analysts' copies to {sd / pl.TRANSCRIPTS}/." if done else
               "No interview of this study has a turn on record yet, so no transcript was written.")


if __name__ == "__main__":
    import interview  # the module launch.py imports, so that the script and that module are one object
    interview.main()
