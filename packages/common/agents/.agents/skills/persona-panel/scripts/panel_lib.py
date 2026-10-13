"""Shared helpers for the persona-panel scripts: study config, runs.json, and persona-file parsing.

Standard library only. Every script takes a study directory laid out as:

    <study>/study.json        lead config (never shown to panellists)
    <study>/key.md            neutral label -> concept key (lead only)
    <study>/forms.json        {concept id: form} for each "files" concept, the form its files reached
                              the panel in (lead only: concept_forms(), below)
    <study>/sites/            neutral copies of the "site" concepts, when panellists do not browse
                              (lead only: sites_dir(), below)
    <study>/study-brief.md    what the lead agreed with the user, from assets/study-brief.md (lead
                              only: init_study.py refuses a copy of it anywhere under panel/)
    <study>/runs.json         one entry per run (schema below)
    <study>/prompts/          one run prompt per run, <run id>.md, and one filled brief per analyst
                              and writer job, <job id>.md
    <study>/panel/            the only folder panellists may read
        _panel-instructions.md
        sites/concept-<L>/    neutral copies of each concept of kind "site", only in a study whose
                              panellists browse: a copy holds the page source under its own file
                              names, so a study that does not browse (a text-only study, "browse":
                              false, or a "url" concept without "browse": true) keeps them in
                              <study>/sites/ instead, where no panellist can read one. A "url" or
                              "files" concept has no copy (concept kinds, below)
        materials/concept-<L>/<page>/
        personas/<pid>-<slug>--<key>.md, or ...--<key>-r<n>.md for replicate n > 1. None is
                              read or written through a symbolic link (persona_bytes(), below)
        scratch/<run id>/     and, in a usability study with accounts, its account.json: what
                              the run's panellist is told of its test account (below)
        evidence/<run id>/    usability only: the run's step log, steps.jsonl, and the
                              screenshot of each step (below). Nothing else belongs here, and
                              nothing is read from it through a symbolic link (evidence_fd())
        rooms/<run id>/       interview only: the folder a participant's process starts in. It
                              holds nothing, and nothing reads what a process leaves there
    <study>/interviewer/      interview only: <run id>/, the folder the interviewer of that run
                              starts in. It holds nothing either: all an interviewer is given is
                              in its prompt
    <study>/interviews/       interview only, and the launcher's alone: <run id>.jsonl, the turn
                              log of each interview ("The turn log", below), and <run id>.md,
                              its transcript. No session of either side is told it exists
    <study>/accounts/         usability only, lead only: <run id>.json, the test account
                              provisioned for each run, with its secrets (accounts.py). Mode
                              0600, never under panel/. And fingerprints.json, what a scan
                              knows those secrets by once they are gone ("Secrets", below)
    <study>/analysis/         scores.csv, rankings.csv, runs.csv, answers.csv, lines.csv (what each run
                              answered and quoted), in a usability study tasks.csv and steps.csv
                              (extract_scores.py), quant.md, quant.json, checks.md,
                              lead-notes.md (the lead's), qual-<n>.md (one per analyst), SYNTHESIS.md
                              (the writer's) and, from launch.py, <job id>-reply.md and usage.md
                              (what each harness reported: per run, per model key, per role and
                              in total). In an interview study also transcripts/<run id>.md, the
                              analysts' copy of each transcript: the questions and answers, with
                              no situation card and none of the interviewer's notes
    <study>/logs/             launch.py only: <run id>.<attempt>.in, .out and .err, the input and
                              output of each CLI process it started; .pid, where the attempt's
                              watchdog records itself and the CLI before the CLI runs, the
                              process namespace they run in where the system names one, and,
                              for as long as it runs, the command that starts the attempt's
                              browser session; .lock, an empty file the watchdog holds a lock
                              on for as long as it lives, which is how any shell tells that it
                              does; .end, the end record the watchdog writes when the
                              attempt has ended (all three in run_watchdog.py); for an
                              attempt of a run that may browse, .browser, the record of the
                              browser session its watchdog starts before the CLI and stops
                              after it, .policy, that session's action policy while it is up
                              (both in browser_session.py, and both named by the attempt alone:
                              whoever stops a session works them out from the attempt, and
                              takes no path to delete from the record), and
                              .hooks, what starting and stopping it printed; .state, a private
                              copy of the run's saved browser state, which the session deletes
                              once it has loaded it; modifications.json (the
                              modification record, below); earlier-sessions.json (the sessions
                              of the runs init_study.py --force replaced, below); and, for an
                              attempt that put a follow-up question, .before, the persona file
                              as it was, kept until the attempt's end is in runs.json (the
                              snapshot rule, below), and .rejected.md, the file as a rejected
                              follow-up left it; and, in a usability study,
                              <run id>.<attempt>.evidence, a folder: what the run's evidence
                              folder held after that attempt, moved here when the run was
                              next started afresh (launch.py). It is the lead's alone, and
                              nothing reads it as evidence. A process that never
                              ran as the CLI is no attempt: its files stay until the next
                              attempt, which has the same number, replaces them. And, in an
                              interview study, interviews-<epoch seconds>/: the turn logs and
                              transcripts that an init_study.py --force replaced, the analysts'
                              copies under transcripts/ in it, the files of the replaced
                              entries' attempts under logs/ and analysis/usage.md and
                              analysis/checks.md as they stood under analysis/
    <study>/.launch.lock      launch.py only: the study's lock file, which a launcher holds a
                              lock on while it has the study and which names that launcher
                              meanwhile. Made empty by init_study.py, emptied by a launcher
                              that ends, and never removed (launch.py, Lock)
    <study>/.capture-<pid>-*/ capture.py only: the scratch folder of one capture, named after its
                              process, where each page or item is captured before it moves
                              under panel/materials, beside a record of any move under way. One
                              whose process is gone is settled by the next capture, which
                              finishes the move or puts the earlier capture back, and removed
                              (capture.py, publish() and settle())
    <study>/followups.json    followup.py only: the follow-up questions asked (format below)

Concept kinds. A concept in study.json is one of three kinds, named by its optional "kind":

    site    (default) "path": a folder with index.html. init_study.py copies it to
            concept-<L>/ under sites_dir(), and capture.py captures each <page>.html of the copy
            into materials/concept-<L>/<page>/
    url     "pages": [{"name", "url"}, ...], the first named "index", or "url" alone for a
            concept of one page. Nothing is copied: capture.py opens each address and captures it
            as it does a site page, into materials/concept-<L>/<name>/. "states" work as for a site
    files   "files": image and PDF paths in the order to go through them, or "path": a folder
            whose images and PDFs are taken in name order. Nothing is copied by init_study.py.
            capture.py writes each file to materials/concept-<L>/item-<NN>/: an image as
            image.<type>, with part-<NN>.png when it is much taller than a screen, and a PDF as
            page-<NN>.png, one per page, with page-text.txt. A text-only study takes the PDFs only

Nothing under panel/ and no run prompt carries a concept id, a source path, a file name or, unless
the study browses, a URL: key.md maps them for the lead. concept_kind(), url_pages(),
concept_items(), concept_pages() and concept_folders() read a concept, and check_concepts()
validates its shape.

Names that become paths. Every configured string that names a file or folder is checked when
study.json is loaded, so none can leave the folder it belongs in: a url page's name and a state's
name (PAGE_NAME, a folder under materials/), a pinned label (LABEL), a concept id, a persona id
and a persona slug (name_problem(): one file-name part, with no separator and no leading dot or
hyphen). A persona id holds no hyphen at all (persona_id_problem()), and a persona whose name
gives an empty slug needs a "slug". Model keys are letters and digits (KEY_RE). capture.py checks again, on the paths
themselves, that everything it writes or deletes is inside panel/materials.

Forms. forms.json records the form each "files" concept reached the panel in ("image files",
"PDF files" or "image and PDF files"), by concept id. init_study.py and capture.py write it from
the source files, and concept_forms() reads it when those can no longer be read, as in an
archived round, so that analyze.py still says when a PDF was compared with an image.

Browsing ("browse") defaults to true for a study of sites. With any "url" concept it is off unless
study.json says "browse": true, and then the instructions give each page's address. A "files"
concept has nothing to open, and a study of nothing else never browses (apply_kinds()). Where the
site copies are kept follows from it (sites_dir()).

A study with one concept ranks and compares nothing: single_concept() says so, and the
templates, checks and analysis follow it. Its instructions speak of one "artefact" (the singular
of "artefact_plural"), which study.json must give when it sets the plural.

Usability studies. "type": "usability" tests whether a persona can complete tasks in a running
product. It has no concepts, nothing is captured, and every run browses, so it has no key.md,
forms.json, sites/ or panel/materials. The unit a run works through is a task, and its persona file has a scored "### Task <id>" section for each
(study_units(), in the order study.json lists them). check_usability() validates these keys:

    target      {"base_url", "allow_remote"}: where the product runs, scheme, host and port
                alone, read by a grammar of its own (target_parts()): http or https, then a
                plain name, an IPv4 address or a bracketed IPv6 address, then an optional
                port, in ASCII, and nothing else. A host a browser would read as another one
                is refused: a backslash, a user name, a number in another notation. The
                address every panellist is given is built again from those parts, lower-cased,
                and is what cfg["target"]["base_url"] then holds. It must be a local
                development host (local_host()): exactly localhost, 127.0.0.1 or [::1], or a
                name ending in .localhost or .test with no punycode label. Any other, another
                way to write this machine included (127.0.0.2, 0.0.0.0, [::ffff:127.0.0.1]),
                needs "allow_remote": true, and then every task says "read_only": true and
                the study has no "accounts": cfg["_remote"] is true, and the instructions tell
                panellists to submit nothing, sign in nowhere and change nothing
    tasks       [{"id", "goal", "start", "steps", "success_check", "read_only"}, ...]. "id" is
                letters and digits, unique ignoring case: it is the section heading, a part of
                each screenshot's name and the "task" of a step-log entry. "goal" is in the
                user's words. "start" is a path on the target (default "/"): one "/" to begin
                with, no "//", no backslash, space or control character, and plain ASCII with
                anything else percent-encoded (START), so that it can name no other host.
                "steps" is the step limit a panellist keeps to (default DEFAULT_STEPS), with
                the launcher as its backstop (launch.py). "success_check" is a lead-only command that says
                whether the task was really completed, by its exit code: 0 yes, 1 no, and
                any other "the check failed to run", which is no verdict (accounts.py). The
                launcher runs it when a run reaches a final state
    accounts    {"provision" | "map", "teardown", "reset", "signin"}, optional (accounts.py).
                "provision" is a command that prints one account for a run, "map" the same
                accounts written out, keyed by run id. An account is {"identifiers": {...},
                "secrets": {...}, "state": "<file>"}: values that may be seen, values that must
                never be, and a saved browser state to start signed in from (account_problem()).
                "teardown" runs when a run reaches a final state, "reset" between the runs of a
                sequential study. "signin" is "session" (the default: the browser session
                starts from the state, and the panellist is given the identifiers alone) or
                "panellist" (signing in is the task under test: the panellist is given the
                secrets to type, and its screenshots are then not safe to keep)
    sequential  true runs one panellist at a time across all runners

A command is split with shell rules and run without a shell, from the study directory, with the
run id as its last argument. Its first word is a file, resolved against the study directory, or
a program on PATH (command_argv()). Whether the file is there is checked when it is needed
(usability_problems(): the scaffold, the plan and every start), so that an archived study loads.

A usability run's time limit, when study.json sets no limits.run.minutes, comes from its tasks:
STEP_SECONDS for each step they permit, plus RUN_MINUTES (usability_minutes()).

The step log, panel/evidence/<run id>/steps.jsonl, has one JSON object per line, two for each
step, written by the panellist (read_steps()):

    {"task", "attempt", "step", "phase": "intent", "sees", "expects", "action"}
    {"task", "attempt", "step", "phase": "result", "happened", "url", "screenshot"}

"step" counts a task's actions on the page from 1. A step is complete when it has both entries.
"url" is the address the action left the browser on, which is how the analysis tells one screen
from another. A result entry has "sensitive": true when its step entered a secret. "attempt" is
1 until a run is cut off part-way through a task: the resume message (runs.py) then gives the
task's next attempt its number, so the steps of an earlier attempt are known as superseded
(step_attempts(), task_steps()). An entry without one reads as attempt 1. The number is the
launcher's to issue: it is on the run's entry in runs.json ("task_attempts", issued_attempts())
before the message is made. An entry that carries a number the launcher did not issue, or that
is not in the form of an entry (no whole step number, a phase that is neither), is left out
before anything is read from the log (counted()): it supersedes no step, and gives a run no
more steps (steps_begun(), the launcher's backstop). The backstop keeps its own count of the
steps a run's process has begun, in runs.json, so nothing a panellist does to its log takes a
step off it, and it stops a run whose log is there and cannot be read as the run's own. It
counts what a log shows and no more: a run that logs no step is bounded by its time limit. A
run that is started afresh, in a new session, starts with an empty evidence folder: what the
folder held is moved to logs/ first. step_notes() says what is wrong with a
log's form. A screenshot is saved beside the log as <task>-<step>.png, or
<task>-a<attempt>-<step>.png from the second attempt on. What a panellist saw of the same page
after scrolling is a further view of the step, named with a letter after the step number
(<task>-<step>b.png, then c): it has no entry in the log, and is evidence like the step's own.
run_evidence() lists what an evidence folder holds. An archived round has it as
evidence/<run id>/ (evidence_dir()), with a note, <screenshot name>.left-out.txt, in place of
each screenshot archive.py left out.

A panellist can write anywhere under panel/, so an evidence folder is read as something another
process may have put there. The evidence root, the run's folder and each file are opened
without following a symbolic link and without waiting, as an open of a FIFO would
(evidence_fd(), open_regular()): a link is never read through, to a file outside the study
least of all, and what is refused is named with the reason (run_evidence() "refused" and
"log_problem"). The step log, the backstop, the scan, check_runs.py, extract_scores.py and
archive.py all read through the same functions.

A persona file is read the same way, in a review study as in a usability study: persona_bytes()
is the one way one is opened, by every script that reads one, and it follows no link, at the
file or at a folder between the study directory and it (open_below(), which archive.py copies
through too), reads a regular file only, and never waits. What stands at a persona file's name
and cannot be read so is no persona file: read_persona() reads it as no file, so its run is not
done and nothing is extracted from it, and check_runs.py blocks, naming the file and the reason
(persona_problem()). What a launcher writes to a persona file, to settle a follow-up, goes
through no link either (write_persona()), nor does a scaffold's (init_study.py).

Secrets. A secret of a test account (a password, a token, a one-time code) may be in no persona
file, step log, analysis file or archive. check_runs.py and archive.py scan for every value any
run of the study was ever given, and teardown takes the values off every record, so they are
known by fingerprint: accounts/fingerprints.json, lead only, mode 0600, never archived:

    salt      hex, made once for the study
    runs      the run ids whose account it has heard of, with or without secrets
    secrets   one {"run", "name", "length", "hash"} for each secret: the name it had in the
              account, how many characters its value has, and the salted BLAKE2b hash of the
              value, null for a value shorter than SECRET_MIN characters, which is not looked for

accounts.py adds to it whenever it writes an account's record (remember_secrets()), and a scan
first adds what is still written out, in accounts.map and in the records in force
(known_secrets()). A scan fingerprints every run of characters of a text that is as long as a
known secret (secrets_in()), so it finds a value wherever it stands, inside a longer word too,
and names the file, the line and whose secret it was, never the value. A file that could not
be scanned is not "nothing found": scan_file() raises, and check_runs.py and archive.py name
the file with the reason and stop for it. Nor does a message repeat a panellist's own text
unchecked: shown() is the one way a task id the study does not have, a label, a file's or a
screenshot's name or a page is quoted in a usability study, and it describes a value that holds
a known secret, is long or has other characters than a name has. shown_path() is the same for
the path of a file or a folder, any part of which may be a panellist's: it is repeated only as
far down as it is clean, and the rest is described. What a scan cannot find: a
value written in another form (broken across two lines, in another case, encoded or partly
masked), a value shorter than SECRET_MIN characters, one of fewer than SECRET_WORD characters
with a letter or a digit against it, anything in a screenshot, and the secrets of an account
that was torn down before the record had heard of it, which the scripts name. The hash is a
fast one, so whoever can read the file can guess a weak password from it: it is kept from
panellists like the records, and teardown is what makes the password worthless.

Interview studies. "type": "interview" is a round of simulated discovery interviews. An
interviewer session talks to each persona in turn, and the launcher carries every message
between the two sessions, so neither side reads or writes a file: a run is an interview, its
panellist is the participant, and what decides that it is done is its turn log, as a persona
file decides it for a review. It has no concepts, tasks, materials, factors or scores, nothing
is captured or browsed, it names no product, and it cannot run in native mode. The unit a run
works through is a topic of the guide (study_units()). check_interview() validates "interview",
the guide, and fills its defaults:

    about           one neutral sentence on the area of work, which the interviewer may state
                    when a participant asks what this is for. It names an area, never an idea
    interviewer     the model entry of every interviewer of the study, as synthesis.analyst is
                    one. There is no default: it names a runner, or the study does. Its "key"
                    is "interviewer" unless it gives one
    goals           [{"id", "learn"}, ...]: what the user wants to find out, each written as a
                    question to settle and never as something to prove. "id" is letters and
                    digits, unique ignoring case
    topics          [{"id", "area", "goals", "turns", "opener", "segments"}, ...], opened in the
                    order written. "id" is as a goal's, and never open, close or end, which an
                    interviewer's reply uses for itself. "area" is a neutral name the
                    interviewer may say to raise the topic, and "opener" its first question,
                    sent as written. "goals" lists the ids of the goals the topic serves
                    (default: none). "turns" caps the topic in exchanges (default
                    DEFAULT_TOPIC_TURNS): the interviewer is told, and nothing enforces it.
                    "segments" keeps the topic to the personas of those segments (default
                    None: every persona gets it)
    turns           the cap of one interview in exchanges, which the launcher enforces (default
                    DEFAULT_TURNS). At least the number of topics plus two: the opening and
                    the close
    situation_card  true (the default): a participant's first reply is its situation card,
                    which is recorded and never passed on. false: it replies "Ready"

An exchange is one question and its answer, and every cap counts exchanges. guide() is the one
reading of the guide for one persona: the topics it gets, with their caps, and the goals those
topics leave it. Two more things are checked only when something is to be written or started
(interview_problems(): the scaffold, the plan and every start), so that an archived study
loads: a "leak_terms" entry in anything the interviewer is given to say, and a persona that
"segments" leaves with no topic. A runner that does not exist is refused where it is looked up,
as in every study (runners.get()).

Its limits are limits.run (each participant, over its whole interview: INTERVIEW_RUN where
study.json gives none), limits.interviewer (each interviewer, the same), limits.turn (minutes
alone: the most one turn of either side may take) and limits.synthesis. synthesis.critic is the
model entry of the jobs that critique the interviewer's questions, and belongs to no other type.

A run is one persona on one model entry and one replicate. Its id is <pid>-<key>, or
<pid>-<key>-r<n> for replicate n > 1, where <key> is the model entry's key (letters and digits).

Model entries. Each item of study.json "models" is a bare model name or an object
{"key", "runner", "model", "effort"}; model_entries() normalises both. "runner" falls back to
the study-level "runner", and a study where no entry has one is in native mode: the lead starts
each run with its own subagent tool. A study is all native or all runners.

runs.json is a list. init_study.py writes one entry per panellist run:

    run        run id, also the prompt file name and the scratch folder
    persona    persona id
    name       persona name
    segment    persona segment, "" when unset
    key        model key: the name used in file names, run ids, limits.overrides and the
               "model" column of scores.csv
    runner     runner name, or null in native mode
    model      model name to launch with, or null for the runner's default model
    effort     thinking effort to launch with, or null
    replicate  1-based replicate number
    role       "panellist"
    file       persona file, relative to the study directory
    prompt     run prompt, relative to the study directory
    workdir    optional: the directory the entry's processes start in, relative to the study
               directory. An entry without one works where its role does (workdir()): panel/
               for a panellist, the study directory for a job. Only an entry of an interview
               has one so far ("Interview entries", below)

launch.py hands an entry to a runner with three keys more, which are never written here:
"browse", whether this attempt may use agent-browser, with it "browser_env", the variables by
which its process reaches the browser session the launcher starts for it, and "tools", "none"
for a process that is to have no tool at all (runners/__init__.py).

Whatever starts runs adds its own fields to an entry. runs.py mark adds "agent", the subagent
id, in native mode. launch.py adds these, and an entry it has never touched has none of them:

    state         pending, running, done, partial, limited, blocked or failed (run_state())
    pid           process id of the CLI of the attempt now running, else null. For show:
                  logs/<run id>.<attempt>.pid is what a launcher goes by. It names the
                  attempt's watchdog too, and is there even when a launcher died before it
                  could note the pid here
    pid_identity  that process's start time as the system reports it, so a process id that
                  was reused is never taken for the run
    session       the harness session id of the current or last attempt, null when unknown
    sessions      {session id: usage}: what each session reported, one record per session
                  (runners.merge_usage). The run's usage is their sum (runners.total_usage)
    attempts      one object per process started: "n" (1-based), "kind" (launch, retry,
                  resume, restart for a fresh launch made by the resume command, or followup
                  for a follow-up question put to a finished run), "started"
                  (epoch seconds), "allowed" (the seconds its watchdog was given: what was
                  left of the run's time), "ended" (epoch seconds, from the watchdog's end
                  record), "seconds", "exit_code" (null when unknown), "outcome" (the
                  runner's: ok, usage_limit, budget or error), "state" (the state it left the
                  run in) and "session". "usage_reported" is there only for an attempt whose
                  process was stopped (time limit or stop) before the harness reported any
                  tokens or cost: false while that spend is in no figure, true once a later
                  result of the same session has brought its running total. False is "not
                  reported", never zero. "end_record": false is there only for an attempt
                  whose watchdog was killed before it wrote one: "ended" is then the latest
                  the process can have run within its limit, and the exit code is unknown.
                  "leftover" ({"group", "pids"}) is there only for such an attempt whose CLI
                  had gone while a process group of its id still had processes: they may be
                  the run's, the launcher could not prove it and left them alone.
                  "stop" is there only for an attempt of a usability run that the launcher
                  asked its watchdog to stop at a task's step limit: {"limit": "steps", "task",
                  "attempt", "step", "of", "at", "grace"}, the intent entry that went past the
                  limit, when the launcher decided and the grace it asked with. It is on
                  record before the request, and is what makes the run "limited". In place
                  of the task, the attempt, the step and the limit it has "unread", the
                  reason, when the run was stopped because its step log could not be read as
                  the run's own.
                  "steps" is there only for an attempt of a usability run: the backstop's own
                  count, which only goes up. "begun" is {task id: the steps of it the
                  process has begun}, as far as the launcher read the log while the process
                  was alive. "seen", there while the attempt runs, is the marks of the
                  log's lines as last read, which start as the lines the log held when the
                  attempt started: the backstop counts what the attempt adds after them.
                  "rewritten" is there when the log stopped holding what had been read of
                  it, cut short or changed at an earlier line: how many times. What the log
                  held from the first changed line on was then counted on top.
                  "evidence_aside" is there only for an attempt that started a usability run
                  afresh over what earlier attempts had left in its evidence folder: where
                  under logs/ that was moved to.
                  "browser_left" ({"found", "left", "kept"}) is there only for an attempt
                  whose watchdog did not stop its browser session, so that a launcher did,
                  or whose session was stopped with something left: whether a session was
                  still running, the pids that could not be ended, and what was left in
                  place, each as "<path>: <why>" (browser_session.py). With "by":
                  "watchdog" when the watchdog stopped it, and with "refused", the reason,
                  when the session's record could not be trusted and nothing was touched.
                  "was" is there only while the attempt runs: the run's state, pid, session,
                  reason, reset_at and task_attempts before it, so that an attempt whose
                  process never ran as the CLI can be taken back.
                  A followup attempt has three more: "followup" (the follow-up's number),
                  "answer" (its outcome, as in followups.json) and "usage" (what the harness
                  reported for this process alone, each figure null when it gave none). It
                  never changes the run's "state", "reason" or "reset_at": while it runs,
                  and until a launcher has settled it, it is the last attempt and its "ended"
                  is null (asking()).
                  "unallocated" is there only for a followup attempt whose result was one
                  total for itself and for an earlier process of the run that had been
                  stopped before reporting: {"input_tokens", "output_tokens",
                  "cached_tokens", "cost_usd"}, what the two used together, and
                  "run_unreported", the figures the run itself had reported none of. Nothing
                  can split it, so it is in neither the run's usage nor the follow-up's: its
                  "usage" has no tokens or cost, and the usage record lists it apart
    seconds_used  wall-clock seconds over every attempt but the followup ones. With the
                  reported spend it counts against the run's limits, which cover all its
                  attempts. A follow-up has an allowance of its own (limits.followup)
    reason        why the run stopped, in a sentence; null while running and when done. For a
                  blocked run it carries the harness's own message, which says whether it was
                  a usage limit, a rate limit or a capacity refusal. In a usability study a
                  harness's message that holds a secret of a test account is not kept: the
                  reason says that it is withheld, and names the files in logs/ that have it
    reset_at      epoch seconds when the limit that blocked the run lifts, when the harness
                  said, else null
    extended      times "resume --extend" gave the run one more allowance of its limits
    limited_by    there only for a run a limit stopped: "time", "budget" or "steps", the last
                  for a usability run that went past a task's step limit. Gone again when the
                  run is continued
    checks        usability only, for a run that reached a final state in a study whose tasks
                  have a "success_check": {task id: {"checked", "exit_code", "at", "error"}},
                  what each task's check said (accounts.py). "checked" is true, false, or null
                  when the check failed to run, with why in "error". Gone again when the run is
                  continued, and made anew when it next finishes. A run resumed with a new
                  account keeps the record of each task it had written up, with "kept": true
                  (launch.py): its account is gone, so its check is not run again
    account       usability only, for a run that has had a test account (accounts.summary()):
                  "provisioned" (epoch seconds), "times" (how often it was provisioned),
                  "source" (provision or map), "signin", "signed_in" (its browser session
                  starts from a saved state), "secrets_given" (its panellist was given a secret
                  to type, in this or an earlier provisioning: its screenshots may show one),
                  "torn_down" (epoch seconds, null while the account is in force) and
                  "teardown_error" (how a teardown failed, else null: the exit code and the
                  lead-only file its output is in, never a word the command wrote)
    task_attempts usability only, for a run that was continued with a task under way: {task
                  id: n}, the attempt the launcher told the run to log that task under
                  (runs.py issue_attempts()). A task it does not name is on attempt 1. An entry
                  of the step log with any other number counts for nothing (counted()). Gone
                  again when the run is started afresh: a new session is on attempt 1 of
                  every task, in a step log that holds nothing else
    released      usability only: epoch seconds when the lead let go of the run's test account
                  with "launch.py release" while the run was unfinished. "run" and "resume"
                  leave such a run alone unless it is named with --released, which takes the
                  mark off and gives it a new account
    purged        {session id: epoch seconds}: the sessions "purge-sessions" deleted from the
                  harness. A purged session cannot be resumed. Its usage stays in "sessions"
    lost          {session id: epoch seconds}: the sessions a resume found gone from the
                  harness. Treated as purged ones are
    unsaved       {session id: epoch seconds}: the sessions that the runner, when their process
                  ended, found its harness had not kept (parse_result() "session_saved" false:
                  a harness that could not write where it keeps sessions). Such a run cannot be
                  resumed or asked a follow-up, and "status" says so. Not noted for a failed
                  run, which "run" starts afresh in a new session

Job entries. launch.py adds one entry per analyst and writer job (synthesis_jobs()) when
"run --role analyst" or "run --role writer" plans them, and rewrites one while its job is
pending or failed. A job is one output file, so its entry has no persona, segment or replicate:

    run        analyst-1, analyst-2 or writer; also the prompt file name
    role       "analyst" or "writer"
    name       what status shows, for example "Analyst 1 of 2"
    key, runner, model, effort   the synthesis.analyst or synthesis.writer model entry. "key" is
               null when the entry gives none
    personas   analyst only: the ids of the personas whose files it reads, in persona id order
    file       its output file, relative to the study directory. The job is done when this file
               exists and is not empty
    prompt     its brief with every placeholder filled, relative to the study directory

It gets the same launcher fields as a panellist run, and one more: "note", a sentence about a
finished job's output that the lead should know (it was taken from the job's reply, or its
process did not end cleanly), else null. Everything that lists panellist runs selects the role
"panellist", so job entries never appear in run tracking, checks, scores or analysis.

Interview entries. In an interview study init_study.py writes two entries for each run: the
participant's (run_entry()), then its interviewer's (interviewer_entry()). Each side has a
session, attempts, usage and limits of its own, and both name one turn log:

    run        the run id | interviewer-<run id> (interviewer_id())
    role       "panellist" | "interviewer"
    interview  the run id, on both: the mark of an entry of a conversation (interview_of()). It
               is there before any attempt, and nothing works it out from the study type
    persona, segment   the participant's, on both
    name       the persona's name | "Interviewer of <run id>"
    replicate  the participant's. Its interviewer has none
    key, runner, model, effort   the model entry | interview.interviewer
    file       interviews/<run id>.jsonl on both: the turn log, which is what decides "done"
    prompt     prompts/<run id>.md, the participant's whole launch prompt |
               prompts/interviewer-<run id>.md, the interviewer's
    workdir    panel/rooms/<run id> | interviewer/<run id>

Everything that lists panellist runs still selects the role "panellist", so an interviewer
never appears in run tracking. Of the launcher's fields above an entry of a conversation gets
"pid", "pid_identity", "session", "sessions", "attempts", "seconds_used", "extended", "purged",
"lost" and "unsaved", each side its own, and one that no other entry has:

    carried    true while a launcher has this conversation in hand, between two turns too, else
               absent: on both entries of an interview, written in one save. It is the one
               fact about a conversation that its turn log cannot hold

It never gets "state", "reason", "reset_at" or "limited_by": the state of a conversation, and
the reason for it, are read from its turn log every time and written nowhere (interview_state()).
Whether a process of it may be alive is asked of its attempts alone (open_attempt()).

Every process of either side is one attempt of kind "turn", its first included. While it runs
the attempt is whole, as above, with "bound": "turn" or "allowance", which of the two limits its
watchdog was given, and "allowed" is that figure. It has no "state": a turn leaves its entry in
none, and what it came to is on the turn log. Once it has ended and its reply is on the turn
log it is cut down to {"n", "kind", "ended", "seconds"}: the log record has the rest, and
logs/<entry id>.<n>.end the exit code. An attempt that ended with no reply on the log (stopped,
timed out, failed, turned away) stays whole, as evidence. So of a settled attempt only "n",
"kind" and "seconds" can be counted on, and "ended" says that it has ended. TURN_KINDS are the
attempt kinds that are one turn of a conversation, and APART_KINDS the ones that leave their
run's state and limits alone.

read_runs() and write_runs() pass fields they don't know through untouched. Entries written
before "key", "runner", "effort", "replicate" and "role" existed read as native-mode panellist
runs: key = model, replicate 1.

Whether a run is finished is decided by its persona file alone: see run_progress(). The state a
launcher records in an entry's "state" says why an unfinished run stopped: see run_state().

The modification record, logs/modifications.json, is how a persona file changed by a run other
than its owner is found. launch.py hashes every panellist's persona file each time it starts a
process, each time one ends, and when a launcher takes over a study, and compares each hash with
the last one recorded:

    hashes     {persona file, relative to the study directory: SHA-256 of its content, or null
               when the file is missing or cannot be read as the run's own}: the last value seen
    changes    one object per change made while the file's own run was not running and other
               processes were: "file", "run" (the owner), "at" (epoch seconds, when the launcher
               saw it) and "running" (the runs and jobs alive since the hash before)

Between two hashings the set of live processes does not change, so a change is laid at the door
of the processes alive then. One made while the owner's process was alive, or in the moments
between its exit and the launcher noticing, counts as the owner's and is not recorded. One made
while nothing was running is the lead's own edit and is not recorded either: only the hash is
brought up to date. check_runs.py reports each entry of "changes" as a blocking problem for its
run; once dealt with, take the entry out of the file. A native-mode study has no record.

Earlier sessions. init_study.py --force replaces runs.json, and with it the only note of the
harness sessions its runs and jobs started. The ones that were not purged or lost are carried
over to logs/earlier-sessions.json, a list that each --force adds to, so "launch.py
purge-sessions" can still delete them. One object per session:

    run        the id of the run or job that started it, in the scaffold that was replaced
    runner     its runner
    session    the harness session id
    workdir    the directory its process worked in, which a runner may need to find the session
    replaced   epoch seconds when --force replaced the scaffold

purge-sessions (without --runs) takes each one out as it deletes it, and removes the file with the
last. A session whose runner cannot delete one stays on record. A native-mode study has none.

Follow-ups. followups.json is a list with one object per question followup.py asked:

    n          the follow-up's number, 1-based and counted over the study. Its answers are the
               "## Follow-up <n>" sections at the end of persona files
    question   the question, as the researcher wrote it
    asked      epoch seconds when it was asked
    mode       "runner": launch.py's supervisor resumed each run's session with it, or "native":
               the lead sent it to each run's subagent by hand
    limits     runner mode: {"minutes", "budget_usd"}, what each run was allowed for it
    runs       one object per run asked: "run", "outcome", "reason" (a sentence, or null),
               "attempt" (the number of the run's attempt that asked, null when no process ran)
               and "session" (the harness session it was sent to; the subagent id in native mode).
               "settling" is there only while a launcher is settling the attempt (below)

"outcome" is one of FOLLOWUP_OUTCOMES, or null while the question is queued, with the panellist,
or not settled yet:

    answered                the panellist appended its section, and nothing else changed
    answered from the reply it replied without writing a section, so the launcher wrote the
                            section from the reply, and says so in it
    rejected                it changed something else in its file: the file was put back as it
                            was, and what it wrote is in logs/<run id>.<attempt>.rejected.md
    unanswered              its process ended with no section and no reply
    turned away             its harness was turning requests away (a usage limit, a rate limit or
                            a capacity refusal)
    could not start         its CLI could not be started, or its session was gone
    not asked               the command stopped, its runner closed or its launcher was killed
                            before its turn came
    sent by hand            native mode: nothing was checked

Settling. When a follow-up attempt's process has ended, a launcher settles it in steps, each on
record before the next, so that a launcher killed between any two leaves a state the next one
brings to the same end:

    1. It decides, changing nothing, and writes the decision to the run's record as "settling":
       {"attempt", "outcome", "reason", "action", "section"}. "action" is what is to be done to
       the persona file: "keep" (nothing), "restore" (put it back from the copy made before the
       question, keeping what a rejected follow-up left in .rejected.md) or "append" (the copy,
       then "section", the section written from the reply).
    2. It does the action. Every write replaces a file in one step and is made from the copy, so
       doing it twice ends the same.
    3. It sets "outcome" and "reason" and takes "settling" out.
    4. It writes the attempt's end to runs.json.
    5. It deletes the copy.

A launcher that finds "settling" for the attempt does not decide again: it starts at step 2. One
that finds the outcome starts at step 4. Every launcher command settles what it finds this way
before anything else, and so does "followup.py list" when no launcher has the study. A record
with no outcome and no attempt in flight is one whose launcher was killed while the run was
queued: it becomes "not asked".

The snapshot rule. From the moment a follow-up attempt is in runs.json until its end is (step 4),
the persona file may hold what settling will reject. Until then nothing reads the file for
scores, answers, lines, checks or progress: read_persona() reads the copy made before the
question, logs/<run id>.<attempt>.before, and every reader goes through it (load_runs(),
run_records(), launch.py and runs.py). The copy is the launcher's own, and is made and opened as
the other files an attempt keeps in logs/ are (keep_copy(), read_copy(): run_watchdog.py,
fresh() and opened()). A script that read a copy says so in one line per run
(unsettled_lines()). An archive has no logs/, so there the file itself is read, and archive.py
refuses a study with a follow-up that is not settled.

The rule rests on the order a launcher keeps. To ask: the copy is written, then the attempt is
saved in runs.json, and only then is the process started, so the file cannot change before both
are there. To settle: the file is put right (step 2) before the attempt's end is saved (step 4),
and the copy goes last. A reader holds no lock, and the runs.json entry it goes by may be older
than the file it then reads. So read_persona() does not trust the entry it is handed: after
reading it looks the run's attempts up in runs.json again, and chooses and reads again when they
have changed, until two looks one after the other agree. When they never do, it returns a copy
still on disk, or with none refuses the read by exiting: content read from the file between
looks that disagree is never returned. A launcher's own reads cannot come to that, since under
the study lock nothing else writes an attempt to runs.json. What copies files out of a study
(archive.py) cannot read around a launcher that way, so it takes the study lock instead.

A follow-up never changes a score: follow-up sections come after everything parse_persona_file()
reads for scores, rankings, answers and lines, and it lists them apart, under "followups". They
are qualitative evidence only, and no script tallies them.

The turn log. interviews/<run id>.jsonl is the only record of an interview and of why it
stopped: UTF-8, one JSON object a line, append only, written by a launcher that holds the study
lock and by nothing else. append_turns() writes all the records of one settlement in a single
write and syncs it. A settlement is on the log whole or not at all, to every reader: each of its
records but the last carries "more": true, which says that the settlement goes on with the next
line, and a log that ends in records so marked, or in a line with no line break, ends in what a
killed writer left. read_turns() reads a log, [] for none, and leaves that unfinished end out
(turn_torn() says whether there is one), and append_turns() cuts it off before it writes. So a
turn whose "lost" record reached the disk without its "halt" reads as not settled, and the next
launcher settles it again, both records, from its files in logs/. A line that is no JSON object
is read as {"t": "unread", "line": its text}, which belongs to no reading of the log and which
turn_problems() names, and so is a record that is not as a launcher writes one ("A malformed
log", below). A log is never rewritten: a fresh start moves it to logs/, where it is
no interview of the study any more (init_study.py --force moves every one, to
logs/interviews-<epoch seconds>/, and a launcher that starts one interview afresh for want of
a session moves that one, to logs/<run id>.interview-<k>.jsonl). A launcher appends to the log
first and saves runs.json second, so the log is never behind.

Every record has "t", its type (TURN_TYPES), and "at", epoch seconds to three decimals. One made
from a process also has "side" (SIDES), "attempt", that side's attempt number, and "seconds",
and one that is not the last of its settlement "more": true, which no reading of the log uses.
An append is skipped when the log already has a record of that side and attempt, so a launcher
that died between the log and runs.json records nothing twice. A record that was set aside as
malformed (below) counts for that, and for nothing else, by the side and attempt its object
holds: an attempt that is on the log in any form is never added to it again.

    start        the first line: "v": 1, "kind" ("interview", or "debrief" for an interview
                 held in the session of a finished review or usability run) and "run". Also
                 "extended", {side: allowances given before this log began}, on a log that
                 begins again for a conversation whose side had been given one (a fresh start).
                 One that the command which began the log gave is counted there too
    card         the participant's first reply, with the situation card on: "text"
    ready        the same with it off: "text"
    question     an interviewer's reply that parsed and passed the leak gate, which is
                 delivered next: "n", "topic" (a topic id, "open" or "close"), "move", "why"
                 and "say", the only part the participant receives. "topic" is the topic the
                 question counts for, which its words decide where they hold the opener of a
                 topic not yet opened (interview.opened_by()). "labelled" is there only then,
                 and only when the interviewer wrote another TOPIC: what it wrote
    answer       the participant's reply to question n: "n", "text"
    rejected     an interviewer's reply that is not used: "problems", a list of [key, detail]
                 (format, missing, topic, move, say, leak, last-exchange), and "reply", the
                 text as received
    end-offered  the interviewer ended while topics were unopened and exchanges remained, the
                 first time: "reason", "say", "unopened". It is asked once whether it means it
    end          the interview is over: "by" ("interviewer" or "cap"), "reason", "say",
                 "exchanges", "unopened", "close" (whether the last exchange was a close) and
                 "short": true when a cap ended it one exchange short. "side" and "attempt"
                 only when the interviewer ended it
    lost         an attempt ran as the CLI and left no usable reply: "why" (empty, role, stop,
                 time, limit, budget, usage_limit, error or killed), and with "role", a
                 participant's first reply that is neither a card nor "Ready", "reply". Also
                 "reason", what its harness said of the ending, when it said anything
    halt         the interview cannot go on without the lead: "state" (limited, blocked or
                 failed), "side", "reason", and "reset_at" or "limited_by" when known
    resume       a command took the interview up again: "by" (run, resume or debrief) and
                 "extended", the side given one more allowance, when one was. That record is
                 the grant: a side's allowances are one, and one more for each "resume" record
                 that names it so (extensions()), and the "extended" on its runs.json entry is
                 a copy the launcher brings level with the log before it queues a turn

An exchange is question n and answer n, counted from 1: one number, for the transcripts, the
caps and the analysts' notes. turn_problems() lists what is wrong with a log's form, and
check_runs.py blocks on each. First, every record is of a known type and has the fields a
launcher always writes for that type, each of the kind it writes (TURN_FIELDS, turn_lacking()),
and nothing of another kind in a field a launcher writes only sometimes (TURN_SOMETIMES): a log
with a record that does not is named for that and read no further, since every other reading
of it counts on those fields. "unread" is no type of a record. It is what a reader calls a line
it set aside, so a line of a log that calls itself that is of no known type, like any other no
launcher writes, whatever it holds under "record". Then: it starts with "start", its questions
and answers alternate with no number skipped or repeated, an interview has one card or "Ready"
before its first question (a debrief has none), nothing follows the one "end", whose
"exchanges" is the number of answers, and no two records share a side and attempt. An
unfinished end is no problem of form: it is left out before the log is read, and check_runs.py
notes it by turn_torn().

A malformed log is one with a record that turn_lacking() names: changed by hand or damaged,
since append_turns() writes no such record. It is recognised in one place, read_turns(), which
judges each line as the object it holds (_unlike()) and gives each such record as "unread" with
that object under "record": always the object of the line itself, and never one that was found
inside it and trusted. So every reader is given the well-formed records alone, and nothing
that is worked out from a log fails on a damaged one: interview_state(), interview_progress(),
extensions() and interview.fold() pass an "unread" record over as they pass over any type they
do not know. What they then say is what the rest of the log says, which is no account of the
interview, so each place that acts on a log asks turn_lacking() first: check_runs.py blocks on
it and names the record, "status" and the plan give it as what stands in the interview's way
(interview.standing()), and "run" and "resume" leave the interview alone and say what to do,
which is to put the log right or to move it into logs/ and hold the interview again.

interview_state() reads a conversation's state from its log and whether a launcher carries it,
first match first: "done" with an "end" record; "running" while it is carried; the state of the
last "halt" when no "resume" follows it; "partial" with a card, a "Ready", a question or an
answer on record; else "pending". Both entries of an interview ask with the same log and the
same "carried", so they never disagree.

"carried" on an entry says that a launcher took the conversation up and has not put it down,
and a launcher that was killed never took it off. So it counts only while a launcher holds the
study, and one rule decides that for every reader, carried(): a launcher asks with the study
in its own hands, and every other reader of a state (status, the plan, the usage record,
check_runs.py) is told by its caller whether the study lock is held, and reads a conversation
left carried by a dead launcher as its log reads with no launcher: partial, next "resume", or
pending with no turn on record. interview_progress() gives the same log the shape
run_progress() gives a persona file, and run_records() reads an interview study through both.
"""

