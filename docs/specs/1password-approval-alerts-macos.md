# 1Password approval alerts: macOS, every approval type, one shared core

PRD for three changes to the system in
[`1password-approval-alerts.md`](1password-approval-alerts.md) (the **base
spec**):

1. **macOS.** Run the same system on Rod's Macs: the `op-approval-blocked`
   skill, the presence feed, the alert claim and the watcher's fallback, with
   the same behaviour as on Omarchy.
2. **Every 1Password approval.** Detect every approval 1Password can raise, on
   both platforms, not only SSH and the `op` CLI.
3. **One shared core.** Restructure the code so behaviour lives in shared
   files and each platform only translates its own signals. A behaviour change
   made once applies to every machine.

Drafted 8 October 2026 and reviewed by Codex the same day. **Discovery ran on
8 October 2026** on Rod's MacBook (19 cases with real prompts); see
[Discovery results](#discovery-results), which settle the macOS detector and
change the expiry rule on both platforms. **Status: ready to build**, after a
review of the post-discovery changes.

The base spec stays the behaviour reference. This document only describes what
changes; where it says "as in the base spec", the behaviour is identical.

## Goals

- On macOS, Rod hears that an agent is blocked on 1Password when he is away,
  and is not interrupted when he is at the Mac, exactly as on Omarchy:
  - the skill is the primary alert
  - the watcher sends one fallback when nobody reported an expiry
  - at most one push per absence
  - fixed notification templates that say where to go
- Any 1Password approval that is not given while Rod is away is reported,
  whatever asked for it: SSH, git, the `op` CLI, an Environments mount, an
  unlock (including the browser extension's), or a type 1Password adds later.
- A behaviour change is made in one place, tested once, and reaches every
  machine with `git pull` and `./scripts/apply-dotfiles`.

## Non-goals

As in the base spec (no remote approval, no alerts while a prompt is pending,
no alerts while the machine is asleep, no automatic resume), plus:

- **macOS privacy permissions.** The watcher works without Screen Recording,
  Accessibility or Full Disk Access. Discovery confirmed every signal it needs
  is available without them.
- **Windows.** `apply-dotfiles` knows the platform, but nothing here targets
  it.
- **Spaces and window titles on macOS.** Neither is available without
  permissions, so the location names the app and the multiplexer only.
- **Testing approval types Rod does not use.** The SDKs and MCP are covered
  only by the generic detector; nobody exercises them.

## Scope: every 1Password approval

| Type | Typical requester | macOS surface (discovery) | Omarchy today |
| --- | --- | --- | --- |
| SSH (`ssh`, `scp`, `rsync`) | agent, script | 1Password approval window; SSH log lines | Covered |
| Git over SSH | agent | Same as SSH | Covered |
| `op` CLI | agent, script | 1Password approval window; no log line at expiry unless 1Password was locked | Covered |
| Environments (mounted `.env`) | dev server, script, agent | 1Password approval window; Environments log line | Out of scope; now in scope |
| Unlock from an SSH, `op` or Environments request | the request | Inside the same 1Password window (Touch ID or password) | Covered |
| Unlock from the browser extension | Rod, or a browser an agent drives | macOS Touch ID dialog (`coreautha`), not a 1Password window; times out after 30 s | Not considered; now in scope |
| SDKs, MCP, anything 1Password adds later | | Generic detector only; not tested | Generic detector only |

Consequences, on both platforms:

- **A requester no longer decides whether an approval counts.** On Omarchy a
  window only becomes an episode when an SSH socket client or an `op` process
  is found. Discovery showed an Environments read whose requester exited 23 ms
  after raising the prompt. From now on the detector alone qualifies an
  episode; requesters only add identity (harness, project, location). See
  [Detector contract](#detector-contract).
- **Lifetime alone cannot decide expiry.** See
  [Outcome rule](#outcome-rule).
- **Not every requester is an agent.** The fallback names the approval type
  and, when identified, the process; it must not claim an agent was involved.
  See [Notifications](#notifications).
- **One user-facing approval may produce several signals.** An SSH request
  while 1Password is locked logs an unlock line and an SSH line; two requests
  at once share one window. The alert claim already limits pushes to one per
  absence; the engine also merges overlapping episodes so the log stays
  readable.

# Part 1: Shared core

## Principle

Decisions live in shared code. A platform host only observes its desktop and
translates what it sees into engine events, then carries out the effects the
engine returns. If a platform file contains a threshold, a timer length or an
"if Rod is away" test, that is a parity bug: move it into the shared core.

```text
             Omarchy host                       macOS host
     (Quickshell, shell.qml, systemd)    (Swift + JavaScriptCore, launchd)
   window events, IdleMonitor, lock,    window list, 1Password log, HID idle,
   Hyprland health, 1Password log       session lock, sleep/wake, session health
                  │                                   │
                  └──────── normalised events ────────┘
                                   │
                    Engine.js + Policy.js (shared, pure)
                                   │
   effects: write feed · run helper · observe · reset input · timers · log · exit
                                   │
            shared shell: claim, publish, locate, notify, presence, blocked
                                   │
                   platform probes: requesters, locate's per-OS parts
```

## What is shared and what is per platform

| Concern | Shared | Omarchy | macOS |
| --- | --- | --- | --- |
| Episode lifecycle, outcome rule, grace timer, fallback decision, reconcile, merge | `Engine.js` | | |
| Thresholds, presence derivation, synthetic-activity filter, feed document, config normalisation, label allowlist, log signatures | `Policy.js` | | |
| Alert claim, publishing, templates, token handling | `claim`, `publish` | | |
| Skill procedure and scripts | `op-approval-blocked` | | |
| Config and state paths, presence reader, lock | `common.sh` | | feed directory from `getconf DARWIN_USER_TEMP_DIR` |
| Approval candidates | | Hyprland window events, title rule | window list: new 1Password layer-101 window, or `coreautha` window tied to an unlock log line |
| 1Password log follower | parser in `Policy.js` | `~/.config/1Password/logs/` (to confirm) | `~/Library/Group Containers/2BUA8C4S2C.com.1password/Library/Application Support/1Password/Data/logs/1Password_rCURRENT.log` |
| Input idleness | | `IdleMonitor`, 5 s | `CGEventSource` seconds since last HID event |
| Lock state | | `omarchy-hyprland-session-locked` | `CGSessionCopyCurrentDictionary`, plus `com.apple.screenIsLocked` and `screenIsUnlocked` notifications |
| Suspend | wall-clock gap rule in `Policy.js` | | also `NSWorkspace` sleep and wake |
| Session health | | `hyprctl version` | console session present |
| Requesters | | `ss -xap`, `/proc` | `lsof -U`, `ps` |
| `locate` process facts | | `/proc`, `hyprctl` | `lsof -d cwd`, app bundle in ancestry |
| Service | | systemd user unit | LaunchAgent |
| Journal | | systemd journal | unified log (`log show`) |

## Engine

`Engine.js` takes over the orchestration now in `shell.qml`: candidates and
generations, the confirm and requester steps, episode start and end, the
outcome rule, grace timers, the fallback flow, reconciliation, resume handling,
config application, and when to write the feed.

- Written in the JavaScript subset that runs unchanged in Quickshell's QML
  engine, JavaScriptCore and node, like `Policy.js` today (no modules, no
  `.pragma library`, `module.exports` only when defined).
- A pure reducer: `step(state, event) -> {state, effects}`. No I/O, no clock,
  no timers. Every event carries its own `atMs`.
- Helper results come back as events, matched to the effect that asked for
  them by an ID the engine issued.

Events:

- `start` (previous feed, config text, hostname)
- `config` (new config text, or load failure)
- `tick` (every second)
- `input` (`idle` or `active`, from the 5-second threshold)
- `surface_closed` (any window close, for the synthetic-activity filter)
- `lock` (`locked`, `unlocked`, `unknown`)
- `session` (`up` or `down`)
- `sleep`, `wake`
- `log_line` (source, message), new lines of 1Password's log
- `candidate_open`, `candidate_confirmed`, `candidate_rejected`, `candidate_closed` (see below)
- `helper_done` (effect ID, exit code, output)
- `observed` (effect ID, result), the answer to an `observe` effect
- `timer_fired` (timer ID)

Effects:

- `write_feed` (document)
- `run` (helper name, arguments, deadline, effect ID); helper names are
  `requesters`, `locate`, `claim` and `publish`, resolved by the host
- `observe` (what, effect ID): the host takes one reading and answers with
  `observed` (effect ID, result). `what` is one of:
  - `candidate` (key): the platform's confirmation check for one candidate,
    such as `hyprctl clients -j` and the title rule on Omarchy
  - `open_candidates`: approvals already open, for reconciliation
  - `lock`
  - `session`: the health check (`hyprctl version` on Omarchy)
- `reset_input`: discard the input monitor's state and start a new one; the
  host answers with `input` events from the new monitor only
- `set_timer` and `cancel_timer` (timer ID, delay)
- `log` (level, message)
- `exit` (code), for a lost session, so the service manager restarts the host

The engine schedules every reading. For example, it asks for `lock` every 10
s, every 2 s while a candidate or grace period is pending, and on every input
change, and it sends `reset_input` after a clock gap or `wake`. The host only
knows how to take a reading, never when.

`shell.qml` shrinks to the Quickshell adapter. The macOS host is the same
adapter in Swift.

## Detector contract

Each platform's detector reports approval candidates with a key it chooses:

| Event | Meaning |
| --- | --- |
| `candidate_open {key, openedAtMs, reconciled, kind?}` | Something that may be an approval appeared |
| `candidate_confirmed {key, kind?}` | The platform rule says it is an approval |
| `candidate_rejected {key, reason}` | It is not (logged with the reason, never a title) |
| `candidate_closed {key, closedAtMs}` | It went away |

`kind` is one of `ssh`, `op-cli`, `environment`, `unlock` or `unknown`. The
engine owns everything after confirmation: kind from log lines and requesters,
the requester lookup (identity only), the [outcome rule](#outcome-rule),
merging, the grace period and the fallback.

**Merging.** Confirmed episodes whose lifetimes overlap are one episode. The
merged episode is not given if any part was not given, and its kind is the
most specific one reported (`ssh`, `op-cli` or `environment` over `unlock`
over `unknown`).

## Outcome rule

When an episode closes, the engine classifies it:

- **Not given** (eligible for the fallback) if any of these holds:
  1. a log line within its lifetime marks a timeout or a cancellation (see
     [log signatures](#log-signatures))
  2. it lasted at least `watcher.expired_min_seconds` (59 s)
  3. input observations were valid for its whole lifetime, and no input
     occurred after it opened and at or before it closed
- **Answered** otherwise.

Rule 3 details:

- **Raw input, before the synthetic-activity filter.** The click or key that
  answers a prompt lands milliseconds before the window closes, so the filter
  would hold it and, if Rod then leaves, discard it. Rule 3 therefore reads
  the input timestamps the engine records before filtering. The filter only
  ever affects presence.
- **Timestamps.** The macOS host stamps each `input active` with the real
  input time (now minus the HID idle seconds), so the click and the close are
  ordered correctly even though both are polled. Omarchy stamps the event's
  arrival time.
- **Coverage.** If observations were invalid at any point in the lifetime
  (after a start, a `reset_input` or a wake, until the monitor first reports
  idle), rule 3 does not apply and only rules 1 and 2 decide.
- **Bias.** While the input monitor stays active, the reducer counts every
  tick as input. Continuous activity at the start of a prompt therefore
  reads as "answered": a lost alert, never a spurious one. On Omarchy, a
  synthetic input that arrives before the `closewindow` event has the same
  effect.

Why rule 2 is no longer enough, from discovery:

- While the screen is locked, the display turns off after 20 to 30 s, and
  1Password cancels any pending prompt at that moment (`Locked. Reason:
  Automatic(DeviceWentToSleep)`). The prompt ended after 18.5 s and 24.6 s in
  two runs, and `ssh` reported `agent refused operation`, the same as a
  rejection.
- A browser extension unlock times out after 30 s.
- Approving or rejecting needs a click, a key or Touch ID. In 13 of the 14
  unattended runs no input was recorded between the window opening and
  closing, and in every answered case there was. The exception, case 1, ran
  over VNC and recorded input at 15, 20 and 30 s, probably Rod (not
  confirmed); rule 2 still classified it.

Rule 3 takes the input observations the presence feed already uses. Known
edge: an approval given with an Apple Watch produces no input and would count
as not given. It only alerts if Rod is also not present, so it is accepted.

Reconciled episodes (already open at start) keep the base spec's treatment:
never eligible.

## Log signatures

The host feeds new lines of 1Password's current log to the engine;
`Policy.js` matches each line's source path and message against this table.
Observed on macOS 1Password 8.12.36 and 8.12.40:

| Source | Message | Meaning |
| --- | --- | --- |
| `op-ssh-agent` | `ssh authorization prompt timed out` | SSH prompt timed out |
| `op-ssh-agent` | `Session was not authorized` | SSH prompt rejected or cancelled |
| `op-app` `components/ssh_agent.rs` | `received error from SSH auth prompt` | SSH prompt cancelled (with a lock below) |
| `op-app` `backend/lock.rs` | `Locked. Reason: Automatic(DeviceWentToSleep)` | 1Password locked because the display turned off; cancels pending prompts |
| `op-unlock` | `System unlock proceeding with DeviceEnclave backend` | Unlock requested |
| `op-system-auth` | `AppCancel invoked by a timed-out prompt` | Unlock prompt timed out |
| `op-automated-unlock` | `Failed to authorize using system biometry` | Kind hint: browser extension unlock |
| `developer/environment` | `Developer Environment file mount auth was denied by the user` | Kind hint: Environments. Logged on timeout as well as rejection |
| `ProcessValidation.swift` | `Will validate remote process` | Kind hint: an `op` request over XPC |
| `op-ssh-agent` | `Notifying user through tray icon that they have a background prompt waiting` | Kind hint: SSH. Seen 366 times in old logs, never during discovery |

`failed to find NSApplication related to pid` is logged for every SSH and
`op` request, prompted or not, so it is not a signal.

The engine logs any line from a source in this table that matches no message
as "unrecognised 1Password prompt line from `<source>`", never the message
itself. Discovery saw account IDs in neighbouring lines, so log content never
leaves the matcher.

## Shared tests

- **Engine scenarios (node).** One timeline test per acceptance scenario in
  the base spec and this one, and one per discovery case, replayed from the
  recorded event shapes (for example: screen locked, SSH cancelled at 18.5 s
  with no input, grace passes, one fallback). They run against `Engine.js`
  alone, so one test covers both platforms. They replace the parts of
  `policy.test.js` that exercise orchestration indirectly.
- **Shell contracts (Python).** `test_op_approval.py` runs on both platforms,
  with per-OS stubs (`hyprctl` and `ss` on Linux; `lsof`, `ps` and `getconf`
  on macOS).
- **Host adapters.** Omarchy keeps `requesters.test.js`. macOS adds tests for
  its `requesters` and for the Swift host's translation of signals to events,
  with no decisions to test.
- Before merging a change to shared code, run the full suite on both
  platforms. The `test-audit` skill's authoring gate applies.

## Propagating a change

1. Make the change in shared code, with its scenario test.
2. Commit and push from either machine.
3. On every other machine: `git pull`, then `./scripts/apply-dotfiles`.
4. Each watcher restarts itself: the host watches `Engine.js` and `Policy.js`
   and exits when either changes, and the service manager restarts it with
   the new code. A pending grace period is cancelled and logged.
5. Each watcher logs a short content hash of `Engine.js` and `Policy.js` at
   start and writes it to the feed as `engine`, so `scripts/presence` on any
   machine shows which revision is running. Readers ignore the field
   otherwise.

`docs/op-approval.md` gets a parity checklist with these steps.

## Repository layout

```text
packages/common/agents/
├── .agents/lib/op-approval/
│   ├── claim, common.sh, publish
│   ├── locate                     # shared logic; sources platform/<os>.sh
│   └── platform/{linux,darwin}.sh # process cwd, ancestry, app or window part
├── .agents/skills/op-approval-blocked/   # moved from packages/omarchy/agents
└── tests/test_op_approval.py
packages/common/claude/.claude/skills/op-approval-blocked   # link, moved from omarchy
packages/common/codex/.codex/skills/op-approval-blocked     # link, moved from omarchy
packages/common/op-approval-watcher/
├── .local/share/op-approval-watcher/{Engine.js,Policy.js}
└── tests/                                # node: engine scenarios, policy
packages/omarchy/op-approval-watcher/
├── .config/systemd/user/op-approval-watcher.service
├── .local/bin/op-approval-watcher
├── .local/share/op-approval-watcher/{shell.qml,requesters}
└── tests/
packages/macos/op-approval-watcher/
├── Library/LaunchAgents/local.op-approval-watcher.plist
├── .local/bin/op-approval-watcher        # builds the host when stale, then runs it
├── .local/share/op-approval-watcher/
│   ├── host/*.swift
│   └── requesters
└── tests/
```

- `packages/common/op-approval-watcher` joins `common_packages` in
  `scripts/apply-dotfiles`. It is inert without a host.
- `op-approval-watcher` joins the macOS `platform_packages`.
- `packages/omarchy/agents` keeps any Omarchy-only skills; the Omarchy
  `claude` and `codex` links to this skill are removed.
- All packages stow with `--no-folding`, so the common and platform packages
  share `~/.local/share/op-approval-watcher/`.

**Migrating an existing installation.** On Omarchy, the installed links point
into `packages/omarchy/agents` and `packages/omarchy/{claude,codex}`. After
the move they dangle, and Stow refuses to stow the common packages over links
it does not own. `scripts/apply-dotfiles` therefore gains a step that runs
before any stowing: under each target directory the packages install into,
remove symlinks that dangle and whose destination is inside this repository's
`packages/` directory. It removes nothing else, and running it twice is
harmless. Verify by upgrading the existing Omarchy installation and then
running `./scripts/apply-dotfiles --dry-run`, which must show no conflicts.

# Part 2: macOS host

## Runtime

A Swift program that embeds JavaScriptCore, loads `Policy.js` and `Engine.js`,
and runs one `RunLoop`.

- **Why Swift with JavaScriptCore:** it runs the shared JavaScript unchanged,
  calls the macOS APIs directly, and needs no Homebrew runtime under launchd.
  Rejected: a node watcher (needs a helper process for lock and sleep events,
  and a Homebrew path under launchd); JXA (runs the same JavaScript, but its
  Objective-C bridge is fragile and hard to debug, as the probes showed).
- **Build:** `~/.local/bin/op-approval-watcher` hashes the Swift sources,
  compiles with `swiftc` into
  `${XDG_STATE_HOME:-$HOME/.local/state}/op-approval/watcher/` when the hash
  changed, and runs the binary. It needs the Xcode Command Line Tools; without
  them it logs why and exits non-zero. No permissions are granted to the
  binary, so a rebuild loses nothing. The discovery recorder, built the same
  way, compiled in seconds.
- **Service:** a LaunchAgent with `RunAtLoad` and `KeepAlive`. launchd's
  minimum restart interval is 10 s, longer than systemd's 2 s first retry.
  The wrapper sets `PATH` to include `/opt/homebrew/bin` for `jq`.
- **Logging:** the unified log, subsystem `op-approval-watcher`, read with
  `log show --predicate 'subsystem == "op-approval-watcher"'`. Same content
  rules as the journal on Omarchy: no token, titles or request details.

## Approval detection

Two candidate sources, both from `CGWindowListCopyWindowInfo` polled every
250 ms (owner, PID, window number, layer, bounds, on-screen flag; no titles):

1. **1Password approval window.** A 1Password-owned window whose window
   number was not in the previous poll and which reaches layer 101. Confirmed
   after `watcher.confirm_seconds` if it is still present and 400 points wide.
   - Every SSH, git, `op` and Environments approval used it, unlocked or
     locked, with Touch ID or a password field inside it.
   - Heights seen: 325 (`op`, Environments), 369 to 370 (SSH), 425 to 455
     (with an unlock field). Height is not used.
   - Quick Access is also at layer 101, but it is one window created at
     launch and shown and hidden (550 wide), so it is never new. The main
     window (1024×800) and Settings (780×680) are at layer 0.
   - Position depends on the active display and is not used.
2. **macOS Touch ID dialog.** A `coreautha` window (layer 1000) that opens
   within 1 s after a `System unlock proceeding` log line. The browser
   extension's unlock uses it; without the log line it belongs to another app
   and is ignored.

The candidate closes when its window leaves the list. Kind comes from the log
lines during its lifetime and from requesters. Window numbers are new for each
prompt, so they are the candidate keys.

**Log follower.** The host follows `1Password_rCURRENT.log` by name (it rotates
at about 500 KB), reopens it on rotation, starts at the end of the file, and
sends each line as `log_line`. Lines arrived within about 50 ms of being
written.

**Reconcile on start:** 1Password windows already at layer 101 that are not
the Quick Access window become reconciled candidates, never eligible for a
fallback, as in the base spec.

## Presence

The engine's activity reducer and presence rules are unchanged. The host
supplies the same inputs:

- **Input:** polls seconds since the last HID event every 250 ms and sends
  `input idle` when it reaches 5 s, and `input active` when it falls below the
  previous reading. Verified: `caffeinate` and a playing video (with its
  display wake lock) do not count, and nothing registers when an approval
  window opens or closes.
- **Remote control counts as presence.** Input over VNC or Screen Sharing
  registers like local input. Someone controlling the Mac remotely can see
  and answer the prompt, so this is correct.
- **Closes:** the macOS host does not send `surface_closed`. Discovery saw no
  synthetic input when windows close, so there is nothing to filter, and the
  filter cannot hold a real click that happens to land next to a close. This
  is a fact about what the platform emits, not a decision: the filter itself
  stays in `Policy.js` and still runs on Omarchy.
- **Lock:** the session dictionary's `CGSSessionScreenIsLocked`, read on
  every lock notification and on the base spec's polling schedule. Both
  signals agreed within 0.3 s on every lock and unlock.
- **Session:** `down` when the session is not on the console (fast user
  switching, login window), which makes presence `unknown`.
- **Sleep and wake:** `NSWorkspace` `willSleep` and `didWake` send `sleep`
  and `wake`, in addition to the clock-gap rule. `screensDidSleep` was never
  delivered to the recorder, so display sleep is not an input; the log's
  `DeviceWentToSleep` line covers its effect on prompts.

**Sleep behaviour.** Rod's Mac sleeps one minute after the display turns off
(`pmset` `sleep 1`) unless something holds it awake. Claude Code holds
`caffeinate -i -t 300` while it works, so a working agent keeps the Mac awake
and its prompts still raise and expire normally with the display off (case 14).
An idle Mac sleeps, as the base spec's non-goal allows.

**Feed path.** On macOS the feed directory is
`$(getconf DARWIN_USER_TEMP_DIR)op-approval/`, not `$TMPDIR`, because a
sandboxed harness can change `TMPDIR` and would then read the wrong file.
`common.sh` uses the same rule. Linux keeps `$XDG_RUNTIME_DIR/op-approval/`.

## Requesters

`requesters` for macOS, read-only, printing the same JSON as the Linux one.
Identity only:

- **SSH agent:** sockets from `SSH_AUTH_SOCK`, each `IdentityAgent` in
  `~/.ssh/config` (here `Host *` sets one), and
  `~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock`, kept
  when 1Password listens on them. Clients are found with `lsof -U -F pcdn`: a
  client's peer address equals the device address of a socket 1Password
  holds on that path. Paired within 0.5 s in every SSH case.
- **`op`:** `op` holds no Unix socket (it talks to 1Password over XPC), so it
  is matched by start time as on Linux. `ps -o lstart` has one-second
  resolution, so the early-side slack is 1 s instead of 0.2 s. Exclude the
  `op` daemon: an `op` process whose parent is PID 1, which starts with the
  first request and keeps running.
- **Environments:** not identified. The reader may exit within milliseconds
  (case 17) or block on the mounted file (case 17b); the watcher does not know
  the mount paths. The fallback names the machine and the type.

## locate

- **Project:** the requester's working directory from
  `lsof -a -p <pid> -d cwd -Fn`.
- **Ancestry:** `ps -o ppid= -o comm=`, as now.
- **App:** the first ancestor whose executable is inside an `.app` bundle,
  reported by the bundle's display name (`Ghostty`, `iTerm2`, `Zed`,
  `Claude`).
- **Multiplexer servers are re-parented to launchd.** On this Mac, Herdr's
  server has PID 1 as its parent, so the agent's ancestry never reaches
  Ghostty. When the walk ends at a Herdr or tmux server, `locate` finds an
  attached client of that session and walks the client's ancestry to the app.
- **Herdr and tmux without the target's environment.** Today `locate` only
  tries Herdr when the target's environment has `HERDR_ENV` or
  `HERDR_PANE_ID`, and tmux when it has `TMUX`, read from `/proc` for
  `--pid`. `ps -E` does not return another process's environment on macOS 27,
  so the watcher's lookups need another route, on both platforms:
  - When the target's environment is unreadable, `locate` asks each
    multiplexer server it can reach on its default socket (`herdr pane list`
    and `herdr pane process-info`, `tmux list-panes -a -F '#{pane_pid}'`)
    and matches pane shell PIDs against the target's ancestry, as Herdr
    matching does now.
  - The process ancestry itself shows which server to ask: a Herdr or tmux
    server process in the ancestry is the one that owns the pane.
  - The skill's own calls are unaffected: `notify` runs inside the agent and
    reads its own environment.
- Example location: `Ghostty, herdr proxmox/agents`.

# Part 3: Changes on both platforms

## Skill

- Move to `packages/common/agents`, so it installs on every platform.
- `--category` gains `environment`. Browser unlocks are not an agent's
  command, so they reach Rod through the fallback only.
- The description, the procedure's step 2 and the shared `AGENTS.md` rule
  cover any 1Password approval, with these symptoms:

| Command | Not given (expired, or cancelled when the display turned off) | Rejected |
| --- | --- | --- |
| `ssh`, macOS and Linux | expired: `... from agent: communication with agent failed`; cancelled: `... agent refused operation`; then `Permission denied (publickey)`, exit 255 | `... agent refused operation` |
| `git` over SSH | the SSH lines, then `fatal: Could not read from remote repository`, exit 128 | same pattern |
| `op`, macOS | expired: `[ERROR] ... authorization timeout`, exit 1 | `[ERROR] ... authorization prompt dismissed, please try again`, exit 1 |
| `op`, Linux | `[ERROR] ... authorization prompt dismissed, please try again`, exit 1 | identical |
| Reading a mounted Environments `.env` | **no error**: the read blocks about 60 s, then returns an empty file with exit 0 | same, sooner |

- Two discovery facts the procedure states: on macOS, `op` also prints
  `prompt dismissed` when it was waiting on another request's prompt that
  expired (case 6), so no error proves Rod rejected anything; and a mounted
  `.env` is a named pipe, so `test -p <path>` identifies one without raising
  a prompt. An agent whose program stalled for about a minute and then ran
  without its variables checks that, and treats a pipe as "approval not
  given".
- The `AGENTS.md` rule's parenthesis ("SSH with the 1Password agent, git over
  SSH, or the `op` CLI") becomes "any command that needs 1Password, including
  reading a mounted `.env` file", with the current three kept as examples.

## Notifications

Templates stay fixed and use only enumerated or sanitised fields, as in the
base spec.

- **Category labels:** `SSH`, `Git over SSH`, `1Password CLI`, `Environment`,
  `Unlock`, `1Password`.
- **Skill alert:** unchanged; an agent always sent it.
- **Watcher fallback with an identified agent harness:** unchanged.
- **Watcher fallback without one:** title `[<machine>] 1Password approval
  not given`, body `<category> approval not given, with no report from an
  agent, <process> in <project>, <location>.`, with each unknown part left
  out. The process is the requester's `comm`, sanitised.

## Omarchy

- Extract `Engine.js` from `shell.qml` with no behaviour change, then run the
  existing tests and the base spec's E2E checks again.
- Apply the [outcome rule](#outcome-rule). Verify that Hyprland's synthetic
  input arrives after the `closewindow` event (so it does not count for rule
  3), with an unattended expiry and an unattended cancellation (lock the
  screen during a prompt), and that an approval click arrives before it.
- Drop the requester gate (the [scope](#scope-every-1password-approval)
  change). The title rule alone then qualifies an episode, so confirm that an
  Environments prompt uses the same approval window, and that no other
  1Password window keeps the title `1Password` for more than a second.
- Add the log follower if Linux 1Password logs the same signatures. The base
  spec recorded `ssh authorization prompt timed out` and `Session was not
  authorized` there.
- Check whether Linux 1Password cancels a pending prompt when the screen
  locks or the display turns off.

# Discovery results

Run on 8 October 2026 on a MacBook Pro (MacBookPro18,3): macOS 27.0 (26A428),
1Password 8.12.36, `op` 2.32.0, Herdr in use, Ghostty and Arc. 1Password
settings: Touch ID unlock on, auto-lock after 60 minutes, SSH agent on.
Cases 1 to 11 ran over VNC with the lid closed, which disables Touch ID;
cases 12 to 19 ran at the Mac with the lid open. 1Password downloaded 8.12.40
during the run; it was installed afterwards and re-checked (see
[Re-check on 8.12.40](#re-check-on-81240)).

The recorder sampled windows, HID idle time, lock state, the frontmost app,
sleep and wake, 1Password socket peers and processes every 250 to 500 ms, and
followed 1Password's log.

| # | Case | Window | Life | Outcome | Command result |
| --- | --- | --- | --- | --- | --- |
| 1 | SSH, 1Password locked (password), left alone | 1P layer 101, 400×455 | 60.0 s | `ssh authorization prompt timed out` | `communication with agent failed`, 255, 60.2 s |
| 2 | SSH, unlocked, left alone | 400×370 | 60.0 s | same | same |
| 3 | `op vault list`, unlocked, left alone | 400×325 | 60.3 s | no log line | `authorization timeout`, 1, 60.2 s |
| 4 | `op`, rejected | 400×325 | 2.8 s | no log line | `authorization prompt dismissed`, 1, 2.9 s |
| 5 | SSH, rejected | 400×370 | 4.0 s | `Session was not authorized` | `agent refused operation`, 255, 4.3 s |
| 6 | SSH and `op` together, left alone | one shared 400×370 | 60.0 s | SSH timed out | SSH as case 2; `op`: `prompt dismissed` |
| 7 | Rod opens main window, Quick Access, Settings | layer 0, layer 101 (persistent), layer 0 | | no episode | |
| 8 | `git ls-remote` over SSH, left alone | 400×370 | 59.8 s | SSH timed out | SSH lines + `fatal: Could not read from remote repository`, 128, 65 s |
| 9 | SSH, approved; then SSH again | 400×370 | 2.5 s | no log line | 0; repeat: no prompt, 0.3 s |
| 10 | SSH, 1Password locked, Touch ID unavailable (lid closed) | 400×438 | 60.0 s | SSH timed out | as case 1 |
| 11 | SSH, screen locked, over VNC | 400×438 | 24.5 s | display off, `DeviceWentToSleep`, `Session was not authorized` | `agent refused operation`, 24.6 s |
| 12 | SSH, 1Password locked, Touch ID available, left alone | 400×369 | 59.3 s | `System unlock proceeding`, SSH timed out, `AppCancel` | as case 2 |
| 13 | SSH, screen locked, at the Mac | 400×425 | 18.5 s | as case 11 | `agent refused operation`, 18.5 s |
| 14 | SSH raised after the display was already off (`caffeinate -i`) | 400×425 | 59.7 s | SSH timed out, normally | as case 2 |
| 15 | Browser extension unlock, left alone | `coreautha` layer 1000, 260×205 | 30.0 s | `System unlock proceeding`, `AppCancel`, `Failed to authorize using system biometry` | |
| 16 | `op`, 1Password locked, left alone | 400×325 | 60.0 s | `System unlock proceeding`, `AppCancel` | `authorization timeout`, 60.1 s |
| 17 | Open a mounted `.env` (opener exits at once), locked | 400×325 | 60.0 s | `AppCancel`, `Developer Environment file mount auth was denied by the user` | |
| 18 | SDK through desktop integration | none | | dropped: Rod does not use the SDKs | |
| 19 | Video playing, hands off 40 s | | | HID idle reached 61 s | |

Case 17b read the same `.env` with `wc -c`: the read blocked 60.3 s and
returned 0 bytes with exit 0.

Other findings:

- **Input.** No input was recorded in any unattended case except case 1
  (see [Outcome rule](#outcome-rule)), including when windows opened and
  closed. Clicks over VNC and at the Mac both registered.
- **Requesters.** `ssh` was paired with `agent.sock` within 0.5 s every time.
  `op` was found by start time. The Environments opener in case 17 exited
  23 ms after raising the prompt.
- **"Background prompt waiting"** never appeared, although it was logged 366
  times before. Its trigger is unknown; nothing depends on it.
- **Historic timeouts.** The 28 Environments timeouts on 1 October came from
  something reading `~/Developer/--personal/proxmox-configs/.env`, the one
  mounted Environment on this Mac. What read it is not known.

## Re-check on 8.12.40

Two cases after updating 1Password to 8.12.40 the same day:

- SSH with 1Password locked, left alone (as case 12): same window (layer
  101, 400×369, 60.0 s), same `System unlock proceeding`, SSH timeout and
  `AppCancel` lines, same error.
- SSH with the screen locked (as case 13): cancelled 18.0 s after it opened
  when the display turned off, with the same `DeviceWentToSleep`, `received
  error from SSH auth prompt` and `Session was not authorized` lines, `agent
  refused operation`, and no input while it was open.

Only source line numbers changed (for example `lock.rs:237` became
`lock.rs:248`). **Signatures match on the module path and message, never on
line numbers.**

## Not exercised

Verified during the build instead:

- Karabiner's virtual keyboard, the screen saver with a lock delay, fast user
  switching
- launchd loading a symlinked plist at login
- each harness on macOS reading the feed through the `getconf` path and
  reaching ntfy
- `locate --pid` from the watcher's environment, on both platforms
- delivery from the Mac to the locked iPhone
- Touch ID for another app (`sudo` with `pam_tid` is not enabled here); the
  `coreautha` rule ignores it unless 1Password logged an unlock within 1 s

# Configuration and token

The config file, token file and keys are as in the base spec, at the same XDG
paths (`~/.config/op-approval/config.json`,
`~/.local/share/op-approval/secrets/ntfy-token`).

- Set `machine` on each Mac: macOS hostnames are long and similar.
- Each Mac gets its own ntfy token for the `desktop` user, added to
  `NTFY_AUTH_TOKENS` in the `ntfy` stack's Komodo Environment, as in the base
  spec's [notification service](1password-approval-alerts.md#notification-service).
- No new keys. Detector parameters from discovery (layer, width, the
  `coreautha` window, log signatures) are constants in `Policy.js`, not config.

# Security

The base spec's [threat model and rules](1password-approval-alerts.md#security)
apply unchanged. macOS additions:

- The watcher holds no macOS privacy permission.
- 1Password's log contains account identifiers. The watcher only matches
  signatures and never logs or forwards log content.
- The fallback without an agent names a process and project. Set a project
  alias for anything that should not appear on the lock screen.

# Acceptance criteria

macOS, on each Mac:

- Every watcher and skill criterion in the base spec's
  [acceptance criteria](1password-approval-alerts.md#acceptance-criteria)
  passes, with macOS equivalents for Hyprland restart (session loss) and the
  journal (unified log).
- With Rod away, each of these produces exactly one push when no agent
  reports it, and none when he is present: SSH, git over SSH, `op`, an
  Environments read, a browser extension unlock, each with 1Password locked
  and unlocked, and an SSH prompt cancelled by the screen locking.
- Rejected and approved prompts send nothing, including when Rod approves and
  then leaves the Mac untouched for 10 s, and when a prompt is approved
  within 5 s of the watcher starting. The same two checks run on Omarchy.
- Opening the main window, Quick Access or Settings creates no episode.
- The watcher runs without any privacy permission.
- After a 1Password update, the signatures in [Log signatures](#log-signatures)
  still match, or the unrecognised-line log shows what changed.

Shared core:

- Engine scenario tests cover every acceptance scenario and every discovery
  case, and pass under node.
- Both hosts load the same `Engine.js` and `Policy.js`. After a pull, both
  machines log the same engine hash.
- A test change to a default in `Policy.js`, made on one machine, changes
  behaviour on the other after `git pull` and `apply-dotfiles`, with no
  platform file edited.
- No platform file contains a threshold or an alert decision.

Omarchy, after the refactor:

- Upgrading the existing installation with `git pull` and
  `./scripts/apply-dotfiles` succeeds with no Stow conflicts.
- The base spec's E2E criteria still pass.
- An Environments approval produces a fallback when Rod is away.
- An unattended prompt cancelled early (if Linux 1Password does that) is
  classified as not given.
