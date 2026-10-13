#!/usr/bin/env python3
"""The watchdog of one attempt: starts a harness CLI, stays with it until it has ended, and
records how it ended.

launch.py starts one for every attempt of a run or job, in a session of its own, and never
signals a CLI itself. Whatever must not depend on a launcher being alive is done here: the time
limit, the stop, ending the processes a CLI leaves behind, and the record of when and how the
attempt ended. Standard library only, and nothing of the skill is imported: this start-up is
paid once per attempt.

    run_watchdog.py [--hooks <json>] <pid fd> <lock fd> <end record> <seconds> <grace> <command> [<argument> ...]

    --hooks      commands to run around the CLI (see "Hooks"): one JSON object
    pid fd       the attempt's pid file (logs/<run id>.<attempt>.pid), open and locked by the
                 launcher that starts this process
    lock fd      the attempt's lock file (logs/<run id>.<attempt>.lock), open, made anew by that
                 launcher and never written: see "The lock of an attempt"
    end record   the file to write when the attempt has ended (logs/<run id>.<attempt>.end)
    seconds      the attempt's time limit: what is left of the run's allowance
    grace        seconds a process gets between SIGTERM and SIGKILL
    command      the CLI and its arguments

The launcher gives this process the CLI's standard input, output and error, its environment and
its working directory, and the CLI inherits them. Once the CLI is running the watchdog lets go
of all three streams, and it writes to nothing but its two files. Its hooks write to a third.

What it does, in order:

1. Takes the lock of the attempt, which it holds until it exits (see "The lock of an attempt").
   Then starts a child that begins a session of its own and waits. The CLI is then the leader
   of a process group that holds everything it starts, in a session without a terminal.
2. Writes the pid file, two lines: "<pid> <start identity>" for itself, then for the CLI. The
   identity is the process's start time (process()), which tells it from a later process that
   was given the same id. Where the system names the process namespace this attempt runs in
   (namespace()), one line more says which: "namespace <identity>". The ids above name these
   processes only to a shell in that namespace. The line decides nothing of whether the attempt
   is alive, which the lock says. launch.py goes by it for one thing: it looks up no id that
   was recorded in another namespace than its own, and says so of the CLI of a watchdog that
   has gone without an end record.
3. Runs the "before" hook, when there is one, with its process on a line of its own in the pid
   file for as long as it runs (see "Hooks"). Then lets the child become the CLI, or, when the
   hook failed, lets it end without becoming anything. The lock on the pid file drops when
   both have closed it: the child by becoming the CLI, the watchdog once it knows the child
   did, or once it has written the end record of a child that never became the CLI. So
   whoever waits for that lock (launch.py recorded()) reads about a process that is the CLI,
   or one that never will be. A child whose watchdog dies before this step is done never
   becomes the CLI: nothing runs unrecorded.
4. Waits for the CLI to end, and learns that it has without reaping it (ended()). At the time
   limit, or when asked to stop, it sends SIGTERM to the CLI's process group and, after the
   grace, SIGKILL.
5. When the CLI has ended, for whatever reason, ends what is left of its process group the
   same way: SIGTERM unless the group already had one, what is left of the grace, then SIGKILL.
   A process that left the group by starting a session of its own is beyond its reach.
6. Reaps the CLI, runs the "after" hook when there is one, writes the end record in one step,
   and exits.

Hooks. The JSON object is {"before": [<command>, <argument>, ...], "after": [...], "seconds":
{"before": <n>, "after": <n>}, "log": <file>}. Each command is optional. The watchdog knows
nothing of what they do: launch.py uses them for whatever an attempt needs that must not depend
on a launcher being alive, such as a browser session that is started for the CLI and stopped
after it. A hook runs to its end in a process group of its own, in the CLI's working directory
and environment, with nothing on its standard input and its output appended to "log", which is
opened as every file of an attempt is (see "The files of an attempt"): with a symbolic link or
a FIFO at that name the command is not run, and the hook has failed. It
succeeds by exiting with code 0. One that outlasts its seconds (HOOK when none are given) is
killed with its group, and has failed. A request to stop does not cut a hook short.
- "before" runs once the attempt is on record in the pid file and before the CLI exists. When it
  fails the CLI is never executed: the end record says so under "refused", as it does of a
  command the system refused. Its process, the leader of its group, is the third process of the
  pid file, a line "<pid> <start identity>" after the others, from before it can do anything
  until it has ended and been reaped: it waits for that line as the CLI's child waits for its
  own, and ends without running the command when the watchdog dies first. The line is taken out
  before the CLI is let go. So a pid file with a third process is of an attempt whose watchdog
  was killed while "before" ran, whose CLI was never executed, and whose "before" may still be
  running with no one to wait for it: launch.py ends it before it undoes what the hook was to
  do.
- "after" runs once "before" has been attempted, however that and the CLI ended: by itself, at
  the time limit, on a request to stop, or never having been executed. It runs after the CLI
  and its process group have gone and before the end record is written, so a reader of the end
  record knows that it has run. The time it takes is not in "ended".

The invariant: the CLI, the leader of its group, is reaped only after the last signal to that
group. Until then it is at least a zombie, so its process id, which is the group's id, cannot
have been given to another process or group, and every signal sent here reaches this attempt's
processes or nothing. After the reap the group is never signalled again.

The lock of an attempt. The watchdog holds an exclusive flock on the attempt's lock file from
before the pid file names it until it exits, and the system lets go of it when the process
ends, however it ends. So the lock says whether this watchdog is alive, to every shell that can
open the file: a shell in another process namespace, as inside a harness's sandbox, sees the
lock where it sees no process of the attempt, and one outside a sandbox that has ended finds
the lock free where the ids on record can tell it nothing. launch.py asks with a shared lock
that is not waited for and is let go at once (launch.py taken(), unseen()). The lock is taken
once, on a file made for this attempt alone, and waited for: all that can be in its way is
such a question, which is gone in an instant, so there is nothing to ask again. The descriptor
is closed when a child of the watchdog becomes its command, the CLI or a hook, so nothing a
panellist runs holds the lock or can let go of it. A child that has not become its command yet
holds a copy, and ends at once when the watchdog dies (become(), hook()). The child that waits
to be the CLI, and that of a "before" command, hold the pid file the same way, and launch.py
reads that only when they have let go of it (recorded()): so it never asks the lock while one
of them holds it for a watchdog that is dead. The child of an "after" command holds its copy
for the instant before it becomes the command. Where the file system has no locks the watchdog
runs without one, and launch.py goes by the ids on record, as it does for an attempt from
before watchdogs held a lock.

The files of an attempt. Whatever an attempt keeps in logs/ and reads back is read as a file
that another process may have put there, here and in launch.py, browser_session.py and
panel_lib.py (the copy of a persona file made before a follow-up question), which use the two
functions of this file for it. opened() opens one without following a symbolic
link and without waiting for anyone, as an open of a FIFO would, and gives it up unread
(Unsafe) unless it is a regular file of this user of a record's size. fresh() makes one anew:
what had its name is unlinked, never followed and never written through.

The end record is one JSON object:

    ended      epoch seconds when the CLI and its process group had gone
    exit_code  the CLI's exit code, or minus the number of the signal that ended it. null when
               the CLI was never executed
    stopped    "time" when the watchdog stopped it at its time limit, "stop" when it was asked
               to stop, else null: the CLI ended by itself
    refused    the system's message when the command could not be executed at all, else null
    argv       the command
    error      present only when the watchdog itself failed while waiting: what went wrong. It
               has then killed the process group
    hooks      present only when the watchdog was given hooks: {"before", "after"}, each null
               when the hook succeeded or there was none, else what went wrong, in words

Signals. SIGTERM is a request to stop the CLI: launch.py sends it for "stop" and for its own
SIGINT, SIGTERM and SIGHUP. A second one skips the grace, also for a process already being
stopped at its time limit. SIGHUP and SIGINT are ignored, so a terminal that closes or a
Ctrl-C reaches an attempt only as a stop request from its launcher, and never ends the
watchdog before it has written its record. The CLI gets back the signal settings the watchdog
was started with. A watchdog that is killed outright leaves no end record: launch.py then kills
the process group recorded in the pid file if its leader is still running, and otherwise only
names what is left of it (launch.py kill_group()): the group of a "before" hook that was still
running, then the CLI's. Its "after" hook has then not run: what the hook was to undo is the
launcher's to undo.
"""

