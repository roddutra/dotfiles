"""The test account of one usability run: provisioned before the run's first attempt, lent to its
panellist, and torn down when the run reaches a final state. And the success checks of its tasks,
run when it reaches that state, before the account goes.

launch.py owns when each of these happens. This module runs the study's own commands and keeps
the record. It knows no harness. study.json "accounts" (panel_lib.py, "Usability studies"):

    provision   a command that makes the account for a run and prints it as one JSON object:
                {"identifiers": {...}, "secrets": {...}, "state": "<file>"}
    map         in place of a command, the same accounts written out: {run id: account}
    teardown    a command that removes a run's account, so that its password and its saved
                session stop working
    reset       a command that puts the product back as it was, between the runs of a study
                with "sequential": true
    signin      "session" (the default) or "panellist"

Every command is split with shell rules and run without a shell (panel_lib.command_argv), from
the study directory, in the launcher's environment, in a process session of its own with
nothing on its standard input, with the run id as its last argument. It has TIMEOUT seconds,
after which it is killed with what it started, and it succeeds by exiting with code 0.

What a command prints is the lead's alone. A script that fails often prints what it was working
with, a password included, so nothing a command wrote ever reaches a message, runs.json, a
record or an exception: a message gives the exit code, what kind of failure it was and a fixed
sentence. What the command wrote to standard output and standard error is kept, when it did
not do what it was run for, in <study>/accounts/<run id>.<command>.output (output_path()), mode
0600 in a folder of mode 0700, and the message names that file. It is never under panel/, never
archived and never scanned, and it goes when the same command next succeeds for the run. What
accounts.provision prints is the account, secrets and all: it goes to the record and nowhere
else, also when it cannot be read as an account.

One command at a time, and none unrecorded. A command runs in a session of its own, so it
outlives a launcher that is killed, and a second one started beside it could make an account
that nothing knows of, or write over the state of a new run. So command() keeps a record of the
one command now running, <study>/accounts/command.running, lead only:

    command, run, task   which command (provision, teardown, reset or check), for which run,
                         and for a check which task
    times                for a provision, which provisioning of the run it is
    began                epoch seconds when the record was written, before the process existed
    pid, identity        the command's process and its start identity (run_watchdog.identity(),
                         the notion the watchdogs and launch.py go by), null until it exists

The process is started held back: it becomes the command only once its pid is on record, and
ends without running anything when whoever started it has gone (GATE). So a record without a
pid is of a command that never ran. The record goes when the command has ended and been waited
for. recover() is what every launcher command, and init_study.py --force, does before anything
else: a command still on record is ended with its process group when its process is still the
one recorded (SIGTERM, the grace, SIGKILL: end_group()), and waited for. Either way it is taken
as unfinished: a provision is cleared up by "teardown" before the run is provisioned again, a
teardown is run again (below), and a reset or a check runs again when it is next due. Commands
are run one after another by the one launcher a study has, so no two ever overlap.

A command can leave a process of its own behind: one that ignored SIGTERM while the command
itself ended on it, or that was still at work when the command was killed from outside. A group
is signalled only while the process on record is there to prove whose it is, so such a process
is never killed here, and no command is started beside it either. While the group of a command
on record has a process in it that has not ended, recover() exits: it names each one and how to
look at it (ps -o pid,pgid,command), the record stays as it was, and nothing of the study is
run, torn down or provisioned. Stop what is the command's and run the launcher again: once the
group is empty the record goes and the launcher carries on as above. When what is left is not
the command's at all, another's group that was given the id since, delete the record.

An account has three parts:

    identifiers   made-up values that may be seen, in evidence too: username, email, display name
    secrets       values that must never be seen: password, token, one-time code
    state         a saved browser state (agent-browser "state save": cookies and local storage),
                  relative to the study directory. It holds the session cookie in plain text, so
                  it is refused under panel/. With it a run starts signed in

Where each part goes:

    <study>/accounts/<run id>.json   the record (below), with every part. Lead only: the folder
                                     is mode 0700 and the file 0600, and nothing under panel/
                                     ever names it
    panel/scratch/<run id>/account.json   what the panellist is told (lent()): "signed_in",
                                     "identifiers" and "note", a sentence that says how it
                                     starts. "secrets" only with "signin": "panellist"
    logs/<run id>.<attempt>.state    a private copy of the state for one attempt's browser
                                     session, which deletes it once it has loaded it
                                     (browser_session.py --delete-state). The original stays
                                     for the next attempt

Signed-in start is the default: the browser session of every attempt starts from the state, and
the panellist handles no secret. With "signin": "panellist" signing in is the task under test:
the state is not loaded, the secrets are in the panellist's account.json, and the run is marked
"secrets_given" for good, because any of its screenshots may show one. With neither a state nor
that setting the panellist starts signed out with nothing to sign in with, and is told so.

The record, one JSON object:

    run           the run id
    provisioning  epoch seconds when a provision command was started. A record with this and no
                  "identifiers" is of a provisioning that did not finish: the command failed, or
                  the launcher was killed while it ran. Whatever it made is not known, so the
                  next provisioning of the run runs "teardown" first, when the study has one,
                  and carries on whatever that says
    provisioned   epoch seconds when the account was ready
    times         how many times the run has been provisioned
    source        "provision" or "map"
    signin        accounts.signin when it was provisioned
    start         how the run starts with it: "signed_in" (a state, loaded by the browser
                  session), "secrets" (the panellist signs in) or "signed_out" (neither)
    identifiers, secrets, state   the account. "state" is the file's full path, or null
    secrets_given whether a panellist of this run was ever given a secret to type
    torn_down     epoch seconds when the run reached a final state and the account was let go,
                  null while it is in force (in_force())
    teardown      "ran" or "none", whether the study had a teardown command to run then
    teardown_error  how a teardown failed: the exit code and the file its output is in, never
                  the output. The account is then still in force and owed a teardown: the
                  next launcher command that settles the run tries again, and no attempt of
                  the run starts with it (owed())
    cleanup       there only while a teardown is under way: {"began", "remove", "rewrite"},
                  the files to delete and the files to write again without their secrets

Once an account is torn down its secrets are gone from the record and from the panellist's
account.json, and a state file that a provision command made is deleted: the identifiers stay,
because evidence refers to them. A run that is continued afterwards is provisioned again.

A teardown is done in an order that a kill at any point leaves finishable (teardown()): the
record gets "cleanup" first, then the command runs, then the files are seen to, and only then
is the record marked torn down and "cleanup" taken off, in one write. Until that write the
account is in force, so whatever next settles the run does the whole of it again, and each
step is safe to repeat: the study's teardown must succeed for an account that is not there.
A record with "cleanup" is finished by the next launcher command whatever state its run is in
(launch.py), and by init_study.py --force.

Success checks. A task's "success_check" is a command of the same kind, run the same way with
the run id as its last argument (check()). It is the lead's, and nothing of it reaches panel/.
Its exit code is its verdict, and only two codes are one:

    0             the task was really completed
    1             it was not
    anything else the check failed to run: no verdict. So does a check that cannot be executed,
                  one that does not end within TIMEOUT seconds, and one ended by a signal

A check that failed to run is never counted as "not completed". Write a check so that it exits
with 2 or more when it cannot tell: the product is down, the account is not there. A Python
script that raises exits with 1, which reads as "not completed", so catch what can go wrong and
exit with 2. A check finds its run's account by the run id: the identifiers are in
<study>/accounts/<run id>.json, which is still whole when the check runs. Its record, one for
each task of a run, kept in the run's entry of runs.json under "checks" (panel_lib.py):

    checked       true (completed), false (not completed) or null (no verdict)
    exit_code     the check's exit code, minus the signal's number when one ended it, null when
                  it was never executed or was killed at the timeout
    at            epoch seconds when it was run
    error         why there is no verdict, in words, else null: never what the check printed,
                  which is in the file the words name
    kept          there, and true, only on a record made with an account the run no longer has:
                  the run was continued with a new one, and does not attempt the task again

A check can be run again only while the account it judged is there. Once a teardown command has
removed the account (gone()), or the run has a new one, a verdict on record is kept: a check run
then judges the run without what the run did. "launch.py check --force" runs it all the same.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import panel_lib as pl
import run_watchdog as watchdog

FOLDER = "accounts"   # the records, relative to the study directory
IN_FLIGHT = "command.running"  # in that folder: the record of the one command now running (module docstring)
TIMEOUT = 120         # seconds a provision, teardown or reset command gets
GIVE_UP = 5.0         # seconds a process group gets to disappear after SIGKILL
REFUSED = b"\0refused\0"  # what GATE writes before the system's message when the command could not be executed
# What every command is started through: a process that waits to be told it is on record, then
# becomes the command, with nothing on its standard input. Told nothing, because whoever started
# it was killed first, it ends without running the command.
GATE = """import os, sys
try:
    if os.read(0, 1):
        os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
        os.execv(sys.argv[1], sys.argv[1:])
