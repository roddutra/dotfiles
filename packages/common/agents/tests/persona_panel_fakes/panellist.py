"""What a fake CLI does when it plays a whole panellist run, or an analyst or writer job. Shared
by fake_claude.py, fake_codex.py and fake_pi.py.

Switched on by $FAKE_PANEL, a directory the test owns:

    plan.json       {"<run id>": [[step, ...], ...]}: one list of steps per process started for
                    that run, the last list repeating. A run the plan leaves out writes
                    everything and ends ok
    go/<gate>       created by the test to release a "wait:<gate>" step
    sessions/, attempts/   the fake's own memory: which run a session id belongs to, and how
                    many processes each run has had

The run is the one whose persona file the prompt names (.../personas/<pid>-<slug>--<key>.md is
run <pid>-<key>). A prompt with a "## Produce `<file>`" or "## Output: `<file>`" heading is a
job's brief instead: .../analysis/qual-<n>.md is the job analyst-<n> and .../analysis/SYNTHESIS.md
the job writer, and that file is what the job writes. A resume message names no file, so a
resumed process finds its run by its session id, which the fake recorded at launch. A resume of
a session it has no record of ends as the real CLI ends one: its own message on stderr, nothing
on stdout, exit code 1. A test loses a session by deleting sessions/<session id>.json.

Steps, in the order given:

    write:<n>       append the next n concept sections, scored, in the file's review order
    write:all       append every concept section still missing, then the final sections.
                    For a job, any write step writes its whole output file
    final           append the final sections only
    meddle:<run id> append a line to the persona file of another run, <pid>-<key>: a panellist
                    writing outside its own file
    followup        append the "## Follow-up <n>" section the message asks for, with the
                    question quoted: what a panellist does with a follow-up question
    rescore         raise the first score of the first concept section by one: a panellist
                    changing a score it had already given
    cut             cut the persona file off before its last concept section: a panellist that
                    rewrote its file and lost the end of it
    reply           end with DOCUMENT as the final reply, in place of the recorded one: what a
                    job that could not write its file returns
    wait:<gate>     block until the test creates go/<gate>
    starts:<n>      block until n runs have started in all (two runs holding here overlap for sure)
    stubborn        from now on, SIGTERM does not end the process: it appends one more section
                    at once, logs "term" and carries on
    spawn           start a process of its own that ignores SIGTERM and outlives this one, and
                    log its pid: what a CLI leaves behind
    hang            print a run cut off part-way, then sleep until killed
    end:<mode>      print that recorded run and exit with its code: ok, error, usage_limit,
                    budget, or killed (no closing line, exit code 1). Default: end:ok
    exit:<code>     exit with that code and print nothing more: a process that went quiet long
                    before it ended

Sections have one score column for each factor in the score table of the panel instructions.

$FAKE_CLI_LOG gets one JSON line per event instead of one per invocation:

    {"event": "start", "cli", "run", "attempt", "resumed", "session", "pid", "argv", "stdin", "cwd"}
    {"event": "waiting", "run", "gate"}       {"event": "term", "run"}
    {"event": "spawn", "run", "pid"}
    {"event": "end", "run", "pid", "code"}    (absent when the process was killed)
"""

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

PATIENCE = 30  # seconds a blocked step waits before giving up, so a broken test leaves no process behind
PERSONA_FILE = re.compile(r"(\S+/personas/([^/\s-]+)-[^/\s]*--([^/\s]+)\.md)")
JOB_OUTPUT = re.compile(r"^## (?:Produce|Output:) `(\S+/analysis/(?:qual-(\d+)|SYNTHESIS)\.md)`", re.M)
DOCUMENT = "I could not write the file, so here is the document.\n\n# Findings\n\n- From the reply.\n```"


def log(**event):
    if os.environ.get("FAKE_CLI_LOG"):
        with open(os.environ["FAKE_CLI_LOG"], "a") as f:
            f.write(json.dumps(event) + "\n")


def events():
    path = os.environ.get("FAKE_CLI_LOG")
    lines = Path(path).read_text().splitlines() if path and Path(path).exists() else []
    return [e for e in map(json.loads, lines) if "event" in e]


def factors(path):
    """How many scores the panel instructions ask for in a section: the columns of their template row."""
    instructions = (path.parents[1] / "_panel-instructions.md").read_text()
    return re.search(r"^\| n(?: \| n)* \|$", instructions, re.M).group(0).count("n")


def write(path, count):
    """Append `count` concept sections ("all": every one missing, then the final sections).
    A job's output file is written whole instead."""
    if path.parent.name == "analysis":
        path.write_text(f"# Findings\n\n- Written to {path.name} by the job itself.\n")
        return
    text = path.read_text()
    listed = re.search(r"\| Review order \| (.+?) \|", text)  # a study with one concept lists no order
    order = ([x.strip() for x in listed.group(1).split(",")] if listed else
             re.findall(r"^### Concept (\w+)$", (path.parents[1] / "_panel-instructions.md").read_text(), re.M))
    missing = [label for label in order if not re.search(rf"^### Concept {label}\b", text, re.M)]
    n = factors(path)
    row = "| " + " | ".join(["7"] * n) + " |"
    for label in missing if count == "all" else [] if count == "final" else missing[:int(count)]:
        text += f"### Concept {label}\n**5-second take (in my words):** fine.\n\n{row.replace('7', 'F')}\n" \
                f"|{'---|' * n}\n{row}\n\n"
    if count in ("all", "final"):
        ranking = "".join(f"{i}. Concept {label} - reason\n" for i, label in enumerate(order, 1))
        text += (f"## Comparison\n### My ranking (best to worst)\n{ranking}\n" if listed else "") + \
                "## Out of character: researcher notes\nNotes.\n"
    path.write_text(text)


