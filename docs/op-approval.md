# 1Password approval alerts

Coding agents stall silently when a 1Password approval goes unanswered: an SSH key use, an `op` CLI request, a mounted Environments `.env` read or an unlock. The prompt expires after about 60 seconds (or is cancelled earlier) and the command fails, or, for a `.env` read, returns an empty file. This feature tells Rod's phone that an approval was not given, so he can tell the agent to retry when he is back. It is not a race against the prompt. While it waits, the agent keeps doing independent work and never retries on its own.

At most one push is sent per absence, however many approvals fail. Nothing is sent while Rod is at the machine. It runs on Omarchy and on macOS with the same behaviour.

The design and its history are in [`docs/specs/1password-approval-alerts.md`](specs/1password-approval-alerts.md) (base) and [`docs/specs/1password-approval-alerts-macos.md`](specs/1password-approval-alerts-macos.md) (macOS, every approval type, shared core).

## How it works

Three pieces share one machine-local config:

- **The `op-approval-blocked` skill** (primary alert). A one-line rule in the shared global `AGENTS.md` tells every agent to load it, if installed, when a 1Password-backed command fails. The skill stops retries and runs `notify`, which reads presence and, if Rod is away, publishes an alert with the harness, project, location and a 4-character reference that the agent repeats in the chat.
- **The approval watcher** (presence and fallback). It publishes Rod's presence to a feed the skill reads, and watches for 1Password approvals. When one is not given while Rod is away and he has not come back within the grace period, it sends one fallback alert, for requesters that never loaded the skill (an agent without it, a dev server reading `.env`, a browser extension unlock).
- **The shared claim** (`claim`). Both take it under one lock immediately before publishing. It grants a push only if none was sent since Rod was last present, so the fallback is normally refused because the skill already alerted.

```text
1Password approval not given (expired ~60 s, or cancelled)
 ├─ agent: command fails -> skill -> notify -> claim -> push "Agent blocked" (with ref)
 └─ watcher: episode not given, Rod not present
       -> wait 120 s -> Rod still not back -> claim -> push fallback
```

### One engine, two hosts

Every watcher decision lives in two shared files, `Engine.js` (episodes, outcome rule, grace period, fallback, schedules) and `Policy.js` (thresholds, presence, config, log signatures, window rules). Each platform has a host that only translates its signals into engine events and carries out the effects the engine returns:

| | Omarchy | macOS |
| --- | --- | --- |
| Host | Quickshell (`shell.qml`), systemd user unit | Swift with JavaScriptCore, LaunchAgent |
| Approval windows | Hyprland window events; class `com.onepassword.OnePassword`, title exactly `1Password` | Window list: a new 1Password window at layer 101, 400 wide (the system Touch ID dialog would also count right after 1Password logs an unlock request, but see the log row) |
| Input | `IdleMonitor`, 5 s | HID idle time, polled every 250 ms |
| Lock | `omarchy-hyprland-session-locked` | Session dictionary and lock notifications |
| Session | `hyprctl version` (lost: exit and restart) | On the console or not |
| 1Password log | `tail -F ~/.config/1Password/logs/1Password_rCURRENT.log` (path not yet confirmed) | Not read: macOS blocks background processes from other apps' data, and the watcher deliberately holds no Full Disk Access (see [below](#macos-without-1passwords-log)) |
| Requesters | `ss` and `/proc` | `lsof` and `ps` |
| Logs | `journalctl --user -u op-approval-watcher` | `/usr/bin/log show --info --predicate 'subsystem == "op-approval-watcher"'` |

Neither host needs a privacy permission.

#### macOS without 1Password's log

1Password's log lives in its Group Container, which macOS only lets a background process read with Full Disk Access. The watcher does not hold it: Full Disk Access would extend to every script it runs and every rebuild of its sources, all writable by Rod, so any code running as Rod (a compromised dependency, a prompt-injected agent) could use the watcher to read Mail, Messages and other apps' data. Without the log:

- an unanswered browser extension unlock is not detected (its Touch ID dialog cannot be tied to 1Password)
- an approval with no requester to identify (an Environments read whose reader already exited) is reported as "1Password approval not given", without its type
- expiries and cancellations are still caught by the lifetime and no-input rules

The watcher logs once that the log is not readable. A separate fixed-function log reader with its own grant could restore the first two if they turn out to matter.

### When an approval counts as not given

A confirmed approval window (an **episode**) is not given when any of these holds; otherwise it was answered:

1. 1Password logged a timeout or a cancellation while it was open (for example `ssh authorization prompt timed out`, or the cancellation when a locked screen's display turns off, about 20 s in)
2. it was open for at least `watcher.expired_min_seconds` (59 s)
3. input was observed for its whole lifetime and none came while it was open (answering needs a click, a key or Touch ID)

Rule 1 needs 1Password's log, which only the Omarchy watcher can read; on macOS rules 2 and 3 decide.

Overlapping episodes count as one. Requesters are looked up only to name the process and project in the fallback; an approval counts without one.

### Presence

| State | Meaning |
| --- | --- |
| `present` | Input within the last 60 s |
| `idle` | No input for 60 s |
| `away` | No input for 5 min |
| `locked` | The session is locked (polled every 10 s, every 2 s while an approval is pending) |
| `unknown` | Watcher not running, feed older than 30 s, session lost or not on the console, or observations not valid yet |

Idle and away are measured on the wall clock from the last real input. Video playback, `caffeinate` and other idle inhibitors do not count as input; remote control (VNC, Screen Sharing) does. After the watcher starts, a resume or a wake, presence reads `unknown` until 5 s pass without input, and cannot read `present` until real input is seen.

## Tracked files

| File | Responsibility |
| --- | --- |
| `packages/common/agents/.agents/lib/op-approval/common.sh` | Config loading and validation, paths, label sanitiser, presence reader, lock |
| `packages/common/agents/.agents/lib/op-approval/claim` | Shared alert claim (one push per absence) |
| `packages/common/agents/.agents/lib/op-approval/locate` | Machine, harness, project and location for a PID |
| `packages/common/agents/.agents/lib/op-approval/platform/{linux,darwin}.sh` | `locate`'s per-OS process facts and app part |
| `packages/common/agents/.agents/lib/op-approval/publish` | Fixed notification templates and the ntfy request |
| `packages/common/agents/.agents/skills/op-approval-blocked/` | Agent procedure (`SKILL.md`) and its scripts `notify`, `presence`, `blocked` |
| `packages/common/{claude/.claude,codex/.codex}/skills/op-approval-blocked` | Links to the skill for Claude Code and Codex |
| `packages/common/agents/tests/test_op_approval.py` | Python contract tests for the library and skill (not stowed) |
| `packages/common/op-approval-watcher/.local/share/op-approval-watcher/{Engine,Policy}.js` | Shared watcher logic |
| `packages/common/op-approval-watcher/tests/` | Engine scenarios and policy tables, under node (not stowed) |
| `packages/omarchy/op-approval-watcher/` | Omarchy host: `shell.qml`, `requesters`, the start wrapper and the systemd unit |
| `packages/macos/op-approval-watcher/` | macOS host: `host/*.swift`, `requesters`, the build-and-start wrapper and the LaunchAgent |
| `packages/common/agents/.agents/AGENTS.md` | Global rule: if the skill is installed, load it when a 1Password-backed command fails |

Runtime files, all mode 600 in mode 700 directories. The runtime directory is `$XDG_RUNTIME_DIR/op-approval/` on Linux and `$(getconf DARWIN_USER_TEMP_DIR)op-approval/` on macOS (never `$TMPDIR`, which a sandboxed harness may change). `OP_APPROVAL_RUNTIME_DIR` overrides it; the test suites use that.

| Path | Contents |
| --- | --- |
| `<runtime>/presence.json` | Presence feed, written by the watcher every 10 s and on change |
| `<runtime>/last-alert` | Epoch of the last granted claim |
| `<runtime>/lock` | Lock symlink, present only while a script holds it |
| `${XDG_STATE_HOME:-$HOME/.local/state}/op-approval/blocked.jsonl` | Index of blocked steps, one line per `notify` call |
| `${XDG_STATE_HOME:-$HOME/.local/state}/op-approval/watcher/` | macOS only: the compiled host and its build log |

The feed holds `machine`, `state`, `updated_at`, `updated_epoch`, `last_present_at`, `engine` (a hash of the shared code the watcher runs) and, only while the watcher is confirming input, `activity_pending_until`.

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
| `machine` | hostname | Label in alerts and the feed. The default is the hostname on Linux and the local host name (System Settings > Sharing, `scutil --get LocalHostName`) on macOS, whose hostname changes with the network. Set it for a shorter label |
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
| `watcher.fallback_grace_seconds` | `120` | Wait after an approval was not given before the fallback |
| `watcher.expired_min_seconds` | `59` | Minimum lifetime that counts as expired (measured: 59.3 to 60.3 s) |
| `watcher.confirm_seconds` | `1` | Delay before the confirmation check of a new window |

Missing keys take their defaults silently. An invalid value takes its default with a warning on stderr (the scripts) or in the watcher's log. Scripts read the file on every run; the watcher re-reads it every 30 s and logs the values in force.

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

`read -rsp` needs bash; in zsh (the macOS default) use `read -rs 'NTFY_TOKEN?ntfy token: '`.

### Revoke a token

Remove its entry from the server's token list and redeploy. Deleting it only in ntfy's database is undone at the next start.

## Install on a machine

1. Apply the packages with `./scripts/apply-dotfiles`. It removes links left dangling by files that moved between packages, stows everything and, on macOS, loads the LaunchAgent. If an existing `~/.codex/AGENTS.md` or `~/.pi/agent/AGENTS.md` is a regular file, move it to a dated backup first; Stow refuses to replace it.
2. Generate and declare a token for this machine, as in [New machine: generate a token](#new-machine-generate-a-token).
3. Create `config.json` as in [Machine-local configuration](#machine-local-configuration), with `ntfy.url`, `ntfy.topic` and, if wanted, `machine`.
4. Start the watcher:
   - **macOS:** `apply-dotfiles` already loaded it. The first start compiles the host, which needs the Xcode Command Line Tools (`xcode-select --install`) and `jq`. After a later edit to the plist: `launchctl bootout gui/$(id -u)/local.op-approval-watcher`, then run `apply-dotfiles` again.
   - **Omarchy:** `systemctl --user daemon-reload && systemctl --user enable --now op-approval-watcher`
5. Check `~/.agents/skills/op-approval-blocked/scripts/presence` reads a real state within a minute, and send a test push (see [Validation](#validation)).

## Phone

1. Install the **official ntfy iOS app**. A community fork never received the server's ntfy.sh wake-ups, so pushes never arrived.
2. Sign in to your server as the read-only phone user, and subscribe to the topic on that server.
3. Set iOS notification previews for the app to show only when unlocked.

Measured delivery from Omarchy to a locked iPhone: 11 to 14 s, on Wi-Fi and on mobile data over Tailscale.

## Reading state

```sh
journalctl --user -u op-approval-watcher -f                                   # Omarchy: watcher decisions
/usr/bin/log stream --predicate 'subsystem == "op-approval-watcher"' --level info   # macOS (zsh has its own log)
~/.agents/skills/op-approval-blocked/scripts/presence    # {"machine":..,"state":..}
~/.agents/skills/op-approval-blocked/scripts/blocked list
~/.agents/lib/op-approval/claim status                   # inputs of the next claim decision
```

The watcher logs presence transitions, episode IDs, outcomes with their reason, decisions and publish results. It never logs the token, window titles or 1Password log content; an unexpected line from a known 1Password source is logged as "unrecognised 1Password prompt line from `<source>`".

`blocked list` shows every `notify` call on this machine, oldest first: time, reference, machine, harness, project, location, category, state and result. Match the reference against the agent's chat.

## Validation

From the repository root, on each platform:

```sh
python3 -m unittest discover -s packages/common/agents/tests -p 'test_op_approval.py'
node --test packages/common/op-approval-watcher/tests/
node --test packages/omarchy/op-approval-watcher/tests/   # Omarchy
node --test packages/macos/op-approval-watcher/tests/     # macOS
```

`shellcheck` runs through `uvx` (`SC1091` only notes that `common.sh` is sourced at runtime):

```sh
lib=packages/common/agents/.agents/lib/op-approval
skill=packages/common/agents/.agents/skills/op-approval-blocked/scripts
uvx --from shellcheck-py shellcheck -s sh -e SC1091 "$lib"/common.sh "$lib"/claim "$lib"/locate "$lib"/publish "$lib"/platform/*.sh "$skill"/*
uvx --from shellcheck-py shellcheck packages/{omarchy,macos}/op-approval-watcher/.local/bin/op-approval-watcher packages/{omarchy,macos}/op-approval-watcher/.local/share/op-approval-watcher/requesters
```

Send one test push without taking the claim or writing the index (it does reach the phone):

```sh
~/.agents/lib/op-approval/publish --template fallback --identity '{"project":"test"}' --category ssh
```

It prints `{"result":"sent",...}`, `not_configured` with a reason, or `failed` with the curl exit code and HTTP status.

## Changing behaviour on every machine

1. Change `Engine.js` or `Policy.js`, with an engine scenario or policy test. A threshold, timer or alert decision in a host file is a parity bug: move it to the shared files.
2. Run the full suite on both platforms if the change touches a host or a shell script; the shared node tests run anywhere.
3. Commit and push, then on every other machine: `git pull` and `./scripts/apply-dotfiles`.
4. Each watcher checks the shared files every 10 s and exits when they change; systemd or launchd starts it again with the new code. A pending grace period is cancelled and logged.
5. Compare the `engine` hash in `presence.json` (or the watcher's start line) across machines: the same hash means the same code.

## Troubleshooting

### No push

- Check the phone runs the official ntfy app.
- Run `presence`. `present` means no push, by design. Excluded states in `alerts.presence_states` also send nothing.
- Run `claim status`. If `last_alert` is newer than the feed's `last_present_at`, this absence already had its push. The next one needs Rod back at the machine first.
- On Omarchy, closing a window makes Hyprland emit a synthetic input event about 10 ms later, so the approval window closing can look like Rod returning. The watcher holds any activity within 300 ms of a window or layer close and discards it unless input continues past 5.5 s. While it holds activity, the feed carries `activity_pending_until`; `notify` waits up to 7 s for it to clear and the claim refuses while it is there. macOS emits no such input, so its host reports no closes to that filter.
- A `notify` result of `failed` with a curl error usually means the harness sandbox blocked the network. The agent reports it in the chat.

### No fallback from the watcher

The log names every candidate window that was not an approval, with the reason but not its title, and every episode's outcome with its reason. No fallback is sent when:

- the episode was answered (input while it was open, before 59 s, with no timeout or cancellation logged)
- Rod was present when it closed, or at any point during the grace period
- the window was already open when the watcher started (unknown age)
- the machine slept or resumed during the grace period
- the skill already alerted during this absence

An approval given with an Apple Watch produces no input, so it counts as not given; it alerts only if Rod is also not present.

With several requesters at once, the fallback names the machine and the approval type only.

### Presence stays `unknown`

- **Omarchy:** check `systemctl --user status op-approval-watcher`. If Hyprland stops answering, the watcher writes `unknown` and exits, and systemd restarts it against the live instance.
- **macOS:** check `launchctl print gui/$(id -u)/local.op-approval-watcher` and `~/.local/state/op-approval/watcher/build.log`. Wrapper errors (no `jq`, no compiler) go to the unified log under the `op-approval-watcher` tag.

Readers treat a feed older than 30 s as `unknown`, so a stopped watcher shows within 30 s.

## lerd and the linked AGENTS.md

`~/.codex/AGENTS.md` and `~/.pi/agent/AGENTS.md` are links into the tracked shared `AGENTS.md`, and lerd writes its block through symlinks. After any `lerd install`, `lerd mcp:enable-global` or `lerd update`, check:

```sh
git -C ~/dotfiles diff -- packages/common/agents/.agents/AGENTS.md
ls -l ~/.config/opencode/AGENTS.md    # must be absent or a symlink
```

Revert a lerd block with `git -C ~/dotfiles checkout -- packages/common/agents/.agents/AGENTS.md`. The lerd-only `~/.codex/AGENTS.md` that existed before the link is backed up at `~/.codex/AGENTS.md.pre-dotfiles-20261007`.

## Harness support

| Harness | Global rule | Skill | Verified on Omarchy (7 Oct 2026) |
| --- | --- | --- | --- |
| Claude Code | `~/.claude/CLAUDE.md` (link) | `~/.claude/skills/` link | Skill flow in the E2E tests |
| Codex | `~/.codex/AGENTS.md` (link) | `~/.codex/skills/` link | Rule, skill, `presence`, ntfy reached; auto-review allowed the request |
| Pi | `~/.pi/agent/AGENTS.md` (link) | `~/.agents/skills/` | Rule, skill, `presence`, ntfy reached |
| OMP | Loads `~/.agents/AGENTS.md` itself, so no link | `~/.agents/skills/` | Rule, skill, `presence`, ntfy reached |
| OpenCode | Not linked: by its docs it falls back to `~/.claude/CLAUDE.md` | Not checked | Not installed |
| Grok | Not checked | `~/.agents/skills/` through `[skills].paths` | Not checked |
