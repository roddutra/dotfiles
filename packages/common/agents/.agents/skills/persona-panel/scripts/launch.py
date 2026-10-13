#!/usr/bin/env python3
"""Start, limit, track and resume a study's runs as headless CLI processes.

Each run is one process of a harness CLI, started through its model entry's runner
(scripts/runners/) under a watchdog of its own (run_watchdog.py). The analysts and the writer of
the synthesis are jobs, started the same way. The launcher stays in the foreground until the
runs it started have ended and prints one line per state change, so put it in the background
with your shell tool, or run it in a terminal. Exit code 0 when every run it was asked for is
done, 1 otherwise.

Usage: launch.py <study-dir> <command> [options]
  plan [--json]                            # what would run, its limits, estimate and ceiling
  pilot                                    # the first persona on each model entry (no --runs)
  run [--runs <ids>] [--allow-missing]     # start pending and failed runs
  resume [--runs <ids>]                    # continue partial and blocked runs
  resume --runs <ids> --extend             # also continue the limited runs named
  run --role analyst [--allow-incomplete]  # plan and start the analyst jobs
  run --role writer                        # plan and start the writer job
  resume --role analyst|writer             # continue blocked jobs
  stop                                     # stop the processes; runs stay resumable
  status [--json]                          # every run and job, its process, time and usage
  usage [--json]                           # what each harness reported; rewrites analysis/usage.md
  check [--runs <ids>] [--force]           # usability: run the success checks again
  release --runs <ids>                     # usability: let go of unfinished runs' accounts
  purge-sessions [--runs <ids>] [--yes]    # delete the study's harness sessions

States, recorded in runs.json (fields in panel_lib.py):
  pending   not started                                      next: run
  running   a process is alive                               next: wait
  done      the persona file is complete                     next: nothing
  partial   the process ended with some sections written     next: resume
  limited   stopped by a run limit                           next: resume --runs <ids> --extend
  blocked   the harness turned the run away: a usage limit,  next: resume, once it takes requests
            a rate limit or a capacity refusal
  failed    the process ended with nothing written           next: run

How it behaves:
- The persona file decides "done", never the exit code (panel_lib.run_state). Only a plain file
  is one: a symbolic link, a FIFO or a folder at its name, or a link at a folder above it, is
  read as no file (panel_lib.persona_bytes), so its run is not done. check_runs.py says why.
- "run" starts only pending and failed runs, and retries a failed one once. "resume" continues
  only partial and blocked runs, in their original sessions. A run with no session to continue
  is started afresh when it has written nothing, and otherwise left for you to decide. That
  covers a session that was never recorded, one that was purged, and one the harness no longer
  has: the resume that finds it gone says "its session no longer exists", and is no attempt.
- A run's limits cover all its attempts: wall-clock time and reported spend add up, a later
  attempt gets what is left, and a run with nothing left becomes limited without starting.
  The budget is passed to harnesses that enforce one. A process stopped at its time limit, or
  by "stop", can end before its harness reports what it spent: that attempt is recorded with
  "usage_reported": false, shown as "not reported (process was stopped)" and never counted as
  zero. It is counted when its session is next resumed and reports its total, so until then the
  attempt that resumes it can be given more budget than is left. When it is a follow-up question
  that brings that total, the total is the stopped process's spend and the follow-up's in one
  figure: it is recorded as unallocated, counted in the totals and in neither's own figures.
- Every attempt has a watchdog process, which outlives the launcher. It starts the CLI, and at
  the attempt's time limit sends the CLI's process group SIGTERM, gives it --grace seconds to
  finish its write, then SIGKILL. So a time limit holds whether or not a launcher is alive.
  When the CLI ends, whatever it started and left running is ended the same way. The watchdog
  then records the end time, the exit code and why it stopped the process, and the launcher
  settles the run from that record: time used is the process's real duration.
- A usage limit, rate limit or capacity refusal stops new launches on that runner only, with the
  harness's own message as the reason. Its queued runs stay as they are.
- A process that exits with an error before printing anything never ran as the CLI: a sandbox
  that lets the CLI start and then refuses what it needs ends this way. No attempt is recorded
  and nothing is marked failed. The launcher prints the command and the CLI's message, starts
  nothing more on that runner in this command, and names the two ways out of a sandboxed shell
  tool (panel_lib.SANDBOX_HINT): ask the harness to run the command outside its sandbox, or
  run launch.py from a terminal. A run whose CLI started, printed and then failed is failed,
  and retried once.
- A process whose output shows that no run of its CLI can work from this shell (its runner's
  parse_result() says "cannot_run": the CLI could not build its own sandbox, or could not reach
  its provider) is not retried, and nothing more starts on that runner in this command: the
  next would spend the same time and tokens to end the same way. The attempt stays on record,
  with its usage and its session, which may hold the materials and can be purged. The run is
  failed with the CLI's own words as the reason, and the launcher names the two ways out once.
- Before anything starts, every runner needed is checked: installed, signed in, options still
  accepted (its check()), and able to do a run from this shell at all (its shell_check(): the
  directory where its harness keeps sessions can be written, and whatever else the runner knows
  its CLI needs, such as a sandbox of its own). So is the study directory, which must take a
  file. Neither check makes a model call or tests the network. If a runner fails nothing
  starts, unless --allow-missing, which leaves its runs alone. A runner that this shell cannot
  run is refused by name, with what it cannot do here and the two ways out. Nor does a run
  that may browse start while the agent-browser CLI is not on PATH: "plan" names that as a
  problem, and "run", "pilot" and "resume" refuse.
- A run whose process ended in a session that its harness did not keep (parse_result() says
  "session_saved": false, as where the harness could not write its own folder) is said once,
  when the attempt ends: "session not saved: this run cannot be resumed or asked a follow-up".
  The session is noted on the run ("unsaved"), "status" shows the same words, "resume" starts
  the run afresh when it has written nothing and otherwise leaves it alone, and followup.py
  refuses it. A failed run is not noted: "run" starts it in a new session anyway.
- No panellist run starts while a concept of the study has nothing captured under
  panel/materials, or is short of a page, state or item: "run", "pilot" and "resume" name the
  concepts, what each lacks and capture.py, as "plan" does. Analyst and writer jobs do not read
  the materials and are not held back.
- One launcher per study (.launch.lock). The lock file is opened without following a symbolic
  link and without waiting: a link or a FIFO left at its name is no lock, "status" then shows
  no launcher, and a command that needs the study refuses in a sentence until the lead has
  deleted it. The file is the study's from its scaffold on (init_study.py), and no command
  removes it: a launcher that ends empties the record it wrote there and leaves the file, so
  the next launcher and every command that reads lock the same one. A file that is empty names
  no launcher. One that still names a launcher which is gone was left by a launcher that was
  killed: the next says "Cleared a stale lock" and writes over it.
  Whether a launcher has the study is what the lock says, from whatever shell it
  is asked: "status", "plan" and "stop" ask with a shared lock that is not waited for and is
  let go at once (taken()), and a launcher that finds only such a lock in its way asks again,
  so none of them can turn a launcher away. A shell in another process namespace, as inside a
  harness's sandbox, sees the lock and no process of the study. "status" there says "Launcher:
  running" with the command and process id on record, then one line: this shell cannot see
  the launcher's processes, and run states are as last recorded. It says nothing of any run's
  process or browser session, and calls no run gone. "stop" there signals nothing and says
  where to run it, and a command that needs the study is refused as anywhere. So "Launcher:
  not running" means the same in every shell. The launcher records the process namespace it
  runs in beside its process id, where the system names one (run_watchdog.py namespace()): a
  process of another namespace that holds that id, under that start identity, is not taken
  for the launcher and is never signalled (Lock.holder()).
  Processes outlive the launcher and write to <study>/logs/, so a launcher that
  was killed loses nothing: the next one settles the runs
  that have ended, from their end records, and adopts the ones still alive, without starting a
  duplicate. Each watchdog records itself and its CLI in <study>/logs/ before the CLI runs, so
  a run is found even when the launcher died before noting it in runs.json.
- No launcher settles, stops, starts again or scaffolds over a run that is alive where it
  cannot look. With no launcher there is no study lock to tell by, so each attempt has a lock
  of its own: its watchdog holds logs/<run id>.<attempt>.lock for as long as it lives, and the
  system lets go of it when the watchdog ends, however it ends (run_watchdog.py, "The lock of
  an attempt"). Every shell sees that lock, whatever processes it sees, and it is asked as the
  study's is (taken()). A run in flight whose watchdog holds its lock and is not to be seen
  under the id it recorded is out of sight (unseen(), out_of_sight()): alive, in another
  process namespace than the shell's. "status" there shows its process as "unseen", says
  nothing of its browser session, does not call it gone, and prints the line it prints of a
  launcher it cannot see. Every command that takes the study (run, pilot, resume, stop, check,
  release, purge-sessions --yes, followup.py ask, init_study.py --force, archive.py) leaves
  the lock as it found it, changes and signals nothing, and exits with 1, naming the runs and
  the two ways out of a sandboxed shell tool (Lock.acquire()). "followup.py list" lists, and
  settles nothing. Where the study cannot be written either, as in a sandbox that shows it
  read-only, no command is given the lock, and each that needs it says so of the lock file.
  archive.py goes on without it there, for a round that was archived read-only, and keeps a
  shared lock on the lock file in its place until the round is copied (Lock.share()): no
  launcher is given the study meanwhile, so none can start a run under the copy, and one that
  tries says after ASKING seconds that the study is being read, and to try again. Under that
  lock the locks of the watchdogs are asked all the same, which a descriptor that only reads
  can do, and the archive is refused in the same words (Lock.blind()). A study at rest has
  that file to share, as it is never removed. Where there is none all the same, in a study
  from before the scaffold made one that no command has taken since, or flock cannot tell,
  nothing keeps a launcher away: archive.py then copies only a study with no run on record as
  running, and refuses any other.
- A lock that is free is a watchdog that has ended, in whatever namespace it ran: the run is
  then any launcher's to settle, from its end record or as one whose watchdog was killed. So a
  launcher that was started inside a sandbox and killed with it, watchdogs and CLIs and all,
  holds no study up: the next command from any shell settles its runs. One thing is left that
  a launcher then cannot do. Each watchdog records the process namespace it runs in, where the
  system names one (run_watchdog.py namespace(): Linux does, macOS does not). When a watchdog
  has gone without an end record and that namespace is not the shell's, the ids on record
  name no process here, or someone else's: the launcher looks none of them up and signals
  nothing, settles the run as one whose watchdog was killed, and says, in a line and in the
  run's reason, that its CLI could not be checked from this shell because it ran in another
  process namespace (elsewhere()). Its browser session is stopped by its socket alone: the
  daemon and the browser on that session's record are ids of the same namespace, and are not
  looked up or signalled either (Supervisor.browser_left()). That is all the namespace a
  watchdog records is for: it never keeps a command from the study.
- An attempt with no lock file is from before watchdogs held one, and one whose lock cannot be
  asked is on a file system without locks: either is looked for by the process ids on record,
  as it always was.
- The CLI's standard input, output and error of an attempt are logs/<run id>.<attempt>.in,
  .out and .err. Each is made anew and handed to the process by descriptor, and read back
  without following a link or waiting, so a link or a FIFO put at one of those names neither
  redirects a CLI's output nor holds a launcher up: it is unlinked before the attempt, and
  read as nothing written after it.
- A watchdog that was itself killed leaves no end record. The launcher then kills its CLI's
  process group if the CLI is still running. If the CLI has gone and a group of its id still
  has processes, the launcher cannot prove they are the run's: it leaves them alone, names
  them, and "status" keeps naming them until the run next starts. Where no list of processes
  can be had, from /proc or from ps, it says that it could not check the group: it never
  takes "cannot tell" for "nothing left". Either way the attempt is charged from its start to
  now, and no further than the time it was allowed: the most it can
  have used, so the run gets no time past its limit. A watchdog that was killed while it was
  still starting the attempt's browser session left that command on record in the pid file
  (run_watchdog.py, "Hooks"). The launcher ends it first, by the same rule, and only then stops
  what it had started of the session: the CLI was never executed, so the run "could not be
  started" and nothing is marked failed.
- A run that may browse (study.json "browse", on a runner with a browser) gets an agent-browser
  session of its own for each attempt (browser_session.py). The attempt's watchdog starts it
  before the CLI and stops it after, however the attempt ends, so the run only sends it commands
  and nothing of it outlives the run. The launcher gives the runner what the process needs in
  its environment to reach the session (run["browser_env"]). The session's working directory is
  the run's, its viewport the study's capture.desktop, and its action policy refuses what a
  visitor could not do. Its record is logs/<run id>.<attempt>.browser, its policy .policy, and
  what its start and stop printed .hooks: the launcher passes the attempt's log base, and both
  names follow from it. When the session cannot be started the CLI never runs:
  the run "could not be started", with the reason, nothing is marked failed, and nothing more
  starts on that runner in this command. A resumed run gets a new session, on a blank page, and
  its resume message says so. Starting a session takes about half a second, and the launcher
  waits for it, because a run's process is on record only once its session is there. A watchdog
  that was killed stops no session, and one holds about 330 MiB: the launcher that settles the
  attempt stops it, says so, and "status" shows what it found. A session on record that no
  attempt with a live process owns is stopped by the next launcher of any command. Whoever
  stops a session, what could not be ended or was left in place is on its record, said by the
  launcher that settles the attempt, and shown by "status": a process that could not be
  ended, a directory that nothing proves to be the session's, a second session in its socket
  directory whose process the system does not name. A record that cannot be trusted (a symbolic
  link, a FIFO or anything else that is no regular file of this user, or not what the start
  wrote) is refused before it is read or waited for: nothing of its session is stopped or removed,
  and every launcher says so until the lead has looked and deleted it. "status" shows "browser
  session up" for a running run.
- "stop" asks the launcher that has the study to stop, and the launcher asks each watchdog,
  which stops its CLI as at a time limit. With no launcher alive, "stop" asks the watchdogs
  itself. SIGINT, SIGTERM and SIGHUP to the launcher do the same, and a second one skips the
  grace. A launcher started with SIGHUP ignored (under nohup) leaves it ignored and carries on.
  In a usability study "stop" stops the runs even when a command of the study that an earlier
  launcher left cannot be proved gone, where every other command exits at once (below): it
  stops them first, starts no command of the study, then says what holds the study up, on
  stderr, and exits with 1.

Usability studies ("type": "usability", panel_lib.py). Every run browses, nothing is captured,
and a run is done when its persona file has a scored section for every task and the final
sections. What is added for them:
- The time limit of a run, when study.json sets no limits.run.minutes, comes from its tasks
  (panel_lib.usability_minutes), and the plan prints it.
- The step limit of a task counts complete steps, and the panellist keeps to it itself: at the
  limit it records "ran out of steps" and goes on to the next task. The launcher is the backstop.
  While a run is in flight it reads the run's step log each time the log has changed, and an
  "intent" entry this attempt added that begins a step beyond its task's limit stops the run:
  one with a step number above the limit, or one intent more for the task than the limit
  allows (panel_lib.steps_begun). The attempt number an entry carries decides nothing: it is
  the launcher's to issue, so an entry under a number of the panellist's own is one more step
  of the task and starts no count again, and a line that is no entry of a step hides none. The
  count is the launcher's own, on record in the attempt ("steps") and never under panel/, and
  it only goes up: a log that is emptied, cut short or changed where the launcher had read it
  is noted there and said once, and what it holds from the first changed line on is counted on
  top of what was counted (Supervisor.over_steps()). The log is never read through a symbolic
  link. A run with no log yet has begun no step, but a log that is there and cannot be read as
  the run's own (a link, a FIFO, a file or folder that may not be read) would leave the run
  with no backstop, so it stops the run too, as limited with "limited_by": "steps" and the
  reason "step limit: its step log cannot be read as the run's own (<why>), so its steps
  cannot be counted". It is a backstop and no more: it counts the steps a log shows while a
  launcher is running, and a panellist that logs none is bounded by the time limit alone. The
  launcher notes the decision in the attempt ("stop": the task, the step and the limit, or
  why the log could not be read) and only then asks the attempt's watchdog, which stops the
  CLI as at a time limit, with the grace. The run becomes limited with the reason "step
  limit: task T2, step 26 of 25" and "limited_by": "steps", keeps everything it wrote, is not
  restarted by "run", and
  is continued with "resume --runs <id> --extend" like any limited run: the task that was under
  way starts again as a new attempt in the step log, counted from 1. The end record of a watchdog
  says only that it was asked to stop, so the reason is the decision on record: a launcher
  killed after asking loses nothing, the next one settles the run as limited for it, and one
  that finds the decision with the process still alive after the grace asks again. A time
  limit that comes first stands as the reason. Nothing else in a step log stops a run: a line
  that is no entry, an entry for a task the study does not have, an entry with an attempt
  number the launcher did not issue and a step number that goes backwards are said once when
  the attempt ends, and are extract_scores.py's to record. What such a line repeats of the
  panellist's own text, a task id the study does not have, is shown as panel_lib.shown()
  allows: a value that holds a known secret is described, never printed.
- A run that is started afresh begins with evidence that is only its own. Every start that is
  not a resume is a new session ("run" on a failed run or on one that "stop" left pending, the
  retry of a failed run, the restart of a run whose session is gone), which logs each task as
  attempt 1 and names its screenshots as an earlier session did. So the launcher first moves
  what the run's evidence folder held to logs/<run id>.<attempt>.evidence, named for the last
  attempt the run had, makes the folder anew, says so, and takes the run's "task_attempts"
  off its entry. Nothing is deleted: what is set aside is the lead's, is never read as
  evidence, scanned or archived, and is put back when the attempt never runs as the CLI
  (Supervisor.set_aside()). A resumed run keeps its evidence folder as it is.
- A harness's own message, which the launcher prints when a CLI fails and keeps as the run's
  reason, can hold a secret of a test account that the panellist read or typed. One that
  holds a secret a scan knows (panel_lib.secrets_in()) is neither printed nor kept, in
  runs.json or followups.json: the reason says that the harness's message is withheld
  because it holds a secret of a test account, and names logs/<run id>.<attempt>.err and
  .out, which have it. A message with no known secret is repeated as it is, as is every
  message of a review study (Supervisor.repeated()).
- Success checks (accounts.py). When a run reaches a final state, done, limited or failed, the
  "success_check" of each task that has one is run for it, before its account is torn down:
  without a shell, from the study directory, with the run id as its last argument. Exit code 0
  says the task was really completed and 1 that it was not. Any other code, a check that cannot
  be run and one that does not end in time are "failed to run": no verdict, said in capitals,
  and never counted as not completed. Each task's record goes to the run's entry under "checks"
  (checked, exit_code, at, error). No check is run for a partial, blocked or pending run, or
  for a failed run about to be retried, and the records of a run that is continued are dropped
  when it starts, so its checks run again when it next finishes. One exception: a run that is
  resumed with a new account from accounts.provision ("resume --extend", "resume --released")
  keeps the record of each task it has already written up, marked "kept", through every later
  attempt, because it does not attempt that task again and the account the record was made
  with is gone. A launcher killed before the checks ran leaves them to the next command that
  settles runs, while the run's account is still in force. What a check printed is the lead's
  alone: a check that failed to run is said with its exit code and the file its output is in
  (accounts/<run id>.check-<task id>.output), never with a word of it. "check" runs them
  again by hand, for
  every run in a final state or the ones --runs names, as after mending a check, and replaces
  each record it makes. It keeps a verdict whose account is gone (accounts.teardown removed it,
  or the record is marked "kept"), because a check run then judges the run without what the
  run did, and says so for each task: "kept: the account is gone, so the check cannot be run
  again". With --force it runs that check all the same and says that the earlier verdict was
  replaced. A task with no verdict on record, or with "failed to run", is tried either way.
  "release" keeps a "kept" record the same way. A check is the lead's: nothing of it is
  written under panel/. extract_scores.py and analyze.py report each panellist's own claim
  beside it.
- No run starts while a "success_check" or an accounts command names a file that is not there,
  or on a runner that cannot drive a browser: "plan" names both as problems.
- Accounts (accounts.py). A run with study.json "accounts" is given its test account just
  before its first attempt starts: the provision command is run for it once, with the run id,
  or its entry of accounts.map is taken. The whole account goes to <study>/accounts/<run id>.json,
  lead only, and the panellist gets panel/scratch/<run id>/account.json with the identifiers and
  no secret. When the account names a saved browser state, every attempt's browser session
  starts from a private copy of it (logs/<run id>.<attempt>.state, which the session deletes),
  so the run starts signed in. With accounts.signin "panellist" the state is not loaded and the
  panellist is given the secrets to type: the run's entry then says "secrets_given" for good.
  The launcher waits for the provision command, as it waits for a browser session. When it
  fails the run "could not be started", nothing is marked failed, and no further run is
  started in this command.
- What a command of the study wrote (accounts.provision, teardown, reset, a success check) is
  never printed, put in runs.json or shown by "status": a script that fails often prints what
  it was working with, a password included. A failure is said with the exit code and a fixed
  sentence, and what the command wrote is in <study>/accounts/<run id>.<command>.output, mode
  0600, which the message names. What accounts.provision prints is the account itself: it
  goes to the account's record, also when it cannot be read as an account.
- One command of the study runs at a time, on record in accounts/command.running with its
  process and that process's start identity from before it runs. A command outlives a launcher
  that is killed, so every launcher command first sees to one left on record: still running,
  it is ended with its process group (SIGTERM, --grace seconds, SIGKILL) and waited for, and
  either way it is taken as unfinished. A provision is then cleared up with accounts.teardown
  before the run is provisioned again, a teardown is done again, and a reset or a check runs
  again when next due. No two commands of a study ever run side by side. A command that left
  a process which nothing proves gone, or one on a system with no list of processes to prove
  it by, stops every launcher command with what to do (accounts.py): only "stop" does its
  work first, and it starts no command of the study while that holds, so the success checks
  and teardowns of the runs it settles stay due for the next launcher command. A command
  holds a lock of its own while it or anything it started lives, on accounts/command.lock,
  and its record names the process namespace it was started in. Of a command recorded in
  another namespace than the shell's no id is looked up or signalled, as of a run's, and the
  record is never cleared from there, whatever the lock shows: a lock that is free is no
  proof that a command which may have closed its descriptor has ended. Every launcher command
  stops and says to run it from the shell that started the command, and, with the lock free,
  what to delete when that shell was in a sandbox that has ended (accounts.py, "The lock of
  a command"). That is the one place where a study waits for the lead after a sandbox ended.
- Teardown. When a run reaches a final state, done, limited or failed, its account is let go,
  after its success checks:
  accounts.teardown is run with the run id, the secrets are taken out of the record and of the
  panellist's account.json, and a state file the provision command made is deleted. A partial,
  blocked or pending run keeps its account for when it continues. It happens once for each
  provisioning: a run that is continued afterwards ("run" on a failed one, its retry, "resume
  --extend" on a limited one) is provisioned again first. A launcher that was killed, or
  stopped, before it could do this loses nothing: every launcher command that settles runs
  ("run", "pilot", "resume", "check", "stop" with no launcher alive, and a follow-up) lets go of the
  account of every run it finds in a final state with one still in force. A teardown that
  fails is said in capitals, kept on the run's entry ("account", "teardown_error": the exit
  code and the file the command's output is in) and shown by "status", and the next such
  command tries again: a command tries once for each run. An account that is owed a teardown
  is never carried on with. A failed run whose teardown fails is not retried and stays failed,
  and a later "run", or "resume --extend" of a limited one, tears the account down first and
  only then provisions and starts: while the teardown still fails the run is not started, and
  the command exits with 1. A teardown that was cut short, by a kill between its command and
  the files it clears, is on the account's record ("cleanup") and is done again from the
  start by the next launcher command, whatever state its run is in.
- "release". A partial, blocked or pending run keeps its account until it is continued and
  finishes, and nothing else ends that: the credentials keep working, and archive.py refuses a
  study with an account in force. "release --runs <ids>" is for the runs the lead will not
  continue. For each run named that has an account in force and no process: its success checks
  are run first, as for a run that finished, because nothing can tell afterwards what the run
  got done (a task it never reached reads "not completed", and the analysis counts no attempt
  for it); then its account is torn down, once; and its entry gets "released", the time. A run
  that is running is refused, a run with no account in force is said to have none, and a study
  without accounts has nothing to release. A released run keeps its state and everything it
  wrote. "run" and "resume" then leave it alone and say so: to continue it after all, name it
  with --runs and --released, which gives it a new account and takes the mark off. A teardown
  that failed is tried again by the next launcher command, as for a finished run. "status"
  shows "released by the lead".
- "sequential": true starts one panellist run at a time, whatever the runners' concurrency.
  accounts.reset, when the study has one, is run before a run's attempt whenever another run
  has used the product since this one last did: before every launch, retry and restart but
  the study's first, and before a resume unless this run was the last to run.
- A resumed run's message (runs.py) names the tasks written and the tasks left, says that the
  browser was restarted, and gives a task that was under way its next attempt number for the
  step log: the number is put on the run's entry first ("task_attempts"), and no other
  counts. It says that the test account is the same one, or, when the run was provisioned
  again for this attempt, that it is a new one with nothing of the first in it, to be read
  again from account.json. A follow-up question to a usability run gets no browser session:
  its account is gone, and it answers from what it saw (assets/usability-followup-message.md).
- The analyst and writer jobs run as for a review, from briefs of their own:
  assets/usability-qual-brief.md, which gives an analyst each run's persona file with its
  evidence folder (panel/evidence/<run id>/: the step log and the screenshots), and
  assets/usability-synthesis-brief.md. Their follow-up notes are the two assets of those names
  with "-followups".

The plan. "plan" starts no run, makes no model call and changes no file of the study. It asks
each runner whether its CLI is signed in, and a harness may refresh its own login when asked.
It also asks whether this shell can run each CLI, and tests the study directory with a write
that leaves nothing behind.
It works before init_study.py and capture.py have run, and says what is missing. It prints:
- every run with its persona, model key, runner, model, effort, limits in force and prompt file
- what each run can read under panel/materials (pages, images, bytes), and which provider
  receives it through which model entries. A PDF is counted as a PDF with its pages, and an
  image as an image: the page images of a PDF and the parts of a tall image are not counted
  again. In a study with a "url" or "files" concept
  (panel_lib.py, "Concept kinds") the figures are per concept with its kind, and the plan also
  says: when each live page was captured, and that the materials show it as it was then; whether
  panellists may browse, and if so that one who opens a live page sees it as it is at review
  time; the external hosts the instructions send panellists to, the ones on this machine, and
  that nothing limits the browser to them; and which concepts have nothing to open. In any study
  whose runs may browse: that each such run in flight holds a browser session of its own, about
  how much memory that is with the concurrency in force, and what the session refuses. A concept
  with nothing captured or short of a page or item, a concept folder under panel/materials that
  belongs to no concept, site copies left where the other "browse" setting put them, and
  Poppler missing while a PDF is still to be captured are each named
- a note when every persona reviews in the same order (panel_lib.shared_order), as
  init_study.py warns: order is then confounded with concept, and another "seed" fixes it
- what each model entry's runner lacks (images, a budget cap, resume, a browser while the study
  allows browsing, an effort setting, which usage figures), how far a run can pass its budget
  cap, what the runner could not switch off (with what browsing opens only where the study's
  runs can browse on it), and any variable set in your environment that can change who is
  billed (names only)
- whether each runner's CLI is installed and signed in, and whether it can do a run from the
  shell the plan was made in: one that cannot is shown as "CANNOT BE USED" in place of
  "ready", with what it cannot do here and the two ways out, and stops the plan as it stops
  "run". A plan made in another shell than the one that will run the panel says nothing of
  that one
- a problem when this shell cannot write to the study directory: no run can start from it
- what a runner can tell of each model entry without a model call (model_status): a model
  its harness does not have, one whose provider is not signed in and, in a full-materials
  study, one that reads no images each stop the plan and "run"
- for a usability study, in place of the materials: the target, each task with its step limit
  and success check, that the launcher is the backstop of a step limit, when the success checks
  run and what their exit codes say, the time rule and the accounts
- a problem when a run may browse and the agent-browser CLI is not on PATH: every such run
  would end as "could not be started"
- the analyst and writer jobs with their share of the synthesis pool, or which of
  synthesis.analyst and synthesis.writer is missing
- an estimate of what the runs still to go will use. For a model key with finished runs it is
  the mean tokens, cost and time those runs reported, times the runs to go, so a pilot gives the
  next plan a measured baseline. A finished run whose reported usage is known to be short (a
  process of it was stopped before reporting, or its usage came in one total with a follow-up's)
  counts for the time only, and the plan says how many were left out of the tokens and cost: a
  run measures the same whether or not it was asked a follow-up. A harness that reports no cost
  gets "cost not reported" and is judged by time. A key with no finished run gets tokens from
  the method's figure per concept page, times what a run opens (each web page, each page of a
  PDF and each supplied image counts as one), and no dollar figure: a rough forecast. The "In
  all" line sums the figures there are, and names the model entries each sum leaves out (the
  analyst and writer jobs, until one has run)
- a ceiling: every enforced budget cap once, plus the synthesis pool once. It is a guaranteed
  maximum only when every run and job is on a runner that enforces a cap. Otherwise it is
  labelled an estimate, the runs without a cap are left out of it, and the time limit is what
  bounds them. Its caveats say how the capped part can still be passed: what a runner states
  about its cap (one checked after each turn can be overshot by a turn), and the unreported
  spend of stopped processes, with the attempts concerned. In --json, "ceiling.label" is
  "guaranteed maximum" or "estimate" and "ceiling.caveats" lists them. After "resume --extend"
  the ceiling no longer holds, and the plan says so
- dollar figures are list-price equivalents under a subscription login
Exit code 1 when a runner cannot be used, when this shell cannot run it or write to the study
directory, or when study.json asks a runner for something it cannot do: an effort it does not
have, or a study with "materials": "full" on a runner that cannot open images. "run" refuses to
start those runs for the same reasons. On a native-mode study it lists the runs and says that
native mode has no limits, usage record or isolation.

A text-only study ("materials": "text"). Its runs get no browser access, whatever "browse" says,
and a runner that cannot open images is welcome. The plan says that panellists receive the page
text only and which factors they do not score, and notes what the setting overrode in study.json:
a factor named in "fit_factors" that is not scored, and "browse": true. The analysts' and the
writer's briefs say that panellists read text only (assets/qual-brief-text.md and
assets/synthesis-brief-text.md, in place of <TEXT_ONLY_NOTE>).

The usage record. After every process that ends, the launcher rewrites analysis/usage.md from
what the harnesses reported: per run, per role, per model key and in total, with "not reported"
where a harness gave no figure, "not reported (process was stopped)" where the launcher stopped
the process first, and "unallocated" where a follow-up reported one total for itself and for such
a stopped process of its run. "usage" rewrites and prints it.

Sessions. "purge-sessions" deletes the harness sessions recorded for the study's runs and jobs,
through each runner's own delete command. Without --yes it prints each run, session id and
command, and deletes nothing. It cannot be undone and it ends resume for those runs, so it is
refused while a launcher has the study or a run is recorded as running. A runner that cannot
delete a session leaves it in place, and is listed. Each deleted session is recorded on its run,
so "resume" says the session was purged and "status" shows it. The usage it reported is kept.
Without --runs it also covers the sessions of an earlier scaffold: the ones init_study.py --force
carried over to logs/earlier-sessions.json when it replaced runs.json (panel_lib.py). Each is
taken off that record as it is deleted, and "status" and "plan" say how many are left on it.

The modification record. Each time a process starts or ends, the launcher hashes every persona
file and notes in logs/modifications.json any file that changed while its own run was not
running and others were. check_runs.py reports those as a panellist writing outside its file.

Analysts and the writer, set in study.json:
  "synthesis": {"analysts": 2, "analyst": {"runner": "<runner>", "model": "<model>"},
                "writer": {"runner": "<runner>", "model": "<model>"},
                "decision_maker": "the founders", "context_files": ["background.md"]}
- "analyst" and "writer" are model entries like those in "models". There is no default: a role
  without its entry is refused. "analysts" is 1 (the default) or 2. "decision_maker" is who the
  synthesis is written for, and "context_files" are extra files for the jobs to read, relative
  to the study directory. Both are optional. The study brief (study-brief.md) is refused as a
  context file, under any name: it holds the team's hypotheses.
- "run --role analyst" plans the jobs analyst-1 and, with two analysts, analyst-2: it adds them
  to runs.json and writes each one's brief to prompts/<job id>.md, from assets/qual-brief.md
  with every placeholder filled. Two analysts split the personas into halves by persona id, so
  each reads every model of its personas. "run --role writer" does the same for the job writer,
  from assets/synthesis-brief.md. A usability study has briefs of its own (above). A job that
  is pending or failed is planned again each time, so a change to study.json reaches it.
  "status" plans nothing.
- Order. Analysts are refused while any panellist run is pending, running or blocked, unless
  --allow-incomplete. Every run that did not finish is named in the analyst's brief with its
  state, to be read as partial evidence. The writer is refused until every analyst job is done.
  Read the analysts' files before you start it. Both are refused while a follow-up question is
  not settled: a persona file may then hold what settling will put back.
- A job works in the study directory, does not browse, and writes one file: analysis/qual-<n>.md
  or analysis/SYNTHESIS.md. It is done when that file exists and is not empty. Its final reply
  is saved to analysis/<job id>-reply.md, and becomes the output file when the process ended
  well without writing one. When a job ends, the launcher adds the synthetic panel notice
  (panel_lib.NOTICE) to its output file if the job left it out: under the file's title. With
  no file a job is failed (and "run" retries it once), blocked or limited, never partial.
  "resume" continues a blocked job in its session.
- Jobs run under limits.synthesis, apart from the run limits: its minutes for each job, and its
  budget_usd as one pool divided equally among the analysts and the writer, each share a cap.

Follow-up questions. followup.py asks them, through the supervisor here: a follow-up is one more
attempt on a finished run, of kind "followup", which resumes the run's session under the study
lock and a watchdog, within its runner's concurrency.
- It has an allowance of its own, limits.followup (5 minutes and $0.50 unless study.json says
  otherwise), for each run and each question. The run's own limits, time and spend are not
  touched, and the plan's ceiling does not include follow-ups: "plan" and "status" say how many
  were asked, and the usage record lists what they used under the role "follow-up".
- It never changes the run: "state" stays as it was, and the attempt in flight is known by being
  the last one, with no end. Before the process starts the persona file is copied to
  logs/<run id>.<attempt>.before. When it has ended, the file must be that copy plus one
  appended "## Follow-up <n>" section (panel_lib.followup_change). Anything else is rejected:
  the file is put back from the copy, and what the panellist wrote is kept in
  logs/<run id>.<attempt>.rejected.md. A file that can no longer be read as the run's own is
  rejected too, with nothing kept of what a link points at. A process that replied without
  writing has its section written from the reply. The file is written through no symbolic link
  (panel_lib.write_persona): where it cannot be put, the launcher stops and says so, with the
  decision on record for the next command. The outcome goes to followups.json (format in
  panel_lib.py).
- Settling is in steps, each on record before the next: the decision, then what it does to the
  file, then the outcome, then the attempt's end in runs.json, then the copy is deleted
  (panel_lib.py, "Settling"). A launcher killed between two of them leaves a state that the next
  one brings to the same end: it carries out a decision it finds and never decides again, so a
  rejected follow-up whose file was already put back cannot be read as a reply to write in.
- Until the attempt's end is in runs.json, nothing reads the persona file for scores or progress:
  "status", the extract scripts and check_runs.py read the copy made before the question
  (panel_lib.read_persona) and say so in a line for each such run. So the run shows as done with
  all its sections while the question is out, and nothing a follow-up changed reaches a CSV.
- A follow-up that a launcher did not live to settle is settled by the next launcher of any
  command, the same way, and by "followup.py list" when no launcher has the study. A run that
  was still queued when its launcher was killed is then recorded as "not asked". "stop" stops a
  follow-up as it stops a run. A harness that turns the request away closes its runner for the
  command, as does a CLI that shows it cannot do a run from this shell, and a CLI that cannot be
  started, or a session that is gone, is no attempt. A run whose session was not saved is
  refused before anything starts.
- An analyst's brief names the follow-ups answered by its personas, and the writer's names them
  all, each saying that the answers are qualitative only and are cited as prompted
  (assets/qual-brief-followups.md and assets/synthesis-brief-followups.md, in place of
  <FOLLOWUPS>). So ask before the analysts are planned.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import accounts  # noqa: E402
import browser_session as browser  # noqa: E402
import launch_plan as planning  # noqa: E402
import panel_lib as pl  # noqa: E402
import run_watchdog as watchdog  # noqa: E402
import runners  # noqa: E402
import runs as tracker  # noqa: E402

LOCK = ".launch.lock"
NAMING = 0.05  # seconds a launcher that has just taken the lock gets to write its name over the one it found there
ASKING = 5.0   # seconds a launcher keeps asking for a lock that only a command which asks is holding (taken())
# What a command says when a launcher has the study and its processes are not to be seen (Lock.holder()), and
# what "status" says when runs that no launcher has are alive and not to be seen (unseen()).
UNSEEN = "This shell cannot see the launcher's processes, as inside a sandbox"
STATES = ("done", "running", "pending", "partial", "limited", "blocked", "failed")
STARTS = {"run": ("pending", "failed"), "pilot": ("pending", "failed"), "resume": ("partial", "blocked")}
MIN_BUDGET = 0.000001  # in dollars: less than this left is nothing left, and no harness takes a smaller cap
TURNED_AWAY = "the harness is turning requests away"  # a usage limit, a rate limit or a capacity refusal
LOST = "its session no longer exists"  # a resume found it gone from the harness
NOT_SAVED = "its session was not saved"  # its runner found that the harness had kept none when its process ended
UNSAVED = "session not saved: this run cannot be resumed or asked a follow-up"  # what "status" shows of such a run
# Why a runner starts nothing more in a command: a process of it showed that no run of its CLI can work here.
NO_RUN_HERE = "its CLI cannot do a run from this shell"
ENDINGS = {"usage_limit": "its harness turned its request away", "budget": "its process reached its budget",
           "error": "its process ended with an error"}
# Added to the resume message of a run that may browse: each attempt has a browser session of its own.
BROWSER_RESTARTED = (" Your browser was restarted: it is on a blank page again, so open the page you need before "
                     "you act on it. The rules for the browser are unchanged.")
REPLAY = 2.0  # seconds past the grace before a launcher repeats a stop request that an earlier one put on record
VERDICTS = {True: "completed", False: "not completed"}  # what a success check's record says of its task
NEXT = {"pending": "run", "failed": "run", "partial": "resume",
        "blocked": "resume, once the harness takes requests again",
        "limited": "resume --runs <ids> --extend, which gives one more allowance of the limits"}


def say(*lines: str):
    print(*lines, sep="\n", flush=True)


def clock(epoch) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(epoch))


agree, plural = pl.agree, pl.plural  # number agreement, the same in every script


def duration(seconds: float) -> str:
    return f"{seconds:.0f}s" if seconds < 90 else f"{seconds / 60:.1f} min"


def step_reason(stop: dict) -> str:
    """Why a run was stopped at a task's step limit, from the decision on record in its attempt
    (Supervisor.step_limit()): the task, and the step it began beyond the limit. With "unread",
    why its step log could not be read as the run's own: its steps could then not be counted."""
    if stop.get("unread"):
        return (f"step limit: its step log cannot be read as the run's own ({stop['unread']}), so its steps cannot "
                "be counted")
    return f"step limit: task {stop['task']}, step {stop['step']} of {stop['of']}"


