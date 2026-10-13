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
    steps:<n>       usability: how many steps each task attempted from here on takes (default 2)
    act:<n>         usability: take n steps of the next task and write no section for it: a
                    task that was under way when the run was cut off
    intent:<n>      usability: write the intent entry of step n of the next task and nothing
                    more: a panellist that begins a step, as one that ignores its step limit does.
                    intent:<n>@<attempt> writes it under that attempt number, whatever number the
                    run was told: a panellist that numbers a task's attempts itself
    outcome:<words> usability: what the Outcome field of each task section written from here on
                    opens with (default "completed")
    leave           usability: the last step of each task attempted from here on leaves the task's
                    form for the page /help: a panellist that goes looking for help, and stops
    scribble        usability: append to the step log what no panellist should: a line that is
                    no JSON, an entry for a task the study does not have, numbered far above any
                    limit, an intent for step 1 of the first task again, and for the next task an
                    entry that is no step at all, under attempt 999
    empty           usability: empty the step log: a panellist that starts its log again
    link            usability: move the step log to the run's scratch folder and leave a symbolic
                    link to it at its name: a log the launcher cannot read as the run's own
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
    deaf            from now on, SIGTERM does not end the process: it logs "term" and carries on
    spawn           start a process of its own that ignores SIGTERM and outlives this one, and
                    log its pid: what a CLI leaves behind
    hang            print a run cut off part-way, then sleep until killed
    end:<mode>      print that recorded run and exit with its code: ok, error, usage_limit,
                    budget, a run of that CLI alone (unreachable on claude, nested on codex), or
                    killed (no closing line, exit code 1). Default: end:ok
    exit:<code>     exit with that code and print nothing more: a process that went quiet long
                    before it ended
    fail:<words>    write the words on stderr and exit with code 1, printing nothing more: a CLI
                    that fails with a message of its own

Sections have one score column for each factor in the score table of the panel instructions.

A usability run is known by the "## Tasks" list in its persona file. Its units are the tasks
listed there, in that order, and "write" attempts each before it writes the section: for every
step an intent entry, a screenshot file and a result entry, in panel/evidence/<run id>/, as the
usability instructions set them out. Every result entry gives the address <base>/<task>/form,
with the step in its query, <base> being where the instructions say the product runs. A task
that the resume message tells to start again as attempt n is logged as that attempt, with its
screenshots named for it.

$FAKE_CLI_LOG gets one JSON line per event instead of one per invocation:

    {"event": "start", "cli", "run", "attempt", "resumed", "session", "pid", "argv", "stdin", "cwd",
     "browser": {"env", "daemon", "up"}, "account"}  (browser(), below; "account" is what
                                               panel/scratch/<run id>/account.json held, null without one)
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


def browser():
    """The agent-browser session this process was given: the AGENT_BROWSER_* variables it sees, the
    session's daemon as fake_agent_browser.py records it, and whether that process is running now."""
    seen = {k: v for k, v in os.environ.items() if k.startswith("AGENT_BROWSER_")}
    try:
        daemon = int(Path(seen["AGENT_BROWSER_SOCKET_DIR"], seen["AGENT_BROWSER_SESSION"] + ".pid").read_text())
        os.kill(daemon, 0)
    except (KeyError, OSError, ValueError):
        return {"env": seen, "daemon": None, "up": False}
    return {"env": seen, "daemon": daemon, "up": True}


def factors(path):
    """How many scores the panel instructions ask for in a section: the columns of their template row."""
    instructions = (path.parents[1] / "_panel-instructions.md").read_text()
    return re.search(r"^\| n(?: \| n)* \|$", instructions, re.M).group(0).count("n")


TASK_LIST = re.compile(r"^\d+\. \*\*Task (\w+)\.\*\*", re.M)
AGAIN = re.compile(r'Task (\w+) was under way.*?"attempt\\?": (\d+)')
# How this process attempts tasks: play() sets it.
USABILITY = {"steps": 2, "attempts": {}, "run": None, "outcome": "completed", "leave": False}
INTENT = {"phase": "intent", "sees": "A page.", "expects": "The next page.", "action": "Click the button."}


def step_log(path):
    return path.parents[1] / "evidence" / USABILITY["run"] / "steps.jsonl"


def next_task(path):
    text = path.read_text()
    return next(t for t in TASK_LIST.findall(text) if not re.search(rf"^### Task {t}\b", text, re.M))


