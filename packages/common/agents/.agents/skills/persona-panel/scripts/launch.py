#!/usr/bin/env python3
"""Start, limit, track and resume a study's runs as headless CLI processes.

Each run is one process of a harness CLI, started through its model entry's runner
(scripts/runners/) under a watchdog of its own (run_watchdog.py). The analysts and the writer of
the synthesis are jobs, started the same way. An interview is the one run that is many
processes: a participant and an interviewer, each a session of its own, which the launcher
carries turn by turn ("Interview studies", below). The launcher stays in the foreground until
the runs it started have ended and prints one line per state change, so put it in the
background with your shell tool, or run it in a terminal. Exit code 0 when every run it was
asked for is done, 1 otherwise.

Usage: launch.py <study-dir> <command> [options]
  plan [--json]                            # what would run, its limits, estimate and ceiling
  pilot                                    # the first persona on each model entry (no --runs)
  run [--runs <ids>] [--allow-missing]     # start pending and failed runs
  resume [--runs <ids>]                    # continue partial and blocked runs
  resume --runs <ids> --extend             # also continue the limited runs named
  run --role analyst [--allow-incomplete]  # plan and start the analyst jobs
  run --role writer                        # plan and start the writer job
  run --role critic [--allow-incomplete]   # interview: plan and start the critic jobs
  run --role themes                        # interview: plan and start the themes job
  resume --role <role>                     # continue blocked jobs of that role
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
An interview has the same states, read from its turn log and recorded nowhere ("Interview
studies", below).

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

Interview studies ("type": "interview", panel_lib.py). A run is a conversation between two
sessions, a participant in panel/rooms/<run id> and an interviewer in interviewer/<run id>,
each a runs.json entry with attempts, usage and limits of its own (panel_lib.py, "Interview
entries"). Three modules divide the work: panel_lib.py owns the formats, interview.py every
rule of the conversation, and this one the processes. What is added for them:
- The role. The interviewer's entry has the role "interviewer", and both entries of a
  conversation are asked about through the role class Interview, whatever their "role" says
  (role_of()). No command takes --role interviewer: an interviewer starts and stops with its
  interview, which is named by its participant's run id in every command and every line.
- The turn log, interviews/<run id>.jsonl, is the only record of the conversation and of why it
  stopped (panel_lib.py, "The turn log"). The state of an interview is read from it every time:
    pending   no turn on record                                    next: run
    running   a launcher carries it, between two turns too         next: wait
    done      the log has an "end" record, whatever the exit code  next: nothing
              of the process that wrote it
    partial   it was put down with a turn on record: "stop", a     next: resume
              killed launcher, a reply that could not be used
              twice, or a turn of a side that had already replied
              which was stopped at limits.turn, ended with an
              error or lost its watchdog
    limited   a side has used its time or budget                   next: resume --runs <ids> --extend
    blocked   a side's harness is turning requests away            next: resume, later
    failed    a side's first process left no usable reply          next: run
  runs.json holds two facts about a conversation and no more. Whether a process of it may be
  alive: an attempt with no end, on the entry of the side that speaks (in_flight()). Whether a
  launcher carries it: "carried", on both entries (Supervisor.mark()). No "state", "reason",
  "reset_at" or "limited_by" is ever written on an entry of a conversation. "carried" counts
  only while a launcher has the study (panel_lib.carried(), held()): a launcher that was killed
  never took it off, so with no launcher an interview it left reads as its log reads, partial
  with a turn on record, to "status", the plan, check_runs.py and the usage record alike, and
  the next step is "resume", never to wait. A log that is not as a launcher writes one
  (panel_lib.py, "A malformed log") is carried by no command: its state is that of the records
  that are left, "status" and the plan say which record is wrong, and "run" and "resume" leave
  the interview alone, say what to do about the log and exit with 1.
- The loop. A launcher takes an interview up (a "start" record on a new log, a "resume" record
  on any other), then asks interview.py, turn after turn, what the log says comes next
  (interview.fold(), next_step()): a record to append, a turn to start, or a reason to put the
  interview down. So it holds no rule of its own, and a launcher that takes over from one that
  was killed decides the same from the same log. One process is alive for an interview at any
  moment. At most as many interviews are carried at once as the interviewer's runner has slots,
  and each turn then waits for a slot on its own side's runner, so a runner's concurrency counts
  processes, as it always did. While one is carried the launcher looks every 0.2 seconds at
  most, whatever --poll says.
- A turn is one process: an attempt of kind "turn" on the entry of the side that speaks, under
  a watchdog, with the pid file, the lock and the end record every attempt has. A side's first
  process is launched with its prompt in prompts/, and every later one resumes the side's
  session with one message: for the participant the interviewer's words and nothing else, for
  the interviewer the answer, a status line and any cap notice (interview.message()). Neither
  side has a tool where its runner can start a process without (run["tools"]). The watchdog is
  given limits.turn, or what is left of the side's allowance when that is less, and the attempt
  says which ("bound") and how much ("allowed").
- When a turn ends, its reply goes to the turn log first, in one synced write, and the
  attempt's end to runs.json second (Supervisor.turn_over()). Each record made from a process
  names its side and attempt, and nothing is added for a side and attempt the log already has,
  so a launcher killed between the two records nothing twice. What a turn comes to is on the
  log whole or not at all (panel_lib.append_turns()): a launcher killed while it wrote a turn
  that was lost and why the interview stops for it leaves neither to be read, and the next one
  writes both. An attempt whose reply is on the
  log is then cut down to "n", "kind", "ended" and "seconds": the log has the rest. One that
  left no reply stays whole, as evidence.
- What is not used. An interviewer's reply that does not follow the reply format, holds a
  "leak_terms" entry in its words for the participant, or is no close at the last exchange is
  never delivered: it is sent back once, with every problem named, and a second such reply in
  the same slot puts the interview down as partial, or at the last exchange ends it one
  exchange short. An interviewer that ends with topics unopened is asked once whether it means
  it. An empty answer is put to the participant once more. A participant whose first reply is
  not its situation card (or "Ready", with the card off) leaves the interview failed, with the
  reply on its log, and no interviewer is started for it. The launcher puts nothing else again
  unasked: a turn that was stopped, hung until limits.turn, failed or lost its watchdog stays
  on the log as lost until "resume", which puts that turn again and says that it does. "run"
  and "pilot" launch a side afresh once for an interview when its first process left no usable
  reply, as they retry a failed run.
- "done" is decided by the "end" record: the interviewer ended the interview, or the last
  exchange the cap allows has its answer. The launcher then writes both transcripts,
  interviews/<run id>.md and the analysts' copy analysis/transcripts/<run id>.md
  ("interview.py <study-dir> render" writes them again, for an unfinished interview too), and
  the command's last lines say where they are. The usage record is written again whenever an
  interview is put down, since that changes its state with no process ending.
- Limits. Each side has an allowance of its own over all its turns: limits.run for the
  participant, limits.interviewer for the interviewer, time and reported spend adding up as
  they do for a run. A turn is given limits.turn, or what is left of its side's time when that
  is less, and as its budget what is left of its side's. A turn stopped at limits.turn used no
  allowance up: it is lost, the interview is partial (failed, at a side's first process), and
  only "resume" puts it again. A side with nothing left, before a turn or in the middle of one,
  makes the interview limited, with the side named on its log: "resume" leaves it alone, and
  "resume --runs <ids> --extend" gives that side one more allowance and goes on at the turn
  the log reached. Every turn on record is kept. The grant is the "resume" record that names
  the side ("extended"), written before anything else: "extended" on that side's entry is a
  copy, brought level with the log whenever an interview is taken up (Supervisor.level()), so
  a launcher killed between the two loses no grant and none is counted twice. A log that begins
  again takes every grant with it, in its "start" record: a fresh start gives no allowance
  back and takes none away, and when "resume --extend" is the command that finds the log must
  begin again, the allowance it gives is in that record too.
- A runner that closes (a usage limit, a CLI that cannot do a run from this shell) starts no
  further turn of either side of an interview that has a side on it, since neither side goes
  on without the other (Supervisor.shut_out()): an interview waiting to be taken up keeps its
  state, and one that is carried is put down, when its next turn falls due or at once when
  that turn was queued. When the runner's harness is turning requests away the interview is
  blocked: its log says which side's harness, in the harness's words, and when the limit
  lifts. A runner that closed for another reason leaves it as its log reads, partial, and
  either way "resume" goes on with it. A turn already running on the other runner ends as it
  would, and is recorded first. So when the interviewer's runner is turned away every
  interview stops, and the command ends.
- A side that cannot be resumed (Supervisor.lacking()): its session was purged, a resume found
  it gone from its harness, its harness did not keep it, or its runner cannot resume one. Only
  a side with a reply on record counts, since one with none is launched anew anyway, and both
  sides are asked before each turn and before an interview is queued, so none is spent on an
  interview that cannot go on. With no answer on record the interview starts afresh: its turn
  log is moved to logs/<run id>.interview-<k>.jsonl (with its transcripts, as .md and
  .analysts.md, when "interview.py render" had written them), both entries lose their session
  and keep their attempts, their usage and the time they have used, and a new log begins. A
  command does that once for an interview. With an answer on record the interview is left
  alone, as a run with sections written and no session is: the line says which side's session
  is gone and why, the command exits with 1, and the next "resume" says so again without
  starting a process. To hold such an interview again, move its turn log to logs/ and use
  "run".
- "stop" stops the turn in flight through its watchdog, and that turn is recorded as lost. Every
  interview is put down: partial, or pending with no turn yet.
- A launcher that takes over settles a turn that ended with no launcher alive from its files in
  logs/, so the reply there becomes its turn, and adopts one still running: "resume" then goes
  on with that interview, and any other command puts it down when the turn ends. An interview
  on record as carried with no turn in flight was between two turns when its launcher was
  killed: it is put down, and "resume" continues at the turn its log reached.
- "status" has one row for each interview, on its participant's entry: the exchanges of the
  cap, the topics opened, which side is awaited or is replying, the reason its log gives,
  "between turns" or the process of the turn in flight, and for each side the turns it has
  had, its time and its usage, with what became of its session. Under a launcher a turn whose
  process has ended and is not recorded yet is "between turns" too: the launcher records it at
  its next look. With no launcher, one line names the interviews a launcher left with a turn
  in flight, which "resume" takes up. In --json the row's own figures are the participant's and
  "interview" has "exchanges", "cap", "awaiting", "side" (the side with a turn in flight) and
  "interviewer", that entry's figures. "check" and "release" are a usability study's, and
  refuse.
- "purge-sessions --runs <run id>" covers the sessions of both sides of that interview, each
  deleted from the folder its side worked in. It is refused while a turn is in flight and
  while the interview is on record as carried.

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
- for an interview study, in place of the materials: what an interview is, the guide, each cap
  and limit with who enforces it, how many interviews are carried at once, the tools each side
  has on each runner (none; what "none" leaves on a harness that cannot switch every tool off,
  in its runner's words; or the file tools, on a runner that cannot start a process without),
  one line on the tier of model both sides need, which names no model, and its notes: a
  participant or the critic on the interviewer's runner and model, and topic caps that add up
  to more than the interview's. In place of the runs, every interview: its participant's model
  entry, what each of its two sides may use, the cap of each topic its persona gets, the
  exchanges on record of its cap, and its state. The interviewer is a model entry with a row
  and limits of its own. Each provider's line says what a side sends it: a participant's gets
  its prompt and every question, the interviewer's its prompt, the guide and every answer. No
  follow-up is said of: an interview that has ended is closed
- its estimate: for a side with finished interviews what those reported, as for a run, and what
  that came to for each exchange. For one with none, input tokens at the size of one process of
  that side at each exchange, added up to the interview's cap: measured for a runner and a
  side, never for a model, on the date and CLI versions the line names, and high, since few
  interviews run to their cap. A runner with no such figure gets none
- its ceiling: the cap of each side of each interview once, plus the pool. A side on a runner
  without a cap is left out and makes it an estimate, and an allowance that --extend gave
  either side breaks it
- a problem when a run may browse and the agent-browser CLI is not on PATH: every such run
  would end as "could not be started"
- the analyst and writer jobs with their share of the synthesis pool, or which of
  synthesis.analyst and synthesis.writer is missing. For an interview study the critic jobs and
  the themes job too, in the order the jobs run with the script that stands between two of
  them, the pool divided among all of them, and synthesis.critic among what may be missing
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
have, a study with "materials": "full" on a runner that cannot open images, or a side of an
interview on a runner that is not verified for interviews or cannot resume a session. In an
interview study also when the interviewer would say a leak term, or a persona is left with no
topic. "run" refuses to start those runs for the same reasons. On a native-mode study it lists the runs and says that
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
a stopped process of its run. "usage" rewrites and prints it. In an interview study each side
of an interview is a row, named by its interview and its side ("participant", "interviewer"),
and the interviewer's model entry has a row by model key beside the panel's.

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
  (panel_lib.NOTICE) to its output file if the job left it out: under the file's title, or at
  the very top of a file that opens with no title. With no file a job is failed (and "run"
  retries it once), blocked or limited, never partial.
  "resume" continues a blocked job in its session.
- Jobs run under limits.synthesis, apart from the run limits: its minutes for each job, and its
  budget_usd as one pool divided equally among the analysts and the writer, each share a cap.

The synthesis of an interview study has four job roles, in this order (panel_lib.job_roles(),
synthesis_jobs()), and a script between two of them:
    run --role analyst    analyst-<n>   analysis/qual-<n>.md       what each participant said,
                                                                   as evidence notes
    run --role critic     critic-<n>    analysis/critique-<n>.md   marks on the interviewer's
                                                                   questions
    extract_notes.py                    analysis/notes.csv, critique.csv
    run --role themes     themes        analysis/themes.md         the notes put into themes
    analyze.py                          analysis/quant.md, quant.json
    run --role writer     writer        analysis/SYNTHESIS.md      the final summary
- "synthesis": {"critic": {"runner": "<runner>", "model": "<model>"}} is the critics' model
  entry, with no default, as the analysts' and the writer's have none. There are as many critics
  as analysts, and critic <n> has the personas analyst <n> has. The themes job runs on
  synthesis.analyst. The pool is divided equally among every job planned: two analysts make
  six jobs.
- What each role waits for is one table (WAITS), and a job that is refused is not planned
  either. Analysts and critics wait for the panel, in either order: no interview pending,
  running or blocked, unless --allow-incomplete. The themes job waits for every analyst job and
  for analysis/notes.csv. The writer waits for every analyst, critic and themes job and for
  analysis/quant.md. A refusal for a file names the script that writes it.
- An analyst or a critic none of whose interviews has a turn on record has nothing to read. It
  refuses the command, or with --allow-incomplete is passed over with a line while the jobs
  that have something to read run: after a pilot one half of the personas may have no
  interview. --runs <job ids> judges the jobs it names alone. A job that was passed over is
  still pending, so the themes job and the writer wait for it.
- A job is done again by deleting its file and running its role again, and a done job is out
  of date (interview.out_of_date(), from the attempts in runs.json and the turn logs, never
  from a file's time) when an analyst's or a critic's interviews were held, went on or ended
  after its brief was written, or when a job that a themes job or a writer reads was launched
  again after its own last launch, or when a file a themes job or a writer was given to read
  has changed or gone with no job run again. For the last, the launch of such a job records a
  fingerprint of each file its brief names, in the attempt ("read", panel_lib.py "Job
  entries"), taken as the brief is written. "run --role" says which, and that deleting the
  job's file and running the role again puts it right, in place of what comes next, and exits
  with 1. The job stays done: the lead decides. The plan says the same against the job's row
  and under the table. A role that reads a job which is out of date in the second or the third
  way is refused.
- The scripts between the jobs leave no record, so each is asked what it would write now
  (no_longer()): the themes job is refused while analysis/notes.csv is not what the analysts'
  files give, and the writer while analysis/quant.json is not what analyze.py would write.
- A job command that finds every job done starts nothing and says so, with the file to delete
  to have one done again (done_already()).
- "context_files" go to the writer alone, which is never given a transcript: a path under
  interviews/, analysis/transcripts/, prompts/, interviewer/, panel/ or logs/ is refused when
  study.json is loaded (panel_lib.NOT_CONTEXT).
- The briefs are interview.brief()'s, from assets/interview-qual-brief.md,
  interview-critique-brief.md, interview-themes-brief.md and interview-synthesis-brief.md
  (interview.py, "The jobs of the synthesis", has what each job is given and kept from). Before
  an analyst's or a critic's brief is written, both transcripts of every interview with a turn
  on record are written again, so one that never ended has them too, and an analyst's brief
  lists its unfinished interviews with their state.
- Once the jobs of a role are done, the command's last line says what to read and what comes
  next (after_jobs()).

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

Debriefs. "interview.py <study-dir> debrief" interviews finished runs of a review or usability
study, each in the session it worked in, through the supervisor here and with the loop of an
interview study, unchanged: a debrief is told apart by the kind of its conversation
("debrief", on its interviewer's entry and in its log's "start" record), never by the study's
type. panel_lib.py, "Debriefs", has what it leaves on record, and interview.py its command.
- The interviewer's side is an entry of its own, interviewer-<run id>, with "kind": "debrief":
  a prompt from assets/interviewer-brief-debrief.md, no tools where its runner can start it
  without, an empty folder. It alone is "carried" (Supervisor.own(), mark()), and its entry
  and the turn log interviews/<run id>.jsonl hold the debrief's state.
- The participant's side is the finished run's own entry. Each of its turns is an attempt of
  kind "debrief": a resume of the run's session, in the run's own folder and with the tools it
  had, with no browser session and no test account, as a follow-up to it has none. The first
  question it is sent is inside assets/debrief-opening.md, which says what a debrief is and
  that it is spoken, and each later one is under the one line of assets/debrief-question.md
  (interview.message()).
- The run never moves. Nothing writes its "state", "reason", "reset_at", "limited_by",
  "extended" or "carried", its "seconds_used" is summed over its own attempts alone
  (pl.APART_KINDS), and what its debrief turns used is kept apart in its "debrief"
  (Supervisor.count_turn()) and taken off its own usage (planning.usage_of()). Wherever a
  follow-up attempt is told from the run's own, a debrief attempt is too: the step limit of
  a usability run is not watched in one (step_limit()), a sequential study does not hold one
  back or reset the product for one (fill(), reset_due()), "status" counts it among the
  debrief's turns, and the usage record shows both sides under the role "debrief".
- Its persona file is copied to logs/<run id>.<attempt>.before before each of its turns
  (Supervisor.before_debrief_turn()), in the order a follow-up keeps: the copy, the attempt in
  runs.json, the process. When the turn has ended, a file that differs from the copy is put
  back from it, and what the turn left is kept in logs/<run id>.<attempt>.rejected.md
  (restore()): then the reply goes to the turn log, then the attempt's end to runs.json, and
  the copy goes last. No decision is on record, where a follow-up needs one: all a turn can
  come to is the copy, so a launcher killed anywhere does the same again. An attempt that is
  taken back has the file put back first and its copy deleted last. Until the attempt's end
  is in runs.json every reader reads the copy (pl.read_persona()).
- A usability run's evidence folder is kept and put back with it, in the same order and by the
  same rules (keep_evidence(), restore_evidence()): a turn works in panel/ with the file tools
  the run had, on either runner, so the step log and the screenshots are as open to it. The
  folder is copied to logs/<run id>.<attempt>.before.evidence/, each file that differs from
  its copy when the turn has ended is put back, and what the turn left of it is kept in
  logs/<run id>.<attempt>.rejected.evidence/. A file the turn added is left in place and
  named in the line that says what was put back. No reader is given this copy: while a turn
  runs the folder is read as it stands. Nothing else under panel/ is copied: another run's
  persona file that a turn changed is on the modification record, as during any run.
- Each side has limits.debrief over all its turns, once, and a turn limits.turn's default or
  what is left of its side's when that is less (Supervisor.allowed()). A side that has used
  it makes the debrief limited, which is its end: there is no --extend for a debrief, and its
  transcripts are written from what there is (put_down()).
- What stops one short is what stops an interview, with two differences. A debrief never
  starts afresh for want of its participant's session, which is the finished run's and the
  only place it can be held: it is left alone (no_session()). And the command that goes on
  with one that is pending, partial, blocked or failed is "interview.py <study-dir> debrief
  --runs <ids>" again, which writes a "resume" record "by": "debrief": "run" and "resume"
  here take up no debrief. They settle a turn of one that a killed launcher left, adopt one
  still running and put its debrief down when it ends, and "stop" stops one.
- The jobs. An analyst's brief names the analysts' copies of the transcripts of the debriefs
  held with its personas' runs, and the writer's names them all, as product feedback that
  changed no score and is cited as given in a debrief (debriefs_note():
  assets/qual-brief-debriefs.md and the three of its kind, in place of <DEBRIEFS>). No script
  tallies a debrief. So debrief before the analysts are planned. The jobs are refused while a
  turn of a debrief is still running (unsettled_debriefs()). A debrief that is not finished
  holds none back: "run" names it in a line before the jobs start, with the command that goes
  on with it (unfinished_debriefs()), and the plan does too.
- "status" has the debrief on its run's row, under "debrief" (debrief_facts()), with a line
  that counts the debriefs and names the command that goes on with one. The plan has a
  section on debriefs for a study that has the "debrief" block or has held one, which stops
  no run. "purge-sessions --runs <run id>" covers the run's session and its interviewer's.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import accounts  # noqa: E402
import browser_session as browser  # noqa: E402
import interview  # noqa: E402
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
PURGED = "its session was purged (purge-sessions)"  # the lead had it deleted
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
# What "status" says an interview waits for, by what its turn log awaits (interview.fold()).
AWAITED = {"card": "awaiting the participant's first reply", "opening": "awaiting the interviewer's first question",
           "answer": "awaiting an answer", "question": "awaiting a question"}
# The same in a row of "status" while the process of that turn is alive.
REPLYING = {"card": "the participant is writing its first reply",
            "opening": "the interviewer is writing its first question",
            "answer": "the participant is answering", "question": "the interviewer is writing its next question"}
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


# What a turn of a debrief keeps of a usability run's evidence folder in logs/, after "<run id>.<attempt>.": the
# folder as it was before the turn, and what the turn left of each file of it that was put back (restore()).
EVIDENCE_BEFORE, EVIDENCE_REJECTED = "before.evidence", "rejected.evidence"
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
        return pl.workdir(cfg["_dir"], entry)

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

    @staticmethod
    def state(cfg: dict, entry: dict) -> str:
        return pl.run_state(Panellist.progress(cfg, entry), entry.get("state"))

    @staticmethod
    def options(cfg: dict, entry: dict) -> dict:
        return {}  # what an attempt's run gets besides the entry: nothing, so the file tools every run has


class Synthesis:
    """The same questions about a job of the synthesis (an analyst or the writer, and in an
    interview study a critic or the themes job): one process that works in the study
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

    @staticmethod
    def state(cfg: dict, entry: dict) -> str:
        return pl.run_state(Synthesis.progress(cfg, entry), entry.get("state"))

    @staticmethod
    def options(cfg: dict, entry: dict) -> dict:
        return {}


