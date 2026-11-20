# Prompt patterns

The watching model knows nothing about your conversation. Give it the purpose of the recording, who the output is for, and the exact shape you want back.

## Rules that pay off in every prompt

- **Say what the recording is.** "A screen-share call where a bookkeeper shows how they reconcile supplier invoices" gets a better account than "this video".
- **Ask for timestamps in `MM:SS`** (or `H:MM:SS` for recordings over an hour) on every item, so you can window in later.
- **Separate said from shown.** Ask for them as distinct fields or columns. Otherwise the model paraphrases the audio and skips the screen.
- **Ask for on-screen text verbatim**: menu paths, field names, button labels, values, URLs, error messages.
- **Give it a way to say it cannot tell.** "Write `[unreadable]` for text you cannot read; do not guess." Without this, small text is invented.
- **Name the things you care about.** Applications, screens, people. A named target is found; an unnamed one is summarised away.
- **Attach the transcript** with `--context-file` when you have one, and say how to use it: "The transcript is accurate for speech; use it for wording and speaker names, and the video for everything visual."

## Enrich a transcript with what was shown

```
This is a recording of a call where <person/role> walks through <task>. The attached
transcript covers the speech accurately.

Produce an enriched version of the walkthrough. Go through the recording in order and,
for each stretch where the screen shows something relevant, write:

- Time range (MM:SS-MM:SS)
- Said: one or two sentences summarising the speech, using the transcript's wording
- Shown: what is on screen. Name the application and screen, the exact menu path or
  buttons clicked, and copy field names and values verbatim
- Not in the transcript: anything visible that the speaker did not say aloud

Write [unreadable] where you cannot read on-screen text. Do not guess.
```

## Step-by-step procedure

```
Turn this walkthrough into a procedure someone else could follow. Number the steps.
For each: the action (exact UI path and control names as shown on screen), the values
entered, what the screen shows afterwards, and the MM:SS where it happens. List
separately any step the presenter did without explaining, and any point where they
corrected a mistake.
```

## Visual timeline (first pass over a long recording)

```
Give a timeline of this recording. One line per change of what is on screen:
MM:SS, the application or document in view, and a one-sentence description. Mark the
moments where small text, numbers or settings are shown that would be worth a closer
look.
```

Use the marked moments for detail passes with `--start/--end --resolution high`.

## Targeted question

```
Between 12:00 and 15:00 the presenter opens a settings dialog. List every setting
visible in it with its value, exactly as shown.
```

Pair it with `--start 12:00 --end 15:00 --resolution high`.

## Machine-readable output

Describe the JSON you want and ask for JSON only:

```
Return only a JSON array. Each item: {"start": "MM:SS", "end": "MM:SS",
"said": string, "shown": string, "screen_text": [string]}.
```

Parse defensively: strip a surrounding code fence before loading.

## Splitting a recording that does not fit

When a recording exceeds the model's input limit, cover it in consecutive windows with a small overlap (for example 0:00-45:00, 44:00-1:29:00), the same prompt each time, and merge the answers yourself. Tell the model in the prompt that it is seeing one part of a longer recording so it does not write an introduction or conclusion for each part.