MARK = 16  # hex digits in the mark of a line of a step log: what the backstop knows a line it has read by


def marks(lines: list[str]) -> list[str]:
    """The mark of each line of a step log, which tells whether the line is still as it was read."""
    return [hashlib.blake2b(line.encode("utf-8", "replace"), digest_size=MARK // 2).hexdigest() for line in lines]


# ---------------------------------------------------------------- processes

# What start() runs for every attempt: the attempt's watchdog (run_watchdog.py), which starts
# the CLI, stops it at its time limit or on request, and records how it ended. -I keeps the
# working directory, where panellists write, off the import path.
WATCHDOG = [sys.executable, "-I", str(Path(__file__).resolve().with_name("run_watchdog.py"))]
identity = watchdog.identity


def alive(pid, started) -> bool:
    """Whether the process recorded as (pid, start identity) is still running."""
    found = watchdog.process(pid) if pid and started else None
    return bool(found) and not found[0].startswith("Z") and found[1] == started


def recorded(pid_file: Path) -> dict | None:
    """What an attempt's watchdog recorded in its pid file: {"watchdog", "cli"}, each a
    (pid, start identity) pair. None when no watchdog got as far as recording itself, and then
    no CLI ran either: the process that becomes the CLI waits for that record. With "hook", the
    same of its "before" command, when the watchdog was killed while that ran: the CLI was then
    never executed, and the command may still be running (run_watchdog.py, "Hooks"). With
    "namespace", the process namespace the watchdog said the attempt runs in, where the system
    names one: the ids mean these processes only to a shell in it (elsewhere()). And "lock",
    the path of the attempt's lock file, which that watchdog holds a lock on for as long as it
    lives (unseen()): the file beside this one, whether or not it is there.

    Waits for the lock on the file. The launcher that starts a watchdog holds it from before
    the watchdog exists, and the watchdog and its child hold it until the child is the CLI or
    has been refused, so a reader never looks in between: a CLI that is running is always
    found, even when the launcher was killed before it could note the pid in runs.json.

    The file is opened as every file of an attempt is (run_watchdog.py opened()): a symbolic
    link, a FIFO or anything else that is no record of this user's is not followed, waited for
    or read, and is no record.
    """
    try:
        with os.fdopen(watchdog.opened(pid_file)) as f:
            try:
                fcntl.flock(f, fcntl.LOCK_SH)
            except OSError:
                pass  # a file system without locks: read what is there
            lines = [line.partition(" ") for line in f.read().splitlines()]
    except OSError:
        return None
    pairs = [(int(pid), started or None) for pid, _, started in lines if pid.isdigit()]
    if len(pairs) not in (2, 3):
        return None
    within = next((named for word, _, named in lines if word == "namespace" and named), None)
    return {"watchdog": pairs[0], "cli": pairs[1], **({"hook": pairs[2]} if len(pairs) == 3 else {}),
            **({"namespace": within} if within else {}), "lock": Path(pid_file).with_suffix(".lock")}


def taken(fd: int) -> bool | None:
    """Whether a process holds an exclusive lock on the file this descriptor has open: a
    launcher on the study's lock file (Lock), a watchdog on its attempt's (unseen()). None
    where flock cannot tell. Asked with a shared lock that is not waited for, which an
    exclusive one refuses, and which is let go at once. A descriptor that only reads will do,
    and nothing is written: this works where the study cannot be written."""
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except OSError as e:
        return True if e.errno in (errno.EWOULDBLOCK, errno.EACCES) else None
    fcntl.flock(fd, fcntl.LOCK_UN)
    return False


def elsewhere(pids: dict | None) -> bool:
    """Whether the processes on record in an attempt's pid file (recorded()) were recorded in
    another process namespace than this shell's, as they are to a shell inside a harness's
    sandbox and to one outside a sandbox they were started in. Their ids then name no process
    here, or someone else's, so none of them is looked up or signalled from this shell. It says
    nothing of whether the attempt is alive, which the lock of its watchdog does (unseen()),
    and keeps no command from a study: it is why the CLI of a watchdog that has gone without an
    end record is not looked for here, and said not to have been (Supervisor.outcome()).
    Decided from what is on record and never from a process that is missing: the watchdog named
    its namespace, this shell has one (run_watchdog.py namespace()), and the two differ. False
    when either is not known, and the ids are then gone by as before.

    The same is asked of the launcher that the study's lock file names, which records its
    namespace as a watchdog does (Lock.holder())."""
    there, here = (pids or {}).get("namespace"), watchdog.namespace()
    return bool(there and here and there != here)


def living(pids: dict, *who: str) -> bool:
    """Whether a process on record in an attempt's pid file (recorded()) is to be seen running:
    any of them, or of the ones named. Ids recorded in another process namespace are not looked
    up (elsewhere()): a process found under one of them here is not the attempt's."""
    return not elsewhere(pids) and any(alive(*pids[x]) for x in who or ("watchdog", "cli", "hook") if x in pids)


def unseen(pids: dict | None) -> bool:
    """Whether an attempt is alive where this shell cannot look: its watchdog holds the lock of
    the attempt (run_watchdog.py, "The lock of an attempt"), which every shell sees, and is not
    to be seen under the id it recorded. That is a run started outside the sandbox this shell
    is in, or inside one this shell is outside of. Nothing here may be made of its processes
    being missing: it is not gone, not to be settled, and not to be started again.

    The lock alone says so, and never the namespace on record: a lock that is free is a
    watchdog that has ended, wherever it ran, and its run is this shell's to settle like any
    other. So is an attempt with no lock file, from before watchdogs held one, and one whose
    lock cannot be asked: False for each, and the ids on record are gone by, as they always
    were. The watchdog is looked for first and the lock asked second: a watchdog never takes
    its lock twice, so one that holds it after it was not to be seen was alive and out of
    sight all along, and one that ended in between has let go of it."""
    if not pids or living(pids, "watchdog"):
        return False
    try:
        fd = watchdog.opened(pids["lock"])
    except OSError:
        return False
    try:
        return taken(fd) is True
    finally:
        os.close(fd)


def end_record(path: Path) -> dict | None:
    """The end record a watchdog wrote for its attempt (fields in run_watchdog.py), or None
    while there is none. Opened as the pid file is (recorded()). It holds the command, which
    may be as long as the system lets one be: hence the room."""
    try:
        with os.fdopen(watchdog.opened(path, most=64 * watchdog.RECORD)) as f:
            record = json.loads(f.read())
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def printed(path: Path) -> str:
    """What an attempt's process wrote to one of its files in logs/, as text. The file is opened
    as every file of an attempt is (run_watchdog.py opened()), whatever its size: one that is no
    longer the regular file the launcher made for the attempt, a symbolic link or a FIFO put at
    its name since, is not followed or waited for, and reads as nothing written."""
    try:
        with os.fdopen(watchdog.opened(path, most=sys.maxsize), errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def kill_group(pid: int, started: str | None) -> tuple[bool, list[int] | None]:
    """Kill the process group of a CLI whose watchdog was killed, where the group is certain to
    be the CLI's. Returns (whether a group was killed, the processes left untouched). The same
    for the group of a "before" command that such a watchdog left running: read "CLI" as it.
    The second is None when no list of processes could be had, from /proc or from ps: nothing
    then says whether the group is empty, and "cannot tell" is never given as "none left".

    The group is the CLI's for certain only while the CLI itself, its leader, is still there:
    a process that holds the recorded id under the recorded start identity. It holds the id, so
    the group of that id is this attempt's. It is then killed, and waited for.

    In every other case nothing is signalled. With no process holding the id, or with a start
    identity that was never recorded, a group of that id may be what the CLI left behind, or
    may be another's that was given the id since: nothing here can tell, so its members are
    returned for the user to look at. A process that holds the id under another identity got
    it after the CLI's group had emptied: nothing of the attempt is left, and nothing returned.

    What is left: a CLI that ends, and whose id is given to another group, between the look at
    its identity and the signal."""
    found = watchdog.process(pid)
    if found and started and found[1] == started:
        killed = watchdog.signal_group(pid, signal.SIGKILL)
        give_up = time.time() + 2
        while watchdog.signal_group(pid, 0) and time.time() < give_up:
            time.sleep(0.01)
        return killed, []
    if found and started:
        return False, []
    try:
        return False, sorted([*([pid] if found else []), *watchdog.others(pid)])
    except (OSError, subprocess.SubprocessError):
        return False, None  # no list of processes to be had: whether anything is left is not known


def unchecked(groups: list[int]) -> str:
    """What to say when nothing could tell whether the attempt of a killed watchdog left a process
    behind (kill_group())."""
    ids = ", ".join(map(str, groups))
    return (f"no list of processes can be had on this system (neither /proc nor ps), so the launcher could not check "
            f"whether process group {ids} still holds anything left over from this run. That is not known to be "
            "empty: look for yourself, and stop what is the run's.")


# What a launcher says of the CLI of a watchdog that was killed, when its ids were recorded in another
# process namespace than the shell's (elsewhere()): in the run's reason, and at the head of a line of its own.
APART = "its CLI could not be checked from this shell because it ran in another process namespace"


def unlooked(pids: list[int]) -> str:
    """What to say when the attempt of a killed watchdog ran in another process namespace than this
    shell's, so that nothing here could look for what it left (Supervisor.outcome())."""
    ids = ", ".join(map(str, pids))
    return (f"{APART}. Nothing was looked up or signalled under pid {ids}, which is of that namespace and not of "
            "this one. If that namespace is still there, as a sandbox that is still open is, look in it for "
            "yourself, and stop what is the run's.")


def leftover(left: dict) -> str:
    """What to say of the processes that the attempt of a killed watchdog may have left behind."""
    pids = ",".join(map(str, left["pids"]))
    return (f"process group {left['group']} still holds pid {pids.replace(',', ', ')}, which may be left over from "
            "this run. The launcher cannot prove that, so it has left the group untouched: check with "
            f"ps -o pid,pgid,command -p {pids} and stop what is the run's.")


def remainder(rest: dict) -> str:
    """What to say of what a stopped browser session has left (Supervisor.browser_left())."""
    pids = ", ".join(map(str, rest["left"]))
    return " and ".join(x for x in (
        f"pid {pids} may be left of it (check with ps -o pid,command -p {pids.replace(' ', '')} and stop what is "
        "the run's)" if pids else "",
        f"this was left in place: {'; '.join(rest.get('kept') or [])}" if rest.get("kept") else "") if x)


def still_left(left: dict | None) -> dict | None:
    """The same record, less the processes that have gone from the group since. None when none is left."""
    def there(pid):
        try:
            return os.getpgid(pid) == left["group"]
        except OSError:
            return False
    pids = [pid for pid in left["pids"] if there(pid)] if left else []
    return {**left, "pids": pids} if pids else None


class StopSignal:
    """What SIGTERM, SIGINT and SIGHUP set: asked once, stop the runs cleanly; asked again, skip
    the grace period. A SIGHUP that was already ignored when the launcher started stays ignored:
    that is how nohup keeps a launcher going after its terminal has closed."""

    def __init__(self):
        self.asked = self.force = False

    def __call__(self, *_):
        self.force, self.asked = self.asked, True

    def listen(self):
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            if sig != signal.SIGHUP or signal.getsignal(sig) != signal.SIG_IGN:
                signal.signal(sig, self)


# ---------------------------------------------------------------- the study lock

class Lock:
    """One launcher per study. <study>/.launch.lock is held with flock for as long as the
    launcher lives, so the system releases it when the launcher dies, however it dies. The file
    holds {"pid", "identity", "command", "grace", "since"}, which is how "stop" and "status"
    name the launcher, and how a second launcher is refused where flock does not work, and
    "namespace", the process namespace the launcher runs in, where the system names one
    (run_watchdog.py namespace()): the id means the launcher only to a shell in it. A file
    left by a dead launcher names no live process: it is reported and written over.

    The file stays. The scaffold makes it, empty (make()), a command that takes a study
    without one makes it, and no command removes it: a launcher that ends empties the record
    it wrote, under its lock, and leaves the file (release()). So every launcher and every
    reader locks the one file, and a shell that cannot write the study has it to lock in a
    study at rest (share()). A file that is empty names no launcher, and is not one that a
    launcher left behind.

    Whether a launcher has the study is what the lock says, and not whether the process the
    file names is to be seen (holder()): a shell in another process namespace, as inside a
    harness's sandbox, sees the lock and no process of the study. A command that only asks,
    "status" and "plan" among them, holds no lock: it asks with a shared one that is not
    waited for and is let go at once (taken()). A launcher's lock is exclusive, so it refuses
    that, and a launcher that finds only a shared one in its way asks again (acquire()): no
    command that asks can turn a launcher away. One command keeps a shared lock: archive.py,
    for as long as it copies a study that it cannot write (share()). A launcher that finds
    that one still in its way after ASKING seconds says that the study is being read, and to
    try again.

    The lock is not given for a study with a run that is alive where this shell cannot look
    (out_of_sight()): one a killed launcher left under its watchdog, in another process
    namespace. Every command that takes the study comes through acquire(), so that is where
    each of them is refused, with the lock file as it was found and nothing of the study
    changed or signalled. That is looked for also where the lock file cannot be opened to
    write, for a caller that would go on without the study (blind(), share()).

    The file is opened as every file of an attempt is (run_watchdog.py opened()): never through
    a symbolic link, which would put the lock on a file somewhere else, and never waiting, as a
    read of a FIFO left at its name would. flock needs no more than a descriptor of the one
    file every launcher opens, which this still is. What is there and is no regular file of
    this user is no lock: "status" and "stop" then find no launcher, and a command that needs
    the study refuses in a sentence until the lead has looked at it and deleted it."""

    def __init__(self, study_dir: Path):
        self.sd, self.path, self.fd = study_dir, study_dir / LOCK, None
        self.hidden = None  # what acquire() said of runs it could not see: why it left the study, or may not go on
        self.reading = None  # what acquire() said when all that was in its way was a lock that a reader keeps
        self.shared = False  # whether the lock held is a reader's (share()): the file is then not this command's

    @staticmethod
    def holder(study_dir: Path, ask: bool = True) -> dict | None:
        """The launcher that has the study, as the lock file names it, with "seen": whether its
        process is to be seen from this shell. None when no launcher has the study.

        The lock decides (taken()): while it is held a launcher is running, whatever the process
        id on record looks like from here. In another process namespace, as inside a harness's
        sandbox, the lock is seen and the process is not: "seen" is then false, and nothing a
        command says may rest on seeing a process of the study. That is believed only of a lock
        still held after NAMING seconds, with the file read again: a launcher that has just
        taken the lock writes its name over the one it found, and one that has just ended lets
        go of the lock with the file emptied, or, killed, while the file still names it. A lock
        that is held is not always named: "pid" and "command" are then None. A file that names
        no one, as a launcher that ended leaves it, is no launcher once its lock is free.

        The process is seen when one holds the id on record under the start identity on record,
        and the namespace on record is not known to be another than this shell's (elsewhere()).
        An id recorded in another namespace names no process here, or someone else's: whatever
        holds it is not the launcher, "seen" is false, and no command signals it. A file with no
        namespace, from a system that names none or a launcher from before one was recorded, is
        gone by its id and start identity alone.

        Where the lock is not held, or flock cannot tell, a launcher has the study when the
        process the file names is seen alive. ask false is for the launcher that has asked the
        lock itself (acquire()), which a lock of its own would answer."""
        try:
            fd = watchdog.opened(study_dir / LOCK)
        except OSError:
            return None

        def named() -> tuple[dict, bool]:
            try:
                info = json.loads(os.pread(fd, watchdog.RECORD, 0))
            except (OSError, ValueError):
                info = None
            info = info if isinstance(info, dict) else {}
            return info, not elsewhere(info) and alive(info.get("pid"), info.get("identity"))

        try:
            held = ask and taken(fd)
            info, seen = named()
            if held and not seen:
                time.sleep(NAMING)
                held = taken(fd)
                info, seen = named()
        finally:
            os.close(fd)
        if held:
            return {"pid": None, "command": None, **info, "seen": seen}
        return {**info, "seen": True} if seen else None

    @staticmethod
    def make(study_dir: Path):
        """Make the study's lock file where there is none, empty, as the scaffold does
        (init_study.py): a shell that cannot write the study can then keep a launcher away
        before the study has had one (share()). Whatever is at its name already is left as it
        is: a lock file is not emptied, as a launcher may hold it, and one that this shell may
        only read is a lock file all the same, opened as share() opens it. Where there is none
        and none can be made, this raises what the system said, or Unsafe for what is at its
        name and is no lock, as acquire() tells them apart, for the scaffold to say and fail
        on."""
        path = study_dir / LOCK
        try:
            os.close(watchdog.opened(path, os.O_RDWR | os.O_CREAT))
        except watchdog.Unsafe:
            raise
        except OSError as err:
            try:
                os.close(watchdog.opened(path))
            except OSError:
                raise err from None

    @staticmethod
    def who(held: dict | None) -> str:
        """The launcher that has the study, in brackets, for a sentence that refuses for it."""
        if not (held and held.get("pid")):
            return ""
        return f' (pid {held["pid"]}, running "{held.get("command")}" since {clock(held.get("since"))})'

    def refuse(self):
        """Exit, saying why the study is not this command's: for the launcher that has it, or,
        with none, for the runs acquire() found out of sight, or for the reader whose lock
        acquire() could not wait out. A launcher is looked for first: runs that are out of
        sight under one are its own, and it is what there is to wait for."""
        held = self.holder(self.sd)
        if (self.hidden or self.reading) and not held:
            raise SystemExit(self.hidden or self.reading)
        raise SystemExit(f"Another launcher has this study{self.who(held)}. Wait for it to finish, or stop it with: "
                         f"launch.py {self.sd} stop"
                         + (f". {UNSEEN}, so stop it from a shell that can." if held and not held["seen"] else ""))

    def acquire(self, command: str, grace: float, must: bool = True) -> bool:
        """Take the study for command. When it cannot be taken, exit saying why, or with must
        false return False: for a command that carries on without the study.

        It is not taken while a run of it is out of sight (blind()), looked for under the
        lock, where no launcher can start one or settle one meanwhile, and before anything is
        written: the lock is let go and its file left as it was found, or empty where there
        was none, so the command has changed nothing else. refuse() then says which runs, also
        for a caller that passed must false and has to stop after all.

        A lock that only a shared one keeps it from is asked for again, for ASKING seconds: a
        command that asks has let go by then (taken()). One still in the way after that is
        kept by a command that reads the study, as archive.py does while it copies one it
        cannot write (share()). The study is not taken, and refuse() says that it is being
        read and to try again (self.reading), which is no launcher to wait for or to stop.

        A lock file that cannot be opened to write gives no lock to look under: a study that a
        sandbox shows read-only, or something at its name that no launcher made. Nor does one
        in a study directory that cannot be written: the file is there from the scaffold on,
        so that it opens no longer says that a run can be recorded beside it. With must
        false the runs out of sight are looked for all the same before False is returned,
        which needs no more than to read, and are kept for refuse() in self.hidden. A caller
        that would go on without the study, as archive.py does, has more to ask first, under
        a lock of its own where it can have one (share()).

        The file is made where there is none and never removed or put aside (release()), so
        the one that is opened here is the one every other command locks."""
        give_up = time.time() + ASKING
        while True:
            try:
                fd = watchdog.opened(self.path, os.O_RDWR | os.O_CREAT)
                if not os.access(self.sd, os.W_OK):  # the file was there to open, and no other can be made beside it
                    os.close(fd)
                    raise PermissionError(errno.EACCES, os.strerror(errno.EACCES))
            except watchdog.Unsafe as err:  # a link or a FIFO at its name, or another user's file: no lock of ours
                if not must:
                    self.blind(command)
                    return False
                raise SystemExit(f"{err}, so it is no lock a launcher made, and \"{command}\" did nothing. Look at "
                                 "what is there, then delete it.")
            except OSError as err:  # a sandboxed shell, or a study directory that is not ours to write
                if not must:
                    self.blind(command)
                    return False
                raise SystemExit(
                    f"The system refused to write {self.path} ({err.strerror}). The launcher records every run in "
                    f'the study directory, so "{command}" did nothing. {pl.SANDBOX_HINT}')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as e:
                if e.errno in (errno.EWOULDBLOCK, errno.EACCES):
                    # A launcher's lock refuses a shared one as well. Where a shared one is given, what was in
                    # the way was a command that only asks (taken()), which has let go by now: ask again.
                    shared = taken(fd) is False
                    os.close(fd)
                    if shared and time.time() < give_up:
                        time.sleep(0.01)
                        continue
                    if shared:  # still there: no question takes that long, so a command that reads keeps it
                        self.reading = (
                            f"Something is reading this study and keeps a shared lock on {self.path} meanwhile, as "
                            f"archive.py does while it copies a study from a shell that cannot write it, so "
                            f'"{command}" did nothing. Try again once it has finished.')
                    if not must:
                        return False
                    self.refuse()
            break
        if self.holder(self.sd, ask=False):  # where flock does not work: the process the file names is alive
            os.close(fd)
            if not must:
                return False
            self.refuse()
        if self.blind(command):
            os.close(fd)
            if not must:
                return False
            self.refuse()
        try:  # read through the descriptor that holds the lock, never by name again
            left_by = json.loads(os.pread(fd, watchdog.RECORD, 0)).get("pid")
            say(f"Cleared a stale lock left by a launcher that is gone (pid {left_by}).")
        except (OSError, ValueError, AttributeError):
            pass  # an empty file among them: the last launcher ended by itself, and left nothing behind
        within = watchdog.namespace()  # where the system names one: the id below means this process only there
        os.ftruncate(fd, 0)
        os.write(fd, json.dumps({"pid": os.getpid(), "identity": identity(os.getpid()), "command": command,
                                 "grace": grace, "since": round(time.time()),
                                 **({"namespace": within} if within else {})}).encode())
        self.fd = fd
        return True

    def blind(self, command: str) -> bool:
        """Whether a run of the study is alive where this shell cannot look (out_of_sight()),
        with what command is to say of it kept in self.hidden, for refuse(). Nothing is written
        and no lock is kept: the pid file and the lock of each attempt in flight are opened to
        read and asked with a shared lock, so this answers in a study that cannot be written."""
        try:
            hidden = out_of_sight(self.sd, pl.read_runs(self.sd)) if (self.sd / "runs.json").exists() else []
        except ValueError:  # not valid JSON: it names no run to look for
            hidden = []
        if hidden:
            self.hidden = (
                f"This shell cannot see the processes of {', '.join(hidden)}, as inside a sandbox: "
                + agree(len(hidden), "its watchdog holds its lock, so that run is",
                        "their watchdogs hold their locks, so those runs are")
                + f" still at work where this shell cannot look. \"{command}\" changed nothing and signalled "
                f"nothing. {pl.SANDBOX_HINT} Runs that were started inside a sandbox end when it does, and any "
                "shell settles them then.")
        return bool(hidden)

    def share(self, command: str) -> bool:
        """Hold the study for a command that only reads it and cannot take it: archive.py, of a
        study that cannot be written, where acquire() gives no lock. A shared lock on the lock
        file, through a descriptor that only reads, kept until release(). A launcher's lock is
        exclusive and is not given while this one is held, so no launcher can start a run, or
        settle one, from before this looks at the study until the caller lets go: what is
        found here stays so. Nothing is written, and the file is left where it is, as it is
        not this command's. Returns whether the lock is held.

        Under the lock, or with none, the same is asked: whether a run is alive where this
        shell cannot look (blind()), and then whether the file names a launcher that is seen
        alive (holder(), which is how a launcher is found where flock does not work). Exits
        as refuse() does for either, with nothing held, and when the shared lock is refused
        and goes on being refused, which is a launcher at work.

        False when no lock can be had: there is no lock file to open, as in a study from
        before the scaffold made one and launchers left theirs (make(), release()), what is
        at its name is no lock of this user's, or flock cannot tell. Nothing then keeps a
        launcher from starting after the two looks above. The runs are looked for before the
        launcher, so one that started a run and was killed in between leaves that run on
        record in runs.json, which the caller reads last and decides by."""
        while True:
            try:
                fd = watchdog.opened(self.path)
            except OSError:  # no file, or nothing a launcher made: no lock to hold
                fd = None
                break
            try:
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except OSError as e:
                os.close(fd)
                fd = None
                if e.errno not in (errno.EWOULDBLOCK, errno.EACCES):
                    break  # flock cannot tell
                if self.holder(self.sd):  # only an exclusive lock refuses this one: a launcher, when it is still held
                    self.refuse()
                continue  # let go since, by a command that was itself not given the study: ask again
            break  # on the one file every launcher locks: none removes it or puts another in its place
        self.fd, self.shared = fd, fd is not None
        try:
            if self.blind(command) or self.holder(self.sd):
                self.refuse()
        except BaseException:
            self.release()
            raise
        return self.shared

    def release(self):
        """Let go of the study. A launcher empties the record it wrote, while it still has the
        lock, and leaves the file where it is: the next launcher and every reader lock the
        same one, and one that names no launcher is no stale lock. A reader wrote nothing."""
        if self.fd is not None:
            if not self.shared:
                try:
                    os.ftruncate(self.fd, 0)
                except OSError:
                    pass  # it goes on naming this launcher, as one that was killed: the next says so and writes over it
            os.close(self.fd)
            self.fd, self.shared = None, False


# ---------------------------------------------------------------- roles

class Panellist:
    """What the supervisor asks about a panellist run. A role is a class with these methods;
    ROLES maps the "role" of a runs.json entry to it."""

    noun = "run"

    @staticmethod
    def workdir(cfg: dict, entry: dict) -> Path:
        return pl.workdir(cfg["_dir"], entry["role"])

    @staticmethod
    def progress(cfg: dict, entry: dict) -> dict:
        sd = cfg["_dir"]  # read as it stood before a follow-up that is not settled (pl.read_persona)
        return pl.run_progress(cfg, pl.read_persona(sd, cfg, sd / entry["file"], entry))

    @staticmethod
    def limits(cfg: dict, entry: dict) -> dict:
        return pl.limits_for(cfg, "panellist", entry["key"])

    @staticmethod
    def prompt(cfg: dict, entry: dict) -> str:
        return (cfg["_dir"] / entry["prompt"]).read_text()  # verbatim: nothing is added to it

    @staticmethod
    def resume_message(cfg: dict, entry: dict) -> str:
        return tracker.resume_message(cfg, tracker.run_view(cfg["_dir"], cfg, entry))

    @staticmethod
    def browse(cfg: dict, entry: dict) -> bool:
        return cfg["browse"]

    @staticmethod
    def collect(cfg: dict, entry: dict, result: dict, ending: str | None) -> str | None:
        return None  # a panellist's work is its persona file: nothing is taken from its reply


class Synthesis:
    """The same questions about an analyst or writer job: one process that works in the study
    directory and writes one file, entry["file"]. Its progress has that file as its only unit,
    scored once the file holds something and never just "written", so a job is done, or it has
    nothing: pl.run_state() then never calls it partial."""

    noun = "job"

    @staticmethod
    def workdir(cfg: dict, entry: dict) -> Path:
        return pl.workdir(cfg["_dir"], entry["role"])

    @staticmethod
    def progress(cfg: dict, entry: dict) -> dict:
        f = cfg["_dir"] / entry["file"]
        there = [entry["file"]] if f.is_file() and f.read_text(errors="replace").strip() else []
        return {"units": [entry["file"]], "written": there, "scored": there, "has_final": bool(there),
                "complete": bool(there)}

    @staticmethod
    def limits(cfg: dict, entry: dict) -> dict:
        return pl.limits_for(cfg, entry["role"])

    @staticmethod
    def prompt(cfg: dict, entry: dict) -> str:
        return (cfg["_dir"] / entry["prompt"]).read_text()  # the filled brief, verbatim

    @staticmethod
    def resume_message(cfg: dict, entry: dict) -> str:
        return (f"Your work was cut off before `{cfg['_dir'] / entry['file']}` was written. Pick up where you left "
                "off and write the complete document to that file. All the original rules still apply. If you are "
                "blocked from writing the file, return the complete document as your reply instead.")

    @staticmethod
    def browse(cfg: dict, entry: dict) -> bool:
        return False

    @staticmethod
    def collect(cfg: dict, entry: dict, result: dict, ending: str | None) -> str | None:
        """Save the process's final reply to analysis/<job id>-reply.md, and make it the output
        file when the process ended well without writing one. ending is how the process ended
        when that was not a clean finish. An output file, however it came about, is given the
        synthetic panel notice when it lacks it (pl.with_notice), so the line does not depend on
        the job obeying its brief. Returns what the lead should know about the output."""
        sd, reply = cfg["_dir"], result["reply"]
        output = sd / entry["file"]
        if reply and reply.strip():
            (sd / "analysis").mkdir(exist_ok=True)
            (sd / "analysis" / f"{entry['run']}-reply.md").write_text(reply.strip() + "\n")
        if Synthesis.progress(cfg, entry)["complete"]:
            note = f"{ending} after writing {entry['file']}: check that the file is whole" if ending else None
        else:
            document = pl.reply_document(reply or "")
            if not document:
                return None
            output.write_text(document + "\n")
            note = f"its process did not write {entry['file']}, so the file is the document from its reply"
        try:
            text = output.read_text()
        except UnicodeDecodeError:  # not text: left as the job wrote it
            return note
        if pl.NOTICE not in text:
            output.write_text(pl.with_notice(text))
        return note


ROLES = {"panellist": Panellist, "analyst": Synthesis, "writer": Synthesis}


def progress_of(cfg: dict, entry: dict) -> dict:
    return ROLES[entry["role"]].progress(cfg, entry)


def state_of(cfg: dict, entry: dict) -> str:
    return pl.run_state(progress_of(cfg, entry), entry.get("state"))


usage_of, sessions_of = planning.usage_of, pl.sessions_of


def record_usage(cfg: dict, runs: list[dict]) -> dict:
    """Rewrite analysis/usage.md from what runs holds, and return the figures in it. When the
    file cannot be written (a sandboxed shell, a full disk) the figures are returned all the
    same, with a note on stderr: they are in runs.json either way."""
    entries = [e for e in runs if e["role"] in ROLES]
    figures = planning.usage_figures(entries, {e["run"]: state_of(cfg, e) for e in entries})
    try:
        (cfg["_dir"] / "analysis").mkdir(exist_ok=True)
        pl.write_atomic(cfg["_dir"] / "analysis" / "usage.md", planning.usage_markdown(figures))
    except OSError as failed:
        print(f"Note: analysis/usage.md could not be written ({failed.strerror or failed}). The usage is in "
              "runs.json.", file=sys.stderr, flush=True)
    return figures


def allowance(cfg: dict, entry: dict) -> dict:
    """The run's limits over all its attempts: one allowance, plus one for each --extend."""
    limits, times = ROLES[entry["role"]].limits(cfg, entry), 1 + (entry.get("extended") or 0)
    return {"minutes": limits["minutes"] * times, "budget_usd": limits["budget_usd"] * times}


def left(cfg: dict, entry: dict) -> dict:
    """What is left of the allowance: {"seconds", "budget_usd"}. Spend a harness does not report
    counts as none, so the time limit is what bounds such a run. That includes the spend of an
    attempt whose process was stopped before it reported any (planning.unreported): no figure is
    made up for it, so the budget left can be more than is truly left until its session reports."""
    total = allowance(cfg, entry)
    return {"seconds": total["minutes"] * 60 - (entry.get("seconds_used") or 0),
            "budget_usd": total["budget_usd"] - (usage_of(entry)["cost_usd"] or 0)}


# ---------------------------------------------------------------- the supervisor

# What starting an attempt overwrites, or takes out of the entry.
UNDONE = ("state", "pid", "pid_identity", "session", "reason", "reset_at", "limited_by", "checks", "released",
          "task_attempts")


asking = pl.asking  # the follow-up attempt of a run that is not settled yet


def in_flight(e: dict) -> bool:
    """Whether a process of the run may be alive: it is recorded as running, or has a follow-up
    question that is not settled yet."""
    return e.get("state") == "running" or bool(asking(e))


def at_work(study_dir: Path, runs: list[dict]) -> list[str]:
    """The runs and jobs that have a process to be seen alive now: the watchdog or the CLI of an
    attempt in flight, found through the attempt's own pid file, as "status" finds them. One
    that is alive where this shell cannot look is not among them (out_of_sight())."""
    busy = []
    for e in runs:
        attempts = e.get("attempts") or []
        pids = recorded(Path(study_dir) / "logs" / f"{e['run']}.{attempts[-1]['n']}.pid") if (
            in_flight(e) and attempts) else None
        if pids and living(pids):
            busy.append(e["run"])
    return busy


def out_of_sight(study_dir: Path, runs: list[dict]) -> list[str]:
    """The runs and jobs in flight that are alive where this shell cannot look: the watchdog of
    the last attempt holds its lock and is not to be seen (unseen()). Such a run is for a
    launcher in a shell that sees its processes, and what they leave. One whose watchdog has
    ended is not among them, wherever it ran: its lock is free, and any launcher settles it."""
    hidden = []
    for e in runs:
        attempts = e.get("attempts") or []
        pids = recorded(Path(study_dir) / "logs" / f"{e['run']}.{attempts[-1]['n']}.pid") if (
            in_flight(e) and attempts) else None
        if unseen(pids):
            hidden.append(e["run"])
    return hidden


def undo(e: dict):
    """Take back a run's last attempt, whose process never did anything as the CLI: the entry is
    as it was before it. A run that never started has no attempt and is not failed."""
    was = e["attempts"].pop().get("was") or {}
    for field in UNDONE:
        e.pop(field, None)
    e.update(was)
    if not e["attempts"]:
        del e["attempts"]


class Child:
    """One attempt whose watchdog is alive, or was when last looked at: started by this launcher
    (proc is set) or adopted from an earlier one. Both are watched through the attempt's files."""

    def __init__(self, entry: dict, pids: dict, end: Path, proc=None):
        self.entry, self.pids, self.end, self.proc = entry, pids, end, proc
        self.asked = 0  # requests to stop sent to its watchdog
        self.log_seen = None  # what its step log was known by when over_steps() last read it (pl.step_log_stamp())
        self.cut = False  # that read found the log shorter than what had been read of it: looked at once more

    def watched(self) -> bool:
        """Whether its watchdog is still running."""
        return self.proc.poll() is None if self.proc else living(self.pids, "watchdog")


class Supervisor:
    """Starts queued attempts within each runner's concurrency, each under a watchdog of its own
    (run_watchdog.py), settles every attempt from the end record its watchdog writes, and writes
    runs.json after every state change. The watchdogs enforce the time limit and stop the CLIs:
    the supervisor signals no CLI, and asks the watchdogs when it is told to stop.

    queue holds (entry, kind) pairs waiting for a slot, kind being launch, retry, resume,
    restart or followup. Every role goes through the same code: what differs is in ROLES.

    A followup attempt puts the question in question, {"n": the follow-up's number, "message":
    a function from a run's entry to the message for its panellist}, to a finished run in its
    session. It has limits of its own, leaves the run's state alone, and is settled by
    answered(): see "Follow-up questions" in the module docstring."""

    def __init__(self, cfg: dict, runs: list[dict], grace: float, poll: float, retry: bool = False,
                 stop: StopSignal | None = None, question: dict | None = None):
        self.cfg, self.sd, self.runs = cfg, cfg["_dir"], runs
        self.grace, self.poll, self.retry, self.stop = grace, poll, retry, stop or StopSignal()
        self.question = question
        self.queue, self.children, self.adopted = [], [], []
        self.closed = {}        # runner -> why it starts nothing more in this command
        self.retried = set()    # runs already retried by this command
        self.refused = False    # a process could not be started at all
        self.let_go = set()     # runs whose account this launcher has tried to tear down: once for each command
        self.left_alone = False  # a run this command was asked to continue cannot be
        self.distrusted = set()  # the browser session records this command has refused, and said so
        self.held = None        # why no command of the study may be started: what accounts.recover() stopped for
        self.modules = {}

    def runner(self, name: str):
        if name not in self.modules:
            self.modules[name] = runners.get(name)
        return self.modules[name]

    def save(self):
        pl.write_runs(self.sd, self.runs)

    def snapshot(self, during: list[str]):
        """Bring the modification record (panel_lib) up to date: hash every panellist's persona
        file and note each one that changed while its own run was not among the processes alive
        since the last snapshot, during, and others were. Taken at every start and end of a
        process, so the processes alive between two snapshots are always the same ones."""
        record, at, moved = pl.read_modifications(self.sd), round(time.time()), False
        for e in self.runs:
            if e["role"] != "panellist":
                continue
            digest = pl.file_hash(self.sd, self.sd / e["file"])
            if e["file"] in record["hashes"] and digest == record["hashes"][e["file"]]:
                continue
            if e["file"] in record["hashes"] and during and e["run"] not in during:
                record["changes"].append({"file": e["file"], "run": e["run"], "at": at, "running": sorted(during)})
                say(f"{e['run']}: its persona file changed while {', '.join(sorted(during))} ran and it did not. "
                    "check_runs.py will report it.")
            record["hashes"][e["file"]], moved = digest, True
        if moved:
            (self.sd / pl.MODIFICATIONS).parent.mkdir(exist_ok=True)
            pl.write_atomic(self.sd / pl.MODIFICATIONS, json.dumps(record, indent=2) + "\n")

    def log(self, entry: dict, n: int, ext: str) -> Path:
        return self.sd / "logs" / f"{entry['run']}.{n}.{ext}"

    def base(self, entry: dict, n: int) -> Path:
        """The log base of an attempt: what its files in logs/ are named by, less the extension."""
        return self.sd / "logs" / f"{entry['run']}.{n}"

    # ---- runs an earlier launcher left as running

    def reconcile(self, adopt: bool = True, final: bool = True, commands: bool = True):
        """Settle every entry recorded as running. An attempt that has ended is settled from its
        end record, as it would have been by the launcher that started it. One whose watchdog is
        still alive is adopted: it counts against its runner's concurrency, and is settled when
        it ends. An attempt with nothing in its pid file is from a launcher that died before
        its process started. Then every follow-up record that nothing in flight will settle is
        given its outcome (settle_followups()).

        adopt false is for a command that supervises nothing: an attempt still alive is left
        for the next launcher. final false leaves settle_final() to the caller, which has
        something to do first with the runs it would finish. commands false is for "stop", which
        has runs to stop whatever became of a command of the study: where recover() would exit,
        it keeps the reason (self.held) and this launcher starts no command of the study."""
        self.recover(must=commands)  # before anything else: a command left running, a teardown left half done
        if (self.sd / pl.MODIFICATIONS).exists():  # what changed while no launcher was watching
            self.snapshot([e["run"] for e in self.runs if in_flight(e)])
        for e in self.runs:
            if not in_flight(e) or e["role"] not in ROLES:
                continue
            n = e["attempts"][-1]["n"]
            pids = recorded(self.log(e, n, "pid"))
            if not pids:
                self.take_back(e, "an earlier launcher died before starting it")
                say(f"{e['run']}: {state_of(self.cfg, e)} (an earlier launcher died before starting it)")
                continue
            child = Child(e, pids, self.log(e, n, "end"))
            record = self.outcome(child)
            if record:
                self.ended(child, record, settling=True)
                continue
            if not adopt:
                continue
            if e.get("pid") is None:  # that launcher died before it could note the process
                e.update(pid=pids["cli"][0], pid_identity=pids["cli"][1])
                self.save()
            self.children.append(child)
            self.adopted.append(e)
            say(f"{e['run']}: {'being asked a follow-up question' if asking(e) else 'running'}, adopted from an "
                f"earlier launcher (pid {e['pid']})")
        self.sweep_browsers()
        if final:
            self.settle_final()
        self.settle_followups()

    def settle_followups(self):
        """Give an outcome to every record of followups.json that has none and that no attempt in
        flight will give one, and delete the copies of persona files that settled attempts left.

        A launcher records every run it is about to ask before it starts the first, so one that
        was killed leaves the runs still queued on record with no outcome: they are "not asked".
        A record with a decision on it ("settling", panel_lib.py) and no attempt in flight has
        the decision carried out. The caller has the study lock, so no record here is waiting
        its turn in a launcher that is alive."""
        entries = {e["run"]: e for e in self.runs}
        for e in self.runs:  # a launcher died between noting the attempt's end and deleting its copy
            for a in e.get("attempts") or []:
                if a.get("kind") == "followup" and a.get("ended") is not None:
                    self.log(e, a["n"], "before").unlink(missing_ok=True)
        for f in pl.read_followups(self.sd):
            if f.get("mode") == "native":
                continue
            for r in f.get("runs") or []:
                e = entries.get(r.get("run"))
                if r.get("outcome") is not None or (e and (asking(e) or {}).get("followup") == f["n"]):
                    continue
                decision = r.get("settling") if e else None
                if decision:
                    self.act(e, decision)
                    settled = {"outcome": decision["outcome"], "reason": decision["reason"]}
                else:
                    settled = {"outcome": "not asked", "attempt": None,
                               "reason": "the launcher that was asking was killed before its turn came"}
                pl.record_followup(self.sd, f["n"], r["run"], settling=None, **settled)
                say(f"{r['run']}: follow-up {f['n']} {settled['outcome']}: {settled['reason']}")

    # ---- starting

    def fill(self):
        """Start whatever is queued and fits within its runner's concurrency."""
        for item in list(self.queue):
            name = item[0]["runner"]
            if item not in self.queue or name in self.closed:
                continue
            if self.cfg.get("sequential") and item[0]["role"] == "panellist" and any(
                    c.entry["role"] == "panellist" for c in self.children):
                continue  # one panellist at a time, across all runners
            cap = pl.runner_concurrency(self.cfg, name, self.runner(name).capabilities()["default_concurrency"])
            if sum(c.entry["runner"] == name for c in self.children) < cap:
                self.queue.remove(item)
                self.start(*item)

    def start(self, e: dict, kind: str):
        role, runner = ROLES[e["role"]], self.runner(e["runner"])
        number = self.question["n"] if kind == "followup" else None
        if number:  # an allowance of its own for each question: what the run has used does not count
            total = pl.limits_for(self.cfg, "followup")
            remaining = {"seconds": total["minutes"] * 60, "budget_usd": total["budget_usd"]}
        else:
            remaining, total = left(self.cfg, e), allowance(self.cfg, e)
        spent = [f"none of its {allowed} left" for gone, allowed in (
            (remaining["seconds"] <= 0, f"{total['minutes']:g} min"),
            (remaining["budget_usd"] < MIN_BUDGET, f"${total['budget_usd']:g}")) if gone]
        if spent:
            e.update(state="limited", reset_at=None, reason=" and ".join(spent)
                     + f" after {plural(len(e.get('attempts') or []), 'attempt')}",
                     limited_by="time" if remaining["seconds"] <= 0 else "budget")
            self.save()
            say(f"{e['run']}: limited without starting: {e['reason']}")
            self.finish(e)
            return
        usability = self.cfg["type"] == "usability" and e["role"] == "panellist"
        had = (e.get("account") or {}).get("times")  # which provisioning its last attempt ran with
        account = self.prepare(e, kind) if usability and not number else None
        if account is False:
            return
        # Provisioned again for this attempt: the account its session knew was torn down (accounts.py).
        renewed = bool(account) and had is not None and account.get("times") != had
        limits = {"minutes": remaining["seconds"] / 60,
                  "budget_usd": remaining["budget_usd"] if runner.capabilities()["budget_cap"] else None}
        n = len(e.get("attempts") or []) + 1
        # A follow-up to a usability run answers from what it saw: its account is gone, and it opens nothing.
        browse = role.browse(self.cfg, e) and runner.capabilities()["browser"] and not (usability and number)
        run, workdir, hooks, session = {**e, "browse": browse}, role.workdir(self.cfg, e), None, None
        if browse:  # the attempt's own browser session: its watchdog starts it before the CLI and stops it after
            session = browser.plan(self.base(e, n).resolve(), e["run"])
            run["browser_env"] = browser.changes(session)
        if usability and kind == "resume":  # on the run before its message is made, which gives each number
            e["task_attempts"] = tracker.issue_attempts(self.cfg, tracker.run_view(self.sd, self.cfg, e))
        try:
            if number:
                command = runner.resume_command(run, e["session"], self.question["message"](e), workdir, limits)
            elif kind == "resume":  # a usability run's own message says what became of its browser (runs.py)
                command = runner.resume_command(run, e["session"],
                                                role.resume_message(self.cfg, {**e, "new_account": renewed})
                                                + (BROWSER_RESTARTED if browse and not usability else ""),
                                                workdir, limits)
            else:
                command = runner.launch_command(run, role.prompt(self.cfg, e), workdir, limits)
        except ValueError as err:
            self.refused = True
            say(f"{e['run']}: not started, {e['runner']} cannot build its command: {err}")
            if number:
                pl.record_followup(self.sd, number, e["run"], outcome="could not start",
                                   reason=f"{e['runner']} cannot build its command: {err}")
            return
        pid_file, end = self.log(e, n, "pid"), self.log(e, n, "end").resolve()
        pid_file.parent.mkdir(exist_ok=True)
        if session:
            try:  # signed in from the start: a copy of the account's saved state, which the session deletes
                state = accounts.session_state(self.cfg, account, self.log(e, n, "state").resolve())
            except accounts.Failed as err:
                self.hold(e, err)
                return
            hooks = {"before": browser.start_command(session, workdir, self.cfg.get("capture", {}).get("desktop"),
                                                     state, delete_state=True),
                     "after": browser.stop_command(session), "log": str(self.log(e, n, "hooks").resolve()),
                     "seconds": {"before": browser.START, "after": browser.STOP}}
        aside = None
        if usability and not number and kind != "resume":  # a new session: no step or screenshot of an earlier one
            try:
                aside = self.set_aside(e)
            except OSError as err:
                self.hold(e, f"its evidence folder could not be made its own ({pl.unread(err)})")
                return
        self.log(e, n, "hooks").unlink(missing_ok=True)  # as with the end record below
        # The order readers rely on (the snapshot rule, panel_lib.py): the copy, then the attempt in
        # runs.json, and only then the process that may change the file.
        if number:  # the file as it is: all the follow-up may do is append one section to it. In one
            try:    # step: a copy on disk is whole
                pl.keep_copy(self.log(e, n, "before"), pl.persona_bytes(self.sd, self.sd / e["file"]))
            except OSError as err:  # no longer a file that can be read as the run's own: nothing to ask about
                why = f"its persona file could not be copied before the question ({pl.unread(err)})"
                say(f"{e['run']}: follow-up {number} could not be asked: {why}.")
                pl.record_followup(self.sd, number, e["run"], outcome="could not start", reason=why)
                return
        end.unlink(missing_ok=True)  # left by a process that never ran as the CLI: this attempt has its number
        # The attempt's lock file, which its watchdog locks for as long as it lives and nothing ever
        # writes (unseen()). Then the pid file, locked until the watchdog has recorded itself and the
        # CLI in it, and the CLI is running or has been refused. Each is made anew: a link left at
        # its name is not written through, and a lock file an earlier use of this number left is not this one.
        watch = watchdog.fresh(self.log(e, n, "lock"))
        handle = watchdog.fresh(pid_file, os.O_RDWR)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX)
        except OSError:
            pass
        self.snapshot([c.entry["run"] for c in self.children])
        e["attempts"] = [*(e.get("attempts") or []), {
            "n": n, "kind": kind, "started": round(time.time(), 3), "allowed": round(remaining["seconds"], 3),
            "ended": None, "seconds": None, "exit_code": None, "outcome": None, "state": None,
            "session": command["session_id"], "was": {k: e[k] for k in UNDONE if k in e},
            **({"followup": number} if number else {}),
            **({"evidence_aside": aside} if aside else {}),
            # What its step log held already: the step limit is watched in what this attempt adds (over_steps()).
            **({"steps": {"seen": "".join(marks(self.log_lines(e))), "begun": {}}} if usability and not number
               else {})}]
        e.update(pid=None, pid_identity=None)
        if number:  # the run stays as it is: asking() is what says a process is at work on it
            pl.record_followup(self.sd, number, e["run"], attempt=n, session=command["session_id"])
        else:
            e.update(state="running", session=command["session_id"], reason=None, reset_at=None)
            # With a new account, the check of a task the run has written up, and so will not attempt
            # again, is the only one there can be: the account it was made with is gone.
            # It is marked "kept", and stays through every later attempt: no check can be run for it again.
            keep, checks = renewed and kind == "resume" and account.get("source") == "provision", e.get("checks") or {}
            written = role.progress(self.cfg, e)["written"] if checks else []
            kept = {task: {**record, "kept": True} for task, record in checks.items()
                    if task in written and (keep or record.get("kept"))}
            for was in ("limited_by", "checks", "released"):  # of the state this attempt takes the run out of
                e.pop(was, None)
            if kind != "resume":  # a new session logs every task as attempt 1, in a step log that holds no other
                e.pop("task_attempts", None)
            if kept:
                e["checks"] = kept
        self.save()  # before the process exists, so a launcher killed from here on leaves the attempt on record
        proc, pids, refused = None, None, None
        try:
            # The CLI's three streams, each made anew (run_watchdog.py fresh()) and handed over by
            # descriptor: a link or a FIFO left at one of the names is unlinked, never written
            # through or waited for, and nothing is opened by name again.
            with os.fdopen(watchdog.fresh(self.log(e, n, "in"), os.O_RDWR), "w+") as stdin, \
                    os.fdopen(watchdog.fresh(self.log(e, n, "out")), "wb") as out, \
                    os.fdopen(watchdog.fresh(self.log(e, n, "err")), "wb") as err:
                stdin.write(command["stdin"] or "")
                stdin.flush()
                stdin.seek(0)
                proc = subprocess.Popen(
                    [*WATCHDOG, *(["--hooks", json.dumps(hooks)] if hooks else []), str(handle), str(watch),
                     str(end), f"{remaining['seconds']:.3f}", f"{self.grace:.3f}", *command["argv"]],
                    stdin=stdin, stdout=out, stderr=err, cwd=workdir, env=command["env"],
                    start_new_session=True, pass_fds=(handle, watch))
        except OSError as err:
            refused = str(err)
        finally:
            os.close(handle)
            os.close(watch)  # the watchdog's alone from here on: only its own end lets go of the lock
        if proc:
            pids = recorded(pid_file)  # returns once the CLI is running, or will never be
            while not pids and proc.poll() is None:  # only where the file system has no locks to wait on
                time.sleep(0.01)
                pids = recorded(pid_file)
            record = (end_record(end) or {}) if pids else {}
            refused = record.get("refused") if pids else (
                "it ended before it could start the CLI: "
                + (runners.last_line(printed(self.log(e, n, "err"))) or "no message"))
        if refused:  # a sandbox that will not start another CLI, a CLI that has gone, or no browser session
            if proc:
                proc.wait()
            if proc and pids:
                self.not_executed(e, record)
            else:
                self.unstarted(e, command["argv"], "The system refused this command", refused)
            self.browser_left(e, n)
            return
        e.update(pid=pids["cli"][0], pid_identity=pids["cli"][1])
        self.save()
        self.children.append(Child(e, pids, end, proc))
        say(f"{e['run']}: asked follow-up {number} (attempt {n}, pid {e['pid']})" if number
            else f"{e['run']}: running ({kind}, attempt {n}, pid {e['pid']})")

    def unstarted(self, e: dict, argv: list[str], how: str, said: str, settling: bool = False,
                  closing: str = "its CLI could not be started"):
        """Put a run back as it was before an attempt whose process never ran as the CLI, say
        so, and start nothing more on its runner in this command, for the reason in closing.
        how is what happened to the command, and said the system's or the CLI's own message.
        settling is for an attempt of an earlier launcher: the runner stays open, since this
        launcher has not tried it."""
        self.take_back(e, f"{how} ({said})")
        say(f"{e['run']}: could not be started. {how}: {shlex.join(argv[:4])} ... ({said}). Nothing was marked as "
            f"failed. {pl.SANDBOX_HINT}")
        if not settling:
            self.refused = True
            self.close(e["runner"], closing, "in this command")

    def not_executed(self, e: dict, record: dict, settling: bool = False):
        """unstarted(), for an attempt whose end record says that its CLI was never executed: the
        system refused the command, or the watchdog's "before" command, which is the start of
        the attempt's browser session, failed or was cut short with its watchdog (outcome())."""
        hooked = (record.get("hooks") or {}).get("before")
        if hooked:
            self.unstarted(e, [*browser.SCRIPT, "start"], "Its browser session could not be started", hooked,
                           settling, "a browser session could not be started for its run")
        else:
            self.unstarted(e, record["argv"], "The system refused this command", record["refused"], settling)

    def browser_left(self, e: dict, n: int) -> dict | None:
        """Stop the browser session of an attempt whose watchdog did not: it was killed, or its
        "after" command failed. Says what was found, and returns it as {"found", "left", "kept"}:
        whether a session was still running, the pids that could not be ended, and what was left
        in place, each with its reason (browser_session.py). With "refused", the reason, when the
        session's record cannot be trusted: nothing of it was then touched. With "by":
        "watchdog", what a session that its watchdog did stop has left. None when the attempt
        has no session on record, or it was stopped with nothing left.

        The daemon and the browser on the session's record are processes of the attempt, in the
        namespace its watchdog recorded. Where that is another than this shell's (elsewhere()),
        neither id is looked up or signalled here, as the CLI's is not (outcome()): the session
        is stopped by its socket alone, if it answers there (browser_session.py stop() apart)."""
        log = self.base(e, n)
        self.log(e, n, "state").unlink(missing_ok=True)  # the copy of a saved state that no session loaded
        if not browser.unstopped(log):
            rest = browser.remains(log)
            if rest:
                say(f"{e['run']}: its browser session was stopped, but {remainder(rest)}.")
            return {**rest, "by": "watchdog"} if rest else None
        record = browser.record_of(log)
        try:
            result = browser.stop(log, apart=elsewhere(recorded(self.log(e, n, "pid"))))
        except browser.Refused as err:
            if str(record) not in self.distrusted:
                say(f"{e['run']}: the record of its browser session cannot be trusted ({err}), so nothing of the "
                    "session was stopped or removed. Look for a browser it left with ps, then delete the record.")
            self.distrusted.add(str(record))
            return {"found": False, "left": [], "kept": [], "refused": str(err)}
        except OSError as err:
            say(f"{e['run']}: the record of its browser session could not be read ({err.strerror or err}): look for "
                f"a browser it left with ps, and see {record}.")
            return None
        rest = {"found": result["found"], "left": result["left"], "kept": result["kept"]}
        if result["found"] or result["left"] or result["kept"]:
            say(f"{e['run']}: its watchdog left its browser session " + ("running" if result["found"] else "behind")
                + (f", and the launcher could not end or remove all of it: {remainder(rest)}."
                   if result["left"] or result["kept"] else ", and the launcher stopped it."))
        return rest

    def sweep_browsers(self):
        """Stop every browser session still on record in logs/ that belongs to no attempt with a
        process alive: one whose attempt was taken back, or whose runs.json was replaced. The
        copies of saved browser states left the same way are deleted."""
        entries = {e["run"]: e for e in self.runs}

        def owned(name, n):  # by an attempt whose watchdog is alive, and will see to it
            e = entries.get(name)
            if not (e and in_flight(e) and e["attempts"][-1]["n"] == int(n)):
                return False
            pids = recorded(self.log(e, int(n), "pid"))
            return bool(pids) and living(pids)

        for record in sorted((self.sd / "logs").glob("*.browser")):
            name, _, n = record.name[:-len(".browser")].rpartition(".")
            if n.isdigit() and browser.unstopped(record.with_suffix("")) and not owned(name, n):
                self.browser_left(entries.get(name) or {"run": name}, int(n))
        for copy in sorted((self.sd / "logs").glob("*.state")):  # a saved state copied for a session never started
            name, _, n = copy.name[:-len(".state")].rpartition(".")
            if not (n.isdigit() and owned(name, n)):
                copy.unlink(missing_ok=True)

    # ---- the test accounts of a usability study (accounts.py)

    def recover(self, must: bool = True):
        """What a usability study's launcher does before anything else (accounts.py): end a
        command of the study that an earlier launcher left running, and wait for it, so that
        none is ever started beside it. Then finish every teardown that was cut short, whatever
        state its run is in: its command may have removed the account already, so the account
        is not one to carry on with. A teardown that fails here is said like any other, and
        leaves the account owed one (accounts.owed()).

        accounts.recover() exits when it cannot prove that command gone, and so does every
        launcher command but one. must false is for "stop": the reason is kept in self.held, and
        while it is there this launcher starts no command of the study (check(), release()).
        The runs it settles keep their accounts in force, and the success checks and teardowns
        that are due stay due: the next launcher command sees to them, as after a launcher
        that was killed (settle_final())."""
        if self.cfg["type"] != "usability":
            return
        try:
            for line in accounts.recover(self.cfg, self.grace):
                say(line)
        except accounts.Held as held:
            if must:
                raise
            self.held = str(held)
            return
        entries = {e["run"]: e for e in self.runs}
        for record in accounts.records(self.sd):
            e = entries.get(record["run"]) or {"run": record["run"], "role": "panellist"}
            if record.get("cleanup") and accounts.in_force(record) and not in_flight(e):
                say(f"{e['run']}: a teardown of its test account was cut short, so it is done again from the start.")
                self.release(e)

    def known(self) -> dict | None:
        """What a scan knows the study's secrets by, for showing what a panellist wrote
        (pl.shown()). None when the fingerprint record cannot be used: nothing a panellist wrote
        is then repeated at all."""
        try:
            return accounts.known(self.cfg)
        except (SystemExit, OSError):
            return None

    def repeated(self, e: dict, n: int, said: str) -> str:
        """A harness's own message about attempt n of a run, as the launcher prints it and keeps
        it: in a reason in runs.json and followups.json, and so in "status". Every such message
        comes from the runner's parse_result() and passes through here first (ended()).

        In a usability study it can hold a secret of a test account, which the panellist read
        or typed and the harness repeats as it fails. So a message that holds a secret a scan
        knows (pl.secrets_in(), the search check_runs.py makes) is withheld: what is printed
        and kept says so, and names the lead-only files of the attempt that have the harness's
        words. So is every message when the fingerprint record cannot be used, as nothing can
        then be looked for. A message with no known secret, and any message of a review
        study, is repeated as it is."""
        if self.cfg["type"] != "usability" or not said.strip():
            return said
        known = self.known()
        if known is not None and not pl.secrets_in(known, said):
            return said
        files = " or ".join(f"logs/{e['run']}.{n}.{ext}" for ext in ("err", "out"))
        return ("the harness's message is withheld because "
                + ("it holds a secret of a test account" if known is not None else
                   "it could not be checked for the secrets of the test accounts")
                + f": it is in {files}, which are yours alone to read")

    def prepare(self, e: dict, kind: str):
        """What a usability run needs before an attempt of it starts: accounts.reset, when the
        study is sequential and another run has used the product since, and its test account,
        provisioned when it has none in force. Returns the account's record, None for a study
        without accounts, and False when either could not be done: the run is then not started.

        An account that is owed a teardown (accounts.owed(): one failed, or was cut short) is
        never carried on with. The teardown is tried again first, once in a command, and only
        when it has worked is the run provisioned again. While it fails the run is left as it
        is, and other runs go ahead."""
        acc = self.cfg["accounts"] or {}
        if acc and accounts.owed(accounts.read(self.sd, e["run"])):
            if e["run"] not in self.let_go:
                self.release(e)
            if accounts.owed(accounts.read(self.sd, e["run"])):
                self.left_alone = True
                say(f"{e['run']}: not started. Its test account was to be torn down and still is not, and a run "
                    f"never carries on in such an account. It stays {state_of(self.cfg, e)}. Once the teardown "
                    "works, the same command tears the account down, gives the run a new one and starts it.")
                return False
        try:
            if acc.get("reset") and self.reset_due(e, kind):
                accounts.reset(self.cfg, e["run"])
                say(f"{e['run']}: accounts.reset was run before it")
            if not acc:
                return None
            record = accounts.read(self.sd, e["run"])
            if accounts.in_force(record):
                accounts.lend(self.cfg, record)  # as it was provisioned: a file that went missing is put back
            else:
                record, notes = accounts.provision(self.cfg, e["run"])
                for note in notes:
                    say(f"{e['run']}: {note}.")
                say(f"{e['run']}: test account provisioned ({self.account_start(record)})")
        except accounts.Failed as err:
            self.hold(e, err)
            return False
        e["account"] = accounts.summary(record)
        self.save()
        return record

    @staticmethod
    def account_start(record: dict) -> str:
        return {"signed_in": "its browser session starts signed in, and its panellist is given no secret",
                "secrets": "its panellist is given the secrets to sign in with",
                "signed_out": "it names no saved browser state, so its panellist starts signed out with nothing to "
                              "sign in with"}[record["start"]]

    def reset_due(self, e: dict, kind: str) -> bool:
        """Whether another run has used the product since this run last did, so that a sequential
        study's accounts.reset runs before its attempt: any run has had an attempt, unless this
        attempt resumes the run that had the last one."""
        ran = [(a["started"], x["run"]) for x in self.runs if x["role"] == "panellist"
               for a in x.get("attempts") or [] if a["kind"] != "followup"]
        return bool(ran) and not (kind == "resume" and max(ran)[1] == e["run"])

    def hold(self, e: dict, why):
        """Say that a run could not be started because something the study itself supplies
        failed, and start no further panellist run in this command: the next would fail the
        same way. Nothing is marked failed."""
        self.refused = True
        held = [x["run"] for x, _ in self.queue if x["role"] == "panellist"]
        self.queue = [item for item in self.queue if item[0]["role"] != "panellist"]
        say(f"{e['run']}: could not be started: {why}. Nothing was marked as failed. No further run is started in "
            "this command"
            + (f", and {plural(len(held), 'queued run')} {agree(len(held), 'stays as it is', 'stay as they are')} "
               f"({', '.join(held)})." if held else "."))

    def release(self, e: dict):
        """Let go of the test account of a run that has reached a final state (accounts.teardown):
        once for each provisioning. A teardown that failed leaves the account in force, so the
        next launcher that settles the run tries again."""
        if self.cfg["type"] != "usability" or e["role"] != "panellist":
            return
        if self.held:  # no command of the study is started beside what an earlier one may have left (recover())
            due = [what for what, there in (
                ("its success checks were not run", any("success_check" in t and t["id"] not in (e.get("checks") or {})
                                                        for t in self.cfg["tasks"])),
                ("its test account stays in force", accounts.in_force(accounts.read(self.sd, e["run"])))) if there]
            if due and e["run"] not in self.let_go:
                say(f"{e['run']}: {' and '.join(due)}, because no command of the study is started beside a process "
                    "that an earlier one may have left. The next launcher command sees to it.")
            self.let_go.add(e["run"])
            return
        self.let_go.add(e["run"])
        record = accounts.teardown(self.cfg, e["run"])
        if not record:
            return
        if "file" in e:  # an entry of runs.json: a record whose run is no longer there has none to note it in
            e["account"] = accounts.summary(record)
            self.save()
        failed = record.get("teardown_error")
        if failed:
            say(f"{e['run']}: TEARDOWN OF ITS TEST ACCOUNT FAILED: {failed}. The account may still work. The next "
                "launcher command tries again: fix accounts.teardown, or remove the account by hand.")
        else:
            say(f"{e['run']}: its test account was " + ("torn down" if record["teardown"] == "ran" else
                                                         "let go (the study has no accounts.teardown)"))

    def check(self, e: dict, again: bool = False, force: bool = False) -> dict:
        """Run the success check of each task that has one, for a run in a final state, and
        record what each said in the run's entry under "checks" (accounts.check()), one task at
        a time. A task that has its record already is left alone unless again. Even then a
        verdict is kept, and said to be, once the account it was made with is gone (torn down,
        or replaced by a new one when the run was continued): a check run now cannot see what
        the run did. force runs it all the same, and says that the verdict was replaced. A task
        with no verdict on record is tried either way. Returns the records made: {task id:
        record}. None is run while a command an earlier launcher left is unaccounted for
        (recover(), self.held): release() says so."""
        made, kept = {}, 0
        if self.cfg["type"] != "usability" or e["role"] != "panellist" or self.held:
            return made
        torn_down = accounts.gone(accounts.read(self.sd, e["run"]))
        for t in self.cfg["tasks"]:
            had = (e.get("checks") or {}).get(t["id"])
            if "success_check" not in t or (had and not again):
                continue
            verdict = VERDICTS.get(had.get("checked")) if had else None  # None for a check that failed to run
            gone = torn_down or bool(had and had.get("kept"))
            if verdict and gone and not force:
                kept += 1
                say(f"{e['run']}: task {t['id']} kept: the account is gone, so the check cannot be run again. Its "
                    f"verdict stands: {verdict}.")
                continue
            made[t["id"]] = e.setdefault("checks", {})[t["id"]] = result = accounts.check(self.cfg, t, e["run"])
            self.save()
            replaced = (f" The earlier verdict, {verdict}, was replaced: it was made while the run's account was "
                        "there." if verdict and gone else "")
            if result["error"]:
                say(f"{e['run']}: SUCCESS CHECK FAILED TO RUN: {result['error']}. No verdict is recorded for task "
                    f"{t['id']}, and none is assumed."
                    + (" The run's account is gone, and a check that needs it cannot be run again." if gone else
                       f" Fix the check, then: launch.py {self.sd} check --runs {e['run']}") + replaced)
            else:
                after = (" The run's account is gone, so the check may not have seen what the run did." if gone
                         else "") + replaced
                say(f"{e['run']}: task {t['id']} checked: {VERDICTS[result['checked']]}" + (after and "." + after))
        if kept and state_of(self.cfg, e) in accounts.FINAL:  # "check" takes no unfinished run
            say(f"{e['run']}: to run {agree(kept, 'that check', 'those checks')} all the same: launch.py {self.sd} "
                f"check --runs {e['run']} --force")
        return made

    def finish(self, e: dict):
        """What follows a run reaching a final state: the success checks of its tasks, which may
        need its test account, and only then the account let go."""
        self.check(e)
        self.release(e)

    def settle_final(self):
        """What a launcher that was killed or stopped before its finish() left to do, for every
        run that is in a final state: the success checks that have no record yet, then its
        account let go when one is still in force. A check is not caught up on once the run's
        account is gone: it would judge the run without what the run did. "check" runs those.
        A run this launcher has itself just finished is left alone: a teardown that failed is
        tried again by the next command, not twice in this one. A run the lead released while
        it was unfinished is seen to the same way."""
        for e in self.runs if self.cfg["type"] == "usability" else []:
            if e["run"] in self.let_go:
                continue
            if e["role"] == "panellist" and not in_flight(e) and (
                    state_of(self.cfg, e) in accounts.FINAL or e.get("released")):  # or let go by the lead ("release")
                if not self.cfg["accounts"] or accounts.in_force(accounts.read(self.sd, e["run"])):
                    self.check(e)
                self.release(e)

    # ---- the evidence of a usability run that is started afresh

    def set_aside(self, e: dict) -> str | None:
        """Give a usability run that is about to be started afresh an evidence folder that holds
        nothing: a new session logs every task as attempt 1 and names its screenshots as the
        earlier one did, so what an earlier session left would mix with its steps and be
        written over. Whatever is at the folder's name is moved, as it is, to
        logs/<run id>.<attempt>.evidence, named for the last attempt the run has had, with a
        number after it when an earlier scaffold left that name taken, and the folder is made
        anew. Returns that name, relative to the study directory, or None when the folder held
        nothing.

        As with a persona file, nothing a run left is deleted by the launcher: what is set
        aside is the lead's to look at, is never read as evidence, and is never archived or
        scanned, like everything in logs/. The evidence root is opened without following a
        link and the folder is moved by its name in it, so a link put where the folder was is
        moved as a link and nothing is reached through it. Raises OSError when the root cannot
        be read as the study's or the folder cannot be moved: the caller then starts nothing.

        The attempt notes the name ("evidence_aside") and take_back() puts the folder back, so a
        run whose attempt never ran as the CLI is as it was. A launcher killed between this and
        that note leaves the earlier evidence in logs/ and loses none of it."""
        run, last = e["run"], len(e.get("attempts") or [])
        root = pl.evidence_fd(self.sd, None)
        try:
            try:
                held = bool(pl.evidence_names(self.sd, run))
            except OSError:  # a link or a file where its folder was, or a folder that may not be listed: as it is
                held = True
            kept = None
            if held:
                (self.sd / "logs").mkdir(exist_ok=True)
                taken = (f"logs/{run}.{last}.evidence" + (f".{i}" if i else "") for i in range(1 << 16))
                kept = next(name for name in taken if not os.path.lexists(self.sd / name))
                os.rename(run, self.sd / kept, src_dir_fd=root)
            try:
                os.mkdir(run, dir_fd=root)
            except FileExistsError:
                pass
        finally:
            os.close(root)
        if kept:
            say(f"{run}: it starts afresh, so what its evidence folder held was set aside in {kept}, which is yours "
                "alone to read. Its step log and screenshots begin again, and nothing set aside is read as evidence "
                "or archived.")
        return kept

    def put_back(self, e: dict, kept: str):
        """Undo set_aside() for an attempt that never ran as the CLI: the folder made for it,
        which then holds nothing, goes, and what was set aside is the run's evidence again."""
        if not os.path.lexists(self.sd / kept):
            return  # put back already, by a launcher that was killed before it could note it
        try:
            root = pl.evidence_fd(self.sd, None)
            try:
                try:
                    os.rmdir(e["run"], dir_fd=root)
                except FileNotFoundError:
                    pass
                os.rename(self.sd / kept, e["run"], dst_dir_fd=root)
            finally:
                os.close(root)
            say(f"{e['run']}: it was not started after all, so what was set aside in {kept} is its evidence again.")
        except OSError as err:
            say(f"{e['run']}: what its evidence folder held before this attempt could not be put back "
                f"({pl.unread(err)}). It stays in {kept}.")

    # ---- the step limit of a usability task

    def log_lines(self, e: dict) -> list[str]:
        """The whole lines of a run's step log as an attempt of it starts, which the backstop then
        takes as read. Empty when there is no log, and when there is one that cannot be read as
        the run's: the backstop stops the run for that as soon as it looks (over_steps())."""
        try:
            return pl.step_lines(self.sd, e["run"])[0]
        except OSError:
            return []

    def over_steps(self, child: Child) -> dict | None:
        """The backstop of a task's step limit. A panellist keeps to the limit itself. When the
        run's step log shows that it did not, returns {"limit": "steps", "task", "attempt",
        "step", "of"}: the first "intent" entry this attempt added that begins a step beyond
        its task's limit (pl.steps_begun()), with the attempt the launcher has issued for the
        task. None otherwise.

        What counts is what this process added, by the entries themselves and never by the
        attempt number they carry, which is the launcher's to issue: an entry with a number of
        its own choosing is one more step of the task, and starts no count again. A line that
        is no entry, and an entry with no whole step number or with a phase that is neither,
        begin no step and hide none.

        The count is the launcher's own and only goes up. It is on record in the attempt
        ("steps": the marks of the log's lines as last read, and the steps of each task begun
        so far), never in panel/, so whichever launcher watches the run goes on from it. Each
        look sets the log's whole lines against the marks: lines after the ones read are new,
        and are counted. A log that no longer holds what was read of it, cut short or changed
        at an earlier line, is noted on the attempt ("rewritten"), said the first time, and
        read again from the first line that differs: what it holds from there on is counted on
        top of what was counted, so a log that is emptied or written again starts no count
        again. A log found shorter and otherwise the same is looked at once more at the next
        poll before that: a file that a tool is writing again reads so for an instant. What
        stands after the last line feed, an entry still being written, counts towards the
        decision at once, and for good when its line is whole.

        The log is read only when it has changed, and never through a symbolic link, at its own
        name or at its folder's (pl.step_log()). A run with no log yet has begun no step. A log
        that is there and cannot be read as the run's own (a link, a FIFO, a file that may not
        be read, or its folder one) would leave the run with no backstop, so it stops the run
        as well: {"limit": "steps", "unread": why}. Nothing else in a log stops a run: a line
        that is no entry, an entry for a task the study does not have and a step number that
        goes backwards are for the analysis (pl.step_notes), and ended() says them once.

        It counts what the log shows and nothing more: a panellist that logs no step at all is
        bounded by the run's time limit alone."""
        e = child.entry
        attempt = e["attempts"][-1]
        try:
            stamp = pl.step_log_stamp(self.sd, e["run"])
            if stamp == child.log_seen and not child.cut:
                return None
            lines, rest = pl.step_lines(self.sd, e["run"])
        except OSError as err:
            return {"limit": "steps", "unread": pl.unread(err)}
        settled, child.log_seen = stamp == child.log_seen, stamp
        watch = {"seen": "", "begun": {}, **(attempt.get("steps") or {})}
        seen, now = [watch["seen"][i:i + MARK] for i in range(0, len(watch["seen"]), MARK)], marks(lines)
        same = next((i for i, (was, held) in enumerate(zip(seen, now)) if was != held), min(len(seen), len(now)))
        child.cut = same == len(now) < len(seen) and not settled
        if child.cut:  # shorter, and the same as far as it goes: perhaps caught while it was being written
            return None
        begun, changed = dict(watch["begun"]), same < len(seen)
        over = pl.steps_begun(self.cfg, pl.steps_of(lines[same:])[0], begun)
        if changed or same < len(now):
            attempt["steps"] = {**watch, "seen": "".join(now), "begun": begun,
                                **({"rewritten": watch.get("rewritten", 0) + 1} if changed else {})}
        if changed and not watch.get("rewritten"):
            say(f"{e['run']}: its step log was "
                + (f"cut short, to {same} of" if same == len(now) else f"changed at line {same + 1}, among")
                + f" the {plural(len(seen), 'line')} the launcher had read. The steps it had begun stay counted, and "
                "what the log holds from there on is counted on top.")
        if not over and rest.strip():
            over = pl.steps_begun(self.cfg, pl.steps_of([rest])[0], dict(begun))
        return over and {"limit": "steps", "task": over["task"],
                         "attempt": pl.issued_attempts(e).get(over["task"], 1), "step": over["step"], "of": over["of"]}

    def step_limit(self, child: Child):
        """Stop a usability run that has gone past a task's step limit, or whose step log cannot
        be read as its own (over_steps()), through its watchdog, as a time limit stops one:
        SIGTERM, the grace, SIGKILL.

        The decision is on record in the attempt, under "stop", before the watchdog is asked,
        because the end record a watchdog writes says only that it was asked to stop: ended()
        goes by the decision, whichever launcher settles the attempt. It is written with the
        count that led to it, in one step. A launcher that finds a decision it did not make,
        with the process still alive once the grace has passed, asks again: had the first
        request arrived, the process would be gone."""
        e = child.entry
        if self.cfg["type"] != "usability" or e["role"] != "panellist" or asking(e) or child.asked:
            return
        attempt = e["attempts"][-1]
        decision = attempt.get("stop")
        if not decision:
            counted = attempt.get("steps")
            decision = self.over_steps(child)
            if decision:
                attempt["stop"] = decision = {**decision, "at": round(time.time(), 3), "grace": self.grace}
            if decision or attempt.get("steps") is not counted:
                self.save()
            if not decision:
                return
            say(f"{e['run']}: stopping, {step_reason(decision)}")
        elif time.time() < decision["at"] + decision["grace"] + REPLAY:
            return
        child.asked += 1
        try:
            os.kill(child.pids["watchdog"][0], signal.SIGTERM)
        except OSError:
            pass

    def take_back(self, e: dict, why: str):
        """undo() the run's last attempt, whose process never did anything as the CLI, and write
        runs.json. One that was to put a follow-up question is recorded as not having started,
        with why, and the copy it made of the persona file goes: last, once runs.json no longer
        has the attempt, because until then the copy is what readers read (pl.read_persona).
        One that was to start a usability run afresh gives the run back the evidence that was
        set aside for it (put_back())."""
        attempt = e["attempts"][-1]
        undo(e)
        if attempt.get("evidence_aside"):  # it was to start the run afresh: the run has its evidence again
            self.put_back(e, attempt["evidence_aside"])
        if attempt["kind"] == "followup":
            pl.record_followup(self.sd, attempt["followup"], e["run"], outcome="could not start", reason=why,
                               attempt=None)
        self.save()
        if attempt["kind"] == "followup":
            self.log(e, attempt["n"], "before").unlink(missing_ok=True)

    def cannot_continue(self, e: dict, lacks: str):
        """Say that a run with sections written has no session to continue, and leave it alone."""
        self.left_alone = True
        say(f"{e['run']}: {state_of(self.cfg, e)} with sections written, but {lacks}, so it cannot be continued. "
            "Left alone: finish it by hand or reset it.")

    def session_lost(self, e: dict, settling: bool):
        """A resume found its session gone from the harness. The attempt is taken back and the
        session noted, as purge-sessions notes one it deleted. The run is then started afresh
        when it has written nothing, and otherwise left for the lead to decide."""
        session, asked = e["session"], asking(e)
        self.take_back(e, LOST)
        e.setdefault("lost", {})[session] = round(time.time())
        self.save()
        if asked:
            say(f"{e['run']}: follow-up {asked['followup']} could not be asked: {LOST}.")
        elif progress_of(self.cfg, e)["written"]:
            self.cannot_continue(e, LOST)
        elif settling or self.stop.asked or e["runner"] in self.closed:
            say(f"{e['run']}: {LOST} and it has written nothing. Next: resume, which starts it afresh.")
        else:
            say(f"{e['run']}: {LOST} and it has written nothing, so it is started afresh.")
            self.queue.insert(0, (e, "restart"))

    def close(self, name: str, why: str, how_long: str, then: str = ""):
        """Start nothing more on a runner in this command. Its queued runs keep their state.
        then is what the user can do about it, said after the rest, once."""
        if name in self.closed:
            return
        self.closed[name] = why
        held = [e["run"] for e, _ in self.queue if e["runner"] == name]
        self.queue = [item for item in self.queue if item[0]["runner"] != name]
        stay = agree(len(held), "stays as it is", "stay as they are")
        say(f"{name}: {why}. No more launches on this runner {how_long}"
            + (f", and {plural(len(held), 'queued run')} {stay} ({', '.join(held)})" if held else "")
            + ". Other runners carry on." + (f" {then}" if then else ""))

    # ---- watching

    def watch(self):
        """Settle every attempt that has ended, and pass a request to stop on to the watchdogs
        of the others: once, and once more to skip the grace."""
        for child in list(self.children):
            record = self.outcome(child)
            if record:
                self.children.remove(child)
                if child.proc:  # its watchdog exits once the record is written: leave no zombie
                    try:
                        child.proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
                self.ended(child, record)
            elif self.stop.asked and child.asked < 1 + self.stop.force:
                if not child.asked:
                    say(f"{child.entry['run']}: stopping")
                child.asked += 1
                try:
                    os.kill(child.pids["watchdog"][0], signal.SIGTERM)
                except OSError:
                    pass
            else:
                self.step_limit(child)

    def outcome(self, child: Child) -> dict | None:
        """How a child's attempt ended: its end record, or None while its watchdog is at work.

        A watchdog that has gone without a record was killed. The CLI's process group is then
        killed here if it is certain to be the CLI's (kill_group()), and the record is made up:
        no exit code, no reason, "lost", and under "leftover" the processes that were left
        untouched, and under "unchecked" the groups of which nothing could be told, where no
        list of processes was to be had. Nothing says when the CLI ended, so the attempt is
        charged from its start to now, and no further than the allowance its watchdog was
        given. That is the most it can have used within its limit, so a run is never granted
        more time than its limit.

        A "before" command still on record (recorded()) was running when the watchdog was
        killed. Its group goes first, by the same rule, so that nothing is left to start a
        browser session once ended() has stopped what there is of one. The CLI was never
        executed: the record says so as a watchdog's own does, under "refused" and "hooks".

        A watchdog that recorded another process namespace than this shell's (elsewhere()) has
        gone like any other: its lock is free, or this launcher would not have the study
        (Lock.acquire()). What it left cannot be looked for here, where its ids name no process
        or someone else's. So no group is looked up or signalled, and the record names the ids
        under "elsewhere", as they were in that namespace: the CLI, and a "before" command still
        on record. ended() says so, and stops its browser session without the ids on that
        session's record (browser_left())."""
        watched = child.watched()
        record = end_record(child.end)  # read second: a watchdog writes it before it goes
        if record or watched:
            return record
        attempt, hook = child.entry["attempts"][-1], child.pids.get("hook")
        apart = elsewhere(child.pids)
        behind = kill_group(*hook)[1] if hook and not apart else []
        killed, left = (False, []) if apart else kill_group(*child.pids["cli"])
        group = (child.pids["cli"][0], left) if left else (hook[0], behind) if behind else None
        cut_short = "its watchdog was killed while the session was being started"
        return {"ended": min(time.time(), attempt["started"] + attempt["allowed"]), "exit_code": None,
                "stopped": None, "lost": True, "killed": killed,
                "leftover": {"group": group[0], "pids": group[1]} if group else None,
                # The groups nothing could be told of: no list of processes was to be had (kill_group()).
                "unchecked": [pid for pid, rest in ((child.pids["cli"][0], left), ((hook or [None])[0], behind))
                              if rest is None],
                "elsewhere": [pid for pid in (child.pids["cli"][0], (hook or [None])[0]) if pid] if apart else [],
                **({"refused": cut_short, "hooks": {"before": cut_short, "after": None}} if hook else {})}

    def ended(self, child: Child, record: dict, settling: bool = False):
        """Record how an attempt ended and what state that leaves its run in. settling is for an
        attempt that ended under an earlier launcher: its run is classified and nothing more."""
        e, role, runner = child.entry, ROLES[child.entry["role"]], self.runner(child.entry["runner"])
        attempt, code, why = e["attempts"][-1], record.get("exit_code"), record.get("stopped")
        if record.get("leftover"):
            say(f"{e['run']}: its watchdog was killed, and {leftover(record['leftover'])}")
        if record.get("unchecked"):
            say(f"{e['run']}: its watchdog was killed, and {unchecked(record['unchecked'])}")
        if record.get("elsewhere"):
            say(f"{e['run']}: its watchdog was killed, and {unlooked(record['elsewhere'])}")
        # After the CLI has gone, as its watchdog would, and after a "before" command it left (outcome()).
        left_browser = self.browser_left(e, attempt["n"])
        if record.get("refused"):  # the launcher that started it died before it could say so
            self.not_executed(e, record, settling)
            return
        wrote, complained = (printed(self.log(e, attempt["n"], ext)) for ext in ("out", "err"))
        res = runner.parse_result(wrote, complained, code, attempt.get("session"))
        res["message"] = self.repeated(e, attempt["n"], res["message"])  # before it is printed or kept anywhere
        # The same of what shows that no run of this CLI can work from this shell (parse_result() "cannot_run").
        cause = self.repeated(e, attempt["n"], res["cannot_run"]).strip()
        number = attempt.get("followup")
        if attempt["kind"] in ("resume", "followup") and res["session_lost"]:
            self.session_lost(e, settling)
            return
        if code and code > 0 and not why and not wrote.strip() and res["session_id"] is None:
            # It exited with an error before printing a line: the CLI never ran, as in a sandbox
            # that lets it start and then refuses what it needs. Not an attempt, and not a failure.
            self.unstarted(e, record["argv"], f"Its CLI exited with code {code} before printing anything",
                           res["message"].strip() or "no message", settling)
            return
        stopped = bool(why or record.get("killed"))  # the CLI did not end by itself
        session = res["session_id"] or e.get("session")
        own = usage_of(e) if number else {}  # the run's own usage, before this process is counted
        spend = any(res["usage"].get(f) is not None for f in runners.USAGE_FIELDS if f != "duration_s")
        before = {}  # what the session had reported before this process
        if session or any(res["usage"].get(f) is not None for f in runners.USAGE_FIELDS):
            sessions, key = e.setdefault("sessions", {}), session or f"attempt {attempt['n']}"
            before = sessions.get(key) or {}
            sessions[key] = runners.merge_usage(before, res["usage"])
        ending = ("it was stopped at its time limit" if why == "time"
                  else "it was stopped by the stop command" if why == "stop"
                  else None if res["outcome"] == "ok" else ENDINGS[res["outcome"]])
        said = res["message"].strip() if res["outcome"] != "ok" else ""
        detail = ((f": {cause or said}" if cause or said else "") + (f" (exit code {code})" if code else "")
                  + (" (its watchdog was killed, so how it ended is not on record"
                     + (f", and {APART}" if record.get("elsewhere") else "") + ")" if record.get("lost") else ""))
        if number:  # the run is as it was, whatever the process did: what is settled is the answer
            answer, about = self.answered(e, attempt, res, ending, said)
            note, state, reason = e.get("note"), state_of(self.cfg, e), e.get("reason")
            # What this process used: what its session has reported now, less what it had before. A
            # total that also brings the spend of an earlier process of the run, stopped before it
            # reported any, cannot be told apart from it. It is then neither the follow-up's nor
            # the run's: it goes on record as "unallocated" (panel_lib.py), so the run's own
            # usage reads as it did before the question.
            owed = res["usage"].get("scope") == "session" and any(
                a.get("session") == session and a.get("usage_reported") is False and a["kind"] != "followup"
                for a in e["attempts"][:-1])
            now = (e.get("sessions") or {}).get(session or f"attempt {attempt['n']}") or {}
            used = {f: None if res["usage"].get(f) is None
                    else res["usage"][f] if f == "duration_s" else max(0, round(now[f] - (before.get(f) or 0), 9))
                    for f in runners.USAGE_FIELDS}
            spent = [f for f in runners.USAGE_FIELDS if f != "duration_s"]
            attempt.pop("unallocated", None)
            if owed and any(used[f] is not None for f in spent):
                attempt["unallocated"] = {**{f: used[f] for f in spent},
                                          "run_unreported": [f for f in runners.USAGE_FIELDS if own[f] is None]}
                used.update(dict.fromkeys(spent))
            attempt.update(answer=answer, usage=used)
        else:
            note = role.collect(self.cfg, e, res, ending)
            # The launcher's own reason to stop it, on record before it asked (step_limit()): a time
            # limit that came first stands.
            over = attempt.get("stop") if why != "time" else None
            state = pl.run_state(role.progress(self.cfg, e), ended={
                "limit": why == "time" or bool(over), "outcome": res["outcome"], "stopped": why == "stop"})
            limited_by = None if state != "limited" else "time" if why == "time" else "steps" if over else "budget"
            reason = (None if state == "done"
                      else f"time limit reached ({allowance(self.cfg, e)['minutes']:g} min over all attempts)"
                      if limited_by == "time"
                      else step_reason(over) if limited_by == "steps"
                      else f"budget reached{detail}" if state == "limited"
                      else TURNED_AWAY + (f" ({said})" if said else "") if state == "blocked"
                      else "stopped by the stop command" if why == "stop"
                      else f"the process ended before the run was complete{detail}" if state == "partial"
                      else f"the process ended with nothing written{detail}")
        attempt.pop("was", None)
        (attempt.get("steps") or {}).pop("seen", None)  # the backstop's place in the step log: no use from here on
        attempt.update(ended=round(record["ended"], 3),
                       seconds=round(max(0.0, record["ended"] - attempt["started"]), 3), exit_code=code,
                       outcome=res["outcome"], state=state, session=session)
        if record.get("lost"):
            attempt["end_record"] = False  # its watchdog was killed: the end time is the most it can have been
            if record.get("leftover"):
                attempt["leftover"] = record["leftover"]
        if left_browser:
            attempt["browser_left"] = left_browser
        if spend and res["usage"].get("scope") == "session":  # a running total: it holds what earlier
            for earlier in e["attempts"][:-1]:                # processes of the session never reported
                if session and earlier.get("session") == session and earlier.get("usage_reported") is False:
                    earlier["usage_reported"] = True
        elif stopped and not spend:
            attempt["usage_reported"] = False  # stopped before it reported: unknown, and not none
        e.update(pid=None, pid_identity=None, session=session, seconds_used=round(
            sum(a["seconds"] or 0 for a in e["attempts"] if a["kind"] != "followup"), 3))
        # Its process did its work in a session that its harness did not keep: nothing can continue it.
        # Not noted for a failed run, which "run" starts afresh in a session of its own.
        unsaved = res["session_saved"] is False and bool(session) and (bool(number) or state != "failed")
        if unsaved:
            e.setdefault("unsaved", {})[session] = round(time.time())
        if number:  # the file is as the outcome says (answered()): the outcome, then the attempt's end
            pl.record_followup(self.sd, number, e["run"], outcome=answer, reason=about, attempt=attempt["n"],
                               session=session, settling=None)
        else:
            e.update(state=state, reason=reason, reset_at=res["reset_at"] if state == "blocked" else None)
            if limited_by:
                e["limited_by"] = limited_by
            if note or e.get("note"):
                e["note"] = note
        self.save()
        if number:  # runs.json has the attempt's end, so readers read the file again: the copy can go
            self.log(e, attempt["n"], "before").unlink(missing_ok=True)
        self.snapshot([*(c.entry["run"] for c in self.children), e["run"]])
        record_usage(self.cfg, self.runs)
        # No run of this CLI can work from this shell, and this one did not: a retry would end the same way.
        shut = bool(cause) and not settling and (answer not in pl.FOLLOWUP_ANSWERED if number else state != "done")
        retry = (state == "failed" and self.retry and not settling and e["run"] not in self.retried and not number
                 and not self.stop.asked and res["outcome"] != "usage_limit" and e["runner"] not in self.closed
                 and not cause)
        usability = self.cfg["type"] == "usability" and e["role"] == "panellist"
        owes = usability and bool(self.cfg["accounts"])  # a retry waits for the teardown of the account it had
        if number:
            say(f"{e['run']}: " + (f"FOLLOW-UP {number} REJECTED" if answer == "rejected"
                                   else f"follow-up {number} {answer}") + (f": {about}" if about else ""))
        else:
            say(f"{e['run']}: {state}" + (f": {reason}" if reason else "") + (f" ({note})" if note else "")
                + ("; retrying once" if retry and not owes else "; not retried" if shut and state == "failed" else ""))
            if usability:
                for wrong in pl.step_notes(self.cfg, *pl.read_steps(self.sd, e["run"]), pl.issued_attempts(e),
                                           self.known()):
                    say(f"{e['run']}: its step log has {wrong}. Nothing was stopped for it: extract_scores.py "
                        "records it for the analysis.")
            if state in accounts.FINAL and retry:  # its account goes, and the retry is given another: no check yet
                self.release(e)
                if accounts.in_force(accounts.read(self.sd, e["run"])):  # the teardown failed, and release() said so
                    retry = False
                    say(f"{e['run']}: not retried: a retry would carry on in an account that was to go. It stays "
                        f"failed. Once the teardown works, launch.py {self.sd} run tears the account down, gives the "
                        "run a new one and starts it.")
                elif owes:
                    say(f"{e['run']}: retrying once, with a new test account")
            elif state in accounts.FINAL:  # the state is on record: a launcher killed before this leaves it to the next
                self.finish(e)
        if unsaved:
            say(f"{e['run']}: {UNSAVED}. {e['runner']} kept no session for it, so purge-sessions has nothing of "
                "it to delete either.")
        if res["outcome"] == "usage_limit" and not settling:
            self.close(e["runner"], TURNED_AWAY
                       + (f", and said its limit lifts at {clock(res['reset_at'])}" if res["reset_at"] else ""),
                       "for now")
        elif shut:
            self.close(e["runner"], NO_RUN_HERE, "in this command", pl.SANDBOX_HINT)
        elif retry:
            self.retried.add(e["run"])
            self.queue.insert(0, (e, "retry"))

    def answered(self, e: dict, attempt: dict, res: dict, ending: str | None, said: str) -> tuple[str, str | None]:
        """Settle what a follow-up attempt left in its run's persona file: (outcome, reason), the
        outcome one of pl.FOLLOWUP_OUTCOMES. The file ends as the copy made before the question,
        with or without one "## Follow-up <n>" section after it, and as nothing else. ending is
        how the process ended when that was not a clean finish, said its harness's message.

        The decision is on record before anything is done to the file, and is never made twice
        (the steps are in panel_lib.py, "Settling"). decide() makes it and changes nothing, it is
        written to followups.json as "settling", and act() carries it out. A launcher that died
        after recording it left the file in a state decide() would read differently: a rejected
        file already put back reads as a panellist that wrote nothing. So a decision found on
        record is carried out as it stands, and an outcome found on record is returned. The
        caller then records the outcome and the attempt's end, and deletes the copy."""
        number = attempt["followup"]
        asked = next((f for f in pl.read_followups(self.sd) if f.get("n") == number), {})
        settled = next((r for r in asked.get("runs") or [] if r["run"] == e["run"]), {})
        if settled.get("outcome") and settled.get("attempt") == attempt["n"]:
            return settled["outcome"], settled.get("reason")  # by a launcher that died before it could note it here
        decision = settled.get("settling")
        if not decision or decision.get("attempt") != attempt["n"]:
            decision = {"attempt": attempt["n"], **self.decide(e, attempt, res, ending, said, asked.get("question"))}
            pl.record_followup(self.sd, number, e["run"], settling=decision)
        self.act(e, decision)
        return decision["outcome"], decision["reason"]

    def decide(self, e: dict, attempt: dict, res: dict, ending: str | None, said: str, question: str | None) -> dict:
        """What a follow-up attempt comes to, from the copy made before the question, the persona
        file as its process left it and the process's result: {"outcome", "reason", "action",
        "section"}, as in the "settling" of panel_lib.py. Changes nothing."""
        number, file = attempt["followup"], self.sd / e["file"]
        copy, left = pl.read_copy(self.log(e, attempt["n"], "before")), self.left(e)

        def decision(outcome, reason, action="keep", section=None):
            return {"outcome": outcome, "reason": reason, "action": action, "section": section}

        if copy is None:  # nothing to compare with or to put back
            there = left is not None and any(
                f["n"] == number for f in pl.parse_persona_file(file, self.cfg, pl.as_text(left))["followups"])
            return decision("answered" if there else "unanswered", "the copy made of its persona file before the "
                            "question is gone, so the file was not checked")
        usability, known = self.cfg["type"] == "usability", None
        if usability:  # a line of the file that the reason repeats is the panellist's own text (pl.shown())
            known = self.known()
        change, how = pl.followup_change(self.cfg, copy, file, number, *(
            [lambda line: pl.shown(known, line, "a line that is not shown", 60)] if usability else []))
        if change == "section":
            return decision("answered", f"{ending}, so check that the answer is whole" if ending else None)
        if change == "other":
            kept = self.log(e, attempt["n"], "rejected.md")
            return decision("rejected", f"{how}, and a follow-up may only append its one section. Its persona file "
                            "was put back as it was before the question"
                            + (f", and what the panellist left is in logs/{kept.name}" if left is not None else ""),
                            "restore")
        back = "restore" if change == "blank" else "keep"  # a heading with nothing under it goes
        if res["outcome"] == "usage_limit":
            return decision("turned away", TURNED_AWAY + (f" ({said})" if said else ""), back)
        reply = (res["reply"] or "").strip()
        if not reply:
            return decision("unanswered", (ending or "its process ended") + " with no section written and no reply",
                            back)
        return decision("answered from the reply", "it replied without writing its section, so the launcher wrote it",
                        "append", pl.followup_section(number, question or "(the question is not on record)", reply,
                                                      from_reply=True))

    def act(self, e: dict, decision: dict):
        """Do to a run's persona file what a settling decision says. Done twice, or again after a
        launcher died part-way, it ends the same: each write replaces a file in one step, the
        file is made from the copy and never from what is in it now, and what a rejected
        follow-up left is kept only while the file still differs from the copy, so a file
        already put back never replaces it."""
        copy, left = pl.read_copy(self.log(e, decision["attempt"], "before")), self.left(e)
        if decision["action"] == "keep" or copy is None:
            return
        if decision["outcome"] == "rejected" and left is not None and left != copy:
            pl.keep_copy(self.log(e, decision["attempt"], "rejected.md"), left)
        try:
            pl.write_persona(self.sd, self.sd / e["file"], copy if decision["action"] == "restore"
                             else pl.as_text(copy).rstrip("\n") + "\n\n" + decision["section"])
        except OSError as err:  # the decision stays on record, and readers read the copy until it is carried out
            raise SystemExit(
                f"{e['run']}: its persona file {e['file']} could not be written to settle its follow-up "
                f"({pl.unread(err)}). Nothing is written through a symbolic link. The follow-up is not settled, and "
                "until it is the run is read as it stood before the question. Make every folder above the file a "
                "plain folder that can be written, with no folder at the file's own name, then settle it with: "
                f"followup.py {self.sd} list")

    def left(self, e: dict) -> bytes | None:
        """What a run's persona file holds now, None when the run has no file, or none that can be
        read as its own (pl.persona_bytes())."""
        try:
            return pl.persona_bytes(self.sd, self.sd / e["file"])
        except OSError:
            return None

    def supervise(self):
        """Run until nothing is queued and no process is alive."""
        while self.queue or self.children:
            if self.stop.asked and self.queue:
                say(f"Stopping: {plural(len(self.queue), 'queued run')} "
                    f"{agree(len(self.queue), 'stays as it is', 'stay as they are')}.")
                self.queue.clear()
            self.fill()
            if self.children:
                time.sleep(self.poll)
                self.watch()


# ---------------------------------------------------------------- commands

def select(runs: list[dict], role: str, ids: list[str] | None) -> list[dict]:
    """The runs a command is about: every run of the role, or the ones --runs names."""
    pool, noun = [e for e in runs if e["role"] == role], ROLES[role].noun
    if not pool:
        raise SystemExit(f"This study has no {role} {noun}s in runs.json." + (
            f' "run --role {role}" plans and starts them.' if role in pl.JOB_ROLES else ""))
    if ids is None:
        return pool
    unknown = [i for i in ids if i not in {e["run"] for e in pool}]
    if unknown:
        raise SystemExit(f"No {role} {noun} called {', '.join(unknown)}. There {agree(len(pool), 'is', 'are')}: "
                         f"{', '.join(e['run'] for e in pool)}")
    return [e for e in pool if e["run"] in ids]


def text_only_note(cfg: dict, brief_name: str) -> str:
    """What a brief tells its reader about a text-only study, assets/<brief>-text.md: nothing for
    a full-materials study, so the placeholder's line goes."""
    return (pl.ASSETS / f"{brief_name}-text.md").read_text().strip() if cfg["materials"] == "text" else ""


def one_concept_note(cfg: dict, brief_name: str) -> str:
    """What a brief tells its reader about a study with one concept, assets/<brief>-one.md:
    nothing for a study that compares concepts, so the placeholder's line goes."""
    return (pl.ASSETS / f"{brief_name}-one.md").read_text().strip() if pl.single_concept(cfg) else ""


def kinds_note(cfg: dict) -> str:
    """What a brief tells its reader about the concepts that were not captured from a site's own
    files: the ones taken from a live page (assets/brief-kinds-url.md) and the ones supplied as
    images and documents (assets/brief-kinds-files.md), each named by its neutral label. When
    the concepts differ in form, so that a score can turn on the format, it says that too
    (assets/brief-kinds-mixed.md, from pl.form_caution()): a study with one concept, or with
    concepts all of one form, has nothing to set against anything. Nothing for a study of sites
    alone, so the placeholder's line goes."""
    lines = []
    for kind in ("url", "files"):
        labels = [label for label, c in pl.label_map(cfg).items() if pl.concept_kind(c) == kind]
        if labels:
            named = f"{agree(len(labels), 'Concept')} {planning.listed(labels)} {agree(len(labels), 'was', 'were')}"
            lines.append(pl.fill_brief(f"brief-kinds-{kind}.md", {"CONCEPTS": named}).strip())
    caution = pl.form_caution(cfg)
    if caution:
        lines.append(pl.fill_brief("brief-kinds-mixed.md", {"CONCEPTS": caution["concepts"],
                                                            "EXPOSED": caution["exposed"]}).strip())
    return "\n".join(lines)


def reviewed(cfg: dict, labels: list[str]) -> str:
    """What the panel reviewed, for the sentence a brief opens with: "3 concepts (A, B, C) of
    draft homepage designs", or for a study with one concept "one draft homepage design (Concept
    A)". A study of one concept scaffolded without "artefact" has the plural alone to go by."""
    if not pl.single_concept(cfg):
        return f"{len(labels)} concepts ({', '.join(labels)}) of {cfg['artefact_plural']}"
    if cfg["artefact"]:
        return f"one {cfg['artefact']} (Concept {labels[0]})"
    return f"one concept ({labels[0]}) of {cfg['artefact_plural']}"


def followups_note(cfg: dict, brief_name: str, runs: set[str]) -> str:
    """What a brief tells its reader about the follow-up questions that left an answer in the file
    of one of runs, assets/<brief>-followups.md with the questions listed: nothing when there is
    none, so the placeholder's line goes. It opens with an empty line, to stand as a paragraph."""
    asked = []
    for f in pl.read_followups(cfg["_dir"]):
        answered = [x["run"] for x in f.get("runs") or [] if x["run"] in runs
                    and x.get("outcome") in (*pl.FOLLOWUP_ANSWERED, "sent by hand")]
        if answered:
            asked.append(f"- Follow-up {f['n']}, asked of {planning.listed(answered)}: "
                         + " ".join((f["question"] or "").split()))
    return "\n" + pl.fill_brief(f"{brief_name}-followups.md", {"QUESTIONS": "\n".join(asked)}).strip() if asked else ""


def brief(cfg: dict, job: dict, records: list[dict], files: dict) -> str:
    """A job's prompt: its brief from assets/ with every placeholder filled. records is
    pl.run_records(), and files maps a run id to its persona file."""
    sd, syn, keys = cfg["_dir"], cfg["synthesis"], pl.model_keys(cfg)
    usability = cfg["type"] == "usability"  # its briefs are assets of their own, with the same placeholders
    qual, synthesis = ("usability-qual-brief", "usability-synthesis-brief") if usability else (
        "qual-brief", "synthesis-brief")
    done = sum(r["state"] == "done" for r in records)
    context = syn.get("context_files", [])
    missing = [f for f in context if not (sd / f).is_file()]
    if missing:
        raise SystemExit(f"synthesis.context_files: no such file in {sd}: {', '.join(missing)}")
    values = {
        "PERSONAS": plural(len(cfg["personas"]), "persona"),
        "PRODUCT": cfg.get("product") or "the product",
        "MODELS": f"{plural(len(keys), 'model')} ({', '.join(keys)})", "STUDY_DIR": sd,
        "RUNS": plural(len(records), "run") + ("" if done == len(records) else f", {done} of them complete"),
        "DECISION_MAKER": syn.get("decision_maker", pl.DEFAULT_DECISION_MAKER),
    }
    if usability:
        tasks = pl.study_units(cfg)
        values.update(TASKS=f"{plural(len(tasks), 'task')} ({', '.join(tasks)})", TARGET=cfg["target"]["base_url"])
        notes = {}
    else:
        values.update(REVIEWED=reviewed(cfg, list(pl.label_map(cfg))), KINDS_NOTE=kinds_note(cfg))
        notes = {"TEXT_ONLY_NOTE": lambda name: text_only_note(cfg, name),
                 "ONE_CONCEPT_NOTE": lambda name: one_concept_note(cfg, name)}
    if job["role"] == "writer":
        extra = "\n".join(f"- `{f}`: background from the lead." for f in context)
        return pl.fill_brief(f"{synthesis}.md", {
            **values, "EXTRA_CONTEXT_FILES": extra, **{token: note(synthesis) for token, note in notes.items()},
            "FOLLOWUPS": followups_note(cfg, synthesis, {r["run"] for r in records})})

    def spans(ids, mark=""):  # "persona P01", "personas P01 to P04"
        return f"{agree(len(ids), 'persona')} {mark}{ids[0] if len(ids) == 1 else f'{ids[0]} to {ids[-1]}'}{mark}"

    def path(r):
        return sd / files[r["run"]] if r["run"] in files else pl.personas_dir(sd) / r["parsed"]["file"]

    own = [r for pid in job["personas"] for r in records if r["pid"] == pid and (r["run"] in files or r["parsed"])]
    others = [j for j in pl.synthesis_jobs(cfg) if j["role"] == "analyst" and j["run"] != job["run"]]
    unfinished = []
    for r in own:
        prog = r["progress"]
        wrote = (f"{len(prog['written'])} of {plural(len(prog['units']), *pl.unit_nouns(cfg))} written"
                 + ("" if prog["has_final"] else ", final sections missing") if prog["written"] else "nothing written")
        if r["state"] != "done":
            unfinished.append(f"- `{path(r).name}` ({r['run']}): {r['state']}, {wrote}")
    def listed(r):  # a run's persona file and, in a usability study, where its step log and screenshots are
        refused = pl.run_evidence(cfg, sd, r["run"])["refused"] if usability else None
        return f"- `{path(r)}`" + (
            f". Its evidence folder is not given to you, and is not to be opened: {refused}" if refused else
            f", with its step log and screenshots in `{pl.evidence_dir(sd, r['run'])}/`" if usability else "")

    return pl.fill_brief(f"{qual}.md", {
        **values, **{token: note(qual) for token, note in notes.items()},
        "OWN_PERSONAS": spans(job["personas"], "**"), "FILES": plural(len(own), "file"),
        "OTHER_ANALYSTS_SENTENCE": " ".join(
            f"Another analyst owns {spans(j['personas'])} and writes `{j['file']}`: leave both to them."
            for j in others) or "You are the only analyst.",
        "EXTRA_CONTEXT_FILES": "\n".join(f"- `{sd / f}`: background from the lead." for f in context),
        "PERSONA_FILES": "\n".join(listed(r) for r in own),
        "INCOMPLETE_RUNS": "\n".join([
            "", f"{plural(len(unfinished), 'run')} of your {agree(len(job['personas']), 'persona')} did not finish. "
            "Read what an unfinished run wrote as partial evidence: quote it and say the run was incomplete, and "
            f"never count it as a full {'attempt' if usability else 'review'}. Its scores are in "
            '`analysis/quant.md` under "Incomplete runs" and in no other table.',
            *unfinished] if unfinished else []),
        "FOLLOWUPS": followups_note(cfg, qual, {r["run"] for r in own}),
        "OUTPUT_FILE": Path(job["file"]).name})


def unsettled_followups(study_dir: Path, runs: list[dict]) -> list[str]:
    """The runs with a follow-up question that is not settled: an attempt of theirs is in flight,
    or their record in followups.json has no outcome yet or a decision still to carry out."""
    out = [e["run"] for e in runs if asking(e)]
    out += [r["run"] for f in pl.read_followups(study_dir) if f.get("mode") != "native"
            for r in f.get("runs") or [] if r.get("outcome") is None or r.get("settling")]
    return list(dict.fromkeys(out))


def plan_jobs(cfg: dict, runs: list[dict], role: str, command: str, allow_incomplete: bool):
    """What comes before any analyst or writer job starts. Refuses, by exiting, a role with no
    model entry and a job whose inputs are not ready: either while a follow-up question is not
    settled, analysts while panellist runs are pending, running or blocked (unless
    allow_incomplete), the writer until every analyst job is done.
    Then, for the run command, brings the role's job entries in runs and their prompts in line
    with study.json: a new job is added, and one that is pending or failed is planned afresh."""
    sd, planned = cfg["_dir"], pl.synthesis_jobs(cfg)
    wanted = [j for j in planned if j["role"] == role]
    if role not in cfg["synthesis"] or wanted[0]["runner"] is None:
        raise SystemExit(
            f'study.json names no runner for the {role}. Add "synthesis": {{"{role}": {{"runner": "<runner>", '
            f'"model": "<model>"}}}}: there is no default, and "model" may be left out for the runner\'s own.')
    runners.get(wanted[0]["runner"])
    out = unsettled_followups(sd, runs)
    if out:
        files = agree(len(out), "its persona file", "their persona files")
        raise SystemExit(
            f"The {'analysts wait' if role == 'analyst' else 'writer waits'} for the follow-up questions: the one put "
            f"to {planning.listed(out)} is not settled, so {files} may still be put back as before the question. "
            f"Wait for the follow-up to finish, or settle one that was cut short with: followup.py {sd} list")
    records = pl.run_records(sd, cfg)
    if role == "analyst":
        waiting = [r for r in records if r["state"] in ("pending", "running", "blocked")]
        if waiting and not allow_incomplete:
            raise SystemExit(
                f"Analysts wait for the panel: {plural(len(waiting), 'panellist run')} of {len(records)} "
                f"{agree(len(waiting), 'has', 'have')} not finished ("
                + ", ".join(f"{r['run']} {r['state']}" for r in waiting) + "). Finish them with launch.py run and "
                "resume, or pass --allow-incomplete to analyse what there is: the analysts are then told which "
                "runs are incomplete.")
    else:
        recorded_jobs = {e["run"]: e for e in runs}
        analysts = {j["run"]: state_of(cfg, recorded_jobs.get(j["run"], j)) for j in planned if j["role"] == "analyst"}
        if set(analysts.values()) != {"done"}:
            raise SystemExit(
                "The writer waits for the analysts: " + ", ".join(f"{k} is {v}" for k, v in analysts.items())
                + f". Finish them first: launch.py {sd} run --role analyst, or resume --role analyst for one "
                "that is blocked.")
    if command != "run":
        return
    current = {e["run"]: e for e in runs if e["role"] == role}
    settled = {k: state_of(cfg, e) for k, e in current.items() if state_of(cfg, e) not in ("pending", "failed")}
    changed = [k for k, state in settled.items()
               if current[k].get("personas") != next((j.get("personas") for j in wanted if j["run"] == k), "none")]
    if changed:
        raise SystemExit(
            "study.json no longer plans the analysis the way it was when "
            + ", ".join(f"{k} ({settled[k]})" for k in changed) + " started. It now has " + "; ".join(
                f"{j['run']} reading {', '.join(j['personas'])}" for j in wanted)
            + '. Put "synthesis" and the personas back as they were. To plan again instead, delete the output '
            "files of the jobs named, and take any of them that is not done out of runs.json.")
    files = {e["run"]: e["file"] for e in runs if e["role"] == "panellist"}
    prompts = {j["run"]: brief(cfg, j, records, files) for j in wanted if j["run"] not in settled}
    for job in wanted:
        if job["run"] in settled:
            continue
        if job["run"] not in current:
            runs.append({})
            current[job["run"]] = runs[-1]
        current[job["run"]].update(job)  # the plan's fields; whatever a launcher recorded stays
        (sd / job["prompt"]).write_text(prompts[job["run"]])
    for stale in set(current) - {j["run"] for j in wanted}:
        runs.remove(current[stale])  # pending or failed, and no longer planned
    for name in ("analysis/quant.md", "analysis/checks.md", "analysis/lead-notes.md") if prompts else ():
        if not (sd / name).is_file():
            say(f"Note: {name} does not exist, and the {role}'s brief names it.")


def fitness(cfg: dict, entries: list[dict]) -> tuple[dict, dict, list[str]]:
    """Whether each of entries can be started on its runner as study.json has it, asked of the
    runners before any process starts: (unusable, errors, notes). unusable maps a runner whose
    CLI cannot be used to why (planning.usable()): the CLI's words when its check() fails, and
    when this shell does not let it do a run at all (its shell_check()), what it cannot do here
    with the two ways out of a sandboxed shell tool. errors maps the id of each entry on a
    runner that can be used to what refuses its model entry (planning.unfit, which asks the
    runner's model_status()): an empty list when nothing does. notes are what an entry asks for
    that its runner leaves out. Each runner is checked once and each model entry judged once.
    Every command that starts a process judges its runs here first ("run", "pilot" and "resume"
    through preflight(), a follow-up through followup.choose()), so what the plan refuses, none
    of them starts."""
    unusable = {}
    for name in dict.fromkeys(e["runner"] for e in entries):
        checked = planning.usable(name)
        if not checked["ok"]:
            unusable[name] = checked["message"]
    judged = {}  # one judgement for each model entry: asking a runner about a model can take a CLI call
    for e in entries:
        if e["runner"] not in unusable:
            judged.setdefault((e["role"], e["runner"], e["model"], e["effort"]), planning.unfit(cfg, e))
    errors = {e["run"]: judged[e["role"], e["runner"], e["model"], e["effort"]][0]
              for e in entries if e["runner"] not in unusable}
    return unusable, errors, list(dict.fromkeys(note for _, note in judged.values() if note))


def preflight(cfg: dict, targets: list[dict], allow_missing: bool) -> tuple[list[dict], str | None]:
    """Check that this shell can write to the study directory, that the materials are captured
    (or, in a usability study, that the files its commands name are there), that the
    agent-browser CLI is there for runs that may browse, every runner the targets need, and
    what study.json asks of each (fitness()), before any process starts. Returns the targets
    that may start, and why nothing may when that is the case. The plan command reports the
    same things (planning.build), so what it refuses, this refuses. Only a panellist run reads
    the materials: analysts and the writer start without them."""
    locked = planning.unwritable_study(cfg) if targets else None
    if locked:
        return [], f"Nothing was started: {locked}"
    if any(e["role"] == "panellist" for e in targets):
        uncaptured = planning.no_materials(cfg, planning.materials(cfg))
        if uncaptured:
            return [], f"Nothing was started: {uncaptured}"
        missing = pl.usability_problems(cfg)
        if missing:
            return [], "Nothing was started: " + " ".join(missing)
        no_browser = planning.no_browser(cfg, {e["runner"] for e in targets if e["role"] == "panellist"})
        if no_browser:
            return [], f"Nothing was started: {no_browser}."
    unusable, unfit, notes = fitness(cfg, targets)
    for name, message in unusable.items():
        say(f"{name}: cannot be used: {message}")
    if unusable and not allow_missing:
        return [], ("Nothing was started: a panel short of a model is a different study. Fix what is named above "
                    "and run this again, or pass --allow-missing to go ahead with the runners that work.")
    ready = [e for e in targets if e["runner"] not in unusable]
    if unusable:
        skipped = [e["run"] for e in targets if e["runner"] in unusable]
        say(f"--allow-missing: {plural(len(skipped), 'run')} on {', '.join(unusable)} left untouched "
            f"({', '.join(skipped)}).")
    for note in notes:
        say(f"Note: {note}.")
    errors = [f"{e['run']}: {error}" for e in ready for error in unfit[e["run"]]]
    if errors:
        return [], "Nothing was started: fix these model entries in study.json.\n" + "\n".join(errors)
    return ready, None


def summary(cfg: dict, entries: list[dict]) -> bool:
    """Print the closing line and what to do next. True when every run is done."""
    states = [state_of(cfg, e) for e in entries]
    say("Finished: " + ", ".join(f"{s} {states.count(s)}" for s in STATES if s in states) + ".")
    for s, role in ((s, role) for s in STATES if s in NEXT for role in ROLES):
        ids = [e["run"] for e, st in zip(entries, states) if st == s and e["role"] == role and not e.get("released")]
        if ids:
            say(f"  {s}: {', '.join(ids)}. Next: {NEXT[s]}"
                + ("." if role == "panellist" else f", with --role {role}."))
    released = [e["run"] for e, st in zip(entries, states) if e.get("released") and st != "done"]
    if released:
        say(f"  released by the lead: {', '.join(released)}. Next: nothing, or run or resume with --runs <ids> "
            "--released to continue with a new test account.")
    return all(s == "done" for s in states)


def launch(args, cfg: dict) -> int:
    """run, pilot and resume: queue the runs the command owns, then supervise them."""
    sd, command = cfg["_dir"], args.cmd
    if args.extend and not (command == "resume" and args.runs):
        raise SystemExit("--extend goes with resume --runs <ids>: name the limited runs to give one more allowance.")
    if command == "pilot" and args.role != "panellist":
        raise SystemExit("pilot is for panellist runs: it takes no --role.")
    if command == "pilot" and args.runs:
        raise SystemExit("pilot takes no --runs: it starts the first persona on each model entry. To start runs "
                         "you name, use run --runs <ids>.")
    if args.released and not args.runs:
        raise SystemExit("--released goes with run or resume and --runs <ids>: name the released runs to start "
                         "again, each with a new test account.")
    if args.allow_incomplete and args.role != "analyst":
        raise SystemExit("--allow-incomplete goes with --role analyst: it lets the analysts start on an "
                         "unfinished panel.")
    if any(e["runner"] is None for e in pl.read_runs(sd)):
        raise SystemExit("This study is in native mode: its model entries name no runner, so the lead starts each "
                         f"run with its own subagent tool. Use runs.py {sd} next, mark and resume.")
    stop = StopSignal()
    stop.listen()
    lock = Lock(sd)
    lock.acquire(command, args.grace)
    try:
        runs = pl.read_runs(sd)
        sup = Supervisor(cfg, runs, args.grace, args.poll, retry=command != "resume", stop=stop)
        sup.reconcile()
        if args.role in pl.JOB_ROLES:
            plan_jobs(cfg, runs, args.role, command, args.allow_incomplete)
            sup.save()
        ids = [x.strip() for x in args.runs.split(",") if x.strip()] if args.runs else None
        if command == "pilot":
            first = cfg["personas"][0]["id"]
            ids = [e["run"] for e in runs if e["role"] == args.role and e["persona"] == first and e["replicate"] == 1]
        chosen = select(runs, args.role, ids)

        plan = []
        for e in chosen:
            state = state_of(cfg, e)
            extend = state == "limited" and args.extend
            if e.get("released") and not args.released:  # the lead let its account go: started only when asked to
                if state in STARTS[command] or extend:
                    say(f"{e['run']}: released by the lead {clock(e['released'])}, so {command} leaves it alone: "
                        f"its test account is gone. To continue it with a new one: launch.py {sd} "
                        f"{'resume' if state in STARTS['resume'] else 'run'} --runs {e['run']} --released")
                continue
            if state not in STARTS[command] and not extend:
                if ids and state not in ("done", "running"):
                    say(f"{e['run']}: {state}, so {command} leaves it alone. Next: {NEXT[state]}.")
                continue
            kind = "launch"
            if command == "resume":
                gone = ("its session was purged (purge-sessions)" if e.get("session") in (e.get("purged") or {})
                        else LOST if e.get("session") in (e.get("lost") or {})
                        else NOT_SAVED if e.get("session") in (e.get("unsaved") or {}) else None)
                can_resume = e.get("session") and not gone and sup.runner(e["runner"]).capabilities()["resume"]
                kind = "resume" if can_resume else "restart"
                if not can_resume and progress_of(cfg, e)["written"]:
                    sup.cannot_continue(e, gone or ("no session was recorded" if not e.get("session")
                                                    else f"{e['runner']} cannot resume a session"))
                    continue
            plan.append((e, kind, extend))
        ready, refusal = preflight(cfg, [e for e, _, _ in plan], args.allow_missing)
        if refusal:
            say(refusal)
        ready = {e["run"] for e in ready}
        for e, kind, extend in plan:
            if e["run"] not in ready:
                continue
            if extend:
                e["extended"] = (e.get("extended") or 0) + 1
                sup.save()
                say(f"{e['run']}: extended, one more allowance of its limits. The plan's ceiling no longer "
                    "holds for this study.")
            elif e.get("reset_at") and e["reset_at"] > time.time():
                say(f"{e['run']}: its harness said its limit lifts at {clock(e['reset_at'])}; trying anyway.")
            sup.queue.append((e, kind))
        sup.supervise()
        covered = chosen + [e for e in sup.adopted if e["run"] not in {c["run"] for c in chosen}]
        done = summary(cfg, covered)
        if done and args.role == "analyst":
            say(f"Next: read {', '.join(e['file'] for e in chosen)}, then launch.py {sd} run --role writer.")
        return 0 if done and not (refusal or sup.left_alone or sup.refused) else 1
    finally:
        lock.release()


def stop_launcher(args, cfg: dict) -> int:
    """Ask the launcher that has the study to stop its runs. When there is none, take the study
    and ask the watchdogs of the runs still alive.

    That is done whatever became of a command of the study. Every other launcher command exits
    when a process that an earlier command left cannot be proved gone (accounts.recover()), and
    this one would then leave runs alive that it was asked to stop. So it stops them first,
    starts no command of the study meanwhile (Supervisor.recover(), "held"), then says what
    holds the study up, on stderr, and returns 1. The success checks and teardowns that fell due
    stay due, for the next launcher command.

    A launcher whose processes this shell cannot see (Lock.holder()) cannot be signalled from
    it, and the process id on record may be another process's here: nothing is signalled, and
    the command says where to run it. That is so of an id recorded in another process
    namespace even when a process here holds it under the same start identity: holder() is
    the one answer to whether the launcher is seen, and no signal goes to the id on record
    without it. The same holds with no launcher, of runs that one left alive where this shell
    cannot look: the study is then not given to this command (Lock.acquire())."""
    sd = cfg["_dir"]
    done = (f"Stopped. Runs that wrote sections are partial: continue them with launch.py {sd} resume. Runs that "
            f"wrote nothing are pending again: start them with launch.py {sd} run.")
    held = Lock.holder(sd)
    if held and not held["seen"]:
        raise SystemExit(f"A launcher has this study{Lock.who(held)}, and \"stop\" could not ask it to stop. {UNSEEN}, "
                         f"so nothing was signalled and the runs go on. {pl.SANDBOX_HINT}")
    if held:
        try:
            os.kill(held["pid"], signal.SIGTERM)
        except OSError as err:
            raise SystemExit(f"Could not signal the launcher (pid {held['pid']}): {err}")
        say(f"Asked the launcher (pid {held['pid']}) to stop its runs.")
        give_up = time.time() + (held.get("grace") or 0) + 30
        while alive(held["pid"], held["identity"]):
            if time.time() > give_up:
                raise SystemExit(f"The launcher has not exited yet. Check with: launch.py {sd} status")
            time.sleep(min(args.poll, 0.2))
    else:
        lock = Lock(sd)
        lock.acquire("stop", args.grace)
        try:
            sup = Supervisor(cfg, pl.read_runs(sd), args.grace, args.poll)
            sup.reconcile(commands=False)
            stopped = [c.entry["run"] for c in sup.children]
            sup.stop.asked = True
            sup.supervise()
        finally:
            lock.release()
        say(done if stopped else "Nothing is running.")
        if sup.held:  # said last, and by the exit code: the runs are stopped, and the study is still held up
            print(f"{sup.held}\nstop started no command of the study either: the success checks and teardowns that "
                  "are due stay due, and the next launcher command sees to them once that is cleared.",
                  file=sys.stderr, flush=True)
            return 1
        return 0
    say(done)
    return 0


def release_runs(args, cfg: dict) -> int:
    """The "release" command: let go of the test account of each run named that the lead will not
    continue. A partial, blocked or pending run keeps its account for when it continues, and
    nothing else ends that: an account in force keeps its credentials working, and archive.py
    refuses the study. For each run named that has an account in force and no process: its
    success checks are run, while the account is whole, then the account is torn down, once, and
    the entry is marked "released". Exit code 0 when every run named ended with no account in
    force."""
    sd = cfg["_dir"]
    if cfg["type"] != "usability" or not cfg["accounts"]:
        raise SystemExit("Nothing to release: this study has no test accounts.")
    if not args.runs:
        raise SystemExit("release takes --runs <ids>: name the unfinished runs whose test accounts to let go of. "
                         f"launch.py {sd} status shows which runs have one in force.")
    lock = Lock(sd)
    lock.acquire("release", args.grace)
    try:
        runs = pl.read_runs(sd)
        sup = Supervisor(cfg, runs, args.grace, args.poll)
        sup.reconcile(adopt=False)  # which lets go of the accounts of the runs that have finished
        held = False
        for e in select(runs, "panellist", [x.strip() for x in args.runs.split(",") if x.strip()]):
            state, record = state_of(cfg, e), accounts.read(sd, e["run"])
            if in_flight(e):
                held = True
                say(f"{e['run']}: running, so its account stays. Stop it first: launch.py {sd} stop")
            elif not accounts.in_force(record):
                say(f"{e['run']}: {state}, with no test account in force: nothing to release.")
            elif e["run"] in sup.let_go:  # in a final state, and its teardown has just failed again
                held = True
            else:
                sup.check(e, again=True)  # of what it got done: the last time anything can tell
                e["released"] = round(time.time())
                sup.save()
                say(f"{e['run']}: {state}, released. \"run\" and \"resume\" leave it alone from now on, unless "
                    "it is named with --released.")
                sup.release(e)
                held = held or accounts.in_force(accounts.read(sd, e["run"]))
        return 1 if held else 0
    finally:
        lock.release()


def check_runs(args, cfg: dict) -> int:
    """The "check" command: run the success checks again for the runs in a final state, as a
    lead does after fixing a check. A task's record in runs.json is replaced, unless it holds a
    verdict made with an account that is gone: that one is kept, and said to be, without --force
    (Supervisor.check()). Exit code 0 when every check run gave a verdict and every run named
    was checked."""
    sd = cfg["_dir"]
    if cfg["type"] != "usability":
        raise SystemExit("check runs the success checks of a usability study's tasks, and this is a review study.")
    if not any("success_check" in t for t in cfg["tasks"]):
        raise SystemExit('No task of this study has a "success_check" in study.json, so there is nothing to run.')
    missing = [p for p in pl.usability_problems(cfg) if "success_check" in p]
    if missing:
        raise SystemExit("Nothing was checked: " + " ".join(missing))
    lock = Lock(sd)
    lock.acquire("check", args.grace)
    try:
        runs = pl.read_runs(sd)
        sup = Supervisor(cfg, runs, args.grace, args.poll)
        sup.reconcile(adopt=False, final=False)  # an account still in force stays for the checks to see
        ids = [x.strip() for x in args.runs.split(",") if x.strip()] if args.runs else None
        short = False
        for e in select(runs, "panellist", ids):
            state = state_of(cfg, e)
            if in_flight(e) or state not in accounts.FINAL:
                short = short or bool(ids)
                say(f"{e['run']}: {'running' if in_flight(e) else state}, so it is not checked. Its checks run when "
                    "it is done, limited or failed.")
                continue
            short = any(r["error"] for r in sup.check(e, again=True, force=args.force).values()) or short
        sup.settle_final()
        return 1 if short else 0
    finally:
        lock.release()


def status(args, cfg: dict) -> int:
    """Print every run and job as it is on record, with what can be seen of its process. Starts
    nothing, holds no lock and changes nothing.

    A launcher has the study when the lock says so (Lock.holder()). When its process is not to
    be seen from this shell, no process of the study is: a run's process is then "unseen", in
    place of "alive" or "gone", nothing is said of its browser session, and no run is called
    gone for a launcher to settle. One line says so. With no launcher, the same is said of each
    run that is alive where this shell cannot look: its watchdog holds its lock and is not to
    be seen (unseen()). A run whose watchdog has let go of its lock is "gone", wherever it ran."""
    sd, now = cfg["_dir"], time.time()
    held = Lock.holder(sd)
    blind = bool(held) and not held["seen"]
    rows = {"run": [], "job": []}  # panellist runs, then analyst and writer jobs
    for e in pl.read_runs(sd):
        if e["role"] not in ROLES:
            continue
        prog, attempts, running = progress_of(cfg, e), e.get("attempts") or [], in_flight(e)
        asked = planning.followup_attempts(e)
        own = ({"scored": len(prog["scored"]), "of": len(prog["units"])} if e["role"] == "panellist"
               else {"model": e["model"], "file": e["file"], "note": e.get("note")})
        state = pl.run_state(prog, e.get("state"))
        # The attempt's own files say where its processes are, and whether it has ended: runs.json
        # lacks the pid when a launcher died early, and says "running" until a launcher settles it.
        log = str(sd / "logs" / f"{e['run']}.{attempts[-1]['n']}") if running and attempts else None
        pids = (recorded(Path(log + ".pid")) if log else None) or {}
        record = end_record(Path(log + ".end")) if pids else None
        over = not pids or record or not living(pids)
        hidden = blind or unseen(pids)
        current = ((record or {}).get("ended") or now) - attempts[-1]["started"] if log else 0
        rows[ROLES[e["role"]].noun].append({
            "run": e["run"], "role": e["role"], "name": e.get("name", ""), "key": e["key"], "runner": e["runner"],
            "state": state, **own,
            "process": ("unseen" if hidden else "gone" if over else "alive") if running else None,
            "pid": pids["cli"][0] if pids else None, "attempts": len(attempts) - len(asked),
            "followups": sorted({a["followup"] for a in asked if a.get("ended") is not None}),  # the settled ones
            "asking": asking(e)["followup"] if asking(e) else None,
            # Its file was read as it stood before that follow-up: nothing is taken from it until it is settled.
            "unsettled": bool(asking(e)) and pl.read_copy(Path(log + ".before")) is not None,
            "seconds_used": round((e.get("seconds_used") or 0) + (0 if asking(e) else current), 1),
            "usage": usage_of(e), "unreported_attempts": planning.unreported(e),
            "unallocated": planning.unallocated(e),
            "reason": e.get("reason") if state != "done" else None,
            "leftover": still_left(attempts[-1].get("leftover")) if attempts else None,
            # The browser session of the attempt now running (browser_session.state()), and what was found or
            # left of the session of its last attempt (Supervisor.browser_left()).
            "browser": browser.state(log) if log and not over and not hidden else None,
            "browser_left": attempts[-1].get("browser_left") if attempts else None,
            "account": e.get("account"),  # a usability run's test account (panel_lib.py), with no identifier or secret
            "checks": e.get("checks"),    # what the success check of each of its tasks said (accounts.py)
            "released": e.get("released"),  # when the lead let its account go with "release", unfinished
            "reset_at": e.get("reset_at"),
            "extended": e.get("extended") or 0, "session": e.get("session"),
            "purged": sorted(e.get("purged") or {}), "lost": sorted(e.get("lost") or {}),
            "unsaved": sorted(e.get("unsaved") or {})})  # the sessions its harness did not keep (ended())
    every = rows["run"] + rows["job"]
    extended = [r["run"] for r in every if r["extended"]]
    gone = [r["run"] for r in every if r["process"] == "gone"]
    followups, earlier = pl.read_followups(sd), len(pl.read_earlier_sessions(sd))
    if args.json:
        print(json.dumps({"launcher": held, "runs": rows["run"], "jobs": rows["job"], "extended": extended,
                          "ceiling_holds": not extended, "followups": len(followups),
                          "earlier_sessions": earlier}, indent=2))
        return 0
    for noun, group in rows.items():
        if noun == "job" and group:
            print("\nAnalysts and writer:")
        for r in group:
            u, shared = r["usage"], r["unallocated"]
            lump = [] if not shared else (
                [f"{shared['input_tokens']:,} in and {shared['output_tokens'] or 0:,} out tokens"]
                if shared["input_tokens"] is not None else []) + (
                [planning.money(shared["cost_usd"])] if shared["cost_usd"] is not None else [])
            facts = [", ".join(x for x in ("" if r["process"] == "unseen" else f"process {r['process']}",
                                           f"pid {r['pid']}" if r["pid"] else "") if x) if r["process"] else "",
                     {"up": "browser session up", "starting": "browser session starting",
                      "down": "browser session not running"}.get(r["browser"], ""),
                     (f"being asked follow-up {r['asking']}" if r["process"] == "alive"
                      else f"follow-up {r['asking']} not settled") if r["asking"] else "",
                     plural(r["attempts"], "attempt") if r["attempts"] else "",
                     f"asked follow-up {planning.listed([str(n) for n in r['followups']])}" if r["followups"] else "",
                     duration(r["seconds_used"]) if r["attempts"] else "",
                     f"{u['input_tokens']:,} in and {u['output_tokens'] or 0:,} out tokens" if u["input_tokens"] is not None
                     else "",
                     f"${u['cost_usd']:.2f}" if u["cost_usd"] is not None else "",
                     f"usage of {planning.attempts_named(r['unreported_attempts'])} not reported (process was "
                     "stopped)" if r["unreported_attempts"] else "",
                     f"{' and '.join(lump)} unallocated between the run and a follow-up" if lump else "",
                     f"extended {r['extended']}x" if r["extended"] else "",
                     "" if not r["account"] else "test account torn down" if r["account"]["torn_down"]
                     else "test account in force",
                     f"released by the lead {clock(r['released'])}" if r["released"] else "",
                     "checked: " + ", ".join(
                         f"{task} {'failed to run' if c['error'] else 'completed' if c['checked'] else 'not completed'}"
                         for task, c in r["checks"].items()) if r["checks"] else "",
                     "session purged" if r["session"] in r["purged"] else
                     "session lost" if r["session"] in r["lost"] else
                     "earlier sessions purged" if r["purged"] else ""]
            lost = r["browser_left"]
            why = [r["reason"] or "", r.get("note") or "", UNSAVED if r["session"] in r["unsaved"] else "",
                   leftover(r["leftover"]) if r["leftover"] else "",
                   f"TEARDOWN OF ITS TEST ACCOUNT FAILED: {r['account']['teardown_error']}"
                   if (r["account"] or {}).get("teardown_error") else "",
                   "" if not lost else
                   f"THE RECORD OF ITS BROWSER SESSION CANNOT BE TRUSTED ({lost['refused']}): nothing of the session "
                   "was stopped or removed" if lost.get("refused") else
                   ("its browser session was stopped" if lost.get("by") == "watchdog" else
                    "its watchdog left its browser session to the launcher, which "
                    + ("found it running and stopped it" if lost["found"] else "found none running"))
                   + (f", but {remainder(lost)}" if lost["left"] or lost.get("kept") else ""),
                   f"limit lifts {clock(r['reset_at'])}" if r["reset_at"] else ""]
            print(f"{r['run']:<16} {r['state']:<8} " + (f"{r['scored']}/{r['of']}  {r['name']}" if noun == "run"
                                                         else f"{r['file']}  {r['name']}")
                  + (f"  [{', '.join(x for x in facts if x)}]" if any(facts) else "")
                  + (f"  {'; '.join(x for x in why if x)}" if any(why) else ""))
        states = [r["state"] for r in group]
        if group or noun == "run":
            print(" | ".join(f"{s}: {states.count(s)}" for s in sorted(set(states))))
    print("Launcher: " + ("not running" if not held else "running" if not held["pid"] else
                          f'running "{held["command"]}" (pid {held["pid"]})'))
    unseen_here = blind or any(r["process"] == "unseen" for r in every)
    if unseen_here:
        print(f"{UNSEEN}: run states are as last recorded.")
    if gone:
        print(f"Marked running, but the process is gone: {', '.join(gone)}. "
              + ("The launcher above settles them within its next poll." if held else
                 "The next launch.py run, resume or stop settles them"
                 + (", from a shell that sees the runs this one cannot." if unseen_here else ".")))
    for line in pl.unsettled_lines(rows["run"]):
        print(line)
    if extended:
        print(f"Extended past their limits: {', '.join(extended)}. The plan's ceiling no longer holds for this study.")
    if followups:
        print(f"Follow-up questions asked: {len(followups)} (followup.py {sd} list). What they use is outside the "
              "plan's ceiling, under limits.followup.")
    if earlier:
        print(f"{planning.earlier_sessions(earlier)} {planning.purge_hint(sd)}")
    return 0


def plan(args, cfg: dict) -> int:
    """Print the plan. Starts no run, holds no lock and writes nothing to the study: whether a
    launcher has it is asked of the lock, which says so from any shell (Lock.holder()). A
    runner's sign-in check may let its harness refresh its own login."""
    sd = cfg["_dir"]
    scaffolded = (sd / "runs.json").exists()
    entries = pl.read_runs(sd) if scaffolded else pl.planned_runs(cfg)
    on_record = {e["run"]: e for e in entries if e["role"] in pl.JOB_ROLES}
    jobs = []
    for job in pl.synthesis_jobs(cfg):
        seen = on_record.get(job["run"])
        if seen and state_of(cfg, seen) not in ("pending", "failed"):
            jobs.append(seen)  # as it ran: "run" plans afresh only a job that is pending or failed
        else:
            jobs.append({**(seen or {}), **job})
    panel = [e for e in entries if e["role"] == "panellist"]
    facts = planning.build(cfg, panel, jobs, {e["run"]: state_of(cfg, e) for e in panel + jobs}, scaffolded,
                           Lock.holder(sd))
    print(json.dumps(facts, indent=2) if args.json else "\n".join(planning.render(facts)))
    return 0 if facts["ok"] else 1


def usage(args, cfg: dict) -> int:
    """Rewrite analysis/usage.md from runs.json and print it."""
    runs = pl.read_runs(cfg["_dir"])
    if all(e["runner"] is None for e in runs):
        raise SystemExit("This study is in native mode, which has no usage record: the lead's own harness "
                         "starts the runs, and nothing reports what they used.")
    figures = record_usage(cfg, runs)
    print(json.dumps(figures, indent=2) if args.json else planning.usage_markdown(figures), end="")
    return 0


def purge_sessions(args, cfg: dict) -> int:
    """Delete the study's harness sessions through each runner's own command, or, without
    --yes, print what would be deleted. Every delete command comes from a runner. Without --runs
    that includes the sessions of an earlier scaffold (the earlier-sessions record, panel_lib.py),
    each taken off the record once it is deleted."""
    sd = cfg["_dir"]
    lock = Lock(sd)
    if args.yes:
        lock.acquire("purge-sessions", args.grace)  # refuses while a launcher has the study
    elif Lock.holder(sd):
        lock.refuse()
    try:
        runs = pl.read_runs(sd)
        running = [e["run"] for e in runs if in_flight(e)]
        if running:
            raise SystemExit(
                f"{plural(len(running), 'run')} recorded as running ({', '.join(running)}): a running process needs "
                f"its session. Nothing was deleted. Stop and settle them first: launch.py {sd} stop")
        known = [e for e in runs if e["role"] in ROLES]
        ids = [x.strip() for x in args.runs.split(",") if x.strip()] if args.runs else None
        unknown = [i for i in ids or [] if i not in {e["run"] for e in known}]
        if unknown:
            raise SystemExit(f"No run or job called {', '.join(unknown)}.")
        # The sessions of the runs a --force replaced (panel_lib.py), which only a purge of the whole study covers.
        earlier = pl.read_earlier_sessions(sd)
        # (runs.json entry or earlier session, session id, argv, is it an earlier one); why a session stays -> [whose]
        doomed, kept, total = [], {}, 0
        for e in known:
            if ids is not None and e["run"] not in ids:
                continue
            runner = runners.get(e["runner"]) if e["runner"] else None
            for session in sessions_of(e):
                total += 1
                command = None
                if session in (e.get("purged") or {}):
                    why = "purged already"
                elif not runner.capabilities()["purge"]:
                    why = f"{e['runner']} cannot delete a session"
                else:
                    command = runner.purge_command(session, ROLES[e["role"]].workdir(cfg, e))
                    why = f"{e['runner']} found no session to delete"
                if command:
                    doomed.append((e, session, command, False))
                else:
                    kept.setdefault(why, []).append(f"{e['run']}: {session}")
        for old in earlier if ids is None else []:
            total += 1
            command, session = None, old["session"]
            if old["runner"] not in runners.names():
                why = f"there is no runner called {old['runner']} any more"
            elif not runners.get(old["runner"]).capabilities()["purge"]:
                why = f"{old['runner']} cannot delete a session"
            else:
                command = runners.get(old["runner"]).purge_command(session, Path(old.get("workdir") or sd))
                why = f"{old['runner']} found no session to delete"
            if command:
                doomed.append((old, session, command, True))
            else:
                kept.setdefault(why, []).append(f"{old['run']}, of an earlier scaffold: {session}")
        left_out = ([f"{planning.earlier_sessions(len(earlier))} Only purge-sessions without --runs covers them."]
                    if earlier and ids is not None else [])
        if not total:
            say("No session is recorded for " + ("those runs." if ids else "this study: nothing to delete."), *left_out)
            return 0
        say(f"{plural(len(doomed), 'session')} {'to delete' if args.yes else 'would be deleted'}, each by the "
            "command shown:" if doomed else "No session can be deleted.")
        failed = 0
        for e, session, command, replaced in doomed:
            if replaced:
                what = "of an earlier scaffold" + (f", replaced {clock(e['replaced'])}" if e.get("replaced") else "")
            else:
                state = state_of(cfg, e)
                unfinished = state in ("partial", "blocked", "limited")  # what resume could still continue
                what = state + (", and without its session it cannot be resumed" if unfinished else "")
            say(f"  {e['run']} ({what}): {session}", f"    {shlex.join(map(str, command))}")
            if not args.yes:
                continue
            try:
                r = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=120,
                                   stdin=subprocess.DEVNULL)
                problem = None if r.returncode == 0 else (
                    runners.last_line(r.stderr) or runners.last_line(r.stdout) or "no message") \
                    + f" (exit code {r.returncode})"
            except (OSError, subprocess.TimeoutExpired) as err:
                problem = str(err)
            if problem:
                failed += 1
                say(f"    not deleted: {problem}")
                continue
            if replaced:
                earlier.remove(e)
                pl.write_earlier_sessions(sd, earlier)
            else:
                e.setdefault("purged", {})[session] = round(time.time())
                pl.write_runs(sd, runs)
            say("    deleted")
        for why, sessions in kept.items():
            say(("Nothing to delete" if why == "purged already" else "Left in place") + f", {why}:",
                *(f"  {x}" for x in sessions))
        if left_out:
            say(*left_out)
        elif earlier and args.yes:
            say(f"{planning.earlier_sessions(len(earlier))} Take an entry out of that file once you know its "
                "harness no longer holds the session.")
        if doomed and not args.yes:
            say("Nothing was deleted. Deleting a session cannot be undone, and a run whose session is gone cannot "
                f"be resumed. To delete them: launch.py {sd} purge-sessions"
                + (f" --runs {args.runs}" if args.runs else "") + " --yes")
        return 1 if failed else 0
    finally:
        lock.release()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    ap.add_argument("cmd", choices=["plan", "pilot", "run", "resume", "stop", "status", "usage", "check", "release",
                                    "purge-sessions"])
    ap.add_argument("--runs", help="comma-separated run or job ids (run, resume, check, release, purge-sessions; "
                                   "not pilot)")
    ap.add_argument("--role", choices=list(ROLES), default="panellist",
                    help="what to start (run, resume): panellist runs (the default), the analyst jobs, or the "
                         "writer job once the analysts are done")
    ap.add_argument("--allow-incomplete", action="store_true",
                    help="with --role analyst: start the analysts while panellist runs are pending, running or "
                         "blocked, and tell them which runs are incomplete")
    ap.add_argument("--allow-missing", action="store_true",
                    help="go ahead when a runner's CLI is missing or signed out, leaving its runs untouched")
    ap.add_argument("--extend", action="store_true",
                    help="only with resume --runs <ids>: give the limited runs named one more allowance of "
                         "their limits")
    ap.add_argument("--released", action="store_true",
                    help="only with run or resume and --runs <ids>: also start the runs named that \"release\" let "
                         "go of, each with a new test account")
    ap.add_argument("--force", action="store_true",
                    help="only with check: run a success check again though the account its verdict was made "
                         "with is gone, and replace that verdict with what the check says now")
    ap.add_argument("--grace", type=float, default=10.0, metavar="SECONDS",
                    help="how long a process gets to finish its write after SIGTERM, before SIGKILL (default "
                         "10). Given to each process when it starts: one already running keeps the grace it has")
    ap.add_argument("--poll", type=float, default=1.0, metavar="SECONDS",
                    help="how often the launcher looks for runs that have ended and for a request to stop "
                         "(default 1). Time limits do not depend on it")
    ap.add_argument("--yes", action="store_true",
                    help="with purge-sessions: delete the sessions. Without it they are only listed")
    ap.add_argument("--json", action="store_true", help="plan, status or usage as JSON")
    args = ap.parse_args()
    if args.force and args.cmd != "check":
        raise SystemExit("--force goes with check: it runs a success check again for a run whose test account is "
                         "gone, and replaces the verdict on record.")
    cfg = pl.load_study(args.study_dir)
    command = {"plan": plan, "stop": stop_launcher, "status": status, "usage": usage, "check": check_runs,
               "release": release_runs, "purge-sessions": purge_sessions}.get(args.cmd, launch)
    try:
        code = command(args, cfg)
        sys.stdout.flush()
    except BrokenPipeError:  # whoever read the output stopped reading, as "| head" does: that is no traceback
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
