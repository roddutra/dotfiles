# Voxtype Dictation

Voxtype provides local speech recognition with an optional Groq cleanup profile. The primary shortcuts use Groq cleanup; secondary shortcuts keep raw local transcription available.

## Shortcut contract

| Shortcut | Mode |
|---|---|
| `SUPER + CTRL + X` | Toggle dictation with Groq cleanup |
| Hold `F9` | Push-to-talk with Groq cleanup |
| `SUPER + CTRL + SHIFT + X` | Toggle raw dictation |
| Hold `F10` | Raw push-to-talk |

The personal bindings are defined in `packages/omarchy/hypr/.config/hypr/bindings.lua`. Omarchy owns the stock raw bindings on `SUPER + CTRL + X` and `F9`, so the personal configuration explicitly unbinds and replaces them.

## Data flow

The `groq_cleanup` profile follows this path:

1. Voxtype records audio and transcribes it locally with Parakeet.
2. Voxtype pipes the current transcript to `voxtype-groq-cleanup`.
3. `voxtype-prepare-transcript` applies deterministic word replacements and builds the dictionary context.
4. `voxtype-groq-cleanup` sends the cleanup prompt, dictionary, and prepared transcript to Groq.
5. The cleaned text is pasted into the focused application.

Raw dictation skips steps 2 through 4. The cloud path sends only the current transcript, cleanup prompt, and dictionary. It does not send audio or previous transcripts.

## Progress notification

`voxtype-progress` runs as `voxtype-progress.service`, a user unit bound to `voxtype.service`. It follows `voxtype status --follow` and keeps one notification on screen from recording stop until output:

1. `🦜 Recording Stopped`, `Transcribing... Ns`
2. `✨ Groq Cleanup`, `Cleaning up transcript... Ns` (Groq profile only)
3. One outcome:
   - `✅ Done`, shown when text was output
   - `⚠️ Groq Cleanup Failed`, with the reason, shown when Groq failed and the raw transcript was used
   - `No Transcript`, shown when nothing was transcribed

Voxtype's own `on_recording_stop` and `on_transcription` notifications are disabled so toasts do not stack.

Stages are marker files in `$XDG_RUNTIME_DIR/voxtype-progress`, written with `voxtype-progress mark <stage> [detail]`:

- `groq`: written by `voxtype-groq-cleanup` when it starts
- `failed`: written by `voxtype-groq-cleanup` on a nonzero exit, with the error as detail
- `output`: written by Voxtype's `pre_output_command`

Omarchy shell constraints:

- Voxtype 1.0.1 posts `Transcribing...` with a 2 second expiry, which the shell raises to its 8 second minimum. Long recordings take longer than that to transcribe.
- The shell restarts a toast's countdown when its body changes. The per-second counter keeps the progress toast visible.
- The shell ignores `CloseNotification` and keeps the toast until its countdown ends. The watcher replaces the toast with the outcome instead of closing it.

## Tracked files

| File | Responsibility |
|---|---|
| `packages/omarchy/voxtype/.config/voxtype/config.toml` | Voxtype and `groq_cleanup` profile configuration |
| `packages/omarchy/voxtype/.config/voxtype/word-replacements.txt` | Deterministic transcription corrections |
| `packages/omarchy/voxtype/.config/voxtype/personal-dictionary.txt` | Terms supplied to Groq as constrained context |
| `packages/omarchy/voxtype/.config/voxtype/groq-cleanup-prompt.txt` | Cleanup behavior and output contract |
| `packages/omarchy/voxtype/.local/bin/voxtype-prepare-transcript` | Local replacement and dictionary preparation |
| `packages/omarchy/voxtype/.local/bin/voxtype-groq-cleanup` | Groq request, validation, and cleaned output |
| `packages/omarchy/voxtype/.local/bin/voxtype-progress` | Progress notification watcher and stage markers |
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

The cleanup prompt preserves meaning, removes speech disfluencies, resolves self-corrections, fixes punctuation and casing, and returns only the cleaned transcript. Dictated instructions are treated as text to clean, not instructions for the cleanup model to execute.

Current request defaults:

- Endpoint: `https://api.groq.com/openai/v1/chat/completions`
- Model: `openai/gpt-oss-120b`
- Temperature: `0`
- Reasoning effort: `low`
- Completion limit: `4096` tokens
- Curl deadline: `12` seconds
- Voxtype post-processing deadline: `15` seconds

The cleanup command accepts output only when Groq returns a non-empty string with `finish_reason` equal to `stop`. Missing files, invalid replacement configuration, transport errors, truncated responses, and malformed responses return a nonzero status. Voxtype then retains the raw transcript instead of inserting partial or unverified output, and the progress notification reports the failure.

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

`VOXTYPE_GROQ_API_KEY_FILE`, `VOXTYPE_GROQ_API_URL`, `VOXTYPE_GROQ_MODEL`, `VOXTYPE_GROQ_PROMPT_FILE`, `VOXTYPE_REPLACEMENTS_FILE`, `VOXTYPE_DICTIONARY_FILE`, and `VOXTYPE_PREPARE_COMMAND` override the defaults for diagnostics.

## Restore

On an Omarchy workstation:

1. Run `./scripts/bootstrap-omarchy` to install `voxtype-bin` and the other curated packages.
2. Run `./scripts/apply-dotfiles` to link the managed Voxtype directory and helper commands.
3. Restore the Groq key at the machine-local path above.
4. Run `systemctl --user enable --now voxtype.service voxtype-progress.service`.
5. Run `hyprctl reload` and confirm `hyprctl configerrors` is empty.

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
