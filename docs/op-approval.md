# 1Password approval alerts

Coding agents stall silently when a 1Password approval (SSH key use or the `op` CLI) goes unanswered: the prompt expires after about 60 seconds and the command fails. This feature tells Rod's phone that an agent is blocked, so he can tell it to retry when he is back. It is not a race against the 60-second prompt. While it waits, the agent keeps doing independent work and never retries on its own.

At most one push is sent per absence, however many agents block. Nothing is sent while Rod is at the PC.

The design and its history are in [`docs/specs/1password-approval-alerts.md`](specs/1password-approval-alerts.md).

## How it works

Three pieces, installed on Omarchy only, share one machine-local config:

- **The `op-approval-blocked` skill** (primary alert). A one-line rule in the shared global `AGENTS.md` tells every agent to load it, if installed, when a 1Password-backed command fails. The skill stops retries and runs `notify`, which reads presence and, if Rod is away, publishes an alert with the harness, project, location and a 4-character reference that the agent repeats in the chat.
- **The approval watcher** (presence and fallback). A windowless Quickshell instance run by a systemd user service. It publishes Rod's presence to a feed the skill reads, and watches for 1Password approval windows. When one expires while Rod is away and he has not come back within the grace period, it sends one generic fallback alert, for agents that never loaded the skill.
- **The shared claim** (`claim`). Both components take it under one lock immediately before publishing. It grants a push only if none was sent since Rod was last present, so the fallback is normally refused because the skill already alerted.

```text
1Password prompt expires (~60 s)
 ├─ agent: command fails -> skill -> notify -> claim -> push "Agent blocked" (with ref)
 └─ watcher: window lived >= 59 s, Rod not present
       -> wait 120 s -> Rod still not back -> claim -> push fallback
```

### Presence

| State | Meaning |
| --- | --- |
| `present` | Input within the last 60 s |
| `idle` | No input for 60 s |
| `away` | No input for 5 min |
| `locked` | The session is locked (`omarchy-hyprland-session-locked`, polled every 10 s, every 2 s while an approval is pending) |
| `unknown` | Watcher not running, feed older than 30 s, Hyprland not answering, or observations not valid yet |

Activity comes from one 5-second `IdleMonitor` (`ext-idle-notify` v2 input idleness, so idle inhibitors such as video playback are ignored). Idle and away are measured on the wall clock from the last real input. After the watcher starts or the PC resumes, presence reads `unknown` until 5 s pass without input, and cannot read `present` until real input is seen.

## Tracked files

The skill and its library follow the same per-tool split as `packages/common`: platform-specific skills and libraries live in `packages/<platform>/agents`, linked from `packages/<platform>/claude` and `packages/<platform>/codex`. All of it is Omarchy-only, so nothing installs on macOS.

| File | Responsibility |
| --- | --- |
| `packages/omarchy/agents/.agents/lib/op-approval/common.sh` | Config loading and validation, paths, label sanitiser, presence reader, lock |
| `packages/omarchy/agents/.agents/lib/op-approval/claim` | Shared alert claim (one push per absence) |
| `packages/omarchy/agents/.agents/lib/op-approval/locate` | Machine, harness, project and location for a PID |
| `packages/omarchy/agents/.agents/lib/op-approval/publish` | Fixed notification templates and the ntfy request |
| `packages/omarchy/agents/.agents/skills/op-approval-blocked/SKILL.md` | Agent procedure |
| `packages/omarchy/agents/.agents/skills/op-approval-blocked/scripts/{notify,presence,blocked}` | Skill scripts |
| `packages/omarchy/{claude/.claude,codex/.codex}/skills/op-approval-blocked` | Relative links to the skill for Claude Code and Codex |
| `packages/omarchy/agents/tests/` | Python contract tests for the library and skill (not stowed) |
| `packages/omarchy/op-approval-watcher/.local/bin/op-approval-watcher` | Finds the live Hyprland instance and starts Quickshell |
| `packages/omarchy/op-approval-watcher/.local/share/op-approval-watcher/shell.qml` | Watcher: presence feed, episodes, fallback |
| `packages/omarchy/op-approval-watcher/.local/share/op-approval-watcher/Policy.js` | Watcher decision rules (pure functions, tested under node) |
| `packages/omarchy/op-approval-watcher/.local/share/op-approval-watcher/requesters` | Lists processes that may be waiting on an approval window |
| `packages/omarchy/op-approval-watcher/.config/systemd/user/op-approval-watcher.service` | User unit, part of `graphical-session.target` |
| `packages/omarchy/op-approval-watcher/tests/` | Node tests for the watcher (not stowed) |
| `packages/common/agents/.agents/AGENTS.md` | Global rule: if the skill is installed, load it when a 1Password-backed command fails |
| `packages/common/codex/.codex/AGENTS.md`, `packages/common/pi/.pi/agent/AGENTS.md` | Links to the shared `AGENTS.md`, which carries all shared rules |

