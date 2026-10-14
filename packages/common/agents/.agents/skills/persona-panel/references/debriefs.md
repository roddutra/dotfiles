# Debriefs

A debrief is an interview held with a finished run of a review or usability study, in the session that run worked in, about what it did, saw and expected there. It is where questions about the user's own product go: the run has seen it, in the materials or in a browser, and that session is the only real past a persona has.

A debrief belongs to those two study types, and the lead of that study holds it. An interview study has none: its interviews are its runs (`references/interviews.md`). `<study>` below is the study directory.

Contents: [When to hold one](#when-to-hold-one), [How a debrief is carried](#how-a-debrief-is-carried), [The `debrief` block](#the-debrief-block), [Models](#models), [`limits.debrief` and what a debrief costs](#limitsdebrief-and-what-a-debrief-costs), [Holding the debriefs](#holding-the-debriefs), [Reading a transcript](#reading-a-transcript), [Who is refused](#who-is-refused), [States, stopping and going on](#states-stopping-and-going-on), [What a debrief writes](#what-a-debrief-writes-and-what-it-never-changes), [The analysts and the writer](#the-analysts-and-the-writer), [How much to trust a debrief](#how-much-to-trust-a-debrief).

## When to hold one

Optional, after the panel's runs are done and before the analysts. Hold one when the persona files leave open something that one fixed question would not settle: what a panellist expected at the step where it stopped, how it read a page, what it took a confirmation to mean.

| | Follow-up question (`followup.py`) | Debrief |
|---|---|---|
| Form | One wording, sent to every run named | A conversation: the interviewer follows each answer up |
| The answer | A `## Follow-up <n>` section the panellist appends to its persona file | A transcript of its own. The run writes nothing |
| Across runs | The same question, so the answers compare | Different questions for each run, so they do not |
| Allowance | `limits.followup` for each run, for each question | `limits.debrief` for each of the two sides, once |

**What it gives:** a transcript for each run, with the interviewer's reason for every question, which the analysts and the writer quote as product feedback.

**What it does not give:**

- **No number.** No score, ranking, outcome or step changes, and no script counts anything in a debrief.
- **No discovery.** The participant has seen the product, so nothing it says is evidence of a problem it had before. That is an interview study's question.
- **No second look.** The participant answers from what its session holds. It has no browser and no test account, and is told to open nothing.
- **No evidence about real customers** ([How much to trust a debrief](#how-much-to-trust-a-debrief)).

It needs:

- **A review or usability study on runners.** An interview study and a study in native mode are refused.
- **Finished runs whose sessions are still there.** Debrief before `launch.py <study> purge-sessions`.
- **The runs and the interviewer on a runner that is verified for interviews:** `claude` and `codex`. A run on `pi` cannot be debriefed, and the other runs of its study can.

## How a debrief is carried

The turn loop, the reply format, the caps, the repair, the leak gate and the end check are an interview's (`references/interviews.md`, The protocol, has each in full). There is no situation card. What a debrief lead needs of them:

- **Two sessions, with the launcher between them.** The interviewer is a new session and the participant is the run's own, resumed. The launcher resumes one side with the other's words and records each reply in the turn log, `interviews/<run id>.jsonl`. One process is alive for a debrief at any moment.
- **An exchange is one question and its answer.** Every cap counts exchanges, and a number in a transcript or a citation is an exchange number.
- **Every reply of the interviewer has a topic, a move, a reason and a question.** The topic is a topic id of the guide, `open` for an exchange outside every topic, or `close`. The move names the technique, one of twenty that `assets/interviewer-brief-debrief.md` explains. The reason is one sentence on what the interviewer is following. Only the question reaches the participant.
- **`debrief.turns` is exact.** The launcher ends the debrief once the last exchange the cap allows has its answer, and tells the interviewer beforehand that this question is its last and must be a close.
- **A topic's `turns` is advisory.** The interviewer is told when a topic has used them, and nothing enforces it.
- **A repair.** A reply that cannot be used is never delivered. It is sent back once, with every problem named: it does not follow the form, its topic or move is not one of the list, its question is empty or holds a leak term, or the last exchange is no close. The launcher prints "P01-a: a reply of the interviewer could not be used (topic)" and the debrief goes on. A second unusable reply in the same turn stops the debrief as `partial`, or at the last exchange ends it one exchange short with no close.
- **The leak gate.** Before a question is delivered the launcher looks for every `leak_terms` entry in it, ignoring case and inside longer words. A hit is a repair.
- **The end check.** An interviewer that ends while topics are unopened and exchanges remain is asked once to open them or confirm the end. A confirmed end stands, and the transcript names the topics never opened.

A line about a reply, a turn or a turn log that this file does not explain is the turn loop's own: `references/interviews.md`, Troubleshooting.

## The `debrief` block

Add it to the study's `study.json`, before the runs or after them. It changes no run, prompt, brief or score, and nothing is scaffolded again. No example asset has one:

```json
"debrief": {
  "interviewer": {"runner": "claude", "model": "<a model>"},
  "goals": [
    {"id": "G1", "learn": "Where in the booking the person slowed down or stopped, and what they expected there instead"}
  ],
  "topics": [
    {"id": "D1", "area": "making the booking", "opener": "Talk me through what happened when you tried to book the machine, from the first page on.", "goals": ["G1"]},
    {"id": "D2", "area": "the end of the booking", "opener": "What was the last thing you saw before you stopped?", "goals": ["G1"]}
  ],
  "turns": 8
}
```

| Key | Meaning |
|---|---|
| `debrief.interviewer` | The model entry of every debrief's interviewer. No default, and it must name a runner |
| `debrief.goals` | `[{"id", "learn"}, ...]`, at least one, as `interview.goals` in an interview study: `learn` is what to find out. A goal may name the product: a goal is never read to the participant |
| `debrief.topics` | As `interview.topics` in an interview study, at least one, opened in the order written: `id`, `area`, `opener`, `goals`, `turns` (default 8), `dig_for` and `segments` (below) |
| `debrief.turns` | The cap of one debrief in exchanges, which the launcher enforces. Default 30 |
| `limits.debrief` | `{"minutes", "budget_usd"}`: what each side of one debrief may use over all its turns. Default 10 minutes and $2.00 |

The keys of a topic:

| Key | Meaning |
|---|---|
| `id` | Letters and digits, unique ignoring case, and never `open`, `close` or `end`. A goal's id has the same form |
| `area` | A neutral name the interviewer may say aloud to raise the topic. A transcript shows it beside the id |
| `opener` | The topic's first question, which the interviewer is told to use word for word |
| `goals` | The ids of the goals the topic serves. Default none |
| `turns` | The topic's cap in exchanges. Default 8, and advisory ([How a debrief is carried](#how-a-debrief-is-carried)) |
| `dig_for` | Short lines on what the user most wants understood under the topic. Default none. The interviewer alone is given them, to choose which moment to follow and how far, and never says them. A leak term in one is a note, as in a goal |
| `segments` | Keeps the topic to personas of those segments. Default: every persona gets it |

Refused when `study.json` is loaded, by `init_study.py`, the plan and every command:

| Refused | The sentence, or why |
|---|---|
| `debrief.turns` below the number of topics plus two | "debrief.turns is 3, but 2 topics need at least 4: one exchange each, the opening and the close" |
| `about`, `situation_card` or any other key | "debrief: unknown keys: about (use interviewer, goals, topics, turns)". The interviewer is told what the session was in place of `about` |
| A topic id that is also a task id, ignoring case | "debrief.topics: the topic id "T1" is also a task id. ... Give the topic an id that no task has, such as "D1"". The interviewer is told the tasks by their ids |
| `limits.turn` | ""limits" must be an object with any of run, synthesis, followup, debrief and overrides". One turn of a debrief has 3 minutes |
| An empty `leak_terms` entry, or a persona with the id `interviewer` | As in an interview study: an empty term is found in every question, and the launcher names each interviewer's entry `interviewer-<run id>` |
| `debrief` in an interview study | Its interviews are its runs |

Looked at when a debrief is about to be held, and listed by the plan under "Debriefs", never when the study is loaded:

- **A leak term in a topic's `opener` or `area` stops every debrief:** "No debrief was held. study.json: debrief topic D1: its opener holds the leak term "Project Squeegee". The interviewer would say it, and a question that holds a leak term is never delivered. Reword it, or take the term out of "leak_terms"." The leak gate stays on in a debrief: in a review or usability study `leak_terms` are the internal words no panellist may be shown, and a debrief speaks to the panellist.
- **A leak term in a goal is a note, not a refusal.** A question that repeats the term is sent back once, and a second one stops the debrief.
- **Fewer than three exchanges a topic is a note:** "debrief.turns is 4, which leaves the 2 topics fewer than 3 exchanges each after the opening and the close, so a topic is likely to go unopened: an interviewer follows up the first one, and its last question is the close. 8 would give each topic 3." A real debrief of two topics capped at 4 exchanges ended at its cap with the second topic never opened. Set `turns` to three for each topic plus two, or more.
- **A persona that the topics' `segments` leave with no topic** cannot be debriefed, and the other runs can.

Writing the guide:

- **A goal is something to find out,** as in an interview study, and may say the product's name. Write what you would know afterwards that you do not know now: a goal that names the hoped-for answer turns the interviewer into an advocate.
- **An opener asks what happened in the session,** never what the participant thinks of the product: the interviewer's brief holds every question to the session, a specific moment and no verdict.
- **An opener is one question and names no difficulty:** one that presumes a struggle gets one from a polite participant. `references/interviews.md`, `study.json`, has the rules for an opener in full.
- **Name things as the participant knew them:** a task by what it asked for, a concept by its neutral label from `key.md` ("Concept B"). No panellist saw a concept's own id or name.

What each side is given:

| | Given | Never given |
|---|---|---|
| Interviewer | `assets/interviewer-brief-debrief.md` (the method turned on a session), the guide, the participant's name, role and segment, and what the session was: in a usability study the product as the panellists were introduced to it and each task by its id and goal, in a review the artefact and the neutral labels of the concepts | Anything a run wrote, scored or was checked for, a concept's own id or name, the persona's bio |
| Participant | Each question: the first inside `assets/debrief-opening.md`, which says what a debrief is, to answer aloud, and to write and open nothing, and each later one under the one line of `assets/debrief-question.md`, which says so again | The guide, a goal, a topic id, the interviewer's reasoning |

- **The interviewer is started with no tools,** as an interview's is, in the empty folder `interviewer/<run id>/`: no tool of any kind on `claude`, and on `codex` no shell, no file or image reading and no network, which is as few tools as its CLI allows and not none (`references/runners.md`, Interviews).
- **The participant is the run's own session, resumed in `panel/`** with the file tools it had and no browser (`references/runners.md`, Interviews). What keeps it from writing is what those two files tell it, and the put-back ([What a debrief writes](#what-a-debrief-writes-and-what-it-never-changes)).
- **The interviewer's provider receives the guide and every answer.** When it is not the provider the run was on, agree it with the user: the answers describe the product.

## Models

The tier rule of an interview study holds for a debrief's interviewer: a mid-tier model or larger, and the strongest available. The participant is whatever model the run was on. The plan prints the tier line for an interview study only, and nothing checks a tier. Mid-tier and top-tier interviewers were measured. A smallest-tier model on either side of a debrief was not.

## `limits.debrief` and what a debrief costs

- **Each side has the allowance once, over all its turns,** so one debrief can use twice the figure. It is apart from the run's own limits and outside the plan's ceiling.
- **Minutes count a side's own process time.** One turn has 3 minutes, or what is left of its side's time when that is less.
- **The budget is enforced where the harness has a cap** (`claude`, checked after each turn). On `codex` the time limit is what bounds a side.
- **There is no `--extend`.** A debrief that has used a side's allowance is at its end.

Measured in October 2026 on 14 debriefs of 3 to 6 exchanges, held with finished review and usability runs on `claude` and `codex` (148 turns, a median of 3.9 seconds a turn and a 95th percentile of 7.6). Each row is a side's whole debrief, with no turn that hung:

| Side | Process time | Used |
|---|---|---|
| Participant on a mid-tier model, review run, `claude` | 24 to 26 s | $0.03 |
| Participant on a mid-tier model, usability run, `claude` | 17 to 30 s | $0.19 to $0.24, of it $0.17 to $0.19 for the first turn |
| Participant, review run, `codex` | 36 to 42 s | 134,000 to 137,000 input tokens |
| Participant, usability run, `codex` | 17 to 39 s | 101,000 to 208,000 input tokens |
| Interviewer on a mid-tier model | 11 to 22 s, and 54 s where its first turn was slow | $0.02 to $0.06 |
| Interviewer on a top-tier model | 23 to 27 s | $0.14 to $0.15 |

- **The first turn of a usability run's debrief pays for its session again.** A debrief turn has no browser, so its tools differ from the run's and the harness's prompt cache is missed: 45,000 to 47,000 tokens were written to the cache again. A review run keeps its tools, and its first turn cost under $0.01. Later turns of either read from the cache.
- **Why $2.00.** The dearest side measured cost $0.24. On a top-tier model, a session of over about 100,000 tokens would pay about $1 for that first turn alone (worked out from the figures above, not measured). Raise `limits.debrief.budget_usd` for long sessions on a top-tier model.
- **`--runs all` multiplies it.** On a 36-run panel that is 72 sides: up to $144 where every harness enforces the cap. The debriefs measured cost $0.05 to $0.38 for both sides together, where both report a cost. Show the user the dry run when a ceiling was agreed.
- **A turn can be slow.** The first turn of two interviewers took 43 seconds, and two turns hung in their harness for the whole 3 minutes. The 10 minutes leave room for both.
- **Not measured:** a debrief held more than an hour after its run. Past a cache's lifetime the first turn of any run pays for its whole session.

## Holding the debriefs

```text
interview.py <study> debrief --runs <ids>|all [--dry-run] [--skip-unfit] [--grace <seconds>] [--poll <seconds>]
```

| Option | Meaning |
|---|---|
| `--runs <ids>` | Comma-separated panellist run ids. One that cannot be debriefed stops the whole command before any debrief is begun, unless `--skip-unfit` |
| `--runs all` | Every finished run whose debrief is not at its end. A run that is not finished is left out without a line. One whose debrief is `done` or `limited` is passed over with one. A finished run that cannot be debriefed for any other reason (a run on `pi`, a purged session) stops the command, unless `--skip-unfit` |
| `--dry-run` | Prints the lines the command would open with and stops. It takes no lock, starts no process and writes nothing. Exit code 0 when it can say of every run chosen what the command would do, 1 when one is "not known" (below) |
| `--skip-unfit` | Leaves out the runs that cannot be debriefed, with the reason for each, and debriefs the others |
| `--grace <seconds>` | How long a process gets to finish once it is stopped. Default 10 |
| `--poll <seconds>` | How often the command looks for a request to stop. Default 1 |

1. **`launch.py <study> plan`.** A study with the block, or with a debrief on record, has a section "Debriefs": the interviewer, the allowance, each debrief with its state, "Cannot be debriefed: ..." for a model entry or an interviewer on a runner that cannot carry one, and "Problem, which stops a debrief: ..." for a leak term. None of it changes the plan's exit code or stops `run`.
2. **`interview.py <study> debrief --runs all --dry-run`,** and read it:

   ```text
   Debrief: would begin 2 debriefs (P01-a, P01-b).
     Each side of each has up to 10 min and $2.00 over the whole debrief (limits.debrief), apart from the run's own limits, and one turn up to 3 min. So each can use twice that, and a side that is stopped at its limit gets 10s more to finish (--grace): at most 40.7 min of process time between them.
     The interviewer is on claude, model <model>, with the guide of study.json "debrief": at most 8 exchanges a debrief.
     At most $6.00 for the 3 sides on claude, whose harness enforces the cap.
     No budget cap for the 1 side on codex: the harness enforces none, so the time limit is what bounds it.
     This is outside the plan's ceiling. A debrief that has used a side's allowance is at its end: there is no --extend.
   Dry run: no debrief was held and nothing was recorded. Leave out --dry-run to hold them.
   ```

   It says "would begin", "would begin again" (a debrief that failed) or "would go on with" (one that stopped short) for each run, then the notes on the guide. On `claude` two more lines say that the cap is checked after each turn. After a launcher was killed it may say "not known" and exit with 1 ([States, stopping and going on](#states-stopping-and-going-on)).
3. **The same command without `--dry-run`,** in the background with your harness's shell tool or in a terminal, outside a sandbox as `run` is (`references/runners.md`, When the lead's own sandbox blocks the launcher). It prints the same opening lines, holds the debriefs side by side as interviews are held, at most as many at once as the interviewer's runner runs processes (`runners.<name>.concurrency`), and stays in the foreground until they end:

   ```text
   P01-a: running (debrief, participant on claude, interviewer on claude)
   P01-a: debrief done after 8 exchanges
   Debriefs: done 2.
     Transcripts of the 2 debriefs at their end (P01-a, P01-b): <study>/interviews/<run id>.md, and the analysts' copies in analysis/transcripts/.
   No run's state, score or persona file was changed. The analysts' and the writer's briefs name the transcripts as product feedback, so debrief before launch.py <study> run --role analyst.
   ```

   Exit code 0 when every debrief it held is `done`, 1 otherwise.
4. **Read each transcript,** `interviews/<run id>.md` ([Reading a transcript](#reading-a-transcript)): it is headed "Debrief", has no card, and names each topic's area.
5. **Then the analysts:** `launch.py <study> run --role analyst`.

What `--runs all` prints when there is nothing, or less, to do:

| Line | Exit code |
|---|---|
| "Passed over by --runs all, their debriefs being at their end: P01-a (limited), P01-b (done)." | The command goes on with the rest |
| "No debrief is left to hold: every finished run of this study has one at its end." | 0 |
| "No panellist run of this study is done, so there is no one to interview." | 1 |
| "No debrief was held: every finished run has to be one that can be debriefed. Pass --skip-unfit to debrief the others." | 1 |
| "No debrief was held: no run that is left can be debriefed." (with `--skip-unfit`) | 1 |

## Reading a transcript

Two files are written for each debrief, and `interview.py <study> render` writes them again:

| File | Holds | For |
|---|---|---|
| `interviews/<run id>.md` | The participant's name, role, segment and model key, a line on what a debrief is, then each exchange with its topic, move and reason, the question and the answer | The user and the lead |
| `analysis/transcripts/<run id>.md` | The same opening, then each numbered question that has its answer, with the answer, and nothing else | The analysts and the writer, who are kept from the interviewer's reasoning |

An exchange of the full transcript:

```text
### 2

- Topic: D1, making the booking
- Move: anchor
- Why: "It was a bit confusing" is a general impression, so I am asking for the one place it happened.

**Q:** Where were you when it first got confusing?

**A:** ...
```

- **Topic** is the topic the question counts for. Where the interviewer wrote another label it reads "D2, the end of the booking (the interviewer labelled it D1)": a question counts for the topic whose opener its words hold.
- **Lines in square brackets are the launcher's:** a reply that was sent back and why, a turn that left no reply, the end check, how the debrief ended ("[Ended at the cap of 8 exchanges.]", "[Ended by the interviewer after 6 exchanges: ...]", each with "Not opened: D2." where a topic never was), the interviewer's closing line that was not sent, and "[Not finished: ...]" for a debrief that has not ended.

What to look for:

- Did the interviewer keep to one question at a time, open every topic with its opener, and reach a close?
- Is an opener leading, now that you see what it drew?
- Which moments did the participant bring up, and which did the interviewer name first? Each `Why` says what the interviewer heard in the last answer ([How much to trust a debrief](#how-much-to-trust-a-debrief)).
- Does an answer hold a leak term, or speak of being an AI? No script reads a debrief for either.

## Who is refused

A refusal begins no debrief and records nothing of its own. The command first settles what a launcher that is gone left, and can change the records in doing so before it refuses: a turn that has ended since is appended to its turn log and saved to `runs.json`. The dry run writes nothing. The whole command:

| Refused | The sentence |
|---|---|
| An interview study | "A debrief is held with a finished run of a review or usability study, which has seen the product, and this is an interview study: its interviews are its runs. To ask more, put the question in the next round's guide." |
| No `debrief` block | "No debrief was held: study.json has no "debrief": the guide of a debrief, an object with interviewer, goals, topics and turns, as "interview" has them in an interview study. Add it, and no run or score changes: a debrief is held with runs that are finished." |
| Native mode | "No debrief was held: this study is in native mode, and a debrief cannot be held in one: the launcher carries every turn between the interviewer and a run's session, each through a runner." |
| An interviewer whose runner or model cannot be used | "No debrief was held: the interviewer (debrief.interviewer in study.json) cannot be started. ..." |
| No `--runs` | "debrief needs --runs <ids>, comma-separated, or --runs all for every finished panellist run that has not been debriefed." |
| A launcher has the study | The command does nothing. The dry run says: "A launcher is running "run" on this study (pid 123): "debrief" is refused until it has ended." |

One run, printed as "`<run id>`: cannot be debriefed: ..." (or "skipped: ..." with `--skip-unfit`), then "No debrief was held: every run named has to be one that can be debriefed. Take the runs above out of --runs, or pass --skip-unfit to debrief the others.":

| The run | The sentence |
|---|---|
| Is not finished | "it is partial, and only a finished run can be asked: a question to an unfinished run would be taken for its resume" |
| Has a process still running | "a process of it is still running" |
| Has no session to resume | "no session was recorded for it", "its session was purged (purge-sessions)", "its session no longer exists" or "its session was not saved" |
| Is on a runner that carries no interview | "pi is not verified for interviews, and an interview is carried turn by turn through its runner. Put the model entry on a runner that is (claude, codex)" |
| Has a persona with no topic | "its persona is left with no topic by the "segments" of the debrief's topics: every one is limited to other segments" |
| Has a follow-up question that is not settled | "a follow-up question to it is not settled (followup.py `<study>` list settles one that was cut short)" |
| Has been debriefed | "it has been debriefed: its transcript is interviews/P01-a.md, and a run is debriefed once" |
| Has a debrief at its end | "its debrief is at its end: the participant's turn used the last of its side's budget: none of its $2 left, and limits.debrief is the whole of a side's allowance, with no --extend. Its transcript is interviews/P01-a.md" |
| Is being debriefed now | "its debrief is being held now, by the launcher that has this study" |
| Is no run of the study, or is a job or an interviewer | "this study has no run of that name", "it is an analyst job, and only a panellist run can be asked" |

## States, stopping and going on

A debrief has an interview's states, read from its turn log. Its run stays `done` throughout.

- **`pending`:** no question is on record.
- **`running`:** a launcher is carrying it, between two turns too.
- **`failed`:** the interviewer's first turn left no reply: it ended with an error, lost its watchdog or was stopped at the turn limit.
- **`partial`:** it was put down with a question on record: `stop`, a killed launcher, a reply of the interviewer that could not be used twice, an answer that was empty twice, or a turn other than the interviewer's first that ended with an error, lost its watchdog or was stopped at the turn limit.
- **`blocked`:** a side's harness is turning requests away: a usage limit, a rate limit or a capacity refusal.
- **`limited`:** a side has used the time or the budget of `limits.debrief`.
- **`done`:** the turn log has an end record, written when the interviewer ended the debrief or `debrief.turns` was reached. The launcher then writes both transcripts.

| State of the debrief | Next |
|---|---|
| `pending`, `failed` | The same command, which begins it, or begins it again |
| `partial` | The same command, which goes on at the turn its log reached |
| `blocked` | The same command, once the harness takes requests again |
| `limited` | Nothing: it is at its end, and its transcripts are written from what there is. Named again it is refused, and `--runs all` passes it over |
| `done` | Nothing. A run is debriefed once |

- **Going on is the same command again:** `interview.py <study> debrief --runs <ids>`. `launch.py run` and `resume` take up no debrief. They settle a turn that a killed launcher left, or adopt one still running and put its debrief down when the turn ends.
- **`launch.py <study> stop`** stops the turns in flight: "Stopped. A debrief that was stopped is partial: go on with it with interview.py `<study>` debrief --runs P01-a,P01-b."
- **A killed command loses no exchange and repeats none.** On real CLIs it was killed mid-turn in both study types and the same command finished each debrief. `status` then says: "A launcher that is gone left a turn of a debrief in flight in P01-a (ended since) and P01-b (still running). interview.py `<study>` debrief --runs `<ids>` records what each turn came to and goes on with its debrief unless that turn was its last, and launch.py `<study>` stop records it and holds no debrief."
- **The dry run after a killed command** says of a turn that is still running that the command would go on: "A launcher that is gone left a turn in flight in P01-b (still running): the command takes over a turn that is still running, and goes on with its debrief from there." Of a turn that has ended with nothing recorded it cannot say, and exits with 1. Recording that turn can change what refuses its run, so the dry run judges nothing that it could change: not the run's session, not its runner, not the interviewer's. It prints no refusal for that run, and says so:

  ```text
  Debrief: not known for 1 debrief (P01-a). A launcher that is gone left a turn of it in flight, and that turn has ended since with nothing of it recorded. The command first records what that turn came to, and only then judges the run, its runner and the interviewer's: this dry run has judged none of them for that run. A debrief that none of them refuses then goes on, unless the turn was its last (it closed the debrief, or used the last of its side's time or budget, limits.debrief) or left a side with no session to resume: of such a run the command says why it cannot be debriefed, and --runs all passes over a debrief at its end and judges nothing more of it.
    This dry run cannot say which, so its exit code is 1, and the figures below count that debrief. launch.py <study> stop records the turn and holds no debrief: a dry run after it says which.
  ```

  One thing is still asked of such a run, since no record changes it: whether its debrief reads at its end already. One that does is refused by name, or passed over by `--runs all`, as any other. The other runs chosen are judged as usual, and the interviewer's runner when one of them can be debriefed. For a certain answer before anything is held: `launch.py <study> stop`, then the dry run again.
- **A side that uses the last of its allowance** ends the debrief: "P01-a: debrief limited after 5 exchanges: the participant's turn used the last of its side's budget: none of its $2 left" (of time: "none of its 10 min left"). The command then prints "At its end with a side's allowance used: P01-a. A debrief has no --extend." and exits with 1.
- **A turn stopped at the 3 minute turn limit** leaves the debrief `partial`. On one real pass two turns hung in their harness until that limit, and the same command finished both debriefs.
- **A run whose session is gone is left alone:** "..., so the run cannot be debriefed: a debrief is held in the session the run worked in. Left alone, with 3 answers on record". A debrief never starts afresh for want of the run's session. Its turn log stays, and `render` writes its transcript.
- **`init_study.py <study> --force`** replaces every run, so it moves the debriefs held with them (turn logs, transcripts and the interviewers' files in `logs/`) to `logs/interviews-<epoch seconds>/`.
- **`launch.py <study> purge-sessions --runs <run id>`** covers the run's session and its interviewer's.

**`launch.py <study> status`** has the debrief on its run's row:

```text
P01-a  done  1/1  Marg Petersen  [1 attempt, 1.6 min, 57,621 in and 2,753 out tokens, $0.08, debrief partial: 1 of 8 exchanges, awaiting an answer, participant: 2 turns, 5s, 17,962 in and 221 out tokens, $0.01, interviewer: 2 turns, 7s, 20,859 in and 229 out tokens, $0.01]  its debrief: the participant's turn was stopped by the stop command
```

Under the rows:

- "Debriefs: 3 on record, 1 done. What they use is outside the plan's ceiling, under limits.debrief, each side its own. The transcripts of P01-b are in interviews/`<run id>`.md, and the analysts' copies in analysis/transcripts/. P01-a has no transcript yet: a debrief's are written when it ends, and interview.py `<study>` render writes them from the turns so far."
- "Debriefs not finished: P01-a (partial). interview.py `<study>` debrief --runs P01-a goes on with each at the turn its log reached."
- "Debriefs at their end, a side's allowance used (limits.debrief): P01-c. A debrief has no --extend: its transcripts hold what was said."

The plan shows "done, debrief partial" in the run's State cell.

## What a debrief writes, and what it never changes

| Where | What |
|---|---|
| `interviews/<run id>.jsonl` | The turn log, written as each turn ends |
| `interviews/<run id>.md`, `analysis/transcripts/<run id>.md` | The full transcript and the analysts' copy, each headed "Debrief" with the notice. Written when the debrief ends or reads `limited`, and again whenever a brief is about to name them. Before that an unfinished debrief has none: `interview.py <study> render [--runs <ids>]` writes them from the turns so far |
| `prompts/interviewer-<run id>.md`, `interviewer/<run id>/` | The interviewer's prompt and its empty folder |
| `runs.json` | A new entry `interviewer-<run id>` with `"kind": "debrief"`, beside its run, and three keys of the run's own entry (below) |
| `logs/` | The input and output of every turn: `<run id>.<attempt>.*` and `interviewer-<run id>.<attempt>.*` |
| `analysis/usage.md` | The role `debrief` under "By role", where Runs are debriefs and Attempts are turns, and a table "Debriefs" with one row a side |

**On the run's entry in `runs.json`, three keys change:**

- `attempts` gains one `{"n", "kind": "debrief", "ended", "seconds"}` for each of its turns.
- `sessions` has its session's new totals.
- `debrief` is new: `{"turns", "seconds", "usage"}`, what the debrief's turns used. The run's own usage is its session's less this.

**Nothing else of the run changes:** not its `state`, `reason`, `seconds_used` or `extended`, not its persona file, scores or evidence. On real CLIs, the entry of each of the 12 debriefed runs that were compared differed in those three keys alone, every persona file and evidence file had the same SHA-256 before and after, and `check_runs.py`, the extract scripts and `analyze.py` gave the same output (`quant.md` byte for byte).

**The put-back.** A turn's process can write under `panel/`, so the launcher guards the run's own files:

- **Before each turn** the run's persona file is copied to `logs/<run id>.<attempt>.before`, and a usability run's evidence folder (its step log and screenshots) to `logs/<run id>.<attempt>.before.evidence/`. No copy, no turn: "P01-a: a turn of its debrief was not started: its persona file could not be copied before the turn (...)."
- **After it, a file that differs from its copy is put back,** and what the turn left is kept: "P01-a: a turn of its debrief changed its persona file, and a debrief may write nothing. The file was put back as it was before the turn, and what the turn left is in logs/P01-a.3.rejected.md." For evidence: "P01-a: a turn of its debrief wrote in its evidence folder, and a debrief may write nothing. steps.jsonl was put back as it was before the turn, and what the turn left is in logs/P01-a.3.rejected.evidence/."
- **A file the turn added to the evidence folder is left in place** and named in that line ("... was not there before the turn and was left in place: nothing a run wrote is deleted."). Read it, then remove it yourself.
- **The copies are deleted once the turn is settled.** So after a debrief `logs/` holds each turn's input and output, and a `rejected` file or folder only where a turn wrote. Read one before trusting that run's answers.
- **Until a turn is settled every script reads the persona file from its copy** and names the run: "P01-a: a turn of its debrief is not settled, so its file was read as it stood before the turn". The evidence folder is read as it stands.
- **A file that cannot be put back** (a folder at its name, or a folder above it that is a link) stops the launcher with the reason and what to put right. `launch.py <study> stop` then settles the turn.

## The analysts and the writer

- **Debrief before `launch.py <study> run --role analyst`.** A brief is written when its job starts. An analyst's lists the analysts' copies of the transcripts of its own personas' runs, the writer's lists them all, and a debrief held after a job has finished is not in that job's brief.
- **What the briefs say of them:** product feedback and qualitative evidence only. An answer is quoted exactly, cited by run and exchange number, and said to be given in a debrief, in answer to a question. It changed no score and is in no table. A real synthesis cited them so, and said they were "given in answer to the interviewer's questions, not raised unasked".
- **A debrief with no answer on record is not named** in any brief.
- **An unfinished debrief does not hold the jobs back.** Its transcript is written from the turns so far and listed as unfinished, and one line is printed first: "Debriefs not finished: P01-a (partial), P01-b (partial). The analysts are given what there is of them, said to be unfinished. To finish them first: launch.py `<study>` stop, then interview.py `<study>` debrief --runs P01-a,P01-b." The plan says the same under "Debriefs".
- **A turn that is not settled does:** "The analysts wait for the debrief of P01-a: a turn of it is still running, and its answer is not on record yet. Wait for it to end, or stop it with launch.py `<study>` stop. Then interview.py `<study>` debrief --runs P01-a goes on with the debrief, or run this again to analyse what there is."
- **Archiving** keeps the turn logs and both transcripts (`references/archive.md`, Studies that held debriefs). Reporting: `references/communicating.md`, Reporting debrief findings.

## How much to trust a debrief

- **It is the run's own session answering.** On real CLIs the answers named what only that session held: one run quoted the error message it had met and the date format it tried next, as steps 7 to 10 of its step log have them. That shows the session is reached. It makes the account no less a model's.
- **Every answer was asked for.** A panellist that said nothing of a page in its file and speaks of it in a debrief was led there by a question. A moment the participant brings up in the broad opening counts for more than one the interviewer names, and the `Why` line of the next question says which it was. Report an answer as given in a debrief, in answer to a question, never as something the panellist raised.
- **The caveats of any synthetic panel hold.** A model is more articulate, more patient and more agreeable than a busy person, and a reason given afterwards for a click is a model's account of its own session. Compare what a persona said on each of its models: what one model alone said is model taste.
- **An interviewer and a run on the same model** agree more readily, as in an interview study. Nothing notes it for a debrief.
- **No script reads a debrief for problems.** `check_runs.py` checks the runs, not the debriefs: a leak term in an answer or talk of being an AI is yours to find in the transcript. In a usability study the analysts' copies are scanned for a test account's secrets with the rest of `analysis/`, and `archive.py` scans both transcripts.

Known limits:

- **The put-back was never seen on a real model.** In the real debriefs no participant used a tool. In one study the opener asked both participants to edit their file, their score and their step log, and both declined. The put-back is covered by the tests on fake CLIs and was exercised by hand.
- **Only the run's own persona file and evidence folder are guarded.** As during any run, nothing puts back another run's persona file (the modification record, `logs/modifications.json`, flags it and `check_runs.py` blocks on it), another run's evidence, the scratch folders, the instructions, the materials or the site copies.
- **On `codex` a turn has its shell,** so it can also delete and rename under `panel/` and write in `/tmp`. A study kept under `/tmp` is writable whole by such a turn, as by any Codex run that does not browse.
- **Readers see a live evidence folder during a turn.** Only the persona file is read from its copy. Let the debriefs end before `check_runs.py`, the extract scripts or the analysts.
- **The dry run refuses a run whose follow-up question was cut short,** where the command settles that question first and may then hold the debrief. `followup.py <study> list` settles it: then the dry run again.
- **Not tested on real CLIs:** the refusal of a Pi run (tests only), a debrief more than an hour after its run, `purge-sessions` after a debrief, and a follow-up question put to a run that has been debriefed.