from __future__ import annotations

import errno
import fcntl
import os
import select
import signal
import stat
import sys
import time

PROC = os.path.exists("/proc/self/stat")
SWEEP = 0.02    # seconds between looks at a process group whose leader has ended
GIVE_UP = 5.0   # seconds a process group gets to disappear after SIGKILL
LOOK = 5.0      # seconds between looks at a CLI where os.waitid is missing: see ended()
RESTORED = ("SIGPIPE", "SIGXFSZ")  # ignored by Python at start-up: the CLI gets the system's default
HOOK = 60.0     # seconds a hook gets when the launcher names none
RECORD = 1 << 20  # bytes a record in logs/ may have, and far more than one holds: a larger file is not read as one


class Unsafe(OSError):
    """A file that is not opened as an attempt's: a symbolic link, or anything but a regular file
    of this user that is no larger than it may be."""


def opened(path, flags: int = os.O_RDONLY, mode: int = 0o644, dir_fd: int | None = None, most: int = RECORD) -> int:
    """Open a file an attempt keeps in logs/, which another process may have put there, to read
    it or to work on it: a descriptor. A symbolic link is never followed, and the open never
    waits, as it would for the other end of a FIFO. Raises Unsafe, with nothing read, unless
    the descriptor is of a regular file of this user that holds at most `most` bytes."""
    try:
        fd = os.open(path, flags | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, mode, dir_fd=dir_fd)
    except OSError as err:
        if err.errno in (errno.ELOOP, errno.EMLINK):  # what O_NOFOLLOW says of a link, on Linux and macOS, and on BSD
            raise Unsafe(f"{path} is a symbolic link") from None
        raise
    st = os.fstat(fd)
    why = ("is not a regular file of this user" if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
           else f"holds {st.st_size} bytes, more than such a file may" if st.st_size > most else None)
    if why:
        os.close(fd)
        raise Unsafe(f"{path} {why}")
    return fd