Runtime files, all mode 600 in mode 700 directories:

| Path | Contents |
| --- | --- |
| `$XDG_RUNTIME_DIR/op-approval/presence.json` | Presence feed, written by the watcher every 10 s and on change |
| `$XDG_RUNTIME_DIR/op-approval/last-alert` | Epoch of the last granted claim |
| `$XDG_RUNTIME_DIR/op-approval/lock` | Lock symlink, present only while a script holds it |
| `${XDG_STATE_HOME:-$HOME/.local/state}/op-approval/blocked.jsonl` | Index of blocked steps, one line per `notify` call |

The feed holds `machine`, `state`, `updated_at`, `updated_epoch`, `last_present_at` and, only while the watcher is confirming input, `activity_pending_until`.

## Machine-local configuration

`${XDG_CONFIG_HOME:-$HOME/.config}/op-approval/config.json` is never committed. Without `ntfy.url` and `ntfy.topic` nothing is published and `notify` reports `not_configured`. A minimal config:

```json
{
  "ntfy": { "url": "https://ntfy.example.com", "topic": "YOUR_NTFY_TOPIC" },
  "project_aliases": { "client-repo-name": "client-a" }
}
```

| Key | Default | Meaning |
| --- | --- | --- |
| `machine` | hostname | Label in alerts and the feed. Give each machine a distinct hostname or set this |
| `ntfy.url` | none | ntfy server base URL; the JSON body carries the topic |
| `ntfy.topic` | none | Topic, `[A-Za-z0-9_-]`, up to 64 characters |
| `project_aliases` | `{}` | Working-directory basename to the label shown on the lock screen |
| `alerts.when` | `expired` | `stopped`: the skill alerts only when the agent has stopped. The watcher fallback ignores it |
| `alerts.presence_states` | `["idle","away","locked","unknown"]` | States in which an alert may be sent. The watcher never sends while `present` |
| `alerts.once_per_absence` | `true` | At most one push until Rod has been present again |
| `alerts.rate_limit_seconds` | `300` | Minimum gap between pushes when the feed is unavailable or `once_per_absence` is `false` |
| `presence.present_seconds` | `60` | Input within this many seconds reads `present` |
| `presence.away_seconds` | `300` | No input for this long reads `away`. Must exceed `present_seconds` |
| `watcher.fallback` | `true` | Enables the watcher's fallback alert |
| `watcher.fallback_grace_seconds` | `120` | Wait after an expiry before the fallback |
| `watcher.expired_min_seconds` | `59` | Minimum window lifetime that counts as expired (measured: 59.8 to 59.9 s) |
| `watcher.confirm_seconds` | `1` | Delay before checking that a new 1Password window is still titled `1Password` |

Missing keys take their defaults silently. An invalid value takes its default with a warning on stderr (the scripts) or in the journal (the watcher). Scripts read the file on every run; the watcher re-reads it on change and every 30 s, and logs the values in force.

## ntfy token

The token lives at `${XDG_DATA_HOME:-$HOME/.local/share}/op-approval/secrets/ntfy-token` (mode 600, in a mode 700 directory). Each machine has its own token for the server's write-only user, so one machine can be revoked without touching the other.

`publish` accepts only `tk_` followed by letters and digits, and passes it to `curl` on stdin, never in arguments or the environment. Keep a copy of each machine's token in 1Password for recovery, but never read it with `op` at runtime: that would raise the very approval this feature reports.

### New machine: generate a token

The server issues nothing: a token is a random string that is declared in the server's configuration.

1. Generate it straight into the token file, so it never appears on screen or in shell history:

   ```sh
   data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
   install -d -m 700 "$data_home/op-approval/secrets"
   (umask 077; printf 'tk_%s\n' "$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom | head -c 29)" \
     > "$data_home/op-approval/secrets/ntfy-token")
   ```

   This matches ntfy's format (`tk_` plus 29 lowercase letters and digits). `ntfy token generate`, run where the server is installed, is an alternative.

