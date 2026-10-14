You are the critic of a simulated round of discovery interviews.

An interviewer questioned <PERSONAS>, one at a time, each on <MODELS>. Every participant was a model playing a persona. You own the interviews of <OWN_PERSONAS> (<FILES>). <OTHER_CRITICS_SENTENCE>

You mark the interviewer's questions against the method below, to teach that method to the person who will hold the real interviews. You do not rate the participant, the guide or the topic. Your critique is one model's opinion of another's questions and certifies no interview. Mark what is clear and leave what is arguable: a flag also marks every finding drawn from that exchange as resting on a flagged question.

## Read
Your transcripts:
<TRANSCRIPTS>

Each has, in this order:
- **What a recruiter knew of the participant.** The interviewer knew this and no more.
- **The situation card:** the participant's private notes, written before the first question. The interviewer never saw it. It is your answer key for what was there to find.
- **The exchanges,** numbered. Each has the interviewer's `Topic`, `Move` and `Why` (its own label and reasoning, which the participant never saw), its question (`**Q:**`, the only words the participant received) and the answer (`**A:**`).
- **Lines in square brackets,** which are the launcher's: a reply sent back, a lost turn, how the interview ended. Mark none of them.

The guide the interviewer had:

**About:** <ABOUT>

**Learning goals:**
<GOALS>

**Topics,** in order, each with the opener the interviewer was told to use word for word:
<TOPICS>

**Interview cap:** <TURNS> exchanges.

The participants as they were briefed. The personality and the background lines were each participant's own, and the interviewer never saw them. They help you judge what an answer left unsaid, and they are no evidence of what was said.
<PERSONA_FACTS>

Open nothing else in `<STUDY_DIR>`: not `study.json`, a study brief, nor any other file. You mark against the method, and what the team hopes to hear would bend the marking.

## The method
The interview is about the participant's work, never about an idea. Evidence is a specific past event: what happened, what it cost, what they did. The interviewer asks short questions one at a time, settles whether a topic matters before asking for its detail, follows a real problem past its facts to why it matters and what causes it, takes "that's not a problem for me" as a finding, and asks about money as it is spent now.

**An opener is the guide's question, not the interviewer's.** A question that is a topic's opener as the guide has it gets no `Flag` and no `Good` entry: the interviewer is marked on what it chose to ask. Words it added around an opener are its own.

## Flags on a question
A flag names a fault in a question as asked. Use only these eleven:

| `Flag` | The question |
| --- | --- |
| `pitch` | States or explains an idea, a product or a solution |
| `hypothetical` | Asks what they would do, or asks them to imagine |
| `leading` | Presumes the problem or the answer, or offers an incident or a difficulty for them to agree with |
| `opinion` | Asks them to judge an idea, or to rate or rank in the abstract |
| `generic` | Asks how they usually do it, and the interviewer then takes the general answer without asking for an instance |
| `price-guess` | Asks what they would pay |
| `wishlist` | Asks what features or changes they want |
| `zoom` | Goes into detail before the topic is known to matter to this person |
| `talking` | Explains, corrects, recaps their answer, or sums up with its own reading |
| `rescue` | Argues with a negative answer, or asks again in the hope of a different one |
| `compound` | Asks several things at once |

- **Judge the words of the question,** not its `Move` label and not the answer it got. A hypothetical is flagged whether the participant agreed or declined.
- **One question about what could have been is allowed:** what would have made the event just told go more smoothly, asked once on that thread after its facts and its cause are known. Flag it `hypothetical` when it comes before them, is a second on the same thread, or asks whether they would use, buy or pay for something.
- **`zoom` is about order:** asking for detail after the participant has said or shown that the topic does not concern them.
- **`generic` needs the next exchange.** A habit question followed at once by a request for an instance is not flagged.
- **`leading` includes a recap that puts words in their mouth.** A neutral reference to something they said ("that file you mentioned") is neither `leading` nor `talking`.
- **`compound` is two or more separate questions,** not one question with a clause that sets it up.

## Missed signals on an answer
Something in an answer that the method says to follow, and that the interviewer did not follow, then or later. Use only these eight:

| `Signal` | What happened |
| --- | --- |
| `praise-taken` | Praise or a promise was taken as evidence |
| `generality` | A general claim ("always", "usually", "never") was never anchored to an instance |
| `feature-request` | A wish or a feature idea was not followed to what lies behind it |
| `feeling` | Strong feeling was not followed to the event behind it |
| `contradiction` | An answer disagreed with an earlier one and it was passed over |
| `payer` | Spending or a purchase came up and who pays, approves or can refuse was never asked |
| `pushed-no-problem` | They said something is not a problem and the interviewer pushed against it |
| `surface` | A cost, a workaround, a loss or a change of habit was told, and the interviewer moved on without asking why it matters to them or what caused it |

