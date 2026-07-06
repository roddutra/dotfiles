---
name: video-inspector
description: "Visually inspect a video of a UI — a screen recording of a web app, an animation, a transition, a navigation flow, a button/dropdown/modal interaction, or a product/marketing demo — by extracting timestamp-labelled frames with ffmpeg and reading them as stills (models can't ingest video natively, so this bridges a video file to frames the agent can see). Load whenever the user wants the agent to watch, review, audit, or analyse how an interface or animation plays, or to record a UI flow and then assess it — e.g. 'watch this recording', 'review the animation in this .mp4/.mov/.webm', 'check how this transition plays', 'record the hero section and tell me what's wrong', 'capture that flow and audit it' — whether the recording already exists or the agent must capture it first."
---

# Video Inspector

Claude (and most coding-agent models) cannot ingest video natively — the vision API accepts still images only, and an animated GIF is read as a single frame. This skill bridges that gap: it drives the `ffmpeg` CLI locally to sample a recorded video into timestamp-labelled still frames, persists them under a hidden home-directory folder, and hands the agent an ordered list to read. The agent then genuinely *sees* each frame's pixels and can reason about layout, motion, timing, and what changes between moments.

The logic lives in the bundled Python scripts so the invoking agent only runs a script and reads the results — it never hand-builds an ffmpeg command or does frame math.

**Work cheap-to-expensive.** Reading many full-size frames is the dominant cost of this skill — each frame is a separate image the model ingests, so 30 frames is tens of thousands of vision tokens. Start with a **contact sheet** (one montage image of the whole timeline) to understand the staging, then drill into only the moments that need detail with full-resolution frames. The scripts are built around that order.

## When to Use

- Reviewing a **UI animation or transition** (easing, timing, jank, staging)
- Watching a **navigation flow** across pages, or an interaction: a button press, a dropdown expanding, a modal opening
- Sanity-checking a **product or marketing demo / sales-demo recording** visually
- Any time you need to *see* what an interface actually does over time

**Getting the recording is your job first — don't reflexively push it back to the user.** In order of preference:

- **The user handed you a video** (or pointed at a file/URL) → use it directly.
- **They didn't, but you have a capture tool** → record it yourself. For web UIs the usual way is a browser-automation tool's record function (e.g. the `agent-browser` CLI): drive the page to reproduce the interaction, record it, and take the resulting file. See `references/recording-tools.md` for capture options and the timing gotchas (triggering scroll-based animations, catching a full loop).
- **You have no way to capture a recording** → *then* ask the user — either to provide the file, or to give you a capture tool (install/enable one, share screen-recording access). This is the fallback, not the first move.

This skill's *scripts* don't record — capture is the upstream step, and it's yours to arrange whenever you can. Once you have a video file (`.mp4`, `.mov`, `.webm`, …), everything below turns it into frames you can read.

## Requirements & Preflight (check first)

The scripts need Python 3 and the `ffmpeg`/`ffprobe` CLIs. **Before extracting, run the preflight check:**

```bash
python3 <skill-path>/scripts/check_env.py
```

It prints JSON (`ready`, detected `os`, ffmpeg/ffprobe presence + versions, overlay capability, and OS-appropriate `install_options`) and exits 0 when ready, 1 when ffmpeg/ffprobe are missing.

**If ffmpeg is missing, do NOT silently install it.** Installing system packages changes the user's machine and is their call. Instead:

1. Tell the user ffmpeg isn't installed and show the command for their OS from `install_options` (e.g. macOS `brew install ffmpeg`, Debian/Ubuntu `sudo apt-get install -y ffmpeg`, Windows `winget install --id Gyan.FFmpeg -e`).
2. **Ask permission**, then run that command for them, or let them run it themselves.
3. Re-run `check_env.py` to confirm `ready: true`, then proceed.

`extract_frames.py` also guards this itself — if ffmpeg is absent it exits with the same OS-aware guidance rather than failing cryptically.

## How Frames Are Organised

Everything lives under a hidden home-directory folder, so frames and the source recording are never committed and never touch the project repo (there is no `.gitignore` to manage). The layout mirrors the codex-reviewer skill (project -> date -> session):