from __future__ import annotations

import errno
import fcntl
import fnmatch
import hashlib
import io
import ipaddress
import json
import math
import os
import random
import re
import shlex
import statistics
import shutil
import stat
import string
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from run_watchdog import Unsafe, fresh, opened  # Unsafe: a file that is not read, a link or no regular file

SKILL_DIR = Path(__file__).resolve().parents[1]
ASSETS = SKILL_DIR / "assets"

DEFAULT_FACTORS = [
    {"key": "first", "label": "First impression", "short": "First",
     "question": "After 5 seconds, do I know what this is, who it's for and what it does for me?"},
    {"key": "relevance", "label": "Relevance to me", "short": "Relevance",
     "question": "Does this feel built for someone in my role and my kind of business?"},
    {"key": "problem", "label": "Problem recognition", "short": "Problem",
     "question": "Does it name problems I actually have, in words I'd use?"},
    {"key": "how", "label": "How it works", "short": "How",
     "question": "Do I understand how it would work in my business, day to day?"},
    {"key": "why_care", "label": "Why care", "short": "Why care",
     "question": "Is the benefit to me clear and big enough to act on?"},
    {"key": "trust", "label": "Trust", "short": "Trust",
     "question": "Do I believe it? Think risk, my brand, my clients' data, and the vendor itself."},
    {"key": "visual", "label": "Visual design", "short": "Visual", "needs_design": True,
     "question": "Does it look professional, calm and credible, or busy, gimmicky or cheap?"},
    {"key": "structure", "label": "Structure and flow", "short": "Structure",
     "question": "Is it easy to scan and follow, the right length, with things where I expect them?"},
    {"key": "mobile", "label": "Mobile", "short": "Mobile", "needs_design": True,
     "question": "Judged from the phone screens: would it work if I opened it on my phone?"},
    {"key": "next_step", "label": "Next step", "short": "Next step",
     "question": "How likely am I to book a demo, sign up or pass it on?"},
    {"key": "overall", "label": "Overall", "short": "Overall",
     "question": "Your overall verdict. It doesn't have to be the average of the other scores."},
]

# The factors a usability study scores for each task, unless study.json gives its own.
USABILITY_FACTORS = [
    {"key": "success", "label": "Task success", "short": "Success",
     "question": "Did I get done what I set out to do? 10 is completely, 1 is not at all."},
    {"key": "ease", "label": "Ease", "short": "Ease",
     "question": "How little effort did it take, from the first screen to the last?"},
    {"key": "confidence", "label": "Confidence", "short": "Confidence",
     "question": "How sure am I that what I did was right, and that it went through?"},
    {"key": "clarity", "label": "Clarity of next step", "short": "Next step",
     "question": "At each screen, did I know what to do next without guessing?"},
    {"key": "trust", "label": "Trust", "short": "Trust",
     "question": "After doing this, would I trust the product with my real details and decisions?"},
    {"key": "overall", "label": "Overall", "short": "Overall",
     "question": "My overall verdict on doing this task here. It doesn't have to be the average of the other "
                 "scores."},
]

DEFAULT_FIT_FACTORS = ["relevance", "why_care", "next_step"]
# The factors that cannot be judged without seeing the page. A factor in study.json says so with
# "needs_design": true, and one that reuses a key below needs it unless it says false.
DESIGN_FACTORS = tuple(f["key"] for f in DEFAULT_FACTORS if f.get("needs_design"))
DASHES = ("\u2013", "\u2014")
FINAL_MARKER = "## Out of character"

# Study type -> the unit a run works through: its nouns, and its section heading in a persona file,
# None for an interview study, which has no persona file.
STUDY_TYPES = {
    "review": {"unit": "concept", "units": "concepts", "heading": "Concept"},
    "usability": {"unit": "task", "units": "tasks", "heading": "Task"},
    "interview": {"unit": "topic", "units": "topics", "heading": None},
}
# What only one type of study has in study.json. A key of another type is refused, not ignored.
REVIEW_KEYS = ("concepts", "labels", "label_style", "shuffle_labels", "find_the_answer", "artefact",
               "artefact_plural", "arrival", "copy_ignore", "extra_yes_bullets")
USABILITY_KEYS = ("target", "tasks", "accounts", "sequential")
INTERVIEW_KEYS = ("interview",)
TYPE_KEYS = {"review": REVIEW_KEYS, "usability": USABILITY_KEYS, "interview": INTERVIEW_KEYS}
# What a study of one type is told to do about a key of another: [this type, the key's type], as
# the end of check_type_keys()'s sentence, with {it} for "it" or "them".
TYPE_HINT = {
    ("review", "usability"): '. Set "type": "usability" (it then has "tasks" and no "concepts"), or take {it} out',
    ("usability", "review"): (": it has tasks and no concepts, nothing is captured, and tasks are attempted in the "
                              "order written. Take {it} out"),
    ("review", "interview"): '. Set "type": "interview" (it then has a guide and no "concepts"), or take {it} out',
    ("usability", "interview"): '. Set "type": "interview" (it then has a guide and no "tasks"), or take {it} out',
    ("interview", "review"): ": nothing is reviewed, attempted, captured or scored. Take {it} out",
    ("interview", "usability"): ": nothing is reviewed, attempted, captured or scored. Take {it} out",
}
# What the other two types share and an interview study cannot have: refused there, not ignored.
NOT_INTERVIEW = ("materials", "browse", "capture", "factors", "fit_factors", "model_notes", "product",
                 "product_phrase", "debrief")
GUIDE_KEYS = ("about", "interviewer", "goals", "topics", "turns", "situation_card")  # of "interview", the guide
DEBRIEF_KEYS = ("interviewer", "goals", "topics", "turns")  # of "debrief", the guide of a debrief
GOAL_FIELDS, TOPIC_FIELDS = ("id", "learn"), ("id", "area", "goals", "turns", "opener", "segments")
GUIDE_ID = re.compile(r"[A-Za-z0-9]+")  # a goal or topic id. A topic id is none of NOT_TOPIC, in any case
NOT_TOPIC = ("open", "close", "end")    # what an interviewer's reply writes where a topic id goes, or to end
DEFAULT_TURNS = 30       # the cap of an interview that names none, in exchanges
DEFAULT_TOPIC_TURNS = 8  # the cap of a topic that names none
SIDES = ("participant", "interviewer")  # the two sides of a conversation, as a turn log names them
TURN_KINDS = ("turn", "debrief")        # attempt kinds that are one turn of a conversation
APART_KINDS = ("followup", "debrief")   # attempt kinds that leave their run's state and limits alone
INTERVIEWS = "interviews"               # the turn logs and transcripts, relative to the study directory
ROOMS = "panel/rooms"                   # a folder for each participant, <run id>, relative to it too
INTERVIEWER_DIR = "interviewer"         # a folder for each interviewer, <run id>
TRANSCRIPTS = "analysis/transcripts"    # the analysts' copies of the transcripts
# The record types of a turn log (module docstring, "The turn log"), and the ones made from a reply.
TURN_TYPES = ("start", "card", "ready", "question", "answer", "rejected", "end-offered", "end", "lost", "halt",
              "resume")
SPOKEN = ("card", "ready", "question", "answer")  # with one of these on record an interview has begun
HALTS = ("limited", "blocked", "failed")          # the states a "halt" record can give an interview
# The fields of a record of each type, beside "t" and "at", each with the kind of value a launcher writes
# there (_of_kind()): a type, a tuple of types for any of them, [kind] for a list of such values, [kind, kind]
# for a list of exactly those, and {kind: kind} for an object of such keys and values. TURN_FIELDS has the
# fields it always writes, and TURN_SOMETIMES the ones it writes only sometimes, on a record of any type ("")
# or of one: a record may leave those out, and may not hold another kind of value there (turn_lacking()).
_SPOKE = {"side": str, "attempt": int}
_NUMBER = (int, float)
TURN_FIELDS = {
    "start": {"v": int, "kind": str, "run": str},
    "card": {**_SPOKE, "text": str}, "ready": {**_SPOKE, "text": str},
    "question": {**_SPOKE, "n": int, "topic": str, "move": str, "why": str, "say": str},
    "answer": {**_SPOKE, "n": int, "text": str},
    "rejected": {**_SPOKE, "problems": [[str, str]], "reply": str},
    "end-offered": {**_SPOKE, "reason": str, "say": str, "unopened": [str]},
    "end": {"by": str, "reason": str, "say": str, "exchanges": int, "unopened": [str], "close": bool},
    "lost": {**_SPOKE, "why": str},
    "halt": {"state": str, "side": str, "reason": str},
    "resume": {"by": str}}
TURN_SOMETIMES = {
    "": {**_SPOKE, "seconds": _NUMBER, "more": bool},  # "side" and "attempt": of an "end" by its interviewer
    "start": {"extended": {str: int}}, "question": {"labelled": str}, "end": {"short": bool},
    "lost": {"reason": str, "reply": str}, "halt": {"limited_by": str, "reset_at": _NUMBER},
    "resume": {"extended": str}}
TASK_ID = re.compile(r"[A-Za-z0-9]+")  # a task id: what the parsers read after "Task", and part of a file name
TASK_FIELDS = ("id", "goal", "start", "steps", "success_check", "read_only")
ACCOUNT_FIELDS = ("provision", "map", "teardown", "reset", "signin")
ACCOUNT_COMMANDS = ("provision", "teardown", "reset")
ACCOUNT_PARTS = ("identifiers", "secrets", "state")  # of one account: what "provision" prints, or a "map" entry
SIGNIN = ("session", "panellist")  # who signs in: the browser session, from a saved state, or the panellist
LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]")  # with LOCAL_ENDINGS, the local development hosts: local_host()
LOCAL_ENDINGS = (".localhost", ".test")
LOCAL_RULE = "localhost, 127.0.0.1, [::1], or a name ending in .localhost or .test"
# What a target.base_url may be, and nothing else: target_parts() reads the host. ASCII only, so
# that no letter here is one a browser would fold into another.
TARGET = re.compile(r"(?P<scheme>[A-Za-z]+)://(?P<host>\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9.-]+)(?::(?P<port>[0-9]+))?/?")
HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
HOST_NUMBER = re.compile(r"[0-9]+|0x[0-9a-f]*")  # a last label that makes a browser read the host as an IPv4 address
IPV4 = re.compile(r"(?:0|[1-9][0-9]{0,2})(?:\.(?:0|[1-9][0-9]{0,2})){3}")
# A task's "start": a path on the target, with a query or a fragment when the task needs one.
START = re.compile(r"/(?:[A-Za-z0-9._~!$&'()*+,;=:@/?#-]|%[0-9A-Fa-f]{2})*")
DEFAULT_STEPS = 25    # the step limit of a task that names none
STEP_SECONDS = 30     # the time rule of a usability run: this for each step its tasks permit,
RUN_MINUTES = 5       # plus this for reading the instructions and writing the persona file
# How a task section states what became of the task: its "Outcome" field opens with one of these.
OUTCOME_LABEL = "Outcome"
USABILITY_OUTCOMES = ("completed", "gave up", "ran out of steps")
EVIDENCE = "panel/evidence"  # the step logs and screenshots of a usability study, one folder per run
STEP_LOG = "steps.jsonl"     # a run's step log, in its evidence folder
STEP_PHASES = ("intent", "result")  # the two entries of a step
READ_MOST = 64 << 20         # bytes a file read whole for a scan or as evidence may hold: a larger one is not read
MATERIALS = ("full", "text")
KINDS = ("site", "url", "files")
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
DOCUMENT_TYPES = (".pdf",)
PAGE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")  # a url page's name or a state's, which becomes a folder name
LABEL = re.compile(r"[A-Za-z0-9]+")  # a pinned label: what the parsers read after "Concept", and a folder name
NAME_PART = re.compile(r"[^\s./\\-][^/\\\x00-\x1f\x7f]*")  # one part of a file name: name_problem()
NAME_RULE = ("must be one part of a file name: no slash, backslash or line break, and no dot, hyphen or space to "
             "begin with")
FILE_FORMS = ("image files", "PDF files", "image and PDF files")  # the forms of a "files" concept
DEFAULT_ARTEFACT = ("draft website design", "draft website designs")  # singular, plural
ENTRY_FIELDS = ("key", "runner", "model", "effort")
KEY_RE = re.compile(r"[A-Za-z0-9]+")
LIMIT_NAMES = ("minutes", "budget_usd")
DEFAULT_LIMITS = {
    "run": {"minutes": 15, "budget_usd": 2.0},        # each panellist run, over all its attempts
    "synthesis": {"minutes": 30, "budget_usd": 5.0},  # analyst and writer jobs
    "followup": {"minutes": 5, "budget_usd": 0.5},    # each run asked a follow-up, for each question
    "interviewer": {"minutes": 15, "budget_usd": 1.0},  # each interviewer, over its whole interview
    "turn": {"minutes": 3},                           # one turn of either side of a conversation
    "debrief": {"minutes": 15, "budget_usd": 1.5},    # each side of a debrief: a placeholder, not yet measured
}
# limits.run of an interview's participant, where study.json gives none. With the interviewer's and
# the turn limit above it is what interviews measured on 13 October 2026 leave room for: the slowest
# of 921 processes took 31 seconds, the longest side used 280 seconds of its own process time, and
# the dearest cost 0.30 USD. Minutes count a side's own process time, never the time since the
# interview began.
INTERVIEW_RUN = {"minutes": 15, "budget_usd": 0.5}
# The limits a study of each type may set, each beside "overrides". Any other is refused.
LIMIT_SETS = {"review": ("run", "synthesis", "followup", "debrief"),
              "usability": ("run", "synthesis", "followup", "debrief"),
              "interview": ("run", "interviewer", "turn", "synthesis")}
RUN_DEFAULTS = {"runner": None, "effort": None, "replicate": 1, "role": "panellist"}
JOB_ROLES = ("analyst", "writer")
SYNTHESIS_KEYS = ("analysts", "analyst", "writer", "decision_maker", "context_files", "critic")
DEFAULT_DECISION_MAKER = "the decision-maker"
MODIFICATIONS = "logs/modifications.json"  # the modification record, relative to the study directory
EARLIER_SESSIONS = "logs/earlier-sessions.json"  # sessions of the runs a --force replaced, relative to it too
STUDY_BRIEF = "study-brief.md"             # the lead's copy of assets/study-brief.md, beside study.json
FOLLOWUPS = "followups.json"               # the follow-up questions asked, relative to the study directory
FORMS = "forms.json"                       # the form of each "files" concept, relative to it too
FOLLOWUP_OUTCOMES = ("answered", "answered from the reply", "rejected", "unanswered", "turned away",
                     "could not start", "not asked", "sent by hand")