except OSError as err:
    os.write(2, %r + (err.strerror or str(err)).encode())
    os._exit(126)
""" % REFUSED
FINAL = ("done", "limited", "failed")  # the states in which a run has no further use for its account
VERDICTS = {0: True, 1: False}         # what a success check's exit code says of its task: any other is no verdict
NOTES = {  # what a panellist's account.json says of how it starts
    "signed_in": "The browser is already signed in to this test account. Its name may differ from your "
                 "persona's: the account is lent to you for the test, so carry on as yourself, and do not "
                 "report the difference as a finding about the product.",
    "secrets": "The browser is not signed in. Sign in with these details when a task needs it, and enter them "
               "nowhere else. The account's name may differ from your persona's: it is lent to you for the test, so "
               "do not report the difference as a finding about the product.",
    "signed_out": "The browser is not signed in, and you have no password. If a page asks you to sign in, that "
                  "is as far as you can go: say so in your step log and your task section.",
}


class Failed(Exception):
    """A command of the study failed, or what it printed cannot be used: the reason, as a sentence
    without its full stop."""


def record_path(study_dir: Path, run: str) -> Path:
    return Path(study_dir) / FOLDER / f"{run}.json"


def lent_path(study_dir: Path, run: str) -> Path:
    return Path(study_dir) / "panel" / "scratch" / run / "account.json"


def read(study_dir: Path, run: str) -> dict | None:
    """A run's record, None when it has none."""
    try:
        record = json.loads(record_path(study_dir, run).read_text())
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def write_private(path: Path, text: str):
    """Replace a file in one step, readable by this user alone from the moment it exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def save(study_dir: Path, record: dict):
    """Write a run's record. Its secrets are remembered by their fingerprints first
    (pl.remember_secrets), so that a scan still knows them once teardown has taken them off the
    record. A map's accounts need nothing here: a scan reads them from study.json."""
    pl.remember_secrets(study_dir, record["run"], record.get("secrets"))
    path = record_path(study_dir, record["run"])
    path.parent.mkdir(mode=0o700, exist_ok=True)
    write_private(path, json.dumps(record, indent=2) + "\n")


