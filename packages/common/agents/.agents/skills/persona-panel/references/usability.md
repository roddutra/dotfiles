# Usability studies

A usability study (`"type": "usability"`) tests whether a persona can get something done in a running product. Each panellist drives a browser through the tasks you set, thinking aloud, and logs every action with a screenshot. The analysis reports who completed what, by their own claim and by your check, and where runs got stuck.

`assets/study.usability.example.json` is a complete study. Its script paths (`scripts/make-account.sh` and the like) are placeholders: write your own, or `init_study.py`, `plan` and `run` stop and name the missing file.

## When to use one

| Question | Study |
|---|---|
| Which concept do prospects prefer, and what do they make of the page? | Review: panellists read captured materials and score them |
| Can this person finish this task in the product, and where do they stop? | Usability: panellists act in a running build |

A usability study compares nothing. It has one product, no concepts, no labels, no review order and no ranking. To compare two versions of a flow, run two studies with the same personas, tasks, models and step limits, and read the difference as a direction only.

It needs:

- **A running local build,** up during the pilot and the runs. A prototype counts when it runs in a browser at a local address.
- **The `agent-browser` CLI on PATH.** `plan` names its absence as a problem, and `run`, `pilot` and `resume` refuse.
- **A runner with the browser capability for every model entry.** All three have it today: `claude`, `codex` and `pi` (`references/runners.md`, Capabilities). Native mode is refused: the launcher starts each run's browser session and test account.
- **Memory for the browsers:** about 330 MiB for each run in flight.

## `study.json`

Personas, `models`, `runner`, `runners`, `limits`, `synthesis`, `replicates`, `segments`, `leak_terms` and `model_notes` work as in a review study (`references/runners.md`). These are the keys a usability study adds or reads differently:

| Key | Meaning |
|---|---|
| `type` | `"usability"` |
| `product` | Required: the product's name, which the briefs use. The instructions say "a product called **X**" unless `product_phrase` gives other words. `product_phrase` alone is refused |
| `target.base_url` | Where the product runs: `http://` or `https://`, a host and an optional port, with nothing after them (The target, below) |
| `target.allow_remote` | Default false. True permits a host that is not local (The target, below) |
| `tasks` | A list, attempted in the order written |
| `tasks[].id` | Letters and digits, unique ignoring case. It is the section heading (`### Task T1`), part of each screenshot's name and the `task` of each step log entry |
| `tasks[].goal` | What the person wants to get done, in their own words |
| `tasks[].start` | A path on the target where the task begins. Default `/`. One leading `/`, no `//`, no backslash or space, plain ASCII with anything else percent-encoded. A query or fragment is allowed |
| `tasks[].steps` | The step limit. Default 25 |
| `tasks[].success_check` | Optional command that says whether the task was really completed |
| `tasks[].read_only` | Default false. Your declaration that the goal can be met by looking. Required on every task of a remote target |
| `accounts` | Optional: `provision` or `map` (one of the two), `teardown`, `reset`, `signin` (Accounts, below) |
| `sequential` | Default false. True runs one panellist at a time, across all runners |
| `capture.desktop` | `[width, height]` of each panellist's browser window. Default 1440 x 900. No other `capture` key applies |
| `limits.run.minutes` | When left out, 30 seconds for each step the tasks permit, plus 5 minutes |
| `factors` | Default: Task success, Ease, Confidence, Clarity of next step, Trust, Overall (keys `success`, `ease`, `confidence`, `clarity`, `trust`, `overall`), scored 1 to 10 for each task |
| `context_notes` | Bullets in the instructions: what is made up, what is stubbed |

A study is one type or the other, and a key that would be quietly ignored is refused:

- A usability study refuses `concepts`, `labels`, `label_style`, `shuffle_labels`, `find_the_answer`, `artefact`, `artefact_plural`, `arrival`, `copy_ignore`, `extra_yes_bullets`, `"materials": "text"` and `"browse": false`.
- A review study refuses `target`, `tasks`, `accounts` and `sequential`.

**Commands** (`success_check`, `accounts.provision`, `accounts.teardown`, `accounts.reset`) are all run the same way:

- Split with shell rules and run without a shell, so no pipes, `&&` or variables: put those in a script.
- Run from the study directory, in the launcher's environment, with nothing on standard input and the run id as the last argument.
- The first word is an executable file, relative to the study directory, or a program on PATH.
- Each has 120 seconds, then is killed with whatever it started.
- The shape is checked when `study.json` is loaded. Whether the file exists is checked by `init_study.py`, by `plan` and at every start, so an archived study still loads.
- **What a command prints is never shown.** A failing script often prints what it was working with, a password included. The launcher gives the exit code and a fixed sentence, and puts what the command wrote in `<study>/accounts/<run id>.<command>.output` (mode 0600, never archived), which the message names: `P01-opus.teardown.output`, `P01-opus.check-T1.output`. Read that file to see why a command failed. It goes when the same command next succeeds for the run.
- **One command runs at a time, and none survives its launcher unnoticed.** A command still running after its launcher was killed is stopped by the next launcher command (SIGTERM, `--grace` seconds, SIGKILL) and treated as unfinished: a provision is cleared up with `teardown` and run again, a teardown, reset or check is run again. Write each so that it can be interrupted and repeated.
- **A process that a command left behind holds up the next command.** The launcher signals a command's process group only while the command itself is there to prove whose group it is. A worker that ignores SIGTERM while its command ends on it, or that is still at work after its command was killed from outside, is never killed. The launcher names its pid, keeps `accounts/command.running`, starts no command of the study and exits with 1: nothing is run, torn down or provisioned beside it. Check with `ps -o pid,pgid,command -p <pid>`, stop what is the command's, and run the launcher again: once the group is empty it carries on. If nothing there is the command's, delete `accounts/command.running` instead. Have each command end its own workers when it is stopped.
- **A command holds a lock while it or anything it started lives.** The lock is on `accounts/command.lock`, a file the launcher makes for each command: the command is given the open file, and so is whatever it starts that does not close it. The system lets go of the lock when the last of them has ended, and every shell sees that, whatever processes it sees. A process that left the command's group and still holds the lock holds up the next command too: the launcher cannot name it, so it names the lock file (`lsof <file>` lists what has it open, where `lsof` is installed), keeps `accounts/command.running` and exits with 1. Stop it and run the launcher again, or delete the record if it is meant to stay. A process started through `sudo`, or by Python's `subprocess`, closes the file and holds no lock: it is found by its process group, as above.
- **A command started on the other side of a sandbox is never signalled by its process id.** The record names the process namespace the command was started in. A launcher in another one, inside a harness's sandbox when the command was started outside it or the other way round, looks up and signals nothing under the recorded id, which names no process there, or someone else's. It never clears that record by itself either, whatever the command's lock shows: it keeps `accounts/command.running`, starts no command and exits with 1. Run the launcher from the shell that started the command, which can look (`references/runners.md`, A lead on Codex).
- **A free lock is not proof that such a command has ended.** With the lock held, the message says that the command or something it started is running where this shell cannot look. With the lock free it says that the command has probably ended and that this shell cannot be sure: a process that closed the lock file, as above, holds no lock. On a file system without locks it says that nothing tells whether the command has ended. In both of those cases, if the shell that started the command was in a sandbox that has ended, the command ended with it and no shell can look any more. Delete `accounts/command.running` and `accounts/command.lock`, then run the launcher again: it treats the command as unfinished, so a provision gets `teardown` before the run is provisioned again, and a teardown, reset or check is run again. This is the one place where a study waits for the lead after a sandbox has ended.
- **`stop` still stops the runs.** It is the one command that does its work first: it stops every run that is alive, starts no command of the study, then says what holds the study up and exits with 1. A run it settles as `done`, `limited` or `failed` keeps its account in force and gets no success check yet. Both stay due, and the next launcher command sees to them once the process is gone.
- **"Cannot tell" is never "nothing left".** Where no list of processes can be had (no `/proc` and no `ps`), nothing proves the command's group empty. The launcher keeps `accounts/command.running`, starts no command and exits with 1, as for a process it found: look for what the command left yourself, stop it, then delete the record.

## Designing tasks

**Goals.** A goal is all a panellist is given for a task, beside its start page and step limit. Write it in the user's words, with a motive and an end the person would recognise, and name no button, menu or page.

| Goal | Verdict |
|---|---|
| "You want to know roughly how much you could borrow for a home. See how far you get." | Good: a motive, an end, and room to give up |
| "Click 'Borrowing calculator' in the Tools menu and complete both steps." | Bad: it names the path, so the run tests reading, not finding |
| "Test the estimate form." | Bad: no person wants this, and nothing says when it is done |

- **One goal per task.** A task with two goals has one outcome line and one check.
- **Put the facts a form will ask for in the persona's bio** (income, dependants, postcode), or say in `context_notes` that figures are the persona's to invent. A panellist with no account is already told to make details up.
- **The persona and the account can have different names.** The account's display name comes from your provision script, so a page that greets someone else is the test's doing and no finding about the product. The instructions and each `account.json` say the account is lent for the test, and the briefs tell the analysts and the writer not to report the name. Before that, a panellist stopped at step 1 because the page greeted someone else.

**Order.** Every run attempts the tasks in the order written. Nothing is shuffled, so what a persona learnt in T1 is in every T2, on every run.