def fresh(path, flags: int = os.O_WRONLY, mode: int = 0o644, dir_fd: int | None = None) -> int:
    """Make a file anew at a path, to write it: a descriptor. Whatever had that name is unlinked
    first, a symbolic link and not what it points at, and none is followed or written through."""
    try:
        os.unlink(path, dir_fd=dir_fd)
    except FileNotFoundError:
        pass
    return os.open(path, flags | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode, dir_fd=dir_fd)


def process(pid) -> tuple[str, str] | None:
    """(state, start identity) of a process, or None when there is none. The identity is the
    process's start time, which tells it from a later process that was given the same id."""
    try:
        if PROC:
            with open(f"/proc/{pid}/stat") as f:
                fields = f.read().rsplit(")", 1)[1].split()
            return fields[0], f"tick {fields[19]}"
        import subprocess  # only where there is no /proc, so the watchdog pays for it only there
        r = subprocess.run(["ps", "-o", "stat=", "-o", "lstart=", "-p", str(pid)], capture_output=True,
                           text=True, env={**os.environ, "LC_ALL": "C"}, stdin=subprocess.DEVNULL)
    except (OSError, IndexError):
        return None
    state, _, started = r.stdout.strip().partition(" ")
    return (state, " ".join(started.split())) if started.strip() else None