def side_of(entry: dict) -> str:
    """Which side of a conversation an entry speaks for, as a turn log names it (pl.SIDES): the
    interviewer's entry is the interviewer, and any other the participant, the finished run of
    a debrief included."""
    return "interviewer" if entry["role"] == "interviewer" else "participant"


def named(entry: dict) -> str:
    """How a line to the lead names the entry a process belongs to: its id, and for an entry of a
    conversation its interview and its side, "P01-cx, the interviewer's turn". Every command
    takes an interview by its run id, and none takes an interviewer's entry, so no line names
    one by itself. A finished run with a turn of its debrief out is named the same way, for
    as long as that turn has no end."""
    turn = "interview" in entry or (pl.open_attempt(entry) or {}).get("kind") in pl.TURN_KINDS
    return f"{pl.interview_of(entry)}, the {side_of(entry)}'s turn" if turn else entry["run"]


class Interview:
    """The same questions about an entry of a conversation: either side of an interview, each
    with a session, attempts, usage and limits of its own (panel_lib.py, "Interview entries").
    Every process of it is one turn, in a folder of its own, with no tool where its runner can
    start one so (interview.tools()). Its progress and its state are read from the turn log
    both entries name, every time: runs.json holds neither. What a turn is sent is the entry's
    prompt for a side's first process and interview.message() for every later one, so it has
    no resume_message()."""

    noun = "interview"

    @staticmethod
    def workdir(cfg: dict, entry: dict) -> Path:
        return pl.workdir(cfg["_dir"], entry)

    @staticmethod
    def progress(cfg: dict, entry: dict) -> dict:
        return pl.interview_progress(cfg, entry, pl.read_turns(cfg["_dir"], pl.interview_of(entry)))

    @staticmethod
    def limits(cfg: dict, entry: dict) -> dict:
        if entry.get("kind") == "debrief":  # the interviewer of a debrief: each side of one has limits.debrief
            return pl.limits_for(cfg, "debrief")
        if side_of(entry) == "interviewer":
            return pl.limits_for(cfg, "interviewer")
        return pl.limits_for(cfg, "panellist", entry["key"])

    @staticmethod
    def prompt(cfg: dict, entry: dict) -> str:
        return (cfg["_dir"] / entry["prompt"]).read_text()  # the side's whole launch prompt, verbatim

    @staticmethod
    def browse(cfg: dict, entry: dict) -> bool:
        return False

    @staticmethod
    def collect(cfg: dict, entry: dict, result: dict, ending: str | None) -> str | None:
        return None  # a turn's reply goes to the turn log (Supervisor.turn_ended())

    @staticmethod
    def state(cfg: dict, entry: dict) -> str:
        return pl.interview_state(pl.read_turns(cfg["_dir"], pl.interview_of(entry)), pl.carried(entry, held(cfg)))

    @staticmethod
    def options(cfg: dict, entry: dict) -> dict:
        return {"tools": interview.tools(side_of(entry), runners.get(entry["runner"]))}


# An entry the launcher runs has its role here. The jobs of the synthesis are in the order they run, and
# "critic" and "themes" are an interview study's alone (pl.job_roles()). An interviewer starts and stops
# with its interview, so no command takes it as a --role (STARTABLE).
ROLES = {"panellist": Panellist, "analyst": Synthesis, "critic": Synthesis, "themes": Synthesis,
         "writer": Synthesis, "interviewer": Interview}
STARTABLE = [role for role in ROLES if role != "interviewer"]


def role_of(entry: dict):
    """The role class of an entry: Interview for an entry of a conversation, whatever its "role"
    says (a participant is a panellist), and otherwise what ROLES has for its role."""
    return Interview if "interview" in entry else ROLES[entry["role"]]


def progress_of(cfg: dict, entry: dict) -> dict:
    return role_of(entry).progress(cfg, entry)


def state_of(cfg: dict, entry: dict) -> str:
    return role_of(entry).state(cfg, entry)


def held(cfg: dict) -> bool:
    """Whether a launcher has the study, which is what makes "carried" on an entry of a
    conversation count (pl.carried()): asked of the study lock (Lock.holder()), which a
    launcher's own process finds held as any other does, so the supervisor and "status" go by
    one rule. Asked once for a command and kept on cfg, so that every state a command reads
    is read against the same answer. A command that takes the study does so before it reads a
    state, and holds it until it ends."""
    if "_held" not in cfg:
        cfg["_held"] = bool(Lock.holder(cfg["_dir"]))
    return cfg["_held"]


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
    limits, times = role_of(entry).limits(cfg, entry), 1 + (entry.get("extended") or 0)
    return {"minutes": limits["minutes"] * times, "budget_usd": limits["budget_usd"] * times}


def left(cfg: dict, entry: dict) -> dict:
    """What is left of the allowance: {"seconds", "budget_usd"}. Spend a harness does not report
    counts as none, so the time limit is what bounds such a run. That includes the spend of an
    attempt whose process was stopped before it reported any (planning.unreported): no figure is
    made up for it, so the budget left can be more than is truly left until its session reports."""
    total = allowance(cfg, entry)
    return {"seconds": total["minutes"] * 60 - (entry.get("seconds_used") or 0),
            "budget_usd": total["budget_usd"] - (usage_of(entry)["cost_usd"] or 0)}


def used_up(remaining: dict, total: dict) -> list[str]:
    """What an allowance (allowance()) has nothing left of, given what is left of it (left()):
    "none of its 15 min left", "none of its $2 left", or neither. With either, nothing more is
    started against it."""
    return [f"none of its {allowed} left" for gone, allowed in (
        (remaining["seconds"] <= 0, f"{total['minutes']:g} min"),
        (remaining["budget_usd"] < MIN_BUDGET, f"${total['budget_usd']:g}")) if gone]


def session_gone(e: dict, runner, whose: str = "its") -> str | None:
    """Why an entry's session cannot be continued, None when it can: it was purged, a resume
    found it gone from the harness, its harness never kept it, none was recorded, or the
    entry's runner cannot resume one. Nothing is started to find out: each is on record.
    whose is how the sentence names the session's owner: "its" of a run, "the participant's"
    of a side of a conversation."""
    session = e.get("session")
    for why, noted in ((PURGED, "purged"), (LOST, "lost"), (NOT_SAVED, "unsaved")):
        if session in (e.get(noted) or {}):
            return whose + why[len("its"):]
    if not session:
        return "no session was recorded" if whose == "its" else f"{whose} session was never recorded"
    return None if runner.capabilities()["resume"] else f"{e['runner']} cannot resume a session"


# ---------------------------------------------------------------- the supervisor

# What starting an attempt overwrites, or takes out of the entry.
UNDONE = ("state", "pid", "pid_identity", "session", "reason", "reset_at", "limited_by", "checks", "released",
          "task_attempts")


asking = pl.asking  # the follow-up attempt of a run that is not settled yet


