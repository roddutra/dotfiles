#!/usr/bin/env python3
"""The browser session of one attempt of a run: an agent-browser session that is started before
the run's process exists and stopped after it has ended, so that the run only sends it commands.

launch.py has each attempt's watchdog (run_watchdog.py) run "start" before the harness CLI and
"stop" after it, whichever way the attempt ends, and stops a session itself when a watchdog did
not live to. Nothing here knows a harness: every runner drives the same session, through three
environment variables. Standard library only. Of the skill it imports run_watchdog.py alone, for
the one definition of a process's identity and of how a file in logs/ is opened.

    browser_session.py start --log <base> --session <name> --socket-dir <dir>
                             [--cwd <dir>] [--viewport <width>x<height>]
                             [--state <file> [--delete-state]]
    browser_session.py stop --log <base>

    --log          the attempt's log base, logs/<run id>.<attempt>. The session's record is
                   <base>.browser and its action policy <base>.policy: both names come from the
                   attempt, for "start" and for "stop" alike, and from nowhere else. The policy is
                   then outside anything the run can write, and outside what its file tools read
    --session      the session's name: the run id
    --socket-dir   a directory to make for the session's sockets alone, mode 0700: pp-<8 hex
                   digits>, directly in the system's temporary directory. Short, because a
                   socket path has about 100 bytes
    --cwd          the working directory of the session: the run's own, because the session, not
                   the run, resolves a relative screenshot path. Default: the current one
    --viewport     default 1440x900. Left alone, agent-browser opens a window of 1280x577
    --state        a saved browser state (cookies and local storage, from "agent-browser state
                   save") to start from, so that a run begins signed in. It holds the cookie in
                   plain text: keep it where no run can read it
    --delete-state delete that file once the session has loaded it, and also when the session
                   could not be started: it is a copy made for this session alone, and the
                   session stays signed in without it

plan() gives a caller the names to pass, and changes() what the run's process needs in its
environment. "start" prints the three variables as one JSON object.

What "start" does, in order. Each thing is on the record before it exists or as soon as it does,
so a "start" that is killed at any point leaves nothing that "stop" cannot find:

1. Writes the record: the session's name, its socket directory and a random token.
2. Makes the socket directory, puts the token in it (the file MARKER), and writes a policy that
   allows everything: its own commands need what no run is allowed.
3. Notes on the record that a session is being launched, and starts it from the working
   directory, with the state file when there is one, on a blank page.
4. Records the session's daemon and its browser process, each with its start identity, and the
   browser's profile directory. The daemon is the process that listens on the session's socket,
   by the system's word (peer()). Deletes the state file when asked to, and sets the viewport.
5. Replaces the policy, at the same path, with the strict one. agent-browser reads the file again
   for every command, so it holds from the next one on, with no restart.
6. Checks that the session still answers, and that it now refuses a command the policy leaves
   out. A policy that is not in force would allow everything without a word.

When any step fails the session is stopped again, "start" says why on standard error and exits
with code 1.

The environment. A session is found by AGENT_BROWSER_SOCKET_DIR and AGENT_BROWSER_SESSION, and
AGENT_BROWSER_ACTION_POLICY names its policy. agent-browser restarts a session, on a blank page
and signed out, when a command reaches it with other settings than it was started with. So the
run's process must have exactly these three, and no other AGENT_BROWSER_* variable but the ones in
KEEP, which only say how a browser is started on this machine: changes() says which to set and
which to remove, and "start" calls agent-browser with the same. The useful side: a run that
drops or changes the policy loses its session, and gains nothing.

The action policy. ALLOW is the whole list, and this file the one place it is kept. It holds
what a visitor does with a page: open an address, go back, forward and reload, list the elements
(snapshot), click, type, select, tick, press a key, hover, scroll, wait, answer a dialog, take a
screenshot, and read the address and the title. COMMANDS are the agent-browser commands that
reach those actions, for a runner that can allow commands one by one. Everything else is
refused by the session itself, whatever the harness allows: running JavaScript in the page
(eval, wait --fn), reading the page source, an element's text, value or attributes, cookies,
local and session storage, saving or loading a browser state, network requests, the console,
the debugging address, new tabs, the clipboard, PDFs, recordings, changing the viewport, closing
the session, and every option that would start the browser again with other settings (--state,
--profile, --cdp, --headed, --args, --proxy and the like). REFUSES says so for the plan.

What the policy does not cover: where "open" goes (any address, and any file:// path the user
can read), where a screenshot is saved, what the snapshot shows (the accessibility tree: text
for screen readers and elements off screen are in it), commands that never reach a session
(session list, profiles and others), and a second session a run starts in the same socket
directory, which gets the same policy and is stopped with the first.

What "stop" does. It never runs agent-browser. Every way that CLI has of closing a session can
end in a signal to whatever process holds the id in a pid file: "close --all" kills it when the
socket does not answer, and "close" for one session, like every command, restarts a session
whose settings differ from its own, by a signal to that id when the session does not go by
itself (agent-browser 0.38.1, cli/src/main.rs run_close_all() and cli/src/connection.rs
kill_stale_daemon()). A pid file is a file, and an id in it can be another process's by now. So:

1. It finds the sessions by their sockets: every socket in the socket directory that something
   listens on, the session of the record and any other a run started there. The system names the
   listening process (peer()), which is then held to its start identity like a recorded one.
2. It allows everything again and asks each of them to close, through its socket and nothing
   else: one request, with no signal behind it.
3. It makes sure of the processes it knows: the recorded daemon and browser, each listening
   daemon, and the browser each daemon started. Each only while a process still holds the id
   under the start identity it was noted with: a daemon that did not say it would close gets
   SIGTERM, which is a clean close too, and what is left after GRACE seconds is killed, a
   browser with its process group while it still leads that group.
4. It removes what the session left, by the rule below, notes "stopped" and what it found on the
   record, and says so in one line. It exits with code 0, with 1 when a process could not be
   ended or something was left in place, and with 2 when it refused the record.

A session that still answers and whose process the system would not name is left alone, with
its socket directory and the strict policy back in place, and named in "kept". "stop" is safe
to run twice, and waits for a "start" that is still at work on the same record.

What "stop" removes, and on what proof. The record is read as any file a stranger could have
written: nothing is deleted because the record says so.
- The record itself is opened without following a symbolic link and without waiting for anyone,
  as an open of a FIFO would. Before a byte of it is read it must be, by its open descriptor, a
  regular file of this user of no more than RECORD bytes (run_watchdog.py opened()), and then
  hold what "start" writes: every field of the right shape, and the policy named as the
  attempt's. Otherwise "stop" refuses it (Refused), touches nothing and says why. Every reader
  opens it that way, so a look at it (read(), state(), for "status" and for a launcher that
  settles the attempt) never waits either: it takes such a record for one that cannot be read,
  and "stop" then refuses it.
- The policy is <base>.policy, from --log. The path on the record is never used. It is written
  to a file beside it that is made anew (run_watchdog.py fresh()), and put in place in one step:
  a symbolic link at either name is replaced, never written through.
- The socket directory is removed only when it is a real directory of this user alone (mode
  0700), directly in the temporary directory, named as plan() names one, and holds the record's
  token in MARKER, read as the record is: only what could write inside the directory could have
  put it there. An empty one that passes the rest is removed too, since "start" may have been killed before it wrote
  the token, and nothing can be lost with it. It is opened once, without following a link, and
  emptied through that handle: each entry is unlinked, which never follows a link, and a
  directory inside it is no session's making, so it stays and so does the socket directory.
- A browser's profile directory is removed only when a browser process that "stop" identified,
  and has seen end, named it as its --user-data-dir while it was alive, and it is a real
  directory of this user, named as agent-browser names a temporary profile, directly in the
  temporary directory. A session that closes takes its profile with it, so this is for the
  browser of a daemon that was killed. shutil.rmtree removes it, which unlinks a symbolic link
  and never descends through one. The profile on the record is only ever named, in "kept".
- Whatever fails its proof stays where it is and is named in "kept", with the reason.

What is left: a browser whose daemon was killed and that neither the record nor a living daemon
leads to; a session whose socket appears more than SETTLE seconds after the "start" that
launched it was killed; and a process that ends, and whose id is given to another, between the
look at its identity and the signal.

The record is one JSON object: "session", "socket_dir", "policy", "token", "cwd", "started",
"launching" (true from just before the session is launched until its daemon is on record),
"daemon" and "browser" (each [pid, start identity] or null), "profile", and after "stop":
"stopped" (epoch seconds), "found" (whether a process of the session was still running), "left"
(the pids that could not be ended) and "kept" (what was left in place, each as "<path>: <why>").

A session holds about MEMORY_MIB MiB (16 processes, measured as proportional memory on Linux
with agent-browser 0.38.1), and a daemon that is killed outright leaves its browser running:
hence "stop" by a launcher for the session of a watchdog that was killed (launch.py).
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import secrets
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_watchdog as watchdog  # noqa: E402

CLI = "agent-browser"
PREFIX = "AGENT_BROWSER_"
SOCKET_DIR, SESSION, POLICY = PREFIX + "SOCKET_DIR", PREFIX + "SESSION", PREFIX + "ACTION_POLICY"
KEEP = (PREFIX + "EXECUTABLE_PATH", PREFIX + "ARGS")  # how a browser starts on this machine: the user's to say
SOCKETS = re.compile(r"pp-[0-9a-f]{8}")                    # what plan() names a socket directory
PROFILES = re.compile(r"agent-browser-chrome-[0-9A-Za-z-]+")  # agent-browser's name for a browser's temporary profile
MARKER = ".pp-session"  # the file in a socket directory that holds its session's token
TOKEN = re.compile(r"[0-9a-f]{32}")
SOCKET_PATH = 100    # bytes a socket's path may have, with room to spare on Linux (108) and macOS (104)
VIEWPORT = (1440, 900)
MEMORY_MIB = 330     # approximate: what one session holds
LAUNCH, COMMAND = 60, 20  # seconds an agent-browser command of "start" gets: the first, any other
ASK = 5.0            # seconds a session gets to answer a request to close
GRACE = 5.0          # seconds a session gets to go after it was asked to, before it is killed
SETTLE = 2.0         # seconds "stop" waits for the socket of a session whose "start" was cut short as it launched
START, STOP = 90, 45  # seconds a caller should give "start" and "stop" before it takes either for stuck
SCRIPT = [sys.executable, "-I", str(Path(__file__).resolve())]  # this script, with the caller's Python

# The actions a run may take, as agent-browser's policy names them.
ALLOW = ("navigate", "back", "forward", "reload", "snapshot", "screenshot", "click", "dblclick", "fill", "type",
         "press", "keyboard", "select", "check", "uncheck", "hover", "focus", "scroll", "scrollintoview", "wait",
         "waitforurl", "waitforloadstate", "dialog", "url", "title")
# The agent-browser commands that reach them. A command of two words is allowed with nothing after it.
COMMANDS = ("open", "back", "forward", "reload", "snapshot", "screenshot", "click", "dblclick", "fill", "type",
            "press", "keyboard", "select", "check", "uncheck", "hover", "focus", "scroll", "scrollintoview", "wait",
            "dialog", "get url", "get title")
STRICT, OPEN = {"default": "deny", "allow": list(ALLOW)}, {"default": "allow"}  # the policy of a run, and of "start"
DENIED = "denied by policy"  # in agent-browser's message for an action its policy leaves out
REFUSES = ("Each session refuses, whatever its harness allows: running JavaScript in the page, reading the page "
           "source, cookies, storage or a saved browser state, an element's text or value by selector, network "
           "requests and the console, opening tabs, closing the session, and starting the browser again with "
           "other options. It allows opening an address, going back, forward and reloading, the element list, "
           "clicking, typing, selecting, pressing keys, hovering, scrolling, waiting, screenshots, and reading "
           "the address and the title.")


class Failed(Exception):
    """A session could not be started, with the reason to give."""


class Refused(Exception):
    """A record that "stop" will not act on, with the reason: nothing of its session is touched."""


# ---------------------------------------------------------------- for a caller

def record_of(log) -> Path:
    """The record of the session of the attempt with this log base."""
    return Path(f"{log}.browser")


def policy_of(log) -> Path:
    return Path(f"{log}.policy")


def plan(log, session: str) -> dict:
    """The names of a session that "start" is yet to make, for the attempt with this log base:
    what to pass it, with a socket directory of a name of its own. Makes nothing."""
    return {"log": str(log), "session": session, "policy": str(policy_of(log)),
            "socket_dir": os.path.join(tempfile.gettempdir(), "pp-" + secrets.token_hex(4))}


def variables(session: dict) -> dict:
    """The three variables by which a process reaches a session, from its plan or its record."""
    return {SOCKET_DIR: session["socket_dir"], SESSION: session["session"], POLICY: session["policy"]}


def changes(session: dict, environ=None) -> dict:
    """What to change in an environment so that a process started with it reaches the session and
    no other: each variable to set, and with None each one to remove."""
    environ = os.environ if environ is None else environ
    return {**{name: None for name in environ if name.startswith(PREFIX) and name not in KEEP}, **variables(session)}


def start_command(session: dict, cwd, viewport=None, state=None, delete_state: bool = False) -> list[str]:
    w, h = viewport or VIEWPORT
    return [*SCRIPT, "start", "--log", session["log"], "--session", session["session"],
            "--socket-dir", session["socket_dir"], "--cwd", str(cwd), "--viewport", f"{int(w)}x{int(h)}",
            *(["--state", str(state)] if state else []), *(["--delete-state"] if state and delete_state else [])]


def stop_command(session: dict) -> list[str]:
    return [*SCRIPT, "stop", "--log", session["log"]]


def read(log) -> dict | None:
    """The record of an attempt's session as it reads now, without waiting for anyone and without
    following a symbolic link: None when there is none, {} when it is no JSON object. Raises
    OSError when it cannot be read, and for a record that "stop" would refuse as no regular
    file of this user (watchdog.Unsafe). For looking only: "stop" reads it under its lock."""
    try:
        fd = watchdog.opened(record_of(log))
    except FileNotFoundError:
        return None
    with os.fdopen(fd) as f:
        try:
            info = json.loads(f.read() or "{}")
        except ValueError:
            return {}
    return info if isinstance(info, dict) else {}


def state(log) -> str | None:
    """What is known of the session of an attempt, without waiting for anyone: None when there is
    no record, "starting" while "start" has not recorded a daemon, "up" while the recorded
    daemon is running, "down" when it has gone with no "stop" or the record cannot be read, and
    "stopped"."""
    try:
        info = read(log)
    except OSError:
        return "down"
    if info is None:
        return None
    if info.get("stopped"):
        return "stopped"
    return "up" if alive(info.get("daemon")) else "down" if info.get("daemon") else "starting"


def unstopped(log) -> bool:
    """Whether an attempt has a session on record that no "stop" has dealt with yet."""
    return state(log) not in (None, "stopped")


def remains(log) -> dict | None:
    """What a "stop" could not end or remove of an attempt's session, from its record: {"found",
    "left", "kept"}. None when there is no such record, or nothing was left."""
    try:
        info = read(log) or {}
    except OSError:
        return None
    rest = {"found": bool(info.get("found")), "left": [pid for pid in info.get("left") or [] if type(pid) is int],
            "kept": [str(what) for what in info.get("kept") or []]}
    return rest if info.get("stopped") and (rest["left"] or rest["kept"]) else None


# ---------------------------------------------------------------- processes

def pair_of(pair) -> list | None:
    """A process as a record holds it, [pid, start identity], or None when it is anything else.
    No id below 2: a signal to 0, 1 or a negative number reaches other processes than one."""
    ok = isinstance(pair, list) and len(pair) == 2 and type(pair[0]) is int and pair[0] > 1 \
        and isinstance(pair[1], str) and pair[1]
    return pair if ok else None


def alive(pair) -> bool:
    """Whether the process recorded as [pid, start identity] is still running, and still that one."""
    found = watchdog.process(pair[0]) if pair_of(pair) else None
    return bool(found) and not found[0].startswith("Z") and found[1] == pair[1]


def recorded(pid) -> list | None:
    identity = watchdog.identity(pid) if pid and pid > 1 else None
    return [pid, identity] if identity else None


def named(pid) -> str:
    """The command line of a process, "" when there is none."""
    try:
        r = subprocess.run(["ps", "-ww", "-o", "args=", "-p", str(pid)], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL)
    except OSError:
        return ""
    return r.stdout.strip()


def browsers(daemons=(), also=()) -> list[tuple[list, str]]:
    """The browser each of these daemons started, as ([pid, start identity], profile directory):
    the child whose command names a profile. And the same of each process in also, whoever its
    parent is: a browser on record, whose daemon may have gone."""
    try:
        r = subprocess.run(["ps", "-ww", "-A", "-o", "pid=", "-o", "ppid=", "-o", "args="], capture_output=True,
                           text=True, stdin=subprocess.DEVNULL)
    except OSError:
        return []
    out = []
    for line in r.stdout.splitlines():
        pid, _, rest = line.strip().partition(" ")
        ppid, _, args = rest.strip().partition(" ")
        profile = re.search(r"--user-data-dir=(\S+)", args)
        if pid.isdigit() and ppid.isdigit() and profile and (int(ppid) in daemons or int(pid) in also):
            pair = recorded(int(pid))
            if pair:
                out.append((pair, profile.group(1)))
    return out


def peer(conn) -> int | None:
    """The process at the other end of a connected socket, as the system names it: for a socket
    that was listened on, the process that listened. None where the system does not say."""
    try:
        if hasattr(socket, "SO_PEERCRED"):  # Linux: struct ucred, {pid, uid, gid}
            pid, uid, _ = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                                                struct.calcsize("3i")))
            return pid if uid == os.getuid() and pid > 1 else None
        if sys.platform == "darwin":        # SOL_LOCAL and LOCAL_PEERPID, of sys/un.h
            pid = struct.unpack("i", conn.getsockopt(0, 2, struct.calcsize("i")))[0]
            return pid if pid > 1 else None
    except (OSError, struct.error):
        pass
    return None


def listener(path) -> tuple[socket.socket | None, list | None]:
    """Connect to a session's socket: the connection, or None when the path is no socket of this
    user or nothing listens on it, and the listening process as [pid, start identity], or None
    when the system does not name it. A symbolic link is not followed to another's socket."""
    try:
        st = os.lstat(path)
        if not stat.S_ISSOCK(st.st_mode) or st.st_uid != os.getuid():
            return None, None
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(ASK)
        conn.connect(str(path))
    except OSError:
        return None, None
    return conn, recorded(peer(conn))