FOLLOWUP_ANSWERED = FOLLOWUP_OUTCOMES[:2]  # the outcomes that leave a section the launcher has checked
FOLLOWUP_HEADING = re.compile(r"^## Follow-up (\d+)\s*$")
FROM_REPLY = "(Taken from the panellist's reply by the launcher: the panellist did not write this section itself.)"
PLACEHOLDER = re.compile(r"<([A-Z][A-Z0-9_]*)>")
# The synthetic panel notice: the one line every persona file, synthesis, report and archive README
# carries, so that a file read on its own is never taken for research with real people. with_notice()
# adds it, and a brief asks for it with <NOTICE>.
NOTICE = ("Synthetic panel: the feedback in this study was generated by AI personas, not by real people. "
          "It is not user research.")
# The name roster.py gives a skeleton persona. init_study.py refuses a study that still has one.
SKELETON_NAME = "TODO"
# What every script says after a refusal that a sandboxed shell tool can cause: the two ways out.
SANDBOX_HINT = ("If your shell tool is sandboxed, ask your harness to run this command outside its sandbox, or run "
                "launch.py from a terminal.")


# ---------------------------------------------------------------- wording

def agree(n: int, one: str, many: str | None = None) -> str:
    """The word that agrees with a count of n: one for exactly 1, else many, which is one + "s"
    when it is not given. Every sentence a script writes around a count takes its nouns, verbs
    and pronouns from here ("is" or "are", "it" or "them"), so none says "1 runs"."""
    return one if n == 1 else one + "s" if many is None else many


def plural(n: int, noun: str, many: str | None = None) -> str:
    """A count with its noun: "1 run", "2 runs", "1,200 pages", "2 model entries"."""
    return f"{n:,} {agree(n, noun, many)}"


# ---------------------------------------------------------------- config

def load_study(study_dir: Path) -> dict:
    study_dir = Path(study_dir).resolve()
    try:
        cfg = json.loads((study_dir / "study.json").read_text())
    except OSError as err:
        raise SystemExit(f"Cannot read {study_dir / 'study.json'} ({err.strerror}). Pass the study directory, the "
                         "one that holds study.json.")
    except ValueError as err:
        raise SystemExit(f"{study_dir / 'study.json'} is not valid JSON: {err}")
    if not isinstance(cfg, dict):
        raise SystemExit(f"{study_dir / 'study.json'} must hold one JSON object")
    given = frozenset(cfg)  # the keys study.json itself has, before any default
    interview = cfg.get("type") == "interview"  # nothing is scored, reviewed or browsed in one
    cfg.setdefault("factors", [] if interview else USABILITY_FACTORS if cfg.get("type") == "usability"
                   else DEFAULT_FACTORS)
    cfg.setdefault("fit_factors", [f for f in DEFAULT_FIT_FACTORS if f in {x["key"] for x in cfg["factors"]}])
    cfg.setdefault("models", ["opus", "fable"])
    cfg.setdefault("seed", 1)
    cfg.setdefault("label_style", "letters")
    cfg.setdefault("shuffle_labels", True)
    cfg.setdefault("leak_terms", [])
    cfg.setdefault("find_the_answer", [])
    cfg.setdefault("context_notes", [])
    cfg.setdefault("segments", {})
    cfg.setdefault("type", "review")
    cfg.setdefault("materials", "full")
    cfg.setdefault("replicates", 1)
    cfg.setdefault("runner", None)
    asked_to_browse = cfg.get("browse") is True  # said in study.json, which a text-only study overrides
    cfg.setdefault("browse", True)
    # The singular is known only for the default plural: a study of one concept that names its
    # own "artefact_plural" names "artefact" too (init_study.py refuses it otherwise).
    cfg.setdefault("artefact", None if "artefact_plural" in cfg else DEFAULT_ARTEFACT[0])
    cfg.setdefault("artefact_plural", DEFAULT_ARTEFACT[1])
    for k in ("limits", "runners", "synthesis"):
        cfg.setdefault(k, {})
    cfg.setdefault("concepts", [])
    cfg["_dir"], cfg["_given"] = study_dir, given
    check_study(cfg)
    if interview:  # it has no materials or concept kinds to apply, and no factor that must come last
        cfg["browse"], cfg["_text_only"], cfg["_browse_off"] = False, None, None
        return cfg
    apply_materials(cfg, asked_to_browse)
    apply_kinds(cfg, asked_to_browse)

    def resolved(path):
        p = Path(path).expanduser()
        return (p if p.is_absolute() else study_dir / p).resolve()

    for c in cfg["concepts"]:
        if "path" in c:
            c["_path"] = resolved(c["path"])
        if "files" in c:
            c["_files"] = [resolved(f) for f in c["files"]]
    if cfg["factors"][-1]["key"] != "overall":
        raise SystemExit("study.json: the last factor must be 'overall'")
    return cfg


def _fail(msg: str):
    raise SystemExit(f"study.json: {msg}")


def _positive(x, whole: bool = False) -> bool:
    return isinstance(x, int if whole else (int, float)) and not isinstance(x, bool) and x > 0


def check_study(cfg: dict):
    """Validate the shape of the optional keys. Whether a runner exists is the launcher's check."""
    if cfg["type"] not in STUDY_TYPES:
        _fail(f'unknown "type" {cfg["type"]!r} (use {listed(list(STUDY_TYPES), "or")})')
    check_type_keys(cfg)
    if cfg["materials"] not in MATERIALS:
        _fail(f'unknown "materials" {cfg["materials"]!r} (use {" or ".join(MATERIALS)})')
    if not _positive(cfg["replicates"], whole=True):
        _fail('"replicates" must be a whole number, 1 or more')
    if cfg["runner"] is not None and not (isinstance(cfg["runner"], str) and cfg["runner"]):
        _fail('"runner" must be a runner name')
    if not isinstance(cfg["browse"], bool):
        _fail('"browse" must be true or false: whether panellists may open pages with agent-browser')
    for key in ("artefact", "artefact_plural"):
        if cfg[key] is not None and not (isinstance(cfg[key], str) and cfg[key].strip()):
            _fail(f'"{key}" must be a few words for what is reviewed, such as "{DEFAULT_ARTEFACT[key == "artefact_plural"]}"')
    if cfg["type"] == "review" and not cfg["concepts"]:
        _fail("a review study needs at least one concept")
    check_concepts(cfg)
    check_personas(cfg)
    check_capture(cfg)
    keys = model_keys(cfg)
    if cfg["type"] == "usability":
        check_usability(cfg)
    if cfg["type"] == "interview":
        check_interview(cfg)

    limits, allowed = cfg["limits"], LIMIT_SETS[cfg["type"]]
    if not isinstance(limits, dict) or set(limits) - {*allowed, "overrides"}:
        _fail(f'"limits" must be an object with any of {", ".join(allowed)} and overrides')
    sets = {f"limits.{k}": limits[k] for k in allowed if k in limits}
    overrides = limits.get("overrides", {})
    if not isinstance(overrides, dict):
        _fail("limits.overrides must be an object keyed by model key")
    for k, v in overrides.items():
        if k not in keys:
            _fail(f'limits.overrides: "{k}" is not a model key (keys: {", ".join(keys)})')
        sets[f"limits.overrides.{k}"] = v
    for where, d in sets.items():
        names = DEFAULT_LIMITS["turn"] if where == "limits.turn" else LIMIT_NAMES  # a turn has a time limit alone
        if not isinstance(d, dict) or set(d) - set(names):
            _fail(f"{where} must be an object with {'any of ' if len(names) > 1 else ''}{' and '.join(names)}")
        for name, v in d.items():
            if not _positive(v):
                _fail(f"{where}.{name} must be a positive number")

    if not isinstance(cfg["runners"], dict):
        _fail('"runners" must be an object keyed by runner name')
    for name, opts in cfg["runners"].items():
        if not isinstance(opts, dict):
            _fail(f"runners.{name} must be an object")
        if "concurrency" in opts and not _positive(opts["concurrency"], whole=True):
            _fail(f"runners.{name}.concurrency must be a whole number, 1 or more")

    syn = cfg["synthesis"]
    if not isinstance(syn, dict) or set(syn) - set(SYNTHESIS_KEYS):
        _fail(f'"synthesis" must be an object with any of {", ".join(SYNTHESIS_KEYS)}')
    if syn.get("analysts", 1) not in (1, 2) or isinstance(syn.get("analysts"), bool):
        _fail("synthesis.analysts must be 1 or 2")
    if "critic" in syn and cfg["type"] != "interview":
        _fail(f'synthesis.critic belongs to an interview study, and this is {a_type(cfg["type"])} study: it is the '
              "model entry of the jobs that critique an interviewer's questions. Take it out")
    for job in (*JOB_ROLES, "critic"):
        if job in syn:
            model_entry(syn[job], cfg["runner"], f"synthesis.{job}")
    who = syn.get("decision_maker", DEFAULT_DECISION_MAKER)
    if not (isinstance(who, str) and who.strip()):
        _fail("synthesis.decision_maker must be a non-empty string: who the synthesis is written for")
    files = syn.get("context_files", [])
    if not isinstance(files, list) or not all(isinstance(f, str) and f for f in files):
        _fail("synthesis.context_files must be a list of file paths")
    for f in files:
        if Path(f).is_absolute() or ".." in Path(f).parts:
            _fail(f'synthesis.context_files: "{f}" must be a path inside the study directory, written relative '
                  "to it, because an analyst can read nothing outside it")
        if study_brief_copy(cfg["_dir"], [cfg["_dir"] / f]):
            _fail(f'synthesis.context_files: "{f}" is the study brief, or a copy of it. The brief holds the '
                  "team's hypotheses, and an analyst or writer that has read them tends to find them. Take it "
                  "out, and put what the jobs need (the decisions and constraints that apply now) in a file of "
                  "its own")
    variants(cfg)


def name_problem(name) -> str | None:
    """Why a configured string cannot be one part of a file or folder name, else None. It names a
    file or a folder, so it must stay in the folder it is put in: a string with no slash, no
    backslash and no control character, that does not begin with a dot (".." is the folder above)
    or with a hyphen (a tool given the name would read an option), and with no space at either
    end."""
    return None if isinstance(name, str) and NAME_PART.fullmatch(name) and name == name.strip() else NAME_RULE


def persona_id_problem(pid) -> str | None:
    """Why a string cannot be a persona id, else None, as the end of a sentence about it. An id
    names the persona's files, so it is one part of a file name (name_problem()), and it holds no
    hyphen: a persona file is <id>-<slug>--<key>.md and a run id <id>-<key>, and both are read
    back by their first hyphen (FILE_RE). The one rule for study.json and for a roster file."""
    if name_problem(pid):
        return f"{NAME_RULE}, because it names the persona's files"
    if "-" in pid:
        return ("cannot hold a hyphen, because the persona file is named <id>-<slug>--<key>.md and is read back by "
                "its first hyphen")
    return None


def check_personas(cfg: dict):
    """Validate what of each persona names files: its id (the persona file, the run prompt, the
    scratch folder and the logs are named after it) and its slug, given as "slug" or made from
    its name. Two personas with one id would write the same files, each over the other's."""
    people = cfg.get("personas") or []
    if not isinstance(people, list) or not all(isinstance(p, dict) for p in people):
        _fail('"personas" must be a list of objects')
    seen = set()
    for p in people:
        pid = p.get("id")
        if persona_id_problem(pid):
            _fail(f"the persona id {json.dumps(pid)} {persona_id_problem(pid)}")
        if pid.lower() in seen:
            _fail(f'two personas have the id "{pid}". Ids must be unique, ignoring case, because they name files')
        seen.add(pid.lower())
        if p.get("slug") and name_problem(p["slug"]):
            _fail(f'persona {pid}: its "slug" {json.dumps(p["slug"])} {name_problem(p["slug"])}, because it is '
                  "part of the persona file's name")
        name = p.get("name")  # a skeleton, with no name yet, is init_study.py's to refuse
        if not p.get("slug") and isinstance(name, str) and name.strip() and not slugify(name):
            _fail(f"persona {pid}: its name {json.dumps(name, ensure_ascii=False)} has no letter from a to z and no "
                  'digit to make its file name from. Give it a "slug" of such letters, digits and hyphens, for '
                  'example "slug": "persona-one"')


def check_capture(cfg: dict):
    """Validate study.json "capture": its values are sizes and counts that capture.py hands to the
    browser, ImageMagick and Poppler as arguments, so each must be the number or the words it
    stands for."""
    cap = cfg.get("capture", {})
    if not isinstance(cap, dict):
        _fail('"capture" must be an object')
    for key in ("max_screens", "max_pdf_pages", "pdf_pixels"):
        if key in cap and not _positive(cap[key], whole=True):
            _fail(f"capture.{key} must be a whole number, 1 or more")
    for key in ("mobile_screens_home", "mobile_screens_other"):
        if key in cap and not (isinstance(cap[key], int) and not isinstance(cap[key], bool) and cap[key] >= 0):
            _fail(f"capture.{key} must be a whole number, 0 or more")
    for key in ("desktop", "mobile"):
        if key in cap and not (isinstance(cap[key], list) and len(cap[key]) == 2
                               and all(_positive(v, whole=True) for v in cap[key])):
            _fail(f"capture.{key} must be [width, height] in pixels")
    media = cap.get("media", "")
    if not isinstance(media, str) or not all(re.fullmatch(r"[a-z][a-z-]*", word) for word in media.split()):
        _fail('capture.media must be words such as "light" or "light reduced-motion"')


# ---------------------------------------------------------------- usability studies

def a_type(kind: str) -> str:
    """A study type with its article: "a review", "an interview"."""
    return f"{'an' if kind[0] in 'aeio' else 'a'} {kind}"


def check_type_keys(cfg: dict):
    """Refuse a key that belongs to another type of study, and a setting a usability or an
    interview study cannot have: a key that is quietly ignored reads as a setting in force."""
    kind, given = cfg["type"], cfg.get("_given", frozenset(cfg))
    for other, keys in TYPE_KEYS.items():
        stray = [] if other == kind else [k for k in keys if k in given and not (k == "concepts" and cfg[k] == [])]
        if stray:
            _fail(f'{listed_keys(stray)} {agree(len(stray), "belongs", "belong")} to {a_type(other)} study, and this '
                  f"is {a_type(kind)} study"
                  + TYPE_HINT[kind, other].format(it=agree(len(stray), "it", "them")))
    if kind == "interview":
        named = [k for k in ("product", "product_phrase") if k in given]
        if named:
            _fail(f"an interview study has no {listed_keys(named, 'or')}: a standalone interview never names a "
                  f"product, and its briefs would. Take {agree(len(named), 'it', 'them')} out, and put the product's "
                  'name in "leak_terms", so that no question can carry it')
        if "debrief" in given:
            _fail('an interview study has no "debrief": a debrief is an interview held in the session of a finished '
                  "review or usability run, which has seen the product. Take it out")
        stray = [k for k in NOT_INTERVIEW if k in given]
        if stray:
            _fail(f'an interview study has no {listed_keys(stray, "or")}: nothing is scored, captured or browsed. Take '
                  f'{agree(len(stray), "it", "them")} out')
    if kind != "usability":
        return
    if cfg["materials"] != "full":
        _fail('a usability study has no "materials": "text": its panellists use the running product in a browser. '
              "Take it out")
    if cfg["browse"] is not True:
        _fail('a usability study always browses: take "browse": false out')
    extra = sorted(set(cfg.get("capture") or {}) - {"desktop"}) if isinstance(cfg.get("capture"), dict) else []
    if extra:
        _fail(f"capture.{extra[0]}: a usability study captures nothing. Only capture.desktop applies: [width, "
              "height] of each panellist's browser window")


def listed(words: list[str], last: str = "and") -> str:
    """Words as a list in a sentence: "a", "a and b", "a, b and c"."""
    return ", ".join(words[:-1]) + (f" {last} " if words[:-1] else "") + words[-1]


def listed_keys(keys: list[str], last: str = "and") -> str:
    return listed([f'"{k}"' for k in keys], last)


def target_parts(url) -> tuple[str, str, int | None]:
    """The scheme, host and port of a target.base_url, read by a grammar of its own and never by
    a URL parser, which can take another host from an address than a browser does: a browser
    reads a backslash as a slash, so a host written before one is where it goes, whatever
    follows. The whole text must be

        http:// or https://, a host, then optionally ":" and a port, then optionally one "/"

    in ASCII, and a host is one of three things, lower-cased:

        a name      labels of letters, digits and hyphens, joined by dots: no empty label, so no
                    dot at either end, no label that begins or ends with a hyphen, at most 63
                    characters a label and 253 in all
        IPv4        four numbers from 0 to 255 in decimal, with no leading zero: "127.0.0.1"
        IPv6        an address in square brackets: "[::1]"

    Nothing else is a target: no user name or password, no path, query or fragment, no backslash,
    space, control character, "@" or "%". A name whose last label is a number ("2130706433",
    "0x7f.1", "127.1", "127.0.0.01") is refused outright: a browser reads it as an IPv4 address
    in another notation, so it names a host other than the one it shows. The port is 1 to 65535,
    with no leading zero. Raises ValueError with what is wrong, as the end of a sentence."""
    m = TARGET.fullmatch(url) if isinstance(url, str) and url.isascii() else None
    if not m or m["scheme"].lower() not in ("http", "https"):
        raise ValueError("is not http:// or https://, a host and an optional port, in plain ASCII letters, digits, "
                         "hyphens and dots, with nothing after them")
    host, port = m["host"].lower(), m["port"]
    if port and (port[0] == "0" or int(port) > 65535):
        raise ValueError("has a port that is not a number from 1 to 65535, written without a leading zero")
    if host[0] == "[":
        try:
            ipaddress.IPv6Address(host[1:-1])
        except ValueError:
            raise ValueError("has square brackets around something that is no IPv6 address") from None
    elif not IPV4.fullmatch(host) or any(int(n) > 255 for n in host.split(".")):
        labels = host.split(".")
        if HOST_NUMBER.fullmatch(labels[-1]):
            raise ValueError("has a host that ends in a number and is not four decimal numbers from 0 to 255: a "
                             "browser reads it as an IP address written another way, so it is ambiguous. Write the "
                             'address as "127.0.0.1" is written, or use a name')
        if len(host) > 253 or not all(HOST_LABEL.fullmatch(label) for label in labels):
            raise ValueError("has a host that is not a plain name: labels of letters, digits and hyphens joined by "
                             "single dots, with no dot at either end and no hyphen at either end of a label")
    return m["scheme"].lower(), host, int(port) if port else None


def local_host(host: str) -> bool:
    """Whether a host, as target_parts() gives it, is a local development host (LOCAL_RULE): the
    hosts a usability study may drive a browser through, sign in on and submit forms to without
    "allow_remote". Exactly three, and the names that end in ".localhost" or ".test". Every other
    way to write this machine is not local, and needs "allow_remote" like any other host:
    "127.0.0.2", "0.0.0.0", "[::ffff:127.0.0.1]", "[0:0:0:0:0:0:0:1]". Nor is a name with a
    punycode label ("xn--"), which a browser shows as other letters than the ones written."""
    return host in LOCAL_HOSTS or (host.endswith(LOCAL_ENDINGS)
                                   and not any(label.startswith("xn--") for label in host.split(".")))


def command_words(text) -> list[str] | None:
    """A configured command split with shell rules, None when it is no command: not a string,
    empty, or with a quote left open."""
    try:
        return (shlex.split(text) or None) if isinstance(text, str) else None
    except ValueError:
        return None


def command_argv(cfg: dict, text: str) -> list[str]:
    """What to execute for a configured command, without a shell: its words, the first made the
    path of the file it names under the study directory, or of the program of that name on PATH.
    Raises ValueError, with the reason as the end of a sentence, when there is neither."""
    words = command_words(text)
    if not words:
        raise ValueError("is not a command")
    named = Path(words[0]).expanduser()
    file = named if named.is_absolute() else cfg["_dir"] / named
    if file.is_file():
        if not os.access(file, os.X_OK):
            raise ValueError(f"names {file}, which is not executable (chmod +x)")
        return [str(file), *words[1:]]
    found = shutil.which(words[0]) if os.sep not in words[0] else None
    if not found:
        raise ValueError(f"names {json.dumps(words[0])}: there is no file {file}"
                         + ("" if os.sep in words[0] else " and no program of that name on PATH"))
    return [found, *words[1:]]


def account_problem(account, signin: str = "session") -> str | None:
    """Why a value is not one test account, as the end of a sentence, else None. An account is
    what accounts.provision prints for a run and what accounts.map holds for one: {"identifiers":
    {name: value}, "secrets": {name: value}, "state": "<file>"}, the last two optional."""
    def values(part):
        held = account.get(part, {})
        return isinstance(held, dict) and all(isinstance(k, str) and k and isinstance(v, (str, int, float))
                                              and not isinstance(v, bool) for k, v in held.items())

    shape = ('{"identifiers": {"username": "..."}, "secrets": {"password": "..."}, "state": "<saved browser state '
             'file>"}')
    if not isinstance(account, dict) or set(account) - set(ACCOUNT_PARTS):
        return f"must be one JSON object with any of {', '.join(ACCOUNT_PARTS)}: {shape}"
    if not account.get("identifiers") or not values("identifiers"):
        return ('needs "identifiers": the made-up values a panellist may see, such as {"username": "test-1", '
                '"display_name": "Priya Raman"}, each a string or a number')
    if not values("secrets"):
        return 'has "secrets" that are not an object of strings or numbers: the values no one may see, such as a password'
    if "state" in account and not (isinstance(account["state"], str) and account["state"].strip()):
        return 'has a "state" that is not the path of a saved browser state file'
    if signin == "panellist" and not account.get("secrets"):
        return ('has no "secrets", and accounts.signin is "panellist": the panellist is to sign in itself, and has '
                "nothing to sign in with")
    return None


def check_usability(cfg: dict):
    """Validate "target", "tasks", "accounts" and "sequential" (module docstring, "Usability
    studies"), fill each task's defaults, and set cfg["_remote"]: whether the target is not a
    local development host. Whether a command's file exists is usability_problems()'s to say."""
    if any(e["runner"] is None for e in model_entries(cfg)):
        _fail('a usability study runs through runners: the launcher starts each run\'s browser session and its '
              'test account, which native mode cannot. Set a study-level "runner", or give every model entry one')
    if not (isinstance(cfg.get("product"), str) and cfg["product"].strip()):
        _fail('a usability study needs "product": the name of what is tested, such as "Acme Home Loans". The '
              'analysts\' and the writer\'s briefs call the product by it. "product_phrase" changes only how the '
              "instructions introduce it, and does not stand in for it")

    target = cfg.get("target")
    if not isinstance(target, dict) or set(target) - {"base_url", "allow_remote"}:
        _fail('a usability study needs "target": {"base_url": "http://app.localhost:8080"}, with "allow_remote": '
              "true only for a remote site that panellists must not change")
    if not isinstance(target.setdefault("allow_remote", False), bool):
        _fail("target.allow_remote must be true or false")
    url = target.get("base_url")
    try:
        scheme, host, port = target_parts(url)
    except ValueError as err:
        _fail(f'target.base_url {json.dumps(url)} {err}. It must be where the product runs, as in '
              '"http://app.localhost:8080". A page to begin on is a task\'s "start"')
    # As the parts say, and never as written: this is the address every panellist is given.
    target["base_url"] = f"{scheme}://{host}" + (f":{port}" if port else "")
    remote = cfg["_remote"] = not local_host(host)
    if remote and not target["allow_remote"]:
        _fail(f"target.base_url {json.dumps(url)} is not a local development host ({LOCAL_RULE}"
              + (': a name with a punycode label, "xn--", is never taken as one' if host.endswith(LOCAL_ENDINGS)
                 else "") + "). A usability "
              "study signs in, fills in forms and submits them, so it runs against a local build. To study a "
              'remote site without changing anything on it, add "allow_remote": true to "target": every task '
              'must then say "read_only": true, and the study can have no "accounts"')

    tasks = cfg.get("tasks")
    if not isinstance(tasks, list) or not tasks or not all(isinstance(t, dict) for t in tasks):
        _fail('a usability study needs "tasks": a list of {"id", "goal", "start", "steps"} objects, in the order '
              "to attempt them")
    seen = set()
    for t in tasks:
        tid = t.get("id")
        if not (isinstance(tid, str) and TASK_ID.fullmatch(tid)):
            _fail(f'the task id {json.dumps(tid)} must be letters and digits only, such as "T1", because it is '
                  'what a panellist writes after "Task" and part of each screenshot\'s file name')
        if tid.lower() in seen:
            _fail(f'two tasks have the id "{tid}". Ids must be unique, ignoring case, because they name sections '
                  "and files")
        seen.add(tid.lower())
        where = f"task {tid}:"
        if set(t) - set(TASK_FIELDS):
            _fail(f"{where} unknown fields: {', '.join(sorted(set(t) - set(TASK_FIELDS)))} (use "
                  f"{', '.join(TASK_FIELDS)})")
        if not (isinstance(t.get("goal"), str) and t["goal"].strip()):
            _fail(f'{where} it needs "goal": what the person wants to get done, in their own words, naming no '
                  "button or menu")
        start = t.setdefault("start", "/")
        if not (isinstance(start, str) and START.fullmatch(start) and "//" not in start):
            _fail(f'{where} "start" {json.dumps(start)} must be a path on the target, beginning with one "/", such '
                  'as "/" or "/account/settings?tab=email". It can have no "//", no backslash, no space or control '
                  "character and no address of its own, and anything outside plain ASCII is written percent-encoded. "
                  "A task never starts at another address")
        if not _positive(t.setdefault("steps", DEFAULT_STEPS), whole=True):
            _fail(f'{where} "steps" must be a whole number, 1 or more: the most actions a panellist takes on it '
                  f"(default {DEFAULT_STEPS})")
        if "success_check" in t and not command_words(t["success_check"]):
            _fail(f'{where} "success_check" must be a command, such as "scripts/check-{tid.lower()}.sh": it is run '
                  "without a shell, with the run id as its last argument")
        if not isinstance(t.setdefault("read_only", False), bool):
            _fail(f'{where} "read_only" must be true or false')
        if remote and not t["read_only"]:
            _fail(f'{where} it must say "read_only": true, because the target is a remote site ("allow_remote"): '
                  "its panellists may look and move around, and must submit nothing, sign in nowhere and change "
                  "nothing. Check that the goal can be met that way")

    if not isinstance(cfg.setdefault("sequential", False), bool):
        _fail('"sequential" must be true or false: whether one panellist runs at a time, across all runners')
    acc = cfg.setdefault("accounts", None)
    if acc is None:
        return
    if remote:
        _fail('"accounts" cannot be used with a remote target ("allow_remote"): no test credentials are ever '
              'entered on a remote site. Take "accounts" out, or point "target" at a local build')
    if not isinstance(acc, dict) or set(acc) - set(ACCOUNT_FIELDS) or ("provision" in acc) == ("map" in acc):
        _fail('"accounts" must be an object with "provision" (a command that prints one account for a run) or "map" '
              f'(the accounts, keyed by run id), not both, and any of {", ".join(ACCOUNT_FIELDS[2:])}')
    if acc.setdefault("signin", SIGNIN[0]) not in SIGNIN:
        _fail(f'accounts.signin must be "{SIGNIN[0]}" (the default: each browser session starts from the saved state '
              f'its account names, and the panellist is given no secret) or "{SIGNIN[1]}" (signing in is the task '
              "under test: the panellist is given the secrets to type)")
    for name in ACCOUNT_COMMANDS:
        if name in acc and not command_words(acc[name]):
            _fail(f'accounts.{name} must be a command, such as "scripts/{name}-account.sh": it is run without a '
                  "shell, with the run id as its last argument")
    if "reset" in acc and not cfg["sequential"]:
        _fail('accounts.reset runs between the runs of a sequential study, and this one is not: set "sequential": '
              "true, or take it out")
    if "map" in acc:
        runs = [run_id(p["id"], key, rep) for p in cfg.get("personas") or [] for key in model_keys(cfg)
                for rep in range(1, cfg["replicates"] + 1)]
        held = acc["map"]
        if not isinstance(held, dict):
            _fail("accounts.map must be an object, {run id: account}")
        lacking, unknown = [r for r in runs if r not in held], [r for r in held if r not in runs]
        if lacking or unknown:
            _fail("accounts.map must have one account for each run, keyed by run id"
                  + (f". It has none for {', '.join(lacking)}" if lacking else "")
                  + (f". It names {', '.join(unknown)}, which {agree(len(unknown), 'is no run', 'are no runs')} of "
                     f"this study (runs: {', '.join(runs)})" if unknown else ""))
        for run, account in held.items():
            problem = account_problem(account, acc["signin"])
            if problem:
                _fail(f"accounts.map: the account of {run} {problem}")


def usability_problems(cfg: dict) -> list[str]:
    """What would stop a usability study's runs as the files stand, each a sentence: a
    "success_check" or an accounts command whose file is not there (command_argv()), and a saved
    browser state of accounts.map that is missing or where a panellist could read it. Empty for
    a review study. The scaffold, the plan and every command that starts a run ask this."""
    if cfg["type"] != "usability":
        return []
    acc, out = cfg["accounts"] or {}, []
    commands = {f'task {t["id"]}: "success_check"': t["success_check"] for t in cfg["tasks"] if "success_check" in t}
    commands.update({f"accounts.{name}": acc[name] for name in ACCOUNT_COMMANDS if name in acc})
    for where, text in commands.items():
        try:
            command_argv(cfg, text)
        except ValueError as err:
            out.append(f"{where} {err}.")
    for run, account in (acc.get("map") or {}).items():
        problem = state_problem(cfg, account.get("state"))
        if problem:
            out.append(f"accounts.map: the saved browser state of {run} {problem}.")
    return out