def in_flight(e: dict) -> bool:
    """Whether a process of the entry may be alive: it is recorded as running, or has an attempt
    that leaves its state alone and has no end yet (pl.open_attempt()): a follow-up question
    that is not settled, or a turn of a conversation. An entry of a conversation has no state
    on record, so that attempt is all that says so of it: one with no attempt is never in
    flight, and one that a launcher carries between two turns is not either ("carried")."""
    if "interview" in e:
        return bool(pl.open_attempt(e))
    return e.get("state") == "running" or bool(pl.open_attempt(e))


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
    answered(): see "Follow-up questions" in the module docstring.

    A conversation is carried turn by turn: see "Interview studies" in the module docstring.
    Two more kinds are queued for one. (participant entry, "interview") waits to be taken up
    (take_up()). (entry of the side that speaks, "turn") is one process to start, and sending
    has the step it carries out, by the entry's id. interviews has every conversation this
    command carries, by its run id: {"p": the participant's entry, "i": the interviewer's,
    "kind": "interview" or "debrief", "own": whether this command goes on with it, false for one
    whose turn it only adopted}. Each of them has, at every moment, exactly one of: a queued
    turn, a child, or a put_down() under way. drop() and sweep() hold that, so that no exit of
    start() or ended() has to. by is the command as a "resume" record names it. What stops a
    conversation short of its end is decided in three places and nowhere else: cannot_send()
    before a turn is queued, shut_out() for a runner that starts nothing more, and no_session()
    for a side that cannot be resumed.

    A debrief is such a conversation with a finished run for its participant (module docstring,
    "Debriefs"): that run's entry is no entry of the conversation (own()), its turns are of kind
    "debrief" (turn_kind()), counted against limits.debrief (allowed()), and before and after
    each the two hooks see to its persona file and, for a usability run, its evidence folder
    (before_debrief_turn(), after_debrief_turn())."""

    def __init__(self, cfg: dict, runs: list[dict], grace: float, poll: float, retry: bool = False,
                 stop: StopSignal | None = None, question: dict | None = None, by: str = "run"):
        self.cfg, self.sd, self.runs = cfg, cfg["_dir"], runs
        self.grace, self.poll, self.retry, self.stop = grace, poll, retry, stop or StopSignal()
        self.question, self.by = question, by
        self.queue, self.children, self.adopted = [], [], []
        self.interviews = {}    # run id -> the conversation this command carries
        self.sending = {}       # entry id -> the step its queued turn carries out (interview.next_step())
        self.turned_away = {}   # runner closed because its harness turns requests away -> {"lifts", "said"}
        self.extend = set()     # the limited interviews "resume --extend" named: take_up() extends the side in need
        self.restarted = set()  # the interviews this command has started afresh for want of a session: once each
        self.closed = {}        # runner -> why it starts nothing more in this command
        self.retried = set()    # runs already retried by this command
        self.refused = False    # a process could not be started at all
        self.let_go = set()     # runs whose account this launcher has tried to tear down: once for each command
        self.left_alone = False  # a run this command was asked to continue cannot be
        self.distrusted = set()  # the browser session records this command has refused, and said so
        self.held = None        # why no command of the study may be started: what accounts.recover() stopped for
        self.given = {}         # job id -> the fingerprints of what its brief gives it to read (plan_jobs())
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
            if e["role"] != "panellist" or "interview" in e:  # whose file is its turn log, which the launcher writes
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

        A turn of a conversation in flight is settled or adopted like any attempt, and an
        adopted one has its conversation carried from here on, though not as this command's own
        (interviews, "own"). Then every conversation on record as carried that has no attempt
        in flight and was not adopted is put down: its launcher was killed between two turns,
        or with a turn that has now been settled or taken back. One whose turn is still alive
        under a command that adopts nothing stays carried, for the next launcher.

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
                turn = e["attempts"][-1]["kind"] in pl.TURN_KINDS
                self.take_back(e, "an earlier launcher died before starting it")
                say(f"{pl.interview_of(e)}: a turn of the {side_of(e)} was never started (an earlier launcher died "
                    "before starting it)" if turn else
                    f"{e['run']}: {state_of(self.cfg, e)} (an earlier launcher died before starting it)")
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
            if e["attempts"][-1]["kind"] in pl.TURN_KINDS:
                run = pl.interview_of(e)
                self.interviews[run] = {**self.pair(run), "own": False}
                say(f"{run}: a turn of the {side_of(e)} is running, adopted from an earlier launcher (pid {e['pid']})")
                continue
            say(f"{e['run']}: {'being asked a follow-up question' if asking(e) else 'running'}, adopted from an "
                f"earlier launcher (pid {e['pid']})")
        for run in dict.fromkeys(pl.interview_of(e) for e in self.runs if e.get("carried")):
            pair = self.pair(run)
            if run not in self.interviews and not (in_flight(pair["p"]) or in_flight(pair["i"])):
                self.put_down(run)
        self.sweep_browsers()
        if final:
            self.settle_final()
        self.settle_followups()
        self.sweep()

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
            for a in e.get("attempts") or []:  # of a follow-up, or of a turn of a debrief (pl.APART_KINDS)
                if a.get("kind") in pl.APART_KINDS and a.get("ended") is not None:
                    self.drop_copies(e, a["n"])
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
        """Start whatever is queued and fits within its runner's concurrency. An interview that
        waits is taken up when fewer are carried than its interviewer's runner has slots: started
        all at once, half of them would always wait for that runner between two turns. Each turn
        then waits for a slot on the runner of its own side like any other process, so a
        runner's concurrency still counts processes. An item of a conversation is never left
        waiting for a runner that starts nothing more, whichever of its two sides is on it: it
        is dropped (drop()), by the rule close() goes by."""
        for item in list(self.queue):
            if item not in self.queue:
                continue
            name = item[0]["runner"]
            if self.runners_of(item) & self.closed.keys():
                if item[1] == "interview" or item[1] in pl.TURN_KINDS:
                    self.drop(lambda queued: queued is item)
                continue
            if item[1] == "interview":
                host = self.pair(pl.interview_of(item[0]))["i"]["runner"]
                most = pl.runner_concurrency(self.cfg, host, self.runner(host).capabilities()["default_concurrency"])
                if sum(carried["i"]["runner"] == host for carried in self.interviews.values()) < most:
                    self.queue.remove(item)
                    self.take_up(item[0])
                continue
            if self.cfg.get("sequential") and item[0]["role"] == "panellist" and item[1] not in pl.TURN_KINDS and any(
                    c.entry["role"] == "panellist" for c in self.children):
                continue  # one panellist at a time, across all runners: a turn of a debrief uses no product
            cap = pl.runner_concurrency(self.cfg, name, self.runner(name).capabilities()["default_concurrency"])
            if sum(c.entry["runner"] == name for c in self.children) < cap:
                self.queue.remove(item)
                self.start(*item)

    def start(self, e: dict, kind: str):
        """Start one attempt of an entry under a watchdog of its own, on record in runs.json
        before its process exists. kind is the attempt's: launch, retry, resume or restart for
        a run or job, followup for a follow-up question, and for one turn of a conversation
        "turn", or "debrief" on a finished run (pl.TURN_KINDS), which carries out the step that
        sending holds for the entry.

        A turn's watchdog is given limits.turn, or what is left of its side's allowance when
        that is less. The attempt records the figure as "allowed", and which of the two it was
        as "bound": outcome() charges an attempt whose watchdog was killed up to "allowed", so
        it must be what the watchdog was given and never the side's whole remainder. A turn
        leaves its entry's state, reason and checks alone, as a follow-up does, and "was" keeps
        every field undo() would take off, so taking the attempt back costs the entry nothing.
        Every way this returns with no process leaves a carried conversation to sweep()."""
        role, runner = role_of(e), self.runner(e["runner"])
        number = self.question["n"] if kind == "followup" else None
        turn = kind in pl.TURN_KINDS
        step = self.sending.pop(e["run"], None) if turn else None
        if number:  # an allowance of its own for each question: what the run has used does not count
            total = pl.limits_for(self.cfg, "followup")
            remaining = {"seconds": total["minutes"] * 60, "budget_usd": total["budget_usd"]}
        elif turn:
            remaining, total = self.allowed(pl.interview_of(e), e)
        else:
            remaining, total = left(self.cfg, e), allowance(self.cfg, e)
        spent = used_up(remaining, total)
        if spent and turn:  # not reached: cannot_send() answered before the turn was queued, and wrote the "halt"
            return
        if spent:
            e.update(state="limited", reset_at=None, reason=" and ".join(spent)
                     + f" after {plural(len(e.get('attempts') or []), 'attempt')}",
                     limited_by="time" if remaining["seconds"] <= 0 else "budget")
            self.save()
            say(f"{e['run']}: limited without starting: {e['reason']}")
            self.finish(e)
            return
        # What the watchdog is given: all that is left, and for a turn no more than one turn may take.
        most = pl.limits_for(self.cfg, "turn")["minutes"] * 60 if turn else None
        bound = None if not turn else "turn" if most < remaining["seconds"] else "allowance"
        given = most if bound == "turn" else remaining["seconds"]
        usability = self.cfg["type"] == "usability" and e["role"] == "panellist"
        own = not number and not turn  # an attempt of the run itself: it has the account, the evidence and the steps
        had = (e.get("account") or {}).get("times")  # which provisioning its last attempt ran with
        account = self.prepare(e, kind) if usability and own else None
        if account is False:
            return
        # Provisioned again for this attempt: the account its session knew was torn down (accounts.py).
        renewed = bool(account) and had is not None and account.get("times") != had
        limits = {"minutes": given / 60,
                  "budget_usd": remaining["budget_usd"] if runner.capabilities()["budget_cap"] else None}
        n = len(e.get("attempts") or []) + 1
        # A follow-up to a usability run answers from what it saw: its account is gone, and it opens nothing.
        # Nor does a turn of a conversation, which is words alone.
        browse = (role.browse(self.cfg, e) and runner.capabilities()["browser"] and not (usability and number)
                  and not turn)
        run, workdir = {**e, "browse": browse, **role.options(self.cfg, e)}, role.workdir(self.cfg, e)
        hooks, session = None, None
        if browse:  # the attempt's own browser session: its watchdog starts it before the CLI and stops it after
            session = browser.plan(self.base(e, n).resolve(), e["run"])
            run["browser_env"] = browser.changes(session)
        if usability and kind == "resume":  # on the run before its message is made, which gives each number
            e["task_attempts"] = tracker.issue_attempts(self.cfg, tracker.run_view(self.sd, self.cfg, e))
        try:
            if number:
                command = runner.resume_command(run, e["session"], self.question["message"](e), workdir, limits)
            elif turn:
                command = self.turn_command(e, step, runner, run, workdir, limits)
            elif kind == "resume":  # a usability run's own message says what became of its browser (runs.py)
                command = runner.resume_command(run, e["session"],
                                                role.resume_message(self.cfg, {**e, "new_account": renewed})
                                                + (BROWSER_RESTARTED if browse and not usability else ""),
                                                workdir, limits)
            else:
                command = runner.launch_command(run, role.prompt(self.cfg, e), workdir, limits)
        except ValueError as err:
            self.refused = True
            say(f"{named(e)}: not started, {e['runner']} cannot build its command: {err}")
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
        if usability and own and kind != "resume":  # a new session: no step or screenshot of an earlier one
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
        unkept = self.before_debrief_turn(e, n, kind)
        if unkept:  # no copy, no turn: the copy is what puts the file back, and what readers read meanwhile
            self.refused = True
            say(f"{pl.interview_of(e)}: a turn of its debrief was not started: {unkept}.")
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
            "n": n, "kind": kind, "started": round(time.time(), 3), "allowed": round(given, 3),
            "ended": None, "seconds": None, "exit_code": None, "outcome": None,
            **({"bound": bound} if turn else {"state": None}),  # a turn decides no state: its turn log has it
            "session": command["session_id"], "was": {k: e[k] for k in UNDONE if k in e},
            **({"followup": number} if number else {}),
            **({"evidence_aside": aside} if aside else {}),
            # What its brief gave a job to read, as it was when the brief was written: only a launch starts from one.
            **({"read": self.given[e["run"]]} if kind == "launch" and self.given.get(e["run"]) else {}),
            # What its step log held already: the step limit is watched in what this attempt adds (over_steps()).
            **({"steps": {"seen": "".join(marks(self.log_lines(e))), "begun": {}}} if usability and own else {})}]
        e.update(pid=None, pid_identity=None)
        if number:  # the run stays as it is: asking() is what says a process is at work on it
            pl.record_followup(self.sd, number, e["run"], attempt=n, session=command["session_id"])
        elif turn:  # the entry stays as it is too: a side's first process alone gives it a session, the one it names
            if step["how"] == "launch":
                e["session"] = command["session_id"]
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
                     str(end), f"{given:.3f}", f"{self.grace:.3f}", *command["argv"]],
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
        if not turn:  # a turn is one of many: its interview said that it is running, and says how it ends
            say(f"{e['run']}: asked follow-up {number} (attempt {n}, pid {e['pid']})" if number
                else f"{e['run']}: running ({kind}, attempt {n}, pid {e['pid']})")

    def turn_command(self, e: dict, step: dict, runner, run: dict, workdir: Path, limits: dict) -> dict:
        """The command of one turn, from the step it carries out (interview.next_step()): a
        side's first process is launched with its prompt, as it is, and every later one resumes
        the side's session with the message its frame makes of the turn log
        (interview.message()). Raises ValueError as a runner does for a command it cannot build,
        a session that is no session among them."""
        if step["how"] == "launch":
            return runner.launch_command(run, role_of(e).prompt(self.cfg, e), workdir, limits)
        run_id = pl.interview_of(e)
        said = interview.message(step, interview.fold(pl.read_turns(self.sd, run_id)), self.guide_of(run_id))
        return runner.resume_command(run, e.get("session"), said, workdir, limits)

    def before_debrief_turn(self, e: dict, n: int, kind: str) -> str | None:
        """What a turn put to a finished run needs before its attempt is on record: nothing for a
        turn of an interview, whose participant has no persona file. A debrief keeps a copy of
        the persona file here, as a follow-up does, for after_debrief_turn() to put back: the
        copy, then the attempt in runs.json, then the process, the order every reader relies on
        (the snapshot rule, panel_lib.py). A usability run has its evidence folder copied first,
        in the same order (keep_evidence()): its session works in panel/ with the file tools it
        had, so its step log and screenshots are as open to a turn as its persona file is.
        Returns why a copy could not be kept, in a clause: the turn is then not started."""
        if kind != "debrief":
            return None
        if self.cfg["type"] == "usability":
            try:
                self.keep_evidence(e, n)
            except OSError as err:  # no longer a folder, or a file of it, that can be read as the run's own
                return f"its evidence folder could not be copied before the turn ({pl.unread(err)})"
        try:
            pl.keep_copy(self.log(e, n, "before"), pl.persona_bytes(self.sd, self.sd / e["file"]))
        except OSError as err:  # no longer a file that can be read as the run's own
            return f"its persona file could not be copied before the turn ({pl.unread(err)})"
        return None

    def keep_evidence(self, e: dict, n: int):
        """Keep a copy of a usability run's evidence folder in logs/<run id>.<n>.before.evidence,
        for restore() to put back from: every file of it, the step log and each screenshot,
        read as evidence is read (pl.read_evidence()) and kept as a copy of a persona file is
        (pl.keep_copy()). Anything else in the folder, a folder or a link, is nothing a script
        reads as evidence: an empty folder of its name stands for it, so that the copy also
        says what the folder held, and a name that is not in it is one the turn made.

        The copy is filled under another name and takes its own in one step, in place of
        whatever an attempt that never ran left there, so a copy on disk is whole. Raises
        OSError when the folder or a file of it cannot be read as the run's own, or the copy
        cannot be made."""
        copy = self.log(e, n, EVIDENCE_BEFORE)
        made = copy.with_name(f".{copy.name}.{os.getpid()}.tmp")
        shutil.rmtree(made, True)
        try:
            made.mkdir()
            for name, kind in pl.evidence_names(self.sd, e["run"]):
                if kind == "file":
                    pl.keep_copy(made / name, pl.read_evidence(self.sd, e["run"], name))
                else:
                    (made / name).mkdir()
            shutil.rmtree(copy, True)
            os.rename(made, copy)
        except OSError:
            shutil.rmtree(made, True)
            raise

    def after_debrief_turn(self, e: dict, attempt: dict):
        """What a turn put to a finished run needs once its process has ended, before its reply
        goes to the turn log: nothing for a turn of an interview. A debrief puts the persona
        file, and a usability run's evidence folder, back here when the turn changed them
        (restore())."""
        if attempt["kind"] == "debrief":
            self.restore(e, attempt["n"])

    def restore(self, e: dict, n: int):
        """Put a finished run's persona file back as it was before attempt n, a turn of its
        debrief, when it is not as the copy made before that turn has it: a debrief is spoken,
        and a turn of it may write nothing. What the turn left is kept first, in
        logs/<run id>.<n>.rejected.md, as a rejected follow-up's is.

        No decision goes on record, where a follow-up needs one: all a turn can come to is the
        copy, so putting the file back from it is the same done once or twice, and a launcher
        killed anywhere between the turn's end and the attempt's end in runs.json is followed
        by one that does it again. What was left is kept only while the file still differs
        from the copy, so a file already put back never replaces it. The file is written
        through no symbolic link (pl.write_persona()): where it cannot be put, the launcher
        stops and says so, with the attempt still open and the copy still what is read.

        A usability run has its evidence folder put back first, by the same rules
        (restore_evidence())."""
        if self.cfg["type"] == "usability":
            self.restore_evidence(e, n)
        copy, left = pl.read_copy(self.log(e, n, "before")), self.left(e)
        if copy is None:
            say(f"{e['run']}: the copy made of its persona file before a turn of its debrief is gone, so the file "
                "was not checked against it.")
            return
        if left == copy:
            return
        kept = self.log(e, n, "rejected.md")
        if left is not None:
            pl.keep_copy(kept, left)
        try:
            pl.write_persona(self.sd, self.sd / e["file"], copy)
        except OSError as err:  # readers go on reading the copy until a launcher can put the file back
            raise SystemExit(
                f"{e['run']}: a turn of its debrief changed its persona file {e['file']}, which could not be put "
                f"back ({pl.unread(err)}). Nothing is written through a symbolic link. The turn is not settled, and "
                "until it is the run is read as it stood before it. Make every folder above the file a plain folder "
                f"that can be written, with no folder at the file's own name, then settle it with: launch.py "
                f"{self.sd} stop")
        say(f"{e['run']}: a turn of its debrief changed its persona file, and a debrief may write nothing. The file "
            "was put back as it was before the turn"
            + (f", and what the turn left is in logs/{kept.name}." if left is not None else "."))

    def restore_evidence(self, e: dict, n: int):
        """Put each file of a finished usability run's evidence folder back as it was before
        attempt n, a turn of its debrief, when it is not as the copy made before that turn has
        it (keep_evidence()): changed, gone, or no longer a file that can be read as the run's
        own. What the turn left of it is kept first, in logs/<run id>.<n>.rejected.evidence/,
        under the file's own name. One line says what was put back.

        As with the persona file, the copy is all a turn can come to, each file is put back in
        one step and through no symbolic link, and what was left is kept only while the file
        still differs from the copy, so a launcher killed anywhere before the attempt's end is
        in runs.json is followed by one that does the same again. The run's folder is made
        again where the turn took it away. Where a file cannot be put back the launcher stops
        and says so, with the attempt still open and the copy still in logs/.

        Nothing a run wrote is deleted by the launcher: a name the folder has now and the copy
        does not is left where it is, and named in the same line. Unlike the persona file, the
        folder is read as it stands while the turn runs: no reader is given the copy."""
        run, copy, kept = e["run"], self.log(e, n, EVIDENCE_BEFORE), self.log(e, n, EVIDENCE_REJECTED)
        try:
            with os.scandir(copy) as listing:
                before = {f.name: f.is_file(follow_symlinks=False) for f in listing}
        except OSError:
            say(f"{run}: the copy made of its evidence folder before a turn of its debrief is gone, so the folder "
                "was not checked against it.")
            return
        back, saved = [], False
        for name in sorted(name for name, file in before.items() if file):
            was = pl.read_copy(copy / name)
            try:
                left = pl.read_evidence(self.sd, run, name)
            except OSError:  # gone, or no longer a file that can be read as the run's own: nothing of it is kept
                left = None
            if was is None or left == was:  # with no copy of it left in logs/, nothing to check it against
                continue
            if left is not None:
                kept.mkdir(exist_ok=True)
                pl.keep_copy(kept / name, left)
                saved = True
            try:
                root = pl.evidence_fd(self.sd, None)
                try:
                    os.mkdir(run, dir_fd=root)
                except FileExistsError:  # as it should be. A link at the folder's name is refused below
                    pass
                finally:
                    os.close(root)
                pl.write_persona(self.sd, pl.evidence_dir(self.sd, run) / name, was)
            except OSError as err:
                raise SystemExit(
                    f"{run}: a turn of its debrief changed {name} in its evidence folder, which could not be put "
                    f"back ({pl.unread(err)}). Nothing is written through a symbolic link. The turn is not settled, "
                    f"and what the folder held before it is in logs/{copy.name}/. Make {pl.EVIDENCE}/{run} and "
                    "every folder above it a plain folder that can be written, with no folder at the file's own "
                    f"name, then settle it with: launch.py {self.sd} stop")
            back.append(name)
        try:
            new = [name + ("/" if kind == "folder" else "") for name, kind in pl.evidence_names(self.sd, run)
                   if name not in before]
        except OSError:  # a folder that cannot be listed holds nothing that is read as evidence
            new = []
        said = []
        if back:
            verb, as_before = ("was", "it was") if len(back) == 1 else ("were", "they were")
            said.append(f"{pl.listed(back)} {verb} put back as {as_before} before the turn"
                        + (f", and what the turn left is in logs/{kept.name}/." if saved else "."))
        if new:
            verb = "was" if len(new) == 1 else "were"
            said.append(f"{pl.listed(new)} {verb} not there before the turn and {verb} left in place: nothing a run "
                        "wrote is deleted.")
        if said:
            say(f"{run}: a turn of its debrief wrote in its evidence folder, and a debrief may write nothing. "
                + " ".join(said))

    def drop_copies(self, e: dict, n: int):
        """Delete what was kept before attempt n, a follow-up or a turn of a debrief, for putting
        back: the copy of the persona file and, of a usability run's debrief, the copy of its
        evidence folder. Last of all, once runs.json has the attempt's end, or no longer has
        the attempt."""
        self.log(e, n, "before").unlink(missing_ok=True)
        shutil.rmtree(self.log(e, n, EVIDENCE_BEFORE), True)

    def unstarted(self, e: dict, argv: list[str], how: str, said: str, settling: bool = False,
                  closing: str = "its CLI could not be started"):
        """Put a run back as it was before an attempt whose process never ran as the CLI, say
        so, and start nothing more on its runner in this command, for the reason in closing.
        how is what happened to the command, and said the system's or the CLI's own message.
        settling is for an attempt of an earlier launcher: the runner stays open, since this
        launcher has not tried it."""
        whose = named(e)  # while the attempt is there: a finished run is named with its turn only while it has one
        self.take_back(e, f"{how} ({said})")
        say(f"{whose}: could not be started. {how}: {shlex.join(argv[:4])} ... ({said}). Nothing was marked as "
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
               for a in x.get("attempts") or [] if a["kind"] not in pl.APART_KINDS]  # neither uses the product
        return bool(ran) and not (kind == "resume" and max(ran)[1] == e["run"])

    def hold(self, e: dict, why):
        """Say that a run could not be started because something the study itself supplies
        failed, and start no further panellist run in this command: the next would fail the
        same way. Nothing is marked failed."""
        self.refused = True
        held = [x["run"] for x, kind in self.drop(lambda item: item[0]["role"] == "panellist")
                if kind not in pl.TURN_KINDS]
        say(f"{named(e)}: could not be started: {why}. Nothing was marked as failed. No further run is started in "
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
        if self.cfg["type"] != "usability" or e["role"] != "panellist" or pl.apart_attempt(e) or child.asked:
            return  # a follow-up and a turn of a debrief take no step: the step log is the run's own attempts'
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
        One that was a turn of a debrief has the file, and a usability run's evidence folder,
        put back from its copies first (restore()), whatever became of its process, and the
        copies go last the same way.
        One that was to start a usability run afresh gives the run back the evidence that was
        set aside for it (put_back())."""
        attempt = e["attempts"][-1]
        if attempt["kind"] == "debrief":  # first, while the attempt still says that the copy is what is read
            self.restore(e, attempt["n"])
        undo(e)
        if attempt.get("evidence_aside"):  # it was to start the run afresh: the run has its evidence again
            self.put_back(e, attempt["evidence_aside"])
        if attempt["kind"] == "followup":
            pl.record_followup(self.sd, attempt["followup"], e["run"], outcome="could not start", reason=why,
                               attempt=None)
        self.save()
        if attempt["kind"] in pl.APART_KINDS:
            self.drop_copies(e, attempt["n"])

    def cannot_continue(self, e: dict, lacks: str):
        """Say that a run with sections written has no session to continue, and leave it alone."""
        self.left_alone = True
        say(f"{e['run']}: {state_of(self.cfg, e)} with sections written, but {lacks}, so it cannot be continued. "
            "Left alone: finish it by hand or reset it.")

    def session_lost(self, e: dict, settling: bool):
        """A resume found its session gone from the harness. The attempt is taken back and the
        session noted, as purge-sessions notes one it deleted. The run is then started afresh
        when it has written nothing, and otherwise left for the lead to decide. A turn of a
        conversation is taken back and noted the same way, and its conversation is put down by
        the same rule (no_session()): started afresh with no answer on record, and otherwise
        left alone. So the next command knows the session is gone, and tries it no more."""
        session, asked, turn = e["session"], asking(e), e["attempts"][-1]["kind"] in pl.TURN_KINDS
        self.take_back(e, LOST)
        e.setdefault("lost", {})[session] = round(time.time())
        self.save()
        if turn:  # no record goes to the turn log: the attempt was taken back, and its number is used again
            run = pl.interview_of(e)
            self.put_down(run, self.no_session(run, e, session_gone(e, self.runner(e["runner"]),
                                                                    f"the {side_of(e)}'s")))
        elif asked:
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
        then is what the user can do about it, said after the rest, once.

        A conversation has two sides, and is on this runner when either is: an interview that
        waits to be taken up keeps its state like a queued run, and one that is carried and
        has a turn queued, for whichever side, is put down (drop()). The other side waits."""
        if name in self.closed:
            return
        self.closed[name] = why
        held = [e["run"] for e, kind in self.queue if name in self.runners_of((e, kind)) and kind not in pl.TURN_KINDS]
        stay = agree(len(held), "stays as it is", "stay as they are")
        say(f"{name}: {why}. No more launches on this runner {how_long}"
            + (f", and {plural(len(held), 'queued run')} {stay} ({', '.join(held)})" if held else "")
            + ". Other runners carry on." + (f" {then}" if then else ""))
        self.drop(lambda item: name in self.runners_of(item))

    def turn_away(self, name: str, lifts, said: str = ""):
        """close() a runner whose harness is turning requests away, for now. lifts is when the
        harness said its limit lifts, None when it did not say, and said the harness's own
        message. That this is why it closed is kept (turned_away), with both: a conversation
        with a side on it starts no further turn and reads blocked (shut_out())."""
        self.turned_away.setdefault(name, {"lifts": lifts, "said": said})
        self.close(name, TURNED_AWAY + (f", and said its limit lifts at {clock(lifts)}" if lifts else ""), "for now")

    # ---- conversations, carried turn by turn. interview.py has every rule: these ask it what to do

    def pair(self, run: str) -> dict:
        """The conversation with that run id, as interviews holds one: the one this command
        carries, or for one it does not carry the same made from runs.json. The kind is on the
        interviewer's entry, which has none for an interview."""
        if run in self.interviews:
            return self.interviews[run]
        host = next(e for e in self.runs if e["role"] == "interviewer" and e.get("interview") == run)
        return {"p": next(e for e in self.runs if e["run"] == run), "i": host,
                "kind": host.get("kind") or "interview", "own": True}

    def guide_of(self, run: str) -> dict:
        """The guide of a conversation as its persona has it (pl.guide()), by the conversation's kind."""
        pair = self.pair(run)
        return pl.guide(self.cfg, pair["p"]["persona"], pair["kind"])

    def runners_of(self, item: tuple) -> set[str]:
        """The runners a queue item needs: its entry's, and for an item of a conversation the
        runner of each side, since neither side goes on without the other."""
        e, kind = item
        if kind != "interview" and kind not in pl.TURN_KINDS:
            return {e["runner"]}
        pair = self.pair(pl.interview_of(e))
        return {pair["p"]["runner"], pair["i"]["runner"]}

    def turn_kind(self, e: dict) -> str:
        """The kind of an attempt that is one turn of entry e: "turn" for an entry of a
        conversation. A finished run that is debriefed is none, and its turns are apart from its
        own attempts (pl.APART_KINDS)."""
        return "turn" if "interview" in e else "debrief"

    def allowed(self, run: str, e: dict) -> tuple[dict, dict]:
        """What a side of a conversation has left for its next turn, and its whole allowance:
        (left(), allowance()) of its entry, which every turn of that side counts against. In
        a debrief each side has limits.debrief, once: the interviewer's entry is asked as any
        entry is (Interview.limits()), and the participant is a finished run, whose own limits
        and usage a debrief leaves alone, so its side is counted against what its debrief
        attempts have used, entry["debrief"] (count_turn())."""
        if self.turn_kind(e) != "debrief":
            return left(self.cfg, e), allowance(self.cfg, e)
        total, used = pl.limits_for(self.cfg, "debrief"), e.get("debrief") or {}
        return {"seconds": total["minutes"] * 60 - (used.get("seconds") or 0),
                "budget_usd": total["budget_usd"] - ((used.get("usage") or {}).get("cost_usd") or 0)}, total

    def again(self, run: str) -> str:
        """The command that takes a conversation up where a line to the lead names one: "run" or
        "resume" for an interview, which launch.py has, and for a debrief the one command that
        holds it and goes on with it."""
        kind = self.pair(run)["kind"]
        return {"run": "run", "resume": "resume"} if kind == "interview" else dict.fromkeys(
            ("run", "resume"), f"interview.py {self.sd} debrief --runs {run}")

    def mark(self, run: str, carried: bool):
        """Write whether a launcher carries a conversation: "carried" on both entries of an
        interview, in one save, and on the interviewer's entry alone in a debrief, whose
        participant is a finished run that stays as it is. This is the one thing runs.json says
        of a conversation as a whole: its state, and the reason for it, are read from its turn
        log (interview.py). It is saved before the conversation's first attempt is recorded, and
        taken off only when no attempt of either side is without an end."""
        for e in self.own(run):
            if carried:
                e["carried"] = True
            else:
                e.pop("carried", None)
        self.save()

    def level(self, run: str):
        """Bring "extended" on a conversation's own entries level with its turn log, which is the
        truth of what "resume --extend" has given each side (pl.extensions()): the number the
        log gives, neither more nor less, so a grant on the log that never reached runs.json
        is applied, and one that did is not applied again. Called whenever a conversation is
        taken up, after its "start" or "resume" record is written and before a turn is queued,
        and before a log is moved out of the way of a fresh start (shelve()). Nothing is saved
        here: mark() saves, and shelve()."""
        given = pl.extensions(pl.read_turns(self.sd, run))
        for e in self.own(run):
            if given[side_of(e)]:
                e["extended"] = given[side_of(e)]
            else:
                e.pop("extended", None)

    def own(self, run: str) -> tuple:
        """The entries that are a conversation's own: both of an interview, and the
        interviewer's alone of a debrief, whose participant is a finished run."""
        pair = self.pair(run)
        return (pair["p"], pair["i"]) if pair["kind"] == "interview" else (pair["i"],)

    def answers(self, run: str) -> int:
        """The answers a conversation has on record: its exchanges."""
        return sum(r["t"] == "answer" for r in pl.read_turns(self.sd, run))

    def take_up(self, e: dict):
        """Begin to carry the conversation whose participant's entry is e, or carry it again: a
        "start" record on a log that has none, a "resume" record on any other, which is what
        clears a "halt", a "lost" record and a count that is used up (interview.fold()). The
        log is written first and runs.json second, as everywhere.

        Two things are settled first. One that "resume --extend" named (extend) and that reads
        limited gives the side its "halt" names one more allowance: the "resume" record says
        which side, and that record is the grant. "extended" on the entries is then brought
        level with the log (level()), in the save that marks the conversation carried, and so
        it is for a grant that an earlier launcher recorded and was killed before it saved. A
        log that begins again says in its "start" record what each side had been given, with
        what this command gives it: the grant of a "resume --extend" that finds the log must
        begin again is in that record, since there is no "resume" record to hold it. And
        one with a side that has replied and cannot be resumed
        (lacking()) starts afresh while it has no answer on record: its log is moved to logs/
        (shelve(), which first brings the entries level with it, so that no grant it holds goes
        with it), and a new one begins. With an answer on record it is taken up as it is, and
        cannot_send() leaves it alone at its first turn: launch() does not queue such a one.
        Nor does a debrief start afresh for want of its participant's session, which is the
        finished run's and the only place it can be held: no_session() leaves that one alone.

        So in every order of events each side's "extended" is the grants it was ever given: the
        old log's are on the entries before that log goes, the new log's "start" record takes
        them from the entries with the one this command gives, and level() then reads the
        entries off the new log. A launcher killed before the "start" record is written gave
        nothing that was announced, and one killed after it has the grant on the log."""
        run = pl.interview_of(e)
        pair = self.interviews[run] = {**self.pair(run), "own": True}
        had, lacks = pl.read_turns(self.sd, run), self.lacking(run)
        halt = interview.fold(had)["halt"] if run in self.extend else None
        side = halt["side"] if halt and halt["state"] == "limited" else None
        if lacks and not self.answers(run) and any(lacks[0] is x for x in self.own(run)):
            kept, had = self.shelve(run), []
            self.restarted.add(run)
            say(f"{run}: {lacks[1]} and no answer is on record, so the {pair['kind']} starts afresh. The turn log "
                f"it had is {kept.relative_to(self.sd)}.")
        at = round(time.time(), 3)
        if had:
            record = {"t": "resume", "at": at, "by": self.by, **({"extended": side} if side else {})}
        else:  # no log, so the entries are all that says what each side was given: shelve() saw to it that they do
            brought = {side_of(x): x["extended"] for x in self.own(run) if x.get("extended")}
            brought.update({side: brought.get(side, 0) + 1} if side else {})
            record = {"t": "start", "at": at, "v": 1, "kind": pair["kind"], "run": run,
                      **({"extended": brought} if brought else {})}
        pl.append_turns(self.sd, run, [record])
        self.level(run)
        if side:
            say(f"{run}: extended, one more allowance of the {side}'s limits. The plan's ceiling no longer holds "
                "for this study.")
        self.mark(run, True)
        answers = sum(r["t"] == "answer" for r in had)
        say(f"{run}: running ({pair['kind']}, " + (f"taken up again after {plural(answers, 'exchange')}" if had else
                                                  f"participant on {pair['p']['runner']}, interviewer on "
                                                  f"{pair['i']['runner']}") + ")")
        self.advance(run)

    def advance(self, run: str):
        """Do what a conversation's log says comes next (interview.next_step()), until that is a
        turn to start, which is queued, or a reason to put it down. A turn goes ahead of
        everything queued that is no turn, so an interview under way is served before another
        is taken up, and behind the turns already queued, so that where the carried interviews
        share a runner with fewer slots than there are of them, each gets its turn in the order
        it fell due and none waits until the others have ended. One side is queued or running
        at any moment, never both: an interview has one process alive."""
        pair, guide = self.interviews[run], self.guide_of(run)
        while True:
            pos = interview.fold(pl.read_turns(self.sd, run))
            step = interview.next_step(pos, guide, time.time())
            if step["do"] == "append":
                pl.append_turns(self.sd, run, [step["record"]])
                continue
            if step["do"] == "stop":
                return self.put_down(run)
            if self.stop.asked:
                return self.put_down(run)
            e = pair["i"] if step["side"] == "interviewer" else pair["p"]
            refusal = self.cannot_send(run, e, step)
            if refusal:
                return self.put_down(run, refusal)
            self.sending[e["run"]] = step
            ahead = next((i for i, (_, kind) in enumerate(self.queue) if kind not in pl.TURN_KINDS), len(self.queue))
            self.queue.insert(ahead, (e, self.turn_kind(e)))
            return

    def cannot_send(self, run: str, e: dict, step: dict) -> str | None:
        """Why the turn a step asks of entry e cannot be started, None when it can: the sentence
        put_down() says. First match first. The side has nothing left of its time or budget: a
        "halt" is appended first, so the log reads limited. A runner of either side starts
        nothing more in this command (shut_out()): blocked when its harness is turning requests
        away, and otherwise put down as the log reads. A side that has replied cannot be
        resumed (lacking()): the conversation starts afresh or is left alone (no_session())."""
        remaining, total = self.allowed(run, e)
        spent = used_up(remaining, total)
        if spent:
            side = side_of(e)
            turns = sum(a["kind"] in pl.TURN_KINDS for a in e.get("attempts") or [])  # a finished run has others
            reason = f"the {side} has {' and '.join(spent)} after {plural(turns, 'turn')}"
            pl.append_turns(self.sd, run, [{"t": "halt", "at": round(time.time(), 3), "state": "limited", "side": side,
                                            "reason": reason,
                                            "limited_by": "time" if remaining["seconds"] <= 0 else "budget"}])
            return reason
        shut = self.shut_out(run, e)
        if shut:
            return shut
        lacks = self.lacking(run)
        return self.no_session(run, *lacks) if lacks else None

    def shut_out(self, run: str, e: dict) -> str | None:
        """Why a conversation starts no further turn once a runner starts nothing more in this
        command (closed), None while the runners of both its sides do. This is the one rule for
        a turn about to be queued (cannot_send()) and for one taken out of the queue (drop(),
        which close() and fill() come through). e is the entry whose turn it would be, and its
        runner is looked at first, then the interviewer's, then the participant's: neither side
        goes on without the other.

        When the runner closed because its harness is turning requests away (turn_away()), a
        "halt" is appended first, so the log reads blocked: it names the side that is on that
        runner, which need not be the side that was about to speak, with what the harness said
        and when it said its limit lifts. A runner that closed for any other reason (its CLI
        could not be started, or cannot do a run from this shell) leaves the log as it is:
        nothing turned the conversation away, and "resume" goes on with it."""
        pair = self.pair(run)
        shut = next((x for x in (e, pair["i"], pair["p"]) if x["runner"] in self.closed), None)
        if not shut:
            return None
        side, name = side_of(shut), shut["runner"]
        if name not in self.turned_away:
            return f"{name} starts nothing more in this command, and the {side} is on it"
        away = self.turned_away[name]
        reason = (f"the {side}'s harness is turning requests away ({name}"
                  + (f": {away['said']}" if away["said"] else "") + ")")
        pl.append_turns(self.sd, run, [{"t": "halt", "at": round(time.time(), 3), "state": "blocked", "side": side,
                                        "reason": reason, **({"reset_at": away["lifts"]} if away["lifts"] else {})}])
        return reason

    def lacking(self, run: str) -> tuple[dict, str] | None:
        """The side of a conversation that cannot be resumed, as (its entry, why), None when
        both can: its session was purged, is gone from its harness, was not kept by it or was
        never recorded, or its runner cannot resume one (session_gone()). Only a side with a
        reply on record is asked: one with none is launched anew whatever became of an earlier
        session of it. Both sides are asked whichever speaks next, so a conversation that
        cannot go on is found before another turn is spent on it."""
        pair, spoke = self.pair(run), interview.fold(pl.read_turns(self.sd, run))["spoke"]
        for e in (pair["p"], pair["i"]):
            why = spoke[side_of(e)] and session_gone(e, self.runner(e["runner"]), f"the {side_of(e)}'s")
            if why:
                return e, why
        return None

    def no_session(self, run: str, e: dict, why: str) -> str:
        """What becomes of a conversation whose entry e cannot be resumed (lacking()), as the
        sentence put_down() says. With an answer on record it is left for the lead to decide,
        as a run with sections written is (cannot_continue()): nothing of it is moved, and the
        command exits with 1. With none it starts afresh, since nothing would be lost: at once
        when this command goes on with it, by queueing it to be taken up again (take_up()), and
        otherwise by the next "resume". A command starts a conversation afresh once: a harness
        that keeps no session would lose the next one too."""
        answers, pair, next_ = self.answers(run), self.interviews.get(run), self.again(run)
        if not any(e is x for x in self.own(run)):  # the finished run of a debrief: there is no one else to ask
            self.left_alone = True
            return (f"{why}, so the run cannot be debriefed: a debrief is held in the session the run worked in. "
                    "Left alone" + (f", with {plural(answers, 'answer')} on record" if answers else ""))
        if answers:
            self.left_alone = True
            return (f"{why}, so it cannot be continued. Left alone, with {plural(answers, 'answer')} on record. To "
                    f"hold it again from the start, move {pl.INTERVIEWS}/{run}.jsonl into logs/ and use "
                    f"{next_['run']}")
        again = run in self.restarted
        if (pair and pair["own"] and not again and not self.stop.asked
                and not self.runners_of((e, "interview")) & self.closed.keys()):
            self.queue.insert(0, (pair["p"], "interview"))
            return why
        return (f"{why} and no answer is on record"
                + (f", though this command had started the {self.pair(run)['kind']} afresh" if again else "")
                + f". Next: {next_['resume']}, which starts it afresh")

    def shelve(self, run: str) -> Path:
        """Move a conversation's turn log out of the way of a fresh start, and return where it is
        now: logs/<run id>.interview-<k>.jsonl, k counting from 1. Its two transcripts, when
        "interview.py render" had written them, go beside it as .md and .analysts.md, first, so
        that none is left to be read as the new interview's. Nothing is deleted: a turn log is
        the only record of what was said. Each entry of the conversation loses "session", so
        its side is launched anew, and keeps its attempts, the usage its sessions reported and
        the time it has used: a fresh start gives no new allowance, and takes none away that
        "resume --extend" gave. Those are counted on the log that is about to go
        (pl.extensions()), and "extended" on an entry is only a copy, which a launcher that was
        killed after it recorded a grant never brought level. So the entries are brought level
        with the log and saved first (level()): once the log is moved they are the only record
        of the grants, and the new log's "start" record is written from them (take_up()). The
        log then goes before runs.json loses the sessions, as everywhere: a launcher killed
        between the two leaves a conversation that reads pending, which "run" starts."""
        self.level(run)
        self.save()
        logs, k = self.sd / "logs", 1
        moved = ((self.sd / pl.INTERVIEWS / f"{run}.md", ".md"),
                 (self.sd / pl.TRANSCRIPTS / f"{run}.md", ".analysts.md"), (pl.turn_log(self.sd, run), ".jsonl"))
        while any((logs / f"{run}.interview-{k}{ext}").exists() for _, ext in moved):
            k += 1
        logs.mkdir(exist_ok=True)
        for was, ext in moved:
            if was.exists():
                os.replace(was, logs / f"{run}.interview-{k}{ext}")
        for e in self.own(run):
            e.pop("session", None)
        self.save()
        return logs / f"{run}.interview-{k}.jsonl"

    def put_down(self, run: str, why: str | None = None):
        """Stop carrying a conversation, which has no process alive: "carried" comes off, its
        transcripts are written when its log has an "end", and one line says the state the log
        reads as and why: the reason the caller gives, else the one the log holds
        (interview.standing()), else that a stop was asked, which is no reason for one that
        is done. Nothing is appended here and no state is written: whatever stops it for good
        is on the log before this is called.

        A debrief is said to be one, since its run id is a finished run's, and one that reads
        limited has its transcripts written too: a side has used limits.debrief, which is its
        whole allowance, so the debrief is at its end.

        The usage record is written again, since this is where an interview stops reading
        running with no process ending: the record a turn's end wrote (turn_over()) still has
        it so, and for an interview that ends at its cap the "end" is appended after that."""
        debrief = self.pair(run)["kind"] == "debrief"
        self.interviews.pop(run, None)
        self.mark(run, False)
        records = pl.read_turns(self.sd, run)
        state = pl.interview_state(records, False)
        if state == "done" or (debrief and state == "limited"):
            interview.write_transcripts(self.cfg, run)
        record_usage(self.cfg, self.runs)
        why = (why or interview.standing(records, self.guide_of(run))["reason"]
               or ("stopped by the stop command" if self.stop.asked and state != "done" else None))
        say(f"{run}: {'debrief ' if debrief else ''}{state} after "
            f"{plural(sum(r['t'] == 'answer' for r in records), 'exchange')}" + (f": {why}" if why else ""))

    def drop(self, match) -> list[tuple]:
        """Take out of the queue every item that match(item) is true of, without starting it,
        and return them. This is the only code that does: close(), hold(), fill() and a request
        to stop come through it, so a carried conversation can never lose its queued turn
        unnoticed. One that does is put down, for the reason shut_out() gives when a runner of
        either side starts nothing more: blocked, with a "halt" on its log, when that runner's
        harness is turning requests away, and as its log reads otherwise. A request to stop
        leaves the log as it is too. An interview that was waiting to be taken up was not
        carried: it keeps its state, as a queued run does."""
        gone = [item for item in self.queue if match(item)]
        self.queue = [item for item in self.queue if not any(item is taken for taken in gone)]
        for e, kind in gone:
            if kind not in pl.TURN_KINDS:
                continue
            self.sending.pop(e["run"], None)
            run = pl.interview_of(e)
            self.put_down(run, self.shut_out(run, e))
        return gone

    def sweep(self):
        """Put down every conversation this command carries that has neither a queued turn nor a
        process: what is left of one whose turn could not be started (a command its runner
        cannot build, a process the system refused) or was taken back when it ended."""
        busy = {pl.interview_of(e) for e, kind in self.queue if kind in pl.TURN_KINDS}
        busy |= {pl.interview_of(c.entry) for c in self.children if pl.open_attempt(c.entry)}
        for run in [run for run in self.interviews if run not in busy]:
            self.put_down(run)

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
                    say(f"{named(child.entry)}: stopping")
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
        attempt that ended under an earlier launcher: its run is classified and nothing more.

        One turn of a conversation shares the head of this with every attempt: what a killed
        watchdog left, a process that was never executed, the runner's reading of the output, a
        session that is gone, a CLI that never ran, and the usage. From there it is turn_over()'s:
        a turn decides no state, and its reply goes to the turn log."""
        e, role, runner = child.entry, role_of(child.entry), self.runner(child.entry["runner"])
        attempt, code, why = e["attempts"][-1], record.get("exit_code"), record.get("stopped")
        if record.get("leftover"):
            say(f"{named(e)}: its watchdog was killed, and {leftover(record['leftover'])}")
        if record.get("unchecked"):
            say(f"{named(e)}: its watchdog was killed, and {unchecked(record['unchecked'])}")
        if record.get("elsewhere"):
            say(f"{named(e)}: its watchdog was killed, and {unlooked(record['elsewhere'])}")
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
        if res["session_lost"] and (attempt["kind"] in ("resume", "followup") or self.resumes(e, attempt)):
            self.session_lost(e, settling)
            return
        if code and code > 0 and not why and not wrote.strip() and res["session_id"] is None:
            # It exited with an error before printing a line: the CLI never ran, as in a sandbox
            # that lets it start and then refuses what it needs. Not an attempt, and not a failure.
            self.unstarted(e, record["argv"], f"Its CLI exited with code {code} before printing anything",
                           res["message"].strip() or "no message", settling)
            return
        session = res["session_id"] or e.get("session")
        # The run's own usage, before a process that leaves it alone is counted: a follow-up, a turn of a debrief.
        own = usage_of(e) if attempt["kind"] in pl.APART_KINDS else {}
        before = {}  # what the session had reported before this process
        if session or any(res["usage"].get(f) is not None for f in runners.USAGE_FIELDS):
            sessions, key = e.setdefault("sessions", {}), session or f"attempt {attempt['n']}"
            before = sessions.get(key) or {}
            sessions[key] = runners.merge_usage(before, res["usage"])
        if attempt["kind"] in pl.TURN_KINDS:
            self.turn_over(e, record, {**res, "cannot_run": cause}, session, left_browser, settling, before, own)
            return
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
            used, lump = self.used_by(e, attempt, res, session, before, own)
            attempt.pop("unallocated", None)
            if lump:
                attempt["unallocated"] = lump
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
        attempt["state"] = state
        self.close_attempt(e, record, res, session, left_browser)
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
            self.turn_away(e["runner"], res["reset_at"], said)
        elif shut:
            self.close(e["runner"], NO_RUN_HERE, "in this command", pl.SANDBOX_HINT)
        elif retry:
            self.retried.add(e["run"])
            self.queue.insert(0, (e, "retry"))

    def used_by(self, e: dict, attempt: dict, res: dict, session: str | None, before: dict,
                own: dict) -> tuple[dict, dict | None]:
        """What the process of an attempt that leaves its run alone used, a follow-up or a turn of
        a debrief (pl.APART_KINDS): (usage, unallocated). before is what its session had
        reported before this process, and own the run's own usage then.

        The usage is what the session has reported now, less what it had before. A total that
        also brings the spend of an earlier process of the run itself, stopped before it
        reported any, cannot be told apart from it. It is then neither this attempt's nor the
        run's: the usage has no tokens or cost, and they are returned as "unallocated"
        (panel_lib.py), with the figures the run had reported none of, so the run's own usage
        reads as it did before."""
        owed = res["usage"].get("scope") == "session" and any(
            a.get("session") == session and a.get("usage_reported") is False and a["kind"] not in pl.APART_KINDS
            for a in e["attempts"][:-1])
        now = (e.get("sessions") or {}).get(session or f"attempt {attempt['n']}") or {}
        used = {f: None if res["usage"].get(f) is None
                else res["usage"][f] if f == "duration_s" else max(0, round(now[f] - (before.get(f) or 0), 9))
                for f in runners.USAGE_FIELDS}
        spent = [f for f in runners.USAGE_FIELDS if f != "duration_s"]
        if not (owed and any(used[f] is not None for f in spent)):
            return used, None
        lump = {**{f: used[f] for f in spent}, "run_unreported": [f for f in runners.USAGE_FIELDS if own[f] is None]}
        return {**used, **dict.fromkeys(spent)}, lump

    def count_turn(self, e: dict, used: dict, lump: dict | None):
        """Add a settled turn of a debrief to what the debrief has used of its finished run,
        entry["debrief"] (panel_lib.py, "Debriefs"): the turns that have ended and their seconds,
        counted over the entry's debrief attempts, and the usage, which those attempts no
        longer hold once they are cut down, summed here. It is what the participant's side of
        limits.debrief is counted against (allowed()), and what the run's own usage leaves out
        (planning.usage_of()). Nothing is saved here: turn_over() saves it with the attempt's
        end, so a launcher killed before that leaves neither."""
        turns = [a for a in e["attempts"] if a["kind"] == "debrief" and a.get("ended") is not None]
        had = e.get("debrief") or {}
        shared = [u for u in (had.get("unallocated"), lump) if u]
        lumped = {f: v for f, v in runners.total_usage(shared).items() if f != "duration_s"}
        e["debrief"] = {"turns": len(turns), "seconds": round(sum(a["seconds"] or 0 for a in turns), 3),
                        "usage": runners.total_usage([had.get("usage") or {}, used]),
                        **({"unallocated": {**lumped, "run_unreported": sorted({f for u in shared
                                                                               for f in u["run_unreported"]})}}
                           if shared else {})}

    def close_attempt(self, e: dict, record: dict, res: dict, session: str | None, left_browser: dict | None):
        """Put the end of an entry's last attempt on the attempt, while it is whole, and on the
        entry: when it ended and how long it ran, its exit code, outcome and session, what a
        killed watchdog or a browser session left, and whether its usage is on record. A total
        for the session marks the earlier attempts of that session reported, and a process
        that was stopped before it reported any is marked as not having. The entry has no
        process from here on, and its time used is the sum over its own attempts: the ones that
        leave its limits alone (pl.APART_KINDS) are not in it. Nothing is saved here."""
        attempt = e["attempts"][-1]
        stopped = bool(record.get("stopped") or record.get("killed"))  # the CLI did not end by itself
        spend = any(res["usage"].get(f) is not None for f in runners.USAGE_FIELDS if f != "duration_s")
        attempt.pop("was", None)
        (attempt.get("steps") or {}).pop("seen", None)  # the backstop's place in the step log: no use from here on
        attempt.update(ended=round(record["ended"], 3),
                       seconds=round(max(0.0, record["ended"] - attempt["started"]), 3),
                       exit_code=record.get("exit_code"), outcome=res["outcome"], session=session)
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
            sum(a["seconds"] or 0 for a in e["attempts"] if a["kind"] not in pl.APART_KINDS), 3))

    # ---- when a turn of a conversation ends

    def resumes(self, e: dict, attempt: dict) -> bool:
        """Whether an attempt in flight is a turn that resumes its side's session. The attempt
        does not say: the turn log has not moved since it was started, so the step it carries
        out is the one the log gives now (interview.next_step())."""
        if attempt["kind"] not in pl.TURN_KINDS:
            return False
        run = pl.interview_of(e)
        step = interview.next_step(interview.fold(pl.read_turns(self.sd, run)), self.guide_of(run), time.time())
        return step.get("how") == "resume"

    def logged(self, e: dict, attempt: dict) -> list[dict]:
        """The records a turn log has of one attempt of a side: none until its end is settled.

        A record that pl.read_turns() set aside as malformed ("unread") is one of them when the
        object its line held names this side and attempt, and is given as it was set aside. The
        attempt is then on the log, so nothing is added for it again (turn_ended()). That is
        all its side and attempt are read for: what the record says is still read by nothing,
        so it is no reply the log has (turn_over())."""
        side, records = side_of(e), pl.read_turns(self.sd, pl.interview_of(e))

        def of_it(r: dict) -> bool:
            held = r.get("record", r) if r["t"] == "unread" else r
            return held.get("side") == side and held.get("attempt") == attempt["n"]

        return [r for r in records if of_it(r)]

    def turn_over(self, e: dict, record: dict, res: dict, session: str | None, left_browser: dict | None,
                  settling: bool, before: dict | None = None, own: dict | None = None):
        """Settle a turn that ran as the CLI, in the one order that a launcher killed at any
        point leaves for the next to finish: what the reply comes to on the turn log first, in
        one synced write (turn_ended()); then the attempt's end, whole; then the attempt cut
        down to {"n", "kind", "ended", "seconds"} when its reply is on the log, which has the
        rest; then one save. So the log is never behind runs.json, and an attempt that is still
        open with its record already on the log is settled without a second record, whether
        that record can be read or was set aside as malformed (logged()). An attempt that left
        no reply stays whole, as evidence, and so does one whose record cannot be read, which
        is no reply the log has. Then the usage record, the runner closed when its harness
        turned the request away or showed that no run of it can work here, and what the
        conversation does next (carry_on()).

        A turn of a debrief put to a finished run has three things more, each in the place
        that order gives it. First of all, before the log, the persona file and a usability
        run's evidence folder are put back when the turn changed them (after_debrief_turn()).
        What the turn used goes on the entry's "debrief" with the attempt's end, in the one save
        (count_turn(); before is what its session had reported before this process and own the
        run's usage then, as ended() kept them). And the copies made before the turn go last,
        after that save (drop_copies()). The run's own state, reason, time used and usage are
        never written."""
        attempt, run = e["attempts"][-1], pl.interview_of(e)
        n, spoken = attempt["n"], attempt["kind"] == "debrief"  # a turn put to a finished run
        self.after_debrief_turn(e, attempt)
        appended = self.turn_ended(e, attempt, res, record, record.get("stopped"))
        used = self.used_by(e, attempt, res, session, before or {}, own or {}) if spoken else None
        self.close_attempt(e, record, res, session, left_browser)
        if spoken:
            self.count_turn(e, *used)
        logged = self.logged(e, attempt)
        spoke = interview.fold(pl.read_turns(self.sd, run))["spoke"][side_of(e)]
        # A session its harness did not keep cannot be resumed. A side with no reply on record is launched afresh
        # whatever became of its session, so nothing is noted for it.
        unsaved = res["session_saved"] is False and bool(session) and spoke
        if unsaved:
            e.setdefault("unsaved", {})[session] = round(time.time())
        replied = any(r["t"] not in ("lost", "unread") for r in logged)
        if replied:
            kept = {k: attempt[k] for k in ("n", "kind", "ended", "seconds")}
            attempt.clear()
            attempt.update(kept)
        self.save()
        if spoken:  # runs.json has the attempt's end, so readers read the file again: the copies can go
            self.drop_copies(e, n)
        self.snapshot([*(c.entry["run"] for c in self.children), e["run"]])
        record_usage(self.cfg, self.runs)
        for line in filter(None, map(interview.remark, appended)):
            say(f"{run}: {line}")
        if unsaved:
            say(f"{run}: the {side_of(e)}'s session was not saved by {e['runner']}, so its next turn cannot resume it.")
        if res["outcome"] == "usage_limit" and not settling:
            self.turn_away(e["runner"], res["reset_at"], res["message"].strip())
        elif res["cannot_run"] and not replied and not settling:
            self.close(e["runner"], NO_RUN_HERE, "in this command", pl.SANDBOX_HINT)
        self.carry_on(run, appended, res, settling)

    def turn_ended(self, e: dict, attempt: dict, res: dict, record: dict, why: str | None) -> list[dict]:
        """Add to the turn log what an ended turn comes to, and return the records added: none
        when the log has a record of this side and attempt already, in any form (logged()),
        from a launcher that was killed between the log and runs.json. interview.taken() decides
        the records. This says only how the process ended: by the stop command; at the limit
        its watchdog was given, which was limits.turn or the last of its side's allowance
        ("bound"); as its harness reported it; or with its watchdog killed, the end record then
        being made up (outcome()). A process that finished its turn left a reply, whatever its
        exit code.

        A turn that used the last of its side's time or budget is said with the side's whole
        allowance, in used_up()'s words: "none of its $2 left". What a harness says of a budget
        names the cap that one process was given, which is the slice that was left for it, and
        reads as an allowance nobody set. Its words stay in the attempt's output in logs/."""
        if self.logged(e, attempt):
            return []
        run = pl.interview_of(e)
        ending = ("stop" if why == "stop" else
                  ("time" if attempt.get("bound") == "turn" else "limit") if why == "time" else
                  res["outcome"] if res["outcome"] in ("budget", "usage_limit") else
                  "killed" if record.get("lost") else None if res["outcome"] == "ok" else "error")
        said = (res["cannot_run"] or res["message"].strip()) if ending in ("usage_limit", "error") else ""
        if ending in ("limit", "budget"):  # what the side has none left of, whatever its figures say by now
            none = {"seconds": 0.0 if ending == "limit" else 1.0, "budget_usd": 0.0 if ending == "budget" else 1.0}
            said = used_up(none, self.allowed(run, e)[1])[0]
        result = {"reply": res["reply"] if ending is None else None, "ending": ending, "reason": said or None,
                  "reset_at": res["reset_at"] if ending == "usage_limit" else None,
                  "seconds": round(max(0.0, record["ended"] - attempt["started"]), 3)}
        added = interview.taken(interview.fold(pl.read_turns(self.sd, run)), self.guide_of(run), side_of(e),
                                attempt["n"], result, self.cfg["leak_terms"], time.time())
        pl.append_turns(self.sd, run, added)
        return added

    def carry_on(self, run: str, appended: list[dict], res: dict, settling: bool):
        """What a conversation does once a turn of it is settled. A turn that ended under an
        earlier launcher is settled and no more: reconcile() puts its conversation down. One
        this command does not go on with, or any once a stop was asked, is put down. Otherwise
        the log decides (advance()), and nothing is put again unasked: after a turn that left
        no reply it stops there, but for an empty answer, which is put once more.

        The one exception is run's and pilot's, as for a run that failed: a side's first process
        that left no usable reply (a "halt" with the state failed) is launched afresh once for
        an interview in a command, whichever side it was, unless its runner starts nothing more
        or its CLI showed that no run of it can work here. The "resume" record is what lets the
        log go on."""
        pair = self.interviews.get(run)
        if settling or not pair:
            return
        if not pair["own"] or self.stop.asked:
            return self.put_down(run)
        last = appended[-1] if appended else {}
        failed = last if (last.get("t"), last.get("state")) == ("halt", "failed") else None
        side = pair["i"] if failed and failed["side"] == "interviewer" else pair["p"]
        if (failed and self.retry and run not in self.retried and side["runner"] not in self.closed
                and not res["cannot_run"]):
            self.retried.add(run)
            pl.append_turns(self.sd, run, [{"t": "resume", "at": round(time.time(), 3), "by": self.by}])
            say(f"{run}: failed: {failed['reason']}; launching the {failed['side']} afresh, once")
        self.advance(run)

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
        """Run until nothing is queued and no process is alive. While a conversation is carried
        the launcher looks every interview.TURN_POLL seconds at most: each of its turns waits for
        that look, and at a second a look an interview of sixty turns would wait a minute in all.
        After everything that can take a turn out of the queue or a process out of the children,
        a carried conversation left with neither is put down (sweep()). On a request to stop,
        whatever is queued goes through drop(), which puts down the conversations that were
        waiting for a slot: one with a process alive is put down when that process ends."""
        while self.queue or self.children:
            if self.stop.asked and self.queue:
                waiting = [e for e, kind in self.drop(lambda item: True) if kind not in pl.TURN_KINDS]
                if waiting:
                    say(f"Stopping: {plural(len(waiting), 'queued run')} "
                        f"{agree(len(waiting), 'stays as it is', 'stay as they are')}.")
            self.fill()
            self.sweep()
            if self.children:
                time.sleep(min(self.poll, interview.TURN_POLL) if self.interviews else self.poll)
                self.watch()
                self.sweep()


# ---------------------------------------------------------------- commands

def select(runs: list[dict], role: str, ids: list[str] | None) -> list[dict]:
    """The runs a command is about: every run of the role, or the ones --runs names. In an
    interview study the panellist runs are the participants' entries, one for each interview."""
    pool = [e for e in runs if e["role"] == role]
    noun = role_of(pool[0]).noun if pool else ROLES[role].noun
    what = noun if noun == Interview.noun else f"{role} {noun}"  # an interview is named by itself, not by a side
    if not pool:
        raise SystemExit(f"This study has no {what}s in runs.json." + (
            f' "run --role {role}" plans and starts them.' if ROLES[role] is Synthesis else ""))
    if ids is None:
        return pool
    known(what, ids, [e["run"] for e in pool])
    return [e for e in pool if e["run"] in ids]


def known(what: str, ids: list[str], names: list[str]):
    """Refuse, by exiting, the ids of --runs that are none of names: what a command is asked to
    start is checked before it does anything."""
    unknown = [i for i in ids if i not in names]
    if unknown:
        raise SystemExit(f"No {what} called {', '.join(unknown)}. There {agree(len(names), 'is', 'are')}: "
                         f"{', '.join(names)}")


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


def debriefs_note(cfg: dict, brief_name: str, runs: set[str], absolute: bool = False) -> str:
    """What a brief tells its reader about the debriefs held with runs, assets/<brief>-debriefs.md
    with their transcripts listed: nothing when none of them has an answer on record, so the
    placeholder's line goes. It opens with an empty line, to stand as a paragraph.

    What is named is the analysts' copy of each transcript, analysis/transcripts/<run id>.md:
    the questions and the answers, with nothing of the interviewer's notes. Both transcripts
    are written again first, so a debrief that did not reach its end has them too, and is said
    to be unfinished. absolute: the paths as an analyst's brief gives every path, where the
    writer's are relative to the study directory. No script tallies a debrief: the asset says
    that it is product feedback, and how an answer is cited."""
    sd, listed = cfg["_dir"], []
    entries = pl.read_runs(sd) if (sd / "runs.json").exists() else []
    for host in (e for e in entries if e.get("kind") == "debrief" and e.get("interview") in runs):
        run = host["interview"]
        records = pl.read_turns(sd, run)
        answers = sum(r["t"] == "answer" for r in records)
        if not answers:
            continue
        if "debrief" in cfg:  # the guide is what a transcript names a topic's area from
            interview.write_transcripts(cfg, run)
        copy = Path(pl.TRANSCRIPTS) / f"{run}.md"
        if (sd / copy).is_file():
            listed.append(f"- `{sd / copy if absolute else copy}` ({run}): {plural(answers, 'exchange')}"
                          + ("" if any(r["t"] == "end" for r in records) else ", and the debrief did not finish"))
    if not listed:
        return ""
    return "\n" + pl.fill_brief(f"{brief_name}-debriefs.md", {"TRANSCRIPTS": "\n".join(listed)}).strip()


def unfinished_debriefs(cfg: dict, runs: list[dict]) -> dict[str, str]:
    """The debriefs on record that "interview.py debrief" would still go on with: {run id: the
    state its debrief reads as}, one of DEBRIEF_NEXT. None of them holds a job back, as a turn
    still out does (unsettled_debriefs()): the analysts and the writer are given what there is
    of each, and the lead is told so before they start (plan_jobs())."""
    states = {e["interview"]: state_of(cfg, e) for e in runs
              if e.get("kind") == "debrief" and e["role"] == "interviewer"}
    return {run: state for run, state in states.items() if state in DEBRIEF_NEXT}


def unsettled_debriefs(runs: list[dict]) -> list[str]:
    """The runs with a turn of a debrief that is not settled: an attempt of either side of it has
    no end in runs.json. Its process may still be answering, and a finished run's persona file
    may hold what the launcher will put back."""
    return list(dict.fromkeys(pl.interview_of(e) for e in runs
                              if (e.get("kind") == "debrief" or "interview" not in e)
                              and (pl.open_attempt(e) or {}).get("kind") in pl.TURN_KINDS))


def brief(cfg: dict, job: dict, records: list[dict], files: dict) -> str:
    """A job's prompt: its brief from assets/ with every placeholder filled. records is
    pl.run_records(), and files maps a run id to its persona file. An interview study's four
    briefs are interview.brief()'s: what each job of one is given and kept from is a rule of
    the interview, and is written there."""
    sd, syn, keys = cfg["_dir"], cfg["synthesis"], pl.model_keys(cfg)
    usability = cfg["type"] == "usability"  # its briefs are assets of their own, with the same placeholders
    qual, synthesis = ("usability-qual-brief", "usability-synthesis-brief") if usability else (
        "qual-brief", "synthesis-brief")
    done = sum(r["state"] == "done" for r in records)
    context = syn.get("context_files", [])
    missing = [f for f in context if not (sd / f).is_file()]
    if missing:
        raise SystemExit(f"synthesis.context_files: no such file in {sd}: {', '.join(missing)}")
    if cfg["type"] == "interview":
        return interview.brief(cfg, job, records)
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
            "FOLLOWUPS": followups_note(cfg, synthesis, {r["run"] for r in records}),
            "DEBRIEFS": debriefs_note(cfg, synthesis, {r["run"] for r in records})})

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
        "DEBRIEFS": debriefs_note(cfg, qual, {r["run"] for r in own}, absolute=True),
        "OUTPUT_FILE": Path(job["file"]).name})