def act(path, task, steps):
    """Take `steps` steps of a task: two entries in the run's step log and a screenshot for each."""
    evidence = step_log(path).parent
    attempt = USABILITY["attempts"].get(task, 1)
    base = re.search(r"running at `([^`]+)`", (path.parents[1] / "_panel-instructions.md").read_text()).group(1)
    with open(evidence / "steps.jsonl", "a") as log_file:
        for n in range(1, steps + 1):
            shot = f"{task}-{n}.png" if attempt == 1 else f"{task}-a{attempt}-{n}.png"
            who = {"task": task, "attempt": attempt, "step": n}
            log_file.write(json.dumps({**who, **INTENT}) + "\n")
            (evidence / shot).write_bytes(b"\x89PNG fake")
            page = "help" if USABILITY["leave"] and n == steps else f"{task}/form?step={n}"
            log_file.write(json.dumps({**who, "phase": "result", "happened": "It moved on.",
                                       "url": f"{base}/{page}", "screenshot": shot}) + "\n")


def attempt_tasks(path, count):
    """write(), for a usability run: attempt and write up the next `count` tasks."""
    text = path.read_text()
    missing = [task for task in TASK_LIST.findall(text) if not re.search(rf"^### Task {task}\b", text, re.M)]
    n = factors(path)
    row = "| " + " | ".join(["7"] * n) + " |"
    for task in missing if count == "all" else [] if count == "final" else missing[:int(count)]:
        act(path, task, USABILITY["steps"])
        text += f"### Task {task}\n**Outcome:** {USABILITY['outcome']}, as it went.\n\n{row.replace('7', 'F')}\n" \
                f"|{'---|' * n}\n{row}\n\n"
    if count in ("all", "final"):
        text += "## Overall verdict\nIt was fine.\n\n## Out of character: researcher notes\nNotes.\n"
    path.write_text(text)


def write(path, count):
    """Append `count` concept sections ("all": every one missing, then the final sections).
    A job's output file is written whole instead, and a usability run attempts its tasks."""
    if path.parent.name == "analysis":
        path.write_text(f"# Findings\n\n- Written to {path.name} by the job itself.\n")
        return
    text = path.read_text()
    if "\n## Tasks\n" in text:
        return attempt_tasks(path, count)
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

    lent = file.parents[1] / "scratch" / run / "account.json"
    USABILITY.update(run=run, attempts={task: int(n) for task, n in AGAIN.findall(prompt)})
    log(event="start", cli=cli, run=run, attempt=attempt + 1, resumed=resumed, session=session, pid=os.getpid(),
        argv=sys.argv[1:], stdin=prompt, cwd=os.getcwd(), browser=browser(),
        account=json.loads(lent.read_text()) if lent.exists() else None)
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
        elif verb == "steps":
            USABILITY["steps"] = int(arg)
        elif verb == "act":
            act(file, next_task(file), int(arg))
        elif verb == "intent":
            task, (n, _, numbered) = next_task(file), arg.partition("@")
            with open(step_log(file), "a") as steps_file:
                steps_file.write(json.dumps({"task": task, "attempt": int(numbered or USABILITY["attempts"].get(task, 1)),
                                             "step": int(n), **INTENT}) + "\n")
        elif verb == "outcome":
            USABILITY["outcome"] = arg
        elif verb == "leave":
            USABILITY["leave"] = True
        elif verb == "scribble":
            with open(step_log(file), "a") as steps_file:
                steps_file.write("not an entry\n" + json.dumps({"task": "T99", "attempt": 1, "step": 99, **INTENT})
                                 + "\n" + json.dumps({"task": TASK_LIST.findall(file.read_text())[0], "attempt": 1,
                                                      "step": 1, **INTENT})
                                 + "\n" + json.dumps({"task": next_task(file), "attempt": 999, "step": "one",
                                                      "phase": "note"}) + "\n")
        elif verb == "empty":
            step_log(file).write_text("")
        elif verb == "link":
            moved = file.parents[1] / "scratch" / run / "steps.jsonl"
            step_log(file).rename(moved)
            step_log(file).symlink_to(moved)
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
        elif verb == "deaf":
            signal.signal(signal.SIGTERM, lambda *_: log(event="term", run=run))
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
        elif verb == "fail":
            sys.stderr.write(arg + "\n")
            log(event="end", run=run, pid=os.getpid(), code=1)
            sys.exit(1)
        else:
            raise SystemExit(f"fake CLI: unknown step {step!r}")
    end("ok")