def state_file(cfg: dict, state: str) -> Path:
    """A saved browser state named by an account, as a path: relative to the study directory."""
    named = Path(state).expanduser()
    return (named if named.is_absolute() else cfg["_dir"] / named).resolve()


def state_problem(cfg: dict, state: str | None, named: bool = True) -> str | None:
    """Why the saved browser state an account names cannot be used, as the end of a sentence,
    else None: it holds the account's session cookie in plain text, so it must be a file that
    no panellist can read. named false leaves the file's name out: it is then part of what a
    provision command printed, none of which is repeated (accounts.py)."""
    if not state:
        return None
    file, panel = state_file(cfg, state), (cfg["_dir"] / "panel").resolve()
    where = f"is {file}, " if named else "is "
    if file == panel or panel in file.parents:
        return f"{where}under panel/, where every panellist can read it: it holds the account's cookie"
    return None if file.is_file() else f"{where}and there is no such file" if named else "is not there"


def task_url(cfg: dict, task: dict) -> str:
    """The address a task starts at: the target, as check_usability() rebuilt it from its parts,
    plus the task's "start", which is a path and can name no other host."""
    return cfg["target"]["base_url"] + task["start"]


def usability_minutes(cfg: dict) -> float:
    """The minutes a usability run gets when study.json sets no limits.run.minutes: STEP_SECONDS
    for each step its tasks permit, plus RUN_MINUTES for reading the instructions and writing the
    persona file. Measured at 6 to 10 seconds a step on small models, so it leaves room for
    larger ones."""
    return sum(t["steps"] for t in cfg["tasks"]) * STEP_SECONDS / 60 + RUN_MINUTES


def evidence_dir(study_dir: Path, run: str) -> Path:
    """Where a usability run keeps its step log and screenshots: panel/evidence/<run id> in a
    live study, evidence/<run id> in an archived round (archive.py flattens panel/). To name it,
    and for the scaffold to make it: whatever reads from it opens it with evidence_fd()."""
    live = (Path(study_dir) / "panel").is_dir()
    return Path(study_dir) / (EVIDENCE if live else Path(EVIDENCE).name) / run


def open_regular(path, dir_fd: int | None = None, most: int = READ_MOST) -> int:
    """Open a file that a panellist may have put there, to read it: a descriptor. A symbolic link
    at its name is never followed, and the open never waits, as it would for the other end of a
    FIFO. Raises Unsafe, with nothing read, unless the descriptor is of a regular file that
    holds at most `most` bytes, and the system's own error when there is no such file or it may
    not be read. As run_watchdog.opened() opens a file of an attempt, without its rule that the
    file be this user's: an archived round may be another's."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)
    except OSError as err:
        if err.errno in (errno.ELOOP, errno.EMLINK):  # what O_NOFOLLOW says of a link, on Linux and macOS, and on BSD
            raise Unsafe("it is a symbolic link") from None
        raise
    st = os.fstat(fd)
    why = ("it is not a regular file" if not stat.S_ISREG(st.st_mode)
           else f"it holds {st.st_size:,} bytes, more than is read" if st.st_size > most else None)
    if why:
        os.close(fd)
        raise Unsafe(why)
    return fd


def unread(err: OSError) -> str:
    """Why a file or a folder was not read, for a message: the system's words, or Unsafe's."""
    return err.strerror or str(err)


def folder_fd(study_dir: Path, parts) -> int:
    """Open a folder below the study directory, given by the names on the way down to it: a
    descriptor, to list it and to open what is in it by dir_fd. A panellist can write under
    panel/, and so can put a symbolic link where a folder was: each part of the way below the
    study directory is opened without following one, so nothing outside the study is ever
    listed, read or written through this. Raises FileNotFoundError when there is no such
    folder, and Unsafe, naming the part, when one is a link or no folder."""
    fd = os.open(study_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for i, part in enumerate(parts):
            try:
                below = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            except OSError as err:
                if err.errno not in (errno.ELOOP, errno.EMLINK, errno.ENOTDIR):
                    raise
                link = stat.S_ISLNK(os.stat(part, dir_fd=fd, follow_symlinks=False).st_mode)
                raise Unsafe(f"{'/'.join(parts[:i + 1])} is {'a symbolic link' if link else 'not a folder'}, so "
                             "nothing was read through it") from None
            os.close(fd)
            fd = below
    except BaseException:
        os.close(fd)
        raise
    return fd


def parts_below(study_dir: Path, path) -> tuple[str, ...]:
    """The names on the way from the study directory down to a path under it. Raises Unsafe for
    a path that is not under it, or that goes back up."""
    try:
        parts = Path(path).relative_to(study_dir).parts
    except ValueError:
        parts = ()
    if not parts or ".." in parts:
        raise Unsafe("it is not a path under the study directory")
    return parts


def open_below(study_dir: Path, path, most: int = READ_MOST) -> int:
    """Open a file under the study directory that a panellist may have put there, to read it: a
    descriptor. Every folder between the study directory and the file is opened without
    following a symbolic link (folder_fd()), and so is the file, without waiting
    (open_regular()): nothing outside the study is read through this, whatever was put at the
    file's name or at a folder's since anyone last looked. Raises OSError, with the reason
    (unread()): FileNotFoundError when there is no such file, Unsafe when a folder on the way
    is a link or no folder, or the file is a link, no regular file or holds more than `most`
    bytes, and the system's own error when either may not be read."""
    *folders, name = parts_below(study_dir, path)
    try:
        folder = folder_fd(study_dir, folders)
    except Unsafe:  # which names the folder, and a name under panel/ may be a panellist's own text
        raise Unsafe("a folder above it is a symbolic link, or no folder") from None
    try:
        return open_regular(name, dir_fd=folder, most=most)
    finally:
        os.close(folder)


def evidence_fd(study_dir: Path, run: str | None) -> int:
    """Open a run's evidence folder (evidence_dir()) to read from it, or with run None the
    evidence root that holds every run's: a descriptor, for evidence_names() and for opening
    the files in it by dir_fd. A panellist can write under panel/, and so can put a symbolic
    link where the evidence root or its own folder was: each part of the way below the study
    directory is opened without following one (folder_fd()), so nothing outside the study is
    ever listed or read through this. Raises FileNotFoundError when there is no such folder,
    and Unsafe, naming the part, when one is a link or no folder."""
    live = (Path(study_dir) / "panel").is_dir()
    parts = (*(Path(EVIDENCE).parts if live else (Path(EVIDENCE).name,)), *([] if run is None else [run]))
    if run is not None and (not run or run in (".", "..") or "/" in run or "\x00" in run):
        raise Unsafe("the run id is no folder name")
    return folder_fd(study_dir, parts)


def evidence_names(study_dir: Path, run: str | None) -> list[tuple[str, str]]:
    """What a run's evidence folder holds, or with run None the evidence root: (name, kind) in
    name order, kind being "file", "folder" or "other", which a symbolic link is whatever it
    points at. Empty when there is no such folder. Raises OSError as evidence_fd() does."""
    try:
        folder = evidence_fd(study_dir, run)
    except FileNotFoundError:
        return []
    try:
        with os.scandir(folder) as listing:
            return sorted((f.name, "file" if f.is_file(follow_symlinks=False) else
                           "folder" if f.is_dir(follow_symlinks=False) else "other") for f in listing)
    finally:
        os.close(folder)


def open_evidence(study_dir: Path, run: str, name: str, most: int = READ_MOST) -> int:
    """Open one file of a run's evidence folder to read it, as evidence_fd() and open_regular()
    open: no link is followed, to the folder or at the file's name. A descriptor. Raises
    OSError: FileNotFoundError when there is no such folder or file, Unsafe when one is refused."""
    if not name or name in (".", "..") or "/" in name or "\x00" in name:
        raise Unsafe("it is not the name of a file in the folder")
    folder = evidence_fd(study_dir, run)
    try:
        return open_regular(name, dir_fd=folder, most=most)
    finally:
        os.close(folder)


def read_evidence(study_dir: Path, run: str, name: str) -> bytes:
    """The content of one file of a run's evidence folder (open_evidence())."""
    with os.fdopen(open_evidence(study_dir, run, name), "rb") as f:
        return f.read()


def step_log_stamp(study_dir: Path, run: str) -> tuple | None:
    """What tells whether a run's step log has changed since it was last read: which file it is,
    its size, and when it and its mode last changed. None when the run has no log, or no
    evidence folder. Asked without following a link, as the log is read. Raises OSError, with
    the reason (unread()), when there is something at the log's name, or at its folder's, that
    cannot be read as the run's: a symbolic link, a FIFO, a folder that may not be opened."""
    try:
        folder = evidence_fd(study_dir, run)
    except FileNotFoundError:
        return None
    try:
        st = os.stat(STEP_LOG, dir_fd=folder, follow_symlinks=False)
    except FileNotFoundError:
        return None
    finally:
        os.close(folder)
    if not stat.S_ISREG(st.st_mode):
        raise Unsafe("it is a symbolic link" if stat.S_ISLNK(st.st_mode) else "it is not a regular file")
    return st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def step_log(study_dir: Path, run: str) -> str | None:
    """The text of a run's step log, None when the run has none. Raises OSError, with the reason
    (unread()), when there is one that cannot be read as the run's: its folder or the evidence
    root is a symbolic link, the log is one, or a FIFO, or may not be read. A reader that must
    not pass over such a log asks this: read_steps() reads it as no log."""
    try:
        return read_evidence(study_dir, run, STEP_LOG).decode(errors="replace")
    except FileNotFoundError:
        return None


def step_lines(study_dir: Path, run: str) -> tuple[list[str], str]:
    """A run's step log as the launcher's backstop reads it: the lines that are whole, each ended
    by a line feed, and what stands after the last of them, which a panellist may still be
    writing. Both empty when the run has no log. Raises OSError as step_log() does."""
    *lines, rest = (step_log(study_dir, run) or "").split("\n")
    return lines, rest


def read_steps(study_dir: Path, run: str) -> tuple[list[dict], list[int]]:
    """A run's step log: its entries in file order, and the 1-based numbers of the lines that
    are no entry (not a JSON object, or one with no task). Both empty when there is no log, or
    none that can be read as the run's (step_log(), run_evidence() "log_problem"). Each entry is
    as the panellist wrote it, with "attempt" filled in: 1 where it gave none, and 0, which is
    never issued (counted()), where it gave one that is no whole number above 0."""
    try:
        return steps_of((step_log(study_dir, run) or "").splitlines())
    except OSError:
        return [], []


def steps_of(lines: list[str]) -> tuple[list[dict], list[int]]:
    """read_steps(), for lines of a step log that were read already."""
    entries, odd = [], []
    for i, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            entry = None
        if not isinstance(entry, dict) or not isinstance(entry.get("task"), str):
            odd.append(i)
            continue
        if not _positive(entry.setdefault("attempt", 1), whole=True):
            entry["attempt"] = 0
        entries.append(entry)
    return entries, odd


def step_number(entry: dict) -> int | None:
    """An entry's step number when it is a whole number, 0 or more, else None."""
    step = entry.get("step")
    return step if isinstance(step, int) and not isinstance(step, bool) and step >= 0 else None


def issued_attempts(entry: dict | None) -> dict[str, int]:
    """{task id: the latest attempt the launcher has told a run to log the task under}, from the
    run's entry in runs.json ("task_attempts"). A task it does not name is on attempt 1, as
    every task is until the run is continued with the task under way (launch.py). The number is
    the launcher's to give: a panellist that writes another gets nothing by it (counted())."""
    held = (entry or {}).get("task_attempts")
    return {task: n for task, n in held.items() if _positive(n, whole=True)} if isinstance(held, dict) else {}


def counted(entries: list[dict], issued: dict[str, int]) -> list[dict]:
    """The entries of a step log that say what a run did, from read_steps(): those in the form
    the instructions set, a whole step number and a phase that is "intent" or "result", whose
    attempt the launcher issued for their task (issued_attempts()): 1 up to the task's latest.
    Every other entry is left out before anything is read from the log, so that none can pass
    for a later attempt and supersede the steps a run took (step_notes() counts them)."""
    return [e for e in entries if step_number(e) is not None and e.get("phase") in STEP_PHASES
            and 1 <= e["attempt"] <= issued.get(e["task"], 1)]


def step_attempts(entries: list[dict], issued: dict[str, int]) -> dict[str, int]:
    """{task id: the number of its latest attempt in a step log}, among the entries that count
    (counted()). The entries of an earlier attempt of a task are superseded: its run was cut off
    part-way, and began the task again."""
    latest = {}
    for e in counted(entries, issued):
        latest[e["task"]] = max(latest.get(e["task"], 1), e["attempt"])
    return latest


def task_steps(entries: list[dict], issued: dict[str, int]) -> dict[str, dict]:
    """What a step log says of each task it has entries for that count (counted()), from
    read_steps(): {task id: {"attempt", "attempts", "steps"}}. "attempt" is the task's latest
    attempt (step_attempts()) and "attempts" how many it has had. "steps" has the steps of that
    attempt alone, in step order: one {"step", "intent", "result"} for each step number from 1
    up that has an entry, with None where the log has no entry of that phase. A step is complete
    when it has both. The first entry stands when a step has two of one phase."""
    latest, out = step_attempts(entries, issued), {}
    for e in counted(entries, issued):
        task = out.setdefault(e["task"], {"attempt": latest[e["task"]], "attempts": set(), "steps": {}})
        task["attempts"].add(e["attempt"])
        n, phase = step_number(e), e["phase"]
        if e["attempt"] == task["attempt"] and n:
            task["steps"].setdefault(n, {"step": n, "intent": None, "result": None})
            if task["steps"][n][phase] is None:
                task["steps"][n][phase] = e
    for task in out.values():
        task.update(attempts=len(task["attempts"]), steps=[task["steps"][n] for n in sorted(task["steps"])])
    return out


def steps_begun(cfg: dict, added: list[dict], begun: dict[str, int] | None = None) -> dict | None:
    """The backstop of a task's step limit (launch.py), over the entries one process of a run
    added to its step log: {"task", "step", "of"} for the first "intent" entry that begins a
    step beyond its task's limit, None when none does. An entry is beyond the limit when its
    step number is above it, or when it is one intent more than the limit allows the process
    for that task. Every intent of a task of the study counts, whatever attempt it carries: the
    process logs one attempt of a task, the one the launcher issued, so an entry that names
    another neither starts the count again nor escapes it. "step" is the entry's own number
    when that is above the limit, else how many steps of the task the process has begun.

    begun is {task id: the steps of it the process had begun before these entries}, for a
    caller that reads the log a part at a time. It is added to, so the count is the caller's to
    keep and goes on from one part to the next whatever becomes of the log between them."""
    limits, begun = {t["id"]: t["steps"] for t in cfg["tasks"]}, {} if begun is None else begun
    for e in added:
        n = step_number(e)
        if e.get("phase") != "intent" or n is None or e["task"] not in limits:
            continue
        begun[e["task"]] = begun.get(e["task"], 0) + 1
        if n > limits[e["task"]] or begun[e["task"]] > limits[e["task"]]:
            return {"task": e["task"], "step": n if n > limits[e["task"]] else begun[e["task"]],
                    "of": limits[e["task"]]}
    return None


def step_notes(cfg: dict, entries: list[dict], odd: list[int], issued: dict[str, int], known: dict | None) -> list[str]:
    """What is wrong with the form of a step log, from read_steps(), each as the end of a
    sentence that begins "its step log has". None of them stops a run or an analysis: lines that
    are no entry, entries for a task the study does not have, entries with no whole step number
    or with a phase that is neither "intent" nor "result", entries with an attempt number the
    launcher did not issue (issued_attempts()), and an intent whose step number is lower than
    that of the intent before it in the same task and attempt. known is what a scan knows the
    study's secrets by: a task id the study does not have is a panellist's own text, and is
    shown as shown() allows."""
    tasks, notes = {t["id"] for t in cfg["tasks"]}, []
    if odd:
        notes.append(f"{plural(len(odd), 'line')} that cannot be read as an entry (line "
                     f"{', '.join(map(str, odd[:5]))}{', ...' if len(odd) > 5 else ''})")
    unknown = list(dict.fromkeys(e["task"] for e in entries if e["task"] not in tasks))
    if unknown:
        notes.append(f"entries for {agree(len(unknown), 'a task', 'tasks')} this study does not have "
                     f"({', '.join(shown(known, x, 'a value that is not a task id') for x in unknown[:5])}"
                     f"{', ...' if len(unknown) > 5 else ''})")
    shapeless = sum(step_number(e) is None or e.get("phase") not in STEP_PHASES for e in entries)
    if shapeless:
        notes.append(f"{plural(shapeless, 'entry', 'entries')} with no whole step number, or with a phase that is "
                     'neither "intent" nor "result"')
    strangers = sum(e["task"] in tasks and not 1 <= e["attempt"] <= issued.get(e["task"], 1) for e in entries)
    if strangers:
        notes.append(f"{plural(strangers, 'entry', 'entries')} with an attempt number the launcher did not give "
                     f"{agree(strangers, 'its', 'their')} task, which {agree(strangers, 'is', 'are')} left out of the "
                     "steps counted")
    before, back = {}, []
    for e in counted(entries, issued):
        n, where = step_number(e), (e["task"], e["attempt"])
        if e["phase"] != "intent" or e["task"] not in tasks:
            continue
        if n < before.get(where, 0):
            back.append(f"task {e['task']}, step {n} after step {before[where]}")
        before[where] = n
    if back:
        notes.append(f"step numbers that go backwards ({'; '.join(back[:3])}{'; ...' if len(back) > 3 else ''})")
    return notes


def join_notes(notes: list[str]) -> str:
    """Several notes as one cell of a CSV file (runs.csv, "step_notes"), for split_notes() to
    take apart again: the notes with "; " between them, and in a note a backslash before each
    ";" and each backslash of its own, so that nothing a note holds reads as the end of it. A
    note with no text at all is written as a backslash and a 0."""
    return "; ".join(note.replace("\\", "\\\\").replace(";", "\\;") or "\\0" for note in notes)


def split_notes(cell: str) -> list[str]:
    """The notes join_notes() put in a cell, whatever each holds. A cell written before a note's
    own ";" had its backslash holds none, and reads as it always did, apart at every "; ": a
    note of that time that has one of its own (step numbers that went backwards more than
    once) still comes apart there. extract_scores.py writes the cell anew."""
    notes, note, chars = [], "", iter(cell)
    for c in chars:
        if c == "\\":  # what comes after it is the note's own
            c = next(chars, "")
            note += "" if c == "0" else c
        elif c == ";":  # the end of a note, with the space after it
            next(chars, None)
            notes.append(note)
            note = ""
        else:
            note += c
    return [*notes, note] if cell else []


_OUTCOMES = "|".join(r"\s+".join(map(re.escape, o.split())) for o in USABILITY_OUTCOMES)
_OUTCOME_LINE = re.compile(rf"^\s*(?:[-*+]\s+)?(?:\*\*|__)?\s*{OUTCOME_LABEL}\b\s*:?\s*(?:\*\*|__)?\s*:?(.*)$", re.I)
_OUTCOME = re.compile(rf"({_OUTCOMES})\b(.*)$", re.I)
_NEXT_OUTCOME = re.compile(rf"[\s,/;:-]*(?:(?:and|or|but|then)\s+)?(?:{_OUTCOMES})\b", re.I)


def claimed_outcome(section: str | None) -> str:
    """What a panellist says became of a task, from its task section: one of USABILITY_OUTCOMES,
    "unparsed", or "" when the task has no section. Only an "Outcome" field that opens with
    exactly one of the three phrases counts, in any case. One that opens with anything else
    ("Not completed", "I gave up"), goes straight on to another of the three ("completed / gave
    up", as the template has it before it is filled in), or is missing, is "unparsed": the
    parser never guesses a claim."""
    if section is None:
        return ""
    for line in section.split("\n")[1:]:
        m = _OUTCOME_LINE.match(line)
        if m:
            said = _OUTCOME.match(_MARKUP.sub("", m.group(1)).strip())
            if not said or _NEXT_OUTCOME.match(said.group(2)):
                return "unparsed"
            return " ".join(said.group(1).lower().split())
    return "unparsed"


# ---------------------------------------------------------------- interview studies

def _guide_id(value, what: str, where: str, seen: set, reserved: tuple = ()) -> str:
    """One goal or topic id of a guide, checked: letters and digits, not a word of reserved, and
    not one of seen, ignoring case. Exits naming what it is ("goal", "topic") and where."""
    if not (isinstance(value, str) and GUIDE_ID.fullmatch(value)):
        _fail(f'{where}: the {what} id {json.dumps(value)} must be letters and digits only, such as '
              f'"{what[0].upper()}1", because the interviewer writes it in every reply')
    if value.lower() in reserved:
        _fail(f'{where}: the {what} id "{value}" is taken: an interviewer\'s reply writes '
              f'{listed(list(reserved), "or")} where a {what} id goes. Give the {what} another id')
    if value.lower() in seen:
        _fail(f'{where}: two {what}s have the id "{value}". Ids must be unique, ignoring case')
    seen.add(value.lower())
    return value


def check_guide(cfg: dict, block: str, keys: tuple = GUIDE_KEYS) -> dict:
    """Validate a guide, cfg[block], and fill its defaults in place: its interviewer a normalised
    model entry, and every topic with "goals", "turns" and "segments" (module docstring,
    "Interview studies"). Returns it. A key of keys that the block may leave out is checked only
    when it is there."""
    guide = cfg.get(block)
    if not isinstance(guide, dict):
        _fail(f'"{block}" must be the guide, an object with {listed(list(keys))}: who interviews, what to learn, '
              "and the topics in the order to open them")
    if set(guide) - set(keys):
        _fail(f"{block}: unknown keys: {', '.join(sorted(set(guide) - set(keys)))} (use {', '.join(keys)})")
    if "about" in keys and not (isinstance(guide.get("about"), str) and guide["about"].strip()):
        _fail(f'{block}.about must be one neutral sentence on the area of work, such as "how mortgage brokers run a '
              'loan from first enquiry to settlement": the interviewer may state it when a participant asks what '
              "this is for, so it names no idea and no product")

    raw = guide.get("interviewer")
    if raw is None:
        _fail(f'{block}.interviewer is missing: the model entry of the interviewer, such as {{"runner": "claude", '
              '"model": "<a model>"}. There is no default')
    entry = model_entry(raw, cfg["runner"], f"{block}.interviewer")
    if entry["runner"] is None:
        _fail(f'{block}.interviewer needs a "runner": there is no default, and the launcher carries every turn '
              'through one. Give it one, or set a study-level "runner"')
    if not (isinstance(raw, dict) and raw.get("key")):
        entry["key"] = "interviewer"
    guide["interviewer"] = entry

    goals, seen = guide.get("goals"), set()
    if not isinstance(goals, list) or not goals or not all(isinstance(g, dict) for g in goals):
        _fail(f'{block}.goals must be a list of {{"id", "learn"}} objects, at least one: what the user wants to '
              "find out")
    for g in goals:
        gid = _guide_id(g.get("id"), "goal", f"{block}.goals", seen)
        if set(g) - set(GOAL_FIELDS):
            _fail(f"goal {gid}: unknown fields: {', '.join(sorted(set(g) - set(GOAL_FIELDS)))} (use "
                  f"{', '.join(GOAL_FIELDS)})")
        if not (isinstance(g.get("learn"), str) and g["learn"].strip()):
            _fail(f'goal {gid}: it needs "learn": what to find out, written as a question to settle and never as '
                  "something to prove")
    goal_ids = [g["id"] for g in goals]

    topics, seen = guide.get("topics"), set()
    if not isinstance(topics, list) or not topics or not all(isinstance(t, dict) for t in topics):
        _fail(f'{block}.topics must be a list of {{"id", "area", "opener"}} objects, at least one, in the order to '
              "open them")
    segments = {p.get("segment") for p in cfg.get("personas") or [] if p.get("segment")}
    for t in topics:
        tid = _guide_id(t.get("id"), "topic", f"{block}.topics", seen, NOT_TOPIC)
        where = f"topic {tid}:"
        if set(t) - set(TOPIC_FIELDS):
            _fail(f"{where} unknown fields: {', '.join(sorted(set(t) - set(TOPIC_FIELDS)))} (use "
                  f"{', '.join(TOPIC_FIELDS)})")
        if not (isinstance(t.get("area"), str) and t["area"].strip()):
            _fail(f'{where} it needs "area": a neutral name for the topic that the interviewer may say to raise it, '
                  'such as "collecting documents from clients"')
        if not (isinstance(t.get("opener"), str) and t["opener"].strip()):
            _fail(f'{where} it needs "opener": the first question of the topic, which is sent as written')
        served = t.setdefault("goals", [])
        if not isinstance(served, list) or not all(isinstance(g, str) for g in served):
            _fail(f'{where} "goals" must be a list of goal ids: the goals the topic serves')
        for g in served:
            if g not in goal_ids:
                _fail(f'{where} "goals" names "{g}", which is not a goal id (ids: {", ".join(goal_ids)})')
        if not _positive(t.setdefault("turns", DEFAULT_TOPIC_TURNS), whole=True):
            _fail(f'{where} "turns" must be a whole number, 1 or more: the most exchanges the topic gets (default '
                  f"{DEFAULT_TOPIC_TURNS})")
        only = t.setdefault("segments", None)
        if only is not None:
            if not isinstance(only, list) or not only or not all(isinstance(x, str) for x in only):
                _fail(f'{where} "segments" must be a list of segment names: the personas the topic is for. Leave it '
                      "out for a topic every persona gets")
            for name in only:
                if name not in segments:
                    _fail(f'{where} "segments" names "{name}", which no persona has'
                          + (f" (segments: {', '.join(sorted(segments))})" if segments else ""))

    turns = guide.setdefault("turns", DEFAULT_TURNS)
    if not _positive(turns, whole=True):
        _fail(f"{block}.turns must be a whole number, 1 or more: the most exchanges an interview gets (default "
              f"{DEFAULT_TURNS})")
    if turns < len(topics) + 2:
        _fail(f"{block}.turns is {turns}, but {plural(len(topics), 'topic')} "
              f"{agree(len(topics), 'needs', 'need')} at least {len(topics) + 2}: one exchange each, the opening and "
              "the close")
    return guide


def check_interview(cfg: dict):
    """Validate "interview", the guide of an interview study, and fill its defaults (module
    docstring, "Interview studies"). What depends on files and runners being there is
    interview_problems()'s to say."""
    if any(e["runner"] is None for e in model_entries(cfg)):
        _fail("an interview study cannot run in native mode: the launcher carries every turn between the two "
              'sessions, each through its runner. Set a study-level "runner", or give every model entry one')
    if "interview" not in cfg:
        _fail('an interview study needs "interview": the guide, an object with '
              f"{listed(list(GUIDE_KEYS[:4]))}, and {listed(list(GUIDE_KEYS[4:]))} when the defaults do not suit")
    guide = check_guide(cfg, "interview")
    if not isinstance(guide.setdefault("situation_card", True), bool):
        _fail("interview.situation_card must be true or false: whether each participant writes its situation card "
              "before the first question")
    terms = cfg["leak_terms"]
    if not isinstance(terms, list) or not all(isinstance(t, str) and t.strip() for t in terms):
        _fail('"leak_terms" must be a list of words or phrases, none of them empty: every question is searched for '
              "each before it is delivered, and an empty one is in every question")
    taken = [p["id"] for p in cfg.get("personas") or [] if p["id"].lower() == "interviewer"]
    if taken:
        _fail(f'the persona id "{taken[0]}" is taken: the launcher names each interviewer\'s entry '
              f'"{interviewer_id("<run id>")}". Give the persona another id')


def guide(cfg: dict, pid: str, block: str = "interview") -> dict:
    """The guide as one persona's interview has it, the one reading of it: {"about", "turns",
    "card", "goals", "topics"}.

    "topics" are the topics that persona gets, in the order written: every topic without
    "segments", and one with it when the persona's segment is among them. Each is as
    check_guide() left it, so it has its cap, "turns". "goals" are the goals those topics leave
    the interviewer: every goal but one that only topics kept from this persona serve, since a
    goal with no topic to pursue it under would be pursued anyway. "turns" is the interview's
    cap, "card" whether the participant writes a situation card, and "about" the purpose the
    interviewer may state. block is "interview", or "debrief" for the guide of a debrief, which
    has no card and no "about".
    """
    held = cfg[block]
    segment = next((p.get("segment") for p in cfg["personas"] if p["id"] == pid), None)
    topics = [t for t in held["topics"] if t["segments"] is None or segment in t["segments"]]
    kept = {g for t in topics for g in t["goals"]}
    elsewhere = {g for t in held["topics"] for g in t["goals"]} - kept
    return {"about": held.get("about"), "turns": held["turns"],
            "card": block == "interview" and held["situation_card"],
            "goals": [g for g in held["goals"] if g["id"] not in elsewhere], "topics": topics}