def block(until, what):
    give_up = time.time() + PATIENCE
    while not until():
        if time.time() > give_up:
            sys.stderr.write(f"fake CLI: gave up waiting for {what}\n")
            sys.exit(3)
        time.sleep(0.01)


def play(cli, session, resumed, prompt, recording, modes, lost):
    """Play the run or job this process was started for, and exit. Returns without doing
    anything when no plan is in force or the prompt belongs to no run this fake knows.

    recording(name, reply=None) is what the CLI's recorded run `name` prints on stdout under this
    session id, with reply, when given, in place of its final reply. It is first called for
    "killed", whose first line is printed at once. modes maps an end:<mode> to (recording name,
    exit code), and lost is what the real CLI prints on stderr when the session to resume is gone."""
    home = os.environ.get("FAKE_PANEL")
    if not home:
        return
    home = Path(home)
    known = home / "sessions" / f"{session}.json"
    named, job = PERSONA_FILE.search(prompt), JOB_OUTPUT.search(prompt)
    if resumed and not known.exists():
        sys.stderr.write(lost)
        sys.exit(1)
    if resumed:
        run, file = json.loads(known.read_text())
    elif job:
        run, file = (f"analyst-{job.group(2)}" if job.group(2) else "writer"), job.group(1)
    elif named:
        run, file = f"{named.group(2)}-{named.group(3)}", named.group(1)
    else:
        return
    known.parent.mkdir(parents=True, exist_ok=True)
    known.write_text(json.dumps([run, file]))
    counter = home / "attempts" / run
    counter.parent.mkdir(exist_ok=True)
    attempt = len(counter.read_text()) if counter.exists() else 0
    counter.write_text("x" * (attempt + 1))
    plan = json.loads((home / "plan.json").read_text()) if (home / "plan.json").exists() else {}
    steps = (plan.get(run) or [["write:all"]])
    steps, file = steps[min(attempt, len(steps) - 1)], Path(file)

    log(event="start", cli=cli, run=run, attempt=attempt + 1, resumed=resumed, session=session, pid=os.getpid(),
        argv=sys.argv[1:], stdin=prompt, cwd=os.getcwd())
    cut_off = recording("killed").splitlines(keepends=True)
    sys.stdout.write("".join(cut_off[:1]))  # a CLI that prints events names its session before anything else
    sys.stdout.flush()

    said = []  # the reply to end with, when a step set one

    def end(mode):
        name, code = modes[mode] if mode in modes else ("killed", 1)
        sys.stdout.write(recording(name, said[-1] if said and mode == "ok" else None))
        sys.stdout.flush()
        log(event="end", run=run, pid=os.getpid(), code=code)
        sys.exit(code)

    def on_term(*_):
        write(file, 1)
        log(event="term", run=run)

    for step in steps:
        verb, _, arg = step.partition(":")
        if verb == "write":
            write(file, arg)
        elif verb == "final":
            write(file, "final")
        elif verb == "meddle":
            pid, _, key = arg.partition("-")
            other = next(file.parent.glob(f"{pid}-*--{key}.md"))
            other.write_text(other.read_text() + "A line written by another run.\n")
        elif verb == "followup":
            number = re.search(r"`## Follow-up (\d+)`", prompt).group(1)
            asked = re.search(r"^-{10}\n(.*?)\n-{10}$", prompt, re.S | re.M).group(1)
            file.write_text(file.read_text() + f"\n## Follow-up {number}\n\n> {asked}\n\nIn character: it depends.\n")
        elif verb == "rescore":
            file.write_text(re.sub(r"^\| 7 \|", "| 8 |", file.read_text(), count=1, flags=re.M))
        elif verb == "cut":
            whole = file.read_text()
            file.write_text(whole[:whole.rindex("### Concept ")])
        elif verb == "reply":
            said.append(DOCUMENT)
        elif verb == "wait":
            log(event="waiting", run=run, gate=arg)
            block((home / "go" / arg).exists, f"gate {arg}")
        elif verb == "starts":
            block(lambda: sum(e["event"] == "start" for e in events()) >= int(arg), f"{arg} runs to start")
        elif verb == "stubborn":
            signal.signal(signal.SIGTERM, on_term)
        elif verb == "spawn":  # the last argument does nothing: it marks the process as this test's
            left = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(600)", str(home)], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                preexec_fn=lambda: signal.signal(signal.SIGTERM, signal.SIG_IGN))
            log(event="spawn", run=run, pid=left.pid)
        elif verb == "hang":
            sys.stdout.write("".join(cut_off[1:]))
            sys.stdout.flush()
            time.sleep(600)
        elif verb == "end":
            end(arg)
        elif verb == "exit":
            log(event="end", run=run, pid=os.getpid(), code=int(arg))
            sys.exit(int(arg))
        else:
            raise SystemExit(f"fake CLI: unknown step {step!r}")
    end("ok")