- A run keeps one browser and one account across its tasks: a sign-in, a saved figure or a basket carries over, and each task opens its own `start` page.
- A later task may depend on an earlier one. Its completion then measures both, so keep tasks independent unless the dependence is what you are testing.

**Step limits.** A step is one action on the page: a click, filling in a field, choosing from a list, pressing a key, or going to an address. Opening the start page, snapshots, screenshots, scrolling and waiting are not steps. The limit is per task and counts steps that have both their log entries.

- **Choosing from a drop-down list is one step,** made with `select`, with the choice read from the element list. A person would open the list and see the same choices, so this does not break "decide from the screen". A panellist that clicked a list open counted two steps for one choice, and the open list hid other controls in its screenshot.
- **Choose it from the shortest path.** Walk the task yourself and count the actions: a form of six fields and a button is seven, whether a field is typed in or chosen from a list. Then leave room for a wrong turn and the way back.
- **Too low** turns every hesitation into "ran out of steps". **Too high** lets an agent get there by patience where a person would have left.
- **Steps set the time limit** (30 seconds each, plus 5 minutes for the run) and the cost: each step adds a screenshot to the run's context.
- **The panellist keeps to the limit itself.** At the limit it records "ran out of steps" and goes on to the next task.
- **The launcher is the backstop.** An `intent` entry that begins a step beyond the task's limit stops the run as `limited`, with the reason "step limit: task T2, step 26 of 25": one numbered above the limit, or one intent more for the task than the limit allows. Renumbering does not help a panellist: an entry under an attempt number the launcher did not give is one more step of the task.
- **The count is the launcher's own, and only goes up.** How many steps of each task a run's process has begun is on the run's entry in `runs.json` (`steps` in the attempt), never under `panel/`. A step log that is emptied, cut short or changed where the launcher had read it starts no count again: the launcher says so once, notes it on the attempt (`rewritten`), and counts what the log holds from the first changed line on, on top of what it had counted.
- **A step log the launcher cannot read stops the run.** While a run is alive, a `steps.jsonl` that is a symbolic link, a FIFO, or a file or folder that may not be read stops the run as `limited`, with the reason "step limit: its step log cannot be read as the run's own (it is a symbolic link), so its steps cannot be counted". A log that does not exist yet stops nothing. Look at `panel/evidence/<run id>/`, put it right, then `resume --runs <id> --extend`: a run whose log is still unreadable is stopped again at once.
- **It is a backstop and no more.** It counts the steps a step log shows, while a launcher is running. A panellist that logs no step at all is bounded by the run's time limit alone.

**Success checks.** A check is your own script. It answers "did this run really complete this task" from the product's side, so the analysis can set it beside what the panellist believed.

- **It receives the run id** and finds the run's account in `<study>/accounts/<run id>.json`, which is still whole when the check runs.
- **When it runs:** once a run is `done`, `limited` or `failed`, before its account is torn down. Not for a `partial`, `blocked` or `pending` run, until you release it (Accounts, below).
- **It cannot be run again once the account is gone.** `launch.py <study> check` keeps a verdict made while the account was there (Running, below).
- **Check what the server holds,** such as the saved estimate or the callback request for that account. The address or page the browser ended on is what the panellist saw too, so it cannot catch a success that did not go through.
- **A check sees the whole run,** so a task's check must look for that task's result alone.
- **Keep it lead-only.** Nothing of a check is written under `panel/`: keep the script out of it too.
- **A task with no check** has completion by the panellist's claim alone, and the plan says so.

The exit code is the verdict:

| Exit code | Meaning |
|---|---|
| 0 | The task was really completed |
| 1 | It was not |
| Anything else, a timeout, a signal, a file that cannot be run | The check failed to run: no verdict. Reported in capitals and never counted as "not completed" |

Exit with 2 or more when the check cannot tell: the product is down, or the account is missing. An unhandled error in a Python script exits with 1, which reads as "not completed", so catch what can go wrong.

**What cannot be tested.** A second factor, an emailed or texted code, a real payment, a CAPTCHA and an outside sign-in provider are out of scope. Stub each in the test build (a fixed code that is always accepted, a fake payment step, mail that goes nowhere) and say so in `context_notes`. The instructions forbid creating real accounts, paying and sending messages to real people, and only the build can make those impossible.

## The target

- **A local development host by default:** exactly `localhost`, `127.0.0.1` or `[::1]`, or a name ending in `.localhost` or `.test`. A usability study signs in, fills in forms and submits them, so it runs against a local build.
- **`base_url` is read strictly,** so that it names the host a browser will go to. It is `http://` or `https://`, a host, an optional port (1 to 65535) and at most one trailing `/`, in ASCII. The host is a plain name (letters, digits, hyphens, single dots), four decimal numbers (`127.0.0.1`) or a bracketed IPv6 address. Refused outright:
  - a user name or password, a path, a query or a fragment
  - a backslash, a space, `@` or `%`, and any letter outside ASCII
  - a host ending in a dot
  - a host whose last label is a number without being four decimal numbers: `2130706433`, `0x7f.1`, `127.1`, `127.0.0.01`. A browser reads these as an IP address written another way