def answers(path) -> bool:
    conn = listener(path)[0]
    if conn:
        conn.close()
    return bool(conn)


def ask(conn) -> bool:
    """Ask the session at the other end of a connection to close, as agent-browser's own "close"
    asks it: one JSON line. True when it said that it would. Nothing else is done to it here."""
    try:
        conn.sendall((json.dumps({"id": secrets.token_hex(4), "action": "close"}) + "\n").encode())
        with conn.makefile() as replies:
            return json.loads(replies.readline() or "{}").get("success") is True
    except (OSError, ValueError, AttributeError):
        return False
    finally:
        conn.close()


def daemon_at(socket_dir: Path, session: str) -> list | None:
    """The daemon of a session that "start" has just started or reached: the process that
    listens on its socket, by the system's word. Where the system does not say, the process
    that the pid file agent-browser wrote a moment ago names, when it is an agent-browser
    process. Only "start" reads that file, of a session it launched itself: "stop" never does."""
    conn, pair = listener(socket_dir / f"{session}.sock")
    if not conn:
        return None
    conn.close()
    if pair:
        return pair
    try:
        pid = int((socket_dir / f"{session}.pid").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    return recorded(pid) if CLI in named(pid) else None


# ---------------------------------------------------------------- files

def in_temp(path) -> bool:
    """Whether a path is directly in the temporary directory."""
    return os.path.realpath(os.path.dirname(path)) == os.path.realpath(tempfile.gettempdir())


def environment(session: dict) -> dict:
    """This process's environment as changes() makes it: what every agent-browser command of
    "start" runs with, and what the run's own commands run with."""
    env, change = dict(os.environ), changes(session)
    return {**{k: v for k, v in env.items() if k not in change}, **{k: v for k, v in change.items() if v is not None}}


def browser(session: dict, *args: str, seconds: float = COMMAND, cwd=None):
    """Run one agent-browser command on the session. Raises Failed when it cannot be run or does
    not end in time, and returns the finished process otherwise, whatever its exit code."""
    try:
        return subprocess.run([CLI, *args], env=environment(session), cwd=cwd, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=seconds)
    except subprocess.TimeoutExpired:
        raise Failed(f"{CLI} {args[0]} did not end within {seconds:g} s")
    except OSError as err:
        raise Failed(f"{CLI} {args[0]} could not be run: {err}")


def must(session: dict, *args: str, **how):
    """The same, for a command that has to succeed: Failed with the CLI's own first line otherwise."""
    r = browser(session, *args, **how)
    if r.returncode != 0:
        said = [line.strip() for line in (r.stderr + "\n" + r.stdout).splitlines() if line.strip()]
        words = " ".join(a for a in args if not a.startswith("-"))
        raise Failed(f"{CLI} {words} failed (exit code {r.returncode})" + (f": {said[0][:300]}" if said else ""))
    return r


def write_policy(path: Path, policy: dict):
    """Put a policy at its path in one step: the session reads the file again for every command.
    Through a file made anew beside it: a symbolic link at either name is replaced, never followed."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with os.fdopen(watchdog.fresh(tmp, mode=0o600), "w") as f:
        f.write(json.dumps(policy) + "\n")
    os.replace(tmp, path)


@contextlib.contextmanager
def held(record, create: bool):
    """The record, open and locked for as long as "start" or "stop" works on it, so that neither
    acts on a session the other is half-way through. None when there is none and create is false.
    Refused, before it is read or waited for, when it is a symbolic link or anything but a regular
    file of this user of a record's size (watchdog.opened())."""
    try:
        fd = watchdog.opened(record, os.O_RDWR | (os.O_CREAT if create else 0))
    except FileNotFoundError:
        yield None
        return
    except watchdog.Unsafe as err:
        raise Refused(str(err))
    with os.fdopen(fd, "r+") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX)
        except OSError:
            pass  # a file system without locks
        yield f