def interview_problems(cfg: dict) -> list[str]:
    """What would spoil an interview study's interviews as study.json stands, each a sentence: a
    "leak_terms" entry, ignoring case, in something the interviewer is given to say (the purpose,
    a goal, a topic's opener or its area), and a persona that "segments" leaves with no topic.
    Empty for a study of another type. The scaffold, the plan and every command that starts an
    interview ask this, so an archived study still loads. A runner that does not exist is said
    by runners.get(), which exits, as for every study."""
    if cfg["type"] != "interview":
        return []
    held, out = cfg["interview"], []
    said = [("interview.about", "it", held["about"])]
    said += [(f"goal {g['id']}", 'its "learn"', g["learn"]) for g in held["goals"]]
    said += [(f"topic {t['id']}", f"its {part}", t[part]) for t in held["topics"] for part in ("opener", "area")]
    for where, what, text in said:
        found = next((term for term in cfg["leak_terms"] if term.lower() in text.lower()), None)
        if found:
            out.append(f'{where}: {what} holds the leak term "{found}". The interviewer would say it. Reword it.')
    for p in cfg["personas"]:
        if not guide(cfg, p["id"])["topics"]:
            out.append(f'persona {p["id"]} (segment "{p.get("segment", "")}") is left with no topic: every topic is '
                       'limited to other segments. Add its segment to a topic\'s "segments", or take the persona '
                       "out.")
    return out


def concept_kind(c: dict) -> str:
    return c.get("kind", "site")


def url_pages(c: dict) -> list[dict]:
    """The pages of a "url" concept, [{"name", "url"}, ...], home page first: its "pages", or its
    one "url" as the page "index"."""
    return c["pages"] if "pages" in c else [{"name": "index", "url": c["url"]}]


def check_concepts(cfg: dict):
    """Validate the shape of every concept for its kind. Whether a folder or a file exists is
    checked when it is needed (init_study.py, capture.py), so that an archived study, whose
    sources may be gone, still loads."""
    concepts = cfg["concepts"]
    if not isinstance(concepts, list) or not all(isinstance(c, dict) for c in concepts):
        _fail('"concepts" must be a list of objects')
    seen = set()
    for c in concepts:
        cid = c.get("id")
        if not (isinstance(cid, str) and cid.strip()):
            _fail(f'every concept needs an "id": {json.dumps(c)} has none')
        if name_problem(cid) or "--" in cid:
            _fail(f'the concept id {json.dumps(cid)} {name_problem(cid) or "must not contain two hyphens in a row"}, '
                  "because the archive names a folder after it, and its screenshots <id>--<page>")
        if cid.lower() in seen:
            _fail(f'two concepts have the id "{cid}". Ids must be unique, ignoring case, because key.md, the '
                  "labels and the archive's folders go by them")
        seen.add(cid.lower())
        where, kind = f"concept {cid}:", concept_kind(c)

        def text(key):
            return isinstance(c.get(key), str) and bool(c[key].strip())

        def only(*allowed):
            for key in ("path", "url", "pages", "files"):
                if key in c and key not in allowed:
                    hint = (f'. Add "kind": "{"url" if key in ("url", "pages") else "files"}" if that is what it is'
                            if kind == "site" and "kind" not in c else "")
                    _fail(f'{where} "{key}" does not belong to a concept of kind "{kind}"{hint}')

        def states(pages=None):
            """Check the concept's states, each of which capture.py writes to the folder
            <page>@<name>. pages: the names of the concept's pages, when study.json gives them."""
            listed, folders = c.get("states", []), set()
            if not isinstance(listed, list) or not all(isinstance(st, dict) for st in listed):
                _fail(f'{where} "states" must be a list of {{"name", "page", "js"}} objects')
            for st in listed:
                name, page = st.get("name"), st.get("page", "index")
                if not (isinstance(name, str) and PAGE_NAME.fullmatch(name)):
                    _fail(f"{where} the state name {json.dumps(name)} must be letters, digits, hyphens and "
                          "underscores only, because it names a folder that panellists see")
                if not isinstance(page, str) or (pages is not None and page not in pages):
                    _fail(f"{where} a state names the page {json.dumps(page)}, which is not one of its pages"
                          + (f" ({', '.join(pages)})" if pages else ""))
                if not (isinstance(st.get("js"), str) and st["js"].strip()):
                    _fail(f'{where} the state "{name}" needs "js": the script that sets it on the page')
                if (page, name) in folders:
                    _fail(f'{where} two states of the page "{page}" have the name "{name}", and each is captured '
                          "to a folder of that name")
                folders.add((page, name))

        if kind not in KINDS:
            _fail(f'{where} unknown "kind" {json.dumps(kind)} (use {", ".join(KINDS[:-1])} or {KINDS[-1]})')
        if kind == "site":
            only("path")
            if not text("path"):
                _fail(f'{where} a site concept needs "path": the folder that holds its index.html')
            states()
        elif kind == "url":
            only("url", "pages")
            if ("url" in c) == ("pages" in c):
                _fail(f'{where} a url concept needs "pages": [{{"name": "index", "url": "https://..."}}, ...], '
                      'or "url" alone for a concept of one page, and not both')
            if "url" in c and not text("url"):
                _fail(f'{where} "url" must be an address')
            pages = url_pages(c)
            if not isinstance(pages, list) or not pages or not all(
                    isinstance(p, dict) and set(p) == {"name", "url"} and all(isinstance(v, str) for v in p.values())
                    for p in pages):
                _fail(f'{where} "pages" must be a list of {{"name", "url"}} objects, the home page first')
            names = [p["name"] for p in pages]
            for name in names:
                if not PAGE_NAME.fullmatch(name):
                    _fail(f'{where} the page name {json.dumps(name)} must be letters, digits, hyphens and '
                          "underscores only, because it names a folder that panellists see")
            if names[0] != "index":
                _fail(f'{where} its first page must be the home page, named "index" (it is "{names[0]}"): the '
                      "instructions tell panellists that the home page is always index")
            if len(set(names)) < len(names):
                _fail(f"{where} two pages have the same name")
            for p in pages:
                try:
                    parts = urlsplit(p["url"])
                    ok = parts.scheme in ("http", "https") and bool(parts.hostname)
                except ValueError:
                    ok = False
                if not ok:
                    _fail(f'{where} the address of page "{p["name"]}", {json.dumps(p["url"])}, must be a full '
                          "http:// or https:// URL. A folder of HTML files is a site concept, with \"path\"")
            states(names)
        else:
            only("path", "files")
            if ("path" in c) == ("files" in c):
                _fail(f'{where} a files concept needs "files": the images and PDFs in the order to go through '
                      'them, or "path": a folder whose images and PDFs are taken in name order, and not both')
            if "path" in c and not text("path"):
                _fail(f'{where} "path" must be a folder')
            if "files" in c:
                files = c["files"]
                if not isinstance(files, list) or not files or not all(isinstance(f, str) and f.strip() for f in files):
                    _fail(f'{where} "files" must be a list of file paths, in the order to go through them')
                for f in files:
                    if Path(f).suffix.lower() not in (*IMAGE_TYPES, *DOCUMENT_TYPES):
                        _fail(f'{where} "{f}" is not a file type a panel can review. {SUPPORTED_FILES}')
                if cfg["materials"] == "text" and not any(Path(f).suffix.lower() in DOCUMENT_TYPES for f in files):
                    _fail(f"{where} {NO_TEXT}")
            if c.get("states"):
                _fail(f'{where} "states" run a script on a page, and a files concept has no page to run one on')
    pinned = cfg.get("labels")
    if pinned:  # {label: concept id}, in place of the shuffle (label_map())
        if not isinstance(pinned, dict):
            _fail('"labels" must be an object, {label: concept id}')
        for label in pinned:
            if not LABEL.fullmatch(label):
                _fail(f"labels: the label {json.dumps(label)} must be letters and digits only, because it names a "
                      'folder and is what a panellist writes after "Concept"')
        if len({label.lower() for label in pinned}) < len(pinned):
            _fail("labels: two labels differ only in case, and each names a folder")
        if sorted(map(str, pinned.values())) != sorted(c["id"] for c in concepts):
            _fail(f"labels: every concept id needs one label, and no label another id (ids: "
                  f"{', '.join(c['id'] for c in concepts)})")


SUPPORTED_FILES = (f"Images: {', '.join(t[1:] for t in IMAGE_TYPES)}. Documents: "
                   f"{', '.join(t[1:] for t in DOCUMENT_TYPES)}.")
NO_TEXT = ('it has only images, and a text-only study ("materials": "text") reads text alone. Give it a PDF, take '
           'the concept out, or review it with "materials": "full"')


def apply_kinds(cfg: dict, asked_to_browse: bool):
    """Set what follows from the concepts' kinds, and cfg["_browse_off"]: why the study does not
    browse although study.json did not say "browse": false, for the plan to say, else None.

    "url": the study has a "url" concept and study.json does not say "browse": true. A live page
    is opened by panellists only when the study sets it. "files": every concept is of kind
    "files", which has nothing to open, so the study never browses whatever "browse" says. A
    text-only study has its own reason (apply_materials) and none here.
    """
    kinds = {concept_kind(c) for c in cfg["concepts"]}
    cfg["_browse_off"] = None
    if cfg["materials"] == "text" or not cfg["browse"]:
        return
    if kinds == {"files"}:
        cfg["_browse_off"], cfg["browse"] = "files", False
    elif "url" in kinds and not asked_to_browse:
        cfg["_browse_off"], cfg["browse"] = "url", False


def natural(name: str) -> list:
    """A sort key that puts screen-9 before screen-10."""
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", name)]


def concept_items(cfg: dict, c: dict) -> tuple[list[tuple[str, Path]], list[Path]]:
    """The items of a "files" concept, [(folder name, source file), ...] in the order to go
    through them, and the files left out: the images, in a text-only study, which reads text.

    Folder names are item-01, item-02 and so on, never the file names, which would leak intent
    as a concept's folder name does. Exits, naming the concept, when its folder or one of its
    files is missing, when a file is of no supported type, or when nothing is left to review.
    """
    where = f"Concept {c['id']}:"
    if "_files" in c:
        files = c["_files"]
    else:
        folder = c["_path"]
        if not folder.is_dir():
            raise SystemExit(f"{where} no folder {folder}")
        files = sorted((f for f in folder.iterdir() if f.is_file()
                        and f.suffix.lower() in (*IMAGE_TYPES, *DOCUMENT_TYPES)), key=lambda f: natural(f.name))
        if not files:
            raise SystemExit(f"{where} no image or PDF in {folder}. {SUPPORTED_FILES}")
    for f in files:
        if not f.is_file():
            raise SystemExit(f"{where} no file {f}")
        if f.suffix.lower() not in (*IMAGE_TYPES, *DOCUMENT_TYPES):
            raise SystemExit(f"{where} {f.name} is not a file type a panel can review. {SUPPORTED_FILES}")
    text_only = cfg["materials"] == "text"
    kept = [f for f in files if not text_only or f.suffix.lower() in DOCUMENT_TYPES]
    if not kept:
        raise SystemExit(f"{where} {NO_TEXT}.")
    return [(f"item-{i:02d}", f) for i, f in enumerate(kept, start=1)], [f for f in files if f not in kept]


def concept_pages(cfg: dict, c: dict, site: Path | None = None) -> list[str] | None:
    """The names of a concept's page folders under panel/materials, without its states: the
    HTML files of a site (of the folder site, default its source), the page names of a url
    concept, the items of a files concept. None when the source cannot be read yet."""
    kind = concept_kind(c)
    if kind == "url":
        return [p["name"] for p in url_pages(c)]
    try:
        if kind == "files":
            return [name for name, _ in concept_items(cfg, c)[0]]
        return sorted(p.stem for p in (site or c["_path"]).glob("*.html"))
    except SystemExit:
        return None


def concept_folders(cfg: dict, c: dict, site: Path | None = None) -> list[str] | None:
    """The name of every folder capture.py makes for a concept under panel/materials: its pages
    (concept_pages()) and <page>@<state> for each state of a page it has. None when the source
    cannot be read yet. capture.py captures these and removes any other, and the plan holds a
    run back until each one is there (launch_plan.materials())."""
    pages = concept_pages(cfg, c, site)
    if pages is None:
        return None
    return pages + [f"{st.get('page', 'index')}@{st['name']}" for st in c.get("states", [])
                    if st.get("page", "index") in pages]


def source_problem(cfg: dict, c: dict) -> str | None:
    """Why a concept cannot be scaffolded or captured as its source stands, else None: a site
    folder with no index.html or with a page file whose name cannot name a folder, or what
    concept_items() says of a "files" concept. A url concept has no source to read."""
    kind = concept_kind(c)
    if kind == "site" and not (c["_path"] / "index.html").exists():
        return f"Concept {c['id']}: no index.html in {c['_path']}"
    if kind == "site":  # a page is captured to a folder named after its file: "...html" would be the folder above
        odd = sorted(p.name for p in c["_path"].glob("*.html") if name_problem(p.stem))
        if odd:
            return (f"Concept {c['id']}: the page file {json.dumps(odd[0])} in {c['_path']} cannot be captured, "
                    f"because its capture goes to a folder of that name, which {NAME_RULE}. Rename it")
    if kind == "files":
        try:
            concept_items(cfg, c)
        except SystemExit as err:
            return str(err)
    return None


def poppler_needed(cfg: dict) -> tuple[list[str], list[str]]:
    """(the Poppler tools capture.py needs for this study's PDFs, the ids of the concepts that
    have one): pdftotext for the text, and pdftoppm for the page images of a full-materials
    study. Both empty when no concept has a PDF that can be found."""
    with_pdf = []
    for c in cfg["concepts"]:
        if concept_kind(c) == "files":
            try:
                items = concept_items(cfg, c)[0]
            except SystemExit:
                continue
            if any(f.suffix.lower() in DOCUMENT_TYPES for _, f in items):
                with_pdf.append(c["id"])
    tools = ["pdftotext", *(["pdftoppm"] if cfg["materials"] == "full" else [])] if with_pdf else []
    return tools, with_pdf


def poppler_missing(cfg: dict) -> str | None:
    """What to tell the lead when the study has a PDF to capture and Poppler is not installed,
    else None."""
    tools, with_pdf = poppler_needed(cfg)
    missing = [t for t in tools if not shutil.which(t)]
    if not missing:
        return None
    return (f"Poppler is required for the {agree(len(with_pdf), 'PDF')} of {agree(len(with_pdf), 'concept')} "
            f"{', '.join(with_pdf)}: {' and '.join(missing)} {agree(len(missing), 'is', 'are')} not on PATH. "
            "Install Poppler (the package is poppler-utils on Debian and Ubuntu, poppler on Homebrew and Arch)")


KIND_NAMES = {"site": "site", "url": "live URL", "files": "files"}  # how the lead's files name a concept's kind


def read_forms(study_dir: Path) -> dict[str, str]:
    """The forms record, forms.json: {concept id: form} for the "files" concepts whose form was
    known when it was written. Empty when there is none, as in a study scaffolded before the
    record existed, and an entry that is not one of FILE_FORMS is left out."""
    try:
        held = json.loads((Path(study_dir) / FORMS).read_text())
    except (OSError, ValueError):
        return {}
    return {cid: form for cid, form in held.items() if form in FILE_FORMS} if isinstance(held, dict) else {}


def file_forms(cfg: dict) -> dict[str, str]:
    """{concept id: form} for each "files" concept whose form is known: "image files", "PDF
    files" or "image and PDF files", worked out from its source files (the images a text-only
    study leaves out among them), or taken from the forms record when they can no longer be read,
    as in an archived round or once the sources have moved."""
    recorded, forms = read_forms(cfg["_dir"]), {}
    for c in cfg["concepts"]:
        if concept_kind(c) != "files":
            continue
        try:
            kept, left_out = concept_items(cfg, c)
        except SystemExit:
            if c["id"] in recorded:
                forms[c["id"]] = recorded[c["id"]]
            continue
        pdf = {f.suffix.lower() in DOCUMENT_TYPES for f in [*(f for _, f in kept), *left_out]}
        forms[c["id"]] = " and ".join(["image"] * (False in pdf) + ["PDF"] * (True in pdf)) + " files"
    return forms


def write_forms(study_dir: Path, forms: dict[str, str]):
    """Write the forms record of a study directory, or of an archive of one: file_forms() as it
    stands. With no form to record the file is removed, so none outlives the concepts it was for.
    Lead only, like key.md: it sits beside study.json and never under panel/."""
    path = Path(study_dir) / FORMS
    if forms:
        write_atomic(path, json.dumps(forms, indent=2) + "\n")
    else:
        path.unlink(missing_ok=True)


def concept_forms(cfg: dict) -> dict[str, str]:
    """{label: the form the concept reached the panel in}, in label order: "site", "live URL", and
    for a "files" concept what file_forms() knows of it, "image files", "PDF files" or "image and
    PDF files" ("files" when neither its source nor the forms record can say). For the lead's
    files only: a panellist is never told what a concept is made of beyond what its folders show."""
    known = file_forms(cfg)
    return {label: known.get(c["id"], KIND_NAMES[concept_kind(c)]) if concept_kind(c) == "files"
            else KIND_NAMES[concept_kind(c)] for label, c in label_map(cfg).items()}


def mixed_forms(cfg: dict) -> dict[str, str] | None:
    """concept_forms() when the concepts did not all reach the panel in one form, else None. A
    site and a live URL are captured the same way, as sheets and page text, and count as one
    form. A PDF, an image and a captured page do not: a file cannot be scrolled or clicked and
    shows a phone only if it holds one, so part of any difference in score is the format. In a
    text-only study every concept reached the panel as text, and no factor that needs the design
    is scored, so it has one form."""
    forms = concept_forms(cfg)
    paged = (KIND_NAMES["site"], KIND_NAMES["url"])
    mixed = len({"pages" if form in paged else form for form in forms.values()}) > 1
    return forms if mixed and cfg["materials"] != "text" else None


def form_caution(cfg: dict) -> dict | None:
    """What the analysis and the briefs say of a study whose concepts differ in form
    (mixed_forms()), else None: "forms" (label -> form), "concepts", the same in a phrase ("A is
    a live URL and B is PDF files"), "factors", the labels of the scored factors that need the
    design ("needs_design"), which a format moves most, and "exposed", the clause that names them."""
    forms = mixed_forms(cfg)
    if not forms:
        return None
    named = [f"{label} is {'a ' if form in (KIND_NAMES['site'], KIND_NAMES['url']) else ''}{form}"
             for label, form in forms.items()]
    factors = [f["label"] for f in cfg["factors"] if needs_design(f)]
    listed = ", ".join(factors[:-1]) + (" and " if factors[:-1] else "") + (factors[-1] if factors else "")
    return {"forms": forms, "concepts": ", ".join(named[:-1]) + " and " + named[-1], "factors": factors,
            "exposed": (f"{listed} {agree(len(factors), 'is the factor', 'are the factors')} most exposed" if factors
                        else "Any score that turns on how a concept looks or behaves is exposed")}


def single_concept(cfg: dict) -> bool:
    """Whether the study has one concept: there is then nothing to rank or compare, so the
    templates ask for no ranking and no score summary, and the checks and analysis expect none."""
    return len(cfg["concepts"]) == 1


def ranked(cfg: dict) -> bool:
    """Whether a run of the study ranks what it went through and has a review order: a review of
    more than one concept. The tasks of a usability study are attempted in the order written and
    are not ranked against each other."""
    return cfg["type"] == "review" and not single_concept(cfg)


def unit_order(cfg: dict, pid: str) -> list[str]:
    """The order a persona goes through the study's units in: its review order (review_order()),
    the tasks as study.json lists them, which may build on each other, or the topics of its own
    guide in the order written (guide())."""
    if cfg["type"] == "interview":
        return [t["id"] for t in guide(cfg, pid)["topics"]]
    units = study_units(cfg)
    return units if cfg["type"] == "usability" else review_order(cfg, pid, units)


def study_brief_copy(study_dir: Path, files) -> Path | None:
    """The first of files that is the study brief or a copy of it, else None: a path named
    study-brief.md in any case, whether or not it exists, a path that resolves to the study's own
    brief (a link to it), or a file with the brief's content."""
    brief = Path(study_dir) / STUDY_BRIEF
    content = brief.read_bytes() if brief.is_file() else b""
    for f in map(Path, files):
        if f.name.lower() == STUDY_BRIEF or (brief.exists() and f.resolve() == brief.resolve()):
            return f
        if content.strip() and f.is_file() and f.stat().st_size == len(content) and f.read_bytes() == content:
            return f
    return None


def variants(cfg: dict) -> dict[str, str]:
    """{variant persona id: its parent's id}, in persona order, from each persona's "variant_of".

    A variant is its parent with one trait changed, written by the lead. It is a persona like
    any other, with its own runs and files, and it reviews in its parent's order (review_order):
    only analyze.py pairs it with its parent. Exits when a "variant_of" names no persona, the
    persona itself, or another variant.
    """
    found = {p["id"]: p["variant_of"] for p in cfg.get("personas") or [] if p.get("variant_of") is not None}
    ids = {p["id"] for p in cfg.get("personas") or []}
    for pid, parent in found.items():
        where = f'persona {pid}: "variant_of"'
        if parent == pid:
            _fail(f"{where} names the persona itself")
        if not isinstance(parent, str) or parent not in ids:
            _fail(f"{where} {json.dumps(parent)} is not a persona id (ids: {', '.join(sorted(ids))})")
        if parent in found:
            _fail(f"{where} names {parent}, which is itself a variant of {found[parent]}. Name the persona both "
                  "are variants of")
    return found


def needs_design(factor: dict) -> bool:
    """Whether a factor can only be judged by seeing the page: its "needs_design", or for a
    factor that does not say, whether its key is one of DESIGN_FACTORS."""
    return factor.get("needs_design", factor["key"] in DESIGN_FACTORS)


def apply_materials(cfg: dict, asked_to_browse: bool):
    """Make cfg what a "materials": "text" study runs with, and set cfg["_text_only"]: None for a
    full-materials study, else what was changed, for the plan to say.

    A text-only study scores no factor that needs the design, takes those factors out of
    "fit_factors" too, and never browses, whatever "browse" says. Every script takes its factors
    from cfg["factors"], so the templates, parsers, score columns and analysis follow.
    "_text_only" holds "dropped_factors" and "dropped_fit_factors" (factor keys), "fit_factors"
    (the ones in force: the default fit factors still scored when every one named was dropped) and
    "browse_ignored" (study.json says "browse": true).
    """
    for f in cfg["factors"]:
        if not isinstance(f.get("needs_design", False), bool):
            _fail(f'factor "{f["key"]}": "needs_design" must be true or false: whether the factor can only '
                  "be judged by seeing the page")
    cfg["_text_only"] = None
    if cfg["materials"] != "text":
        return
    dropped = [f["key"] for f in cfg["factors"] if needs_design(f)]
    if "overall" in dropped:
        _fail('the factor "overall" cannot have "needs_design": a text-only study would have no verdict to rank by')
    cfg["factors"] = [f for f in cfg["factors"] if f["key"] not in dropped]
    named = cfg["fit_factors"]
    fit = [k for k in named if k not in dropped]
    if named and not fit:
        fit = [k for k in DEFAULT_FIT_FACTORS if k in factor_keys(cfg)]
    cfg["_text_only"] = {"dropped_factors": dropped, "dropped_fit_factors": [k for k in named if k in dropped],
                         "fit_factors": fit, "browse_ignored": asked_to_browse}
    cfg["fit_factors"], cfg["browse"] = fit, False


def sites_dir(cfg: dict, used: bool = True) -> Path:
    """Where the neutral copies of the "site" concepts are: panel/sites in a study whose
    panellists browse, which is where a run opens a page from, and <study>/sites in every other.
    A copy is the page source under its own file names, and a run may read anything under
    panel/, so it is there only while the browser needs it. cfg["browse"] alone decides:
    load_study() has turned it off for a text-only study, for a "url" concept without "browse":
    true, and for a study of files alone. used=False gives the other of the two folders, where a
    scaffold made under the other setting left its copies: init_study.py clears it."""
    return cfg["_dir"] / ("panel/sites" if cfg["browse"] == used else "sites")


def factor_keys(cfg: dict) -> list[str]:
    return [f["key"] for f in cfg["factors"]]


def model_entry(raw, default_runner: str | None = None, where: str = "models") -> dict:
    """Normalise one model entry, a bare model name or an object, to {key, runner, model, effort}.

    runner None means native mode, model None the runner's default model, effort None unset.
    key is None when the entry gives none and its model name cannot stand in for one.
    """
    shown = json.dumps(raw)
    if isinstance(raw, str):
        raw = {"model": raw}
    if not isinstance(raw, dict):
        _fail(f"{where}: {shown} must be a model name or an object")
    if set(raw) - set(ENTRY_FIELDS):
        _fail(f"{where}: {shown} has unknown fields: {', '.join(sorted(set(raw) - set(ENTRY_FIELDS)))} "
              f"(use {', '.join(ENTRY_FIELDS)})")
    e = {f: raw.get(f) for f in ENTRY_FIELDS}
    for f, v in e.items():
        if v is not None and not (isinstance(v, str) and v):
            _fail(f'{where}: {shown}: "{f}" must be a non-empty string')
    if e["key"] is not None and not KEY_RE.fullmatch(e["key"]):
        _fail(f'{where}: {shown}: "key" must be letters and digits only, '
              "because file names and run ids split on hyphens")
    if e["key"] is None and e["model"] and KEY_RE.fullmatch(e["model"]):
        e["key"] = e["model"]
    e["runner"] = e["runner"] or default_runner
    return e


def model_entries(cfg: dict) -> list[dict]:
    """The study's model entries, normalised: one {key, runner, model, effort} per "models" item."""
    if not isinstance(cfg["models"], list) or not cfg["models"]:
        _fail('"models" must be a list with at least one entry')
    entries, seen = [], set()
    for raw in cfg["models"]:
        e = model_entry(raw, cfg.get("runner"))
        shown = json.dumps(raw)
        if e["key"] is None:
            fix = f': write it as {{"key": "<short name>", "model": {shown}}}' if isinstance(raw, str) else ""
            _fail(f'models: {shown} needs a "key" of letters and digits only, because its model name '
                  f"cannot be used in file names and run ids{fix}")
        if e["key"].lower() in seen:
            _fail(f'models: {shown} repeats the key "{e["key"]}". Keys must be unique within a study, '
                  "ignoring case, because they name files")
        if e["runner"] is None and e["model"] is None:
            _fail(f'models: {shown} needs a "model", or a "runner" whose default model it should use')
        seen.add(e["key"].lower())
        entries.append(e)
    native = [e["key"] for e in entries if e["runner"] is None]
    if native and len(native) < len(entries):
        _fail(f"models mix native entries ({', '.join(native)}) with runner entries "
              f"({', '.join(e['key'] for e in entries if e['runner'])}). A study is one or the other: "
              'set a study-level "runner", or give every entry one')
    return entries


def model_keys(cfg: dict) -> list[str]:
    return [e["key"] for e in model_entries(cfg)]


def limits_for(cfg: dict, role: str = "panellist", key: str | None = None) -> dict:
    """{"minutes", "budget_usd"} in force: limits.run for a panellist run, with that model key's
    limits.overrides merged over it, where a usability run's "minutes" default to what its tasks
    permit (usability_minutes()) and an interview's participant has INTERVIEW_RUN where
    study.json gives none; the job's share of limits.synthesis (synthesis_share) for
    an analyst or writer job; limits.followup for "followup", what each run asked a follow-up
    question may use for that question, apart from its run limits, and limits.debrief for
    "debrief" the same way, for each side of a debrief; limits.interviewer for "interviewer",
    each interviewer over its whole interview; and for "turn" {"minutes"} alone, limits.turn:
    the most one turn of either side of a conversation may take."""
    limits = cfg.get("limits") or {}
    if role in ("followup", "debrief", "interviewer", "turn"):
        return {**DEFAULT_LIMITS[role], **limits.get(role, {})}
    if role == "panellist":
        timed = ({"minutes": usability_minutes(cfg)} if cfg.get("type") == "usability"
                 else INTERVIEW_RUN if cfg.get("type") == "interview" else {})
        return {**DEFAULT_LIMITS["run"], **timed, **limits.get("run", {}), **limits.get("overrides", {}).get(key, {})}
    if role in JOB_ROLES:
        return synthesis_share(cfg)
    raise ValueError(f"unknown role {role!r}")


def synthesis_pool(cfg: dict) -> dict:
    """limits.synthesis in force, {"minutes", "budget_usd"}: "minutes" for each analyst or writer
    job, "budget_usd" one pool for all of them. Panellist runs never spend it."""
    return {**DEFAULT_LIMITS["synthesis"], **(cfg.get("limits") or {}).get("synthesis", {})}


