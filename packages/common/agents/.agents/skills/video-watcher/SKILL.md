---
name: video-watcher
description: "Have a model with native video input (Gemini and others) actually watch a video file, frames, motion and audio together, and report back, for recordings the agent cannot see itself. Load whenever the user wants a video, meeting recording, screen-share walkthrough, demo, lecture or screen capture summarised, described, searched or turned into notes; wants a transcript enriched with what was shown on screen; asks what happens or what is visible at some point in a recording; or hands over a long video (minutes to hours), with or without a transcript. Examples: 'watch this recording and write up the process', 'what did they show on screen in this call', 'enrich this transcript from the video', 'summarise this .mp4'. Also load to set up or change this skill's provider, model or API key. For short UI clips where frame-accurate inspection of an animation or layout matters, use `video-inspector` instead, or both: this skill finds the moments, that one extracts the frames."
---

# Video Watcher

Coding agents read text and still images. This skill hands the real video file to a model that takes video natively and returns that model's answer as text. The watching model sees motion, on-screen content and audio together, which is what a transcript or a handful of frames cannot give you.

The bundled scripts do the work: resolve configuration, upload, call the model, save the answer. They are plain Python 3 with no dependencies; `ffmpeg` is needed only for `prepare.py`. `<skill-path>` below is this skill's directory.

Run the scripts by path from the user's working directory, for example `python3 <skill-path>/scripts/watch.py ...`. Do not `cd` into the skill directory first: project overrides and the session's project name both come from the directory you run from.

## This skill or `video-inspector`

- **`video-watcher`**: long recordings, anything where narration and visuals matter together, meeting walkthroughs, "what happened in this video". Another model watches; you read its report.
- **`video-inspector`**: short UI clips where you need your own eyes on exact frames (animation timing, layout, jank).
- **Both**: ask here for the timestamps of the moments that matter, then extract those frames with `video-inspector` to check a detail yourself.

## Before you send anything

The video leaves the machine and goes to a third party.

- Send only videos the user asked you to analyse.
- Run `config.py show` and tell the user which endpoint and model will receive the recording before the first send in a conversation. Project `.env` files can change both, so read them from `show`, not from memory.
- On Gemini the upload stays on Google's servers for about 48 hours so follow-ups skip the upload. Pass `--delete-remote` when the user wants nothing left behind.
- Providers treat data differently by plan. On Gemini, free-tier content may be used to improve Google's products. Say so when a recording looks confidential.

## Configuration

Four settings, with the same names everywhere:

| Setting | Meaning |
|---|---|
| `VIDEO_WATCHER_PROVIDER` | `gemini`, `openrouter` or `openai-compatible` |
| `VIDEO_WATCHER_MODEL` | Model id as the provider names it |
| `VIDEO_WATCHER_API_KEY` | Secret |
| `VIDEO_WATCHER_BASE_URL` | Endpoint override; required for `openai-compatible` |

Each setting is taken from the first place that defines it:

1. Flags on the command (`--provider`, `--model`, `--base-url`)
2. Environment variables
3. `.env.local`, then `.env`, in the directory the script is run from
4. `.env.local`, then `.env`, at the git root (when that is a different directory)
5. The global file, `~/.config/video-watcher/config.env`

So a project that sets only `VIDEO_WATCHER_MODEL` still uses the global provider and key. Only `VIDEO_WATCHER_*` names are read from a `.env`; the rest of the file is ignored. If a project changes the provider without supplying its own key, the run stops instead of sending the global key to a different service.

```bash
python3 <skill-path>/scripts/config.py show
```

Prints every resolved value and the file or layer it came from, with the key reduced to set or not set. `ready: false` plus `missing` means setup is needed.

### First-time setup

Help the user through this when `show` reports missing settings:

1. Ask which provider they want, then create the global file:
   `python3 <skill-path>/scripts/config.py init --scope global --provider gemini`
2. Get the key into the file **without it passing through the conversation**. Never ask the user to paste a key into chat. In order of preference:
   - If your harness has a secret-entry tool that delivers a value as a file or on stdin, pipe it: `python3 <skill-path>/scripts/config.py set-key --scope global < <secret-file>`
   - Otherwise ask the user to run `python3 <skill-path>/scripts/config.py set-key --scope global` in their own terminal (it prompts with hidden input), or to edit the file.