- **Every other way to write this machine is not local** and needs `allow_remote`: `127.0.0.2`, `0.0.0.0`, `[::ffff:127.0.0.1]`, `[0:0:0:0:0:0:0:1]`. So does a `.localhost` or `.test` name with a punycode label (`xn--`).
- **Panellists are given the address rebuilt from those parts,** lower-cased: `HTTP://App.LocalHost:8080/` becomes `http://app.localhost:8080`.
- **The rule reads the host name in `study.json` and nothing else.** A local name that proxies a hosted service passes it. Check what the build talks to: its database, its mail, its payment provider.
- **`"allow_remote": true` permits another host,** on two conditions the load enforces: every task says `"read_only": true`, and the study has no `accounts`. The instructions then tell panellists to submit nothing, sign in nowhere and change nothing, and the plan prints "REMOTE TARGET".
- **It enforces nothing in the browser.** Only that instruction stands between a panellist and a form, and every visit reaches the site's server and its analytics. Agree a remote target with the user first.
- **Nothing limits where a browser goes on a local target either:** another site, a `file://` path. The instructions say to stay on the product.

## Accounts

Give each run an account of its own, so no run sees another's data and one teardown makes its credentials worthless. Without `accounts`, panellists attempt the tasks signed out and are told so.

An account is one JSON object. `accounts.provision` prints it on standard output, and nothing else, for the run id it is given:

```json
{"identifiers": {"username": "test-P01-opus", "display_name": "Sam Ortega", "email": "p01-opus@example.test"},
 "secrets": {"password": "..."},
 "state": "states/P01-opus.json"}
```

| Part | Holds | Seen by |
|---|---|---|
| `identifiers` | Made-up values: username, email, display name. Required | The panellist, its model's provider, the evidence and the archive |
| `secrets` | Password, token, one-time code. Optional | No one, unless `"signin": "panellist"` |
| `state` | A saved browser state file, relative to the study directory. Optional. Refused under `panel/`, and it must exist | The run's browser session only |

Where the launcher puts them:

| File | Holds |
|---|---|
| `<study>/accounts/<run id>.json` | The whole account. Lead only, mode 0600 |
| `panel/scratch/<run id>/account.json` | What the panellist is told: `signed_in`, `identifiers` and a `note` on how it starts. `secrets` only with `"signin": "panellist"` |
| `logs/<run id>.<attempt>.state` | A private copy of the state for one attempt's browser session, which deletes it once loaded |

**The saved state** is what `agent-browser state save <file>` writes: cookies and local storage, with the session cookie in plain text. Treat the file as a secret. A provision script makes one like this:

1. Create the account.
2. Sign it in through a throwaway session: `agent-browser --session signin-<run id> open <base_url>/login`, then fill in and submit the form. Send the password on standard input through `agent-browser batch`, not on a command line.
3. `agent-browser --session signin-<run id> state save <study>/states/<run id>.json`, with a umask of 077 so the file is created mode 0600.
4. `agent-browser --session signin-<run id> close`.

- **Sign in on the host in `target.base_url`.** A cookie is tied to its host: a state saved on `127.0.0.1` does not sign in `localhost`.
- **`state save` does not carry IndexedDB.** A product that keeps its sign-in there, or in session storage, was not tested.

**Provision** runs just before a run's first attempt, and the launcher waits for it.

- **When it fails** the run "could not be started", nothing is marked failed, and no further run starts in that command. That includes output that is not the one JSON object expected: the message says so and names the output file, and never repeats what was printed.
- **It can run twice for one run id.** A `failed` run that is retried and a `limited` run that is extended were torn down, so they are provisioned again.
- **A new account has none of the old one's data.** So the run keeps the check of each task it had already written up, made with the account that is gone, and only the tasks it attempts afterwards are checked on the new one.

**Teardown** removes the account and its server sessions, so its password and its saved cookie stop working.

- **When:** once for each provisioning, when the run is `done`, `limited` or `failed`, after its success checks.
- **Afterwards** the secrets are gone from the record and from the panellist's `account.json`, and a state file the provision command made is deleted. The identifiers stay, because evidence refers to them.
- **Make it succeed for an account that is not there.** It also runs first after a provisioning that did not finish.
- **A teardown that fails** is reported in capitals and shown by `status`, with its exit code and the file its output is in. The account stays in force, the next launcher command that settles runs tries again, and `archive.py` refuses the study until it works.
- **No run carries on in an account that was to go.** A `failed` run whose teardown fails is not retried and stays `failed`. Once the teardown works, `run` (or `resume --runs <id> --extend` for a `limited` run) tears the account down first, then provisions a new one and starts. While it still fails the run is not started, and the command exits with 1.
- **A teardown cut short is done again.** The account's record notes a teardown before its command runs. A launcher killed part-way leaves that note, and the next launcher command runs the whole teardown again, whatever state the run is in, so make it safe to repeat.
- **Without one** an account outlives its run, and so does its saved session. The plan says so.

