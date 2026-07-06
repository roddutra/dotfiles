# Recording a Video to Inspect

**Getting the recording is the agent's job first.** If the user handed you a
video, use it; otherwise **record it yourself** with whatever capture tool you
have, rather than reflexively asking the user to produce one. Only fall back to
asking the user — for the file, or for a capture tool you can use — when you
genuinely have no way to record. The skill's scripts turn a finished recording
into frames; capturing that recording is the upstream step, and this reference
lists ways to do it. Any tool that outputs a standard video file (`.mp4`,
`.mov`, `.webm`) works; pass its path to `contact_sheet.py` /
`extract_frames.py`.

**Save the recording to a scratch/temp path outside the session directory**,
not into the session folder itself. The pass scripts copy the source into
their own timestamped pass folder, so the recording ends up nested and the
session root stays clean (just `session.json` and pass folders). If you write
the raw recording into the session root by hand, it sits there loose.

## Browser automation (primary example)

The most common source for UI/animation inspection is a browser-automation
tool driving a real Chrome session and recording it. The `agent-browser`
skill is one such tool: it controls a Chrome session, interacts with the page
(navigate, click, hover, type), and has a **record** function that captures
the session to a video file. The typical flow is:

1. Use the browser agent to reproduce the interaction you want to inspect —
   navigate between pages, click the button, open the dropdown or modal, or
   trigger the animation.
2. Start/stop its recording around that interaction.
3. Take the resulting video path and run this skill on it:
   `init_session.py` → `extract_frames.py --video <that path>`.

This skill deliberately does **not** depend on `agent-browser` — it is only a
convenient upstream. Substitute any equivalent (Playwright, Puppeteer,
Selenium with a recorder, a manual screen capture) and the rest is identical.

## Other ways to produce a recording

- **Playwright** records video per context: set
  `recordVideo: { dir: 'videos/' }` on `browser.newContext(...)`; the `.webm`
  is finalised when the context closes. Good for deterministic, scripted flows.
- **Puppeteer** via `puppeteer-screen-recorder`, or Chrome's tracing/screencast.
- **macOS**: QuickTime Player (File → New Screen Recording), or
  `screencapture -v out.mov` for a headless screen capture, or ffmpeg with the
  `avfoundation` input.
- **Linux**: ffmpeg with `x11grab`/`kmsgrab`/`pipewire`, or OBS Studio.
- **Windows**: the Xbox Game Bar capture, OBS Studio, or ffmpeg with `gdigrab`.

Record the **shortest clip that contains the interaction**. This skill's
default is one frame per second with a 60-frame cap, so a tight 10–30 second
clip of just the flow you care about gives the cleanest, cheapest inspection.
A long recording forces the sampler to thin frames out (it will tell you it
did), which can miss fast transitions.

## Triggering and duration (learned from real use)

Two things decide whether a recording is actually useful: catching the
animation from its *start*, and recording *long enough*.

- **Scroll- or viewport-triggered animations** (very common — components that
  animate when they enter the viewport via `IntersectionObserver`): the
  animation resets to frame one each time the element scrolls into view. So
  **start the recording while the element is still off-screen, then scroll it
  into view.** If you scroll first and record second, you miss the opening and
  may catch it mid-loop. Concretely, with a browser tool: open the page at the
  top, `record start`, scroll the target element into view, hold, `record stop`.

- **Looping animations: record at least one full loop.** If you don't know the
  loop length, either read the component's timing source, or just record
  generously (e.g. 30–40s) and let the contact sheet reveal the loop boundary —
  then re-inspect a single clean loop with `--start`/`--end`.

- **Two elements that loop at different lengths drift out of phase.** If a
  section has two animated pieces side by side with different loop durations,
  they are never showing the same moment at the same time. A contact sheet makes
  this obvious at a glance (the two columns visibly desync down the grid) in a
  way that clicking through separate frames does not.

- **Hold with the recorder running.** Some browser-automation `wait` commands
  cap at ~25s; chain a few (`wait 8000` ×4) to hold ~30s+ while the animation
  plays, then stop.

