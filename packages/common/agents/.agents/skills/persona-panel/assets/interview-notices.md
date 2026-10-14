# Interview notices

The fixed sentences the launcher sends to an interviewer. An entry is a line that starts with a lower-case key, then a colon and a space, and the sentence is the rest of the line. Every other line is ignored.

- A `topic-cap` or `last-question` sentence fills the notice of `interviewer-turn.md`.
- An `end-check` sentence fills `interviewer-end-check.md`.
- One or more `repair` sentences fill `interviewer-repair.md`.
- The `again` sentence goes above a message that is sent to the interviewer a second time, after a turn that left no reply.

All of it is this skill's own wording for the turn loop. None of it comes from the book.

topic-cap: <TOPIC> has used its turns: move on or close.
last-question: This is your last question: close the interview.
end-check-one: <TOPICS> was not opened. Open it, or confirm the end with your reason.
end-check-many: <TOPICS> were not opened. Open the next one, or confirm the end with your reason.
repair-format: It does not follow the reply format.
repair-missing: It is missing: <FIELDS>.
repair-topic: TOPIC must be a topic id from your guide, `open` or `close`.
repair-move: MOVE must be one of the moves listed in your brief.
repair-say: SAY is empty. Put the words for the participant on the lines under `SAY:`.
repair-leak: SAY holds "<TERM>", which must not reach the participant: drop this term and ask again.
repair-last-exchange: This is the last exchange: reply with TOPIC: close.
again: Your reply to the message below was lost before it was recorded. Here it is again.