**`accounts.map`** is the alternative to a command: the same accounts written out in `study.json`, keyed by run id (`<persona id>-<model key>`, with `-r<n>` for a replicate). It must have one for every run and none for any other. Use it when the build has fixed, seeded accounts. Its state files are yours and are not deleted, and the archive replaces its secrets.

**Signed-in start is the default** (`"signin": "session"`). Each attempt's browser starts from the saved state, and the panellist is given the identifiers alone. No secret reaches the model, its provider, the harness's session record or a screenshot. An account with no state starts signed out with nothing to sign in with, and the panellist is told that is as far as it can go.

**`"signin": "panellist"` is for a study where signing in is the task under test.** The state is not loaded, and the panellist reads the secrets in its `account.json` and types them. The plan prints "SECRETS ARE GIVEN TO PANELLISTS", because:

- the secrets reach each model's provider and stay in each harness's session record
- any screenshot of the run may show one, so the archive leaves out all of that run's screenshots
- a password field is masked in the element list and in a screenshot, but a "show password" control or a plain field (a one-time code) shows the value in both. The instructions forbid both, and nothing enforces it.

**Sequential studies.** Where the build cannot hold separate accounts (one tenant, one shared dataset), set `"sequential": true`. One panellist runs at a time, whatever the runners' concurrency, so the wall clock is the sum of the runs.

- `accounts.reset` puts the product back as it was. It is refused without `"sequential": true`.
- It runs before an attempt whenever another run has used the product since this one last did: before every launch, retry and restart but the study's first, and before a resume unless the same run ran last.
- When it fails the run "could not be started", as for a provision.

**Releasing an account.** A `partial`, `blocked` or `pending` run keeps its account until it finishes: the credentials keep working and the archive is refused. For a run you will not continue, `launch.py <study> release --runs <ids>` runs its success checks, tears the account down and marks the run released. To continue it after all, name it with `--runs <ids> --released`, which gives it a new account.

## What a panellist does

The full text is `assets/usability-instructions.md`. For each task, in order:

1. Opens the start page and saves a screenshot of it as step 0.
2. Before every action, appends an `intent` entry to its step log: what it sees, what it expects, what it will do.
3. Acts, saves a screenshot, looks at it, and appends a `result` entry: what happened, the address it is now on, and the screenshot's name.
4. Stops when it believes the task is done, when its persona would give up, or at the step limit.
5. Writes the task's section in its persona file: an Outcome line that opens with "completed", "gave up" or "ran out of steps", the steps taken, where it hesitated (with step numbers), what it expected instead, and its scores.

After the last task it writes the final sections. A run is `done` when every task has a scored section and the final sections are there.

The evidence is in `panel/evidence/<run id>/`:

- **`steps.jsonl`**, two lines for each step:
  - `{"task", "attempt", "step", "phase": "intent", "sees", "expects", "action"}`
  - `{"task", "attempt", "step", "phase": "result", "happened", "url", "screenshot"}`
- **`sensitive: true`** on a result entry marks a step that entered a secret.
- **Screenshots** are `<task>-<step>.png`, with `<task>-0.png` for the start page.
- **A further view** is what a panellist saw after scrolling the page a step left it on: `<task>-<step>b.png`, then `c`. It belongs to that step and has no log entry of its own.
- **`attempt`** is 1 unless the run was cut off in the task and began it again (Running, below).

A panellist acts through refs from the element list (`agent-browser snapshot -i`) and is told to decide from the screenshot. The one thing it takes from the element list is the choices of a drop-down list (Step limits, above). It runs one `agent-browser` command per shell call and keeps the log with its file tools.

## Running