def load(f, log) -> dict:
    """The record in an open file, as "stop" may act on it: {} for a "start" that got no further
    than making the file. Refused unless it is what "start" writes, every field of its shape and
    the policy named as the attempt's (module docstring)."""
    f.seek(0)
    record = record_of(log)
    try:
        info = json.loads(f.read() or "{}")
    except ValueError:
        info = None
    if not isinstance(info, dict):
        raise Refused(f"{record} is not a record of a browser session: it holds no JSON object")
    if not info or ("socket_dir" not in info and info.get("stopped")):  # nothing was made
        return info
    name, folder, policy = info.get("session"), info.get("socket_dir"), info.get("policy")
    wrong = [field for field, ok in (
        ("session", isinstance(name, str) and name not in ("", ".", "..") and not set(name) & {"/", "\0", os.sep}),
        ("socket_dir", isinstance(folder, str) and os.path.isabs(folder) and os.path.normpath(folder) == folder
         and SOCKETS.fullmatch(os.path.basename(folder))),
        ("policy", isinstance(policy, str) and os.path.basename(policy) == policy_of(log).name),
        ("token", isinstance(info.get("token"), str) and TOKEN.fullmatch(info["token"])),
        *((field, info.get(field) is None or pair_of(info[field])) for field in ("daemon", "browser")),
        ("profile", info.get("profile") is None or isinstance(info["profile"], str))) if not ok]
    if wrong:
        raise Refused(f"{record} is not as \"start\" wrote it: its {', '.join(wrong)} "
                      f"{'is' if len(wrong) == 1 else 'are'} not what a session of this attempt has")
    return info