- A **session** is one inspection subject: a page section, a flow, a component. Start a new session per subject (see step 1). The project bucket is derived from git automatically.
- Each **pass** over that subject is its own timestamped subfolder inside the session: an overview contact sheet, or a drill-in frame extraction. Running the sheet several times, or a sheet then an extraction, just adds more timestamped folders, and the `HHMMSS` prefixes read in the order you ran them.
- Each pass folder is **self-contained**: it keeps a copy of the source recording it operated on, so the session root stays clean (only `session.json` and pass folders) and no recording is left loose. Record to a scratch/temp location *outside* the session directory; the scripts copy the source in for you. For a very large source, opt out with `--no-copy-video`.

```
~/.video-inspector/<project>/<YYYY-MM-DD>/<HHMMSS-title>/   # session = one subject
  session.json
  <HHMMSS-slug>-sheet/            # a contact sheet (overview pass)
    source.<ext>                  # persisted copy of the source recording
    contact-sheet.jpg             # ONE montage image of the whole timeline
    manifest.json                 # grid layout + cell -> timestamp map
  <HHMMSS-video-slug>/            # a frame extraction (drill-in pass)
    source.<ext>                  # persisted copy of the source recording
    manifest.json                 # extraction params + full frame list
    frames/
      frame_00001_t0.000s.jpg     # index + ABSOLUTE source timestamp in the name
      frame_00002_t1.000s.jpg
      ...
```

A contact sheet tiles sampled frames into a single image in reading order
(left-to-right, top-to-bottom) from the window start. Its `cells` array maps
each tile to its exact timestamp, so even without a burned-in label you know
what time any tile is.

**Every frame's filename carries its exact source timestamp** (`frame_<index>_t<seconds>s`). That is the authoritative label: reading frames in filename order walks the video forward in time, and the gap between two timestamps is the real elapsed time. An optional burned-in overlay (on by default) also prints the time onto the frame as a visual aid — but it needs an ffmpeg built with the `drawtext` filter and a usable font. A stock Homebrew `ffmpeg` often lacks `drawtext`; when it's unavailable the overlay is skipped automatically (a `note` says so) and the filenames remain the source of truth, so nothing breaks. `check_env.py` reports `overlay.available` up front.

## Workflow

### 1. Initialise a session

```bash
python3 <skill-path>/scripts/init_session.py --title <title> [--project <name>]
```

Returns JSON with `session` (the path to track) and `session_dir`. Inside a git repo the project name is derived from the repo automatically (shared across worktrees), so **omit `--project`**; outside a repo it defaults to the current directory's name, or pass `--project` to override. Store the `session` path for the next step.

**One session per subject; reuse it for every pass over that subject.** A session groups everything you do to one thing you are inspecting: the overview sheet, any drill-in extractions, and the same UI at another viewport (e.g. desktop then mobile) all belong in one session, each as its own timestamped pass folder. Start a *new* session (run this step again) only when you move to a genuinely different subject - another section, another flow. When unsure, start a new one: it is cheap and keeps `list_sessions` rediscovery clean.

### 2. Overview: build and read a contact sheet (cheapest first pass)

```bash
python3 <skill-path>/scripts/contact_sheet.py --session <session> --video <path> [options]
```

With no options it samples **one frame per second** (thinned to fit a single 40-cell sheet) and tiles them into ONE `contact-sheet.jpg`. Read that single image. In one picture you can follow the whole timeline — overall staging, what changes, roughly when, and whether anything janks — for the token cost of one frame instead of dozens. The JSON output carries the grid (`columns`, `rows`), `effective_fps`, `interval_seconds`, and a `cells` array mapping each tile (in reading order) to its exact timestamp.

**This is almost always the right first step.** Only skip straight to extraction when you already know the exact short moment you care about.

Contact-sheet options:

| Option | Default | Use when |
|---|---|---|
| `--fps <n>` | `1.0` | Denser timeline (higher) or sparser (lower); thinned to `--max-cells` |
| `--start <s>` / `--end <s>` | whole video | Sheet just one region of a long clip |
| `--max-cells <n>` | `40` | More tiles per sheet (denser, less legible) |
| `--columns <n>` | `5` | Grid width |
| `--cell-width <px>` | `320` | Bigger tiles to read small text in thumbnails |
| `--label <name>` | source filename | Name the sheet subfolder meaningfully |
| `--no-copy-video` | copies source in | Skip persisting the source into the sheet folder (very large files) |