| Step | In a usability study |
|---|---|
| `init_study.py <study>` | Writes the instructions, persona files, prompts and `runs.json`, and makes each run's `panel/scratch/<run id>/` and `panel/evidence/<run id>/`. Provisions nothing. `--force` first stops a command a killed launcher left running, tears down every account in force and removes the step logs and screenshots |
| `capture.py`, `extract_answers.py` | Nothing to do: each refuses in one line |
| `launch.py <study> plan` | Prints the target, each task with its step limit and check, the time rule, the accounts, and the browser sessions |
| `launch.py <study> pilot` | The first persona on each model entry |
| `launch.py <study> run`, `status`, `stop` | As in a review. `status` shows "browser session up", a teardown that failed, and "released by the lead" |
| `launch.py <study> resume` | Continues `partial` and `blocked` runs. `--runs <ids> --extend` continues a `limited` one |
| `launch.py <study> check [--runs <ids>] [--force]` | Runs the success checks again, after you mend one (below) |
| `launch.py <study> release --runs <ids>` | Lets go of the account of a run you will not continue |
| `check_runs.py <study>` | Also scans for secrets and checks the evidence (Safety, below) |
| `extract_scores.py`, `analyze.py` | Also write `analysis/tasks.csv` and `steps.csv`, and a report of its own shape |
| `followup.py <study> ask` | The run gets no browser: its account is gone, so it answers from its persona file, step log and screenshots |
| `launch.py <study> run --role analyst`, `--role writer` | From `assets/usability-qual-brief.md` and `assets/usability-synthesis-brief.md` |

**Read in the plan:**

- **Memory.** Each run in flight holds a browser of about 330 MiB, and the plan gives the total for the concurrency in force. Lower `runners.<name>.concurrency` on a small machine.
- **The time limit.** 25 steps give 17.5 minutes. A step took about 6 seconds on a small Claude model and 7 to 10 on Codex at low effort. Larger models and higher effort were not measured, so use the pilot's time to set `limits.run.minutes`.
- **The accounts block,** and any line in capitals: a remote target, secrets given to panellists.
- **What each runner leaves open** with browsing on (`references/runners.md`, Browser sessions).

**`check` keeps a verdict whose account is gone.** A check run after teardown judges the run without what it did: it turned "completed" into "failed to run" in a real study.

- A task with a verdict (completed or not completed) made while the account was there is not run again. A line says so: "kept: the account is gone, so the check cannot be run again".
- A task with no verdict, or with "failed to run", is tried either way.
- `--force` runs every check all the same, replaces the record and says that the earlier verdict was replaced. Use it only for a check that does not need the account.
- An account that was let go in a study with no `accounts.teardown` is still in the product, so its checks run again as before.

**A run that is started afresh begins with an empty evidence folder.** Every start that is not a resume is a new session: `run` on a `failed` run or on one that `stop` left `pending`, the one retry of a failed run, and a `resume` that finds no session for a run that wrote nothing. A new session logs every task as attempt 1 and names its screenshots as the earlier one did, so the two would mix.

- The launcher first moves what the evidence folder held to `logs/<run id>.<attempt>.evidence/`, named for the last attempt the run had, makes the folder anew and says so.
- That folder is yours alone, like everything in `logs/`: nothing reads it as evidence, and it is never scanned or archived. It may hold a secret.
- Nothing is deleted, and a start that never ran as the CLI ("could not be started") puts the folder back.
- The attempt numbers the launcher had given the run's tasks (`task_attempts`) go with it: the new session is on attempt 1 of each.

**A resumed run** gets a new browser session on a blank page, signed in again when its account has a state. It keeps its evidence folder as it is.

- Tasks already written are not attempted again.
- A task that was under way starts again from its start page as a new attempt. Its new entries have `"attempt": 2` and steps numbered from 1, and its screenshots are named `T2-a2-<step>.png`.
- **The attempt number is the launcher's to give.** It is on the run's entry in `runs.json` (`task_attempts`) before the resume message is sent. An entry under any other number is left out of the analysis, never supersedes the steps a run took, and still counts towards the step limit. `check_runs.py` notes such entries.
- The earlier attempt's entries and screenshots stay in the log. The analysis reads each task's latest attempt, and "Steps taken" counts the tasks that were started again.
- What the earlier attempt changed in the product is still there when the run kept its account (`partial`, `blocked`). The resume message then says "You are signed in to the same test account again."
- A run that was provisioned again (`--extend`, `--released`) is told "Your test account is a new one: the one you had was closed when your run stopped, and nothing you did in it is in this one", and to read its `account.json` again.
- A run stopped at a step limit is continued with `resume --runs <id> --extend`, like any `limited` run, and is not stopped again for the step that stopped it.

## Reading the results

`analyze.py` writes `analysis/quant.md` in this order:

| Table | What it shows |
|---|---|
| Completion by task, by persona and by model | Of the attempts that ended, how many the panellist claimed as completed beside how many the check found completed |
| Claimed against checked | Every mismatch, run by run, then the checks that failed to run and the Outcome lines that could not be read |
| Steps taken | Mean, fewest and most steps for each task, how many attempts used the whole limit, how many tasks were started again |
| Where runs stopped | For each task: completed, gave up, ran out of steps, stopped at the step limit or the time limit, unfinished, not reached. Then one row for each run |
| Stuck points | Ranked by how many runs hit them, each with its runs, step numbers and screenshot names, and where each run ended the task |
| Step logs to check | What could not be read in a step log |
| Scores by task, by persona and by model | Each factor's mean |
| Incomplete runs | With the Overall score each gave a task before it stopped |

