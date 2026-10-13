# Persona panel: interview studies

**Status:** Draft, 13 October 2026. Nothing here is built or tested. Codex
reviewed it over two rounds on 13 October 2026 and approved it with notes,
which are applied. The [open questions](#open-questions-for-the-user) are
the user's to settle.

PRD for a third study type in the `persona-panel` skill
(`packages/common/agents/.agents/skills/persona-panel/`): simulated discovery
interviews, run the way [The Mom Test](https://www.momtestbook.com/) teaches.

1. **An interviewer agent** talks to each persona in turn: it asks, reads the
   answer and drills down, within a discussion guide the user approved.
2. **The launcher carries every turn** between the two sessions and writes the
   transcript, so neither side needs to write a file.
3. **The analysis codes each transcript** into problems, tallies them across
   participants and segments, and critiques the interviewer's questions.
4. **Two later additions** reuse the same turn loop: a debrief interview in
   the session of a finished review or usability run, and a practice mode
   where the user asks the questions.

It follows [persona-panel-expansion.md](persona-panel-expansion.md), which
built the runners, the launcher, follow-up questions and usability studies.
That PRD lists moderated interviews as a non-goal. This one reverses that.

## Checked against the code

The design discussion read only `SKILL.md`, `scripts/followup.py` and
`scripts/init_study.py`. Its claims were checked on 13 October 2026 against
the working tree of `persona-panel-expansion` at `21ff323`, which had
uncommitted changes from other work in progress. Recheck anything below that
names a function before building.

Confirmed:

- The `description` in `SKILL.md` is 1,022 of 1,024 characters.
- `followup.py` resumes a finished run's own session with one question, as
  one more attempt on the run (kind `followup`), under the study lock, a
  watchdog and `limits.followup`.
- Usability was added as a type with its own reference file, assets and a
  branch in the scaffold (`scaffold_usability`).
- `synthesis.analyst` and `synthesis.writer` are model entries with no
  default, and the study brief is refused under `panel/` and in
  `synthesis.context_files`.

Corrected:

- **The follow-up is not the turn primitive as it stands.** It asks only a
  `done` run, and settles each answer by comparing the persona file with a
  copy made before the question. An interview reuses what sits under it: the
  supervisor in `launch.py`, the lock, the watchdog, the runners' resume
  commands and the usage record.
- **"A participant needs no file access" is not available today.** Both
  runners pass file tools on every launch (`FILE_TOOLS` in
  `runners/claude.py`, `-s workspace-write` in `runners/codex.py`), and the
  Codex sandbox leaves the whole disk readable. `claude --help` lists
  `--tools ""` to disable every tool, which no run has tried. Codex has no
  switch for its shell tool. So this PRD isolates by folder first and treats
  a session without tools as a [discovery](#discovery) result.
- **Every resume is a new CLI process.** It repeats every launch flag, pays
  the CLI's start-up time, and on Claude Code gets a budget cap that counts
  that process alone. An interview of 30 exchanges is about 60 processes.
- **Two study types are assumed in places.** `STUDY_TYPES` has two entries
  and `check_type_keys` reads "not usability" as "review".
- **A job is one output file, and the synthesis pool is split `analysts + 1`
  ways** (`synthesis_share`). The new job roles change that arithmetic.
- **Analysts and the writer work in the study directory**
  (`panel_lib.workdir`). Keeping a file from them is an instruction, as it is
  for `study-brief.md` today.
- **`archive.py` keeps `prompts/`.** A prompt that held real background
  material would be archived with it.
- **Native mode cannot run an interview.** The turn loop is the launcher's.

## Problem

The skill answers "which concept do prospects prefer" and "can they complete
this task". It cannot answer the question that comes before both: what
problems do these people have, and which of them matter.

The example behind this PRD: what mortgage brokers struggle with day to day,
what their main challenges are, and what challenges they have with the
user's own tool.

A follow-up question is the nearest thing today. It puts one fixed question
to a panellist who has already reviewed something. It cannot open a topic,
react to an answer or dig past the first shallow one.

The user also wants to learn the technique: to read the questions, the answers
and how the interviewer drilled down, and to rehearse before real interviews.

## Goals

- The lead helps the user draft the learning goals and a discussion guide,
  and the user approves the guide and the roster before anything runs.
- Each participant is a persona on a chosen model entry, as today. The
  interviewer's model is set once for the study.
- The interviewer follows The Mom Test: past behaviour and specifics, no
  pitch, no hypotheticals, compliments deflected, each problem followed to
  its consequence, its workaround and what was tried.
- Every interview leaves a transcript that shows each question, the move the
  interviewer meant to make and why, and the answer.
- An interview survives a kill, a usage limit and a rate limit, and resumes
  at the turn it reached.
- The analysis reports problems by how they were raised and how well they are
  evidenced, with no scores.
- A critique marks leading, hypothetical and pitching questions, missed
  signals and good moves, so the user can learn from it.
- Existing studies and archives keep loading, and the review and usability
  workflows do not change.

## Non-goals

- **Evidence about real customers.** A persona answers from a model's
  training data. The output is hypotheses and a rehearsed guide.
- **Commitment and advancement.** The book's test of a solution is what
  someone gives up for it. A simulated yes to a pilot proves nothing, so the
  interviewer never asks for one.
- **Recruiting.** Finding conversations, invitations and warm introductions
  have no place in a simulation.
- **Interviews in native mode.**
- **New work on the Pi, OMP or OpenCode runners.** See
  [Runners](#runners).
- **An interviewer that learns from one interview to the next** inside a
  round. See [Design decisions](#design-decisions).
- **Scores, leaderboards, capture, concept labels and review orders.**
- **Group interviews**, and more than one interviewer in a conversation.

## Terms

| Term | Meaning |
| --- | --- |
| Interview | One participant's conversation with the interviewer: one run |
| Participant | The panellist of an interview study: a persona on a model entry. Its `runs.json` role stays `panellist` |
| Interviewer | A headless session that asks the questions. One per interview, on the study's `interview.interviewer` model entry |
| Guide | The learning goals, topics, opening questions and turn caps in `study.json` |
| Exchange | One question and its answer. Turn caps count exchanges |
| Turn log | `interviews/<run id>.jsonl`, written by the launcher: the source of truth for an interview |
| Situation card | What a participant privately decides about its own working life before the first question |
| Room | A participant's own folder, `panel/rooms/<run id>/` |
| Debrief | An interview held in the session of a finished review or usability run |

## Design decisions

The seven the design discussion asked this PRD to settle. Each is built into
the draft and repeated under [Open questions](#open-questions-for-the-user) where
the user should confirm it.

**1. Same skill, a third type.** `"type": "interview"`, built as usability
was. Personas, rosters, model entries, the launcher, limits, the plan, the
usage record, the study brief, the synthesis jobs, the archive and the notice
all carry over. A derived skill would import this skill's scripts by path and
drift from them. The `description` is rewritten for three types:
[Changes to the skill's documents](#changes-to-the-skills-documents).

**2. A separate interviewer session for each interview, never the lead.** The
lead would carry one participant's answers into the next participant's
questions, and its context would fill with transcripts.

**3. Interviewers do not learn across interviews in a round.** A real
interviewer does, and the book says to update the learning goals as answers
come in. Here it would cost three things: interviews could no longer run side
by side, a difference between two models could be the interviewer's doing,
and the first participant's wording would lead the second. Learning happens
between rounds instead. The debrief ends with a revised guide, and the next
round is a new study directory, as the book's batch procedure has it.

**4. Practice mode is in scope, as the last milestone.** The turn loop does
not care who writes the question. It costs a terminal front end, runs marked
as practice and kept out of the tallies, and a critique of one run.

**5. Interviews about the user's own tool happen only in a debrief.** A persona
has never used the tool, so a question about its history with it gets pure
invention. A finished review or usability run has seen it, and what happened
in that session is the only real past a persona has. A standalone interview
is discovery, and its interviewer never names the tool. A debrief is product
feedback. The two are never mixed, because the book treats feedback given
after a demo as a different kind of evidence.

**6. Background material reaches participants only, in their prompts.** It
lives in `<study>/background/`, never under `panel/`. The interviewer never
sees it: it would ask about what it knew was there. Analysts are not given
it, by instruction only.

**7. Hypotheses stay with the lead.** The interviewer gets learning goals
written as things to find out, never the study brief, the idea or the tool's
name. A deterministic gate checks each question before it is delivered, and
the critique marks leading questions afterwards.
[Isolation and safety](#isolation-and-safety) has the layers.

Completeness is under [When an interview is done](#when-an-interview-is-done).

## How the parts divide the work

```mermaid
flowchart TD
    study["study.json<br/>guide, personas, models"]
    scaffold["init_study.py<br/>prompts, runs.json, rooms"]
    launcher["launch.py<br/>plan, pilot, run"]
    records[("interviews/<br/>turn logs and transcripts")]

    subgraph interview ["One interview, carried turn by turn"]
        direction LR
        interviewer(["Interviewer session"])
        participant(["Participant session"])
        interviewer -->|question| participant
        participant -->|answer| interviewer
    end

    subgraph analysis ["Analysis"]
        direction LR
        check["check_runs.py"] --> coding["analyst and<br/>critic jobs"]
        coding --> notes["extract_notes.py"]
        notes --> themes["themes job"]
        themes --> tally["analyze.py"]
        tally --> writer["writer job"]
    end

    study --> scaffold
    scaffold --> launcher
    launcher -->|starts and resumes both sessions| interview
    interview -->|every turn recorded| records
    records --> analysis
```

The turn log is the source of truth for whether an interview is done, where a
persona file is for a review. A new module, `scripts/interview.py`, holds the
turn loop's rules (parsing a reply, choosing the next turn, rendering) and
the supervisor calls it, as it calls `accounts.py` for a usability run.

## `study.json` changes

All new keys are optional for the other two types, which load unchanged.

```json
{
  "type": "interview",
  "runner": "claude",
  "models": [
    {"key": "sonnet", "runner": "claude", "model": "sonnet"},
    {"key": "codex", "runner": "codex"}
  ],
  "personas": [
    {
      "id": "P01",
      "name": "Dana Whitlock",
      "role": "Mortgage broker, sole operator",
      "segment": "solo",
      "personality": "Blunt, short of time, suspicious of new software",
      "bio": ["Eleven years broking, the last four on her own.", "..."]
    },
    {
      "id": "P02",
      "name": "Marcus Oyelaran",
      "role": "Principal of a six-broker firm",
      "segment": "principal",
      "personality": "Measured, delegates the detail, watches cost",
      "bio": ["Runs the firm and signs off every subscription.", "..."]
    }
  ],
  "interview": {
    "about": "how mortgage brokers run a loan from first enquiry to settlement",
    "interviewer": {"key": "interviewer", "runner": "claude", "model": "opus"},
    "goals": [
      {"id": "G1", "learn": "What takes most of a broker's time and attention in a normal week, and what they have done about it"},
      {"id": "G2", "learn": "How documents are collected from clients, and what happens when that goes wrong"},
      {"id": "G3", "learn": "Who decides what software the business pays for, and what was last bought or dropped"}
    ],
    "topics": [
      {"id": "T1", "area": "the working week", "goals": ["G1"], "turns": 6,
       "opener": "What has taken most of your attention at work over the last couple of weeks?"},
      {"id": "T2", "area": "collecting documents from clients", "goals": ["G2"], "turns": 8,
       "opener": "Walk me through the last loan where you had to collect documents from a client."},
      {"id": "T3", "area": "tools and spending", "goals": ["G3"], "turns": 6, "segments": ["solo", "principal"],
       "opener": "What was the last piece of software the business started or stopped paying for?"}
    ],
    "turns": 30,
    "situation_card": true,
    "background": {
      "all": ["background/forum-threads.md"],
      "personas": {"P01": ["background/calls-with-solo-brokers.md"]}
    }
  },
  "limits": {
    "run": {"minutes": 20, "budget_usd": 2.0},
    "interviewer": {"minutes": 30, "budget_usd": 3.0},
    "turn": {"minutes": 3},
    "synthesis": {"minutes": 30, "budget_usd": 10.0}
  },
  "synthesis": {
    "analysts": 2,
    "analyst": {"runner": "claude", "model": "opus"},
    "critic": {"runner": "codex"},
    "writer": {"runner": "claude", "model": "opus"}
  },
  "leak_terms": ["LoanLoop", "doc chase"]
}
```

Rules:

- **`models`** work as they do today, and mixing harnesses is the point:
  every persona is interviewed once on each entry, here on Claude Code's
  Sonnet and on Codex's default model, so an answer that only one model
  gives shows up as model taste. The study-level `runner` is the default for
  an entry that names none.
- **`interview.about`** is the honest, neutral purpose the interviewer may
  state when a participant asks what this is for. It names an area of work,
  never an idea.
- **`interview.interviewer`** is a model entry, as `synthesis.analyst` is.
  There is no default. One interviewer for the whole study, so that what
  differs between two runs is the participant.
- **`goals[].learn`** is written as something to find out, never something to
  prove. `init_study.py` refuses a goal, an opener or `about` that holds a
  `leak_terms` entry. The book's advice is three goals for each type of
  person, one of them uncomfortable. More than five draws a warning.
- **`topics[]`** are opened in the order written. `area` is a neutral name
  the interviewer may use to raise the topic when it has not come up.
  `opener` is the first question, sent as written. `goals` lists what the
  topic serves. `turns` is its cap in exchanges. `segments` limits a topic to
  personas in those segments, so that a buyer is asked about buying and a
  user is not.
- **`interview.turns`** caps the whole interview in exchanges. It must be at
  least the number of topics plus two, for the opening and the close.
- **`situation_card`** defaults to true: [Situation card](#situation-card).
- **`background`** names text or Markdown files inside
  `<study>/background/`, for every participant or by persona id. A path
  outside that folder is refused, and so is one over 20,000 words, since a
  participant's every turn re-reads it.
- **`limits.interviewer`** is each interviewer's allowance over a whole
  interview. `limits.run` stays the participant's. `limits.turn.minutes`
  bounds any single turn of either side. The defaults come from the
  [discovery](#discovery) measurements.
- **`synthesis.critic`** is the model entry of the critique jobs. The plan
  says so when it is the interviewer's own model.
- **Keys of the other types are refused**, as now: `concepts`, `tasks`,
  `target`, `accounts`, `find_the_answer`, `materials`, `browse`, `capture`,
  `factors` and `fit_factors` among them. `replicates`, variants, the roster
  grid, `segments`, `context_notes`, `leak_terms` and `runners` work as they
  do today. `context_notes` go to participants, as facts about the setting.
- **Run ids and model keys** keep their rules. The interviewer of run
  `P01-sonnet` is the job entry `interviewer-P01-sonnet`.

## Protocol

### The turn loop

For each interview the launcher:

1. **Starts the participant** in its room with its prompt: the participant
   brief, the persona, any `context_notes` and any background. With
   `situation_card` on, the prompt asks for the card as its only reply.
   Otherwise it asks for the single word "Ready".
2. **Starts the interviewer** in its folder with its prompt: the interviewer
   brief, the guide, and what a recruiter would know of the participant
   (name, role, segment). The reply is the opening and the first question.
3. **Alternates.** It resumes the participant with the interviewer's words,
   records the answer, resumes the interviewer with that answer and a status
   line, records the next question, and so on.
4. **Ends** when the interviewer ends the interview or the cap is reached,
   and renders the transcript.

One process is alive for an interview at any moment. Interviews run side by
side within each runner's concurrency, which counts processes as it does now.

### What the interviewer replies

Every interviewer reply has this form, and the launcher parses it:

```text
TOPIC: T2
MOVE: anchor
WHY: "We always chase documents" is a general claim, so I am asking for the latest instance.
SAY:
Which loan did that last happen on?
```

- **`SAY`** is everything after its line, and is the only part the
  participant receives, word for word.
- **`TOPIC`** is a topic id, or `open` or `close`. The launcher counts
  exchanges by it.
- **`MOVE`** is one of a fixed list, so a transcript names the technique at
  each turn: `open`, `priority`, `raise`, `anchor`, `sequence`,
  `consequence`, `coping`, `alternatives`, `frequency`, `constraint`,
  `money`, `deflect`, `dig`, `clarify`, `accept`, `close`. The list follows
  the field guide's event reconstruction and recovery table:
  [The Mom Test in the briefs](#the-mom-test-in-the-briefs).
- **`WHY`** is one sentence for the user and the critic. The participant never
  sees it.
- **To end**, the first line is `END: <reason>` in place of `TOPIC` and
  `MOVE`, and `SAY` holds a closing line, which is recorded and not sent.

A reply that does not parse gets one repair message naming what is missing.
A second failure stops the interview as `partial`, with the reply kept in
`logs/`.

### What each message carries

- **To the participant:** the `SAY` text and nothing else. No frame, no turn
  count, no topic. The brief it was launched with is its only instruction.
- **To the interviewer:** the answer between two lines of dashes, as the
  follow-up frame does, then one status line:
  `Exchange 9 of 30. T2: 4 of 8. Not opened: T3.`
- **Cap notices** ride on the status line. When a topic has used its turns:
  "T2 has used its turns: move on or close." When one exchange is left:
  "This is your last question: close the interview."

The frames are assets, sent verbatim with their placeholders filled.

### When an interview is done

An interview is `done` when its turn log has an end record. There are two
ways to get one:

- **The interviewer ended it.** If topics are still unopened and exchanges
  remain, the launcher asks once: "T3 was not opened. Open it, or confirm the
  end with your reason." A confirmed end stands, since a participant who says
  a topic does not matter is a finding. The unopened topics are on record.
- **The interview cap was reached.** The launcher writes the end record once
  the last permitted exchange has its answer. That exchange is meant to be
  the close. A question offered for it with any other `TOPIC` is sent back
  once, as a repair is, with "This is the last exchange: reply with TOPIC:
  close." If the second reply is no close either, the launcher ends the
  interview there, one exchange short and with no close, and
  `check_runs.py` notes it. Topics never opened are on record.

Unopened topics never block. They appear in `check_runs.py`, in the tallies
and in the synthesis as coverage the round did not get.

### States

The states of `launch.py` keep their meaning. Both entries of an interview
read their state from the turn log, so they never disagree.

| State | For an interview | Next |
| --- | --- | --- |
| `pending` | No turn recorded | `run` |
| `running` | A turn's process is alive, or a launcher is between two turns | wait |
| `done` | The turn log has an end record | none |
| `partial` | Stopped between or during turns: `stop`, a killed launcher, a reply that failed twice | `resume` |
| `limited` | Either side has used its time or budget | `resume --extend` |
| `blocked` | Either side's harness is turning requests away | `resume` later |
| `failed` | A side's first process ended with no reply | `run` |

### Resume

- **Every turn is recorded before the next starts**, in this order: the turn
  is appended to the turn log, then the attempt's end is saved in
  `runs.json`. Each turn record carries its entry and attempt number, so a
  launcher that died between the two records nothing twice.
- **A launcher that takes over a study** settles what a dead one left, as it
  does now: a process that finished while no launcher was alive has its reply
  in `logs/`, and that reply becomes its turn.
- **`resume` continues at the turn the log reached**, in both original
  sessions. Nothing is asked again that has an answer on record.
- **A turn whose reply was never captured** is put again, with one line
  saying the earlier reply was lost. The session may then hold an answer the
  transcript does not. That is accepted.
- **A lost, purged or unsaved session** of either side ends resume for that
  interview. With no participant answer on record it starts afresh. With
  some, it is reported for the lead to decide, as a partial review is.
- **`init_study.py --force`** resets every interview and moves the turn logs
  and transcripts it replaces to `logs/`.

### Limits and the plan

| Limit | Covers | Enforced by |
| --- | --- | --- |
| `interview.turns` | Exchanges in the interview | The launcher, exactly: it carries every turn |
| `topics[].turns` | Exchanges in a topic | The interviewer, on the launcher's notice. Advisory |
| `limits.run` | The participant, over the whole interview | Time by the launcher, budget by the harness where it has a cap |
| `limits.interviewer` | The interviewer, over the whole interview | The same |
| `limits.turn.minutes` | One turn of either side | The watchdog of that turn's process |

The launcher cannot make an interviewer change subject, so an exchange past
a topic's cap is delivered, counted, noted by `check_runs.py` and bounded by
the interview's cap.

`launch.py plan` prints for an interview study:

- every interview: its participant's model entry, the interviewer's, the
  caps and all three limits
- what each provider receives. The participant's provider gets the persona
  and the background. The interviewer's provider gets the guide and every
  answer, which can repeat background material in the participant's words
- the estimate, from measured tokens per exchange when a pilot has run
- the ceiling: both sides' caps for each interview, plus the synthesis pool,
  labelled a guaranteed maximum or an estimate by today's rule

`pilot` runs one whole interview on each model entry. Read its transcript
before the rest: whether the persona holds, how long the answers are, and
whether the interviewer keeps to the method.

### Runners

An interview needs nothing new from a runner: a launch, a resume with a
message, a final reply and usage. The interface in `runners/__init__.py`
does not change in the first three milestones.

- **Claude Code and Codex** are the runners this PRD verifies.
- **Pi** stays as built. A Pi model entry is allowed if the unchanged runner
  passes the pilot. No work is done to make it pass.
- **A runner that cannot resume** is refused at the plan step.
- **Both runners keep their harness's default system prompt.** Whether a
  conversation needs otherwise is a [discovery](#discovery) question. If it
  does, the user decides.

## Isolation and safety

The skill's trust boundary stands: a panellist can write only under `panel/`, and
everything else in the study is the lead's and trusted.

### What each side sees

| | Participant | Interviewer | Analyst | Critic | Writer |
| --- | --- | --- | --- | --- | --- |
| Persona: name, role, segment | yes | yes | yes | yes | no |
| Persona: bio and personality | yes | no | yes | yes | no |
| Background material | yes | no | no | no | no |
| Its situation card | yes | no | no | yes | no |
| Learning goals and the guide | no | yes | no | yes | yes |
| The interviewer's `SAY` | yes | yes | yes | yes | no |
| `TOPIC`, `MOVE` and `WHY` | no | yes | no | yes | no |
| The study brief and hypotheses | no | no | no | no | no |
| Other interviews | no | no | its half | its half | through the analysis |

An analyst codes what was said, so it is kept from the interviewer's
reasoning, which would colour the coding. The writer reads the analysis
files, not the transcripts, as it does today.

### Folders

- **A participant's process starts in its room,** `panel/rooms/<run id>/`,
  which holds nothing. It needs no file and writes none. Nothing reads what
  it leaves there.
- **An interviewer's process starts in `interviewer/<run id>/`,** which holds
  the Mom Test reference files and nothing else. A folder for each interview
  stops one interviewer leaving notes for another.
- **The launcher writes `interviews/`,** outside `panel/`. No session of
  either side is told it exists.
- **`background/` is lead only.** The scaffold copies its text into the
  participant's prompt, between two marker lines. `archive.py` cuts that
  block from the archived prompt and never copies `background/`.

### What enforces it

| Harness | A participant or interviewer can |
| --- | --- |
| Claude Code | Read and write only its own folder (`--restricted`) |
| Codex | Write its own folder and `/tmp`, and read the whole disk. Only its instructions keep it out of the rest of the study |
| Pi | Read and write only its own folder (the guard) |

On Codex the guide, the background and the other transcripts are a file read
away from either side. That gap exists for every Codex panellist today and is
printed by the plan. A session with no tools would close it on Claude Code:
[Discovery](#discovery).

### Keeping hypotheses from the participant

Four layers, the first two deterministic:

1. **The interviewer is never given them.** Its prompt holds the guide and
   nothing from `study-brief.md`. `init_study.py` refuses a copy of the brief
   in `interviewer/`, as it does under `panel/`.
2. **A gate on every question.** Before a `SAY` is delivered the launcher
   looks for each `leak_terms` entry in it. A hit is not delivered: the
   interviewer is told which term to drop and asks again, once. A second hit
   stops the interview as `partial`. The tool's name and the team's own words
   for its idea belong in `leak_terms`.
3. **The interviewer brief.** Never state an idea, a product or a hoped-for
   answer. Never suggest a problem for the participant to agree with.
4. **The critique** marks each leading or pitching question, and the tallies
   show which findings rest on one.

A leading question that uses no listed term gets past the gate. That is what
layers 3 and 4 are for.

### Background material

- It is third-party text and may hold instructions. It reaches a session with
  no network, which can write only in its own room.
- It may hold real people's words. The user removes names and identifying
  details before adding a file. No script can check that, so the scaffold says it
  once, and the plan names the providers that will receive it.
- A harness transcript holds whatever its session read. `purge-sessions`
  deletes those sessions, as now.

## The Mom Test in the briefs

The briefs, the reference files and the critique are written from three
research notes on the book. The notes are the user's own and are kept
outside this repository, so whoever writes the briefs is given them then.
The skill ships only what is written from them: original wording, with no
dialogue or worksheet from the book. Each file states which parts are the
book's method and which are operator adaptations, as the notes do. Nothing
the skill ships names a person: its briefs, references and scripts say "the
user".

| Short name | File |
| --- | --- |
| Framework | `the-mom-test-framework.md` |
| Field guide | `interview-field-guide.md` |
| Toolkit | `implementation-toolkit.md` |

### Interviewer brief

`assets/interviewer-brief.md` teaches the method first, then points to the
reference files. In this order:

| Part of the brief | Rule | From |
| --- | --- | --- |
| Stance | Uncover what is true, not approval. A problem that turns out not to exist is a good result | Framework: Scope and core thesis; Important questions ("Love bad news") |
| The three rules | Their life, not your idea. Specific past events, not habits or futures. Listen more than you speak | Framework: Three rules |
| What a question can tell you | A fact or a constraint, never an endorsement, an imagined purchase or a roadmap | Framework: Question quality |
| Opening | State the purpose from `about`. Start broad when priority is unknown, and note whether a topic came up unprompted or you raised it | Field guide: Opening. Framework: "Look before you zoom" |
| Following one event | Anchor, trigger, desired outcome, sequence, tools and people, breakdown, consequence, coping, alternatives, frequency, constraints | Field guide: Event reconstruction, steps 1 to 11 |
| Bad data | Compliments, generalities, hypotheticals, promises and feature ideas are not evidence. Return to the last real instance | Framework: Bad-data handling. Field guide: Recovery |
| Feature requests | Ask what it would enable, what happened without it and how they cope | Framework: Feature requests. Field guide: Feature triage |
| Money and buying | What is spent now, who approved it, who can veto. Never "how much would you pay" | Framework: Money and buying. Toolkit: Question rewrites, Buying map |
| Never | Pitch, name an idea, ask "would you", ask a question that presumes its answer, suggest an incident, argue with an answer, ask two questions at once | Framework: Bad-data handling (pitching and correction). Toolkit: Question rewrites. Field guide: Event reconstruction, step 1. The last is an operator adaptation |
| When to move on | The topic is not a priority for this person, the answers repeat, or the topic's turns are used | Framework: Evidence and stopping; Important questions |
| Closing | Ask what you missed, and who else does this work | Field guide: Closing. Framework: Question quality |
| Left out, and why | No commitment or next-step ask, no demo, no request to see a document: none means anything in a simulation | Framework: Commitment and advancement. Field guide: Event reconstruction, step 12 |
| Reply format | `TOPIC`, `MOVE`, `WHY`, `SAY` and `END` | This PRD |

### Reference files

Copied into each interviewer's folder, and named in the brief with when to
open each, so the interviewer reads one when the situation comes up.

| File | Open it when | From |
| --- | --- | --- |
| `recovery.md` | An answer is praise, a generality, a promise, a feature idea or strong feeling, or you catch yourself explaining | Field guide: Recovery |
| `event-reconstruction.md` | A participant has named a real instance and you want all of it | Field guide: Event reconstruction |
| `question-rewrites.md` | The question you are about to ask sounds like an opinion poll | Toolkit: Question rewrites |
| `feature-requests.md` | They ask for a feature, or describe their ideal tool | Framework: Feature requests. Field guide: Feature triage |
| `money-and-buying.md` | Spending, budgets or who decides comes up | Framework: Money and buying. Toolkit: Buying map |
| `priority.md` | You do not know yet whether the topic matters to them | Framework: Important questions. Field guide: Opening |
| `case-lessons.md` | An answer surprises you and you are unsure what it means | Framework: Case lessons |

If discovery shows that interviewers never open them, their text moves into
the brief and the interviewer's file tools go.

### Participant brief

`assets/participant-brief.md` pushes against a model's wish to be helpful. It
is written from how the notes say real people answer, which is the reason the
book exists.

| Rule in the brief | From |
| --- | --- |
| Answer as you would aloud: two to five sentences, no lists, no headings, no offer to say more | This PRD |
| Start general, as people do ("it's usually fine"). Give a specific instance when you are asked for one | Framework: Three rules, rule 2 |
| A polite question gets a polite answer. Asked whether an idea sounds good or whether you would use something, say the easy, agreeable thing | Framework: Bad-data handling (compliments, fluff) |
| Most things are not a problem for you. Say so, and do not let a question talk you into one | Framework: "Look before you zoom"; Case lessons (fitness ranking, investor dealflow) |
| A complaint is not a need. Something can annoy you and still be handled well enough that you would change nothing. What you have tried and paid for is what your persona and your card say, no more | Framework: Case lessons (the complaint solved by interns). The last sentence is this PRD's |
| Your habits have exceptions you do not think of until asked | Framework: Case lessons (the inbox-zero claim) |
| Know only what your role knows. If someone else holds the budget, say so | Framework: Money and buying |
| Say "I'd have to check" or "I don't remember" where a real person would | Field guide: Event reconstruction, step 1 |
| Keep to what you have already said, and to your card | This PRD |
| You have other things to do. If the interviewer wastes your time or starts selling, get shorter, and leave if you would | Framework: Casual conversations; Bad-data handling |
| Stay in character. Never mention being an AI, a model or a panel | This PRD |

The effect is that a bad question gets the bad data it would get in real
life, and a good one gets specifics. That is what makes the transcript worth
learning from.

### Situation card

Before the first question a participant writes a short private card from its
persona and its background material:

- what is taking its attention at work now
- two to four things that really bother it, each with one recent incident:
  when, what happened, what it cost, what it did about it
- things an outsider would assume are problems and are not
- what it uses and pays for, and who decides

The card is the participant's first reply. The launcher records it and never
passes it on. It does three things:

- **It fixes the invented history before the interviewer can shape it.** A
  probe then recalls the card, where without one each deeper question makes
  up more.
- **It gives the critique something to mark against:** which of the card's
  problems the interview found, and which it missed. A real interview has no
  such answer key.
- **It shows what is model taste.** The same persona on two models writes two
  cards.

It costs one turn for each interview. Whether participants keep it to
themselves until asked is a [discovery](#discovery) question.

## Analysis and reporting

No scores. The steps, each a script or a job the launcher starts:

1. `check_runs.py <study>`
2. `launch.py <study> run --role analyst` and `run --role critic`, in either
   order
3. `extract_notes.py <study>`
4. `launch.py <study> run --role themes`
5. `analyze.py <study>`
6. `launch.py <study> run --role writer`

The synthesis pool is divided equally among every job planned: the analysts,
as many critics, the themes job and the writer.

### What `check_runs.py` checks

Blocking:

- no end record, or a turn log whose turns do not alternate or skip a number
- a `leak_terms` entry in a question that was delivered

Notes, none blocking:

- topics never opened, exchanges past a topic's cap, and a capped interview
  that ended with no close
- a `leak_terms` entry in an answer, which is background leaking in from the
  harness, as it is in a review
- an answer that speaks of being an AI, a model or a persona
- an interviewer turn with more than two question marks
- the median length of the answers, when it is over 120 words
- a repair turn, and a turn that was put again

### Coding

Each analyst reads the analysts' copy of its personas' transcripts
(`analysis/transcripts/<run id>.md`): the numbered turns as they were spoken,
with no situation card and none of the interviewer's `TOPIC`, `MOVE` and
`WHY`. It writes `analysis/qual-<n>.md`: what each participant said, in
prose, then one evidence note for each signal, in a fixed form the next
script reads:

```text
### Note P01-sonnet/3
- Turns: 7-9
- Signal: PAIN
- Statement: Chases clients for payslips by text, three or four times a loan
- Raised: unprompted
- Evidence: incident
- Effort: workaround
- Quote: "I sent her the list on the Monday and I was still texting her on the Friday."
```

| Field | Values | From |
| --- | --- | --- |
| Signal | `PAIN`, `GOAL`, `OBSTACLE`, `WORKAROUND`, `REQUEST`, `BUYING-CRITERION`, `MONEY`, `PERSON`, `CONTEXT` | Toolkit: Evidence note card |
| Raised | `unprompted`: the participant brought it up before the interviewer named the area. `prompted`: after | Field guide: Opening |
| Evidence | `incident`: a specific past event. `general`: a "usually" or "always" with no instance. `opinion`. `future`: what they would do. `request`: a feature asked for | Field guide: Evidence interpretation |
| Effort | `none`, `workaround`, `searched`, `paid`, `unknown`: what they have done about it | Framework: Bad-data handling; Early customers |

`extract_notes.py` writes `analysis/notes.csv`, one row for each note. It
gives each note its topic from the turn log, by the first turn the note
names, since an analyst never sees a topic id. It checks every `Quote` against the turns the note names, word for word, and
lists the ones it cannot find as unverified. A note it cannot parse is listed
and never guessed, as `extract_answers.py` does.

### Themes and tallies

Two analysts name the same problem two ways, so one job puts the notes into
themes. `run --role themes` reads `notes.csv` alone, on the `synthesis.analyst`
model entry, and writes `analysis/themes.md`: each theme with an id, a name,
a one-line definition and the notes that belong to it.

`analyze.py` joins the two and writes `analysis/quant.md`. For each theme:

- participants who raised it, of those interviewed, and how many unprompted
- how many gave a specific incident, and the spread of `Effort`
- the same by segment, and by model key
- how many of its notes rest on a question the critique flagged

And for the round:

- coverage: for each topic, how many interviews opened it and how many
  participants said it did not matter
- model agreement: a theme a persona raised on one model and not another is
  model taste
- the notes no theme took, and the incomplete interviews, listed apart from
  the headline tables as today

A count here is a count of simulated participants. Every table says so in its
heading, and none is labelled frequency or prevalence.

### Critique

Each critic reads the full transcripts of its half, with `MOVE` and `WHY`,
the guide and each situation card, and writes `analysis/critique-<n>.md` in a
fixed form. `extract_notes.py` reads it into `analysis/critique.csv`.

Flags on a question, each with a better question beside it:

| Flag | The question | From |
| --- | --- | --- |
| `pitch` | States or explains an idea or a solution | Framework: Three rules, rule 1 |
| `hypothetical` | Asks what they would do, or to imagine | Framework: Three rules, rule 2. Toolkit: Question rewrites |
| `leading` | Presumes the problem or the answer | Toolkit: Question rewrites. Field guide: Event reconstruction, step 1 |
| `opinion` | Asks them to judge an idea | Framework: Question quality |
| `generic` | Asks how they usually do it, and takes the general answer | Framework: Three rules, rule 2 |
| `price-guess` | Asks what they would pay | Framework: Money and buying |
| `wishlist` | Asks what features they want | Framework: Feature requests |
| `zoom` | Goes into detail before the topic is known to matter | Framework: "Look before you zoom" |
| `talking` | Explains, corrects, or sums up with its own reading | Framework: Three rules, rule 3 |
| `rescue` | Argues with a negative answer | Framework: "Love bad news" |
| `compound` | Asks several things at once | Operator adaptation |

Missed signals on an answer: praise taken as evidence, a generality not
anchored, a feature request not followed to its cause, strong feeling not
explored, a contradiction passed over, who pays never asked, a "that's not a
problem for me" pushed against.

Good moves are named too, with the turn, because the user learns as much from
them: a generality anchored, a consequence asked for, bad news accepted.

Each interview ends with the field guide's final interview check, as far as
it applies: whether a specific event, its effort and its consequence were
found or their absence recorded, whether priority came before detail, whether
user and buyer were told apart, and what was learned against each goal. Then
the card: which of its problems the interview found and which it missed.

### The transcript

`interviews/<run id>.md`, rendered from the turn log, opens with the notice,
the participant's recruitment facts and the situation card marked as hidden
from the interviewer. Each exchange then shows the topic, the move, the
reason, the question and the answer. It is for the user, the lead and the
critic.

The analysts' copy, `analysis/transcripts/<run id>.md`, has the notice, the
recruitment facts and the numbered questions and answers, and nothing else:
no card, no topic, no move and no reason. The launcher writes both when an
interview ends, and `interview.py <study> render` writes them again.

### The final summary

The writer's `analysis/SYNTHESIS.md` follows the toolkit's batch debrief and
decision record:

1. **What this is.** The notice, then the limits in plain words.
2. **Each learning goal:** what was heard, how strongly, and what was heard
   against it.
3. **Problem themes,** from the tallies.
4. **What was not a problem,** and the topics participants did not care
   about.
5. **How they cope now:** workarounds, tools, spending and who decides, as
   told.
6. **Where segments differ,** and where models disagree.
7. **Quotes,** each verified, with its run and turn.
8. **How the interviews went:** the critique's counts, the most instructive
   good and bad exchanges, the findings that rest on a flagged question, and
   what the cards held that no interview found.
9. **For the real interviews:** the hypotheses worth testing, a revised
   guide, and the next three learning goals.
10. **What remains unproven.** The framework's four conclusions stay apart: a
    problem exists, this segment puts it first, a solution delivers, a buyer
    pays. A simulated round bears on none of them, and offers guesses about
    the first two.

## Debrief interviews

The answer to "what challenges do they have with my tool".

A finished run of a review or usability study has seen the tool, in the
materials or in a browser. `interview.py <study> debrief --runs <ids>|all`
interviews each such run in the session it worked in, as `followup.py ask`
puts a question to one.

- The study's `study.json` gains a `debrief` block: `interviewer`, `goals`,
  `topics` and `turns`, as in `interview`. Its goals may name the tool.
- The interviewer brief for a debrief keeps the same rules and changes the
  subject: what the participant did, saw and expected in the session. It
  still never asks what they would do. It is given the task goals or the
  concept labels, and nothing of the run's results.
- Each participant turn is an attempt of kind `debrief` on the finished run.
  The run stays `done`. Its persona file is copied before each turn and put
  back if the turn changed it, by the rule a follow-up is settled with.
- A usability run answers with no browser and no account, as it does to a
  follow-up.
- `limits.debrief` is each run's allowance, outside the plan's ceiling, and
  `--dry-run` prints the most the runs can use.
- The transcripts land in `interviews/`. The analysts' and the writer's
  briefs name them as product feedback, and no script tallies them.
- Ask before `run --role analyst`, as with follow-ups.

A debrief has no situation card, and nothing in it counts as discovery: the
participant has seen the product.

## Practice mode

`interview.py <study> practise --persona <id> --model <key>` puts the user in
the interviewer's seat, in a terminal.

- It starts a participant exactly as an interview does, prints the
  recruitment facts, and reads each question from the keyboard. `/end` closes
  the interview and `/quit` leaves it to continue later.
- It is a run of its own, `<pid>-<key>-p<n>`, marked as practice. It appears
  in `status` and the usage record, and in no tally.
- `launch.py <study> run --role critic --runs <id>` critiques it against the
  same rubric and the participant's card. That is the point of the mode.
- It holds the study lock while it is open, so nothing else runs in that
  study meanwhile. A study directory of its own avoids that.
- It needs a real terminal. A lead's background shell cannot type for the user.
- The participant's `limits.run` and `limits.turn` apply. Time the user
  spends thinking is not counted, since only a process's time is.

## Known weaknesses

`references/interviews.md` and every report state these.

- **Invented history.** The method's core move is asking about real past
  behaviour, and a persona has no past. It invents one, and each deeper probe
  invents more. The card fixes the outline early, and nothing makes it true.
  The output is hypotheses and a rehearsed guide. It says nothing about how
  often a problem happens or how much it costs.
- **Agreeable participants.** A model is more articulate, more cooperative
  and more self-aware than a busy broker. The participant brief pushes
  against that and will not remove it. Comparing models shows what is model
  taste. Nothing shows what real people would say.
- **Cost grows with length.** Each turn is a process that re-reads the whole
  conversation, so an interview's input grows with the square of its
  exchanges. Most of it should be read from a cache. Whether it is, on each
  harness, is a discovery measurement, and turn caps bound it either way.
- **Background material cannot be told from invention.** An answer that
  paraphrases a real support ticket reads like one the model made up. The
  user checks any finding that matters against their own material.
- **An interviewer and a participant on the same model** agree with each
  other more readily. The plan says when they match.
- **The critique is a model's opinion** of a model's questions. It teaches
  the method. It does not certify an interview.
- **On Codex, isolation is by instruction** for everything a session could
  read.

## Changes to the skill's documents

**`SKILL.md`:**

- The `description`, rewritten for three types in 1,021 characters:

  > Run simulated customer research with AI agents playing personas (buyers,
  > users, gatekeepers, sceptics) on several models. Review: personas score
  > design concepts such as landing pages, pricing pages or onboarding flows
  > (site folders, live URLs, PDFs, screenshots), giving a leaderboard,
  > quotes, ICP signal and recommendations. Usability: personas attempt
  > tasks in a running local build through a browser, giving task completion
  > and stuck points. Interview: an interviewer agent runs Mom Test style
  > discovery interviews with each persona, giving transcripts, problem
  > themes and a critique of the questions. Load whenever the user wants
  > personas, a persona panel, simulated or synthetic users, customers or
  > user research, AI agents to review, compare or score concepts 'like real
  > customers would', which concept prospects prefer or who the ideal
  > customer is, usability or task testing with AI personas, simulated
  > customer interviews, interview practice, or to rerun or extend an
  > earlier round, even without the word 'panel'.

- The study layout gains `interviews/`, `interviewer/`, `background/` and
  `panel/rooms/`.
- One paragraph for an interview study, as usability has: read
  `references/interviews.md` first, start from
  `assets/study.interview.example.json`, and how the workflow differs.
- One line each for debriefs and practice mode.
- Rules: a standalone interview never names the user's own product, and a
  count of simulated participants is never reported as frequency.

**References:**

- New `references/interviews.md`: when to run one, drafting the goals and the
  guide with the user (the toolkit's discovery brief), the protocol, reading
  a transcript, the analysis steps, debriefs, practice mode, safety and how
  much to trust the result.
- `references/method.md`: a short section that points to it.
- `references/runners.md`: what an interview asks of a runner.
- `references/archive.md`: what is kept and what is cut.
- `references/communicating.md`: how to report an interview round.

**Assets:**

- `study.interview.example.json`
- `interview-study-brief.md`: the lead's brief for an interview round, from
  the toolkit's discovery brief: the decision, the hypotheses, what would
  change the decision, the segment, the three learning goals with the
  uncomfortable one, and what the round cannot prove
- `interviewer-brief.md` and `interviewer-brief-debrief.md`
- `interview-reference/`: the seven reference files
- `participant-brief.md` and `participant-run-prompt.md`
- `interviewer-turn.md`, `interviewer-repair.md` and `interviewer-end-check.md`:
  the frames the launcher sends
- `interview-qual-brief.md`, `interview-critique-brief.md`,
  `interview-themes-brief.md` and `interview-synthesis-brief.md`

**Scripts:**

- New `interview.py` (the turn rules, `render`, `debrief`, `practise`) and
  `extract_notes.py`.
- Changed: `panel_lib.py` (the type, its keys, the turn log),
  `init_study.py` (a third scaffold), `launch.py` and `launch_plan.py` (the
  interviewer role, the turn loop, the plan, the job roles `critic` and
  `themes`), `check_runs.py`, `analyze.py` and `archive.py`.
- `followup.py` refuses an interview study: an interview that has ended is
  closed, and a new question belongs in the next round's guide.

## Discovery

To settle before the first milestone is built, on Claude Code and Codex, with
the results recorded in this document as the expansion PRD records its own.

1. **Turn cost.** For exchanges 1, 10 and 30 on each harness: input, cached
   and output tokens, list-price cost where reported, and seconds from start
   to reply, with the CLI's own start-up time apart. That gives the estimate
   for the plan and the defaults for `limits`.
2. **Caching across resumes.** Whether a resumed turn reads its history from
   a cache, and what happens when the other side took minutes to answer.
3. **Persona hold.** One participant through 40 resumes on each harness:
   breaks of character, drift in answer length, talk about files or tools,
   and whether an answer at exchange 35 agrees with one at exchange 5.
   Whether a harness compacts the conversation, and what is lost when it
   does.
4. **A session with no tools.** Whether `claude -p --tools ""` runs and
   resumes under the runner's other flags, and whether anything removes
   Codex's shell tool. If Claude Code can, the participant runs that way
   there, behind a new runner option, and the Pi runner is not touched.
5. **The default system prompt in a conversation.** The same interview with
   the default prompt and with a replaced one, for both sides. The review
   experiment found no difference, and a conversation may differ. If a
   replaced prompt is needed, stop and ask the user.
6. **The reply format.** How often each model's interviewer reply parses
   over 30 turns, and how often one repair fixes it.
7. **The reference files.** Whether an interviewer opens them, and whether
   the critique's flags differ with the references in files, in the brief,
   or absent.
8. **The situation card.** Whether a participant keeps it to itself until
   asked, stays consistent with it, and still says that some things are not
   a problem.
9. **Resumed turns against fresh ones.** The same interview with every turn
   a new session that is handed the transcript so far. It needs no resume
   and survives a lost session. It may cost more and read less like a
   conversation. This PRD assumes resumed sessions. If the measurements say
   otherwise, stop and ask the user.
10. **Many short processes.** Whether 60 processes an interview, several
    interviews at once, trip a rate limit that today's concurrency defaults
    do not.

## Edge cases

- **The interviewer replies with no `SAY`, or an empty one.** One repair,
  then `partial`.
- **The participant replies with nothing.** The question is put once more,
  then `partial`.
- **The participant asks what this is about.** The interviewer answers from
  `about`, and that exchange counts.
- **The participant ends the conversation in character.** The interviewer
  ends the interview with that as its reason. It is `done`, with its unopened
  topics on record.
- **The interviewer tries to end at the first turn.** The end check asks
  once, and a confirmed end stands. The pilot is where that shows.
- **A topic's `segments` leaves a persona with no topic.** The scaffold
  refuses it.
- **One side is blocked by a usage limit.** The interview is `blocked` and
  the other side waits. `resume` continues it, at whatever a cold cache then
  costs.
- **The interviewer's runner is blocked.** Every interview stops, since all
  share it.
- **The same model entry interviews and answers.** Allowed, and the plan
  says so.
- **Replicates.** Each is a separate interview with a new card. The spread
  between them is reported beside model agreement.
- **A variant** is interviewed like any persona and grouped with its parent
  in the tallies.
- **A background file changes after the scaffold.** The prompt holds the
  copy made then. `init_study.py --force` takes the new one.
- **A practice run is left open.** It stays `partial` and holds no lock once
  its terminal has gone.
- **A debrief names a run whose session is gone.** It is refused before
  anything starts, as a follow-up is.
- **An old study is loaded.** It has no `interview` key and reads as it does
  today.

## Tests

Contract tests in `packages/common/agents/tests/test_persona_panel.py`,
against the fake CLIs, under the `test-audit` authoring gate. The fakes learn
to play a participant and an interviewer from a plan. No test calls a model.

Contracts worth a test:

- the turn loop alternates, and the turn log has one record for each turn
- only `SAY` reaches the participant: a marker planted in `WHY` and in the
  guide never appears in a participant's input
- a marker planted in a persona's bio, its background and its card never
  appears in an interviewer's input
- a launcher killed at each point of a turn loses no turn and records none
  twice, and `resume` continues at the turn reached
- `done` is decided by the end record, never by an exit code
- the analysts' copy of a transcript holds no card and none of the
  interviewer's notes, and each note gets its topic from the turn log
- at the interview cap a last question that is no close is sent back once,
  then the interview ends without it, and a topic cap adds
  its notice
- an end with topics unopened is asked about once, then stands
- a question that holds a leak term is not delivered
- a reply that will not parse is repaired once, then leaves the run `partial`
- each side's limits add up over its turns, and a single turn is stopped at
  `limits.turn`
- a usage limit on either side leaves the interview `blocked` and resumable
- the plan's ceiling counts both sides of every interview and starts nothing
- keys of another type are refused in an interview study, and `interview` is
  refused in the others
- existing review and usability studies load and pass unchanged
- `check_runs.py` blocks on a missing end record and notes an unopened topic
- `extract_notes.py` lists an unparsed note and an unverified quote, and
  guesses neither
- the tallies count participants, split prompted from unprompted, and mark
  notes that rest on a flagged question
- the synthesis pool is divided among every planned job
- the archive keeps the turn logs and transcripts, cuts the background from
  the prompts and leaves `background/` out
- a debrief turn never changes a persona file or a run's state
- a practice run takes its questions from standard input and stays out of
  the tallies

## Acceptance criteria

**E2E** means verified with real harnesses. **Tests** means covered by the
contract tests.

Interviews:

- A study with participants on Claude Code and Codex and one interviewer runs
  to completion from one `launch.py run`, and every interview passes
  `check_runs.py`. E2E
- A transcript shows the topic, the move and the reason for every question.
  E2E
- No participant input holds a learning goal, a topic id or the
  interviewer's notes. Tests, and once E2E with planted markers
- No interviewer input holds a persona's bio, background or card. Tests, and
  once E2E with planted markers
- Killing the launcher mid-interview and starting it again loses no turn and
  repeats none. Tests and E2E
- An interview stopped by a limit keeps its turns and is reported `limited`.
  Tests
- `plan` starts no process and makes no model call. Tests

Method:

- In a pilot, the critique finds no `pitch` and no `price-guess` in an
  interview led by the interviewer brief. E2E
- A deliberately bad question from a scripted interviewer ("would you pay
  for an app that does this?") gets an agreeable answer from the participant
  and a flag from the critic. E2E
- Asked about something its card lists as no problem, a participant says so.
  E2E

Analysis:

- The tallies for a finished study match a hand count of three interviews.
  E2E
- Every quote in the synthesis is in the transcript it names, word for word.
  Tests
- An incomplete interview is absent from the headline tables. Tests
- The synthesis carries the notice and states the known weaknesses. E2E

Debrief and practice:

- A debrief reaches the session of a finished usability run and changes
  nothing in its persona file. E2E
- The user completes a practice interview in a terminal and gets a critique of
  their own questions. E2E

Documents:

- A lead on a harness other than Claude Code runs an interview study by
  following `SKILL.md`. E2E
- The `description` is under 1,024 characters. Tests

## Risks

- **False confidence.** A fluent transcript reads like evidence. Mitigation:
  the notice, the weaknesses in every report, counts labelled as simulated,
  and a summary that ends in what to ask real people.
- **The interviewer drifts from the method** over a long conversation.
  Mitigation: the pilot, the critique, and turn caps that keep interviews
  short.
- **The participant gives everything away at once,** or will not be drawn.
  Mitigation: the participant brief, the card, the pilot, and the answer
  length note in `check_runs.py`.
- **A coding harness's own prompt works against a conversation.**
  Mitigation: discovery item 5, with the decision left to the user.
- **Cost surprises.** Mitigation: discovery items 1 and 2, the pilot's
  measured estimate, and caps on turns, time and budget for both sides.
- **The launcher grows.** `launch.py` is about 3,150 lines and gains a role
  and a loop. Mitigation: the turn rules live in `interview.py`, and the
  supervisor only calls them.
- **Real material leaves the machine.** Mitigation: `background/` is
  explicit, the plan names who receives it, and the archive leaves it out.
- **The book's method is bent to fit.** Mitigation: the briefs say what was
  left out and why, and name their sources.

## Order of work

Each milestone is usable without the ones after it.

1. **Discovery.** The ten items above, recorded here, with any decision they
   force put to the user.
2. **The interview study.** The type and its keys, the scaffold, the two
   briefs and the reference files, the turn loop, limits, states and resume,
   the transcript, the plan and `check_runs.py`.
3. **Analysis.** Coding, `extract_notes.py`, the themes job, the tallies, the
   critique and the writer's brief. The archive.
4. **Debrief interviews** on finished review and usability runs.
5. **Practice mode.**

## Open questions for the user

Each is drafted as the recommended answer.

1. **A third type in the same skill?** Recommended: yes.
2. **Should interviewers learn across interviews?** Recommended: no, within
   a round. Revise the guide between rounds.
3. **The situation card.** Recommended: on by default. It costs one turn an
   interview and gives the critique an answer key.
4. **Your own tool.** Recommended: only in a debrief of a finished review or
   usability run. A standalone interview never names it. Is the debrief
   worth building, or do follow-up questions cover it for now?
5. **Background material.** Recommended: participants only, copied into
   their prompts from `background/`, with names removed by you first. Should
   analysts later see it too, so each note can be marked as backed by real
   material or not? Recommended: yes, as a later addition.
6. **Practice mode.** Recommended: in scope, last. Should it ship before the
   debrief, since rehearsal is one of your two reasons for wanting this?
7. **One interviewer model for a study.** Recommended: yes. Comparing
   interviewers is a second study.
8. **The critic's model.** Recommended: a different vendor from the
   interviewer's, with a note in the plan when they match and no refusal.
9. **A themes job of its own.** Recommended: yes. The alternative is one
   analyst for a whole round, which reads worse as transcripts add up.
10. **Follow-up questions after an interview.** Recommended: refused. A new
    question goes in the next round's guide.
11. **Pi.** Recommended: allowed when the unchanged runner passes the pilot,
    with no work to make it pass.
12. **Defaults** for `interview.turns` (30), a topic's turns (8) and
    `limits.turn` (3 minutes). Recommended: keep these until discovery
    measures them.