def synthesis_share(cfg: dict) -> dict:
    """What one analyst or writer job may use over all its attempts, {"minutes", "budget_usd"}.

    The pool's budget is divided equally among the jobs study.json plans, the analysts and the
    writer, and each share is a cap. A share is rounded down to a millionth of a dollar, so the
    caps never add up to more than the pool. "minutes" is the pool's, for each job.
    """
    pool = synthesis_pool(cfg)
    jobs = (cfg.get("synthesis") or {}).get("analysts", 1) + 1
    return {"minutes": pool["minutes"], "budget_usd": math.floor(round(pool["budget_usd"] / jobs * 1e6, 3)) / 1e6}


def synthesis_jobs(cfg: dict) -> list[dict]:
    """The analyst and writer jobs study.json plans, each as its runs.json job entry before a
    launcher has touched it (fields in the module docstring).

    With two analysts the personas are split into halves in persona id order, the first taking
    the extra one, so each analyst reads every model and replicate of its personas. A single
    analyst writes analysis/qual-1.md too. A job whose synthesis.analyst or synthesis.writer
    entry is missing has no runner and no model: there is no default, and a launcher refuses it.
    """
    syn = cfg.get("synthesis") or {}
    n = syn.get("analysts", 1)
    ids = sorted((p["id"] for p in cfg["personas"]),
                 key=lambda pid: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", pid)])
    if len(ids) < n:
        _fail(f"synthesis.analysts is {n}, but the study has {plural(len(ids), 'persona')} to split between them"
              + (": set it to 1, or add a persona" if ids else ": add its personas first"))
    cut = math.ceil(len(ids) / n)
    entry = {role: model_entry(syn[role], cfg.get("runner"), f"synthesis.{role}") if role in syn
             else dict.fromkeys(ENTRY_FIELDS) for role in JOB_ROLES}
    jobs = [{"run": f"analyst-{i}", "role": "analyst", "name": f"Analyst {i} of {n}", **entry["analyst"],
             "personas": own, "file": f"analysis/qual-{i}.md", "prompt": f"prompts/analyst-{i}.md"}
            for i, own in enumerate((ids[:cut], ids[cut:])[:n], start=1)]
    return [*jobs, {"run": "writer", "role": "writer", "name": "Synthesis writer", **entry["writer"],
                    "file": "analysis/SYNTHESIS.md", "prompt": "prompts/writer.md"}]


def runner_concurrency(cfg: dict, runner_name: str, default: int) -> int:
    return (cfg.get("runners") or {}).get(runner_name, {}).get("concurrency", default)


def make_labels(n: int, style: str) -> list[str]:
    if style == "numbers":
        return [f"{i + 1:02d}" for i in range(n)]
    if n > 26:
        raise SystemExit("More than 26 concepts: use label_style 'numbers'")
    return list(string.ascii_uppercase[:n])


def label_map(cfg: dict) -> dict[str, dict]:
    """Deterministic neutral label -> concept. Shuffled with the study seed unless disabled."""
    concepts = list(cfg["concepts"])
    if cfg.get("labels"):  # explicit {"A": "<concept id>"} mapping, e.g. to reproduce an earlier study
        by_id = {c["id"]: c for c in concepts}
        return {label: by_id[cid] for label, cid in cfg["labels"].items()}
    if cfg["shuffle_labels"]:
        random.Random(f"{cfg['seed']}:labels").shuffle(concepts)
    labels = make_labels(len(concepts), cfg["label_style"])
    return dict(zip(labels, concepts))


def review_order(cfg: dict, pid: str, labels: list[str]) -> list[str]:
    """Per-persona random order, identical across that persona's models and replicates. A
    variant reviews in its parent's order, so that order is no part of the difference between
    the two."""
    order = list(labels)
    random.Random(f"{cfg['seed']}:order:{variants(cfg).get(pid, pid)}").shuffle(order)
    return order


def shared_order(cfg: dict) -> str | None:
    """What to tell the lead when every persona reviews in the same order, else None. The seeded
    shuffle can land two or three personas on one order, and order is then confounded with
    concept: whatever is read first is always the same concept. A variant takes its parent's
    order on purpose, so variants are not counted, and one concept has no order."""
    labels, own = list(label_map(cfg)), [p["id"] for p in cfg["personas"] if p["id"] not in variants(cfg)]
    orders = {tuple(review_order(cfg, pid, labels)) for pid in own}
    if len(labels) < 2 or len(own) < 2 or len(orders) > 1:
        return None
    return (f"every persona reviews in the same order ({', '.join(orders.pop())}), so order is confounded with "
            "concept: the concept read first is the same for everyone, and the order effect in the analysis measures "
            f'nothing. Set another "seed" in study.json (it is {json.dumps(cfg["seed"])}) and scaffold again '
            "(init_study.py --force) before any run. A new seed reshuffles the labels too, unless study.json pins "
            "them.")


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def persona_slug(p: dict) -> str:
    return p.get("slug") or slugify(p["name"])


def run_id(pid: str, key: str, replicate: int = 1) -> str:
    """<pid>-<key>, or <pid>-<key>-r<n> for replicate n > 1."""
    return f"{pid}-{key}" + (f"-r{replicate}" if replicate > 1 else "")


def persona_file(study_dir: Path, p: dict, key: str, replicate: int = 1) -> Path:
    name = f"{p['id']}-{persona_slug(p)}--{key}" + (f"-r{replicate}" if replicate > 1 else "")
    return Path(study_dir) / "panel" / "personas" / f"{name}.md"


def run_entry(study_dir: Path, p: dict, e: dict, replicate: int = 1, interview: bool = False) -> dict:
    """The runs.json entry of persona p on model entry e, before anything has started the run.
    interview: the entry of the participant of an interview, whose file is its turn log and
    which starts in a room of its own (module docstring, "Interview entries")."""
    rid = run_id(p["id"], e["key"], replicate)
    entry = {"run": rid, "persona": p["id"], "name": p["name"], "segment": p.get("segment", ""), **e,
             "replicate": replicate, "role": "panellist"}
    if interview:
        return {**entry, "interview": rid, "file": f"{INTERVIEWS}/{rid}.jsonl", "prompt": f"prompts/{rid}.md",
                "workdir": f"{ROOMS}/{rid}"}
    return {**entry, "file": str(persona_file(study_dir, p, e["key"], replicate).relative_to(study_dir)),
            "prompt": f"prompts/{rid}.md"}


def interviewer_id(run: str) -> str:
    """The id of the entry of the interviewer of a run."""
    return f"interviewer-{run}"


def interview_of(entry: dict) -> str:
    """The run id of the conversation an entry is a side of: its "interview", or for a finished
    run that is being debriefed, which has none, the run itself. It names the turn log."""
    return entry.get("interview") or entry["run"]


def interviewer_entry(cfg: dict, participant: dict) -> dict:
    """The runs.json entry of the interviewer of an interview, from its participant's entry,
    before anything has started it (module docstring, "Interview entries")."""
    rid = participant["run"]
    return {"run": interviewer_id(rid), "role": "interviewer", "interview": rid, "persona": participant["persona"],
            "name": f"Interviewer of {rid}", "segment": participant["segment"], **cfg["interview"]["interviewer"],
            "file": participant["file"], "prompt": f"prompts/{interviewer_id(rid)}.md",
            "workdir": f"{INTERVIEWER_DIR}/{rid}"}


def planned_runs(cfg: dict) -> list[dict]:
    """Every panellist run study.json plans, in the order init_study.py writes them to runs.json.
    In an interview study they are the participants' entries: planned_interviewers() has the
    others."""
    return [run_entry(cfg["_dir"], p, e, rep, cfg["type"] == "interview") for p in cfg["personas"]
            for e in model_entries(cfg) for rep in range(1, cfg["replicates"] + 1)]


def planned_interviewers(cfg: dict) -> list[dict]:
    """The interviewer's entry of every interview study.json plans, in the order of
    planned_runs(). Empty for a study of another type."""
    return [interviewer_entry(cfg, e) for e in planned_runs(cfg)] if cfg["type"] == "interview" else []


def render_template(name: str, **values) -> str:
    return string.Template((ASSETS / name).read_text()).substitute(**values)


def fill_brief(name: str, values: dict) -> str:
    """An assets/ brief with every <PLACEHOLDER> token replaced by its value.

    The tokens stay in the asset as written, because a lead fills the same ones by hand in
    native mode. A token alone on its line takes the line with it when its value is empty.
    Exits naming every token the brief holds that values does not, so a brief is never sent
    with a placeholder left in it. <NOTICE> is the synthetic panel notice unless values says
    otherwise.
    """
    text, values = (ASSETS / name).read_text(), {"NOTICE": NOTICE, **values}
    unfilled = sorted(set(PLACEHOLDER.findall(text)) - set(values))
    if unfilled:
        raise SystemExit(f"assets/{name} has placeholders with no value to fill them: "
                         f"{', '.join(f'<{t}>' for t in unfilled)}. Take them out of the brief, or write their "
                         "text into it.")
    lines = []
    for line in text.split("\n"):
        alone = PLACEHOLDER.fullmatch(line.strip())
        if not (alone and not str(values[alone.group(1)])):
            lines.append(PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), line))
    return "\n".join(lines)


def with_notice(text: str) -> str:
    """Markdown text carrying the synthetic panel notice: unchanged when it has the line anywhere,
    else with the line as a paragraph of its own under the heading the text opens with, or at the
    very top when it opens with anything else."""
    if NOTICE in text:
        return text
    lines = text.split("\n")
    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    at = first + 1 if first is not None and lines[first].startswith("#") else 0
    after = [] if at < len(lines) and not lines[at].strip() else [""]
    return "\n".join([*lines[:at], *([""] if at else []), NOTICE, *after, *lines[at:]])


def reply_document(text: str, start: str | None = None) -> str:
    """The document inside an agent's reply: everything from the first line matching the regex
    start (default: the first "# " heading), or the whole reply when no line matches, without
    the code fence a reply sometimes closes with."""
    lines = text.splitlines()
    pat = re.compile(start or r"^# ")
    first = next((i for i, line in enumerate(lines) if pat.search(line)), 0)
    return re.sub(r"\n```\s*$", "", "\n".join(lines[first:]).strip())


# ---------------------------------------------------------------- runs.json

def read_runs(study_dir: Path) -> list[dict]:
    """runs.json entries, with defaults filled for entries written before the newer fields."""
    path = Path(study_dir) / "runs.json"
    if not path.exists():
        raise SystemExit(f"No runs.json in {path.parent}: run init_study.py first")
    runs = json.loads(path.read_text())
    for r in runs:
        if r.get("role", "panellist") != "panellist":  # a job or an interviewer: written whole, with none of
            continue                                   # a panellist run's fields to fill in
        r.setdefault("key", r.get("model"))
        for k, v in RUN_DEFAULTS.items():
            r.setdefault(k, v)
    return runs


def not_written(path: Path, err: OSError) -> str:
    """What a script says when the system will not let it write one of its own files under the
    study directory, as a sandboxed shell tool does: one sentence that names the file and gives
    the system's reason. Never a traceback."""
    return f"The system refused to write {path} ({unread(err)})."


def output(path: Path, **how):
    """Open one of a script's output files for writing, in a folder that is made when it is not
    there. Where the system refuses either, the script ends with not_written()'s sentence and
    exit code 1."""
    try:
        Path(path).parent.mkdir(exist_ok=True)
        return open(path, "w", **how)
    except OSError as err:
        raise SystemExit(not_written(path, err))


def write_atomic(path: Path, text: str):
    """Replace a file in one step, so a reader or a killed writer never sees half of it."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def write_runs(study_dir: Path, runs: list[dict]):
    write_atomic(Path(study_dir) / "runs.json", json.dumps(runs, indent=2) + "\n")


def read_modifications(study_dir: Path) -> dict:
    """The modification record (module docstring): {"hashes", "changes"}, empty when no launcher
    has kept one for this study."""
    try:
        record = json.loads((Path(study_dir) / MODIFICATIONS).read_text())
    except (OSError, ValueError):
        record = {}
    return {"hashes": record.get("hashes") or {}, "changes": record.get("changes") or []}


def file_hash(study_dir: Path, path: Path) -> str | None:
    """SHA-256 of a persona file's content (persona_bytes()), None when there is no such file, or
    none that can be read as its run's own."""
    try:
        return hashlib.sha256(persona_bytes(study_dir, path)).hexdigest()
    except OSError:
        return None


def workdir(study_dir: Path, of: dict | str) -> Path:
    """The directory a run's or job's process works in. of is its runs.json entry, or a role.
    An entry that names a "workdir" works there, as each side of an interview does, in a folder
    of its own. Any other works where its role does, which is all a role alone can say: panel/
    for a panellist, the study directory for an analyst or the writer."""
    if isinstance(of, dict):
        if of.get("workdir"):
            return Path(study_dir) / of["workdir"]
        of = of.get("role") or "panellist"
    return Path(study_dir) / "panel" if of == "panellist" else Path(study_dir)


def sessions_of(entry: dict) -> list[str]:
    """Every harness session id recorded for a run or job, over all its attempts."""
    ids = [entry.get("session"), *(a.get("session") for a in entry.get("attempts") or []),
           *(entry.get("sessions") or {})]
    return list(dict.fromkeys(i for i in ids if i and not i.startswith("attempt ")))


def held_sessions(study_dir: Path, runs: list[dict], now: float) -> list[dict]:
    """The sessions that runs.json entries record and that their harnesses still hold, neither
    purged nor lost nor found unsaved, each as an entry of the earlier-sessions record (module docstring)."""
    return [{"run": e["run"], "runner": e["runner"], "session": session,
             "workdir": str(workdir(study_dir, e)), "replaced": round(now)}
            for e in runs if e.get("runner")
            for session in sessions_of(e)
            if session not in {**(e.get("purged") or {}), **(e.get("lost") or {}), **(e.get("unsaved") or {})}]


def read_earlier_sessions(study_dir: Path) -> list[dict]:
    """The earlier-sessions record (module docstring): the sessions of runs that a --force
    replaced and that no purge-sessions has deleted since. Empty when there is none."""
    try:
        held = json.loads((Path(study_dir) / EARLIER_SESSIONS).read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(held, list):
        return []
    return [s for s in held if isinstance(s, dict) and s.get("run") and s.get("runner") and s.get("session")]


def write_earlier_sessions(study_dir: Path, held: list[dict]):
    """Replace the earlier-sessions record, or remove it when nothing is left to hold."""
    path = Path(study_dir) / EARLIER_SESSIONS
    if not held:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(exist_ok=True)
    write_atomic(path, json.dumps(held, indent=2) + "\n")


# ---------------------------------------------------------------- follow-ups

def read_followups(study_dir: Path) -> list[dict]:
    """followups.json (module docstring): the follow-up questions asked, oldest first. Empty when
    none was."""
    try:
        asked = json.loads((Path(study_dir) / FOLLOWUPS).read_text())
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as err:
        raise SystemExit(f"Cannot read {Path(study_dir) / FOLLOWUPS}: {err}")
    return asked if isinstance(asked, list) else []


def write_followups(study_dir: Path, asked: list[dict]):
    write_atomic(Path(study_dir) / FOLLOWUPS, json.dumps(asked, indent=2) + "\n")


def record_followup(study_dir: Path, n: int, run: str, **fields):
    """Set fields of one run's record under follow-up n in followups.json, adding the record, and
    the follow-up, when the file does not have them. settling=None takes "settling" out."""
    asked = read_followups(study_dir)
    followup = next((f for f in asked if f.get("n") == n), None)
    if followup is None:
        followup = {"n": n, "question": None, "asked": None, "mode": "runner", "runs": []}
        asked.append(followup)
    record = next((r for r in followup.setdefault("runs", []) if r.get("run") == run), None)
    if record is None:
        record = {"run": run, "outcome": None, "reason": None, "attempt": None, "session": None}
        followup["runs"].append(record)
    record.update(fields)
    if record.get("settling") is None:
        record.pop("settling", None)
    write_followups(study_dir, asked)


def asking(entry: dict) -> dict | None:
    """The attempt of a run that has a follow-up question out and is not settled yet, if there is
    one: the last attempt, of kind followup, with no end in runs.json. Its process may be at work
    or may have ended with no launcher alive to settle it. The run's "state" does not show it."""
    last = (entry.get("attempts") or [None])[-1]
    return last if last and last.get("kind") == "followup" and last.get("ended") is None else None


def open_attempt(entry: dict) -> dict | None:
    """The attempt of an entry that leaves its "state" alone and has no end in runs.json yet, if
    there is one: the last attempt, of kind followup, turn or debrief. Its process may be at
    work, or may have ended with no launcher alive to settle it. For an entry of a conversation,
    which has no "state", this alone says that a process of it may be alive: an entry with no
    attempt is never in flight. asking() is the same for a follow-up alone."""
    last = (entry.get("attempts") or [None])[-1]
    return last if last and last.get("kind") in ("followup", *TURN_KINDS) and last.get("ended") is None else None


def as_text(content: bytes) -> str:
    """What a file holds, as Path.read_text() reads it."""
    return io.TextIOWrapper(io.BytesIO(content)).read()


def read_copy(path: Path) -> bytes | None:
    """What a copy of a persona file that a launcher keeps in logs/ holds (.before,
    .rejected.md), None when there is none, or none that is the launcher's own: it is opened as
    every file of an attempt is (run_watchdog.opened()), never through a symbolic link and
    never waiting."""
    try:
        with os.fdopen(opened(path, most=READ_MOST), "rb") as f:
            return f.read()
    except OSError:
        return None


def keep_copy(path: Path, content: bytes):
    """Keep a copy of a persona file in logs/, in one step, as write_atomic() writes a text: a
    copy on disk is whole. It is made anew (run_watchdog.fresh()), so nothing left at its name
    is written through."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with os.fdopen(fresh(tmp), "wb") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def followup_section(n: int, question: str, answer: str, from_reply: bool = False) -> str:
    """A "## Follow-up <n>" section as a launcher writes one: the question quoted, then the
    answer. No line of either is left as a heading, because a heading would end the section and
    could pass for one of the run's own. from_reply marks it as taken from the panellist's reply."""
    def plain(text):
        return re.sub(r"^(\s*)#", r"\1\\#", text.strip(), flags=re.M)
    quoted = "\n".join(f"> {line}".rstrip() for line in plain(question).split("\n"))
    return "\n".join([f"## Follow-up {n}", "", quoted, "", plain(answer),
                      *(["", FROM_REPLY] if from_reply else []), ""])


def followup_change(cfg: dict, before: bytes, after: Path, n: int, quote=str) -> tuple[str, str]:
    """What follow-up n did to a persona file, from what the copy made before the question holds
    (before, read_copy()) and the file now (after, under the study directory): (kind, why).
    quote is how why repeats a line of the file, which in a usability study is shown()'s to
    decide.

    "section": the file is the copy plus one appended section that opens with the heading
    "## Follow-up <n>", holds something under it and has no other "## " or "### " heading, and
    the scores, ranking, unit sections and progress parse as they did. That is all a follow-up
    may do. "none": nothing was added. "blank": the heading was added with nothing under it.
    "other": anything else, with why in a clause: a file that can no longer be read as the run's
    own (persona_bytes()) among it. White space at the very end of the copy is not held against
    the file, since an editor that appends may tidy it.
    """
    old = as_text(before)
    try:
        new = as_text(persona_bytes(cfg["_dir"], after))
    except FileNotFoundError:
        return "other", "its persona file is gone"
    except OSError as err:
        return "other", f"its persona file can no longer be read as the run's own ({unread(err)})"
    was, now = parse_persona_file(after, cfg, old), parse_persona_file(after, cfg, new)
    if not new.startswith(old.rstrip()):
        rescored = sorted(u for u in {*was["scores"], *now["scores"]}
                          if was["scores"].get(u) != now["scores"].get(u))
        return "other", (f"it changed the scores of {unit_nouns(cfg)[0]} {', '.join(rescored)}" if rescored
                         else "it changed its ranking" if was["ranking"] != now["ranking"]
                         else "it changed what was already in the file")
    added = new[len(old.rstrip()):].strip().split("\n")
    if added == [""]:
        return "none", ""
    if not re.fullmatch(rf"## Follow-up {n}\s*", added[0]):
        return "other", (f"what it appended does not open with the heading `## Follow-up {n}`: it opens "
                         f"`{quote(added[0][:60])}`")
    extra = [line for line in added[1:] if line.startswith(("## ", "### "))]
    if extra:
        return "other", f"what it appended has a heading besides `## Follow-up {n}`: `{quote(extra[0][:60])}`"
    if any(was[k] != now[k] for k in ("scores", "ranking", "sections", "duplicates", "unknown_labels", "has_final")):
        return "other", "it changed how the scores, ranking or sections of the file read"
    return ("section", "") if any(line.strip() for line in added[1:]) else ("blank", "")


def own_words(parsed: dict, questions: dict[int, str]) -> str:
    """A persona file's text without the researcher's follow-up questions: what the panellist
    itself wrote. parsed is parse_persona_file()'s result and questions maps a follow-up's
    number to its question as followups.json records it.

    A panellist quotes the question in its "## Follow-up <n>" section, so the lead's own words
    would otherwise be checked as the panellist's. The question is taken out of that section
    only, wherever it stands there word for word: line breaks, indents and block-quote marks may
    differ. A question the panellist reworded stays, and so does every answer.
    """
    text = parsed["text"]
    for f in parsed["followups"]:
        words = (questions.get(f["n"]) or "").split()
        if words:
            quoted = re.compile(r"(?:\s|>)+".join(map(re.escape, words)))
            text = text.replace(f["text"], quoted.sub("", f["text"]), 1)
    return text


# ---------------------------------------------------------------- parsing

NUM = re.compile(r"\d+(?:\.\d+)?")
FILE_RE = re.compile(r"^(?P<pid>[^-]+)-(?P<slug>.+)--(?P<model>[^-]+)(?:-r(?P<rep>[1-9]\d*))?\.md$")


def unit_nouns(cfg: dict) -> tuple[str, str]:
    """Singular and plural of what a run in this study works through: concept(s), task(s) or
    topic(s)."""
    t = STUDY_TYPES[cfg["type"]]
    return t["unit"], t["units"]


def study_units(cfg: dict) -> list[str]:
    """The units every run must cover, in section-heading form: the concept labels of a review,
    the task ids of a usability study in the order study.json lists them, or every topic id of
    an interview study's guide. One persona's interview may have fewer: guide()."""
    if cfg["type"] == "usability":
        return [t["id"] for t in cfg["tasks"]]
    if cfg["type"] == "interview":
        return [t["id"] for t in cfg["interview"]["topics"]]
    return list(label_map(cfg))


def parse_persona_file(path: Path, cfg: dict, text: str) -> dict:
    """Parse one run file. Returns scores per unit, ranking, order, and structural problems.

    "model" is the model key and "replicate" the replicate number, both from the file name;
    "run" is the run id they make with the persona id. "followups" lists the file's follow-up
    sections in file order, each {"n", "text"}: the number in its "## Follow-up <n>" heading and
    the section from that heading to the next "## " heading. Nothing else here reads them.

    text is the file's content, and path only names the run: nothing is read here. A reader of
    scores or progress calls read_persona(), which decides what to read and reads it.
    """
    path = Path(path)
    labels, n_factors = study_units(cfg), len(cfg["factors"])
    heading = STUDY_TYPES[cfg["type"]]["heading"]
    m = FILE_RE.match(path.name)
    lines = text.split("\n")
    replicate = int(m["rep"] or 1) if m else 1
    out = {
        "file": path.name, "pid": m["pid"] if m else path.stem, "model": m["model"] if m else "",
        "replicate": replicate, "run": run_id(m["pid"], m["model"], replicate) if m else path.stem,
        "slug": m["slug"] if m else "", "scores": {}, "sections": {}, "ranking": [], "order": [],
        "unknown_labels": [], "duplicates": [], "missing_scores": [], "has_final": FINAL_MARKER in text,
        "text": text, "followups": [],
    }
    label_set = set(labels)
    for i, line in enumerate(lines):
        mf = FOLLOWUP_HEADING.match(line)
        if mf:
            end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
            out["followups"].append({"n": int(mf.group(1)), "text": "\n".join(lines[i:end]).rstrip()})
    for line in lines:
        mo = re.match(r"^\|\s*Review order\s*\|\s*(.+?)\s*\|\s*$", line)
        if mo:
            out["order"] = [x.strip() for x in mo.group(1).split(",") if x.strip()]
            break
    for i, line in enumerate(lines):
        mc = re.match(rf"^###\s+{heading}\s+([A-Za-z0-9]+)\b", line)
        if not mc:
            continue
        label = mc.group(1)
        if label not in label_set:
            out["unknown_labels"].append(label)
            continue
        if label in out["sections"]:
            out["duplicates"].append(label)
        end = next((j for j in range(i + 1, len(lines))
                    if lines[j].startswith("### ") or lines[j].startswith("## ")), len(lines))
        out["sections"][label] = "\n".join(lines[i:end])
        for j in range(i + 1, end):
            cells = [c.strip().strip("*") for c in lines[j].strip().strip("|").split("|")]
            if len(cells) == n_factors and all(NUM.fullmatch(c) for c in cells):
                out["scores"][label] = [float(c) for c in cells]
                break
    out["missing_scores"] = [lab for lab in out["sections"] if lab not in out["scores"]]
    in_rank = False
    for line in lines:
        if re.match(r"^#{2,4}\s+My ranking", line):
            in_rank = True
            continue
        if in_rank and line.startswith("#"):
            break
        if in_rank:
            mr = re.match(r"^\s*\d+[.)]\s*\**\s*Concept\s+([A-Za-z0-9]+)", line)
            if mr and mr.group(1) in label_set and mr.group(1) not in out["ranking"]:
                out["ranking"].append(mr.group(1))
    return out


# ---------------------------------------------------------------- answers and lines

# What extract_answers.py reads from a unit section: the fields init_study.py's concept_template
# asks for, each known by the opening words of its label. The template is built from these, so a
# label changed here changes there too, and files written under the old label stop parsing. The
# parsers never guess: an entry that is not written the way its rule below says comes back as
# "unparsed" with its text, and one left out as "missing".
FIELD_LABELS = {
    "answers": "Could I find the answer",       # one bullet per find_the_answer question
    "keep": "One line to keep",
    "cut": "One line to cut",
    "not_believed": "One line I don't believe",
    "forward": "Would I forward it",
    # Not tallied. Listed so that a field ends where the next one starts.
    "pages": "Pages I looked at", "take": "5-second take", "real_life": "What I'd do in real life",
    "worked": "What worked for me", "put_off": "What confused", "questions": "Questions it left me with",
    "explain": "Explain it back", "quote": "Quote (my gut reaction",
}
LINE_FIELDS = ("keep", "cut", "not_believed")
ANSWERS_HINT = "For each question"  # how the template's own instruction under the answers label starts
VERDICTS = {"found": "Found", "partly": "Partly", "partially": "Partly", "not found": "Not found"}

_ITEM = r"(?:[-*+]|\d+[.)])\s+"
_FIELD = {key: re.compile(rf"^\s*(?:{_ITEM})?(?P<bold>\*\*|__)?\s*" + re.escape(label).replace("'", "['\u2019]")
                          + r"(?P<rest>.*)$", re.I) for key, label in FIELD_LABELS.items()}
_BULLET = re.compile(rf"^(\s*){_ITEM}")
_MARKUP = re.compile(r"\*\*|__|`")
_STRAIGHT = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})
_VERDICT = re.compile(r"(not\s+found|found|partly|partially)\b", re.I)
_AFTER_VERDICT = re.compile(r"[\s,/;-]*(?:(?:and|or|but|to)\s+)?(not\s+found|found|partly|partially|nothing|none"
                            r"|no|neither|zero)\b", re.I)
_NONE = re.compile(r"(none|nothing|n/a)\b", re.I)
# Where the recipient of a forward ends and the message is announced: ", with the message", "and a
# short note", ", saying". "message" is the template's own word for what goes with the page.
_MESSAGE_NEXT = r",?\s+(?:with|and)\s+(?:the|a|this|my|one)\s+(?:[\w-]+\s+)?(?:message|note)\b|,\s+saying\b"
_RECIPIENT = re.compile(r"[\s,.:;-]*(?i:to)\s+((?:(?i:my|our|the|an?|one|two|three|four|five|some|any|anyone|"
                        r"everyone|another|other|every|all|both|his|her|their|that|this|those|these|whoever)\b"
                        r"|[A-Z])[^:\"]*?)(?=\s*(?::|\.(?:\s|$)|\"|$)|(?i:" + _MESSAGE_NEXT + "))")
_STOPWORDS = frozenset("a already an and any are at be can do does each for how i in is it many me much my of on "
                       "or our per that the there this to we what which who will with would you your".split())


def _straight(text: str) -> str:
    """Curly quotes and apostrophes made straight. One character for one, so positions hold."""
    return text.translate(_STRAIGHT)


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def section_fields(section: str) -> dict[str, list[str]]:
    """The lines of each template field in a unit section, keyed as FIELD_LABELS.

    A field starts at the line that opens with its label, through a bullet marker and bold, and
    its first line is what follows the label on that line. It runs to the next label, table row
    or heading. When a section repeats a label the first field stands.
    """
    fields, current = {}, None
    for line in section.split("\n")[1:]:
        key, m = next(((k, m) for k, m in ((k, pat.match(line)) for k, pat in _FIELD.items()) if m), (None, None))
        if m:
            rest = m["rest"]
            close = rest.find(m["bold"]) if m["bold"] else -1
            end = re.search(r"[:?]", rest)
            value = rest[close + 2:] if close >= 0 else rest[end.end():] if end else rest
            current = None if key in fields else fields.setdefault(key, [value.lstrip(" :")])
        elif line.lstrip().startswith(("|", "#")):
            current = None
        elif current is not None:
            current.append(line)
    return fields


def _field_text(lines: list[str] | None) -> str:
    """A one-line field's text: its first paragraph, cut where a bullet or a bold label starts."""
    text = []
    for line in lines or []:
        if text and (not line.strip() or _BULLET.match(line) or line.lstrip().startswith(("**", "__"))):
            break
        if line.strip():
            text.append(line)
    return _one_line(" ".join(text))


def read_verdict(text: str) -> tuple[str | None, str]:
    """(verdict, where it was found) from an answer with its question taken off, or (None, "").

    Only an answer that starts with Found, Partly, Partially or Not found counts, in any case.
    One that goes straight on to another verdict or to a denial ("Found, partly", "Found nothing")
    is ambiguous and does not count; "Partly found" is Partly. A later sentence may qualify the
    verdict without changing it.
    """
    text = text.lstrip(" \t:*_-")
    m = _VERDICT.match(text)
    if not m:
        return None, ""
    verdict, rest = VERDICTS[" ".join(m[1].lower().split())], text[m.end():]
    more = _AFTER_VERDICT.match(rest)
    if more:
        word = " ".join(more[1].lower().split())
        if (verdict, word) == ("Partly", "found"):
            rest = rest[more.end():]
        elif verdict == "Found" or (word in VERDICTS and VERDICTS[word] != verdict):
            return None, ""
    return verdict, rest.strip().lstrip(",;:.-").strip()


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", _straight(text).casefold().replace("'", ""))
            if w not in _STOPWORDS]