- **Completion, steps and stuck points count every run. The score tables count complete runs only.** A run stopped at a step limit is incomplete, and leaving it out would make its task look easier than it was.
- **Checked completion is a share of the attempts a check gave a verdict on.** Checks that failed to run and attempts with no check have columns of their own.
- **Never give one figure as "completion".** Report claimed beside checked.

**A mismatch is the most useful row in the report, and the first to verify:**

| Kind | Reads as | Before you believe it |
|---|---|---|
| Claimed completed, the check says no | The product looked finished and was not: a confirmation that shows before the save, a silent validation error | Open the run's last steps and screenshots, then run the check by hand on a task you completed yourself |
| Claimed gave up or ran out of steps, the check says yes | The product did the job and did not say so | The same. Also check that the task's check is not passing on another task's result |

**Stuck points** come from a script, not a reader. A stuck point is a task and a page address without its query. A run hits it in one of two ways:

- **It did not complete the task** (gave up, ran out of steps, stopped at the step limit), and this is the screen that held it: the one most of its last 4 steps left it on, and the later of two that tie. The evidence also gives the screen the run ended on and the one its last step was taken on.
- **It took 4 or more steps in a row there** that left the address unchanged.

The first is not "where the run ended". In a real study two runs left the form that blocked them for the help page and gave up there, and the help page ranked first until the rule changed. The definition's limits:

- It cannot tell a long form from a person going round in circles.
- It misses a wrong turn that changed the address.
- A run that wandered over several screens after the one that blocked it is counted against the last of them.
- In a product whose address never changes, every screen is one page.

The analysts refine the list from the step logs and screenshots: they confirm, merge, split or reject each point and add what the script missed.

**The step evidence** is what makes a finding checkable. The analysts and the writer cite the run, task, step and screenshot for every finding ("P05-opus, T2 step 7, `T2-7.png`"), and the writer leaves out a finding with no step to cite. Open the cited screenshots for the findings you report.

## Safety

**Where secrets live, and until when:**

| Place | Holds | Until |
|---|---|---|
| `<study>/accounts/<run id>.json` | The account with its secrets | Teardown takes the secrets out |
| A saved state file | The session cookie in plain text | Teardown deletes one a provision command made. A map's file is yours to delete |
| `panel/scratch/<run id>/account.json` | Secrets only with `"signin": "panellist"` | Teardown takes them out |
| `accounts/fingerprints.json` | A salted hash of each secret, so a scan still knows it after teardown. Lead only, never archived | You delete the study |
| `accounts/<run id>.<command>.output` | What a command wrote when it failed, which may include a secret. Lead only, never archived or scanned | The same command next succeeds for the run, or `init_study.py --force` |
| `study.json` | The secrets of an `accounts.map` | You remove them. The archived copy has them replaced |
| The harness's session record | Whatever a panellist read or typed | `purge-sessions`, where the harness allows it |

The fingerprint is a fast hash, so a weak password can be guessed from the file. Teardown is what makes the password worthless.

**The secret scan.** `check_runs.py` looks through every run's persona file and step log, the names of the files in its evidence folder, and every markdown file of `analysis/`, for every secret any run was given. A hit blocks, and names the file, the line and whose secret it was, never the value. `archive.py` scans every file it would hold.

- **A file that could not be scanned blocks too.** A persona file, step log or analysis file that cannot be read, or is a symbolic link, is named with the reason. "Could not be scanned" is never "nothing found".
- **No message repeats a panellist's own text unchecked.** A task id or label the study does not have, a file or screenshot name and a page address are quoted only when they hold no known secret, are short and are made of letters, digits, spaces and `. _ - / : # ~`. Anything else is described: "(a value that is not a task id, 14 characters)". The same rule covers `analysis/checks.md`, `runs.csv`, `tasks.csv` and `steps.csv`. A path under `panel/` is the panellist's own text in every part, a folder's name included, so `archive.py` quotes one only as far down as it is clean and describes the rest: "panel/personas/(a path of 2 names that is not shown, 17 characters)".
- **Nor a harness's own message.** When a CLI fails, the launcher prints the harness's message and keeps it as the run's reason, which `status` shows. A message that holds a known secret is withheld from both: the launcher says "the harness's message is withheld because it holds a secret of a test account" and names `logs/<run id>.<attempt>.err` and `.out`, which have it and are yours alone. So is every message while `accounts/fingerprints.json` cannot be used. A message with no known secret is printed as it is.
- **Evidence is never read through a symbolic link.** A panellist can write under `panel/`, so the evidence root, each run's folder and each file are opened without following one. A folder that is a link is named and left unread: `check_runs.py` fails the run, the launcher stops a run that is alive when its step log cannot be read as its own (Step limits, above), and the archive is refused. A persona file is read the same way, here as in a review study (`references/method.md`, Run states and the analysis).

