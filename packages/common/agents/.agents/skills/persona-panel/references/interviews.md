# Interview studies

An interview study (`"type": "interview"`) is a round of simulated discovery interviews, run the way the book The Mom Test teaches: about the person's work, past events and what they already do and pay for, never about an idea. An interviewer agent talks to each persona in turn, the launcher carries every message between the two, and the analysis codes what was said into problem themes and marks the interviewer's questions.

`assets/study.interview.example.json` is a complete study, and `assets/interview-study-brief.md` is the brief to fill in with the user first. `<study>` below is the study directory.

Contents: [When to run one](#when-to-run-one), [Framing the round](#framing-the-round-with-the-user), [`study.json`](#studyjson), [Models](#models), [The protocol](#the-protocol), [Running](#running), [Checking](#checking), [Reading a transcript](#reading-a-transcript), [The analysis](#the-analysis), [Part of a panel](#part-of-a-panel), [Reporting](#reporting-to-the-user), [How much to trust the result](#how-much-to-trust-the-result), [Debriefs](#debriefs), [Troubleshooting](#troubleshooting).

## When to run one

| Question | Study |
|---|---|
| Which concept do prospects prefer? | Review |
| Can this person finish this task in the product? | Usability |
| What problems do these people have, which matter to them, and how do they cope now? | Interview |
| What did a panellist make of the product it has just reviewed or used? | A debrief on a finished review or usability run (`references/debriefs.md`) |

**What it gives:** a transcript of each interview with the interviewer's reasoning at every question, problem themes with who raised each and how well it is evidenced, a critique of the questions against the method, and a revised guide for interviews with real people.

**What it does not give:** evidence about real customers. A persona has no past, so a model invents each incident, figure and date. The output is hypotheses to test and a rehearsed guide. It says nothing about how often a problem happens, what it costs, or whether anyone would pay. Say so to the user before the round, and again with the results.

- **A standalone interview never names the user's own product.** A persona has never used it, so any history with it is pure invention, and naming it tells the participant what the team hopes to hear. The product's name and the team's words for its idea go in `leak_terms`, and nowhere else in `study.json`.
- **Questions about the user's own tool belong in a debrief:** a finished review or usability run has seen it.
- **No commitment is asked for.** The book tests a solution by what a person gives up for it. A simulated yes proves nothing, so the interviewer asks for no pilot, purchase, follow-up or introduction.
- **A new question after the round goes in the next round's guide.** `followup.py` refuses an interview study: an interview that has ended is closed.

It needs:

- **Every model entry on a runner that is verified for interviews:** `claude` and `codex` today. `pi` is refused at the plan step, and native mode when `study.json` is loaded: the launcher carries every turn (`references/runners.md`, Interviews).
- **No browser, no build and nothing to capture.** `capture.py`, `extract_scores.py`, `extract_answers.py` and `followup.py` each refuse an interview study in a line.

## Framing the round with the user

Copy `assets/interview-study-brief.md` to `<study>/study-brief.md` and fill it in with the user before writing `study.json`. It holds the team's hypotheses, so it stays beside `study.json`: `init_study.py` refuses to scaffold while a copy is under `panel/` or `interviewer/`, and it is refused as a `synthesis.context_files` entry.

Agree, in this order:

1. **The decision** the round informs, and what each outcome would change. A round that could change nothing is not worth running.
2. **The hypotheses,** each written as unproven, and **what would change the decision,** written before any result.
3. **The segment:** who does the work, who pays for it and who can refuse. Each is a persona, with a `segment` of its own where its topics differ.
4. **Three learning goals for each type of person,** each something to find out, never something to prove. One is the uncomfortable one: the question whose answer could end the idea.
5. **The topics,** each with a neutral area, an opener, its goals and its cap.
6. **The leak terms:** the product's name, code names, feature names and the team's own phrases for its idea.
7. **What the round cannot prove,** which providers may receive the personas and the guide, and the scale: personas, models, caps and the cost ceiling.

The user approves the guide and the roster before anything runs. Design the roster as for any study (`references/personas.md`).

## `study.json`

Personas, `models`, `runner`, `runners`, `replicates`, `segments`, `leak_terms`, the roster grid and variants work as in a review study (`references/runners.md`). `context_notes` go to participants, as facts about the setting. These are the keys an interview study adds or reads differently:

| Key | Meaning |
|---|---|
| `type` | `"interview"` |
| `interview.about` | One neutral sentence on the area of work, such as "how mortgage brokers run a loan from first enquiry to settlement". The interviewer states it as the purpose when it opens every interview, before the first topic's opener, and again when a participant asks what this is for. So every participant hears it before any question, and what it names is no longer something a participant can raise unprompted: name the whole area of work, not the part of it the team's idea is about, and never an idea, a product or a problem |
| `interview.interviewer` | The model entry of every interviewer of the study. No default. Its key is `interviewer` unless it gives one |
| `interview.goals` | `[{"id", "learn"}, ...]`, at least one. `learn` is what to find out. More than five draw a warning from `init_study.py`: none is then followed far |
| `interview.topics` | `[{"id", "area", "opener", "goals", "turns", "segments"}, ...]`, opened in the order written |
| `topics[].id` | Letters and digits, unique ignoring case, and never `open`, `close` or `end` |
| `topics[].area` | A neutral name the interviewer may say aloud to raise the topic |
| `topics[].opener` | The topic's first question, which the interviewer is told to use word for word |
| `topics[].goals` | The ids of the goals the topic serves. Default none |
| `topics[].turns` | The topic's cap in exchanges. Default 8. The interviewer is told when it is reached, and nothing enforces it |
| `topics[].segments` | Keeps the topic to personas of those segments. Default: every persona gets it. A goal that only topics kept from a persona serve is left out of that persona's interview |
| `interview.turns` | The cap of one interview in exchanges, which the launcher enforces. Default 30. At least the number of topics plus two, for the opening and the close |
| `interview.situation_card` | Default true: each participant writes a private situation card before the first question ([The protocol](#the-protocol)). False: it replies "Ready" |
| `limits.run` | What each participant may use over its whole interview. Default 15 minutes and $0.50. `limits.overrides` raises it for one model key |
| `limits.interviewer` | What each interviewer may use over its whole interview. Default 15 minutes and $1.00 |
| `limits.turn` | `{"minutes"}` alone: the most one turn of either side may take. Default 3 |
| `limits.synthesis` | `minutes` for each job, `budget_usd` as one pool divided equally among every job planned: the analysts, as many critics, the themes job and the writer. Default 30 minutes and $5 |
| `synthesis.analysts` | 1 or 2. Two split the personas by persona id, and there are as many critics, with the same halves |
| `synthesis.analyst`, `synthesis.critic`, `synthesis.writer` | Model entries, none with a default. The themes job runs on `synthesis.analyst` |
| `synthesis.decision_maker`, `synthesis.context_files` | Who the summary is written for, and extra files for the writer alone |

- **An exchange is one question and its answer.** Every cap counts exchanges, and a number in a transcript, a note or a quotation is an exchange number.
- **The minutes of a side count its own process time,** never the time since the interview began.
- **Where the defaults come from:** interviews measured on 13 October 2026. The slowest of 921 turns took 31 seconds, the longest side used 280 seconds of its own process time over 32 exchanges, and the dearest side cost $0.30 at list price over 34 exchanges. The interviewers ended by themselves at 23 to 34 exchanges with five topics capped at 8.
- **Topic caps that add up to more than `interview.turns`** cannot all be reached, and the plan notes it.

What is refused, each in a sentence that says what to do:

| Refused | Why |
|---|---|
| `concepts`, `labels`, `find_the_answer`, `artefact`, `tasks`, `target`, `accounts`, `sequential` and the other keys of a review or a usability study | Nothing is reviewed, attempted, captured or scored |
| `materials`, `browse`, `capture`, `factors`, `fit_factors`, `model_notes` | The same |
| `product`, `product_phrase` | A standalone interview names no product. Put its name in `leak_terms` |
| `debrief` | A debrief belongs to a review or a usability study |
| `limits.followup` | No follow-up question is put to an interview |
| A model entry with no runner | Native mode cannot carry a turn |
| A `leak_terms` entry in `interview.about`, a goal's `learn`, a topic's `opener` or its `area` | The interviewer would say it. Checked by `init_study.py`, by the plan and at every start |
| A persona whose segment no topic takes | It would have nothing to be asked. Add its segment to a topic, or take the persona out |
| An empty `leak_terms` entry | It is found in every question |
| A `synthesis.context_files` path under `interviews/`, `analysis/transcripts/`, `prompts/`, `interviewer/`, `panel/` or `logs/` | The writer is given the analysis and the guide, never what was said or how it was asked |
| A persona with the id `interviewer` | The launcher names each interviewer's entry `interviewer-<run id>` |
| A side of an interview on a runner that is not verified for interviews, or cannot resume a session | Refused at the plan step and by `run`, with the runners that are |

`interview.interviewer` and a persona's model entry may be the same runner and model. The plan notes it, and the study runs.

**Writing a learning goal.** Write what you would know afterwards that you do not know now: "How documents are collected from clients, and what happens when that goes wrong". A goal that names the hoped-for answer ("Confirm that chasing documents is painful") turns the interviewer into an advocate. The interviewer is told never to read a goal to the participant.

**Writing an opener.** It is the one question you control word for word, so hold it to the method:

- **Ask about a recent real event,** not a habit, an opinion or a future: "Walk me through the last loan where you had to collect documents from a client."
- **Name no problem.** "What do you struggle with when collecting documents?" presumes the struggle, and a polite participant supplies one.
- **One question.** No second clause that asks something else.
- **Put a broad topic first,** one that names no area ("What has taken most of your attention at work over the last couple of weeks?"), so that what a participant raises unprompted can be told from what was put to them.
- **Test each three ways:** could a polite yes answer it, does it ask about something that has not happened, and does it carry the answer the team hopes for?

**Writing a persona for an interview.** A participant can only recall what its bio gives it to build on: the tools it uses and pays for, who decides on them, how the work reaches it and its habits (`references/personas.md`).

## Models

**Both sides need a mid-tier model or larger, never a vendor's smallest and fastest tier, and the interviewer the strongest model available.** No model is named here or matched in the code, because models change: judge by tier. The plan prints the rule in every interview study, and cannot tell a tier from a name.

- **Why.** In testing, a smallest-tier model with no tools refused the participant's role or its situation card at launch on both harnesses (it wrote the card in 3 of 16 launches on one, and refused it in 4 of 13 on the other). Small models also asked two questions at once and left topics unopened. A mid-tier interviewer kept the format but opened the next topic under the old topic's label in 4 of 8 interviews, which the launcher now reads from the question's words ([Reading a transcript](#reading-a-transcript)).
- **A participant that will not hold the role is caught at its first reply.** That reply must be the situation card (or "Ready" with the card off). Anything else leaves the interview `failed` before an interviewer starts, with the reply kept on its turn log and the reason "the participant did not write its situation card: this model may be too small to hold the role. Use a larger one". `run` and `pilot` try once more by themselves. When it fails again, put the model entry on a larger model. Nothing gives a participant its tools back to work round it.
- **The tier of an entry with no `model` cannot be checked from the study.** It runs on its harness's default, which depends on the account. The plan prints `default` for it, and neither the plan, `status` nor `analysis/usage.md` says which model that is. `assets/study.interview.example.json` has such entries. Ask the user which model their account defaults to and name it in the entry. Otherwise tell them that side's tier is unchecked, and report it so: the first-reply check catches a model that refuses the role, and nothing else.
- **One interviewer for the study,** so that what differs between two interviews is the participant.
- **Every persona on at least two model entries,** from two vendors where runners for both are available. A theme a persona told of on one model and not on another is model taste.
- **The plan notes two things:** a participant on the interviewer's runner and model (one model then asks and answers, and agrees with itself more readily), and `synthesis.critic` on the interviewer's runner and model (the critique would come from the model that asked the questions: give it another where there is one). Both are allowed.
- **Default effort was what was measured.** A higher effort setting was not, so read the pilot's time against `limits.turn`.

## The protocol

**Two sessions for each interview.** A participant, started in `panel/rooms/<run id>/`, and an interviewer, started in `interviewer/<run id>/`. Both folders are empty and stay empty. The launcher carries every turn: it resumes one side with the other's words, records the reply in the turn log `interviews/<run id>.jsonl`, and resumes the other side. One process is alive for an interview at any moment, and an interview of 30 exchanges is about 60 processes.

**What each side is given:**

| | Given | Never given |
|---|---|---|
| Participant | The participant brief, its persona (name, role, personality, segment, bio), `context_notes`, then each question | The guide, a goal, a topic id, the interviewer's reasoning |
| Interviewer | The method, the reply format, the guide as this persona's interview has it, the participant's name, role and segment, seven short reference notes, then each answer with a status line | The persona's bio and personality, the situation card, the study brief |
| Analyst | The analysts' copy of its personas' transcripts, and who each persona is | The guide, the card, the interviewer's topic, move and reason |
| Critic | The full transcripts of the same personas, with the card and the interviewer's reasoning, who each persona is, and the study's guide | The study brief |
| Themes job | `analysis/notes.csv` | Everything else |
| Writer | The files under `analysis/`, the purpose, goals and topics, and `synthesis.context_files` | Every transcript |

**No tools on either side.** A side reads and writes no file, runs no command and browses nothing, so the guide, the card and the other interviews are not a file read away.

- **On `claude`:** no tool of any kind.
- **On `codex`:** no shell, no file or image reading and no network. Its CLI has no single switch, so that is as few tools as it allows and not none: a patch tool can still write files in the process's own empty folder, and a clock, three tools that read MCP resources, a tool to wait, tools that ask the user for input and sub-agent tools with the same set stay. The plan prints this under "Tools".
- **The jobs of the synthesis keep their file tools** and work in the study directory, where `study.json`, the study brief and the full transcripts are. For a job, "Never given" in the table is what its brief keeps from it: the brief tells it to open nothing else, and no file boundary stands behind that. Report it as an instruction, not as a control.

**The situation card.** With `situation_card` on, a participant's first reply is a private card in four parts: what is on its mind at work, two to four things that really bother it (each with one recent incident), things an outsider would assume are problems and are not, and what it uses and pays for. The launcher records it and never passes it on. It fixes the invented history before a question can shape it, gives the critic an answer key (which of the card's problems the interview found), and shows model taste: one persona on two models writes two cards.

**What the interviewer replies.** Every reply has one form, which the launcher parses:

```text
TOPIC: T2
MOVE: anchor
WHY: "We always chase documents" is a general claim, so I am asking for the latest instance.
SAY:
Which loan did that last happen on?
```

- **Only the words under `SAY` reach the participant,** word for word, with no frame, count or topic.
- **`TOPIC`** is a topic id of this persona's guide, `open` for an exchange outside every topic, or `close`.
- **`MOVE`** names the technique, one of sixteen: `open`, `priority`, `raise`, `anchor`, `sequence`, `consequence`, `coping`, `alternatives`, `frequency`, `constraint`, `money`, `deflect`, `dig`, `clarify`, `accept`, `close`. `assets/interviewer-brief.md` says what each is.
- **`WHY`** is one sentence for the user and the critic.
- **To end,** `END: <reason>` replaces `TOPIC`, `MOVE` and `WHY`, and the line under `SAY` is recorded and not sent.

The interviewer receives each answer between two lines of dashes, then a status line such as "Exchange 9 of 30. T2: 4 of 8. Not opened: T3.", then a notice when a topic has used its turns or one exchange is left.

**Caps.**

- **`interview.turns` is exact.** The launcher counts exchanges and ends the interview once the last one the cap allows has its answer. That exchange is meant to be a close: the interviewer is told "This is your last question: close the interview."
- **A topic's cap is advisory.** The interviewer is told "T2 has used its turns: move on or close." An exchange past the cap is delivered, counted and noted by `check_runs.py`.

**A repair.** A reply that cannot be used is never delivered. It is sent back once, with every problem named in one message: it does not follow the format, a field is missing, `TOPIC` or `MOVE` is not one of the list, `SAY` is empty, `SAY` holds a leak term, or the last exchange is no close. Each interviewer turn gets one send-back whatever the reasons. A second unusable reply in the same turn stops the interview as `partial`, or at the last exchange ends it one exchange short with no close.

- **Forgiven without a repair:** one code fence around the whole reply, blank space around it, a margin every line shares, and a `WHY` that runs over two lines.
- **Not forgiven:** a key in another case, markdown around a key, words on the `SAY:` line, text before the first key, a code fence around part of the reply.

**The leak gate.** Before a question is delivered the launcher looks for every `leak_terms` entry in its `SAY`, ignoring case and inside longer words. A hit is sent back as a repair that names the term. So a leak term that is a common word of the trade sends every question back: list the product's and the team's own words, not the area's.

**The end check.** An interviewer that ends while topics are unopened and exchanges remain is asked once: "T3 was not opened. Open it, or confirm the end with your reason." A confirmed end stands, since a participant who has no time for a topic is a finding. The unopened topics are on record and in the checks.

**An empty answer** is put to the participant once more. A participant may end the conversation in character: the interviewer then ends the interview with that as its reason, and it is `done`.

**Done is decided by the turn log,** never by an exit code: an interview is `done` when its log has an end record, written when the interviewer ended it or the cap was reached. The launcher then writes both transcripts.

## Running

| Step | In an interview study |
|---|---|
| `init_study.py <study>` | Writes a launch prompt for each side in `prompts/` (`<run id>.md` and `interviewer-<run id>.md`), `runs.json` with two entries for each interview, and the two empty folders. There is no `key.md`, no instructions file and no persona file. It ends "Nothing is captured for an interview study. Next: launch.py `<study>` plan" |
| `capture.py`, `extract_scores.py`, `extract_answers.py`, `followup.py` | Nothing to do: each refuses in one line |
| `launch.py <study> plan` | Prints the study, every interview with both sides' limits, the estimate and the ceiling (below) |
| `launch.py <study> pilot` | One whole interview of the first persona on each model entry |
| `launch.py <study> run`, `status`, `stop`, `resume` | As in a review, by interview. An interview is named by its participant's run id in every command and line. No command takes `--role interviewer` or `interviewer-<run id>` |
| `launch.py <study> check`, `release` | A usability study's: each refuses |
| `check_runs.py <study>` | Checks each interview from its turn log ([Checking](#checking)) |
| `interview.py <study> render [--runs <ids>]` | Writes both transcripts again, for an unfinished interview too |
| The analysis | Four job roles and two scripts, in a fixed order ([The analysis](#the-analysis)) |
| `launch.py <study> purge-sessions [--runs <ids>] [--yes]` | Covers the sessions of both sides of each interview. Refused while a turn is in flight |

### The plan

Read all of it, and confirm the cost and the gaps with the user before anything starts. The parts an interview study adds:

- **"Interview study, what each interview is":** the guide, the interviewer's runner and model, each cap and limit with who enforces it, how many interviews are carried at once (as many as the interviewer's runner runs processes at once, `runners.<name>.concurrency`), the tools each side has on each runner, the line on model tiers, and any note.
- **"Model entries":** one row for each participant model key and one for the interviewer, each with its side's time limit and budget. "not enforced" beside a budget means the harness has no cap, and the time limit is what bounds that side.
- **"Interviews":** one row each, with what its two sides may use, the cap of each topic its persona gets, the exchanges on record of its cap, and its state.
- **"What each provider receives":** a participant's provider gets its prompt and every question. The interviewer's gets its prompt, the guide and every answer. Each job's line says what it is given.
- **The jobs,** with each one's share of the pool, what it has used and has left once it has run, and the order of the analysis with what each step waits for.

**The estimate.**

- **Before a pilot** it is input tokens only, for an interview that runs to its cap, by runner and by side and not by model: "About 67,200 input tokens for an interview that runs to its cap of 12 exchanges". It is a forecast and no ceiling. An interview that ends before its cap uses less, and a first reply, a repair and a turn that is put again are not in it. Nearly all of that input is read from a cache after a side's first process, so it is not what is billed. There is no dollar figure, because the skill keeps no price tables.
- **After a pilot** it is measured: "measured on 2 finished interviews: 70,578 tokens, $0.0426 and 56s an interview. They ran 12 exchanges on average: about 5,882 tokens and 4.7s an exchange." Judge an interview of another length by the figure for an exchange.
- **What real interviews used:** a 12-exchange interview took about a minute of process time a side on `claude` and a minute and a half on `codex`, at $0.04 to $0.08 a side at list price on mid-tier models. A 34-exchange interview with a largest-tier interviewer and a mid-tier participant cost $0.41 for both sides and took 5 minutes.

**The ceiling** counts the cap of each side of each interview once, plus the synthesis pool. It is "a guaranteed maximum" only when every side and job is on a runner that enforces a budget cap. With a side on `codex`, which has none, it is labelled an estimate, those sides are left out of the figure and named, and their time limits are what bound them. A job on `codex` is counted the other way: the pool is in the figure whole, so that job's share is counted though nothing enforces it, and the plan names the job. `resume --extend` on either side breaks it, and the plan says so. No figure here holds the study to a total in dollars or lets one be checked afterwards: say so to a user who sets one (`references/method.md`, Limits and the plan).

### Pilot, then run

1. **`launch.py <study> pilot`,** in the background with your harness's shell tool or in a terminal. It prints one line when an interview is taken up, one for anything out of the usual course, and one when it is put down:

   ```text
   P01-a: running (interview, participant on claude, interviewer on claude)
   P01-a: a reply of the interviewer could not be used (topic)
   P01-a: done after 12 exchanges
   Finished: done 2.
   ```

2. **Read each pilot transcript,** `interviews/<run id>.md`, before the rest:
   - Does the participant sound like the persona, in two to five spoken sentences, starting general and giving an instance only when asked?
   - Did it say that something is not a problem? A card whose "Not a problem" part never surfaces points at leading questions.
   - Did the interviewer keep to one question at a time, open every topic with its opener, and reach a close?
   - Is an opener leading, now that you see what it drew?
   - How long did a turn take, against `limits.turn`?
3. **Fix the guide or the personas now,** then `init_study.py <study> --force` and pilot again, so no change lands mid-round. Pilot interviews that need no fix count: `run` starts only the rest.
4. **`launch.py <study> plan` again:** its estimate is now measured.
5. **`launch.py <study> run`.** It ends with where the transcripts are: "Transcripts of the 4 interviews that are done: `<study>`/interviews/`<run id>`.md, and the analysts' copies in analysis/transcripts/."

A lead in a sandboxed shell needs `run`, `pilot`, `resume` and the job commands outside the sandbox, as for any study (`references/runners.md`, When the lead's own sandbox blocks the launcher).

### Status

`launch.py <study> status` has one row for each interview:

```text
P01-a  running  Dana Whitlock  [2 of 30 exchanges, 1 of 3 topics opened, the participant is answering, process alive, pid 123, participant: 3 turns, 16s, 12,239 in and 914 out tokens, $0.02, interviewer: 3 turns, 10s, 30,906 in and 340 out tokens, $0.04]
```

- **In the brackets:** the exchanges with an answer, of the cap; the topics opened; which side is replying or awaited; the process of the turn in flight, or "between turns"; then each side's turns, process time and usage, with "extended" or what became of its session where that applies.
- **After the brackets:** the reason the interview stopped, from its turn log: "the participant's turn was stopped by the stop command".
- **A turn is one process,** so a side has one more turn than exchanges where a card, a repair or a turn put again was needed.
- **Under the interviews:** the jobs, headed "Analysts, critics, themes and writer:".

### States

An interview's state is read from its turn log every time and written nowhere, so both its entries always agree.

| State | What happened | Next |
|---|---|---|
| `pending` | No turn on record | `launch.py <study> run` |
| `running` | A launcher is carrying it, between two turns too. It reads so only while a launcher has the study | Wait |
| `done` | The log has an end record | Nothing |
| `partial` | It was put down with a turn on record: `stop`, a killed launcher, a reply that could not be used twice, or a turn that was stopped at `limits.turn`, ended with an error or lost its watchdog | `launch.py <study> resume` |
| `limited` | A side has used its time or budget. The reason names the side and its whole allowance: "the participant has none of its 15 min left after 31 turns", or of the turn that used the last of it "the interviewer's turn used the last of its side's budget: none of its $1 left". The harness's own words for a budget name the cap of that one process, and stay in the turn's output in `logs/` | Read the transcript, then `launch.py <study> resume --runs <ids> --extend`, which gives that side one more allowance. The plan's ceiling then no longer holds, so ask the user first |
| `blocked` | A side's harness is turning requests away: a usage limit, a rate limit or a capacity refusal. The reason has the harness's words, and `status` says when the limit lifts where the harness said | `launch.py <study> resume`, once it takes requests again |
| `failed` | A side's first process left no usable reply, or the participant's first reply was not the card | `launch.py <study> run`. Read the reason first: a participant that did not write its card needs a larger model |

- **`resume` continues at the turn the log reached,** in both original sessions. Nothing with an answer on record is asked again, and every turn on record is kept.
- **A turn that left no reply is put again only by `resume`,** never unasked: a turn that hung for the whole of `limits.turn` is for the lead to look at first. The side is told its reply was lost. Its session may then hold an answer the transcript does not, which is accepted.
- **A turn stopped at `limits.turn` leaves the interview `partial`,** or `failed` at a side's first process. It is never `limited`: no allowance was used up.
- **`run` never restarts a `partial` or `limited` interview,** and names the command that does.
- **When the interviewer's runner is turned away, every interview stops,** since all share it. A participant's runner that is turned away stops its own interviews.
- **Replicates** are separate interviews, each with a card of its own.

### Stop, a killed launcher and sessions

- **`launch.py <study> stop`** stops the turn in flight of every interview and prints: "Stopped. Interviews with a turn on record are partial: continue them with launch.py `<study>` resume, which puts the turn that was stopped again. Interviews with none are pending: start them with launch.py `<study>` run."
- **A killed launcher loses no turn and records none twice.** Each reply goes to the turn log before anything else. The turns in flight end under their own watchdogs, and the interviews read `partial`. `status` then says: "A launcher that is gone left a turn in flight in P01-a (still running). launch.py `<study>` resume records what each turn came to and goes on with its interview, and stop records it and leaves the interview partial." `check_runs.py` names the same command, never to wait.
- **A session that is gone** (purged, lost by its harness, or never saved) ends resume for that interview. Both sides are asked before every turn.
  - **With no answer on record** the interview starts afresh: its turn log moves to `logs/<run id>.interview-<k>.jsonl`, both sides are launched anew, and each keeps its attempts and usage. A command does that once for an interview.
  - **With an answer on record** it is left alone and the command exits with 1: "the participant's session was purged (purge-sessions), so it cannot be continued. Left alone, with 5 answers on record. To hold it again from the start, move interviews/P01-a.jsonl into logs/ and use run". Decide: keep the part there is, which the analysis reads as an unfinished interview ([Part of a panel](#part-of-a-panel)), or move the log as the line says and `launch.py <study> run --runs <run id>`. The summary still ends "Next: resume" for such an interview: go by the line above it.
  - **A lost session is found only by trying:** the resume that finds it gone says so ("the participant's session no longer exists"), and is no attempt.
- **`init_study.py <study> --force`** starts every interview again. The turn logs, both sets of transcripts, the files of the replaced attempts and `analysis/usage.md` and `checks.md` move to `logs/interviews-<epoch seconds>/`, never deleted. The sessions stay on record in `logs/earlier-sessions.json` for `purge-sessions`. It is refused while a launcher has the study or a process of it is alive.
- **`purge-sessions`** ends resume for the interviews it covers. Run it when the round is analysed and archived.

## Checking

`check_runs.py <study>` reads each turn log, prints a table and writes `analysis/checks.md`. It exits with 1 when any interview has a blocking problem, and ends "4 interviews with a turn log, of 4 expected; 0 with blocking problems."

Blocking. A blocking problem makes `check_runs.py` exit with 1, and does not by itself keep an interview out of the analysis. The tallies leave out only an interview with no end record. A finished interview is given to its analyst and its critic and counted in `quant.md` whatever else its row says, so repair it or discard it before analysing:

| Problem | What it means | What to do |
|---|---|---|
| "no end record: it reads partial, after 2 of 12 exchanges" | The interview is not finished, or was never held. `quant.md` has it in no table and counts none of its notes. Analysts and critics wait while it reads `pending`, `running` or `blocked`, and read a `partial`, `limited` or `failed` one as unfinished ([Part of a panel](#part-of-a-panel)) | The command for the state it reads as, which the lines under the table give with the run ids filled in |
| "turn log of the wrong form: Record 8 (answer) lacks "text", which a launcher always writes" | The log was changed by hand or damaged. Nothing else of it is checked, and `run` and `resume` leave the interview alone. The analysis reads what it can of such a log: with an end record the interview is finished, and is tallied from the records that can be read | Put back what was changed, or discard the interview, before analysing |
| "leak term "LoanLoop" in question 7, which was delivered" | The gate lets none through, so the term was added to `study.json` afterwards or the log was changed. The participant has read it. A finished interview is tallied with the leak in it | Discard the interview before analysing, or keep it and report the leak with whatever is drawn from it |

To discard an interview and hold it again: move `interviews/<run id>.jsonl` into `logs/`, then `launch.py <study> run --runs <run id>`, which launches both sides anew. To discard it and not hold it again, move the log and stop there. The interview then reads `pending` with no turn on record: no analyst or critic is given it, and `quant.md` counts it as not started. `check_runs.py` still exits with 1 for it, and the analysts and critics start only with `--allow-incomplete` ([Part of a panel](#part-of-a-panel)). No option leaves out one interview: `analyze.py --exclude-persona` and `--exclude-model` leave out every interview of a persona or a model key, from the tallies alone.

Notes, none of which blocks. Record them: the writer is given `checks.md`.

| Note | Read it as |
|---|---|
| "topic never opened: T3" | Coverage the round did not get for that participant. `quant.md` counts it too |
| "ended at its cap of 30 exchanges with no close" | The interviewer ran out of room. Lower the topic caps or raise `interview.turns` |
| "T2 had 9 exchanges, 1 past its cap of 8" | The interviewer went on after the notice |
| "question 7 holds the opener of T3 and was labelled T2: it is counted under T3" | The interviewer opened the next topic under the old label. The launcher went by the words, so nothing is wrong with the counts. Many of these point at a smaller interviewer model |
| "leak term "doc chase" in answer 4" or in its card | Background leaking in from the harness, as in a review. Read where it came from before trusting that interview |
| "speaks of being an AI, a model or a persona in answer 9 ("language model")" | The participant broke character. Read the answer, and treat what follows it with care |
| "more than 2 question marks in question 5" | The interviewer asked several things at once |
| "long answers: a median of 140 words, over 120" | The participant is writing, not talking: a model that ignores the brief |
| "1 reply of the interviewer sent back for repair" | Harmless once. Many point at the interviewer's model |
| "1 turn of the participant left no reply and was put again" | A stop, a kill or a failed turn that `resume` put again |
| "its turn log ends in a write that a killed launcher never finished, which is not read" | The next launcher settles that turn again |

A turn log under `logs/` is not checked: a fresh start or `--force` moved it there, and it is no interview of the study. The table says how many there are.

## Reading a transcript

Two files are written for each interview, and `interview.py <study> render` writes them again:

| File | Holds | For |
|---|---|---|
| `interviews/<run id>.md` | The recruitment facts, the situation card under a heading that says the interviewer never saw it, then each exchange with its topic, move and reason, the question and the answer | The user, the lead and the critic |
| `analysis/transcripts/<run id>.md` | The recruitment facts and the numbered questions and answers, and nothing else | The analysts, who code what was said and are kept from the interviewer's reasoning |

An exchange of the full transcript:

```text
### 2

- Topic: T1, the working week
- Move: anchor
- Why: They raised lender policy changes unprompted, but it is a general account; asking for the latest specific deal they rechecked.

**Q:** Tell me about the last deal you went back over because of that. What happened?

**A:** A first home buyer couple I had pre-approved with one of the lenders that tightened. ...
```

- **Topic** is the topic the question counts for. Where the interviewer wrote another label it reads "T3, tools and spending (the interviewer labelled it T2)": a question counts for the topic whose opener its words hold.
- **Lines in square brackets are the launcher's:** a reply that was sent back and why, a turn that left no reply, the end check, how the interview ended ("[Ended at the cap of 12 exchanges.]", "[Ended by the interviewer after 23 exchanges: ...]"), the interviewer's closing line that was not sent, and "[Not finished: ...]" for an interview that has not ended.

**Learning the method from it.** Read the card first, then each `Why` before its question: it says what the interviewer heard in the last answer (a generality, praise, a feature idea) and which move it chose. Then read the critic's file for the same interview, `analysis/critique-<n>.md`: its "Worth learning from" items, each flag with the better question beside it, and which card items the interview found. The card shows what a better question would have reached.

## The analysis

No scores. Four job roles and two scripts, in this order. A role is started with `launch.py <study> run --role <role>`, and each command's last line says what to read and what comes next.

| Step | Command | Reads | Writes |
|---|---|---|---|
| 1 | `check_runs.py <study>` | The turn logs | `analysis/checks.md` |
| 2 | `launch.py <study> run --role analyst` | The analysts' copies of the transcripts | `analysis/qual-<n>.md`: what each participant said, then evidence notes |
| 2 | `launch.py <study> run --role critic` | The full transcripts and the guide | `analysis/critique-<n>.md`: marks on the questions |
| 3 | `extract_notes.py <study>` | Both kinds of file, and the turn logs | `analysis/notes.csv`, `analysis/critique.csv` |
| 4 | `launch.py <study> run --role themes` | `notes.csv` alone | `analysis/themes.md`: the notes put into themes |
| 5 | `analyze.py <study>` | The two CSV files, `themes.md`, the turn logs | `analysis/quant.md`, `analysis/quant.json`: the tallies |
| 6 | `launch.py <study> run --role writer` | The files under `analysis/` and the guide | `analysis/SYNTHESIS.md`, then `analysis/quote-check.md` |
| 7 | `interview.py <study> quotes` | `SYNTHESIS.md` and the turn logs | `analysis/quote-check.md` |

- **Analysts and critics run in either order, one role to a command.** Both wait for the panel: "Analysts wait for the panel: 1 interview of 4 has not finished (P04-a pending). Finish them with launch.py run and resume, or pass --allow-incomplete to analyse what there is: the analysts are then told which interviews are unfinished."
- **A step taken out of turn refuses and names the step before it:** "The themes job waits for analysis/notes.csv, which is not there: extract_notes.py `<study>` writes it. Run that, then launch.py `<study>` run --role themes again." The writer waits the same way for every analyst, critic and themes job and for `analysis/quant.md`.
- **A role whose model entry is missing is refused** with the key to add. The themes job runs on `synthesis.analyst`.
- **Read each role's files before the next step.** The analysts and the critics are one step: neither reads the other's file, so both may run before either is read, and both are read before `extract_notes.py`. Check a surprising note against the transcript, and log what you find in `analysis/lead-notes.md`.

### Coding and the critique

An analyst writes, for each interview, a `## <run id>` section: 100 to 200 words on what the participant said, then one evidence note for each signal, in a fixed form. A last section, "Across models", says what every model's version of a persona said and what only one did.

```text
### Note P02-a/3
- Turns: 7-8
- Signal: PAIN
- Statement: Rings subcontractors for late timesheets most weeks
- Raised: unprompted
- Evidence: incident
- Effort: workaround
- Quote: "I rang him on the Thursday and I was still waiting on the Monday."
```

| Field | Values |
|---|---|
| `Signal` | `PAIN`, `GOAL`, `OBSTACLE`, `WORKAROUND`, `REQUEST`, `BUYING-CRITERION`, `MONEY`, `PERSON`, `CONTEXT`, `NON-PROBLEM` (the participant said plainly that this is not a problem for them) |
| `Raised` | `unprompted`: the participant's words first brought it up, before any question named its area. A later question that digs into what they raised does not make the detail it draws out prompted. `prompted`: a question named the area first |
| `Evidence` | `incident` (a specific past event), `general`, `opinion`, `future`, `request` |
| `Effort` | `none`, `workaround`, `searched`, `paid`, `unknown`: what they said they have done about it |

A critic writes, for each interview, a summary (a final check, the card items found and missed, the exchanges worth learning from) and one entry for each mark:

- **`Flag`** on a question, with a better question beside it: `pitch`, `hypothetical`, `leading`, `opinion`, `generic`, `price-guess`, `wishlist`, `zoom`, `talking`, `rescue`, `compound`. At most two a question.
- **`Missed`** signal on an answer, with a one-line note: `praise-taken`, `generality`, `feature-request`, `feeling`, `contradiction`, `payer`, `pushed-no-problem`.
- **`Good`** move, with a one-line note: `anchored`, `consequence`, `accepted`, `deflected`, `dug`, `priority`, `spend`.
- **An opener gets no flag and no good move:** it is the guide's question, not the interviewer's. A leading opener is yours to fix.

### `extract_notes.py`

It reads every note and entry against its form and guesses nothing. It prints what it read:

```text
36 notes in analysis/qual-1.md and analysis/qual-2.md: 36 read (P01-a 9, P01-b 8, P02-a 10, P02-b 9), 0 unparsed. 0 quotes of the 36 could not be verified.
29 critique entries in analysis/critique-1.md and analysis/critique-2.md: 9 flags, 8 missed signals, 12 good moves, 0 unparsed.
```

- **A note's topic comes from the turn log,** by the question of the first exchange it names: an analyst never sees a topic id.
- **A quote is verified** when its words stand in the answer of one exchange the note names, as words of their own. Quotation marks, white space, case and one closing full stop are not looked at. The exchange it was found in is recorded, and is what a quotation of it names.
- **Unparsed** is a note or entry that does not fit its form, holds a value outside its list, or names a run or an exchange the study does not have. It is counted in no tally, and listed with what is wrong: "qual-1.md line 104, Note P01-a/5: its Signal is "ANNOYANCE", which is none of ...".
- **Unverified** is a note whose quote is not in the answers it names. The note is still counted, and its quote is offered to nobody. Where another answer holds the words, the line says which: put its `Turns` right.
- **What to do about either:** read it against the transcript, put it right by hand in its qual or critique file, note the edit in `analysis/lead-notes.md`, and run `extract_notes.py` again. Or leave it out: `quant.md` counts how many were.
- **A file that says nothing of an interview** is named: "critique-1.md says nothing of P02-b: it was written before that interview ended, or the critic left it out. To redo it, delete the file and run launch.py `<study>` run --role critic."
- **With the files of one role alone** it writes the other CSV file with its header and no row, and says what to run. It exits with 1 only when neither role has written, or for a study of another type. Real analysts and critics left none unparsed and no quote unverified in two passes (78 notes, 70 entries).

### The themes job

Two analysts name the same problem two ways, so one job puts the notes into themes from `notes.csv` alone. It groups by what was said, never by topic. A note belongs to one theme at most and may belong to none. `analyze.py` lists a theme that names a note `notes.csv` does not have under "Problems in themes.md" and counts it in no table: put the file right by hand, or delete it and run the themes job again.

### `analyze.py` and `quant.md`

`analyze.py <study>` prints the key numbers and writes the tallies. `--segment`, `--exclude-model` and `--exclude-persona` work as in a review, by the interview.

**Every count is of simulated participants,** each one persona on one model entry and replicate. Every heading says so. Report "3 of 8 simulated participants", never a percentage, and never as frequency or prevalence: nothing here says how common anything is among real people.

**Three groups, which never overlap.** Under a theme, and under a topic, a participant with a note there is in exactly one of:

| Group | Has there | Supports |
|---|---|---|
| Raised it | A note that is not a `NON-PROBLEM` note, and no `NON-PROBLEM` note | "told of it" |
| Said it is not a problem | `NON-PROBLEM` notes alone | The most that supports saying it did not trouble them, and only once the notes are read |
| Both | A `NON-PROBLEM` note and at least one other note | Neither by itself. The other note may be a workaround, a person, money or context as well as a pain: its `Signal` says which |

- **Never add the groups into one total of people who "had" a theme.** A `NON-PROBLEM` note is about its own statement, which may be one part of a topic.
- **Unprompted, With an incident and Effort** are counted over the first and the third group. Lead with themes that have unprompted incidents and effort behind them, not the ones most mentioned.
- **Notes on a flagged question** rest on a question the critic flagged, so what they say may be the question's doing. "2 of 4, 1 with no critique" keeps an interview with no critique apart from one in which nothing was flagged.

The sections, in order:

| Section | Shows |
|---|---|
| Key numbers | Interviews finished, notes, themes, and everything left out of the counts: unparsed rows, unverified quotes, problems in `themes.md`, interviews no analyst's or critic's file covers |
| Themes | The three groups, unprompted, with an incident, effort and flagged notes for each theme, then each theme's definition and run ids |
| Themes by segment, by model key, by persona | The same within each. A variant sits under its parent |
| Model agreement | For each persona on more than one model key, where each model's interview stands on each theme. One that a persona told of on one model and not another is model taste |
| Replicate spread | Only with more than one finished replicate |
| Coverage by topic | How many interviews opened each topic, the notes coded under it, and the participants of the second and third groups |
| Notes that rest on a flagged question | Each such note, with the exchange and the flag |
| Critique | The marks by kind and value, and by interview with the critic that marked it |
| Notes in no theme, Problems in themes.md | What the themes job left out or got wrong |
| Verified quotes | Every verified quote by theme, in the form the synthesis must give it: `"..." (P02-a, 7)` |
| Incomplete interviews | Each with how far it got. Their notes are counted nowhere else |

- **Marks by different critics are not comparable.** The critics split the interviews by persona, and one marks more readily than another: in a real round one critic gave 11 flags to two interviews and the other 3. A difference in marks between interviews that different critics read is no finding about the interviews, the personas or the segments.
- **`quant.json`** keeps the run ids beside every count of participants, so a hand count can be set against it.

### The writer and the quote check

The writer's `SYNTHESIS.md` has ten sections: what this is and its limits, each learning goal, the problem themes, what was not a problem, how participants cope now, where segments and models differ, quotes, how the interviews went, a revised guide with the next three learning goals, and what remains unproven. It is given no transcript, and its brief asks for at most 2,500 words. Real writers ran over it, by up to a fifth.

**A quotation has one form:** the words between double quotation marks, then at once the run and the one exchange in brackets.

```text
"I was still waiting on the Monday." (P02-a, 7)
```

`interview.py <study> quotes` checks every quotation of `SYNTHESIS.md` against the exchange it names (its question or its answer), prints what it finds, writes `analysis/quote-check.md` and exits with 1 when anything is listed. The launcher runs the same check when the writer ends, so `run --role writer` exits with 1 on a synthesis that fails it. It lists:

- a quotation whose words are not in the exchange it names, with "Those words are in exchange 8." where another exchange of that interview holds them
- any other stretch between double quotation marks, of any length, as a quotation with no attribution
- words in single quotation marks or guillemets that an attribution follows, or that read as speech (six words or more, or a sentence)
- a bracket `(run id, number)` that follows no quotation: after a paraphrase, in a code span or a fenced block
- a line whose double quotation marks do not pair
- a synthesis in which no quotation was verified at all

When it passes it says: "analysis/SYNTHESIS.md has 17 stretches between double quotation marks. Each is a quotation with its run and exchange, and its words are in the exchange it names. No attribution stands anywhere else."

- **A synthesis is not handed over before `quotes` exits 0.** Nothing is sent back to the writer. Put each listed line right by hand in `SYNTHESIS.md` (a term in double marks goes in italics, a wrong exchange number is corrected, an unverifiable quotation becomes a paraphrase), log the edit in `analysis/lead-notes.md`, and run `quotes` again. Or delete `SYNTHESIS.md` and run the writer again.
- **What the check cannot see.** It holds words to an exchange, never to a speaker: a question's words credited to the participant pass. A short term in single quotation marks passes. One word that is in the exchange passes. Text in a code span or a fenced block is not read. Read the quotes section yourself.

### Doing a job again

A job that is done stays done. To have one done again, delete its output file and run its role again:

```text
rm <study>/analysis/qual-1.md
launch.py <study> run --role analyst
```

- **It spends from the same share of the pool** as its earlier attempts. The plan shows "$0.8333 cap, $0.5913 used, $0.2421 left" against the job, and warns when what is left is less than a finished attempt of it used. A job that stops at its budget reads `limited`: `launch.py <study> resume --role writer --runs writer --extend` gives it one more allowance. One whose process reached its budget after its file was written is `done`, with a note: "writer: done (its process reached its budget after writing analysis/SYNTHESIS.md: check that the file is whole)". Read the file to its last section.
- **A command that finds every job done starts nothing and says so:** "analyst-1 and analyst-2 were done already, and nothing was started. To have one done again, delete its file (analysis/qual-1.md or analysis/qual-2.md) and run launch.py `<study>` run --role analyst again."
- **Every step after a job that was done again is then out of date,** and says so when it is run. After an analyst is done again: `extract_notes.py`, delete `analysis/themes.md` and run the themes job, `analyze.py`, delete `analysis/SYNTHESIS.md` and run the writer, then `quotes`.

**"done, but ..."** is a done job that is out of date. Its own role's command prints the sentence in place of what comes next and exits with 1, the plan shows it against the job's row, and the job stays done: the lead decides. Three reasons:

| Reason | The sentence | The plan's State cell | What is refused until it is put right |
|---|---|---|---|
| An analyst's or a critic's interviews were held, went on or ended after its brief was written | "critic-2: done, but analysis/critique-2.md was written before P02-b was held, so it does not cover that interview as it stands now: to put that right, delete analysis/critique-2.md and run launch.py `<study>` run --role critic again." | `done, 1 interview since` | Nothing. `extract_notes.py` names the interview its file says nothing of, and `quant.md` counts it |
| A job that the themes job or the writer reads was run again after its own last launch | "themes: done, but analysis/themes.md was written before analyst-1 was run again, so it is not built on what that job has written since: ..." | `done, 1 job run again since` | A role that reads it ("The writer waits, because a job it reads is out of date. ..."), and `analyze.py` for the themes job |
| A file the themes job or the writer was given has changed or gone with no job run again: a note put right by hand and extracted again, tallies written again, a critic's file edited | "themes: done, but analysis/themes.md was written before analysis/notes.csv changed, so it is built on what that file held then: ..." | `done, 1 file changed since` | The same |

The two scripts leave no record of when they ran, so each is asked what it would write now:

- "The themes job waits, because analysis/notes.csv is not what analysis/qual-1.md and analysis/qual-2.md now give: run extract_notes.py `<study>` again, then launch.py `<study>` run --role themes again." `analyze.py` refuses for the same reason and writes nothing.
- "The writer waits, because analysis/quant.md is no longer the tallies of the analysis as it stands: run analyze.py `<study>` again, which writes them or says what it needs first, then launch.py `<study>` run --role writer again."

Not seen: a file that was absent when a job was launched and appears later (a `checks.md` written after the writer), and any job whose file was put in place by hand with no launch on record.

## Part of a panel

Analysts and critics wait only while an interview is `pending`, `running` or `blocked`. A `partial`, `limited` or `failed` interview does not hold them back. With `--allow-incomplete` they start whatever the panel's state, to critique a pilot before the rest is held or to analyse what a round got:

```text
launch.py <study> run --role critic --allow-incomplete
```

- **A job with no interview to read is passed over** while the others run: "critic-2: passed over, as it would have nothing to read: no interview of persona P02 has a turn on record. Start it once one is held: launch.py `<study>` run --role critic". Without the option, and when no job of the role has anything to read, the command is refused.
- **A job that was passed over stays pending,** so the themes job and the writer wait for it. After a pilot with two analysts the analysis goes as far as `extract_notes.py`, which is enough to read the notes and the critique of the pilot.
- **An analyst is told which of its interviews are unfinished.** A critic reads where one stopped from its transcript, which ends "[Not finished: ...]".
- **Once the rest of the panel is held,** a job that ran on part of it is out of date for the first reason above: delete its file and run the role again.
- **An unfinished interview is in no headline table.** `quant.md` lists it under "Incomplete interviews", and the writer reports from it only with a note that it was cut short.

## Reporting to the user

`references/communicating.md`, Reporting an interview round, has what to lead with and what never to claim. In short:

- **The synthetic panel notice first.** The scripts put it in the transcripts, `quant.md`, `checks.md` and `quote-check.md`, and the jobs in their files.
- **The weaknesses below, in plain words,** before any finding.
- **Findings as hypotheses,** each with the kind of evidence behind it: unprompted or prompted, an incident or a generality, effort or none, and whether it rests on a flagged question or on one model alone.
- **What was not a problem** gets as much room as what was.
- **What the round cannot prove:** four conclusions stay apart (a problem exists, this segment puts it first, a solution delivers, a buyer pays). The round offers guesses about the first two and nothing on the last two.
- **The revised guide and the next three learning goals,** for interviews with real people. Read the writer's proposed questions against the method before passing them on.
- **What was used** (`analysis/usage.md`), and that `quotes` exits 0.

Archive when the user wants it kept (`references/archive.md`, Interview studies), after `quotes` exits 0.

## How much to trust the result

- **The history is invented.** The method's core move is asking about real past behaviour, and a persona has none. It invents one, and each deeper question invents more. The card fixes the outline early, and nothing makes it true. In testing, answers agreed with the card and late answers with early ones, which makes a transcript consistent, not real.
- **Participants are agreeable, by model.** A model is more articulate, more cooperative and more self-aware than a busy person. The participant brief pushes against that and does not remove it. Asked whether it would pay for a described app, one vendor's model agreed three times of three, and another agreed with a caveat twice and declined once. Comparing models shows what is model taste. Nothing shows what real people would say.
- **A count is of simulated participants.** It says nothing of how often a problem happens or what it costs.
- **An interviewer and a participant on the same model** agree with each other more readily. The plan says when they match, and the summary says which interviews they were.
- **The critique is a model's opinion of a model's questions.** It teaches the method and certifies no interview. Of 41 entries judged by hand in a real round, 32 were fair, 7 arguable and 2 wrong, and two critics marked at different rates.
- **The coding is a model's reading.** Checked field by field in a real round, analysts on a mid-tier model had 79 of 85 coded fields right, with every quote word for word. `Evidence` and `Effort` are where they slipped, and `Raised` was right on 33 of 36 notes. Nothing invented was found.
- **A mid-tier interviewer drifts from the method in small ways:** it joined two questions with "and", went into detail before a topic was known to matter, and left generalities unanchored when a cap left no room. The critique marks these, and a tally says which notes rest on a flagged question.
- **A small model may not hold the participant's role.** The launcher fails such an interview at its first reply. Nothing checks a tier, so a small model that does write its card runs. In one test a smallest-tier participant stayed in character and told no incident with a when and a cost.
- **Cost grows with length, by less than feared.** Each turn re-reads the whole conversation, but a resumed turn read 93 to 98 per cent of its input from a cache, and the cost of a turn stayed flat across an interview where it is reported. One harness missed its cache in 9 per cent of resumed turns. A wait longer than a cache's lifetime (an hour on the harness that states one) was not tested: such a turn pays for its whole history once.
- **On `codex` a side's tools are switched off one by one.** Neither side can read a file. What stays open: a patch tool that can write in the session's own empty folder, sub-agent tools, and whatever a later CLI version adds that no switch here names.
- **The leak gate knows only the listed terms.** A leading question that uses none gets past it. That is what the interviewer brief and the critique are for.
- **Not measured:** an interview at a higher effort setting, a study that runs for hours against a usage window, and what a harness loses when it compacts a long conversation (none did at 40 exchanges).

**What a pilot should confirm before the full round:**

1. Every participant wrote its card, and no interview `failed` at its first reply.
2. Answers are two to five spoken sentences, start general and give an instance when asked.
3. Something the card lists as no problem was said to be no problem.
4. The interviewer opened every topic with its opener, one question at a time, and closed.
5. `check_runs.py` shows no blocking problem for the pilot's interviews, and their notes are few. It checks the whole study and takes no `--runs`, so after a pilot it exits with 1: every interview not held yet is listed as "no end record: it reads pending, with no turn on record", with the advice to start them with `launch.py <study> run`. That is expected. Read the pilot's rows, and run `plan` before `run`.
6. How long an interview took against its limits. The next plan estimates from it.

## Debriefs

A debrief is an interview held with a finished run of a review or usability study, in the session that run worked in, about what it did, saw and expected there. It belongs to those two study types: an interview study has none, since its interviews are its runs, and `debrief` in its `study.json` is refused. `references/debriefs.md` covers it: the `debrief` block, the cost, the command, who is refused, what it writes and how much to trust it.

## Troubleshooting

| What you see | What it means | What to do |
|---|---|---|
| "pi is not verified for interviews, and an interview is carried turn by turn through its runner. Put the model entry on a runner that is (claude, codex)" under "Problems" in the plan | A participant or the interviewer is on a runner that cannot carry an interview | Change that model entry's runner |
| "topic T2: its opener holds the leak term "doc chase". The interviewer would say it. Reword it. Nothing was written." from `init_study.py` | The guide itself names what must not be named | Reword the opener, the area, the goal or `about` |
| `init_study.py`: "runs.json already exists. Re-run with --force to replace it and the run state it records." | The study is scaffolded | `--force` only when every interview should start again |
| "P01-a: a reply of the interviewer could not be used (topic)" | One reply was sent back for repair. The interview goes on | Nothing, unless every interview has one: then the interviewer's model is too small, or a leak term is a common word |
| "P01-a: failed after 0 exchanges: the participant did not write its situation card: this model may be too small to hold the role. Use a larger one" | The first-reply check | `run` once more, then a larger model for that entry and `init_study.py --force` |
| "P01-a: partial, so run leaves it alone. Next: resume." after `run --runs P01-a`, or "partial: P01-a. Next: resume." in the summary | `run` starts only `pending` and `failed` interviews | `launch.py <study> resume` |
| "limited: P01-a. Next: resume --runs `<ids>` --extend, which gives one more allowance of the limits." in the summary | A side used its time or budget, and `resume` alone leaves the interview where it is | Read the transcript and ask the user, then `resume --runs P01-a --extend` |
| "its turn log is of the wrong form (...), so resume leaves it alone." | The turn log was changed by hand or damaged | Put the file right, or move it into `logs/` and `launch.py <study> run --runs <run id>` |
| `check_runs.py` shows "no end record: it reads pending, with no turn on record" | The interview was never held. After a pilot, that is every interview the pilot left | `launch.py <study> run`, after the plan |
| "No interview called interviewer-P01-a. There are: ..." | An interviewer is not named in any command | Name the interview by its participant's run id |
| "Critics wait for the panel: ..." | An interview is pending, running or blocked | Finish the panel, or `--allow-incomplete` |
| "done, but ... was written before ..." and exit code 1 | A done job is out of date | Delete its file and run its role again ([Doing a job again](#doing-a-job-again)) |
| `run --role writer` ends with a quote check that lists lines, exit code 1 | The writer is done, and a quotation could not be verified | Put the lines right in `SYNTHESIS.md`, then `interview.py <study> quotes` until it exits 0 |
| "CANNOT BE USED" in place of "ready" in the plan | The lead's shell is sandboxed | `references/runners.md`, When the lead's own sandbox blocks the launcher |