def _overlap(words: list[str], others: list[str]) -> float:
    """The share of words that are in others, taking "month" and "monthly" as one word."""
    def same(a, b):
        n = len(os.path.commonprefix([a, b]))
        return a == b or (n >= 4 and n >= min(len(a), len(b)) - 1)
    return sum(any(same(w, o) for o in others) for w in words) / len(words) if words else 0.0


def _answer_items(lines: list[str]) -> list[str]:
    """The entries of an answers field: its top-level bullets, each with the lines and nested
    bullets under it folded in, or its lines when it has no bullet. The template's own
    instruction is no entry."""
    marks = [m for m in map(_BULLET.match, lines) if m]
    if not marks:
        return [t for t in map(_one_line, lines) if t and not t.startswith(ANSWERS_HINT)]
    top = min(len(m[1]) for m in marks)
    items = []
    for line in lines:
        m = _BULLET.match(line)
        if m and len(m[1]) == top:
            items.append(line[m.end():])
        elif items and line.strip():
            items[-1] += " " + (line[m.end():] if m else line)
    return [_one_line(t) for t in items]


def parse_answers(section: str, questions: list[str]) -> list[dict]:
    """A unit section's answer to each find_the_answer question, in question order.

    Each is {"verdict", "where", "raw"}: verdict is Found, Partly or Not found (read_verdict),
    "missing" when the panellist gave the question no answer, or "unparsed"; where is what
    followed the verdict; raw is the entry as written, "" when missing.

    An entry belongs to a question when it starts with the question's text or with "Q<n>"; or,
    when the panellist reworded the question, when the words before its first colon or question
    mark point at one question only: either some of them are that question's and the entry sits
    at its position among as many entries as questions, or most of them (0.6) are. An entry that
    starts with its verdict takes the question at its position, when there are as many entries as
    questions. An entry that fits no question leaves every question without one "unparsed", as
    does a question two entries claim.
    """
    def blank(verdict, raw=""):
        return {"verdict": verdict, "where": "", "raw": raw}

    lines = section_fields(section).get("answers")
    if lines is None:
        return [blank("missing") for _ in questions]
    items = _answer_items(lines)
    aligned = len(items) == len(questions)
    asked = [re.compile(r"\s*" + r"\s+".join(map(re.escape, _straight(_MARKUP.sub("", q)).strip(" ?:.").split()))
                        + r"(?!\w)\s*[?:.]*", re.I) for q in questions]
    q_words = [_words(q) for q in questions]
    claims, loose = {}, {}  # question index -> [(entry, its answer)]; entry index -> entry that fits none
    for i, item in enumerate(items):
        text = _one_line(_MARKUP.sub("", item))
        flat = _straight(text)
        q, answer = None, text
        starts = [(m.end(), j) for j, m in enumerate(rx.match(flat) for rx in asked) if m]
        if starts:
            end, q = max(starts)
            answer = text[end:]
        elif _VERDICT.match(flat.lstrip(" \t:*_-")):
            q = i if aligned else None
        else:
            cut = re.search(r"[:?](?=\s|$)", flat)
            label, answer = (text[:cut.start()], text[cut.end():]) if cut else (text, "")
            number = re.fullmatch(r"(?:q|question)\s*#?(\d+)", label.strip(), re.I)
            if number:
                q = int(number[1]) - 1 if 0 < int(number[1]) <= len(questions) else None
            else:
                score = [_overlap(_words(label), w) for w in q_words]
                best = max(score, default=0)
                if best > 0 and score.count(best) == 1 and ((aligned and score.index(best) == i) or best >= 0.6):
                    q = score.index(best)
        if q is None:
            loose[i] = item
        else:
            claims.setdefault(q, []).append((item, answer))
    out = []
    for j in range(len(questions)):
        got = claims.get(j, [])
        if len(got) == 1:
            item, answer = got[0]
            verdict, where = read_verdict(answer)
            if verdict:
                out.append({"verdict": verdict, "where": where, "raw": item})
            else:
                out.append(blank("unparsed", item) if answer.strip(" .:*_-") else blank("missing"))
        elif got:
            out.append(blank("unparsed", " / ".join(item for item, _ in got)))
        elif loose:
            out.append(blank("unparsed", loose[j] if aligned and j in loose else " / ".join(loose.values())))
        else:
            out.append(blank("missing"))
    return out


def read_line(value: str) -> dict:
    """One "line to keep", "to cut" or "I don't believe" field: {"status", "text", "to", "note"}.

    quoted: the field opens with a line in double quotes, straight or curly. text is the line,
    note what the panellist added after it. Further quotes outside brackets make it "unparsed":
    two lines, or a line with quotes inside it, and which is not for this script to say.
    none: the panellist wrote none, nothing or n/a, quoted or not. unquoted: anything else, kept
    whole in text. missing: empty, or the template's "..." left in place.
    """
    def entry(status, text="", note=""):
        return {"status": status, "text": text, "to": "", "note": note}

    v = _one_line(_MARKUP.sub("", value))
    flat = _straight(v)
    if not flat.strip(' ."'):
        return entry("missing")
    if flat.startswith('"'):
        end = flat.find('"', 1)
        if end < 0 or '"' in re.sub(r"\([^)]*\)", "", flat[end + 1:]):
            return entry("unparsed")
        text, note = v[1:end].strip(), v[end + 1:].strip()
        if not text.strip(" ."):
            return entry("missing")
        return entry("none", note=note) if _NONE.fullmatch(text.rstrip(" .")) else entry("quoted", text, note)
    m = _NONE.match(flat)
    if m and flat[m.end():].lstrip()[:1] in ("", *".,;:("):
        return entry("none", note=v[m.end():].lstrip(" .,;:"))
    return entry("unquoted", v)


def read_forward(value: str) -> dict:
    """The "Would I forward it?" field: {"status", "text", "to", "note"}.

    status is yes, no or maybe when the answer starts with that word, else "unparsed" (so "Not
    yet" and "yes/no" are), or "missing". to is who it would go to, read only where "to" and a
    person follow the answer directly ("Yes, to my bookkeeper: ..."), and never for a no. It
    ends at a colon, a full stop or a quotation mark, or sooner where the answer announces the
    message ("to a client who asked, with the message: ..." gives "a client who asked"). text
    is the message: the one passage in double quotes, "" when there is none or more than one.
    """
    v = _one_line(_MARKUP.sub("", value))
    flat = _straight(v)
    out = {"status": "missing", "text": "", "to": "", "note": ""}
    if not flat.strip(" .*_"):
        return out
    m = re.match(r"(yes|no|maybe)\b(?!\s*(?:/|(?:and|or)\s+(?:yes|no)\b))", flat, re.I)
    if not m:
        return {**out, "status": "unparsed"}
    out["status"] = m[1].lower()
    who = _RECIPIENT.match(flat, m.end()) if out["status"] != "no" else None
    if who:
        out["to"] = v[who.start(1):who.end(1)]
    quoted = list(re.finditer(r'"([^"]+)"', flat))
    if len(quoted) == 1:
        out["text"] = v[quoted[0].start(1):quoted[0].end(1)].strip()
    return out


def parse_lines(section: str) -> dict[str, dict]:
    """A unit section's keep, cut, not_believed and forward entries (read_line, read_forward),
    each with "raw": the field as written, on one line."""
    fields = section_fields(section)
    out = {}
    for key in (*LINE_FIELDS, "forward"):
        raw = _field_text(fields.get(key))
        out[key] = {**(read_forward if key == "forward" else read_line)(raw), "raw": raw}
    return out


def same_line(text: str) -> str:
    """A quoted line reduced to what makes two quotations of it the same: straight quotes, single
    spaces, no case and no closing full stop."""
    return _one_line(_straight(text)).casefold().rstrip(".").strip()


def personas_dir(study_dir: Path) -> Path:
    """panel/personas in a live study; personas/ in an archived round (archive.py flattens panel/).
    To name it, as evidence_dir() names a run's evidence folder: whatever reads a file in it
    reads through persona_bytes()."""
    live = (Path(study_dir) / "panel").is_dir()
    return Path(study_dir) / ("panel/personas" if live else "personas")


def persona_bytes(study_dir: Path, path: Path) -> bytes:
    """What a persona file holds: the one way a persona file is opened, by every script that
    reads one. A panellist can write under panel/, so what stands at the file's name is read as
    something another process may have put there (open_below()): no symbolic link is followed,
    at the file or at a folder between the study directory and it, only a regular file is
    read, and the open never waits, as it would for a FIFO. Raises FileNotFoundError when the
    run has no file, and another OSError, with the reason (unread()), when what is there cannot
    be read as the run's own. That is no persona file: its run is not done, nothing is taken
    from it, and check_runs.py names it with the reason (persona_problem())."""
    with os.fdopen(open_below(study_dir, path), "rb") as f:
        return f.read()


def persona_problem(study_dir: Path, path: Path) -> str | None:
    """Why what stands at a persona file's name cannot be read as its run's own
    (persona_bytes()), None when it can, or nothing is there."""
    try:
        os.close(open_below(study_dir, path))
    except FileNotFoundError:
        return None
    except OSError as err:
        return unread(err)
    return None


def write_persona(study_dir: Path, path: Path, content: str | bytes):
    """Replace a persona file in one step, as write_atomic() replaces a file, and through no
    symbolic link: its folder is opened as persona_bytes() opens it (folder_fd()), the content
    goes to a file made anew in that folder (run_watchdog.fresh()), and that file takes the
    name, so a link left at the name goes and what it points at is not written. Raises OSError,
    with the reason (unread()), when a folder on the way is a link or no folder, or the file
    cannot be put there."""
    *folders, name = parts_below(study_dir, path)
    try:
        folder = folder_fd(study_dir, folders)
    except Unsafe:
        raise Unsafe("a folder above it is a symbolic link, or no folder") from None
    tmp = f".{name}.{os.getpid()}.tmp"
    try:
        with os.fdopen(fresh(tmp, mode=0o666, dir_fd=folder), "wb" if isinstance(content, bytes) else "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.replace(tmp, name, src_dir_fd=folder, dst_dir_fd=folder)
        except OSError:  # a folder at the name: nothing of this stays in a folder panellists read
            os.unlink(tmp, dir_fd=folder)
            raise
    finally:
        os.close(folder)


def run_progress(cfg: dict, parsed: dict | None) -> dict:
    """How far a run has got, from its parsed persona file (None when it has no file yet).

    units: every unit the study expects; written: those with a section; scored: those with a
    score row; has_final: the final marker is present. A run is complete, for every study type,
    when every unit is scored and the final marker is present. Nothing else decides "done".
    """
    units = study_units(cfg)
    sections, scores = (parsed["sections"], parsed["scores"]) if parsed else ({}, {})
    scored = [u for u in units if u in scores]
    has_final = bool(parsed and parsed["has_final"])
    return {"units": units, "written": [u for u in units if u in sections], "scored": scored,
            "has_final": has_final, "complete": has_final and len(scored) == len(units)}


def run_state(progress: dict, recorded: str | None = None, ended: dict | None = None) -> str:
    """A run's lifecycle state, from its run_progress() and the "state" its runs.json entry records.

    The persona file decides whether a run is done: a complete file is "done" whatever was
    recorded and however its process ended, and an incomplete one never is.

    ended is given by a launcher when a process has just ended, and then decides the state of
    an incomplete run, first match first: {"limit": true} (the launcher stopped it at a run
    limit) or {"outcome": "budget"} (the harness's spend cap did) is "limited";
    {"outcome": "usage_limit"} is "blocked"; {"stopped": true} (the stop command) is "partial"
    with a section written and "pending" with none; anything else is "partial" with a section
    written and "failed" with none.

    Without ended the recorded state stands (pending, running, partial, limited, blocked or
    failed), except that "pending" and "failed" mean nothing is written: with a section on
    file they read as "partial", so nothing ever launches such a run afresh. With none
    recorded, or "done" recorded for an incomplete file, the state is "partial" when at least
    one unit section is written and "pending" when none is.
    """
    if progress["complete"]:
        return "done"
    some = "partial" if progress["written"] else None
    if ended is not None:
        if ended.get("limit") or ended.get("outcome") == "budget":
            return "limited"
        if ended.get("outcome") == "usage_limit":
            return "blocked"
        return some or ("pending" if ended.get("stopped") else "failed")
    if recorded in ("running", "partial", "limited", "blocked"):
        return recorded
    return some or (recorded if recorded == "failed" else "pending")


UNSETTLED = "a follow-up is unsettled, so its file was read as it stood before the question"
LOOKS = 5  # how many times read_persona() chooses and reads while the run's attempts change under it


def _attempts(entry: dict | None) -> list:
    return (entry or {}).get("attempts") or []


def _entry_now(study_dir: Path, path: Path, entry: dict | None, run: str | None) -> dict | None:
    """A run's entry as runs.json has it at this moment, None when it has none: the entry of the
    run id, or without one the entry whose persona file has path's name (an archive moves the
    file). With no runs.json, or one that cannot be read, entry stands: there is no later word."""
    try:
        runs = json.loads((study_dir / "runs.json").read_text())
    except (OSError, ValueError):
        return entry
    for e in runs if isinstance(runs, list) else []:
        if isinstance(e, dict) and (e.get("run") == run if run else Path(e.get("file") or "").name == path.name):
            return e
    return None


def read_persona(study_dir: Path, cfg: dict, path: Path, entry: dict | None = None) -> dict | None:
    """A run's persona file as its scores, answers and progress stand: parse_persona_file() with
    "unsettled" added, or None when the run has no file, or none that can be read as its own
    (persona_bytes(): a symbolic link, a FIFO or a folder at its name is no persona file). The
    one place that chooses what to read.

    path is the persona file and entry the run's runs.json entry, when it has one. For a run
    whose latest follow-up attempt is not settled (asking()), the copy made before the question
    is read in place of the file, and "unsettled" is true: the file may hold what settling will
    reject and put back (the snapshot rule, module docstring). The copy is in logs/, which only
    a live study has, and it is there until the attempt's end is in runs.json. Without one the
    file itself is read.

    entry is only the first word on the run: the caller read it some time ago, and a follow-up
    may have started or been settled since. So once the content is read, the run's attempts are
    read again from runs.json, and when they are not the ones the choice was made from (an
    attempt was added, ended or taken back), the choice and the read are made again from the
    newer ones, until two looks one after the other agree. A launcher has the copy on disk and
    the attempt in runs.json before it starts the process that may change the file, and puts
    the file right before it writes the attempt's end, so content read between two looks that
    agree is never what a follow-up has yet to have settled. An archive has no logs/, and a
    study with no runs.json has no attempts: there the file is read as it is.

    After LOOKS reads with no two looks in agreement, nothing read from the file is returned: it
    may be what a follow-up left before it was put back. The newest copy still on disk of a
    follow-up attempt of the run is returned in its place, with "unsettled" true as for any
    copy. Any such copy will do, because a launcher makes one in a single step, under the study
    lock, of a file no follow-up has unsettled: the review and the sections of the follow-ups
    accepted before it, which is also what a rejected follow-up is put back to. So its scores
    and ranking are the review's own, and at worst it lacks a later follow-up's section. With
    no copy on disk the read is refused: the script exits, saying to run it again.
    """
    study_dir, path = Path(study_dir), Path(path)
    run = entry["run"] if entry else None

    def copy(e, attempt):  # None in an archive, or when settled since runs.json was read
        held = read_copy(study_dir / "logs" / f"{e['run']}.{attempt['n']}.before")
        return None if held is None else as_text(held)

    for _ in range(LOOKS):
        attempt = asking(entry or {})
        before = copy(entry, attempt) if attempt else None
        try:
            text = as_text(persona_bytes(study_dir, path)) if before is None else before
        except OSError:  # the run has no file, or none that can be read as its own
            text = None
        now = _entry_now(study_dir, path, entry, run)
        steady = _attempts(now) == _attempts(entry)
        entry = now
        if steady:
            break
    else:  # never the same attempts twice: a copy is the file before a question, whatever happened since
        copies = (copy(entry, a) for a in reversed(_attempts(entry)) if a.get("kind") == "followup")
        text = before = next((c for c in copies if c is not None), before)
        if before is None:  # what was read from the file may be what a follow-up left: it is not returned
            raise SystemExit(
                f"Follow-up questions to {(entry or {}).get('run') or run or path.stem} kept starting and settling "
                f"while its persona file {path} was being read, so nothing was read from it: run the command "
                f"again once they have finished (launch.py {study_dir} status shows them).")
    return None if text is None else {**parse_persona_file(path, cfg, text), "unsettled": before is not None}


def unsettled_lines(runs: list[dict]) -> list[str]:
    """One line for each run that was read from the copy made before an unsettled follow-up, for
    the script that read it to print. runs are read_persona() results or run_records() records."""
    return [f"{r['run']}: {UNSETTLED}" for r in runs if r.get("unsettled")]


def persona_files(study_dir: Path) -> list[tuple[Path, dict | None]]:
    """Every persona file a study has or expects, in name order, each with its run's entry in
    runs.json, None for a file that no entry names: what the personas folder holds under a
    persona file's name, whatever it is, and the file of each panellist entry, there or not.
    The folder is listed as its files are read, through no symbolic link (folder_fd()): one
    that is a link, or reached through one, is listed as holding nothing."""
    study_dir = Path(study_dir)
    entries = {}  # persona file name -> its run's entry: an archive moves the file, so match it by name
    if (study_dir / "runs.json").exists():
        entries = {Path(e["file"]).name: e for e in read_runs(study_dir) if e["role"] == "panellist"}
    folder = personas_dir(study_dir)
    try:
        fd = folder_fd(study_dir, folder.relative_to(study_dir).parts)
    except OSError:
        names = []
    else:
        try:
            names = fnmatch.filter(os.listdir(fd), "*--*.md")
        finally:
            os.close(fd)
    return [(folder / name, entries.get(name)) for name in sorted({*names, *entries})]


def load_runs(study_dir: Path, cfg: dict) -> list[dict]:
    """Every persona file in the study, parsed (read_persona()): of those persona_files() lists,
    the ones that can be read as their run's own. For the runs.json entries, see read_runs().
    An interview study has no persona file, so none: run_records() reads its turn logs."""
    study_dir = Path(study_dir)
    if cfg["type"] == "interview":
        return []
    seg = {p["id"]: p.get("segment", "") for p in cfg["personas"]}
    runs = []
    for path, entry in persona_files(study_dir):
        r = read_persona(study_dir, cfg, path, entry)
        if r:
            r["segment"] = seg.get(r["pid"], "")
            runs.append(r)
    return runs


def run_records(study_dir: Path, cfg: dict, held: bool = False) -> list[dict]:
    """Every expected panellist run, with how far it got. Works on live and archived studies.

    Expected runs are the panellist entries of runs.json, then any persona file no entry names;
    without a runs.json, the persona files found. Each record has "run", "pid", "model" (the
    model key), "replicate", "segment", "parsed" (parse_persona_file's result, None when the run
    has no file, or none that can be read as its own), "progress" (run_progress), "state"
    (run_state) and "unsettled" (whether the file was read as it stood before a follow-up that
    is not settled: read_persona()).

    In an interview study the expected runs are the participants' entries, or without a
    runs.json the interviews study.json plans. A record has the same keys, with "parsed" None
    and "unsettled" false, and one more: "turns", the records of the run's turn log. "progress"
    is interview_progress() and "state" interview_state(). held is whether a launcher has the
    study, which is what makes an entry's "carried" count (carried()): the caller asks the study
    lock, a launcher passes true, and an archived round has none.
    """
    study_dir = Path(study_dir)
    seg = {p["id"]: p.get("segment", "") for p in cfg["personas"]}
    if cfg["type"] == "interview":
        entries = read_runs(study_dir) if (study_dir / "runs.json").exists() else planned_runs(cfg)
        out = []
        for e in (e for e in entries if e["role"] == "panellist"):
            turns = read_turns(study_dir, e["run"])
            out.append({"run": e["run"], "pid": e["persona"], "model": e["key"], "replicate": e["replicate"],
                        "segment": seg.get(e["persona"], ""), "parsed": None, "turns": turns,
                        "progress": interview_progress(cfg, e, turns),
                        "state": interview_state(turns, carried(e, held)), "unsettled": False})
        return out
    files = {r["file"]: r for r in load_runs(study_dir, cfg)}
    found = []  # (pid, key, replicate, run id, recorded state, parsed file)
    if (study_dir / "runs.json").exists():
        for e in read_runs(study_dir):
            if e["role"] == "panellist":  # an archive moves the file, so match it by name
                found.append((e["persona"], e["key"], e["replicate"], e["run"], e.get("state"),
                              files.pop(Path(e["file"]).name, None)))
    found += [(r["pid"], r["model"], r["replicate"], r["run"], None, r) for r in files.values()]
    out = []
    for pid, key, replicate, run, recorded, parsed in found:
        prog = run_progress(cfg, parsed)
        out.append({"run": run, "pid": pid, "model": key, "replicate": replicate, "segment": seg.get(pid, ""),
                    "parsed": parsed, "progress": prog, "state": run_state(prog, recorded),
                    "unsettled": bool(parsed and parsed["unsettled"])})
    return out


# ---------------------------------------------------------------- the turn log

def turn_log(study_dir: Path, run: str) -> Path:
    """Where the turn log of an interview is (module docstring, "The turn log"), in a live study
    and in an archived round alike."""
    return Path(study_dir) / INTERVIEWS / f"{run}.jsonl"


def _settled(data: bytes) -> int:
    """How much of a turn log, given as its bytes, is on record: all of it up to the end of its
    last finished settlement. What a killed writer left after that is not: a last line with no
    line break, and before it the records of a settlement that never got its last one, each a
    whole line marked "more": true (module docstring, "The turn log")."""
    keep = data.rfind(b"\n") + 1
    while keep:
        start = data.rfind(b"\n", 0, keep - 1) + 1
        try:
            record = json.loads(data[start:keep - 1])
        except ValueError:
            break
        if not (isinstance(record, dict) and record.get("more") is True):
            break
        keep = start
    return keep


def _turn_lines(study_dir: Path, run: str) -> tuple[list[str], str]:
    """The lines of a turn log that are on record, and what follows them: the unfinished end a
    writer was killed in the middle of (_settled()), "" when the log ends as it should. No log
    reads as no line."""
    try:
        data = turn_log(study_dir, run).read_bytes()
    except FileNotFoundError:
        return [], ""
    keep = _settled(data)
    return data[:keep].decode("utf-8", "replace").split("\n")[:-1], data[keep:].decode("utf-8", "replace")


def read_turns(study_dir: Path, run: str) -> list[dict]:
    """The records of an interview's turn log, in order, [] when it has none. What a killed
    writer left at its end is left out (turn_torn()): a last line with no line break, and the
    records of a settlement whose last record never reached the disk, so a settlement is read
    whole or not at all. A blank line is passed over.

    This is where a log that is not as a launcher writes one is recognised, for every reader at
    once. A line that is no JSON object with a "t", and a record that is not as a launcher
    writes one (_unlike(): of no known type, or with a field of another kind than a launcher
    writes), is given as {"t": "unread", "line": its text}, with the object under "record" when
    the line was one. A line is judged as the object it holds and as nothing else: one that is
    itself of the type "unread" is of no type a launcher writes, so it is set aside whole, and
    what it has under "record" is never read as a record. No reading of the log counts such a
    record, so whatever is worked out from a log (its state, its progress, the position and
    what stands in its way) is worked out from its well-formed records alone and never fails
    on a damaged one, and turn_lacking() names each."""
    records = []
    for line in _turn_lines(study_dir, run)[0]:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            record = None
        if not (isinstance(record, dict) and isinstance(record.get("t"), str)):
            records.append({"t": "unread", "line": line})
        elif _unlike(record, 0):
            records.append({"t": "unread", "line": line, "record": record})
        else:
            records.append(record)
    return records


def turn_torn(study_dir: Path, run: str) -> bool:
    """Whether a turn log ends in a line or a settlement that was never finished, which
    read_turns() leaves out and the next append_turns() cuts off: a launcher was killed while
    it wrote."""
    return bool(_turn_lines(study_dir, run)[1])


def append_turns(study_dir: Path, run: str, records: list[dict]):
    """Add records to an interview's turn log, making the log and its folder when they are not
    there. The records are one settlement: every one but the last is written with "more": true,
    and all go in a single write to a descriptor opened for append, which is then synced. A
    launcher killed at any moment, in the middle of that write too, so leaves every record of
    the settlement or, to every reader, none: records marked "more" with nothing after them
    are not read (read_turns()). What an earlier writer left unfinished is cut off first, a
    torn line and such records alike, so that the new settlement follows the last one that is
    whole. Only a launcher that holds the study lock calls this.

    A record that is not as TURN_FIELDS has its type is never written, and so none of the type
    "unread", which is a reader's name for a record it set aside and no type of a record: that
    is a mistake of the code that made it and no damage to a log, and read_turns() would set
    the record aside, so no reading of the log would count it."""
    wrong = [said for i, r in enumerate(records, start=1) for said in _unlike(r, i)]
    if wrong:
        raise ValueError(f"A record for the turn log of {run} is not as a launcher writes one, and nothing was "
                         f"written. Of the records to add: {' '.join(wrong)}")
    path = turn_log(study_dir, run)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps({**r, "more": True} if r is not records[-1] else r) + "\n" for r in records).encode()
    fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC, 0o644)
    try:
        size = os.fstat(fd).st_size
        keep = _settled(os.pread(fd, size, 0))
        if keep != size:
            os.ftruncate(fd, keep)
        while data:  # one write, unless the system took only a part of it
            data = data[os.write(fd, data):]
        os.fsync(fd)
    finally:
        os.close(fd)


def _of_kind(value, kind) -> bool:
    """Whether a value read from a turn log is of the kind the format gives its field
    (TURN_FIELDS, TURN_SOMETIMES): a type, or any type of a tuple, where true and false are no
    numbers; [kind], a list of values of that kind; a list of several kinds, a list of exactly
    that many values, each of its kind; {kind: kind}, an object whose keys and values are of
    those kinds."""
    if isinstance(kind, list):
        kinds = kind * len(value) if len(kind) == 1 and isinstance(value, list) else kind
        return isinstance(value, list) and len(value) == len(kinds) and all(map(_of_kind, value, kinds))
    if isinstance(kind, dict):
        [(key, held)] = kind.items()
        return isinstance(value, dict) and all(_of_kind(k, key) and _of_kind(x, held) for k, x in value.items())
    return isinstance(value, kind) and (kind is bool or not isinstance(value, bool))