def unsettled_followups(study_dir: Path, runs: list[dict]) -> list[str]:
    """The runs with a follow-up question that is not settled: an attempt of theirs is in flight,
    or their record in followups.json has no outcome yet or a decision still to carry out."""
    out = [e["run"] for e in runs if asking(e)]
    out += [r["run"] for f in pl.read_followups(study_dir) if f.get("mode") != "native"
            for r in f.get("runs") or [] if r.get("outcome") is None or r.get("settling")]
    return list(dict.fromkeys(out))


# What each job role waits for, the one table of it: the panel (no run or interview pending, running or
# blocked, unless --allow-incomplete), the job roles whose every job must be done, which are the roles whose
# files it is written from (pl.JOB_READS), and a file that a script writes from those jobs' output, with the
# script. Only the roles a study has are asked for (pl.job_roles()), and only an interview study is held to
# the file: the writer of a review or usability study is told when a file its brief names is missing, and
# starts. In an interview study the file must also be what its script would write now (no_longer()), and
# every job read must still be good (interview.rerun(), interview.altered()).
WAITS = {"analyst": (True, (), None),
         "critic": (True, (), None),
         "themes": (False, pl.JOB_READS["themes"], ("analysis/notes.csv", "extract_notes.py")),
         "writer": (False, pl.JOB_READS["writer"], ("analysis/quant.md", "analyze.py"))}