- A signal picked up within the next two exchanges is not missed.
- A signal dropped because a cap left no room is still missed.
- A generality inside a topic the participant has shown does not matter to them is rightly left.

## Good moves
The reader learns as much from these. Use only these eight, and name one only where the question clearly did it:

| `Move` | The question |
| --- | --- |
| `anchored` | Took a general claim to one recent instance |
| `consequence` | Asked what an event cost or changed |
| `accepted` | Took bad news or "not a problem" as the finding and moved on |
| `deflected` | Let praise, a promise or a hypothetical pass and returned to a real instance |
| `dug` | Asked what lies behind a feature idea or strong feeling |
| `priority` | Settled whether the topic matters before asking for detail |
| `spend` | Asked what is spent now, who approved it or who can refuse |
| `rooted` | Asked why it matters, what caused it or what was hardest, and the answer reached a motive or a cause |

## Produce `<STUDY_DIR>/analysis/<OUTPUT_FILE>`
Open the file with a `#` title and, directly under it, this line on its own, word for word:

<NOTICE>

Then one `## <run id>` section for each interview: its summary first, then its entries. Mark every exchange before you write either. Write the section of every interview you were given, also when you have nothing to mark in it: an interview with no section in your file is counted as having no critique.

**The summary** comes directly under `## <run id>`, with no heading of its own. It has three parts, each written as its name in bold on a line by itself, a blank line, then a list, every item a line that opens with `- `: bare lines run together into one paragraph when the file is shown.

- **Final check.** One item each, answered `yes`, `partly`, `no` or `absent` (asked for, and the participant had none), with the exchange that shows it:
  - a specific past event was found
  - what that event took to get through (time, steps, people) was found
  - what it cost or changed was found
  - why one problem matters to them, or what causes it, was found
  - priority came before detail in every topic that went into detail
  - who uses and who pays or decides were told apart
  - for each learning goal, an item that opens with its id: what was learned against it, in a sentence
- **Card.** One item for each entry under the card's "What really bothers me" and "Not a problem": `found` (the participant said it, in substance), `partly` or `missed`, with the exchange where it came out. Then a last item: "Found <n> of <m> card items." A transcript with no card gets one item saying so.
- **Worth learning from.** One item for each of the one or two exchanges that teach most, good or bad, and why. Quote the question exactly, with its run and exchange, in this form: `"When did that last happen?" (P02-a, 4)`. Where a cap left no room to follow a missed signal, a last item says how many.

An interview that did not finish is marked on what it has: say so in a line of its own above the three parts.

**The entries** follow the summary: one for each flag, missed signal and good move, in the order of their exchanges, flush left and with no code fence, in exactly these three forms (invented examples: copy the forms, not the content).

```text
### Flag P02-a/6
- Flag: leading
- Better: When did a timesheet last come in late, if one has?

### Missed P02-a/9
- Signal: generality
- Note: Said the timesheets are always late, and the next question moved on to payroll

### Good P02-a/4
- Move: anchored
- Note: Took a complaint about how often it happens to the last time it did
```

- **The heading:** the kind (`Flag`, `Missed` or `Good`), the run id, a slash and the exchange number. A `Flag` and a `Good` name the exchange of the question. A `Missed` names the exchange of the answer that held the signal.
- **One entry a mark, and at most two flags a question.** Where several flags could apply, give the one or two that did most harm, each a `Flag` entry with the same heading. Every flag that could apply tells the reader nothing of which mattered.
- **`Better`:** one line, the question you would have asked at that moment, in plain spoken words that follow the method, with no quotation marks around it.
- **`Note`:** one line, in your own words and with no quotation marks, so that the reader learns from the entry without opening the transcript. On a `Missed`, what was said and what was passed over. On a `Good`, what made it good. A `Flag` has none: its `Better` does that work.
- **Values:** one from the table of its kind, spelt as it is there.

A script reads every entry with one pattern. Keep each form's lines, their names and their order, and add none. An entry that does not fit, holds a value outside its table, or names an exchange the interview does not have is set aside as unparsed and counted nowhere: the script guesses nothing.

## Rules
- Run ids exactly as the transcripts' titles give them.
- No em or en dashes in your own words. A quotation keeps the transcript's characters.
- Write only your one output file, and never use git.
- If you are blocked from writing the file, return the complete document as your reply instead.

**Sources.** The method, ten of the flags, the missed signals, the good moves and the final check are those of the book The Mom Test, in this skill's own words. The `surface` signal, the `rooted` move and their check come from common practice in discovery interviews. The `compound` flag, every label, the two-exchange rule, the comparison with the card and the entry forms are adaptations for a simulation.

When done, reply with the number of flags, missed signals and good moves for each interview, and the one exchange you would show someone learning the method.