def _unlike(r: dict, i: int) -> list[str]:
    """What makes one record, the i-th of its log, unlike any a launcher writes, each a sentence:
    it is of no known type; it lacks a field every launcher writes on a record of its type
    (TURN_FIELDS, and "at" on every one); it has another kind of value than a launcher writes in
    a field it writes only sometimes (TURN_SOMETIMES). A field is lacking when it is not there,
    or holds another kind of value than a launcher writes, a side that is none of SIDES, a
    "halt" with a state that is none of HALTS and an "end-offered" that names no topic among
    them. [] for a record every reader can count on.

    The record is judged as it stands: the object a line of a log holds (read_turns()), or one
    about to be written (append_turns()). "unread" is no type a launcher writes, so a record
    that calls itself that is of no known type, whatever it holds under "record"."""
    if r["t"] not in TURN_TYPES:
        return [f"Record {i} is not a record of a known type."]
    wanted = {"at": _NUMBER, **TURN_FIELDS[r["t"]]}
    lacking = [f for f, kind in wanted.items() if not _of_kind(r.get(f), kind)]
    lacking += ["side"] if "side" not in lacking and r.get("side", SIDES[0]) not in SIDES else []
    lacking += ["state"] if r["t"] == "halt" and "state" not in lacking and r["state"] not in HALTS else []
    lacking += ["unopened"] if r["t"] == "end-offered" and r.get("unopened") == [] else []
    odd = [f for f, kind in {**TURN_SOMETIMES[""], **TURN_SOMETIMES.get(r["t"], {})}.items()
           if f in r and f not in wanted and f not in lacking and not _of_kind(r[f], kind)]
    out = []
    if lacking:
        out.append(f"Record {i} ({r['t']}) lacks {listed_keys(lacking)}, which a launcher always writes.")
    if odd:
        out.append(f"Record {i} ({r['t']}) holds another kind of value in {listed_keys(odd)} than a launcher "
                   "writes.")
    return out


def turn_lacking(records: list[dict]) -> list[str]:
    """The records of a turn log that are not as a launcher writes one, each a sentence (_unlike()
    has the rules): one of no known type; one that lacks a field every launcher writes on a
    record of its type; and one with another kind of value than a launcher writes in a field it
    writes only sometimes. [] for a log every reader can count on: everything that interprets a
    log (interview.py) reads those fields without asking, and what it reads there is of the kind
    the format says, down to the items of a list.

    records are as read_turns() gives them, which has judged each line and set aside the ones
    that are named here ("unread", with the object under "record"). Such a one is named by
    what that object is unlike a launcher's in, as the line was judged, so the sentences are
    those of the log as it was written, and each still counts by its place in the log. An
    "unread" record is always named, whatever it holds: it is unwrapped once and no further, so
    an object under "record" that is itself called "unread" is of no known type."""
    out = []
    for i, r in enumerate(records, start=1):
        said, aside = _unlike(r, i), r.get("record") if r["t"] == "unread" else None
        if isinstance(aside, dict) and isinstance(aside.get("t"), str):
            said = _unlike(aside, i) or said
        out += said
    return out


def turn_problems(records: list[dict]) -> list[str]:
    """What is wrong with the form of a turn log, each a sentence, [] for a log that is as a
    launcher writes one (module docstring, "The turn log"). Records are counted from 1, as the
    lines of the log are when none is blank. check_runs.py blocks on each. records are as
    read_turns() gives them, so a settlement a killed writer left unfinished is not among
    them, and "more" on a record is no problem: every settlement here has its last record.

    A log with a record of no known type, or one that lacks a field a launcher always writes
    (turn_lacking()), has those sentences and no other: what follows here, and every other
    reading of the log, counts on the fields."""
    out, kind = turn_lacking(records), (records[0].get("kind") if records else None)
    if out:
        return out
    if records and records[0]["t"] != "start":
        out.append('It does not begin with a "start" record.')

    due = ("question", 1)  # questions and answers alternate, and their numbers run 1, 1, 2, 2
    for i, r in enumerate(records, start=1):
        if r["t"] not in ("question", "answer"):
            continue
        if (r["t"], r.get("n")) != due:
            out.append(f"Record {i} is {r['t']} {r.get('n')} where {due[0]} {due[1]} was due: turns must "
                       "alternate, and none may skip or repeat a number.")
            break
        due = ("answer", due[1]) if r["t"] == "question" else ("question", due[1] + 1)

    opened = [i for i, r in enumerate(records) if r["t"] in ("card", "ready")]
    first = next((i for i, r in enumerate(records) if r["t"] == "question"), None)
    if kind == "debrief":
        if opened:
            out.append("It has a situation card or a \"Ready\", and a debrief has neither.")
    else:
        if len(opened) > 1:
            out.append(f"It has {len(opened)} records of a situation card or a \"Ready\", and an interview has one.")
        if first is not None and not (opened and opened[0] < first):
            out.append("Its first question comes before the participant's situation card or \"Ready\".")

    ends = [i for i, r in enumerate(records) if r["t"] == "end"]
    if len(ends) > 1:
        out.append(f'It has {len(ends)} "end" records, and an interview ends once.')
    if ends and ends[0] != len(records) - 1:
        out.append(f'Record {ends[0] + 2} follows the "end" record, and nothing may.')
    answers = sum(r["t"] == "answer" for r in records)
    if ends and records[ends[0]].get("exchanges") != answers:
        out.append(f'Its "end" record says "exchanges": {json.dumps(records[ends[0]].get("exchanges"))}, and it has '
                   f"{plural(answers, 'answer')}.")

    seen = {}
    for i, r in enumerate(records, start=1):
        if r.get("side") is None or r.get("attempt") is None:
            continue
        who = (r["side"], r["attempt"])
        if who in seen:
            out.append(f"Records {seen[who]} and {i} are both of attempt {r['attempt']} of the {r['side']}: an "
                       "attempt is recorded once.")
        seen.setdefault(who, i)
    return out


def carried(entry: dict, held) -> bool:
    """Whether a launcher carries the conversation an entry belongs to: the entry says that one
    took it up ("carried"), and a launcher has the study (held: what the caller found of the
    study lock, and true to a launcher asking of its own study). This is the one rule for it. A
    launcher that was killed never took "carried" off, so with no launcher the mark is what it
    left behind, and the conversation reads as its log reads: partial, or pending with no turn
    on record, until the next command puts it down. Whether a process of it is still alive is
    another question, asked of the attempts (open_attempt())."""
    return bool(entry.get("carried")) and bool(held)


def interview_state(records: list[dict], carried: bool) -> str:
    """A conversation's lifecycle state, from its turn log and whether a launcher carries it
    (carried(), never an entry's "carried" by itself), first match first: "done" with an "end"
    record, whatever else is on record; "running" while it is carried, between two turns too;
    the state of the last "halt" (HALTS) when no "resume" follows it; "partial" with a card, a
    "Ready", a question or an answer on record; else "pending", which a log of nothing but
    "start", "lost" and "resume" records is too. A "halt" with no state of HALTS is no launcher's
    (turn_lacking()) and decides nothing."""
    if any(r["t"] == "end" for r in records):
        return "done"
    if carried:
        return "running"
    last = next((r for r in reversed(records) if r["t"] in ("halt", "resume")), None)
    if last and last["t"] == "halt" and last.get("state") in HALTS:
        return last["state"]
    return "partial" if any(r["t"] in SPOKEN for r in records) else "pending"


def extensions(records: list[dict]) -> dict[str, int]:
    """The allowances "resume --extend" has given each side of a conversation, {side: how many},
    by its turn log, which is the truth of it: one for each "resume" record whose "extended"
    names the side, and what the "start" record's "extended" says the side brought to a log
    that began again (a fresh start gives no allowance back, and takes none away), which
    counts one that the command that began the log gave, as "resume --extend" does when it
    is what finds that the log must begin again. "extended"
    on a runs.json entry is the launcher's copy of this, which it brings level before it
    queues a turn (launch.Supervisor.level()): a launcher that died between the record and
    runs.json so loses no grant, and none is counted twice."""
    start = next((r for r in records if r["t"] == "start"), {})
    brought = start.get("extended") if isinstance(start.get("extended"), dict) else {}
    return {side: (brought.get(side) or 0) + sum(r["t"] == "resume" and r.get("extended") == side for r in records)
            for side in SIDES}


def interview_progress(cfg: dict, entry: dict, records: list[dict]) -> dict:
    """How far an interview has got, from its turn log, with the keys run_progress() has: "units"
    are the topic ids of the persona's guide, "written" and "scored" alike the ones a question
    has carried, and "has_final" and "complete" alike whether the log has an "end" record. An
    interview that ended with a topic unopened is complete: the unopened topic is a finding.
    Two keys more: "exchanges", the answers on record, and "cap", the most the interview may
    have."""
    held = guide(cfg, entry["persona"])
    carried = {r.get("topic") for r in records if r["t"] == "question"}
    opened = [t["id"] for t in held["topics"] if t["id"] in carried]
    ended = any(r["t"] == "end" for r in records)
    return {"units": [t["id"] for t in held["topics"]], "written": opened, "scored": list(opened),
            "has_final": ended, "complete": ended, "exchanges": sum(r["t"] == "answer" for r in records),
            "cap": held["turns"]}


# ---------------------------------------------------------------- secrets and evidence

FINGERPRINTS = "accounts/fingerprints.json"  # what a scan knows the secrets of the test accounts by, lead only
SECRET_MIN = 4   # a secret shorter than this is not looked for: almost any text holds it by chance
SECRET_WORD = 8  # one shorter than this is found only as a word of its own, with no letter or digit against it
REDACTED = "(removed from the archive)"  # what archive.py leaves in accounts.map where a secret was
LEFT_OUT = ".left-out.txt"  # after a screenshot's name: the note an archive keeps where the screenshot would be
SHOWN = re.compile(r"[A-Za-z0-9._/:#~-][A-Za-z0-9 ._/:#~-]*")  # what shown() repeats of a panellist's own text
SHOWN_MOST = 40   # and how long a value it repeats: a longer one is described
PAGE_MOST = 120   # the same for the page of an address
PATH_MOST = 200   # and for a path under the study directory, which is what its file is found by: shown_path()
SCREENSHOT = re.compile(r"(?P<task>[A-Za-z0-9]+)(?:-a(?P<attempt>[1-9]\d*))?-(?P<step>\d+)"
                        r"(?P<view>[a-z]|-[a-z][a-z0-9-]*)?\.png", re.I)  # screenshot_step()


def _fingerprint(salt: bytes, value: str) -> str:
    return hashlib.blake2b(value.encode("utf-8", "replace"), key=salt, digest_size=16).hexdigest()


def read_fingerprints(study_dir: Path) -> dict:
    """A study's fingerprint record (module docstring, "Secrets"): {"salt", "runs", "secrets"}.
    A study without one gets an empty record with a salt of its own, which is on file only once
    remember_secrets() has something to keep. Exits when the file is there and cannot be used:
    without it the secrets of accounts already torn down can no longer be looked for, and that
    is not to happen quietly."""
    path = Path(study_dir) / FINGERPRINTS
    try:
        store = json.loads(path.read_text())
        bytes.fromhex(store["salt"])
        if not all(isinstance(store[k], list) for k in ("runs", "secrets")):
            raise ValueError
    except (FileNotFoundError, NotADirectoryError):
        return {"salt": os.urandom(16).hex(), "runs": [], "secrets": []}
    except OSError as err:
        raise SystemExit(f"Cannot read {path} ({err.strerror}): it is what a scan knows the secrets of the test "
                         "accounts by, so nothing was scanned.")
    except (ValueError, TypeError, KeyError):
        raise SystemExit(f"{path} is not a fingerprint record, so nothing can be scanned for the secrets of the "
                         "test accounts. Put it back as it was. If it is lost, delete it: the secrets of accounts "
                         "that were torn down can then no longer be looked for, and check_runs.py names them.")
    return store


def _note_secrets(store: dict, run: str, secrets: dict) -> bool:
    """Add a run and the fingerprint of each of its secrets to a record, in memory. Returns
    whether the record learnt anything."""
    salt, news = bytes.fromhex(store["salt"]), run not in store["runs"]
    if news:
        store["runs"].append(run)
    have = {(s.get("run"), s.get("name"), s.get("length"), s.get("hash")) for s in store["secrets"]}
    for name, value in secrets.items():
        value = str(value)
        if value == REDACTED:
            continue
        found = (run, str(name), len(value), _fingerprint(salt, value) if len(value) >= SECRET_MIN else None)
        if found not in have:
            have.add(found)
            store["secrets"].append(dict(zip(("run", "name", "length", "hash"), found)))
            news = True
    return news


def remember_secrets(study_dir: Path, run: str, secrets: dict | None):
    """Keep the fingerprint of each secret of a run's test account, so that a scan can still
    find the value once teardown has taken it off every record (module docstring, "Secrets").
    Whatever writes an account's record calls this with the secrets the record holds, before it
    writes. None, for a record that has no "secrets" yet, does nothing. The file is written only
    when there is something it does not have, in one step, readable by this user alone, and
    under a lock on its folder, so two writers never lose each other's."""
    if secrets is None or not _note_secrets(read_fingerprints(study_dir), run, secrets):
        return
    path = Path(study_dir) / FINGERPRINTS
    path.parent.mkdir(mode=0o700, exist_ok=True)
    folder = os.open(path.parent, os.O_RDONLY)
    try:
        fcntl.flock(folder, fcntl.LOCK_EX)
        store = read_fingerprints(study_dir)  # as it is now: another writer may have been here since
        _note_secrets(store, run, secrets)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            f.write(json.dumps(store, indent=2) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        os.close(folder)  # which lets the lock go


def known_secrets(cfg: dict, records: list[dict] = ()) -> dict:
    """Everything a scan of this study knows a secret by: the fingerprint record, and with it
    the secrets still written out, which are remembered first (remember_secrets()): those of
    accounts.map, and those of records, the account records in force (accounts.py). A study
    directory that cannot be written knows them for this scan all the same. Returns {"salt",
    "by_length": {length: {fingerprint: [its entries of the record]}}, "short": the entries of
    the secrets that are too short to look for, "runs": the runs the record has heard of}."""
    sd = cfg["_dir"]
    held = [(r["run"], r.get("secrets") or {}) for r in records]
    held += [(run, account["secrets"]) for run, account in ((cfg.get("accounts") or {}).get("map") or {}).items()
             if any(str(v) != REDACTED for v in (account.get("secrets") or {}).values())]
    try:
        for run, secrets in held:
            remember_secrets(sd, run, secrets)
    except OSError:
        pass
    store = read_fingerprints(sd)
    for run, secrets in held:
        _note_secrets(store, run, secrets)
    known = {"salt": bytes.fromhex(store["salt"]), "by_length": {}, "short": [], "runs": set(store["runs"])}
    for s in store["secrets"]:
        if s.get("hash"):
            known["by_length"].setdefault(s["length"], {}).setdefault(s["hash"], []).append(s)
        else:
            known["short"].append(s)
    return known


def secrets_in(known: dict, text: str) -> list[dict]:
    """The secrets whose value stands in a text, each as its entry of the fingerprint record
    ({"run", "name", ...}): never the value, which nothing here has. Every run of characters as
    long as a known secret is fingerprinted and compared, so a value is found wherever it
    stands, inside a longer word too. One shorter than SECRET_WORD is found only as a word of
    its own."""
    return list({(s["run"], s["name"]): s for _, s in _secret_places(known, text)}.values())


def _secret_places(known: dict, text: str):
    """Each place a secret's value stands in a text, as secrets_in() finds them: (where it
    begins, the secret's entry of the fingerprint record)."""
    salt, blake = known["salt"], hashlib.blake2b
    for length, prints in known["by_length"].items():
        whole = length < SECRET_WORD
        for i in range(len(text) - length + 1):
            if whole and (i and text[i - 1].isalnum() or text[i + length:i + length + 1].isalnum()):
                continue
            hit = prints.get(blake(text[i:i + length].encode("utf-8", "replace"), key=salt, digest_size=16).hexdigest())
            for s in hit or ():
                yield i, s


def _strings(value):
    """Every string in a parsed JSON value, keys too."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def scan_text(known: dict, text: str, form: str = "") -> list[tuple[int | None, list[dict]]]:
    """Where a text holds a secret: (1-based line number, the secrets on that line as
    secrets_in() gives them), in line order. form "jsonl" reads each line as JSON too, and form
    "json" the whole text, and looks through every string as it decodes, because a value with a
    quote, a backslash or a letter outside ASCII is written differently there. One found only
    in a decoded string of a "json" text has no line: its number is None."""
    if not known["by_length"]:
        return []

    def decoded(source: str) -> list[dict]:
        try:
            strings = [s for s in _strings(json.loads(source)) if s not in source]  # the others were looked through
        except ValueError:
            return []
        return [hit for s in strings for hit in secrets_in(known, s)]

    def distinct(hits: list[dict]) -> list[dict]:
        return list({(s["run"], s["name"]): s for s in hits}.values())

    out = []
    for n, line in enumerate(text.splitlines(), start=1):
        hits = secrets_in(known, line) + (decoded(line) if form == "jsonl" else [])
        if hits:
            out.append((n, distinct(hits)))
    loose = decoded(text) if form == "json" else []
    return out + ([(None, distinct(loose))] if loose else [])


def scan_file(known: dict, path: Path) -> list[tuple[int | None, list[dict]]]:
    """scan_text() for a file, read as text whatever it holds: a .jsonl or .json file in its form.
    Raises OSError, with the reason (unread()), when the file could not be scanned, which is
    never "nothing found": it may not be read, is a symbolic link or is reached through one, is
    no regular file, or holds more than READ_MOST bytes. Whoever scans names such a file and
    stops for it (check_runs.py, archive.py). path is under a study directory as load_study()
    resolved it, so a path that is not its own real path has a link on the way."""
    return scan_text(known, read_kept(path), Path(path).suffix.lower().lstrip("."))


def read_kept(path: Path) -> str:
    """The text of a file of a study that is scanned or copied, read as text whatever it holds.
    Raises OSError, with the reason (unread()), when it is a symbolic link or is reached
    through one, is no regular file, holds more than READ_MOST bytes, or may not be read."""
    path = Path(path)
    if Path(os.path.realpath(path)) != path.absolute():
        raise Unsafe("it is a symbolic link, or is reached through one")
    with os.fdopen(open_regular(path), "rb") as f:
        return f.read().decode(errors="replace")


def shown(known: dict | None, value, what: str, most: int = SHOWN_MOST) -> str:
    """How a value taken from a file a panellist wrote stands in a message or in a file that is
    kept: a task id the study does not have, a label, the name of a file in an evidence folder,
    the name of a screenshot or the page of an address in a step log. The one way such a value
    is quoted, in a usability study: the value itself only when it holds no secret that a scan
    knows (known_secrets(), by the same search as a scan), is no longer than `most` characters
    and is made of letters, digits, spaces and . _ - / : # ~ alone. Anything else is described
    and not repeated, with what it is not, as in "(a value that is not a task id, 14
    characters)". With known None nothing can be looked for, and every value is described."""
    text = value if isinstance(value, str) else str(value)
    if known is not None and len(text) <= most and SHOWN.fullmatch(text) and not secrets_in(known, text):
        return text
    return f"({what}, {plural(len(text), 'character')})"


def shown_path(known: dict | None, path, most: int = PATH_MOST) -> str:
    """shown() for the path of a file or a folder of a study, relative to the study directory:
    how it stands in a message or in a file that is kept. A panellist can write under panel/,
    so every part of such a path may be its own text, the folders above a file as much as the
    file's name. The whole path is searched, so a secret is found in the name of a folder too,
    and one that runs across a slash. The path is repeated in full when it holds no secret
    that a scan knows, each of its parts is made of shown()'s characters, and it is no longer
    than `most` characters: more than shown() allows a value, because a path is what its file
    is found by. Otherwise it is repeated as far down as all of that holds, which is never
    past where the first secret begins, and what is below is described and not repeated, with
    how many names deep it goes: "panel/personas/(a path of 2 names that is not shown, 17
    characters)". With known None nothing can be looked for, and the whole path is described."""
    parts = Path(path).parts
    text, keep, end = "/".join(parts), 0, -1
    if known is not None:
        most = min([most, *(at for at, _ in _secret_places(known, text))])  # nothing from the first secret on
        for part in parts:
            end += 1 + len(part)
            if end > most or not SHOWN.fullmatch(part):
                break
            keep += 1
    if keep == len(parts):
        return text
    rest = "/".join(parts[keep:])
    what = "a name" if len(parts) - keep == 1 else f"a path of {len(parts) - keep} names"
    return "/".join([*parts[:keep], f"({what} that is not shown, {plural(len(rest), 'character')})"])


def secret_owners(found: list[dict]) -> str:
    """Whose secrets a scan found, for a message, which never has a value: 'a secret of
    P03-opus's account ("password")'. Beyond three accounts the rest are counted."""
    names = {}
    for s in found:
        names.setdefault(s["run"], []).append(json.dumps(s["name"]))
    said = [f"{run}'s account ({', '.join(sorted(of))})" for run, of in sorted(names.items())]
    more = len(said) - 3
    return "a secret of " + " and of ".join(said[:3]) + (f" and of {plural(more, 'more account')}" if more > 0 else "")


def secret_places(hits: list[tuple[int | None, list[dict]]]) -> str:
    """Where scan_text() found secrets in one file, for a message: "line 12 (a secret of ...)",
    the first three places and a count of the rest."""
    said = [f"{'a value that reads as JSON' if n is None else f'line {n}'} ({secret_owners(found)})"
            for n, found in hits[:3]]
    return "; ".join(said) + (f"; and {plural(len(hits) - 3, 'more line')}" if len(hits) > 3 else "")


def secret_gaps(known: dict, records: list[dict]) -> list[str]:
    """What a scan of this study could not look for, a line each, for the script that scanned to
    print: the secrets of an account that was torn down before the fingerprint record had heard
    of it (records: every account record of the study), and the secrets too short to look for."""
    lines = []
    unheard = [r["run"] for r in records if r.get("torn_down") and r.get("source") != "map"
               and r["run"] not in known["runs"]]
    if unheard:
        lines.append(f"Not looked for: the secrets of the test {agree(len(unheard), 'account')} of "
                     f"{', '.join(unheard)}, torn down before the fingerprint record ({FINGERPRINTS}) had heard of "
                     f"{agree(len(unheard), 'it', 'them')}. Read the files of "
                     f"{agree(len(unheard), 'that run', 'those runs')} yourself.")
    short = sorted({s["run"] for s in known["short"]})
    if short:
        lines.append(f"Not looked for: {plural(len(known['short']), 'secret')} of the test "
                     f"{agree(len(short), 'account')} of {', '.join(short)}, shorter than {SECRET_MIN} characters, "
                     "which any text holds by chance.")
    return lines


def screenshot_step(cfg: dict, name: str) -> tuple[str, int, int] | None:
    """The step a screenshot's file name says it shows, (task id, attempt, step): <task>-<step>.png
    is of attempt 1 and <task>-a<attempt>-<step>.png of a later one. A letter after the step number
    names a further view of the same step, taken after scrolling: <task>-<step>b.png. A panellist
    that names one in words instead, <task>-<step>-scrolled.png, is read the same way. None for
    any other name and for a task the study does not have. Case is ignored, as task ids are unique
    without it."""
    m = SCREENSHOT.fullmatch(name)
    task = m and next((t["id"] for t in cfg["tasks"] if t["id"].lower() == m["task"].lower()), None)
    return (task, int(m["attempt"] or 1), int(m["step"])) if task else None


def _sensitive(value) -> bool:
    """Whether a step-log entry's "sensitive" marks its step: anything but a plain no does."""
    return bool(value) and str(value).strip().lower() not in ("false", "no", "0")


def run_evidence(cfg: dict, study_dir: Path, run: str) -> dict:
    """What a usability run's evidence folder holds, in a live study and in an archived round.
    The folder is opened and listed without following a link (evidence_fd()), and a link in it
    is never read:

        entries, odd   its step log (read_steps())
        log            whether the folder has a steps.jsonl that is a file
        screenshots    {file name: the steps it shows, each (task id, attempt, step)}: every PNG
                       file whose name says which step it is of (screenshot_step()) or that a
                       result entry names, a relative path to it in the folder included
        sensitive      {file name: (task id, attempt, step)}: the screenshots of a step with an
                       entry marked "sensitive", by the first such step
        left_out       the screenshot names an archive kept a note for in place of the file
                       (LEFT_OUT)
        missing        [(task id, attempt, step, name)] for each result entry that names a
                       screenshot which is neither in the folder nor left out by an archive
        other          the names of everything else in the folder, a folder's with a slash:
                       nothing an archive copies. A link is among them, whatever it points at
        refused        why nothing of the folder was read, None when it was, or there is none:
                       the folder or the evidence root is a symbolic link or no folder, or may
                       not be listed. Everything above is then empty
        log_problem    why the step log could not be read as the run's, None when it was, or
                       there is none: it is a link, a FIFO, or may not be read (step_log())

    Screenshots and "sensitive" go by every entry of the log, counted or not (counted()): an
    entry of no attempt can still name a file or mark a step, and leaving out more is the safe
    side.
    """
    out = {"entries": [], "odd": [], "log": False, "screenshots": {}, "sensitive": {}, "left_out": [], "other": [],
           "missing": [], "refused": None, "log_problem": None}
    try:
        held = evidence_names(study_dir, run)
    except OSError as err:
        return {**out, "refused": unread(err)}
    files = {name for name, kind in held if kind == "file"}
    try:
        step_log(study_dir, run)
    except OSError as err:
        out["log_problem"] = unread(err)
    entries, odd = read_steps(study_dir, run)
    named, marked = {}, set()
    for e in entries:
        step = (e["task"], e["attempt"], step_number(e))
        if _sensitive(e.get("sensitive")):
            marked.add((step[0].lower(), *step[1:]))  # a task id is known whatever its case
        shot = e.get("screenshot")
        if e.get("phase") == "result" and isinstance(shot, str) and shot.strip():
            path = Path(shot.strip())
            inside = path.parent == Path(".") or path.parent.name == run and ".." not in path.parts
            named.setdefault(path.name if inside else shot.strip(), []).append(step)
    out.update(entries=entries, odd=odd, log=STEP_LOG in files,
               left_out=sorted(name[:-len(LEFT_OUT)] for name in files if name.endswith(LEFT_OUT)))
    for name, kind in held:
        steps = [*named.get(name, []), *filter(None, [screenshot_step(cfg, name)])]
        if name in files and steps and Path(name).suffix.lower() == ".png":
            out["screenshots"][name] = list(dict.fromkeys(steps))
            secret = [s for s in steps if (s[0].lower(), *s[1:]) in marked]
            if secret:
                out["sensitive"][name] = secret[0]
        elif name not in files or not (name == STEP_LOG or name.endswith(LEFT_OUT)):
            out["other"].append(name + ("/" if kind == "folder" else ""))
    out["missing"] = [(*step, name) for name, steps in named.items() for step in steps
                      if name not in files and name not in out["left_out"]]
    return out


# ---------------------------------------------------------------- stats

def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else float("nan")


def sd(xs):
    xs = [x for x in xs if x is not None]
    return statistics.stdev(xs) if len(xs) > 1 else 0.0


def ranks(values: list[float]) -> list[float]:
    """Average ranks, 1 = smallest."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    r = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(x: list[float], y: list[float]) -> float:
    if len(x) < 3:
        return float("nan")
    mx, my = mean(x), mean(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def spearman(x: list[float], y: list[float]) -> float:
    return pearson(ranks(x), ranks(y))


def fmt(x, nd=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    return f"{x:.{nd}f}"


# ---------------------------------------------------------------- browser

# Expands collapsed content and forces common scroll-reveal patterns visible, so captured
# text and screenshots show what a reader who scrolled and clicked would see.
REVEAL_JS = (
    "document.querySelectorAll('details').forEach(d=>d.open=true);"
    "document.querySelectorAll('[aria-expanded=\"false\"]').forEach(b=>{try{b.click()}catch(e){}});"
    "document.querySelectorAll('.reveal,[data-reveal],[data-animate],.fade-in,.animate-in')"
    ".forEach(e=>{e.classList.add('is-visible','in','visible','revealed','in-view');"
    "e.style.opacity='1';e.style.transform='none';});1"
)


def which_montage() -> list[str]:
    if shutil.which("magick"):
        return ["magick", "montage"]
    if shutil.which("montage"):
        return ["montage"]
    raise SystemExit("ImageMagick is required (magick or montage on PATH)")


def which_convert() -> list[str]:
    if shutil.which("magick"):
        return ["magick"]
    if shutil.which("convert"):
        return ["convert"]
    raise SystemExit("ImageMagick is required (magick or convert on PATH)")


class Browser:
    """Thin wrapper over the agent-browser CLI with one named session."""

    def __init__(self, session: str):
        if not shutil.which("agent-browser"):
            raise SystemExit("agent-browser CLI is required")
        self.session = re.sub(r"[^A-Za-z0-9_-]", "-", session)

    def run(self, *args: str, check: bool = False) -> str:
        r = subprocess.run(["agent-browser", "--session", self.session, *args],
                           capture_output=True, text=True, timeout=180)
        if check and r.returncode != 0:
            raise RuntimeError(f"agent-browser {' '.join(args)}: {r.stderr.strip()}")
        return r.stdout.strip()

    def eval(self, js: str) -> str:
        out = self.run("eval", js)
        try:
            return json.loads(out)
        except (json.JSONDecodeError, ValueError):
            return out

    def open(self, url: str, width: int, height: int, settle_ms: int = 2500, media: str = ""):
        self.run("set", "viewport", str(width), str(height))
        if media:  # e.g. "light" or "light reduced-motion": stops captures landing mid-animation
            self.run("set", "media", *media.split())
        self.run("open", url, check=True)
        self.run("wait", str(settle_ms))

    def scroll_height(self) -> int:
        v = self.eval("document.documentElement.scrollHeight")
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return 0

    def close(self):
        self.run("close")