def identity(pid) -> str | None:
    found = process(pid)
    return found[1] if found else None


def namespace() -> str | None:
    """The process namespace this process runs in, as the system names it, or None where it
    names none (no /proc, as on macOS). A process id means its process only within the
    namespace: a shell in another, as inside a harness's sandbox, finds no process under it,
    or someone else's."""
    try:
        return os.readlink("/proc/self/ns/pid")
    except OSError:
        return None


def signal_group(group: int, sig: int) -> bool:
    """Send a signal to every process of a group. False when the group has none left, not even
    one that has ended and is not reaped. Signal 0 sends nothing and only asks."""
    try:
        os.killpg(group, sig)
    except OSError:
        return False
    return True


def others(group: int) -> list[int]:
    """The processes of a process group, its leader aside. Asking the group itself (signal 0)
    cannot tell this: a leader that has ended and is not reaped still answers for it."""
    if PROC:
        pairs = []
        for name in filter(str.isdigit, os.listdir("/proc")):
            try:
                pairs.append((int(name), os.getpgid(int(name))))
            except OSError:
                pass  # gone since it was listed
    else:
        import subprocess
        r = subprocess.run(["ps", "-A", "-o", "pid=", "-o", "pgid="], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, check=True)
        rows = (line.split() for line in r.stdout.splitlines())
        pairs = [(int(row[0]), int(row[1])) for row in rows if len(row) == 2 and row[0].isdigit() and row[1].isdigit()]
    return [pid for pid, of in pairs if of == group != pid]