CALLED = {"analyst": "analysts", "critic": "critics", "themes": "themes job", "writer": "writer"}  # the jobs of a role


def waiting(role: str) -> str:
    """The jobs of a role and their verb, for a sentence on what they wait for: "analysts wait",
    "themes job waits"."""
    return f"{CALLED[role]} wait{'' if CALLED[role].endswith('s') else 's'}"


def no_longer(cfg: dict, role: str, records: list[dict]) -> str | None:
    """Why the file that the jobs of a role read from a script (WAITS) no longer stands, in one
    sentence that names the script to run again, None when it is what that script would write
    now. Asked of an interview study, of a file that is there. Nothing records when a script
    ran and no file's time is compared: each script is asked what it would write now.

        themes   analysis/notes.csv against what the analysts' files give now
                 (extract_notes.changed()). The themes job reads nothing of critique.csv
        writer   analysis/quant.json against the report made again (analyze.stale_tallies()),
                 as analyze.py will read the study once this command has let it go: with no
                 launcher holding it

    The two modules are loaded here, so that no study of another type loads them."""
    if role == "themes":
        import extract_notes
        return extract_notes.changed(cfg, records, ("qual",))
    if role == "writer":
        import analyze
        return analyze.stale_tallies(cfg)
    return None


def plan_jobs(cfg: dict, runs: list[dict], role: str, command: str, allow_incomplete: bool,
              ids: list[str] | None = None) -> tuple[set[str], dict[str, dict]]:
    """What comes before any job of the synthesis starts. Refuses, by exiting, a name in ids
    (the jobs --runs names, None for every job of the role) that is no job study.json plans
    for the role, before anything is planned or written, a role with no
    model entry and a job whose inputs are not ready (WAITS): any while a follow-up question is
    not settled, analysts and critics while panellist runs or interviews are pending, running
    or blocked (unless allow_incomplete), the themes job until every analyst job is done, the
    writer until every job of every role before it is, and in an interview study the themes job
    and the writer until the script that writes the file they read has run. There a job that
    is done is not enough: a job that reads one which was built on files since written anew
    (interview.rerun()) or since changed with no job run again (interview.altered()) is refused
    with what puts that job right, and so is one whose script would now write another file than
    the one that is there (no_longer()). So after an analyst is run again, or a note is put
    right by hand, nothing goes on from the old notes, themes or tallies.
    Then, for the run command, brings the role's job entries in runs and their prompts in line
    with study.json: a new job is added, and one that is pending or failed is planned afresh.
    In an interview study both transcripts of every interview with a turn on record are written
    first for the analysts and the critics (interview.write_transcripts()), so an interview
    that never ended has the copy its brief names.

    An analyst or a critic of an interview study none of whose interviews has a turn on record
    has nothing to read (interview.nothing_to_read()), and is not planned. Of the jobs the
    command is about, such a job refuses the command, as it always did. With allow_incomplete
    it is passed over with a line while the others run, so that part of a panel (a pilot, one
    persona's interviews) can be analysed and critiqued, and the command is refused only when
    none of its jobs has anything to read. A job --runs does not name is not judged.

    A debrief that is not finished, with no turn of it out, holds no job back: one line names
    each and the command that goes on with it, before the jobs it is said of are started.

    Returns the ids of the jobs with nothing to read, of which the caller starts none, and for
    each job of an interview study whose brief was written the fingerprints of the files that
    brief gives it to read (interview.given(): of a themes job and a writer), taken as the
    brief is written. The caller hands them to the supervisor, which records them in the
    attempt that launches the job, in the one save that puts the attempt on record."""
    sd, planned, talk = cfg["_dir"], pl.synthesis_jobs(cfg), cfg["type"] == "interview"
    wanted = [j for j in planned if j["role"] == role]
    if command == "run" and ids is not None:  # "resume" plans nothing, and select() asks it of runs.json
        known(f"{role} {Synthesis.noun}", ids, [j["run"] for j in wanted])
    key = pl.job_entry(role)
    if key not in cfg["synthesis"] or wanted[0]["runner"] is None:
        whose = f"the {role}" if key == role else f"the {CALLED[role]}, which runs on synthesis.{key}"
        raise SystemExit(
            f'study.json names no runner for {whose}. Add "synthesis": {{"{key}": {{"runner": "<runner>", '
            f'"model": "<model>"}}}}: there is no default, and "model" may be left out for the runner\'s own.')
    runners.get(wanted[0]["runner"])
    out = unsettled_followups(sd, runs)
    if out:
        files = agree(len(out), "its persona file", "their persona files")
        raise SystemExit(
            f"The {waiting(role)} for the follow-up questions: the one put "
            f"to {planning.listed(out)} is not settled, so {files} may still be put back as before the question. "
            f"Wait for the follow-up to finish, or settle one that was cut short with: followup.py {sd} list")
    out = unsettled_debriefs(runs)
    if out:  # a launcher that is gone left it running: this command adopted it, and it ends within limits.turn
        raise SystemExit(
            f"The {waiting(role)} for the debrief of {planning.listed(out)}: a turn of it is still running, and its "
            f"answer is not on record yet. Wait for it to end, or stop it with launch.py {sd} stop. Then interview.py "
            f"{sd} debrief --runs {','.join(out)} goes on with the debrief, or run this again to analyse what "
            "there is.")
    records = pl.run_records(sd, cfg, held(cfg))
    panel, before, script = WAITS[role]
    before = [r for r in before if r in pl.job_roles(cfg)]
    if panel:
        waiting_for = [r for r in records if r["state"] in ("pending", "running", "blocked")]
        if waiting_for and not allow_incomplete:
            unit = "interview" if talk else "panellist run"
            then = ("analyse what there is: the analysts are then told which runs are incomplete." if not talk else
                    "analyse what there is: the analysts are then told which interviews are unfinished."
                    if role == "analyst" else
                    "critique what there is: a transcript says where an unfinished interview stopped.")
            raise SystemExit(
                f"{CALLED[role].capitalize()} wait for the panel: {plural(len(waiting_for), unit)} of {len(records)} "
                f"{agree(len(waiting_for), 'has', 'have')} not finished ("
                + ", ".join(f"{r['run']} {r['state']}" for r in waiting_for) + "). Finish them with launch.py run and "
                f"resume, or pass --allow-incomplete to {then}")
    if before:
        recorded_jobs = {e["run"]: e for e in runs}
        states = {j["run"]: state_of(cfg, recorded_jobs.get(j["run"], j)) for j in planned if j["role"] in before}
        if set(states.values()) != {"done"}:
            # The roles with a job that is not done, in the order they run: the first is what to start next.
            first, *later = [r for r in before
                             if any(states[j["run"]] != "done" for j in planned if j["role"] == r)]
            raise SystemExit(
                f"The {waiting(role)} for {planning.listed([f'the {CALLED[r]}' for r in before])}: "
                + ", ".join(f"{k} is {v}" for k, v in states.items())
                + f". Finish them first: launch.py {sd} run --role {first}, or resume --role {first} for one "
                "that is blocked."
                + (f" Then the same with --role {planning.listed(later)}." if later else ""))
    if talk and before:  # every job it reads is done: one of them built on files that were since written anew
        on_record = {e["run"]: e for e in runs}
        stale = next((line for line in (interview.out_of_date_line(cfg, on_record[j["run"]], runs, records)
                                        for j in planned if j["role"] in before and j["run"] in on_record
                                        and (interview.rerun(on_record[j["run"]], runs)
                                             or interview.altered(cfg, on_record[j["run"]]))) if line), None)
        if stale:
            raise SystemExit(f"The {waiting(role)}, because a job it reads is out of date. {stale}")
    if talk and script and not (sd / script[0]).is_file():
        raise SystemExit(
            f"The {waiting(role)} for {script[0]}, which is not there: {script[1]} {sd} writes it. Run that, "
            f"then launch.py {sd} {command} --role {role} again.")
    stale = no_longer(cfg, role, records) if talk and script else None
    if stale:
        raise SystemExit(f"The {waiting(role)}, because {stale[:-1]}, then launch.py {sd} {command} --role {role} "
                         "again.")
    if command != "run":
        return set(), {}
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
    # The analysts and critics of an interview study with no interview to read: none is planned or started.
    unheard = {j["run"]: j for j in wanted
               if talk and j["run"] not in settled and interview.nothing_to_read(cfg, j, records)}
    about = [j["run"] for j in wanted if ids is None or j["run"] in ids]  # the jobs this command is asked to start
    empty = [k for k in about if k in unheard]
    if empty and (not allow_incomplete or len(empty) == len(about)):
        raise SystemExit(interview.nothing_to_read(cfg, unheard[empty[0]], records))
    files = {e["run"]: e["file"] for e in runs if e["role"] == "panellist"}
    if talk and panel and len(settled) < len(wanted):  # the transcripts a brief is about to name
        for r in records:
            interview.write_transcripts(cfg, r["run"])
    prompts = {j["run"]: brief(cfg, j, records, files) for j in wanted if j["run"] not in {*settled, *unheard}}
    # What each of those briefs gives its job to read, as it is now: the supervisor records it on the job's launch.
    given = {j["run"]: interview.given(cfg, j) for j in wanted if talk and j["run"] in prompts}
    for k in empty:
        say(interview.nothing_to_read(cfg, unheard[k], records, passed=True))
    for job in wanted:
        if job["run"] not in prompts:
            continue
        if job["run"] not in current:
            runs.append({})
            current[job["run"]] = runs[-1]
        current[job["run"]].update(job)  # the plan's fields; whatever a launcher recorded stays
        (sd / job["prompt"]).write_text(prompts[job["run"]])
    for stale in set(current) - {j["run"] for j in wanted}:
        runs.remove(current[stale])  # pending or failed, and no longer planned
    # The files a brief names that no job is held to. In an interview study only the writer's brief names one.
    named = (("analysis/quant.md", "analysis/checks.md", "analysis/lead-notes.md") if not talk else
             ("analysis/checks.md",) if role == "writer" else ())
    for name in named if prompts else ():
        if not (sd / name).is_file():
            say(f"Note: {name} does not exist, and the {role}'s brief names it.")
    short = unfinished_debriefs(cfg, runs) if prompts and not talk else {}
    if short:  # the lead may want them whole first: said, and nothing is held back for it
        them = agree(len(short), "it", "them")
        say(f"Debriefs not finished: {', '.join(f'{run} ({state})' for run, state in short.items())}. The "
            f"{CALLED[role]} {'are' if CALLED[role].endswith('s') else 'is'} given what there is of {them}, said to "
            f"be unfinished. To finish {them} first: launch.py {sd} stop, then interview.py {sd} debrief --runs "
            f"{','.join(short)}.")
    return set(unheard), given