It finds a value wherever it stands, inside a longer word and inside a JSON string. It does not find:

- a value written another way: split across lines, in another case, encoded or partly masked
- a secret shorter than 4 characters
- a secret of 4 to 7 characters with a letter or digit directly against it
- anything in a screenshot
- the secrets of an account torn down before the fingerprint record had heard of it. The scripts name its run: read that run's files yourself
- anything in `logs/` or a harness's session record, which are not scanned

**The archive** (`references/archive.md`) keeps each run's step log and screenshots, and leaves out:

- every screenshot of a run whose panellist was given a secret to type
- the screenshot of a step marked `sensitive`, with every further view of that step
- everything else in an evidence folder: only the step log and the PNG screenshots of steps are copied
- `panel/scratch`, `accounts/`, saved states and `logs/`

It refuses a study with an account still in force, with a secret value in any file it would hold or in the name of a kept file, a folder above one or a screenshot, or with a kept file, kept folder or evidence folder that cannot be read as the study's own: one that may not be read or listed, a symbolic link, which is named and never followed, or a FIFO, socket or device, which is never opened.

**Harness transcripts are the stated exception.** Each harness keeps its own session record, which resume and follow-ups depend on and the skill cannot edit. It holds everything a panellist read or typed, a secret included when `"signin": "panellist"`. Three things bound that:

- the accounts are throwaway ones on a local build
- teardown makes their credentials worthless when the run ends
- `launch.py <study> purge-sessions --yes` deletes the sessions once the study is archived

**What the browser enforces, and what stays an instruction:**

| Enforced by the session's policy, on every runner | Instruction only |
|---|---|
| No scripts in the page | Decide from the screenshot, not the element list |
| No page source, cookies, storage or saved state | Stay on the product: no other site, no `file://` address |
| No element text or value read by selector | Save screenshots in the evidence folder only |
| No network requests or console | Never use a "show password" control, or type a secret into a plain field |
| No new tabs, no closing the session, no restart with other options | Never create a real account, pay, or message a real person |

A run that reached the browser's debugging port could still read a cookie, and a `codex` run that may browse has network access in its shell (`references/runners.md`).

## How much to trust the result

- **An agent reads a page more thoroughly than a person and does not get bored.** It reads every label, tries again patiently and does not give up at the third form field. Real people will do worse wherever a task takes patience or close reading, so a task every run completed is not shown to be easy.
- **An agent that acts from the element list sees what a person might miss.** In the real study no step acted on an element that no screenshot showed (25 and 24 steps examined on two harnesses, one test app). The list is what a screen reader gets:
  - it includes elements below the fold, with nothing to say they need scrolling
  - it includes text for screen readers only, and a label such as "close dialog" where the screen shows an "X"
  - it leaves out visible content marked `aria-hidden`
  - the list of things to act on leaves out plain text, an error message included
  - it gives the choices of a closed drop-down list, which the instructions allow: a person would see them by opening it
- **Whether a run looked at its screenshots is not always knowable.** The `claude` runner's output (`logs/<run id>.<attempt>.out`) shows every file a run opened. The `codex` runner's shows no image views. In discovery a run reported a name as "not shown in the snapshot" while its screenshot showed it.
- **Small models follow the protocol less well.** In discovery a small model counted snapshots as steps and ran out early, and another run gave up after two refused shell commands. The instructions now cover both, and a new model can find new ways.
- **A difference between two models of one persona may be the model's,** as with scores. Run every persona on at least two models: the analysts say which differences follow the person and which the model.
- **Every result is a hypothesis to test with real people,** not a measurement of them. The writer restates each main finding as one, with the cheapest way to test it.

**What a pilot should confirm before the full run:**

1. Step 0 of each run shows the right account, signed in.
2. Every step has its `intent`, its `result` and a screenshot that exists. `check_runs.py` notes what is missing.
3. Steps count actions only: compare a step log with the task's limit.
4. `happened` matches the screenshot. Open a few steps of each model.
5. The "Out of character" notes say what the run learnt from the element list that the screen did not show.
6. Each success check gives a verdict, and the right one: run it by hand for a task you completed and for one you did not.
7. Teardown ran, and the pilot account's credentials no longer work.
8. `check_runs.py` finds no secret.
9. How long a run took against its limit. The next `plan` estimates from it.

Fix the tasks, the build or the instructions, then `init_study.py --force` and pilot again, so no protocol change lands mid-panel.