def save(f, info: dict):
    f.seek(0)
    f.write(json.dumps(info) + "\n")
    f.truncate()
    f.flush()
    os.fsync(f.fileno())


def proven(info: dict) -> tuple[int | None, str | None]:
    """The socket directory of a record, open, when it is proven to be the one "start" made for
    this session (module docstring, "What "stop" removes"): a descriptor to close. Otherwise
    None, and why it is not this session's to touch, or None again when there is none."""
    path = info["socket_dir"]
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None, None
    except OSError as err:
        return None, f"it is not a directory that can be opened ({err.strerror or err})"
    why, st = None, os.fstat(fd)
    if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
        why = "it is not a directory of this user alone"
    elif not in_temp(path):
        why = f"it is not directly in this command's temporary directory, {tempfile.gettempdir()}"
    else:
        try:
            with os.fdopen(watchdog.opened(MARKER, dir_fd=fd)) as f:
                token = f.read(64).strip()
        except OSError:  # none, or none to read: a link, a FIFO
            token = None
        if token != info["token"] and (token is not None or os.listdir(fd)):
            why = "it does not hold this session's token"
    if why:
        os.close(fd)
        return None, why
    return fd, None


def sockets_in(fd: int) -> list[str]:
    """The sockets in an open socket directory, by name."""
    def is_socket(name):
        try:
            return stat.S_ISSOCK(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode)
        except OSError:
            return False
    return sorted(name for name in os.listdir(fd) if name.endswith(".sock") and is_socket(name))