2. Declare it on the server: append an entry for the write-only user to the server's token list and redeploy. With ntfy's declarative auth that is `NTFY_AUTH_TOKENS` (in this homelab, the ntfy stack's Komodo Environment):

   ```text
   ,YOUR_NTFY_USER:tk_...:desktop-<hostname>
   ```

   Copy the token with `wl-copy --trim-newline < "$data_home/op-approval/secrets/ntfy-token"` (`pbcopy <` on macOS), then clear it from clipboard history: Omarchy's clipboard plugin keeps one. Never edit or move an existing entry to another user: ntfy then refuses to start. Issue a new token instead.

3. Save a copy in 1Password, for example "ntfy desktop-<hostname> token".

Until the server has been redeployed, `notify` reports `failed` with HTTP 403.

### Existing machine: recover or re-enter a token

To recover a token for 1Password, copy it from the server's token list, or from this machine's token file:

```sh
wl-copy --trim-newline < "${XDG_DATA_HOME:-$HOME/.local/share}/op-approval/secrets/ntfy-token"
```

Paste it into 1Password, then clear it from clipboard history.

To write a known token back to the file (for example after a reinstall), enter it without echo:

```sh
data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
install -d -m 700 "$data_home/op-approval/secrets"
read -rsp 'ntfy token: ' NTFY_TOKEN; printf '\n'
(umask 077; printf '%s\n' "$NTFY_TOKEN" > "$data_home/op-approval/secrets/ntfy-token")
unset NTFY_TOKEN
```

### Revoke a token

Remove its entry from the server's token list and redeploy. Deleting it only in ntfy's database is undone at the next start.

## Restore on another Omarchy machine

1. Apply the packages with `./scripts/apply-dotfiles`. If an existing `~/.codex/AGENTS.md` or `~/.pi/agent/AGENTS.md` is a regular file, move it to a dated backup first; Stow refuses to replace it.

   If unrelated drift makes the full run abort, stow only these packages with the same flags:

   ```sh
   cd ~/dotfiles
   stow --dir packages/common --target "$HOME" --no-folding agents claude codex pi
   stow --dir packages/omarchy --target "$HOME" --no-folding agents claude codex op-approval-watcher
   ```

   Add `--simulate --verbose=1` to preview.

2. Generate and declare a token for this machine, as in [New machine: generate a token](#new-machine-generate-a-token).
3. Create `config.json` as in [Machine-local configuration](#machine-local-configuration).
4. Enable the watcher:

   ```sh
   systemctl --user daemon-reload && systemctl --user enable --now op-approval-watcher
   ```

5. Check `~/.agents/skills/op-approval-blocked/scripts/presence` reads a real state within a minute, and send a test push (see [Validation](#validation)).

## Phone

1. Install the **official ntfy iOS app**. A community fork never received the server's ntfy.sh wake-ups, so pushes never arrived.
2. Sign in to your server as the read-only phone user, and subscribe to the topic on that server.
3. Set iOS notification previews for the app to show only when unlocked.

Measured delivery to a locked iPhone: 11 to 14 s, on Wi-Fi and on mobile data over Tailscale.

## Reading state

```sh
journalctl --user -u op-approval-watcher -f              # watcher decisions
~/.agents/skills/op-approval-blocked/scripts/presence    # {"machine":..,"state":..}
~/.agents/skills/op-approval-blocked/scripts/blocked list
~/.agents/lib/op-approval/claim status                   # inputs of the next claim decision
```

The journal logs presence transitions, episode IDs, decisions and publish results. It never contains the token or window titles.

`blocked list` shows every `notify` call on this machine, oldest first: time, reference, machine, harness, project, location, category, state and result. Match the reference against the agent's chat.

## Validation

From the repository root:

```sh
python3 -m unittest discover -s packages/omarchy/agents/tests -p 'test_*.py'
node --test packages/omarchy/op-approval-watcher/tests/
```

`shellcheck` is not installed system-wide; run it through `uvx` (`SC1091` only notes that `common.sh` is sourced at runtime):

```sh
lib=packages/omarchy/agents/.agents/lib/op-approval
skill=packages/omarchy/agents/.agents/skills/op-approval-blocked/scripts
watcher=packages/omarchy/op-approval-watcher/.local
uvx --from shellcheck-py shellcheck -s sh -e SC1091 "$lib"/common.sh "$lib"/claim "$lib"/locate "$lib"/publish "$skill"/*
uvx --from shellcheck-py shellcheck "$watcher"/bin/op-approval-watcher "$watcher"/share/op-approval-watcher/requesters
```

Send one test push without taking the claim or writing the index (it does reach the phone):

```sh
~/.agents/lib/op-approval/publish --template fallback --identity '{"harness":"agent","project":"test"}'
```

It prints `{"result":"sent",...}`, `not_configured` with a reason, or `failed` with the curl exit code and HTTP status.

## Troubleshooting

### No push

- Check the phone runs the official ntfy app.
- Run `presence`. `present` means no push, by design. Excluded states in `alerts.presence_states` also send nothing.
- Run `claim status`. If `last_alert` is newer than the feed's `last_present_at`, this absence already had its push. The next one needs Rod back at the PC first.
- Closing a window makes Hyprland emit a synthetic input event about 10 ms later, so the approval window closing can look like Rod returning. The watcher holds any activity within 300 ms of a window or layer close and discards it unless input continues past 5.5 s. While it holds activity, the feed carries `activity_pending_until`; `notify` waits up to 7 s for it to clear and the claim refuses while it is there. The journal logs each held activity as discarded or confirmed.
- A `notify` result of `failed` with a curl error usually means the harness sandbox blocked the network. The agent reports it in the chat.

### No fallback from the watcher

The watcher counts a window as an approval only when all of these hold:

- class `com.onepassword.OnePassword`, title exactly `1Password` when it is checked one second after opening, and not changed away from `1Password` while the confirmation check runs (the main window, Quick Access and Settings all retitle)
- a requester exists: a client of the 1Password SSH agent socket, or an `op` process that started at most 5 s before the window opened

Polkit is never used: the `omarchy-polkit` layer is ignored, so unrelated `pkexec` or system-authentication dialogs cannot alert. The journal logs every 1Password window that did not qualify, with the reason but not the title.

Even for a confirmed approval, no fallback is sent when:

- the window closed before 59 s (answered, rejected or dismissed)
- Rod was present at expiry, or at any point during the grace period
- the window was already open when the watcher started (unknown age)
- the PC suspended during the grace period
- the skill already alerted during this absence

With several requesters at once, the fallback names the machine only.

### Presence stays `unknown`

Check `systemctl --user status op-approval-watcher`. Readers treat a feed older than 30 s as `unknown`, so a stopped watcher shows within 30 s. If Hyprland stops answering, the watcher writes `unknown` and exits, and systemd restarts it against the live instance.

## lerd and the linked AGENTS.md

`~/.codex/AGENTS.md` and `~/.pi/agent/AGENTS.md` are links into the tracked shared `AGENTS.md`, and lerd writes its block through symlinks. After any `lerd install`, `lerd mcp:enable-global` or `lerd update`, check:

```sh
git -C ~/dotfiles diff -- packages/common/agents/.agents/AGENTS.md
ls -l ~/.config/opencode/AGENTS.md    # must be absent or a symlink
```

Revert a lerd block with `git -C ~/dotfiles checkout -- packages/common/agents/.agents/AGENTS.md`. The lerd-only `~/.codex/AGENTS.md` that existed before the link is backed up at `~/.codex/AGENTS.md.pre-dotfiles-20261007`.

## Harness support

| Harness | Global rule | Skill | Verified (7 Oct 2026) |
| --- | --- | --- | --- |
| Claude Code | `~/.claude/CLAUDE.md` (link) | `~/.claude/skills/` link | Skill flow in the E2E tests |
| Codex | `~/.codex/AGENTS.md` (link) | `~/.codex/skills/` link | Rule, skill, `presence`, ntfy reached; auto-review allowed the request |
| Pi | `~/.pi/agent/AGENTS.md` (link) | `~/.agents/skills/` | Rule, skill, `presence`, ntfy reached |
| OMP | Loads `~/.agents/AGENTS.md` itself, so no link | `~/.agents/skills/` | Rule, skill, `presence`, ntfy reached |
| OpenCode | Not linked: by its docs it falls back to `~/.claude/CLAUDE.md` | Not checked | Not installed |
| Grok | Not checked | `~/.agents/skills/` through `[skills].paths` | Not checked |