def in_force(record: dict | None) -> bool:
    """Whether a record is of an account that was provisioned and not torn down since."""
    return bool(record) and record.get("provisioned") is not None and not record.get("torn_down")


def gone(record: dict | None) -> bool:
    """Whether a record is of an account that a teardown command has removed: a success check
    can then no longer see what its run did. An account let go in a study with no teardown
    command is still in the product."""
    return bool(record) and bool(record.get("torn_down")) and record.get("teardown") == "ran"


def records(study_dir: Path) -> list[dict]:
    """Every record of the study, in run id order: the files of the records folder that name
    themselves as a run's record. Anything else a lead keeps in a folder of that name is not one."""
    found = ((f.stem, read(study_dir, f.stem)) for f in sorted((Path(study_dir) / FOLDER).glob("*.json")))
    return [r for stem, r in found if r and r.get("run") == stem]


def owed(record: dict | None) -> bool:
    """Whether a record is of an account in force that is to go and has not gone: a teardown of
    it failed, or was cut short. No attempt of its run starts with such an account, which the
    product may no longer have: it is torn down first, and the run provisioned again."""
    return in_force(record) and bool(record.get("teardown_error") or record.get("cleanup"))


def output_path(study_dir: Path, run: str, name: str) -> Path:
    """Where what a command wrote is kept when it did not do what it was run for: lead only."""
    return Path(study_dir) / FOLDER / f"{run}.{name}.output"


def kept(cfg: dict, run: str, name: str, out: str, err: str) -> str:
    """Keep what a command wrote for the lead alone (module docstring), and say where, as a
    sentence to end a message with. The message never has a word of it."""
    path = output_path(cfg["_dir"], run, name)
    if not (out.strip() or err.strip()):
        path.unlink(missing_ok=True)
        return ". It wrote nothing"
    try:
        path.parent.mkdir(mode=0o700, exist_ok=True)
        write_private(path, f"standard output:\n{out}\nstandard error:\n{err}")
    except OSError as failed:
        return f". What it wrote could not be kept for you ({failed.strerror or 'the file cannot be written'})"
    return f". What it wrote is in {path.relative_to(cfg['_dir'])}, which is yours alone to read: it may hold a secret"