def done_already(cfg: dict, chosen: list[dict], records: list[dict]) -> str:
    """What the lead is told when a job command of an interview study starts nothing because
    every job it is about is done: that, and how one is done again, which is to delete its file
    and run the role again. Nothing else says so, and "Finished: done 2." reads as if two jobs
    had just run. The command named has --allow-incomplete when the panel would still refuse
    the role without it."""
    names, files, role = [e["run"] for e in chosen], [e["file"] for e in chosen], chosen[0]["role"]
    unfinished = WAITS[role][0] and any(r["state"] in ("pending", "running", "blocked") for r in records)
    one = len(chosen) == 1
    return (f"{pl.listed(names)} {'was' if one else 'were'} done already, and nothing was started. To have "
            f"{'it' if one else 'one'} done again, delete its file ({pl.listed(files, 'or')}) and run launch.py "
            f"{cfg['_dir']} run --role {role}{' --allow-incomplete' if unfinished else ''} again.")


def after_jobs(cfg: dict, runs: list[dict], role: str, chosen: list[dict]) -> list[str]:
    """What comes after the jobs of a role, as the line a command ends with once the jobs it
    was asked for are done: what to read, and the next step of the synthesis. In an interview
    study the analysts and the critics may run in either order, so each names the other while
    it has a job that is not done, and the scripts that stand between two jobs are named with
    what they write. Nothing after the writer.

    A job of the command's own role may be still to run too: one that --allow-incomplete
    passed over for want of an interview to read, or one that --runs did not name. The line
    then names it, says when it can run and which roles wait for it, and goes on only as far
    as the analysis can without it: a line that went straight on to the scripts read as if
    the role were finished."""
    sd, read = cfg["_dir"], f"Next: read {', '.join(e['file'] for e in chosen)}"
    if cfg["type"] != "interview":
        return [f"{read}, then launch.py {sd} run --role writer."] if role == "analyst" else []
    if role == "themes":
        return [f"{read}, then analyze.py {sd}, which writes the tallies (analysis/quant.md), then launch.py {sd} "
                "run --role writer."]
    if role not in ("analyst", "critic"):
        return []
    other, on_record = "critic" if role == "analyst" else "analyst", {e["run"]: e for e in runs}
    to_run = {r: [j for j in pl.synthesis_jobs(cfg)
                  if j["role"] == r and state_of(cfg, on_record.get(j["run"], j)) != "done"] for r in (role, other)}
    extract = (f"extract_notes.py {sd}, which reads the notes and the critique into analysis/notes.csv and "
               "analysis/critique.csv")
    if not to_run[role] and not to_run[other]:
        return [f"{read}, then {extract}, then launch.py {sd} run --role themes."]
    out = [f"{read}."]
    if to_run[role]:
        records = pl.run_records(sd, cfg, held(cfg))
        mine = [j["run"] for j in to_run[role]]
        when = [f"{j['run']} once an interview of {interview.heard_from(j)} is held"
                for j in to_run[role] if interview.nothing_to_read(cfg, j, records)]
        waits = planning.listed([f"the {CALLED[r]}" for r, (_, before, _) in WAITS.items() if role in before])
        out.append(f"{planning.listed(mine)} {agree(len(mine), 'is', 'are')} still to run"
                   + (f", {when[0].split(' ', 1)[1]}" if when and len(mine) == 1 else
                      f" ({'; '.join(when)})" if when else "")
                   + f": launch.py {sd} run --role {role}. {waits[0].upper()}{waits[1:]} "
                   f"{'wait' if ' and ' in waits else 'waits'} for {agree(len(mine), 'it', 'them')}.")
    if to_run[other]:
        out.append(f"The {CALLED[other]} are still to run ({', '.join(j['run'] for j in to_run[other])}): launch.py "
                   f"{sd} run --role {other}.")
    elif role == "critic":  # the notes are all there, and the themes job reads nothing of the critique
        out.append(f"Until then: {extract} so far, then launch.py {sd} run --role themes.")
    return [" ".join(out)]


