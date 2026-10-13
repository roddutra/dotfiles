"""What a fake CLI does when it plays one side of an interview: one process, one reply. Shared by
fake_claude.py and fake_codex.py, which ask here before panellist.py.

Switched on by $FAKE_PANEL, as panellist.py is, and by where the process was started: in
.../panel/rooms/<run id> it is the participant of that run, entry <run id>, and in
.../interviewer/<run id> its interviewer, entry interviewer-<run id>. Anywhere else this plays
nothing. It has no tools to refuse or to use, so whatever its command says of tools is all the
same to it.

    plan.json       {"<entry id>": [[step, ...], ...]}: one list of steps for each process started
                    for that entry, the last list repeating. An entry the plan leaves out, and a
                    list that sets no reply, gets the reply below
    go/<gate>       created by the test to release a "wait:<gate>" step
    sessions/, attempts/, talk/   the fake's own memory: which entry a session id belongs to, how
                    many processes each entry has had, and what an interviewer knows of its interview

A resume of a session it has no record of ends as the real CLI ends one: its own message on
stderr, nothing on stdout, exit code 1.

Steps that set the reply the process ends with:

    say:<text>      the text as it is: a card, an answer, a first reply that refuses the role, or
                    an interviewer's reply that will not parse. "say:" alone is an empty reply
    ask:<topic>[:<move>[:<words>]]   a well-formed reply of the interviewer with that topic, MOVE
                    "anchor" unless given, and under SAY "Question <k>?", k being the exchange it
                    opens, or the words given: a leak term, or a marker
    why:<words>     the WHY of this entry's replies from here on, in this process and every later
                    one, to plant a marker
    finish:<reason> the END form, with that reason
    code:<n>        the process prints its reply as usual and then exits with that code

Every step of panellist.py that is about the process works here as it does there
(panellist.process_step()): wait:<gate>, starts:<n>, deaf, spawn, hang, end:<mode>, exit:<code>
and fail:<words>. So a usage limit is ["end:usage_limit"], a hang ["hang"] and a process that dies
in the middle of its turn ["wait:<gate>", "exit:1"].

With no reply set, a participant answers its prompt with a card of the parts its last section asks
for, each under its label, or with "Ready" when that asks for no card, and every question after that
with "Answer <k>.", k being the number in a "Question <k>?" or else how many replies it has
given. An interviewer opens the first topic its prompt lists with MOVE "open", then the first
topic its status line names as not opened, then asks TOPIC "close" when the status line shows one
exchange left or no topic unopened, then ends once that is answered. Asked whether it means an end, it ends again.
Sent anything else that has no status line, as a repair is, it replies as it would have to the
last status line it saw. So an interview nobody planned runs to its end.

$FAKE_CLI_LOG gets the events panellist.py logs, "run" being the entry id, and in "start" the
process's "stdin", which is how a test reads what each side was sent, and its "side".
"""

import json
import os
import re
import sys
from pathlib import Path

import panellist

CARD_PART = re.compile(r"^\d+\.\s+\*\*(.+?):?\*\*", re.M)  # a part of the card, as the prompt asks for it
FIRST_TOPIC = re.compile(r"^1\. (\w+), .*Cap: ", re.M)    # the first topic of the guide, in the interviewer's prompt
STATUS = re.compile(r"Exchange (\d+) of (\d+)\.(?:.*?Not opened: ([^.]+)\.)?")  # the status line under an answer
NUMBERED = re.compile(r"Question (\d+)\?")
WHY = "Following the guide."


def who():
    """(side, run id) by the folder this process was started in, (None, None) outside an interview."""
    parts = Path.cwd().parts
    if parts[-3:-1] == ("panel", "rooms"):
        return "participant", parts[-1]
    if parts[-2:-1] == ("interviewer",):
        return "interviewer", parts[-1]
    return None, None


def question(topic, move, words, why):
    return f"TOPIC: {topic}\nMOVE: {move}\nWHY: {why}\nSAY:\n{words}"


def ending(reason):
    return f"END: {reason}\nSAY:\nThank you, that is everything."