def emptied(fd: int, path) -> str | None:
    """Empty a proven socket directory through its open descriptor and remove it. None when it
    has gone, else why it has not. Each entry is unlinked: a symbolic link goes, what it points
    at stays. With a directory in it nothing is unlinked, so nothing outside is ever reached."""
    try:
        names = os.listdir(fd)
        if any(stat.S_ISDIR(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode) for name in names):
            return "it holds a directory, which no session makes"
        for name in names:
            os.unlink(name, dir_fd=fd)
        if os.path.samestat(os.fstat(fd), os.lstat(path)):  # still the directory at that path
            os.rmdir(path)
    except OSError as err:
        return f"it could not be emptied and removed ({err.strerror or err})"
    return None


def profile_gone(path: str) -> str | None:
    """Remove the profile directory a browser of the session named, when it is proven to be one
    (module docstring). None when it has gone or was not there, else why it stays."""
    try:
        st = os.lstat(path)
    except OSError:
        return None
    if not (PROFILES.fullmatch(os.path.basename(path)) and stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid()
            and in_temp(path)):
        return "nothing proves that it is a profile directory of this session"
    shutil.rmtree(path, ignore_errors=True)  # unlinks a symbolic link in it, and descends through none
    return "it could not be removed" if os.path.lexists(path) else None