- **Keep commands to a minimum while the recording is live.** Keep the browser
  headed so you can watch it record (that is the point) - but the capture is
  driven by a CLI where each command reconnects to the browser, and firing many
  commands during an active recording can make the visible window thrash (the
  viewport re-asserting between sizes) and can jank the captured scroll. So
  drive the whole in-recording journey from ONE injected script rather than a
  loop of separate scroll/wait calls: a single `eval` that steps through the
  sequence on a timer, then one `wait` covering its duration, then `stop`. For a
  multi-section scroll-through, for example:

      agent-browser eval "(async () => { for (const y of [0,900,1800,2700,3600]) { window.scrollTo({top:y}); await new Promise(r=>setTimeout(r,4000)); } })()"
      agent-browser wait 20000    # cover the script's total run time
      agent-browser record stop

  Fewer mid-recording commands means a steadier window and smoother motion in
  the video. The fix is minimising commands, not hiding the browser.

- **Set the viewport on the recording context, then verify the output.** A
  recorder may spin up a *fresh* browser context when it starts (e.g.
  `agent-browser record start <path> [url]` does), so a viewport you set
  earlier can be silently dropped and the clip comes out at some default size.
  Set the viewport *before* starting the recording (and again just after, if
  the tool allows), then confirm with `ffprobe -select_streams v:0
  -show_entries stream=width,height`. If the dimensions aren't what you asked
  for, re-record before extracting anything.

- **Confirm you captured the right thing, cheaply.** Aim by the section's real
  DOM anchor (heading, id), not by a label you see on screen. Card sub-labels
  and split text nodes often don't match, and scrolling to the wrong node
  frames a neighbouring section. You don't have to trust the scroll blind: the
  contact sheet's first cells show what actually landed on screen, so a bad aim
  costs one sheet read, not a full frame extraction. Re-record if it's wrong.

- **Content taller than the viewport (mobile / stacked layouts).** When the
  thing you're inspecting doesn't fit one screen -- a desktop side-by-side that
  stacks vertically on mobile, a long form, two animations that each fill the
  viewport -- you can't hold still and catch all of it. Two options:
  - **Scroll-through (one clip).** Measure each sub-element's `y` first, then
    hold on the first, scroll the next into view (which also re-triggers a
    viewport-gated animation from stage 1), hold, and so on. This is efficient,
    but the frame's *content position jumps* when you scroll, so read a jump in
    the contact sheet as your scroll, not an animation step. A persistent
    on-screen label per element (or the burned-in timestamp when available)
    keeps the phases unambiguous.
  - **Per-element clips.** Record each sub-element as its own short recording
    and inspect them separately. Cleaner per-element timelines with no scroll
    to reason around; use it when the elements animate independently and you
    want each one's timing isolated.

- **Cell legibility tracks aspect ratio.** Tall, narrow frames (mobile
  portrait) stay readable in a contact sheet because they lose little when
  scaled to the cell width; wide desktop frames crammed into the same cell lose
  fine text. If a wide frame's labels are unreadable in the sheet, raise
  `--cell-width`, or crop/record just the region of interest.

## Tips for a clean inspection

- **Frame rate of the source doesn't need to be high.** The sampler pulls
  frames at its own rate, so a 30 fps or 60 fps recording is fine; you are not
  limited by it and you don't benefit from it beyond smoothness.
- **Resolution helps for reading UI text.** If you need the agent to read
  small labels or numbers in the UI, record at a decent resolution and raise
  `--max-width` (or set `--format png`) when extracting, rather than recording
  tiny.
- **Isolate the moment.** If only one transition matters, record just that.
  Otherwise record the whole flow and use `--start`/`--end` to zoom in.

## Advanced: scene-change sampling (not built in)

This skill samples at uniform time intervals so the spacing between frames is
predictable and the agent can reason about elapsed time. For discrete UI
changes (page A → page B, closed → open), *scene-change* extraction can be
more frame-efficient — ffmpeg's `select='gt(scene,0.3)'` filter emits a frame
only when the image changes substantially. It is intentionally left out of the
default workflow because it breaks the uniform-timing guarantee, but it is a
reasonable manual technique when you want just the "before/after" of each
transition and don't care about even spacing.