def write_end(path: str, record: dict):
    """Write the end record in one step, so a reader never sees half of it."""
    import json  # not needed until an attempt has ended, and the CLI starts sooner without it
    tmp = os.path.join(os.path.dirname(path), f".{os.path.basename(path)}.{os.getpid()}.tmp")
    with os.fdopen(fresh(tmp), "w") as f:
        f.write(json.dumps(record) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def become(argv: list[str], inherited: dict, go: int, held: int, said: int):
    """In the child: start a session, wait for the watchdog to have recorded this process, then
    become argv. When the system refuses that, its message goes to the watchdog through said."""
    try:
        for sig, was in inherited.items():
            signal.signal(sig, was)
        os.setsid()
        os.close(held)  # the watchdog's end of go: with it open here, a dead watchdog would never be noticed
        if os.read(go, 1):
            os.execvp(argv[0], argv)
    except OSError as err:
        os.write(said, str(err).encode())
    finally:
        os._exit(126)


def hook(hooks: dict, name: str, inherited: dict, wake: int, note: int | None = None) -> str | None:
    """Run the attempt's "before" or "after" command to its end (see "Hooks"). None when there is
    no such command or it exited with code 0, else what went wrong, with the last line it wrote.
    note is the open pid file, for "before": the command's process is on record there, as one
    more line, from before it runs the command until it has been reaped."""
    argv, seconds = hooks.get(name), float((hooks.get("seconds") or {}).get(name) or HOOK)
    if not argv:
        return None
    try:
        try:
            written = os.path.getsize(hooks["log"])
        except OSError:
            written = 0
        go, go_w = os.pipe()
        pid = os.fork()
        if not pid:
            try:
                os.setpgid(0, 0)
                for sig, was in inherited.items():
                    signal.signal(sig, was)
                os.close(go_w)  # the watchdog's end: with it open here, a dead watchdog would never be noticed
                if os.read(go, 1):  # on record, when it is to be: a watchdog that died first wrote nothing
                    out = opened(hooks["log"], os.O_WRONLY | os.O_CREAT | os.O_APPEND, most=sys.maxsize)
                    os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
                    os.dup2(out, 1)
                    os.dup2(out, 2)
                    try:
                        os.execvp(argv[0], argv)
                    except OSError as err:
                        os.write(2, f"{argv[0]}: {err}\n".encode())
            finally:
                os._exit(127)
        os.close(go)
        try:
            os.setpgid(pid, pid)  # here too, so that the group is there whichever of the two runs first
        except OSError:
            pass
        at = None
        try:
            if note is not None:
                at = os.lseek(note, 0, os.SEEK_CUR)
                os.write(note, f"{pid} {identity(pid) or ''}\n".encode())
            os.write(go_w, b"\n")
        finally:
            os.close(go_w)  # with nothing written, the child ends without running the command
        give_up, late = time.time() + seconds, False
        while True:
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                break
            if time.time() >= give_up:
                signal_group(pid, signal.SIGKILL)  # not reaped yet, so the group's id is still its own
                status, late = os.waitpid(pid, 0)[1], True
                break
            nap(wake, give_up - time.time())
        if at is not None:  # reaped: its id is no longer its own, and no longer on record
            os.ftruncate(note, at)
            os.lseek(note, at, os.SEEK_SET)
        if late:
            return f'its "{name}" command did not end within {seconds:g} s and was killed'
        if status == 0:
            return None
        how = f"signal {os.WTERMSIG(status)}" if os.WIFSIGNALED(status) else f"exit code {os.WEXITSTATUS(status)}"
        try:
            with os.fdopen(opened(hooks["log"]), errors="replace") as f:
                f.seek(written)
                said = [line.strip() for line in f.read().splitlines() if line.strip()]
        except OSError as err:  # no log of the hook's to read: a link, a FIFO, or none
            said = [str(err)]
        return f'its "{name}" command failed ({how})' + (f": {said[-1][:500]}" if said else "")
    except Exception as err:
        return f'its "{name}" command could not be run: {err!r}'


def forget(wake: int):
    """Drop the signals that have arrived so far, so that only a later one ends the next nap."""
    try:
        while os.read(wake, 512):
            pass
    except BlockingIOError:
        pass


def nap(wake: int, seconds: float):
    """Sleep until a signal arrives (a stop request, or a child that ended) or seconds pass."""
    select.select([wake], [], [], max(0.0, seconds))
    forget(wake)


def ended(pid: int, wake: int) -> bool:
    """Whether a child has ended, without reaping it: it stays a zombie, and its id its own.

    Python has no os.waitid on macOS before 3.13. There the child's state is read as any
    process's is, from ps, which is a child as well: the SIGCHLD of its end is dropped, and one
    of the CLI's can go with it. So a CLI is looked at every LOOK seconds as well as at each
    signal, and one that ps does not show cannot be watched at all: its group is killed."""
    if hasattr(os, "waitid"):
        return os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None
    found = process(pid)
    if not PROC:
        forget(wake)
    if not found:
        raise RuntimeError(f"cannot tell whether the CLI (pid {pid}) has ended: ps does not show it")
    return found[0].startswith("Z")


def main():
    asks = []  # one item for each request to stop
    inherited = {sig: signal.signal(sig, signal.SIG_IGN) for sig in (signal.SIGHUP, signal.SIGINT)}
    inherited[signal.SIGTERM] = signal.signal(signal.SIGTERM, lambda *_: asks.append(1))
    inherited[signal.SIGCHLD] = signal.signal(signal.SIGCHLD, lambda *_: None)  # only to wake the wait
    inherited = {sig: was if was == signal.SIG_IGN else signal.SIG_DFL for sig, was in inherited.items()}
    inherited.update((getattr(signal, name), signal.SIG_DFL) for name in RESTORED if hasattr(signal, name))
    args, hooks = sys.argv[1:], None
    if args[:1] == ["--hooks"]:
        import json  # only for an attempt with hooks: the others start their CLI sooner without it
        hooks, args = json.loads(args[1]), args[2:]
    handle, watch, end = int(args[0]), int(args[1]), args[2]
    seconds, grace, argv = float(args[3]), float(args[4]), args[5:]
    os.set_inheritable(handle, False)  # or the CLI would hold the lock on the pid file for as long as it runs
    os.set_inheritable(watch, False)   # nor may the CLI or a hook hold the attempt's lock: it says this process lives
    try:  # held from here until this process ends, and never closed: see "The lock of an attempt"
        fcntl.flock(watch, fcntl.LOCK_EX)
    except OSError:
        pass  # a file system without locks: launch.py goes by the ids on record
    wake, wake_w = os.pipe()
    os.set_blocking(wake, False)
    os.set_blocking(wake_w, False)
    signal.set_wakeup_fd(wake_w, warn_on_full_buffer=False)

    go, go_w = os.pipe()
    said, said_w = os.pipe()
    cli = os.fork()
    if not cli:
        become(argv, inherited, go, go_w, said_w)
    os.close(go)
    os.close(said_w)
    within = namespace()
    os.write(handle, (f"{os.getpid()} {identity(os.getpid()) or ''}\n{cli} {identity(cli) or ''}\n"
                      + (f"namespace {within}\n" if within else "")).encode())
    failed = hook(hooks, "before", inherited, wake, handle) if hooks else None
    if not failed:
        os.write(go_w, b"\n")
    os.close(go_w)  # with nothing written, the child ends without becoming the CLI
    refused = b""
    while True:  # ends when the child is the CLI, or has given up
        chunk = os.read(said, 4096)
        if not chunk:
            break
        refused += chunk
    os.close(said)
    record = {"ended": None, "exit_code": None, "stopped": None, "refused": None, "argv": argv}
    if hooks:
        record["hooks"] = {"before": failed, "after": None}

    def finish(**fields):
        """Run the "after" hook and write the end record: the time is from before the hook."""
        at = round(time.time(), 3)
        if hooks:
            record["hooks"]["after"] = hook(hooks, "after", inherited, wake)
        write_end(end, {**record, "ended": at, **fields})

    if failed or refused:
        os.waitpid(cli, 0)
        finish(refused=failed or refused.decode(errors="replace"))
        return
    os.close(handle)
    null = os.open(os.devnull, os.O_RDWR)
    for stream in (0, 1, 2):  # the CLI's own from here on: nothing of the watchdog's ever lands in its output
        os.dup2(null, stream)
    os.close(null)

    deadline, signalled, killed = time.time() + seconds, None, False
    look = float("inf") if hasattr(os, "waitid") else LOOK
    try:
        while not ended(cli, wake):
            now = time.time()
            if signalled is None and (asks or now >= deadline):
                record["stopped"], signalled = "stop" if asks else "time", now
                signal_group(cli, signal.SIGTERM)
            if signalled is not None and not killed and (len(asks) > 1 or now >= signalled + grace):
                killed = True
                signal_group(cli, signal.SIGKILL)
            nap(wake, min(look, GIVE_UP if killed else (deadline if signalled is None else signalled + grace) - now))
        # The CLI has ended and is not reaped, so the group's id is still its own. Whatever it
        # started and left behind in its process group goes too.
        if signalled is None:
            signalled = time.time()
            signal_group(cli, signal.SIGTERM)
        give_up = None
        while others(cli):
            if not PROC:
                forget(wake)  # the end of the ps that listed them
            now = time.time()
            if len(asks) > 1 or now >= signalled + grace:
                signal_group(cli, signal.SIGKILL)
                give_up = give_up or now + GIVE_UP
                if now >= give_up:
                    break
            nap(wake, SWEEP)
    except Exception as err:  # never leave a CLI running that nothing is watching
        signal_group(cli, signal.SIGKILL)
        record["error"] = repr(err)
    # The last signal to the group has been sent. Only now is the CLI reaped, and its id let go.
    status = os.waitpid(cli, 0)[1]
    record["exit_code"] = -os.WTERMSIG(status) if os.WIFSIGNALED(status) else os.WEXITSTATUS(status)
    finish()


if __name__ == "__main__":
    main()
