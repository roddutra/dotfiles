#!/usr/bin/env python3
"""The watchdog of one attempt: starts a harness CLI, stays with it until it has ended, and
records how it ended.

launch.py starts one for every attempt of a run or job, in a session of its own, and never
signals a CLI itself. Whatever must not depend on a launcher being alive is done here: the time
limit, the stop, ending the processes a CLI leaves behind, and the record of when and how the
attempt ended. Standard library only, and nothing of the skill is imported: this start-up is
paid once per attempt.

    run_watchdog.py <pid fd> <end record> <seconds> <grace> <command> [<argument> ...]

    pid fd       the attempt's pid file (logs/<run id>.<attempt>.pid), open and locked by the
                 launcher that starts this process
    end record   the file to write when the attempt has ended (logs/<run id>.<attempt>.end)
    seconds      the attempt's time limit: what is left of the run's allowance
    grace        seconds a process gets between SIGTERM and SIGKILL
    command      the CLI and its arguments

The launcher gives this process the CLI's standard input, output and error, its environment and
its working directory, and the CLI inherits them. Once the CLI is running the watchdog lets go
of all three streams, and it writes to nothing but its two files.

What it does, in order:

1. Starts a child that begins a session of its own and waits. The CLI is then the leader of a
   process group that holds everything it starts, in a session without a terminal.
2. Writes the pid file, two lines: "<pid> <start identity>" for itself, then for the CLI. The
   identity is the process's start time (process()), which tells it from a later process that
   was given the same id.
3. Lets the child become the CLI. The lock on the pid file drops when both have closed it: the
   child by becoming the CLI, the watchdog once it knows the child did, or once it has written
   the end record of a child the system refused. So whoever waits for that lock (launch.py
   recorded()) reads about a process that is the CLI, or one that never will be. A child whose
   watchdog dies before step 2 is done never becomes the CLI: nothing runs unrecorded.
4. Waits for the CLI to end, and learns that it has without reaping it (ended()). At the time
   limit, or when asked to stop, it sends SIGTERM to the CLI's process group and, after the
   grace, SIGKILL.
5. When the CLI has ended, for whatever reason, ends what is left of its process group the
   same way: SIGTERM unless the group already had one, what is left of the grace, then SIGKILL.
   A process that left the group by starting a session of its own is beyond its reach.
6. Reaps the CLI, writes the end record in one step, and exits.

The invariant: the CLI, the leader of its group, is reaped only after the last signal to that
group. Until then it is at least a zombie, so its process id, which is the group's id, cannot
have been given to another process or group, and every signal sent here reaches this attempt's
processes or nothing. After the reap the group is never signalled again.

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

Signals. SIGTERM is a request to stop the CLI: launch.py sends it for "stop" and for its own
SIGINT, SIGTERM and SIGHUP. A second one skips the grace, also for a process already being
stopped at its time limit. SIGHUP and SIGINT are ignored, so a terminal that closes or a
Ctrl-C reaches an attempt only as a stop request from its launcher, and never ends the
watchdog before it has written its record. The CLI gets back the signal settings the watchdog
was started with. A watchdog that is killed outright leaves no end record: launch.py then kills
the process group recorded in the pid file if its leader is still running, and otherwise only
names what is left of it (launch.py kill_group()).
"""

from __future__ import annotations

import os
import select
import signal
import sys
import time

PROC = os.path.exists("/proc/self/stat")
SWEEP = 0.02    # seconds between looks at a process group whose leader has ended
GIVE_UP = 5.0   # seconds a process group gets to disappear after SIGKILL
LOOK = 5.0      # seconds between looks at a CLI where os.waitid is missing: see ended()
RESTORED = ("SIGPIPE", "SIGXFSZ")  # ignored by Python at start-up: the CLI gets the system's default


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
    with open(tmp, "w") as f:
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
    handle, end, seconds, grace, argv = int(sys.argv[1]), sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), \
        sys.argv[5:]
    os.set_inheritable(handle, False)  # or the CLI would hold the lock on the pid file for as long as it runs
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
    os.write(handle, f"{os.getpid()} {identity(os.getpid()) or ''}\n{cli} {identity(cli) or ''}\n".encode())
    os.write(go_w, b"\n")
    os.close(go_w)
    refused = b""
    while True:  # ends when the child is the CLI, or has given up
        chunk = os.read(said, 4096)
        if not chunk:
            break
        refused += chunk
    os.close(said)
    record = {"ended": None, "exit_code": None, "stopped": None, "refused": None, "argv": argv}
    if refused:
        os.waitpid(cli, 0)
        write_end(end, {**record, "ended": round(time.time(), 3), "refused": refused.decode(errors="replace")})
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
    write_end(end, {**record, "ended": round(time.time(), 3)})


if __name__ == "__main__":
    main()
