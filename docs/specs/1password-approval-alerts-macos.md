# 1Password approval alerts: macOS, every approval type, one shared core

PRD for three changes to the system in
[`1password-approval-alerts.md`](1password-approval-alerts.md) (the **base
spec**):

1. **macOS.** Run the same system on Rod's Macs: the `op-approval-blocked`
   skill, the presence feed, the alert claim and the watcher's fallback, with
   the same behaviour as on Omarchy.
2. **Every 1Password approval.** Cover every approval 1Password can raise, on
   both platforms, not only SSH and the `op` CLI.
3. **One shared core.** Restructure the code so behaviour lives in shared
   files and each platform only translates its own signals. A behaviour change
   made once applies to every machine.

Drafted 8 October 2026. **Status: draft.** Passive probes ran on Rod's MacBook
the same day (see [What is already known](#what-is-already-known)). The
[discovery run](#discovery) with real prompts has not been done and gates the
macOS detector.

The base spec stays the behaviour reference. This document only describes what
changes; where it says "as in the base spec", the behaviour is identical.

## Goals

- On macOS, Rod hears that an agent is blocked on 1Password when he is away,
  and is not interrupted when he is at the Mac, exactly as on Omarchy:
  - the skill is the primary alert
  - the watcher sends one fallback when nobody reported an expiry
  - at most one push per absence
  - fixed notification templates that say where to go
- Any 1Password approval that expires while Rod is away is reported, whatever
  asked for it: SSH, git, the `op` CLI, an SDK, an Environments mount, an
  unlock, or a type 1Password adds later.
- A behaviour change is made in one place, tested once, and reaches every
  machine with `git pull` and `./scripts/apply-dotfiles`.

## Non-goals

As in the base spec (no remote approval, no alerts while a prompt is pending,
no alerts while the machine is asleep, no automatic resume), plus:

- **macOS privacy permissions.** The watcher must work without Screen
  Recording, Accessibility or Full Disk Access. Every signal probed so far
  needs none. If discovery shows one is unavoidable, Rod decides then.
- **Windows.** `apply-dotfiles` knows the platform, but nothing here targets
  it.
- **Spaces and window titles on macOS.** Neither is available without
  permissions, so the location names the app and the multiplexer only.

## Scope: every 1Password approval

| Type | Typical requester | macOS evidence (8 October 2026) | Omarchy today |
| --- | --- | --- | --- |
| SSH (`ssh`, `scp`, `rsync`) | agent, script | Logged: prompt start and `ssh authorization prompt timed out`; 369 timeouts in retained logs | Covered |
| Git over SSH, SSH commit signing | agent | Same SSH agent path | Covered |
| `op` CLI | agent, script | No log lines found; unknown | Covered |
| SDKs (desktop app integration) | script, app | No log lines found; unknown | Out of scope; now in scope |
| Environments (mounted `.env`) | dev server, script | Logged: `Developer Environment file mount auth was denied by the user`; 28 timeouts, most at :15:05 past the hour | Out of scope; now in scope |
| Unlock with Touch ID or system authentication | any of the above while 1Password is locked | Logged: `System unlock proceeding ...`, then `AppCancel invoked by a timed-out prompt` | Covered as the same approval window |
| MCP integration | agent | Disabled in settings | Not considered; now in scope if enabled |
| Anything 1Password adds later | unknown | | Caught only by a generic detector |

Consequences, on both platforms:

- **A requester no longer decides whether an approval counts.** On Omarchy a
  window only becomes an episode when an SSH socket client or an `op` process
  is found, so Environments and SDK approvals are dropped. From now on the
  detector alone qualifies an episode; requesters only add identity
  (harness, project, location). See [Detector contract](#detector-contract).
- **Not every requester is an agent.** The fallback names the approval type
  and, when identified, the process; it must not claim an agent was involved.
  See [Notifications](#notifications).
- **The skill covers the new types**: new categories and the failure text for
  each, from discovery. See [Skill](#skill).
- **One user-facing approval may produce several signals.** An SSH request
  while 1Password is locked logs an unlock timeout and an SSH timeout. The
  alert claim already limits pushes to one per absence; the engine also merges
  overlapping episodes so the log stays readable.

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
       effects: write feed · run helper · set timer · cancel timer · log · exit
                                   │
            shared shell: claim, publish, locate, notify, presence, blocked
                                   │
                   platform probes: requesters, locate's per-OS parts
```

## What is shared and what is per platform

| Concern | Shared | Omarchy | macOS |
| --- | --- | --- | --- |
| Episode lifecycle, grace timer, fallback decision, reconcile, merge | `Engine.js` | | |
| Thresholds, presence derivation, synthetic-activity filter, feed document, config normalisation, label allowlist, log signatures | `Policy.js` | | |
| Alert claim, publishing, templates, token handling | `claim`, `publish` | | |
| Skill procedure and scripts | `op-approval-blocked` | | |
| Config and state paths, presence reader, lock | `common.sh` | | feed directory from `getconf DARWIN_USER_TEMP_DIR` |
| Approval candidates | | Hyprland window events, title rule | decided by [discovery](#discovery) |
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
generations, the confirm and requester steps, episode start and end, grace
timers, the fallback flow, reconciliation, resume handling, config
application, and when to write the feed.

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
| `candidate_closed {key, closedAtMs, kind?}` | It went away |

`kind` is one of `ssh`, `op-cli`, `sdk`, `environment`, `unlock`, `mcp` or
`unknown`, from a log signature or a requester hint. The engine owns everything
after confirmation: the requester lookup (identity only), the lifetime rule
(`watcher.expired_min_seconds`), merging, the grace period and the fallback.

**Merging.** Confirmed episodes whose lifetimes overlap are one episode. The
merged episode is expired if any part expired, and its kind is the most
specific one reported (`ssh` over `unlock` over `unknown`).

**Log follower**, both platforms. The host feeds new lines of 1Password's
current log; `Policy.js` matches them against a table of signatures, each with
a kind and a role (`start` or `end`):

| Signature (source and message) | Kind | Role |
| --- | --- | --- |
| `op-ssh-agent` `Notifying user through tray icon that they have a background prompt waiting` | `ssh` | start |
| `op-ssh-agent` `ssh authorization prompt timed out` | `ssh` | end, expired |
| `op-unlock` `System unlock proceeding with DeviceEnclave backend` | `unlock` | start |
| `op-system-auth` `AppCancel invoked by a timed-out prompt` | `unlock` | end, expired |
| `developer/environment` `Developer Environment file mount auth was denied by the user` | `environment` | kind hint for the overlapping unlock |

The table is completed by discovery. The engine logs any line from a
prompt-related source that matches no signature as "unrecognised 1Password
prompt line from `<source>`", never the message itself, so a 1Password update
that changes the log shows up in the journal.

## Shared tests

- **Engine scenarios (node).** One timeline test per acceptance scenario in
  the base spec and this one (for example: away, SSH expiry, no skill, grace
  passes, one fallback). They run against `Engine.js` alone, so one test
  covers both platforms. They replace the parts of `policy.test.js` that
  exercise orchestration indirectly.
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
  binary, so a rebuild loses nothing.
- **Service:** a LaunchAgent with `RunAtLoad` and `KeepAlive`. launchd's
  minimum restart interval is 10 s, longer than systemd's 2 s first retry.
  The wrapper sets `PATH` to include `/opt/homebrew/bin` for `jq`.
- **Logging:** the unified log, subsystem `op-approval-watcher`, read with
  `log show --predicate 'subsystem == "op-approval-watcher"'`. Same content
  rules as the journal on Omarchy: no token, titles or request details.

## Approval detection

Decided by discovery against every row of the [scope table](#scope-every-1password-approval).
Two sources are available without permissions:

- **Window list.** `CGWindowListCopyWindowInfo` gives each window's owner,
  PID, layer, bounds and on-screen flag, but not its title. Polled every
  250 ms while 1Password runs.
- **1Password log.** The log follower in the
  [detector contract](#detector-contract). The host follows
  `1Password_rCURRENT.log` by name (it rotates at about 500 KB), reopens it on
  rotation, and starts at the end of the file.

Open questions that decide the rule:

- Does every approval type show a window, and can the approval window be told
  apart from the main window, Quick Access, Settings and the unlock screen by
  owner, layer and size alone?
- "background prompt waiting" suggests that when 1Password is not frontmost,
  the SSH prompt may only highlight the menu bar icon. If some approvals show
  no window, the log is the only source for them.
- Which types log nothing (the `op` CLI and SDKs, so far)? Those depend on the
  window list.

Acceptance rule for the chosen design: every type in the discovery matrix
produces an episode, and none of the [negative cases](#negative-cases) does.

**Reconcile on start:** approval windows already open, and log `start` lines
from the last 65 s with no `end`, become reconciled candidates, never eligible
for a fallback, as in the base spec.

## Presence

The engine's activity reducer and presence rules are unchanged. The host
supplies the same inputs:

- **Input:** polls seconds since the last HID event every 250 ms and sends
  `input idle` when it reaches 5 s, and `input active` when it falls below the
  previous reading. Measured on the hardware event stream, so power assertions
  (video playback, `caffeinate`) do not count as Rod being there. Discovery
  confirms this.
- **Closes:** every 1Password window that leaves the window list sends
  `surface_closed`, so the synthetic-activity filter keeps working if macOS
  shows the same behaviour as Hyprland.
- **Lock:** the session dictionary's `CGSSessionScreenIsLocked`, read on
  every lock notification and on the base spec's polling schedule.
- **Session:** `down` when the session is not on the console (fast user
  switching, login window), which makes presence `unknown`.
- **Sleep and wake:** `NSWorkspace` notifications send `sleep` and `wake`, in
  addition to the clock-gap rule.

**Feed path.** On macOS the feed directory is
`$(getconf DARWIN_USER_TEMP_DIR)op-approval/`, not `$TMPDIR`, because a
sandboxed harness can change `TMPDIR` and would then read the wrong file.
`common.sh` uses the same rule. Linux keeps `$XDG_RUNTIME_DIR/op-approval/`.

## Requesters

`requesters` for macOS, read-only, printing the same JSON as the Linux one:

- **SSH agent:** sockets from `SSH_AUTH_SOCK`, each `IdentityAgent` in
  `~/.ssh/config`, and
  `~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock`, kept
  when 1Password listens on them. Clients are found with `lsof -U`: a
  client's peer address equals the address of a socket 1Password holds on
  that path. Verified with a held connection on 8 October 2026.
- **`op`:** as on Linux, but `ps -o lstart` has one-second resolution, so the
  early-side slack is 1 s instead of 0.2 s.
- **SDK, Environments, MCP:** decided by discovery (which socket an SDK
  client holds; which process has a mounted `.env` file open).

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
- `--category` gains `sdk`, `environment` and `mcp`.
- The description, the procedure's step 2 and the shared `AGENTS.md` rule
  cover any 1Password approval, with the failure text for each type on each
  platform from discovery.
- The `AGENTS.md` rule's parenthesis ("SSH with the 1Password agent, git over
  SSH, or the `op` CLI") becomes "any command that needs 1Password", with the
  current three kept as examples.

## Notifications

Templates stay fixed and use only enumerated or sanitised fields, as in the
base spec.

- **Category labels:** `SSH`, `Git over SSH`, `1Password CLI`, `SDK`,
  `Environment`, `MCP`, `Unlock`, `1Password`.
- **Skill alert:** unchanged; an agent always sent it.
- **Watcher fallback with an identified agent harness:** unchanged.
- **Watcher fallback without one:** title `[<machine>] 1Password approval
  expired`, body `<category> approval expired with no report from an agent,
  <process> in <project>, <location>.`, with each unknown part left out. The
  process is the requester's `comm`, sanitised.

## Omarchy

- Extract `Engine.js` from `shell.qml` with no behaviour change, then run the
  existing tests and the base spec's E2E checks again.
- Drop the requester gate (the [scope](#scope-every-1password-approval)
  change). The title rule alone then qualifies an episode, so confirm on
  Omarchy that Environments and SDK prompts use the same approval window, and
  that no other 1Password window keeps the title `1Password` for more than a
  second.
- Add the log follower if Linux 1Password logs the same signatures. The base
  spec recorded `ssh authorization prompt timed out` there.

# Discovery

An implementation gate for the macOS detector, the requester sources for the
new types and the skill's failure text. Record versions (macOS, 1Password,
`op`, Herdr, tmux, Ghostty, Swift) and every observation in this document
before writing the macOS host.

## Approval matrix

Run each type below. For each, cover 1Password unlocked and locked; 1Password
frontmost, in the background, and with its main window closed; and the outcome
left alone, rejected and approved.

1. `ssh` to a host, with the approval cache lapsed (a new terminal session
   with per-session approval).
2. `git ls-remote` over SSH, and `git commit -S` with SSH signing in a scratch
   repository.
3. `op vault list` with CLI integration on.
4. An SDK call through desktop app integration, if an SDK supports it at the
   time. Otherwise record that and skip.
5. Reading a mounted Environments `.env` file. Also identify what reads one at
   :15:05 past the hour.
6. Unlocking from the browser extension, including from a browser an agent
   drives.
7. MCP, only if Rod enables it.
8. Two requests at once (two SSH, and SSH with `op`).

Record for each run:

- every window from the window list while it runs, sampled every 250 ms:
  owner, PID, layer, bounds, on-screen flag, and open and close times
- whether only the menu bar icon changes
- every log line from start to end, with its source path
- requester visibility: `lsof -U` peers, `op` start time, other sockets or
  open files
- the command's error text, exit code and duration
- seconds since the last HID event, sampled through the window's open and
  close, with nobody touching the Mac (the synthetic-activity question)

## Negative cases

None of these may produce an episode:

- Rod opens the main window, Quick Access or Settings
- a 1Password update prompt
- Touch ID for something else (`sudo` with `pam_tid`, a system dialog)

Unlock prompts are approvals whoever raised them, including Rod and the
browser extension. One Rod raises himself does not alert because he is
present or answers it, under the base spec's rules.

## Presence, service and harness probes

- Idle time ignores `caffeinate -d` and video playback.
- Karabiner's virtual keyboard registers input only when Rod types.
- Lock with Ctrl-Cmd-Q, with the screen saver and a lock delay, on display
  sleep and with the lid closed. The notification and the session dictionary
  agree, and unlocking clears `locked` promptly.
- Sleep and wake produce `sleep` and `wake`, and pending fallbacks are
  cancelled.
- Fast user switching makes presence `unknown`.
- launchd loads a symlinked plist at login, and the wrapper's `PATH` finds
  `jq`.
- In Claude Code, Codex, Pi and OMP on macOS: the global rule loads, the skill
  is found, `presence` reads the feed through the `getconf` path, `notify`
  reaches `https://ntfy.dutrafamily.com`, and the index is writable.
- `locate --pid`, run from the watcher's environment (no `HERDR_*` or
  `TMUX`), names the Herdr workspace and tab, and the tmux session, for a
  requester in each, and maps both to Ghostty through the attached client.
  The same check runs on Omarchy.
- Delivery from the Mac to the locked iPhone on Wi-Fi.

## Probe commands

```sh
logdir="$HOME/Library/Group Containers/2BUA8C4S2C.com.1password/Library/Application Support/1Password/Data/logs"
tail -F "$logdir/1Password_rCURRENT.log" | grep --line-buffered -E 'op-ssh-agent|op-system-auth|op-unlock|environment|cli|sdk|mcp'
lsof -U -a -c 1Password; lsof -U -a -c ssh
ioreg -c IOHIDSystem | awk '/HIDIdleTime/ {print $NF / 1e9; exit}'
```

The window sampler and lock reader are throwaway Swift scripts in the
session's scratch directory, not committed.

## What is already known

Passive probes on 8 October 2026: macOS 27.0 (26A428), arm64, 1Password
8.12.36, Herdr in use, Ghostty and iTerm2 installed, Swift available.

- The log records SSH prompts (start and timeout, about 60 s apart), unlock
  timeouts and Environments denials, as in the
  [scope table](#scope-every-1password-approval). No `op` CLI or SDK lines
  exist in logs retained since 4 September 2026.
- 237 SSH prompts timed out on 30 September and 128 on 1 October, which looks
  like something retrying in a loop.
- `CGSessionCopyCurrentDictionary`, `CGEventSource` idle time and
  `CGWindowListCopyWindowInfo` owner and bounds all work without permissions.
  Window titles do not.
- `lsof -U` pairs an agent socket client with 1Password's accepted socket.
- `getconf DARWIN_USER_TEMP_DIR` returns the per-user temporary directory.
- `ps -E` does not return another process's environment.

# Configuration and token

The config file, token file and keys are as in the base spec, at the same XDG
paths (`~/.config/op-approval/config.json`,
`~/.local/share/op-approval/secrets/ntfy-token`).

- Set `machine` on each Mac: macOS hostnames are long and similar.
- Each Mac gets its own ntfy token for the `desktop` user, added to
  `NTFY_AUTH_TOKENS` in the `ntfy` stack's Komodo Environment, as in the base
  spec's [notification service](1password-approval-alerts.md#notification-service).
- No new keys. Detector parameters that discovery produces (sizes, signatures)
  are constants in `Policy.js`, not config.

# Security

The base spec's [threat model and rules](1password-approval-alerts.md#security)
apply unchanged. macOS additions:

- The watcher holds no macOS privacy permission.
- 1Password's log may contain account and item identifiers. The watcher only
  matches signatures and never logs or forwards log content.
- The fallback without an agent names a process and project. Set a project
  alias for anything that should not appear on the lock screen.

# Acceptance criteria

macOS, on each Mac:

- Every watcher and skill criterion in the base spec's
  [acceptance criteria](1password-approval-alerts.md#acceptance-criteria)
  passes, with macOS equivalents for Hyprland restart (session loss) and the
  journal (unified log).
- Every type in the approval matrix produces exactly one push when Rod is away
  and no agent reports it, and none when he is present.
- No negative case produces an episode.
- The watcher runs without any privacy permission.

Shared core:

- Engine scenario tests cover every acceptance scenario and pass under node.
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
- Environments and SDK approvals produce a fallback when Rod is away.