3. List the provider's models and agree on one with the user. Do not pick from memory; model names go stale quickly. Do not assume the most expensive tier is worth it: in a test on a one-hour screen-share, a mid-priced current model beat an older top-tier one at under half the cost, and the dearest current model was more accurate again at twice the price.
   `python3 <skill-path>/scripts/list_models.py [--filter <text>]`
   Then `python3 <skill-path>/scripts/config.py init --scope global --model <id>`
4. Confirm with a live call: `python3 <skill-path>/scripts/config.py check`

`init` is safe to rerun: it updates the values you pass and leaves the rest of the file alone.

### Project overrides

```bash
python3 <skill-path>/scripts/config.py init --scope project --model <id> [--provider ...] [--base-url ...] [--file .env.local]
```

Appends the overrides to the project's `.env` (or `--file`). It reports whether git tracks or ignores that file. A key belongs only in an ignored file; `set-key --scope project` refuses anything else.

## Workflow

### 1. Ask

```bash
python3 <skill-path>/scripts/watch.py --video <path> --prompt-file <prompt.md> [--context-file <transcript>] [options]
```

- Write anything longer than a line to a scratch file and pass `--prompt-file`; use `--prompt` for short questions.
- Pass a transcript, agenda or notes with `--context-file` (repeatable). The model then lines up what was said with what was shown.
- See `references/prompts.md` for prompt patterns that get dependable timestamps and verbatim on-screen text.

A short clip takes about 15 seconds. Long recordings take longer, plus upload time, so run them in the background if your harness allows it. Progress prints to stderr.

Stdout is one JSON object. On success: `answer_path` (read this file), `session`, `destination`, `usage`, `estimate`, `remote` and `notes`. Read `notes`; they flag cut-off answers and ignored options.

| Option | Use when |
|---|---|
| `--context-file <path>` | You have a transcript or notes to send alongside |
| `--start <t>` / `--end <t>` | Only part of the recording matters. Seconds or `[HH:]MM:SS` |
| `--resolution low\|medium\|high` | `high` for small text in a short window; about 4x the video tokens. Exact text is usually cheaper from frames |
| `--fps <n>` | Fast-moving content needs more than the default 1 frame per second |
| `--max-output-tokens <n>` | Cap or extend the answer length |
| `--session <session.json>` | Group this call with earlier ones about the same subject |
| `--title` / `--label` | Name a new session, or this call's folder |
| `--delete-remote` | Remove the upload from the provider after this call |
| `--model`, `--provider`, `--base-url` | One-off override of the configured values |
| `--timeout <s>` | Default 1800 |
| `--force` | Send even though the context estimate says it will not fit |

### 2. Plan the passes around cost

Every call re-sends the whole window of video; only the upload carries over. Video dominates the bill: an hour at default resolution is 330,000 to 370,000 video tokens on current Gemini models, and `--resolution high` is about four times that. The JSON's `estimate` and `usage` show the real numbers.

Use each tool for what it does best:

| Need | Tool |
|---|---|
| What happened and in what order; what was said versus shown; where to look | `video-watcher`: one full pass at default resolution |
| Exact text: file names, folder paths, numbers, table headers, field values | `video-inspector`: frames at the timestamps the first pass gave |
| Checking a claim the video model made | `video-inspector` |
| Small text across a stretch you have no timestamps for | `video-inspector`: a contact sheet, then frames |
| Motion or sequence that single frames cannot show, or a question tied to the audio | `video-watcher`: a narrow window, minutes long |

In the test that shaped this table, a one-hour screen-share, three high-resolution passes over 39 minutes cost more than the first pass and still got file names and numbers wrong. Reading about 30 frames settled them for a small fraction of those tokens, and you read the pixels yourself at full resolution.

