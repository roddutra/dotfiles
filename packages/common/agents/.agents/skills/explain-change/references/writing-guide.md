# Writing guide

The reader is a product owner who knows their product well and their codebase less well. They read the page once, often on a phone, and want to know three things fast: what changed for their users, what was decided without them, and whether they agree. Every sentence on the page serves one of those. Drawn from the Google developer documentation style guide (developers.google.com/style) and adapted to explainer pages.

## Boil it down first

- Before drafting, write the three sentences that matter most: what the change does for users, the most consequential decision made without the owner, and what the owner should do with this page. They become the "Read this first" block and set the tone for everything after.
- Lead every page, section, paragraph and answer with the point. Readers do not read every word; a key point at the end of a paragraph is a key point missed.
- Explain the behaviour, not the code. Name a class, method or file only when the reader has to go there. Describe the rest in words: "the call ends" rather than "`_end_call` is invoked".
- Cut anything the reader cannot act on or be surprised by. Restated requirements that matched exactly belong in the ledger table, not in prose.
- One idea per paragraph. If a paragraph covers what changed, why, and the risk, it is three paragraphs.

## Make it practical

The reader wants to know what a decision means for real people, not how it is encoded. For every deviation and decision, and for every learning-check answer, write these before anything else:

- **In practice:** one concrete moment, played out step by step. Name the actors and the inputs: "A caller keys the six-digit code. The server approves it. The local update fails. The line goes dead."
- **Users experience:** what the end user or operator sees, hears, waits for or loses. If nothing changes for them, say so and say who is affected instead.
- **Your options:** the shipped behaviour and the real alternatives, each as an experience and a cost: "Retry once: the caller hears two seconds of silence, then continues. Costs a second server round trip."
- **Titles are behaviour, not mechanism.** "If the setup step fails, the call ends without a message" rather than "Failed grant application terminates locally with no rollback".

Assume no prior knowledge of the internals. When a moving part must be named, define it in the same sentence: "the admission grant, the server's approval for this call to continue". Citations go in one muted evidence line at the end of the card; the reader can ask the agent for the code walk.

## Budgets

These are ceilings, checked in the verify step, not targets to fill.

| Page | Whole page | Read this first | Any one card or answer |
|---|---|---|---|
| Small change | 1200 words | 60 words | 120 words |
| Material change or slice | 2500 words | 80 words | 150 words |
| Index | 900 words | 80 words | 60 words per slice entry |

- Sentences: 20 words on average, none over 26. Split rather than join.
- Paragraphs: one idea, five sentences at most, one-sentence paragraphs are fine.
- Lists: four to six items; longer lists mean the grouping is wrong.
- Learning-check answers: the "what the code does" part is two or three sentences; the consequence is one.

## Voice

- Second person for the reader ("you asked for", "you decide"), third person for the software ("the service rejects").
- Present tense for behaviour: "the server removes the record", not "will remove".
- Active voice: "the worker retries the job", not "the job is retried". Passive only when the actor is genuinely unknown or irrelevant.
- Conversational and precise, like a knowledgeable colleague. No forced enthusiasm, no hedging cascades, no lecturing.
- Do not anthropomorphise code. Code specifies, returns, rejects and records; it does not want, think, decide to, or tell.
- Say who did what: "the implementing agent chose", "you approved in review", "the spec requires". Never a bare "it was decided".

## Words

- Cut filler: just, simply, easily, basically, actually, in order to (use "to"), please, leverage (use "use"), utilise (use "use"), robust, seamless, actionable.
- Cut time anchors: currently, now, new, existing, as of this writing. The page is pinned to a snapshot; the snapshot line carries the time.
- Spell out abbreviations on first use, then abbreviate. Write "for example" and "that is", never "e.g." or "i.e.". No "etc."
- Replace jargon with the plain word or define it once in a callout: "import" for "ingest", "affected area" for "blast radius", "does not respond" for "hangs". Test each term: can you write around it, or is there a more specific plain word?
- One term per concept, the repository's canonical one, used the same way on every page.
- No idioms, no figurative language, no humour. They do not survive a tired reader or a second language.
- No double negatives: "you can continue without a path", not "a missing path does not prevent continuing".
- No directional language: "in the preceding figure", not "above"; link by name, not position.

## Layout

- Headings are sentence case, describe the content, contain no code or links, and never skip a level.
- Introduce every list and table with a full sentence ending in a colon. List items are parallel in shape and each starts with a capital.
- Numbered lists only when order matters.
- Tables only when each row has three or more related values. Two-column key-value sets are a list. Never merge cells.
- Callouts sparingly, one at a time, never stacked. Write the information as plain text first; promote it to a callout only if it is outside the main flow and the reader must not miss it.
- Code font for filenames, classes, methods, values and placeholders. Never for product names. Do not inflect code elements ("call its `get` method", not "`get`s the value").
- Code samples only when the shape of the code is the point, at most 15 lines, with a comment where code is omitted.
- Link text is descriptive and front-loaded ("see the run admission guide"), never "here" or "this". Each link is a decision for the reader; prefer explaining on the page.
- Diagrams show mechanism with example data. The text beside a figure is a one-sentence caption, not a second explanation. Never put information only in a figure; colour is never the only signal.

## Learning-check questions

- Ask about consequences the reader can picture: a concrete situation with named inputs, then "what happens?"
- Medium difficulty: answerable from the page, never a gotcha, never trivia about names or line numbers.
- Multiple-choice options are parallel, plausible, and short. The wrong ones are real alternatives, not jokes.
- Answers lead with the outcome, then the evidence, then the consequence. Do not re-teach the section.

## Before and after

Verbose: "The commit also introduces a new dedicated boolean state flag, `outbound_call_terminal`, on the session state model, rather than repurposing the pre-existing `disclosure_completed` flag, which is a decision that was made by the implementing agent and which commits the codebase to maintaining two booleans that must both be read correctly by every future gate check."

Plain: "The agent added a second flag to mark a call as ended, instead of reusing the disclosure flag. Every future check must read both flags. The spec did not ask for this."