def fitness(cfg: dict, entries: list[dict], interview: bool | None = None) -> tuple[dict, dict, list[str]]:
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
    of them starts. interview is passed on to planning.unfit(): true for the entries a debrief
    is about to carry turn by turn, a finished run among them, which nothing on the entry says
    is a side of a conversation."""
    unusable = {}
    for name in dict.fromkeys(e["runner"] for e in entries):
        checked = planning.usable(name)
        if not checked["ok"]:
            unusable[name] = checked["message"]
    judged = {}  # one judgement for each model entry: asking a runner about a model can take a CLI call
    for e in entries:
        if e["runner"] not in unusable:
            judged.setdefault((e["role"], e["runner"], e["model"], e["effort"]),
                              planning.unfit(cfg, e, interview=interview))
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
    the materials: analysts and the writer start without them, and so do both sides of an
    interview, which are given their words and nothing to open. An interview is refused for
    what would spoil it as study.json stands (pl.interview_problems()), and through fitness()
    for a side on a runner that cannot carry one (planning.no_interview())."""
    locked = planning.unwritable_study(cfg) if targets else None
    if locked:
        return [], f"Nothing was started: {locked}"
    if any(e["role"] == "panellist" and "interview" not in e for e in targets):  # an interview reads and opens nothing
        uncaptured = planning.no_materials(cfg, planning.materials(cfg))
        if uncaptured:
            return [], f"Nothing was started: {uncaptured}"
        missing = pl.usability_problems(cfg)
        if missing:
            return [], "Nothing was started: " + " ".join(missing)
        no_browser = planning.no_browser(cfg, {e["runner"] for e in targets if e["role"] == "panellist"})
        if no_browser:
            return [], f"Nothing was started: {no_browser}."
    spoilt = pl.interview_problems(cfg) if any("interview" in e for e in targets) else []
    if spoilt:  # a leak term the interviewer would say, a persona with no topic: study.json changed since the scaffold
        return [], "Nothing was started: " + " ".join(spoilt)
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
    # Every interview has the one interviewer's model entry: what refuses it is said once, not for each interview.
    errors = list(dict.fromkeys(f"{'interviewer' if e['role'] == 'interviewer' else e['run']}: {error}"
                                for e in ready for error in unfit[e["run"]]))
    if errors:
        return [], "Nothing was started: fix these model entries in study.json.\n" + "\n".join(errors)
    return ready, None