# ---------------------------------------------------------------- start and stop

def start(session: dict, cwd, viewport=VIEWPORT, state_file=None, delete_state: bool = False) -> dict:
    """Start the session of a plan() and record it. Returns the record. Raises Failed, with the
    session stopped again, when any step fails."""
    if not shutil.which(CLI):
        raise Failed(f"the {CLI} CLI is not on PATH")
    log, name, socket_dir = session["log"], session["session"], Path(session["socket_dir"])
    policy = policy_of(log)
    if not (SOCKETS.fullmatch(socket_dir.name) and socket_dir.is_absolute() and in_temp(socket_dir)):
        raise Failed(f"the socket directory {socket_dir} is not pp-<8 hex digits> in the temporary directory, "
                     f"{tempfile.gettempdir()}: \"stop\" would not take it for this session's")
    if len(os.fsencode(str(socket_dir / f"{name}.sock"))) > SOCKET_PATH:
        raise Failed(f"the socket path under {socket_dir} would be longer than {SOCKET_PATH} bytes: use a shorter "
                     "temporary directory (TMPDIR) or a shorter run id")
    record_of(log).parent.mkdir(parents=True, exist_ok=True)
    try:
        with held(record_of(log), create=True) as f:
            earlier = load(f, log)
            if earlier.get("socket_dir") and not earlier.get("stopped"):  # of an attempt that never ran as the
                ended(f, earlier, log)                                    # CLI, whose number this one has
            info = {"session": name, "socket_dir": str(socket_dir), "policy": str(policy),
                    "token": secrets.token_hex(16), "cwd": str(cwd), "started": round(time.time(), 3),
                    "launching": False, "daemon": None, "browser": None, "profile": None, "stopped": None}
            nothing = {"stopped": round(time.time(), 3), "found": False, "left": [], "kept": []}
            if os.path.lexists(socket_dir):  # not this session's, so it never gets on its record
                save(f, nothing)
                raise Failed(f"the socket directory {socket_dir} exists already")
            save(f, info)  # on record before it exists
            try:
                os.mkdir(socket_dir, 0o700)
            except OSError as err:  # as above
                save(f, nothing)
                raise Failed(f"the socket directory {socket_dir} could not be made: {err.strerror or err}")
            try:
                os.chmod(socket_dir, 0o700)  # whatever the umask
                with os.fdopen(os.open(socket_dir / MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as m:
                    m.write(info["token"] + "\n")
                write_policy(policy, OPEN)
                info["launching"] = True
                save(f, info)
                must(info, *(["--state", str(state_file)] if state_file else []), "open", "about:blank",
                     seconds=LAUNCH, cwd=cwd)
                daemon = daemon_at(socket_dir, name)
                if not daemon:
                    raise Failed(f"{CLI} started no session in {socket_dir}")
                found = browsers({daemon[0]})
                info.update(daemon=daemon, browser=found[0][0] if found else None,
                            profile=found[0][1] if found else None, launching=False)
                save(f, info)
                if state_file and delete_state:
                    Path(state_file).unlink(missing_ok=True)
                must(info, "set", "viewport", str(int(viewport[0])), str(int(viewport[1])), cwd=cwd)
                write_policy(policy, STRICT)
                must(info, "get", "url", cwd=cwd)
                probe = browser(info, "eval", "1", cwd=cwd)
                if probe.returncode == 0 or DENIED not in probe.stderr + probe.stdout:
                    raise Failed(f"the action policy is not in force: {CLI} did not refuse a command it leaves out")
                if daemon_at(socket_dir, name) != daemon or not alive(daemon):
                    raise Failed(f"{CLI} restarted the session while it was being set up")
            except (Failed, OSError) as err:
                info["launching"] = False  # the command that launches has ended: no session of it is yet to appear
                ended(f, info, log)
                raise Failed(str(err))
    except Refused as err:
        raise Failed(f"an earlier record of this attempt's session cannot be trusted ({err}): look for a browser it "
                     "left with ps, then delete the record")
    return info


def stop(log) -> dict:
    """Stop the session of the attempt with this log base: {"found", "left", "kept", "said"}.
    "found" is whether a process of it was still running, "left" the pids still running
    afterwards, "kept" what was left in place, each with its reason, and "said" one line for a
    person. Raises Refused, with nothing touched, for a record it will not act on."""
    with held(record_of(log), create=False) as f:
        info = load(f, log) if f else {}
        if not info.get("socket_dir"):
            if f and not info:  # a "start" that got no further than making the file
                save(f, {"stopped": round(time.time(), 3), "found": False, "left": [], "kept": []})
            return {"found": False, "left": [], "kept": [], "said": "no browser session is on record"}
        if info.get("stopped"):
            return {"found": False, "left": info.get("left") or [], "kept": info.get("kept") or [],
                    "said": "its browser session was stopped already"}
        return ended(f, info, log)


def ended(f, info: dict, log) -> dict:
    """End the session of a record and what it left, and note it on the record (module docstring,
    "What "stop" does" and "What "stop" removes")."""
    policy, path = policy_of(log), info["socket_dir"]
    daemon, chrome = info.get("daemon"), info.get("browser")
    found = alive(daemon) or alive(chrome)
    daemons, asked, said_yes, allowed = [daemon] if daemon else [], [], [], False
    folder, unproven = proven(info)
    kept = [f"{path}: {unproven}"] if unproven else []
    try:
        if folder is not None:
            give_up = time.time() + SETTLE  # a session that "start" was launching when it was cut short
            while info.get("launching") and not daemon and not sockets_in(folder) and time.time() < give_up:
                time.sleep(0.05)
            for name in sockets_in(folder):  # every session that answers there, whoever started it
                conn, pair = listener(os.path.join(path, name))
                if conn:
                    asked.append((name, conn, pair))
                    daemons += [pair] if pair and pair not in daemons else []
        # The browsers, each with the profile directory its own command names, before anything is asked to go.
        chromes = browsers({pair[0] for pair in daemons if alive(pair)}, {chrome[0]} if alive(chrome) else ())
        known = daemons + [pair for pair, _ in chromes] + ([chrome] if chrome else [])
        found = found or bool(asked)
        if asked:
            try:
                write_policy(policy, OPEN)  # a session refuses to close under the strict one
                allowed = True
            except OSError:
                pass
        for name, conn, pair in asked:
            if ask(conn) and pair:
                said_yes.append(pair)
        closing = bool(asked)
        for pair in daemons:
            try:
                if pair not in said_yes and alive(pair):
                    closing = True
                    os.kill(pair[0], signal.SIGTERM)
            except OSError:
                pass

        def unnamed():  # the sessions that still answer, of a process the system did not name
            return [name for name, _, pair in asked if not pair and answers(os.path.join(path, name))]

        # A daemon that goes takes its browser with it: one that was killed before now did not.
        give_up = time.time() + GRACE
        while closing and time.time() < give_up and (any(map(alive, known)) or unnamed()):
            time.sleep(0.05)
        for pair in [pair for pair, _ in chromes] + ([chrome] if chrome else []) + daemons:
            try:
                if alive(pair) and pair not in daemons and os.getpgid(pair[0]) == pair[0]:
                    os.killpg(pair[0], signal.SIGKILL)
                elif alive(pair):
                    os.kill(pair[0], signal.SIGKILL)
            except OSError:
                pass
        give_up = time.time() + GRACE
        while any(map(alive, known)) and time.time() < give_up:
            time.sleep(0.05)
        left = sorted({pair[0] for pair in known if alive(pair)})
        deaf = unnamed() if folder is not None else []
        if deaf:
            kept.append(f"{path}: the session {', '.join(name[:-len('.sock')] for name in deaf)} in it still "
                        "answers, and the system does not name its process")
        elif left and folder is not None:
            kept.append(f"{path}: a process of the session is still running")
        elif folder is not None:
            why = emptied(folder, path)
            kept += [f"{path}: {why}"] if why else []
        for pair, profile in chromes:
            why = None if alive(pair) else profile_gone(profile)
            kept += [f"{profile}: {why}"] if why else []
        on_record = info.get("profile")
        if on_record and on_record not in [profile for _, profile in chromes] and os.path.lexists(on_record):
            kept.append(f"{on_record}: its browser had gone, so nothing proves that it is this session's")
        try:
            if not (left or deaf or unproven):
                policy.unlink(missing_ok=True)
            elif allowed:
                write_policy(policy, STRICT)
        except OSError:
            pass
    finally:
        if folder is not None:
            os.close(folder)
    info.update(stopped=round(time.time(), 3), found=found, left=left, kept=kept)
    save(f, info)
    said = ("its browser session was stopped" if found else "no browser session was running") + (
        f", but pid {', '.join(map(str, left))} could not be ended: check with "
        f"ps -o pid,command -p {','.join(map(str, left))}" if left else "") + (
        f". Left in place: {'; '.join(kept)}" if kept else "")
    return {"found": found, "left": left, "kept": kept, "said": said}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    go = sub.add_parser("start", help="start a session and print the environment that reaches it")
    go.add_argument("--log", required=True)
    go.add_argument("--session", required=True)
    go.add_argument("--socket-dir", required=True)
    go.add_argument("--cwd", default=os.getcwd())
    go.add_argument("--viewport", default="x".join(map(str, VIEWPORT)))
    go.add_argument("--state")
    go.add_argument("--delete-state", action="store_true")
    end = sub.add_parser("stop", help="stop the session of an attempt, and remove what it left")
    end.add_argument("--log", required=True)
    args = ap.parse_args()
    if args.cmd == "stop":
        try:
            result = stop(args.log)
        except Refused as err:
            print(f"the record of the browser session cannot be trusted, so nothing was stopped or removed: {err}",
                  file=sys.stderr)
            return 2
        print(result["said"])
        return 1 if result["left"] or result["kept"] else 0
    size = re.fullmatch(r"(\d+)x(\d+)", args.viewport)
    if not size:
        ap.error("--viewport is <width>x<height>, as in 1440x900")
    if args.delete_state and not args.state:
        ap.error("--delete-state goes with --state")
    session = {"log": args.log, "session": args.session, "socket_dir": args.socket_dir,
               "policy": str(policy_of(args.log))}
    try:
        info = start(session, args.cwd, (int(size.group(1)), int(size.group(2))), args.state, args.delete_state)
    except Failed as err:
        print(err, file=sys.stderr)
        return 1
    finally:
        if args.delete_state:
            Path(args.state).unlink(missing_ok=True)
    print(json.dumps(variables(info)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