1. **One full pass per recording**, at default resolution, with the transcript attached. Use the first-pass pattern in `references/prompts.md`: it asks the model for an index of exact details, each with the timestamp where it is most legible and a confidence.
2. **Decide what needs checking.** Only the details that matter for the user's goal: the names, paths and values someone will act on. Leave the rest as the model's reading and say so.
3. **Verify with `video-inspector`**, in a subagent so the images stay out of your context. Give it the list of claims and timestamps; have it extract a frame a second or two either side of each and return each value as confirmed, corrected or unreadable.
4. **Ask `video-watcher` again only for what frames cannot settle**, as a narrow window of a few minutes. Tell the user the estimated tokens first. `watch.py` refuses a high-resolution window longer than 10 minutes unless you pass `--force`; needing more than that is a sign the job belongs to frames.

Do not re-run a full pass to fix details. Follow-up questions about the same file reuse the upload, but the model remembers nothing: pass an earlier answer back with `--context-file` when the follow-up depends on it.

### 3. Report what was verified

Treat the answer as a report from a capable but fallible observer. Video models misread small text, tidy typos into what they expected, and occasionally describe screens that were not there.

- Cross-check names and quoted speech against the transcript.
- Mark which details were checked against frames and which are the model's reading.
- Tell the user which parts came from the video model.

Answers to broad prompts about long recordings can run to thousands of words. When the answer is an input to a larger task, have a subagent run this skill and return the distilled findings plus `answer_path`, so the full text stays out of your context but remains readable on demand.

## Timestamps

- With `--start/--end`, the model is told it is seeing part of a longer recording and answers on the full recording's clock.
- A file trimmed by `prepare.py` starts at zero. Add the `time_offset_seconds` from `prepare.py`'s output to every timestamp in the answer.

## When a run is refused

`watch.py` checks before it spends anything. Exit code 3 means nothing was sent to the model; the JSON carries an `error.code`, a message and `options`.

| `error.code` | Meaning | Usual fix |
|---|---|---|
| `file_too_large` | Over the provider's transport limit (2 GB on Gemini) | `prepare.py` |
| `unsupported_container` | The provider does not take this file type | `prepare.py` (outputs mp4) |
| `context_exceeded` | Video plus text plus room for the answer exceeds the model's input limit | A `--start/--end` window per call, or lower `--resolution` |
| `window_unsupported` | Inline providers cannot select a window | `prepare.py --start/--end` |
| `high_res_window_too_long` | More than 10 minutes at high resolution | Frames via `video-inspector`, or a narrower window |

Exit code 2 is configuration (missing or invalid; go to setup). Exit code 4 is the provider refusing or failing; report the message, do not retry blindly.

### Shrinking or trimming with ffmpeg

```bash
python3 <skill-path>/scripts/prepare.py --video <path> [--session <session.json>] [--start <t>] [--end <t>]
```

Keeps resolution (capped at 1080p) so on-screen text stays legible, and cuts size through frame rate and bitrate. Returns the `output` path to pass to `watch.py`. If `ffmpeg` is missing, ask the user before installing it.

## Sessions and housekeeping

Everything is written under `~/.video-watcher/<project>/<date>/<time-title>/`, outside any repo. Each call gets a folder with `prompt.md`, `answer.md` and `call.json`. Source videos are referenced, never copied.

- Reuse one session per subject with `--session`; omit it to start a new one.
- Find earlier answers instead of paying for them again:
  `python3 <skill-path>/scripts/list_sessions.py [--project <name>] [--date today|yesterday|YYYY-MM-DD] [--week] [--month]`
- See or remove uploads still held by the provider:
  `python3 <skill-path>/scripts/remote_files.py list` and `remote_files.py delete --name <files/...>` or `--all`
- Delete a session's local files only when the user asks:
  `python3 <skill-path>/scripts/cleanup_session.py --session <session.json>`

## Providers

`references/providers.md` has the detail. In short:

- **`gemini`**: uploads the file (up to 2 GB), supports windows, frame rate and resolution natively. Exercised end to end.
- **`openrouter`**, **`openai-compatible`**: send the file inline as base64, so they suit short or prepared clips (50 MB cap by default, `--max-inline-mb` to change). Written from the documentation and not yet exercised against a live endpoint; expect to debug the first real use.