def unplanned(side, resumed, prompt, replies, known):
    """The reply of a process whose steps set none (module docstring): text, or (topic, move) for
    a question. known is the interviewer's memory: "first", the first topic of its guide; "k",
    the exchange its next question opens; with a status line seen, "left", the topics not
    opened, and "last", whether one exchange is left; "closed", the exchange it asked its close
    for; and "ended", whether its last reply was an end."""
    if side == "participant":
        if resumed:
            asked = NUMBERED.search(prompt)
            return f"Answer {asked.group(1) if asked else replies}."
        parts = CARD_PART.findall(prompt.rsplit("\n## ", 1)[-1])  # the request for the first reply ends the prompt
        return "\n".join(f"**{part}:** notes on {part.lower()}." for part in parts) or "Ready"
    if known.get("ended"):  # asked whether it means its end: it does
        return ending("Everything I came for is covered.")
    if "left" not in known:  # no answer has come yet
        return (known["first"], "open")
    if known["last"]:
        return ("close", "close")
    if known["left"]:
        return (known["left"][0], "open")
    if known.get("closed", known["k"]) < known["k"]:  # its close has been answered
        return ending("Everything I came for is covered.")
    return ("close", "close")


def play(cli, session, resumed, prompt, recording, modes, lost):
    """Play one process of one side of an interview and exit. Returns without doing anything when
    no plan is in force or the process was started outside an interview's folders. The arguments
    are panellist.play()'s."""
    home, (side, run) = os.environ.get("FAKE_PANEL"), who()
    if not home or not side:
        return
    home, entry = Path(home), run if side == "participant" else f"interviewer-{run}"
    session_file = home / "sessions" / f"{session}.json"
    if resumed and not session_file.exists():
        sys.stderr.write(lost)
        sys.exit(1)
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(json.dumps([entry, None]))
    counter = home / "attempts" / entry
    counter.parent.mkdir(exist_ok=True)
    attempt = len(counter.read_text()) if counter.exists() else 0
    counter.write_text("x" * (attempt + 1))
    plan = json.loads((home / "plan.json").read_text()) if (home / "plan.json").exists() else {}
    steps = plan.get(entry) or [[]]
    steps = steps[min(attempt, len(steps) - 1)]

    memory = home / "talk" / f"{entry}.json"
    known = json.loads(memory.read_text()) if memory.exists() else {"k": 1, "why": WHY}
    status, first = STATUS.search(prompt) if resumed else None, FIRST_TOPIC.search(prompt)
    if not resumed and first:
        known["first"] = first.group(1)
    if status:  # an answer came, under it where the interview stands
        done, cap, left = int(status.group(1)), int(status.group(2)), status.group(3)
        known.update(k=done + 1, last=done == cap - 1, left=[t.strip() for t in left.split(",")] if left else [])

    panellist.log(event="start", cli=cli, run=entry, side=side, attempt=attempt + 1, resumed=resumed, session=session,
                  pid=os.getpid(), argv=sys.argv[1:], stdin=prompt, cwd=os.getcwd(), browser=panellist.browser(),
                  account=None)
    cut_off = recording("killed").splitlines(keepends=True)
    sys.stdout.write("".join(cut_off[:1]))  # a CLI that prints events names its session before anything else
    sys.stdout.flush()

    said, code = [], [0]  # the reply a step set: text, or (topic, move, words) for a question; and the exit code

    def end(mode):
        """Print the recorded run of that mode, with the reply in it when it is "ok", and exit."""
        name, exit_code = modes[mode] if mode in modes else ("killed", 1)
        reply = None
        if mode == "ok":
            reply = said[-1] if said else unplanned(side, resumed, prompt, attempt, known)
            if isinstance(reply, tuple):
                topic, move, words = (*reply, None)[:3]
                if topic == "close":
                    known["closed"] = known["k"]
                reply = question(topic, move, words or f"Question {known['k']}?", known["why"])
            known["ended"] = reply.startswith("END:")
            exit_code = code[0] or exit_code
        memory.parent.mkdir(exist_ok=True)
        memory.write_text(json.dumps(known))
        sys.stdout.write(recording(name, reply))
        sys.stdout.flush()
        panellist.log(event="end", run=entry, pid=os.getpid(), code=exit_code)
        sys.exit(exit_code)

    for step in steps:
        verb, _, arg = step.partition(":")
        if verb == "say":
            said.append(arg)
        elif verb == "ask":
            topic, move, words = (*arg.split(":", 2), None, None)[:3]
            said.append((topic, move or "anchor", words))
        elif verb == "why":
            known["why"] = arg
        elif verb == "finish":
            said.append(ending(arg))
        elif verb == "code":
            code[0] = int(arg)
        elif not panellist.process_step(verb, arg, home, entry, cut_off, end):
            raise SystemExit(f"fake CLI: unknown step {step!r}")
    end("ok")