def summary(cfg: dict, entries: list[dict]) -> bool:
    """Print the closing line and what to do next. True when every run is done."""
    states = [state_of(cfg, e) for e in entries]
    say("Finished: " + ", ".join(f"{s} {states.count(s)}" for s in STATES if s in states) + ".")
    for s, role in ((s, role) for s in STATES if s in NEXT for role in STARTABLE):
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
    """run, pilot and resume: queue the runs the command owns, then supervise them. An interview
    is queued by its participant's entry, as one item that the supervisor takes up and then
    carries turn by turn (Supervisor.take_up()): "run" and "pilot" take the ones that read
    pending or failed, and "resume" the ones that read partial or blocked, and goes on with one
    whose turn it found alive and adopted. "resume --runs <ids> --extend" also takes the ones
    named that read limited. One with a side that cannot be resumed and an answer on record is
    not queued: it is left alone, as a run with sections written and no session is. Nor is one
    whose turn log is not as a launcher writes one (interview.malformed()): what is left of
    such a log is no account of the interview, so nothing is added to it, the line says which
    record is wrong and what to do, and the command exits with 1.

    When "--role writer" leaves the writer of an interview study done, the quotations of its
    synthesis are checked against the transcripts (interview.quote_check(), which also writes
    analysis/quote-check.md): what is found is said, and the command exits with 1 when a
    quotation cannot be verified. The job stays done and nothing is sent back to it.

    A job's names in --runs are checked before anything is planned (plan_jobs()), and a job
    with no interview to read is neither planned nor started. A done job of an interview study
    that is out of date (interview.out_of_date_line(): an analyst or a critic whose file does
    not cover its interviews as they stand, a themes job or a writer written before a job it
    reads was run again or a file it was given changed) is said so in place of what comes next,
    the quote check included, and the command exits with 1: as with a quotation, the job stays
    done and the lead decides. A job command of an interview study that finds every job done
    and starts nothing says so, with how a job is done again (done_already())."""
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
    jobs = pl.job_roles(cfg)
    if args.role not in ("panellist", *jobs):  # "critic" and "themes" are jobs of an interview study alone
        raise SystemExit(f"--role {args.role} is for an interview study, and this is {pl.a_type(cfg['type'])} "
                         f"study: its jobs are {planning.listed([f'--role {job}' for job in jobs])}.")
    if args.allow_incomplete and not WAITS.get(args.role, (False,))[0]:
        raise SystemExit("--allow-incomplete goes with --role analyst or --role critic: it lets them start on an "
                         "unfinished panel." if "critic" in jobs else
                         "--allow-incomplete goes with --role analyst: it lets the analysts start on an "
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
        sup = Supervisor(cfg, runs, args.grace, args.poll, retry=command != "resume", stop=stop,
                         by="resume" if command == "resume" else "run")
        sup.reconcile()
        ids = [x.strip() for x in args.runs.split(",") if x.strip()] if args.runs else None
        unheard = set()  # the jobs with no interview to read: not planned, and never started
        if args.role in jobs:
            unheard, sup.given = plan_jobs(cfg, runs, args.role, command, args.allow_incomplete, ids)
            sup.save()
        if command == "pilot":
            first = cfg["personas"][0]["id"]
            ids = [e["run"] for e in runs if e["role"] == args.role and e["persona"] == first and e["replicate"] == 1]
        chosen = [e for e in select(runs, args.role, ids and [i for i in ids if i not in unheard])
                  if e["run"] not in unheard]

        plan = []
        for e in chosen:
            state = state_of(cfg, e)
            extend = state == "limited" and args.extend
            if "interview" in e:  # carried turn by turn from wherever its log stands
                wrong = interview.malformed(pl.read_turns(sd, e["run"])) if state != "done" else None
                adopted = command == "resume" and e["run"] in sup.interviews
                lacks = sup.lacking(e["run"]) if state in STARTS[command] or extend else None
                if wrong and (state in STARTS[command] or extend or adopted or ids):
                    sup.left_alone = True  # an adopted turn is settled and its interview put down (carry_on())
                    say(f"{e['run']}: {wrong}, so {command} leaves it alone. Put {pl.INTERVIEWS}/{e['run']}.jsonl "
                        "right, or to hold the interview again from its start move that file into logs/ and use "
                        f"launch.py {sd} run --runs {e['run']}.")
                elif lacks and sup.answers(e["run"]):  # with none it starts afresh when it is taken up
                    say(f"{e['run']}: {state} after {plural(sup.answers(e['run']), 'exchange')}: "
                        f"{sup.no_session(e['run'], *lacks)}.")
                elif state in STARTS[command] or extend:
                    plan.append((e, "interview", extend))
                elif command == "resume" and e["run"] in sup.interviews:
                    sup.interviews[e["run"]]["own"] = True  # its turn was adopted: this command goes on with it
                elif ids and state not in ("done", "running"):
                    say(f"{e['run']}: {state}, so {command} leaves it alone. Next: {NEXT[state]}.")
                continue
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
                lacks = session_gone(e, sup.runner(e["runner"]))
                kind = "restart" if lacks else "resume"
                if lacks and progress_of(cfg, e)["written"]:
                    sup.cannot_continue(e, lacks)
                    continue
            plan.append((e, kind, extend))
        # Both sides of an interview are judged, and it starts only when both may.
        hosts = {e["run"]: sup.pair(e["run"])["i"] for e, kind, _ in plan if kind == "interview"}
        ready, refusal = preflight(cfg, [e for e, _, _ in plan] + list(hosts.values()), args.allow_missing)
        if refusal:
            say(refusal)
        ready = {e["run"] for e in ready}
        for e, kind, extend in plan:
            if e["run"] not in ready or (e["run"] in hosts and hosts[e["run"]]["run"] not in ready):
                continue
            # When its harness said its limit lifts: on its entry, or for an interview on its turn log.
            lifts = (interview.standing(pl.read_turns(sd, e["run"]), sup.guide_of(e["run"]))["reset_at"]
                     if kind == "interview" else e.get("reset_at"))
            if extend and kind == "interview":
                sup.extend.add(e["run"])  # the side at its limit is known when it is taken up, which says so
            elif extend:
                e["extended"] = (e.get("extended") or 0) + 1
                sup.save()
                say(f"{e['run']}: extended, one more allowance of its limits. The plan's ceiling no longer "
                    "holds for this study.")
            elif lifts and lifts > time.time():
                say(f"{e['run']}: its harness said its limit lifts at {clock(lifts)}; trying anyway.")
            sup.queue.append((e, kind))
        began = bool(sup.queue or sup.adopted)  # whether this command starts, or goes on with, any process
        sup.supervise()
        # An adopted turn stands for its interview, which the participant's entry names.
        adopted = [sup.pair(e["interview"])["p"] if "interview" in e else e for e in sup.adopted]
        covered = chosen + [e for e in adopted if e["run"] not in {c["run"] for c in chosen}]
        done = summary(cfg, covered)
        ended = [e["run"] for e in covered if "interview" in e and state_of(cfg, e) == "done"]
        if ended:
            say(f"  Transcripts of the {plural(len(ended), 'interview')} that {agree(len(ended), 'is', 'are')} done: "
                f"{sd / pl.INTERVIEWS}/<run id>.md, and the analysts' copies in {pl.TRANSCRIPTS}/."
                + (" Read them before the rest: the next plan estimates from what the pilot used."
                   if command == "pilot" else ""))
        # A done job of an interview study that is out of date: its interviews have more on record than it read,
        # a job it reads was run again after it, or a file it was given has changed since. It stays done and the
        # lead decides, as with a quotation below: said in place of what comes next, and in the exit code.
        short, talk = [], args.role in jobs and cfg["type"] == "interview"
        if talk:
            records = pl.run_records(sd, cfg, held(cfg))
            short = [line for line in (interview.out_of_date_line(cfg, e, runs, records) for e in chosen
                                       if state_of(cfg, e) == "done") if line]
        for line in short:
            say(line)
        if talk and done and chosen and not short and not began:  # every job was done already: how one is done again
            say(done_already(cfg, chosen, records))
        for line in after_jobs(cfg, runs, args.role, chosen) if done and args.role in jobs and not short else ():
            say(line)
        unverified = False  # a quotation of the synthesis that is not in the exchange it names: said, and the exit code
        if talk and done and not short and args.role == "writer":  # the writer stays done: the lead decides
            lines, unverified = interview.quote_check(cfg)
            say("", *lines)
        return 0 if done and not (refusal or sup.left_alone or sup.refused or unverified or short) else 1
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

    def done(own: bool, spoken: list[str]) -> str:
        """What is said once everything is stopped. own: a run, a job or an interview was at
        work, which "resume" and "run" go on with. spoken: the debriefs that were, which only
        "interview.py debrief" goes on with: launch.py takes up none."""
        runs = (f"Runs that wrote sections are partial: continue them with launch.py {sd} resume. Runs that wrote "
                f"nothing are pending again: start them with launch.py {sd} run.")
        if cfg["type"] == "interview":
            runs = (f"Interviews with a turn on record are partial: continue them with launch.py {sd} resume, "
                    "which puts the turn that was stopped again. Interviews with none are pending: start them with "
                    f"launch.py {sd} run.")
        talks = (f"A debrief that was stopped is partial: go on with it with interview.py {sd} debrief --runs "
                 f"{','.join(spoken) or '<ids>'}.")
        return " ".join(["Stopped.", *([runs] if own or not spoken else []), *([talks] if spoken else [])])

    def working(entries: list[dict]) -> tuple[bool, list[str]]:
        """Of entries with a process on record: whether any is a run's, a job's or an
        interview's own, and the debriefs the others are a turn of."""
        turn = [e for e in entries if e.get("kind") == "debrief" or (pl.open_attempt(e) or {}).get("kind") == "debrief"]
        return len(turn) < len(entries), list(dict.fromkeys(pl.interview_of(e) for e in turn))

    held = Lock.holder(sd)
    if held and not held["seen"]:
        raise SystemExit(f"A launcher has this study{Lock.who(held)}, and \"stop\" could not ask it to stop. {UNSEEN}, "
                         f"so nothing was signalled and the runs go on. {pl.SANDBOX_HINT}")
    if held:
        try:
            os.kill(held["pid"], signal.SIGTERM)
        except OSError as err:
            raise SystemExit(f"Could not signal the launcher (pid {held['pid']}): {err}")
        # What it has at work, read before it is asked: once it has stopped, nothing on record says what it held.
        entries = pl.read_runs(sd) if (sd / "runs.json").exists() else []
        own, spoken = working([e for e in entries if in_flight(e) or e.get("carried")])
        if held.get("command") == "debrief":  # it starts nothing but turns of debriefs, and may be between two
            spoken = spoken or ["<ids>"]
        else:  # it may have runs still queued, which nothing on record tells from the ones it never chose
            own = True
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
            own, spoken = working([c.entry for c in sup.children])
            sup.stop.asked = True
            sup.supervise()
        finally:
            lock.release()
        say(done(own, spoken) if stopped else "Nothing is running.")
        if sup.held:  # said last, and by the exit code: the runs are stopped, and the study is still held up
            print(f"{sup.held}\nstop started no command of the study either: the success checks and teardowns that "
                  "are due stay due, and the next launcher command sees to them once that is cleared.",
                  file=sys.stderr, flush=True)
            return 1
        return 0
    say(done(own, spoken))
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
        raise SystemExit("check runs the success checks of a usability study's tasks, and this is "
                         f"{'an interview' if cfg['type'] == 'interview' else 'a review'} study.")
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


def side_facts(e: dict, current: float = 0) -> dict:
    """What "status" says of the interviewer's entry of a conversation, under its row's
    "interview": the model entry, the turns it has had, its time and usage, and what became of
    its session, under the keys a row has for its own entry. current is how long its turn in
    flight has run, which is not in "seconds_used" yet."""
    return {"run": e["run"], "key": e["key"], "runner": e["runner"], "model": e["model"],
            "attempts": len(e.get("attempts") or []), "seconds_used": round((e.get("seconds_used") or 0) + current, 1),
            "usage": usage_of(e), "unreported_attempts": planning.unreported(e), "extended": e.get("extended") or 0,
            "session": e.get("session"), "purged": sorted(e.get("purged") or {}), "lost": sorted(e.get("lost") or {}),
            "unsaved": sorted(e.get("unsaved") or {})}


def side_used(side: str, facts: dict) -> str:
    """One side of an interview in its row of "status": "interviewer: 4 turns, 38s, 21,480 in
    and 912 out tokens, $0.11", then what is out of the usual course with it: usage a stopped
    process never reported, an allowance it was given with --extend, and a session that
    cannot be continued. Nothing of a side that has had no turn. facts is a row, for the
    participant, or side_facts()."""
    u, session = facts["usage"], facts["session"]
    said = [plural(facts["attempts"], "turn") if facts["attempts"] else "",
            duration(facts["seconds_used"]) if facts["attempts"] else "",
            f"{u['input_tokens']:,} in and {u['output_tokens'] or 0:,} out tokens" if u["input_tokens"] is not None
            else "",
            f"${u['cost_usd']:.2f}" if u["cost_usd"] is not None else "",
            f"usage of {planning.attempts_named(facts['unreported_attempts'])} not reported (process was stopped)"
            if facts["unreported_attempts"] else "",
            f"extended {facts['extended']}x" if facts["extended"] else "",
            "session purged" if session in facts["purged"] else "session lost" if session in facts["lost"] else
            "session not saved" if session in facts["unsaved"] else "earlier sessions purged" if facts["purged"]
            else ""]
    return f"{side}: " + ", ".join(x for x in said if x) if any(said) else ""


DEBRIEF_NEXT = ("pending", "partial", "blocked", "failed")  # the states "interview.py debrief" goes on from


def debrief_facts(cfg: dict, e: dict, host: dict, blind: bool = False, now: float | None = None) -> dict:
    """What "status", the plan and "interview.py debrief" say of the debrief of a finished run:
    e is the run's entry and host the entry of the debrief's interviewer (pl.debrief_of()).

        state, reason, reset_at   read from the turn log and whether a launcher carries it, as
                    an interview's are (interview.standing()). The run's own state is no part
                    of this, and stays as it was
        exchanges, cap, awaiting  how far it got, of the cap of study.json "debrief"
        side, process, pid        the side with a turn in flight and what can be seen of its
                    process, as a row of "status" says it of a run: "alive", "gone", "unseen",
                    or "between turns" while a launcher carries it with none. None when
                    nothing of it is at work
        participant {"turns", "seconds", "usage", "unreported_attempts"}: what the debrief's
                    turns have used of the run's session (entry["debrief"])
        interviewer its entry's own figures (side_facts())

    A study whose "debrief" block was taken out after a debrief was held has no guide to read
    a cap from: "cap" is then None, and the reason is what the log itself gives, a "halt" or a
    turn that left no reply (interview.standing(), with no guide). A log that is not as a
    launcher writes one is the reason either way."""
    sd, now = cfg["_dir"], now or time.time()
    records, guided = pl.read_turns(sd, e["run"]), "debrief" in cfg
    state = state_of(cfg, host)
    stands = interview.standing(records, pl.guide(cfg, e["persona"], "debrief") if guided else None)
    live = next((x for x in (e, host) if (pl.open_attempt(x) or {}).get("kind") in pl.TURN_KINDS), None)
    process, pid, current = None, None, 0
    if live:
        log = sd / "logs" / f"{live['run']}.{live['attempts'][-1]['n']}"
        pids = recorded(log.with_name(log.name + ".pid")) or {}
        record = end_record(log.with_name(log.name + ".end")) if pids else None
        over, hidden = not pids or record or not living(pids), blind or unseen(pids)
        process = "unseen" if hidden else "gone" if over else "alive"
        pid = pids["cli"][0] if pids else None
        current = ((record or {}).get("ended") or now) - live["attempts"][-1]["started"]
    if state == "running" and (not live or process == "gone"):  # a launcher has it, and sees to a turn that ended
        process = "between turns"
    spoken = e.get("debrief") or {}
    return {"state": state, "exchanges": sum(r["t"] == "answer" for r in records),
            "cap": cfg["debrief"]["turns"] if guided else None, "awaiting": stands["awaiting"],
            "reason": stands["reason"], "reset_at": stands["reset_at"],
            "side": side_of(live) if live else None, "process": process, "pid": pid,
            "participant": {"attempts": spoken.get("turns") or 0,
                            "seconds_used": round((spoken.get("seconds") or 0) + (current if live is e else 0), 1),
                            "usage": planning.debrief_usage(e),
                            "unreported_attempts": planning.unreported(e, debrief=True), "extended": 0,
                            "session": e.get("session"), "purged": sorted(e.get("purged") or {}),
                            "lost": sorted(e.get("lost") or {}), "unsaved": sorted(e.get("unsaved") or {})},
            "interviewer": side_facts(host, current if live is host else 0)}


def status(args, cfg: dict) -> int:
    """Print every run and job as it is on record, with what can be seen of its process. Starts
    nothing, holds no lock and changes nothing.

    A launcher has the study when the lock says so (Lock.holder()). When its process is not to
    be seen from this shell, no process of the study is: a run's process is then "unseen", in
    place of "alive" or "gone", nothing is said of its browser session, and no run is called
    gone for a launcher to settle. One line says so. With no launcher, the same is said of each
    run that is alive where this shell cannot look: its watchdog holds its lock and is not to
    be seen (unseen()). A run whose watchdog has let go of its lock is "gone", wherever it ran.

    An interview has one row, on its participant's entry: its interviewer's has none. Its state
    and its reason are read from its turn log (interview.standing()), and a log that is not as
    a launcher writes one is the reason, with each such record named, whatever the rest of the
    log reads as, "done" too. "scored" and "of" count
    the topics a question has opened, and "interview" has the exchanges, the cap, which side
    is awaited, which has a turn in flight ("side") and, under "interviewer", what that entry
    has used (side_facts()): the row's own "attempts", "seconds_used", "usage", "extended" and
    "session" are the participant's. Its process is that of whichever side has a turn in
    flight. While a launcher has the study it is "between turns" with none, and also with one
    whose process has ended and is not recorded yet, which the launcher sees to at its next
    look: neither is a process gone missing. With no launcher nothing is carried (pl.carried()):
    an interview that one left reads as its log reads, its process is that of the turn it left
    in flight, alive or gone, and one line under the rows names those, for "resume" to take up.

    A run that has a debrief has "debrief" on its row (debrief_facts()): the debrief's state,
    how far it got, which side is awaited or replying, the reason its log gives and what each
    side has used. The row's own state, attempts, time and usage stay the run's: a turn of the
    debrief is no attempt of the run, and its process is the debrief's. A line under the rows
    counts the debriefs and says which command goes on with one that is not finished."""
    sd, now = cfg["_dir"], time.time()
    held = Lock.holder(sd)
    cfg["_held"] = bool(held)  # the one answer every state below is read against (held())
    blind = bool(held) and not held["seen"]
    rows = {"run": [], "job": []}  # panellist runs, then the jobs of the synthesis
    entries = pl.read_runs(sd)
    hosts = {e["interview"]: e for e in entries if e["role"] == "interviewer" and "interview" in e}
    for e in entries:
        if e["role"] not in ROLES or e["role"] == "interviewer":
            continue
        prog, attempts = progress_of(cfg, e), e.get("attempts") or []
        talk = "interview" in e
        # The entry whose attempt is in flight: of an interview, the side that has a turn out.
        # A turn of a debrief on a finished run is no attempt of the run: its process is said under "debrief".
        spoken = [a for a in attempts if a.get("kind") == "debrief"]
        live = next((x for x in ((e, hosts[e["run"]]) if talk else (e,)) if in_flight(x)
                     and not (x is e and not talk and (pl.open_attempt(e) or {}).get("kind") == "debrief")), None)
        running, turns = bool(live), (live or e).get("attempts") or []
        asked = planning.followup_attempts(e)
        debriefed = pl.debrief_of(entries, e["run"]) if e["role"] == "panellist" and not talk else None
        own = ({"scored": len(prog["scored"]), "of": len(prog["units"])} if e["role"] == "panellist"
               else {"model": e["model"], "file": e["file"], "note": e.get("note")})
        state = state_of(cfg, e)
        stands = interview.standing(pl.read_turns(sd, e["run"]), pl.guide(cfg, e["persona"])) if talk else {}
        # The attempt's own files say where its processes are, and whether it has ended: runs.json
        # lacks the pid when a launcher died early, and says "running" until a launcher settles it.
        log = str(sd / "logs" / f"{live['run']}.{turns[-1]['n']}") if running and turns else None
        pids = (recorded(Path(log + ".pid")) if log else None) or {}
        record = end_record(Path(log + ".end")) if pids else None
        over = not pids or record or not living(pids)
        hidden = blind or unseen(pids)
        current = ((record or {}).get("ended") or now) - turns[-1]["started"] if log else 0
        # A launcher carries it and no turn is at work: none is in flight, or one has ended and is not recorded yet.
        between = talk and state == "running" and (not running or (bool(over) and not hidden))
        host = side_facts(hosts[e["run"]], current if live is hosts[e["run"]] else 0) if talk else None
        rows["job" if role_of(e).noun == "job" else "run"].append({
            "run": e["run"], "role": e["role"], "name": e.get("name", ""), "key": e["key"], "runner": e["runner"],
            "state": state, **own,
            **({"interview": {"exchanges": prog["exchanges"], "cap": prog["cap"], "awaiting": stands["awaiting"],
                              "side": live and side_of(live), "interviewer": host}} if talk else {}),
            "process": "between turns" if between else ("unseen" if hidden else "gone" if over else "alive")
            if running else None,
            "pid": pids["cli"][0] if pids else None, "attempts": len(attempts) - len(asked) - len(spoken),
            **({"debrief": debrief_facts(cfg, e, debriefed, blind, now)} if debriefed else {}),
            "followups": sorted({a["followup"] for a in asked if a.get("ended") is not None}),  # the settled ones
            "asking": asking(e)["followup"] if asking(e) else None,
            # Its file was read as it stood before that follow-up: nothing is taken from it until it is settled.
            "unsettled": bool(asking(e)) and pl.read_copy(Path(log + ".before")) is not None,
            "seconds_used": round((e.get("seconds_used") or 0) + (current if live is e and not asking(e) else 0), 1),
            "usage": usage_of(e), "unreported_attempts": planning.unreported(e),
            "unallocated": planning.unallocated(e),
            # Of an interview that is done, only that its log is not as a launcher writes one (standing()).
            "reason": stands["reason"] if talk else e.get("reason") if state != "done" else None,
            "leftover": still_left(attempts[-1].get("leftover")) if attempts else None,
            # The browser session of the attempt now running (browser_session.state()), and what was found or
            # left of the session of its last attempt (Supervisor.browser_left()).
            "browser": browser.state(log) if log and not over and not hidden else None,
            "browser_left": attempts[-1].get("browser_left") if attempts else None,
            "account": e.get("account"),  # a usability run's test account (panel_lib.py), with no identifier or secret
            "checks": e.get("checks"),    # what the success check of each of its tasks said (accounts.py)
            "released": e.get("released"),  # when the lead let its account go with "release", unfinished
            "reset_at": stands["reset_at"] if talk else e.get("reset_at"),
            "extended": e.get("extended") or 0, "session": e.get("session"),
            "purged": sorted(e.get("purged") or {}), "lost": sorted(e.get("lost") or {}),
            "unsaved": sorted(e.get("unsaved") or {})})  # the sessions its harness did not keep (ended())
    every = rows["run"] + rows["job"]
    extended = [r["run"] for r in every if r["extended"] or (r.get("interview") or {"interviewer": {}})[
        "interviewer"].get("extended")]
    gone = [r["run"] for r in every if r["process"] == "gone" and "interview" not in r]
    # With no launcher, the interviews one left with a turn in flight: nothing carries them, and "resume" does.
    left = [f"{r['run']} ({'still running' if r['process'] == 'alive' else 'ended since'})"
            for r in every if "interview" in r and r["process"] in ("alive", "gone")] if not held else []
    followups, earlier = pl.read_followups(sd), len(pl.read_earlier_sessions(sd))
    debriefs = {r["run"]: r["debrief"] for r in rows["run"] if r.get("debrief")}
    if args.json:
        print(json.dumps({"launcher": held, "runs": rows["run"], "jobs": rows["job"], "extended": extended,
                          "ceiling_holds": not extended, "followups": len(followups),
                          **({"debriefs": len(debriefs)} if debriefs else {}),
                          "earlier_sessions": earlier}, indent=2))
        return 0
    for noun, group in rows.items():
        if noun == "job" and group:
            print("\nAnalysts, critics, themes and writer:" if "critic" in pl.job_roles(cfg) else
                  "\nAnalysts and writer:")
        for r in group:
            u, shared = r["usage"], r["unallocated"]
            lump = [] if not shared else (
                [f"{shared['input_tokens']:,} in and {shared['output_tokens'] or 0:,} out tokens"]
                if shared["input_tokens"] is not None else []) + (
                [planning.money(shared["cost_usd"])] if shared["cost_usd"] is not None else [])
            talk, d = r.get("interview") or {}, r.get("debrief")
            replying = bool(talk.get("side")) and r["process"] in ("alive", "unseen")
            answering = bool(d) and bool(d["side"]) and d["process"] in ("alive", "unseen")
            facts = [f"{talk['exchanges']} of {talk['cap']} exchanges" if talk else "",
                     f"{r['scored']} of {plural(r['of'], 'topic')} opened" if talk else "",
                     (REPLYING if replying else AWAITED).get(talk.get("awaiting"), "") if r["state"] != "done" else "",
                     ", ".join(x for x in ("" if r["process"] == "unseen" else
                                           r["process"] if r["process"] == "between turns" else
                                           f"process {r['process']}",
                                           f"pid {r['pid']}" if r["pid"] and r["process"] != "between turns"
                                           else "") if x) if r["process"] else "",
                     {"up": "browser session up", "starting": "browser session starting",
                      "down": "browser session not running"}.get(r["browser"], ""),
                     (f"being asked follow-up {r['asking']}" if r["process"] == "alive"
                      else f"follow-up {r['asking']} not settled") if r["asking"] else "",
                     *([side_used("participant", r), side_used("interviewer", talk["interviewer"])] if talk else [
                         plural(r["attempts"], "attempt") if r["attempts"] else "",
                         f"asked follow-up {planning.listed([str(n) for n in r['followups']])}" if r["followups"]
                         else "",
                         duration(r["seconds_used"]) if r["attempts"] else "",
                         f"{u['input_tokens']:,} in and {u['output_tokens'] or 0:,} out tokens"
                         if u["input_tokens"] is not None else "",
                         f"${u['cost_usd']:.2f}" if u["cost_usd"] is not None else "",
                         f"usage of {planning.attempts_named(r['unreported_attempts'])} not reported (process was "
                         "stopped)" if r["unreported_attempts"] else "",
                         f"{' and '.join(lump)} unallocated between the run and a follow-up" if lump else "",
                         f"extended {r['extended']}x" if r["extended"] else ""]),
                     *([f"debrief {d['state']}: {d['exchanges']}"
                        + (f" of {plural(d['cap'], 'exchange')}" if d["cap"] else " exchanges"),
                        (REPLYING if answering else AWAITED).get(d["awaiting"], "") if d["state"] != "done" else "",
                        ", ".join(x for x in ("" if d["process"] == "unseen" else
                                              d["process"] if d["process"] == "between turns" else
                                              f"process {d['process']}",
                                              f"pid {d['pid']}" if d["pid"] and d["process"] != "between turns"
                                              else "") if x) if d["process"] else "",
                        side_used("participant", d["participant"]), side_used("interviewer", d["interviewer"])]
                       if d else []),
                     "" if not r["account"] else "test account torn down" if r["account"]["torn_down"]
                     else "test account in force",
                     f"released by the lead {clock(r['released'])}" if r["released"] else "",
                     "checked: " + ", ".join(
                         f"{task} {'failed to run' if c['error'] else 'completed' if c['checked'] else 'not completed'}"
                         for task, c in r["checks"].items()) if r["checks"] else "",
                     "" if talk else  # of an interview each side's session is said with that side (side_used())
                     "session purged" if r["session"] in r["purged"] else
                     "session lost" if r["session"] in r["lost"] else
                     "earlier sessions purged" if r["purged"] else ""]
            lost = r["browser_left"]
            why = [r["reason"] or "", r.get("note") or "",
                   f"its debrief: {d['reason']}" if d and d["reason"] else "",
                   f"its debrief's limit lifts {clock(d['reset_at'])}" if d and d["reset_at"] else "",
                   UNSAVED if r["session"] in r["unsaved"] and not talk else "",
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
            print(f"{r['run']:<16} {r['state']:<8} " + (r["name"] if talk else f"{r['scored']}/{r['of']}  {r['name']}"
                                                         if noun == "run" else f"{r['file']}  {r['name']}")
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
    if left:
        print(f"A launcher that is gone left a turn in flight in {planning.listed(left)}. launch.py {sd} resume "
              "records what each turn came to and goes on with its interview, and stop records it and leaves the "
              "interview partial"
              + (", from a shell that sees the runs this one cannot." if unseen_here else "."))
    for line in pl.unsettled_lines(rows["run"]):
        print(line)
    if extended:
        print(f"Extended past their limits: {', '.join(extended)}. The plan's ceiling no longer holds for this study.")
    if followups:
        print(f"Follow-up questions asked: {len(followups)} (followup.py {sd} list). What they use is outside the "
              "plan's ceiling, under limits.followup.")
    if debriefs:
        ended = sum(d["state"] == "done" for d in debriefs.values())
        # A debrief's transcripts are written when it is put down at its end, and before a brief names them.
        written = [run for run in debriefs if (sd / pl.INTERVIEWS / f"{run}.md").is_file()]
        without = [run for run in debriefs if run not in written]
        where = f"in {pl.INTERVIEWS}/<run id>.md, and the analysts' copies in {pl.TRANSCRIPTS}/."
        print(f"Debriefs: {len(debriefs)} on record, {ended} done. What they use is outside the plan's ceiling, under "
              "limits.debrief, each side its own."
              + (f" Their transcripts are {where}" if not without else
                 f" The transcripts of {planning.listed(written)} are {where}" if written else "")
              + (f" {planning.listed(without)} {agree(len(without), 'has', 'have')} no transcript yet: a debrief's "
                 f"are written when it ends, and interview.py {sd} render writes them from the turns so far."
                 if without else ""))
        adrift = [f"{run} ({'still running' if d['process'] == 'alive' else 'ended since'})"
                  for run, d in debriefs.items() if d["process"] in ("alive", "gone")] if not held else []
        if adrift:
            print(f"A launcher that is gone left a turn of a debrief in flight in {planning.listed(adrift)}. "
                  f"interview.py {sd} debrief --runs <ids> records what each turn came to and goes on with its "
                  f"debrief unless that turn was its last, and launch.py {sd} stop records it and holds no debrief"
                  + (", from a shell that sees the runs this one cannot." if unseen_here else "."))
        open_ = [run for run, d in debriefs.items() if d["state"] in DEBRIEF_NEXT and run not in
                 {x.split(" ")[0] for x in adrift}]
        if open_ and not held:
            each = ", ".join(f"{run} ({debriefs[run]['state']})" for run in open_)
            print(f"Debriefs not finished: {each}. interview.py {sd} debrief --runs {','.join(open_)} goes on with "
                  "each at the turn its log reached.")
        at_end = [run for run, d in debriefs.items() if d["state"] == "limited"]
        if at_end:
            print(f"Debriefs at their end, a side's allowance used (limits.debrief): {', '.join(at_end)}. A debrief "
                  "has no --extend: its transcripts hold what was said.")
    if earlier:
        print(f"{planning.earlier_sessions(earlier)} {planning.purge_hint(sd)}")
    return 0


def plan(args, cfg: dict) -> int:
    """Print the plan. Starts no run, holds no lock and writes nothing to the study: whether a
    launcher has it is asked of the lock, which says so from any shell (Lock.holder()). A
    runner's sign-in check may let its harness refresh its own login. An interview study's
    plan is of its interviews, each with both its sides: its interviewers' entries are given to
    planning.build() with its participants', and exit code 1 says, as for any study, that
    something stops "run", a side on a runner that cannot carry an interview among it. A review
    or usability study with a "debrief" block, or with a debrief on record, has a section on
    debriefs (planning.debrief_lines()): every debrief with its state, and who cannot be
    debriefed as study.json stands (interview.unfit_for_debrief()), which stops no run and so
    is no problem of the plan."""
    sd = cfg["_dir"]
    scaffolded = (sd / "runs.json").exists()
    entries = pl.read_runs(sd) if scaffolded else pl.planned_runs(cfg) + pl.planned_interviewers(cfg)
    on_record = {e["run"]: e for e in entries if e["role"] in pl.job_roles(cfg)}
    jobs = []
    for job in pl.synthesis_jobs(cfg):
        seen = on_record.get(job["run"])
        if seen and state_of(cfg, seen) not in ("pending", "failed"):
            jobs.append(seen)  # as it ran: "run" plans afresh only a job that is pending or failed
        else:
            jobs.append({**(seen or {}), **job})
    # Both sides of an interview are the plan's: each has a model entry, limits and a budget cap of its own.
    panel = [e for e in entries if e["role"] == "panellist" or (e["role"] == "interviewer" and "interview" in e
                                                                and cfg["type"] == "interview")]
    # A review or usability study that can hold a debrief, or has: said in a section of its own, and no run of the plan.
    hosts = [e for e in entries if e.get("kind") == "debrief" and e["role"] == "interviewer"]
    debrief = None
    if cfg["type"] != "interview" and ("debrief" in cfg or hosts):
        runs = {e["run"]: e for e in panel}
        spoken = {h["interview"]: debrief_facts(cfg, runs[h["interview"]], h) for h in hosts if h["interview"] in runs}
        debrief = {"hosts": hosts, "refused": interview.unfit_for_debrief(cfg, panel),
                   "held": {run: {k: d[k] for k in ("state", "exchanges", "cap", "reason")}
                            for run, d in spoken.items()}}
    facts = planning.build(cfg, panel, jobs, {e["run"]: state_of(cfg, e) for e in panel + jobs + hosts}, scaffolded,
                           Lock.holder(sd), debrief)
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
    each taken off the record once it is deleted.

    A conversation is named by its run id, which covers the entries of both its sides, each
    with the folder its own processes worked in. It is refused while a turn of either is in
    flight, and while it is on record as carried: between two turns a launcher that was killed
    left it so, and "stop" settles it."""
    sd = cfg["_dir"]
    lock = Lock(sd)
    if args.yes:
        lock.acquire("purge-sessions", args.grace)  # refuses while a launcher has the study
    elif Lock.holder(sd):
        lock.refuse()
    try:
        runs = pl.read_runs(sd)
        running = list(dict.fromkeys(pl.interview_of(e) for e in runs if in_flight(e) or e.get("carried")))
        if running:
            raise SystemExit(
                f"{plural(len(running), 'run')} recorded as running ({', '.join(running)}): a running process needs "
                f"its session. Nothing was deleted. Stop and settle them first: launch.py {sd} stop")
        known = [e for e in runs if e["role"] in ROLES]
        ids = [x.strip() for x in args.runs.split(",") if x.strip()] if args.runs else None
        unknown = [i for i in ids or [] if i not in {pl.interview_of(e) for e in known}]
        if unknown:
            raise SystemExit(f"No run or job called {', '.join(unknown)}.")
        # The sessions of the runs a --force replaced (panel_lib.py), which only a purge of the whole study covers.
        earlier = pl.read_earlier_sessions(sd)
        # (runs.json entry or earlier session, session id, argv, is it an earlier one); why a session stays -> [whose]
        doomed, kept, total = [], {}, 0
        for e in known:
            if ids is not None and pl.interview_of(e) not in ids:  # an interview's id names both its entries
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
                    command = runner.purge_command(session, role_of(e).workdir(cfg, e))
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
    ap.add_argument("--role", default="panellist", metavar="{" + ",".join(STARTABLE) + "}",
                    help="what to start (run, resume): panellist runs (the default), the analyst jobs, or the "
                         "writer job once the analysts are done. In an interview study also the critic jobs "
                         "and the themes job, and each waits for what it reads")
    ap.add_argument("--allow-incomplete", action="store_true",
                    help="with --role analyst: start the analysts while panellist runs are pending, running or "
                         "blocked, and tell them which runs are incomplete. In an interview study with --role "
                         "critic too")
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
    if args.role == "interviewer":  # a role of runs.json that no command starts by itself
        ap.error("argument --role: no command takes interviewer. An interviewer starts and stops with its "
                 "interview: leave --role out, and name the interview by its run id with --runs.")
    if args.role not in STARTABLE:
        ap.error(f"argument --role: invalid choice: {args.role!r} (choose from {', '.join(STARTABLE)})")
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
