# Voxtype Dictation

Voxtype provides local speech recognition with an optional Groq cleanup profile. The primary shortcuts use Groq cleanup; secondary shortcuts keep raw local transcription available.

Recordings stop automatically after 6.5 minutes (`max_duration_secs = 390`) and transcribe what was captured. `voxtype-progress` counts down the last minute. The reasons are under [Recording limit](#recording-limit).

## Shortcut contract

| Shortcut | Mode |
|---|---|
| `SUPER + CTRL + X` | Toggle dictation with Groq cleanup |
| Hold `F9` | Push-to-talk with Groq cleanup |
| `SUPER + CTRL + SHIFT + X` | Toggle raw dictation |
| Hold `F10` | Raw push-to-talk |
| `SUPER + ALT + X` | Cancel the recording or transcription in progress |

Cancel discards the audio and outputs nothing. Voxtype 1.1.0 does not check for it while the Groq cleanup command runs, so a cancel during that stage still pastes the text.

The personal bindings are defined in `packages/omarchy/hypr/.config/hypr/bindings.lua`. Omarchy owns the stock raw bindings on `SUPER + CTRL + X` and `F9`, so the personal configuration explicitly unbinds and replaces them.

## Data flow

The `groq_cleanup` profile follows this path:

1. Voxtype records audio and transcribes it locally with Parakeet.
2. Voxtype pipes the current transcript to `voxtype-groq-cleanup`.
3. `voxtype-prepare-transcript` applies deterministic word replacements and builds the dictionary context.
4. `voxtype-groq-cleanup` sends the cleanup prompt, dictionary, and prepared transcript to Groq.
5. The cleaned text is pasted into the focused application.

Raw dictation skips steps 2 through 4. The cloud path sends only the current transcript, cleanup prompt, and dictionary. It does not send audio or previous transcripts.

## Recording limit

Investigated on 12 October 2026 with Voxtype 1.1.0 (parakeet-rs 0.3.5), after a 652-second dictation produced no output. Re-open this only when a Voxtype release changes one of the findings below.

Current settings and what they cost:

| Setting | Value | Reason |
|---|---|---|
| `[audio] max_duration_secs` | `390` | Stays under the Parakeet limit |
| `[parakeet] on_demand_loading` | `true` | The daemon idles at about 30 MB of RAM |
| `[parakeet] model` | `parakeet-tdt-0.6b-v3` | The int8 model drops speech |
| `[whisper] eager_processing` | `false` | Has no effect with on-demand loading |
| `[parakeet] streaming` | `false` | Skips Groq cleanup and types while recording |

### Findings

- **Parakeet fails on a pass longer than about 400 seconds.** The ONNX encoder accepts at most 5,001 frames of 80 ms. Longer audio fails with `Attempting to broadcast an axis by a dimension other than 1`. Voxtype then outputs nothing and keeps no audio. `voxtype transcribe` fails the same way, as does `parakeet-unified-en-0.6b`. Upstream: [peteonrails/voxtype#288](https://github.com/peteonrails/voxtype/issues/288), open since 1 April 2026.
- **Voxtype does not chunk batch Parakeet audio.** No setting exists for it.
- **Eager processing needs a preloaded model.** `[whisper] eager_processing = true` transcribes fixed-size chunks during recording and applies to every engine despite its section. With `on_demand_loading = true` the model reaches the recording only at stop, so no chunk is dispatched and the whole recording goes through one pass.
- **A preloaded model is never unloaded.** Voxtype evicts idle Whisper models only. The full-precision Parakeet model holds 2.3 GB after loading and 3.1 GB after use.
- **Streaming types while recording.** `[parakeet] streaming = true` with `parakeet-unified-en-0.6b` has no length limit, but it types at the cursor every 0.56 seconds, splits words with spaces, bypasses post-processing (Groq cleanup and word replacements), discards text the model has not emitted yet when recording stops, needs a preloaded model, and breaks hold-to-talk bindings on Hyprland. Voxtype's default `streaming_*_secs` values fail validation ([peteonrails/voxtype#778](https://github.com/peteonrails/voxtype/issues/778)).
- **The int8 model drops speech on longer passes.** Words kept from the 652-second dictation, by pass length:

  | Pass length | `parakeet-tdt-0.6b-v3` | `parakeet-tdt-0.6b-v3-int8` |
  |---|---|---|
  | 25 s | 1,648 | 1,631 |
  | 60 s | 1,623 | 1,542 |
  | 120 s | 1,616 | 1,553 |
  | 300 s | 1,623 | 1,447 |

- **The full-precision model loads in about 5 seconds**, or about 40 seconds when its 2.4 GB file is not in the disk cache. On-demand loading runs during the recording, so only a short first dictation waits.
- **Handy has the same Parakeet limit** ([cjpais/Handy#2074](https://github.com/cjpais/Handy/issues/2074)); its chunking request ([cjpais/Handy#1332](https://github.com/cjpais/Handy/issues/1332)) was still open.

### Long recordings at the cost of idle RAM

These settings allow recordings up to `max_duration_secs` and were verified on recordings shorter than one chunk. Chunk joins were simulated only: a join repeated one or two words and added a full stop.

```toml
[audio]
max_duration_secs = 900

[whisper]
eager_processing = true
eager_chunk_secs = 300.0
eager_overlap_secs = 1.0

[parakeet]
on_demand_loading = false
```

`systemctl --user stop voxtype.service` frees the RAM when needed.

### What would lift the cap

- Voxtype chunking long Parakeet audio in the batch path (#288).
- Eager processing dispatching chunks once an on-demand model load finishes.
- Idle unloading for non-Whisper engines.

## Handy trial

Started 12 October 2026 to test whether [Handy](https://github.com/cjpais/Handy) 0.9.8 can lift the recording limit while keeping on-demand model loading. Voxtype stays the default until a 10 to 15 minute dictation has worked in Handy.

| Shortcut | Action |
|---|---|
| `F8` | Toggle dictation with Groq cleanup (`handy --toggle-post-process`) |
| `SHIFT + F8` | Toggle raw dictation (`handy --toggle-transcription`) |
| `CTRL + F8` | Cancel (`handy --cancel`) |

Setup. Handy's own files are not linked from this repository:

- `handy-bin` from the AUR. It is not in `manifests/omarchy/aur-packages.txt` until the trial passes.
- Model `parakeet-unified-en-0.6b` (Q8_0 GGUF, 731 MB) in `~/.local/share/com.pais.handy/models/`. It is a streaming model: Handy decodes it in bounded chunks during recording and pastes once at the end. On the RTX 3070 Ti it loads in 0.3 seconds and unloads after each transcription.
- Settings in `~/.local/share/com.pais.handy/settings_store.json`. Handy rewrites this file and stores the Groq API key in it as plain text, so it must not be committed. Edit it only while Handy is stopped.
- Handy starts hidden at login through `~/.config/autostart/Handy.desktop`, which it writes itself.
- The Groq key comes from the 1Password item `Groq`, field `OpenWhispr` in the `API keys` section.
- Idle, with the model unloaded, Handy and its WebKit processes hold about 280 MB of RAM. Voxtype idles at about 30 MB.

How the Voxtype configuration was carried over:

- Groq cleanup uses Handy's Custom provider pointed at `https://api.groq.com/openai/v1` with `qwen/qwen3.8-27b`. The built-in Groq provider does not send `reasoning_effort: none`; Custom does. Handy sets no temperature.
- The cleanup prompt is `groq-cleanup-prompt.txt` with the rules from `word-replacements.txt` and the entries from `personal-dictionary.txt` embedded, because Handy has no replacement table. Exact replacements therefore apply only on `F8`. Its self-correction rule is expanded with six examples and a guard for ordinary uses of "sorry", "actually" and "I mean". Across 55 test cases run four times each, that fixed 94% of self-corrections against 85% for the original rule, with no loss of kept content.
- Handy's fuzzy custom word list holds 28 distinctive terms with `word_correction_threshold` lowered from 0.18 to 0.08. At 0.18 it rewrote "just" to "Joust" 77 times across two weeks of transcripts, "cloud" to "Claude", and "part" to "PRD". "Joust", "Groq", "Nudge" and "Windmill" are left out because they collide with ordinary words or with "Grok".

Known limits found during setup:

- Handy's whole-file path (`handy --transcribe-file`, history retry, and the fallback when a stream returns nothing) ran out of GPU memory on an 11-minute file, needing a 5.1 GB buffer. Only the live streaming path can handle long recordings.
- CLI triggers are toggle only, so there is no hold-to-talk binding.
- Recordings are kept for two weeks in `~/.local/share/com.pais.handy/recordings/`.

Reference copies in `packages/omarchy/handy/`, which `scripts/apply-dotfiles` does not stow:

- `cleanup-prompt.txt`: the cleanup prompt as stored in Handy. `${output}` is Handy's transcript placeholder.
- `settings-overrides.json`: every setting changed from Handy's defaults, without the API key. `post_process_custom_base_url` is the `base_url` of the `custom` entry in `post_process_providers`, and `bindings` holds each binding's `current_binding`.

Update both copies after changing the prompt or settings in Handy. To restore, stop Handy, apply the values to `settings_store.json`, add the prompt to `post_process_prompts` with the id `voxtype_minimal_cleanup`, and set the Groq key under `post_process_api_keys.custom`.

To remove the trial: delete the three `F8` bindings in `bindings.lua`, run `yay -Rns handy-bin`, and delete `~/.local/share/com.pais.handy`, `~/.config/autostart/Handy.desktop`, and `packages/omarchy/handy/`.

## Progress notification

`voxtype-progress` runs as `voxtype-progress.service`, a user unit bound to `voxtype.service`. It follows `voxtype status --follow` and keeps one notification on screen from recording stop until output:

1. `🦜 Recording Stopped`, `Transcribing... Ns`, or `🦜 Recording Limit Reached` when the cap ended the recording
2. `✨ Groq Cleanup`, `Cleaning up transcript... Ns` (Groq profile only)
3. One outcome:
   - `✅ Done`, shown when text was output
   - `⚠️ Groq Cleanup Failed`, with the reason, shown when Groq failed and the raw transcript was used
   - `Dictation Cancelled`, shown when the cancel shortcut ended the transcription
   - `No Transcript`, shown when no speech was detected or transcription failed

Before that, the watcher warns that the recording cap (`audio.max_duration_secs`) is close:

- 60 seconds left: a chime (`message.oga`) and an `⏳ Recording Limit` toast that counts down each second
- 30 seconds left: a second chime (`dialog-warning.oga`)
- A recording cancelled during the countdown replaces the toast with `Dictation Cancelled`

The chimes come from `sound-theme-freedesktop` and play through `pw-play`. Voxtype has no setting for this warning.

Voxtype's own `on_recording_stop` and `on_transcription` notifications are disabled so toasts do not stack.

Stages are marker files in `$XDG_RUNTIME_DIR/voxtype-progress`, written with `voxtype-progress mark <stage> [detail]`:

- `groq`: written by `voxtype-groq-cleanup` when it starts
- `failed`: written by `voxtype-groq-cleanup` on a nonzero exit, with the error as detail
- `output`: written by Voxtype's `pre_output_command`
- `cancelled`: written by the cancel shortcut

Omarchy shell constraints:

- Voxtype 1.0.1 posts `Transcribing...` with a 2 second expiry, which the shell raises to its 8 second minimum. Long recordings take longer than that to transcribe.
- The shell restarts a toast's countdown when its body changes. The per-second counter keeps the progress toast visible.
- The shell ignores `CloseNotification` and keeps the toast until its countdown ends. The watcher replaces the toast with the outcome instead of closing it.

## OSD HUD

The [`blizl.voxtype-osd`](https://github.com/Blizl/Omarchy-VoxType-OSD) plugin replaces Voxtype's GTK overlay with a Quickshell HUD. Voxtype launches it from `~/.local/share/voxtype/quickshell/` because `[osd] frontend = "quickshell"`.

The plugin's `bin/setup` and `bin/uninstall` are not used. Setup refuses `config.toml` because the linked Voxtype directory resolves into this repository. Its changes are tracked here instead:

- `[osd]` settings in `config.toml`
- `SUPER + E` (engine picker) and `SUPER + M` (meeting controls) in `bindings.lua`

`scripts/bootstrap-omarchy` installs the HUD files with the plugin's `lib/qml-installer.sh`. Do not use `voxtype setup quickshell --source` for this plugin: its fixed file list omits `ThemeReveal.qml`, `VadGate.qml`, and `WaveformMeter.qml`. Re-run the bootstrap after `omarchy plugin update` to refresh the installed HUD files.

## Tracked files

| File | Responsibility |
|---|---|
| `packages/omarchy/voxtype/.config/voxtype/config.toml` | Voxtype and `groq_cleanup` profile configuration |
| `packages/omarchy/voxtype/.config/voxtype/word-replacements.txt` | Deterministic transcription corrections |
| `packages/omarchy/voxtype/.config/voxtype/personal-dictionary.txt` | Terms supplied to Groq as constrained context |
| `packages/omarchy/voxtype/.config/voxtype/groq-cleanup-prompt.txt` | Cleanup behavior and output contract |
| `packages/omarchy/voxtype/.local/bin/voxtype-prepare-transcript` | Local replacement and dictionary preparation |
| `packages/omarchy/voxtype/.local/bin/voxtype-groq-cleanup` | Groq request, validation, and cleaned output |
| `packages/omarchy/voxtype/.local/bin/voxtype-progress` | Progress notification watcher, stage markers, and recording cap warning |
| `packages/omarchy/voxtype/.config/systemd/user/voxtype-progress.service` | User unit that runs the watcher alongside Voxtype |

`voxtype-bin` is restored from `manifests/omarchy/aur-packages.txt`.

## Stow ownership

`scripts/apply-dotfiles` applies the `voxtype` package with directory folding. This produces:

```text
~/.config/voxtype -> ~/dotfiles/packages/omarchy/voxtype/.config/voxtype
```

The directory link is required because Voxtype atomically replaces `config.toml` when saving configuration. An individual file symlink is replaced by a regular file and silently stops tracking changes.

Do not move `voxtype` into the normal `--no-folding` package list. Changes made by `voxtype configure` intentionally modify the tracked `config.toml`; review them with the normal repository diff workflow.

## Word replacements

Add observed transcription mistakes to `word-replacements.txt`:

```text
alias, alternate alias => ExactReplacement
```

Rules:

- Blank lines and lines beginning with `#` are ignored.
- Matching is case-insensitive and bounded at word characters.
- Longer aliases are matched first.
- One pass is performed, so replacements never cascade.
- The replacement is emitted with its configured spelling and casing.
- A repeated alias with a different target is a configuration error.
- Replacement targets are added to the dictionary before explicit dictionary entries, so replacement casing wins.

Use replacements for deterministic mistakes with an unambiguous correction. Do not use them where the same spoken form can legitimately mean different things.

## Personal dictionary

Add one preferred word, name, technical term, domain, or common phrase per line in `personal-dictionary.txt`. Blank lines and comments are ignored. Entries are deduplicated case-insensitively.

The dictionary is reference context, not a replacement list. The Groq prompt permits an entry only when the transcript provides evidence for it. Use the replacements file when a correction must be deterministic.

## Prompt and Groq request

The cleanup prompt asks for a minimal edit rather than a rewrite. It lists the only things the model may delete (fillers, repeated words, abandoned false starts, and explicitly corrected wording) and requires everything else, including asides, hedges, and requests, to stay in the speaker's words. It also fixes punctuation and casing, and returns only the cleaned transcript. Dictated instructions are treated as text to clean, not instructions for the cleanup model to execute.

`openai/gpt-oss-120b` condensed long dictation into summaries even with explicit "do not summarize" rules, dropping 30-50% of the words on 600-word transcripts. `qwen/qwen3.8-27b` with reasoning disabled keeps 94-97% and responds faster, so it is the primary model.

Current request defaults:

- Endpoint: `https://api.groq.com/openai/v1/chat/completions`
- Model: `qwen/qwen3.8-27b`, reasoning effort `none`
- Fallback model: `openai/gpt-oss-120b`, reasoning effort `low`
- Temperature: `0`
- Completion limit: `16384` tokens
- Curl deadline: `25` seconds per attempt
- Voxtype post-processing deadline: `60` seconds

If the primary request fails or returns an incomplete response, the command retries once with the fallback model. Accepted output is normalised to ASCII: en and em dashes become ` - ` (or `-` between digits), Unicode hyphens become `-`, and curly quotes become straight quotes. The models emit these characters on longer transcripts despite the prompt.

The cleanup command accepts output only when Groq returns a non-empty string with `finish_reason` equal to `stop`. Missing files, invalid replacement configuration, transport errors, truncated responses, and malformed responses from both models return a nonzero status. Voxtype then retains the raw transcript instead of inserting partial or unverified output, and the progress notification reports the failure.

The request headers and body use mode `600` files inside a mode `700` runtime directory. The directory is removed on exit. The API key and transcript are not passed in process arguments.

## Secret storage

The Groq API key is machine-local and must never be committed. Its default path is:

```text
${XDG_DATA_HOME:-$HOME/.local/share}/voxtype/secrets/groq-api-key
```

Create it without placing the key in shell history:

```sh
data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
install -d -m 700 "$data_home/voxtype/secrets"
read -rsp 'Groq API key: ' GROQ_API_KEY; printf '\n'
printf '%s' "$GROQ_API_KEY" > "$data_home/voxtype/secrets/groq-api-key"
unset GROQ_API_KEY
chmod 600 "$data_home/voxtype/secrets/groq-api-key"
```

`VOXTYPE_GROQ_API_KEY_FILE`, `VOXTYPE_GROQ_API_URL`, `VOXTYPE_GROQ_MODEL`, `VOXTYPE_GROQ_REASONING_EFFORT`, `VOXTYPE_GROQ_FALLBACK_MODEL`, `VOXTYPE_GROQ_FALLBACK_REASONING_EFFORT`, `VOXTYPE_GROQ_PROMPT_FILE`, `VOXTYPE_REPLACEMENTS_FILE`, `VOXTYPE_DICTIONARY_FILE`, and `VOXTYPE_PREPARE_COMMAND` override the defaults for diagnostics.

## Restore

On an Omarchy workstation:

1. Run `./scripts/bootstrap-omarchy` to install `voxtype-bin`, the other curated packages, the OSD plugin, and its HUD files.
2. Run `./scripts/apply-dotfiles` to link the managed Voxtype directory and helper commands.
3. Restore the Groq key at the machine-local path above.
4. Run `voxtype setup --download --model parakeet-tdt-0.6b-v3 --no-post-install` to fetch the model (2.4 GB).
5. Run `systemctl --user enable --now voxtype.service voxtype-progress.service`.
6. Run `hyprctl reload` and confirm `hyprctl configerrors` is empty.

## Validation

Validate replacements and inspect the prepared dictionary without contacting Groq:

```sh
printf '%s' 'check voice ink and lone dolphin' | \
  ~/.local/bin/voxtype-prepare-transcript \
  --replacements ~/.config/voxtype/word-replacements.txt \
  --dictionary ~/.config/voxtype/personal-dictionary.txt
```

Exercise the complete cloud path:

```sh
printf '%s' 'um check voice ink and lone dolphin' | ~/.local/bin/voxtype-groq-cleanup
```

Check runtime and linking:

```sh
systemctl --user status voxtype.service voxtype-progress.service
stat -c '%F %N' ~/.config/voxtype
omarchy menu keybindings --print
```

After changing `config.toml`, restart with `systemctl --user restart voxtype.service`; the progress watcher restarts with it. Prompt, replacement, and dictionary changes apply on the next Groq-cleaned transcription.