def flight_path(study_dir: Path) -> Path:
    return Path(study_dir) / FOLDER / IN_FLIGHT


def command(cfg: dict, text: str, run: str, name: str, what: str, **noted) -> tuple[int, str, str]:
    """Run one of the study's commands for a run, as the module docstring says every one is run:
    (its exit code, what it wrote to standard output, what it wrote to standard error), which
    the caller keeps to itself (kept()). name is the command's, "provision", "teardown", "reset"
    or "check-<task id>", what names it in a message, and noted is what else its record says.
    The command is on record in command.running from before its process exists until it has
    ended and been waited for. Raises Failed when it cannot be run or does not end within
    TIMEOUT seconds."""
    sd = cfg["_dir"]
    try:
        argv = [*pl.command_argv(cfg, text), run]
    except ValueError as err:
        raise Failed(f"{what} {err}")
    shown = shlex.join([*(pl.command_words(text) or []), run])
    note = {"command": name.partition("-")[0], "run": run, **noted, "began": round(time.time(), 3), "pid": None,
            "identity": None}
    proc = None
    try:
        try:
            (sd / FOLDER).mkdir(mode=0o700, exist_ok=True)
            write_private(flight_path(sd), json.dumps(note) + "\n")  # the intent, before the process exists
            proc = subprocess.Popen([sys.executable, "-I", "-c", GATE, *argv], cwd=sd, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            note.update(pid=proc.pid, identity=watchdog.identity(proc.pid))
            write_private(flight_path(sd), json.dumps(note) + "\n")  # on record: only now is it told to go on
        except OSError as err:  # not run: a process that was started ends below without becoming the command
            raise Failed(f"{what} could not be run ({shown}): {err.strerror or err}")
        try:
            out, err = proc.communicate(b"\n", timeout=TIMEOUT)
            late = False
        except subprocess.TimeoutExpired:
            watchdog.signal_group(proc.pid, signal.SIGKILL)  # not reaped yet, so the group's id is still its own
            out, err = proc.communicate()
            late = True
    except BaseException:
        if proc and proc.poll() is None:  # never leave a command running that is about to go off the record
            watchdog.signal_group(proc.pid, signal.SIGKILL)
            proc.wait()
        raise
    finally:
        flight_path(sd).unlink(missing_ok=True)
    if proc.returncode == 126 and err.startswith(REFUSED):
        raise Failed(f"{what} could not be run ({shown}): {err[len(REFUSED):].decode(errors='replace')}")
    out, err = out.decode(errors="replace"), err.decode(errors="replace")
    if late:
        raise Failed(f"{what} did not end within {TIMEOUT} s and was killed ({shown})" + kept(cfg, run, name, out, err))
    return proc.returncode, out, err


def end_group(pid: int, started: str | None, grace: float) -> tuple[bool, list[int]]:
    """End the process group of a command that an earlier launcher left running: SIGTERM, the
    grace, then SIGKILL, and wait for it to have gone. Returns (whether the command was still
    running, the processes still in its group that nothing proves gone). The second is empty
    only when the group is: recover() starts no command while it is not.

    The care is the one launch.py takes of a CLI (kill_group()): the group is the command's
    for certain only while its leader, the process on record, still holds the recorded id under
    the recorded start identity, and only then is it signalled. A leader that ends on SIGTERM
    and is reaped takes that proof with it: what is still in a group of its id, having ignored
    the signal, gets what is left of the grace to go by itself, and is then returned for the
    lead to look at, and not killed. So is what a leader that had gone before this looked left
    in such a group. A process that holds the id under another start identity was given it
    after the command's group had emptied, as an id is given out again only then: nothing of
    the command is left."""
    def leader() -> str | None:  # its state, while it is still the process on record
        found = watchdog.process(pid)
        return found[0] if found and started and found[1] == started else None

    def others() -> list[int]:
        try:
            return watchdog.others(pid)
        except (OSError, subprocess.SubprocessError):
            return []  # no list of processes to be had: nothing to name

    def left() -> list[int]:  # what is in the group still that may be at work: a process that has ended is not
        found = watchdog.process(pid)
        if found and started and found[1] != started:
            return []
        return sorted(x for x in [*([pid] if found else []), *others()]
                      if not (watchdog.process(x) or "Z")[0].startswith("Z"))

    state = leader()
    if not state:
        return False, left()
    running = not state.startswith("Z")
    watchdog.signal_group(pid, signal.SIGTERM)
    give_up = time.time() + grace
    while (leader() or "Z")[0] != "Z" and time.time() < give_up:
        time.sleep(0.02)
    if leader():  # running still, or ended and not reaped: either way the id is its own, and so is the group
        watchdog.signal_group(pid, signal.SIGKILL)
        give_up = time.time() + GIVE_UP
        while ((leader() or "Z")[0] != "Z" or (leader() and others())) and time.time() < give_up:
            time.sleep(0.02)
    while left() and time.time() < give_up:  # no longer signalled: only watched, for what is left of that time
        time.sleep(0.02)
    return running, left()


def recover(cfg: dict, grace: float) -> list[str]:
    """See to a command that an earlier launcher left on record (module docstring), before
    anything else is done with the study: end it when it is still running, wait for it, and
    take its record off. Returns what the lead should be told, each a sentence. Exits when the
    record cannot be read, when it names a process that nothing can tell from the command, or
    when the command's process group still holds a process that nothing proves gone
    (end_group()): the record is then left as it was, and no command is started beside one
    that may still be running. Whoever calls this starts nothing of the study before it."""
    sd, path = cfg["_dir"], flight_path(cfg["_dir"])
    look = (f"Look for a command of this study that is still running (ps -o pid,pgid,command), stop it, then delete "
            f"{path}.")
    try:
        with os.fdopen(watchdog.opened(path)) as f:
            note = json.loads(f.read())
        if not isinstance(note, dict):
            raise ValueError
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as err:
        why = pl.unread(err) if isinstance(err, OSError) else "it holds no JSON object"
        raise SystemExit(f"{path} is the record of a command of this study that an earlier launcher started, and it "
                         f"cannot be read ({why}), so nothing was done. {look}")
    name, run, pid = str(note.get("command")), str(note.get("run")), note.get("pid")
    what = (f"the success check of task {note.get('task')}" if name == "check" else f"accounts.{name}") + f" for {run}"
    again = {"provision": f"Whatever account it made is not known, so accounts.teardown runs for {run} before it is "
                          "provisioned again.",
             "teardown": "The teardown is done again from the start.",
             "reset": "It runs again before the next run that needs it.",
             "check": "No verdict is on record from it, so it runs again."}.get(name, "")
    said = [f"An earlier launcher was killed as it started {what}: the command never ran."]
    if isinstance(pid, int) and not isinstance(pid, bool):
        if not note.get("identity") and watchdog.process(pid):
            raise SystemExit(f"An earlier launcher was killed while {what} ran, and nothing on record tells its "
                             f"process (pid {pid}) from another that was given the same id since, so nothing was "
                             f"done. {look}")
        running, left = end_group(pid, note.get("identity"), grace)
        how = ("It has ended since" if not running else f"It was still running (pid {pid}) and was stopped"
               if pid not in left else f"It was still running (pid {pid}) and did not end when it was killed")
        if left:  # the record stays: the next launcher command looks again, and goes on once the group is empty
            pids = ", ".join(map(str, left))
            raise SystemExit(
                f"An earlier launcher was killed while {what} ran. {how}, but process group {pid} still holds pid "
                f"{pids}, which may be left of that command and still at work. The launcher signals a group only "
                f"while the command itself is there to prove whose it is, so "
                f"{pl.agree(len(left), 'that process is', 'those processes are')} yours to look at. The record is "
                f"kept and no command of the study was started beside {pl.agree(len(left), 'it', 'them')}: nothing "
                f"was run, torn down or provisioned. Check with ps -o pid,pgid,command -p {pids.replace(' ', '')} "
                f"and stop what is the command's, then run this again: once the group is empty it carries on. If "
                f"nothing there is the command's, delete {path} instead.")
        said = [f"An earlier launcher was killed while {what} ran. {how}." + (f" {again}" if again else "")]
    path.unlink(missing_ok=True)
    return said


def ended(code: int) -> str:
    return f"was ended by signal {-code}" if code < 0 else f"exited with code {code}"


def call(cfg: dict, name: str, run: str, **noted) -> str:
    """Run the accounts command `name` for a run, and return what it printed, which is for the
    caller alone. Raises Failed, which has none of it: what a command that failed wrote is kept
    for the lead (kept())."""
    text = cfg["accounts"][name]
    code, out, err = command(cfg, text, run, name, f"accounts.{name}", **noted)
    if code != 0:
        raise Failed(f"accounts.{name} {ended(code)} ({shlex.join([*pl.command_words(text), run])})"
                     + kept(cfg, run, name, out, err))
    output_path(cfg["_dir"], run, name).unlink(missing_ok=True)  # of an earlier try that failed
    return out


def check(cfg: dict, task: dict, run: str) -> dict:
    """Run a task's "success_check" for a run and return its record (module docstring, "Success
    checks"): {"checked", "exit_code", "at", "error"}. Never raises: a check that cannot be run,
    does not end in time, or exits with a code that is no verdict has "checked" None and says
    why in "error", which names the file what it wrote is in and has none of it."""
    what, at, name = f"the success check of task {task['id']}", round(time.time()), f"check-{task['id']}"
    try:
        code, out, err = command(cfg, task["success_check"], run, name, what, task=task["id"])
    except Failed as failed:
        return {"checked": None, "exit_code": None, "at": at, "error": str(failed)}
    if code in VERDICTS:
        output_path(cfg["_dir"], run, name).unlink(missing_ok=True)
        return {"checked": VERDICTS[code], "exit_code": code, "at": at, "error": None}
    return {"checked": None, "exit_code": code, "at": at,
            "error": f"{what} {ended(code)}, which is no verdict (0 says completed, 1 says not completed)"
                     + kept(cfg, run, name, out, err)}


def lent(record: dict) -> dict:
    """What a panellist is told of its account: the content of its account.json. The secrets are
    in it only while the account is in force and signing in is the panellist's to do."""
    kind = record["start"]
    told = {"signed_in": kind == "signed_in", "identifiers": record["identifiers"]}
    if kind == "secrets" and in_force(record):
        told["secrets"] = record.get("secrets") or {}
    return {**told, "note": NOTES[kind]}


def lend(cfg: dict, record: dict):
    """Write the panellist's account.json from a record."""
    path = lent_path(cfg["_dir"], record["run"])
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.write_atomic(path, json.dumps(lent(record), indent=2) + "\n")


def provision(cfg: dict, run: str) -> tuple[dict, list[str]]:
    """Give a run its account: run accounts.provision, or take the run's entry of accounts.map,
    write the record and the panellist's account.json. Returns the record, and what the lead
    should be told. Raises Failed, with the reason, when there is no usable account: the record
    then says a provisioning did not finish (module docstring)."""
    sd, acc, notes = cfg["_dir"], cfg["accounts"], []
    earlier = read(sd, run) or {}
    times, given = earlier.get("times") or 0, bool(earlier.get("secrets_given"))
    if "map" in acc:
        account, source = acc["map"][run], "map"
    else:
        source = "provision"
        if earlier.get("provisioning") and earlier.get("provisioned") is None:
            notes.append("an earlier provisioning of its test account did not finish"
                         + unfinished(cfg, run, bool(acc.get("teardown"))))
        save(sd, {"run": run, "provisioning": round(time.time()), "times": times, "secrets_given": given})
        printed = call(cfg, "provision", run, times=times + 1)
        try:
            account = json.loads(printed)
        except ValueError:  # whatever it is, it may hold the account's secrets: none of it is repeated
            raise Failed("accounts.provision exited with code 0, but what it printed was not the one JSON object "
                         "expected" + kept(cfg, run, "provision", printed, ""))
        held = account.get("secrets") if isinstance(account, dict) else None
        if isinstance(held, dict) and all(isinstance(v, (str, int, float)) for v in held.values()):
            pl.remember_secrets(sd, run, held)  # known to a scan even if the account turns out unusable
    problem = pl.account_problem(account, acc["signin"])
    # A map's state is named in study.json, the lead's own. A command's is part of what it printed.
    wrong = None if problem else pl.state_problem(cfg, account.get("state"), named=source == "map")
    if wrong:
        problem = f"names a saved browser state that {wrong}"
    if problem:
        raise Failed(f"the account {'accounts.map has' if source == 'map' else 'accounts.provision printed'} for "
                     f"{run} cannot be used: it {problem}"
                     + ("" if source == "map" else kept(cfg, run, "provision", printed, "")))
    signin, state = acc["signin"], str(pl.state_file(cfg, account["state"])) if account.get("state") else None
    record = {"run": run, "provisioned": round(time.time()), "times": times + 1, "source": source, "signin": signin,
              "start": "secrets" if signin == "panellist" else "signed_in" if state else "signed_out",
              "identifiers": account["identifiers"], "secrets": account.get("secrets") or {}, "state": state,
              "secrets_given": given or signin == "panellist", "torn_down": None, "teardown": None,
              "teardown_error": None}
    save(sd, record)
    lend(cfg, record)
    return record, notes


def unfinished(cfg: dict, run: str, has_teardown: bool) -> str:
    """Clear up after a provisioning that did not finish, and say what was done, as the end of a
    sentence. Whatever teardown says, the provisioning that follows goes ahead: an account that
    was never made cannot be removed."""
    if not has_teardown:
        return ", and the study has no accounts.teardown to clear up after it"
    try:
        call(cfg, "teardown", run)
    except Failed as err:
        return f", and clearing up after it did not work: {err}"
    return ", so accounts.teardown was run for it first"


def teardown(cfg: dict, run: str) -> dict | None:
    """Let go of a run's account: run accounts.teardown when the study has one, then take the
    secrets out of the record and of the panellist's account.json, and delete a state file that
    a provision command made. Returns the record as it then is, None when the run has no account
    in force. A teardown that failed leaves the account in force, with "teardown_error".

    In the order the module docstring gives, so that one cut short at any point is done again
    from the start by whatever next calls this: the record says "cleanup" before the command
    runs, the files are seen to after it, and the record is marked torn down last, in the write
    that takes "cleanup" off. Until then it is in force, secrets and all."""
    sd, record = cfg["_dir"], read(cfg["_dir"], run)
    if not in_force(record):
        return None
    command = (cfg.get("accounts") or {}).get("teardown")
    made = record.get("state") if record.get("source") == "provision" else None
    record["cleanup"] = {"began": round(time.time()), "remove": [made] if made else [],
                         "rewrite": [str(lent_path(sd, run))]}
    save(sd, record)
    if command:
        try:
            call(cfg, "teardown", run)
        except Failed as err:  # a known end: the account stays, and nothing of it is half cleared
            del record["cleanup"]
            record["teardown_error"] = str(err)
            save(sd, record)
            return record
    after = {**record, "torn_down": round(time.time()), "teardown": "ran" if command else "none",
             "teardown_error": None, "secrets": {}, "state": None if made else record.get("state")}
    for path in record["cleanup"]["remove"]:
        Path(path).unlink(missing_ok=True)
    if lent_path(sd, run).exists():
        lend(cfg, after)  # written anew from the record: no secret, as the account is no longer in force
    del after["cleanup"]
    save(sd, after)
    return after


def reset(cfg: dict, run: str):
    """Run accounts.reset before a run of a sequential study. Raises Failed."""
    call(cfg, "reset", run)


def session_state(cfg: dict, record: dict | None, copy: Path) -> Path | None:
    """A private copy of the account's saved browser state for one attempt's browser session,
    at copy, or None when the session starts signed out: the run has no account, the account
    names no state, or signing in is the panellist's to do. Raises Failed when the state is
    gone."""
    if not in_force(record) or record["start"] != "signed_in":
        return None
    try:
        with open(record["state"], "rb") as source:
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.unlink(missing_ok=True)  # made anew: a link left at its name is not written through
            with os.fdopen(os.open(copy, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as dest:
                shutil.copyfileobj(source, dest)
    except OSError as err:  # the file's name is the account's, from what the provision command printed
        raise Failed("the saved browser state of its test account could not be copied "
                     f'({err.strerror or "it cannot be written"}): the file is the "state" of '
                     f"{record_path(cfg['_dir'], record['run']).relative_to(cfg['_dir'])}")
    return copy


def known(cfg: dict) -> dict:
    """What a scan of the study knows its secrets by (panel_lib.known_secrets()), the secrets of
    the accounts still in force among them."""
    return pl.known_secrets(cfg, [r for r in records(cfg["_dir"]) if in_force(r)])


def summary(record: dict) -> dict:
    """What a run's entry in runs.json says of its account (panel_lib.py, "account"): no
    identifier and no secret."""
    return {"provisioned": record.get("provisioned"), "times": record.get("times"), "source": record.get("source"),
            "signin": record.get("signin"), "signed_in": record.get("start") == "signed_in",
            "secrets_given": bool(record.get("secrets_given")),
            "torn_down": record.get("torn_down"), "teardown_error": record.get("teardown_error")}