### 3. Drill in: extract full-resolution frames where it matters

```bash
python3 <skill-path>/scripts/extract_frames.py --session <session> --video <path> [options]
```

Once the sheet shows you *where* the interesting moment is, extract that window at full size. With no options it samples one frame per second capped at 60 frames at 1280px wide; the real power is narrowing to a window: `--start 3 --end 5 --fps 4` gives eight crisp frames of a two-second transition. It returns JSON with `frame_count`, `effective_fps`, `interval_seconds`, `downsampled`, the `window`, and a `frames` array of `{index, timestamp, path}` in order.

Key options (override only when the default doesn't fit):

| Option | Default | Use when |
|---|---|---|
| `--fps <n>` | `1.0` | Finer timing (`--fps 4` on a short window) or coarser (`--fps 0.5` = one every 2s) |
| `--start <s>` / `--end <s>` | whole video | Zoom into one moment — combine with a higher `--fps` |
| `--max-frames <n>` | `60` | Raise deliberately if you truly need more stills in one pass (costs context) |
| `--max-width <px>` | `1280` | Raise to read small UI text/numbers; `0` disables scaling |
| `--format jpg\|png\|webp` | `jpg` | `png` for crisp text/screenshots |
| `--label <name>` | source filename | Name the video subfolder meaningfully |
| `--no-overlay` | overlay on | Skip the burned-in timestamp (filenames still carry it) |
| `--no-copy-video` | copies video | Skip persisting a copy (large files, or you'll keep the original) |

**Auto-fit to the cap:** if the requested rate over the window would exceed `--max-frames`, the script lowers the rate to fit and reports the `effective_fps` and `interval_seconds`, so the agent always knows the true spacing. Read the `notes` array; it flags downsampling and coarse intervals.

### 4. Read the frames and reason

Read the frame images in `frames` order (you can read several in one turn). The timestamp in each filename tells you *when* in the video that still is, so you can describe timing ("the modal finishes opening between t2.0s and t3.0s"), spot missing intermediate states, and judge motion. If something happens between two frames that you can't resolve, drill into that window at higher fps. Each extraction lands in its own subfolder, so the overview sheet and every detail pass coexist for reference.

**Mind the budget as you go.** If you find yourself about to read more than ~10–12 full frames, stop and ask whether a contact sheet would answer the question instead. Reserve full-frame reads for moments where you genuinely need to see fine detail (small text, exact motion between two instants).

## Discovering Past Sessions

```bash
python3 <skill-path>/scripts/list_sessions.py [--project <name>] [--date today|yesterday|YYYY-MM-DD] [--from ... --to ...] [--week] [--month]
```

Returns matching sessions and the videos processed in each. Use it from a fresh conversation to find a prior inspection and re-read its frames or manifest.

## Cleanup (User-Initiated Only)

```bash
python3 <skill-path>/scripts/cleanup_session.py --session <session>
```

Deletes the whole session directory (all frames, copied videos, manifests) and prunes empty parents. Frames and copied videos take real disk space, so cleanup is useful — but **only run it when the user explicitly asks.** They may want to revisit an inspection later; a completed review is not a reason to delete.

## Notes for the Agent

- **This skill is agent-agnostic.** The scripts are plain Python + ffmpeg with no dependency on any specific coding agent; Codex or another agent can invoke them the same way. Only this SKILL.md is Claude-facing.
- **Resolve `<skill-path>` at runtime** — it's this skill's own directory. The scripts import sibling modules, so run them by path (`python3 <skill-path>/scripts/<name>.py`); the script's directory is placed on `sys.path` automatically.
- **Mind the context budget.** Each full frame is an image the model must read, so many frames is a large token cost. Prefer the **contact-sheet overview first**, then targeted full-resolution drill-ins, over reading a big pile of frames. A whole 30s timeline fits in one sheet; you rarely need more than a handful of full frames after that.
- For how videos get recorded in the first place (browser automation, screen capture, Playwright, etc.), see `references/recording-tools.md`.
