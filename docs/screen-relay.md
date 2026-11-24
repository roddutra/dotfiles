# Remote desktop with screen-relay

[screen-relay](https://screen-relay.dev/docs) streams a machine's existing desktop to a browser as H.264 and takes keyboard and mouse input back. It is used to reach the GUI of the coding machines (the Mac and Omarchy) from each other, for dialogs, settings and approvals that a terminal over SSH cannot answer. Terminal work still goes over SSH.

screen-relay is experimental: version 0.1.5, no audio, text-only clipboard.

| Host | Status | Started by |
| --- | --- | --- |
| macOS | Set up and verified from Omarchy | LaunchAgent `local.screen-relay` (package `packages/macos/screen-relay`) |
| Omarchy | Set up and verified from the Mac, one session per monitor | systemd user units `screen-relay-dp1` and `screen-relay-dp2` (package `packages/omarchy/screen-relay`) |

## How a session is reached

A session captures one real display. Its engine listens only on loopback:

| Host | Session | Display | Engine | Tailscale port |
| --- | --- | --- | --- | --- |
| Mac | `default` | built-in display | `127.0.0.1:8080` | 8444 |
| Omarchy | `dp-1` | DP-1 (ASUS) | `127.0.0.1:8091` | 8444 |
| Omarchy | `dp-2` | DP-2 (Dell) | `127.0.0.1:8090` | 8445 |

A browser on another machine reaches a session one of two ways:

| Route | Viewer address | Needs |
| --- | --- | --- |
| Tailscale Serve (normal) | `https://<host>.<tailnet>.ts.net:<tailscale port>/#token=...` | Both machines on the tailnet |
| SSH tunnel (LAN, no Tailscale) | `http://127.0.0.1:<engine port>/#token=...` | SSH to the host's LAN IP |

There is no plain `http://<lan-ip>:<engine port>` route. The viewer decodes video with WebCodecs and only sends the token from a secure page (HTTPS or loopback), so it cannot work there.

Port 8444 is used instead of 443 because lerd's podman proxy (`gvproxy`) already listens on `*:443` on the Mac. Omarchy uses the same port so links look the same on both. Engine ports must be unique across all hosts: a tunnel binds the same port locally, so a port shared with the local engine would collide. The Mac keeps 8080 and Omarchy uses 8091 and 8090 (a lerd container holds 8081 there).

### Tokens

- Every session start creates a new token: login, reboot, crash, or a display change.
- The token is the only credential. Anyone holding a viewer link controls that desktop. Keep links out of chat, notes and screenshots.
- `screen-relay-link` on the host prints the current link.

## Connect

The shared package `packages/common/screen-relay` installs two commands on every machine:

- `screen-relay-open HOST [SESSION]`: runs `screen-relay-link` on `HOST` over SSH and opens the viewer in the default browser, without printing the token.
- `screen-relay-link [SESSION]`: prints this machine's own current links. `screen-relay-open` calls it on the host.

`HOST` is anything `ssh` accepts: an SSH alias, `<user>@<lan-ip>` or a Tailscale name. The SSH aliases in use are `omarchy` on the Mac and `rfd-mbp` (the Mac's LAN IP) on Omarchy. The alias only fetches the link, so one LAN alias serves both routes: the Tailscale link names the host's MagicDNS name itself. Without `SESSION`, the host picks `default` (the Mac), or else its first running session by name (`dp-1`, then `dp-2` when DP-1 is off).

| Goal | Command |
| --- | --- |
| Open over Tailscale | `screen-relay-open HOST` |
| Open one Omarchy monitor | `screen-relay-open HOST dp-2` |
| Open both Omarchy monitors, one tab each | `screen-relay-open --all HOST` |
| Open over the LAN | `screen-relay-open --tunnel HOST` (combines with `--all` or `SESSION`) |
| Print the links instead | add `--print` |

`--tunnel` forwards each session's engine port to the same local port (for Omarchy, `ssh -f -N -L 8091:127.0.0.1:8091 -L 8090:127.0.0.1:8090 HOST` with `--all`), then opens `http://127.0.0.1:<port>/#token=...`. The local port must match, because the engine accepts a loopback page only when its origin matches the address it connects to. If a local port is already listening, the command stops with an error naming it: close the old tunnel or stop whatever holds the port. The command prints how to close the tunnel.

One viewer owns input at a time. A viewer that opens while another one owns input is view-only until you click **Take control**.

## macOS host

The package `packages/macos/screen-relay` installs:

- `~/Library/LaunchAgents/local.screen-relay.plist`: starts at login in the graphical session and restarts the session whenever it exits (throttled to 15 seconds). Logs go to `~/Library/Logs/screen-relay.log`.
- `~/.local/bin/screen-relay-agent`: builds the permission host on first run, then starts the runner under it.
- `~/.local/share/screen-relay-agent/host.c`: the permission host. It stays the launchd job's program and starts the runner as a child.
- `~/.local/share/screen-relay-agent/run`: waits up to two minutes for Tailscale's name, then runs `screen-relay up --public https://<name>:8444` in the foreground. Without a Tailscale name it starts loopback-only.

### Why a permission host

macOS grants Screen Recording and Accessibility to a process's responsible process, which under launchd is the job's own program. Without the host, both grants would have to go to `node` or `/bin/sh` and would then apply to every launchd job that runs them. The host is ad-hoc signed as `local.screen-relay-host` and built to `~/.local/state/screen-relay-agent/screen-relay-host-<hash>`. The grants are tied to that exact build:

- Upgrading Node or screen-relay keeps them.
- Changing `host.c` rebuilds the host, and both permissions must be granted again.

### Set up

1. Install `node` and `jq` from the Brewfile, and the Xcode Command Line Tools.
2. Install and build screen-relay with Homebrew's Node. The LaunchAgent uses `/opt/homebrew/bin/screen-relay`, so the lerd Node shim is not used.

   ```sh
   /opt/homebrew/bin/npm install -g screen-relay@0.1.5
   screen-relay install --yes
   ```

3. Enable Remote Login (System Settings > General > Sharing). `screen-relay-open` and the tunnel route both use SSH.
4. Add the Tailscale route once. Tailscale keeps it across restarts.

   ```sh
   tailscale serve --bg --https=8444 http://127.0.0.1:8080
   ```

5. Apply the dotfiles and load the agent:

   ```sh
   ./scripts/apply-dotfiles
   launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/local.screen-relay.plist
   ```

6. In System Settings > Privacy & Security, turn on **Screen & System Audio Recording** and **Accessibility** for `screen-relay-host-<hash>`. If it is not listed, add it with **+** from `~/.local/state/screen-relay-agent/` (Cmd+Shift+G in the file picker). Do not grant your terminal, `node` or `sh`.
7. Restart the agent and check that the session is ready:

   ```sh
   launchctl kickstart -k "gui/$(id -u)/local.screen-relay"
   screen-relay status
   ```

### Operate

| Task | Command |
| --- | --- |
| Status | `screen-relay status` |
| Restart (new token) | `launchctl kickstart -k "gui/$(id -u)/local.screen-relay"` |
| Stop until next login | `launchctl bootout "gui/$(id -u)/local.screen-relay"` |
| Agent log | `tail -f ~/Library/Logs/screen-relay.log` |
| Engine log | `screen-relay logs engine` |
| Remove the Tailscale route | `tailscale serve --https=8444 off` |

`screen-relay-link` and the agent log both contain the token. The log is readable only by its owner, and each token stops working at the next start.

### Notes

- FileVault is on, so after a reboot the Mac must be unlocked before any user session exists. The agent starts once that login completes.
- The stream uses the display's native pixels (3600x2338 on the built-in Retina display).
- Changing the resolution or connecting a display stops the session. launchd starts a new one with a new token.
- On 24 November 2026, clicks and typing from Omarchy worked over Tailscale and over the SSH tunnel.
- Lock-screen behaviour and a full reboot have not been tested.
- If `screen-relay status` reports missing permissions after a change to `host.c`, repeat step 6 for the new `screen-relay-host-<hash>`.

## Omarchy host

Upstream lists Hyprland as **untested** for attaching to a running Wayland session. On Hyprland 0.56 the engine binds `wlr-screencopy` v3, the virtual keyboard, virtual pointer v2 (per output) and `wlr-data-control`, and `screen-relay move` lands on the right monitor for both sessions. On 24 November 2026, clicks and typing from the Mac worked on both monitors over Tailscale and over the SSH tunnel.

Each monitor has its own session, like wayvnc. The browser shows one monitor per tab; open both with `screen-relay-open --all HOST`.

The package `packages/omarchy/screen-relay` installs:

- `~/.config/systemd/user/screen-relay-dp1.service` and `screen-relay-dp2.service`: tied to `graphical-session.target`, so they inherit `WAYLAND_DISPLAY` from the Hyprland session. Each runs one session in the foreground and restarts it 5 seconds after it ends, which covers a resolution change.
- `screen-relay-dp1.timer` and `screen-relay-dp2.timer`: retry the service every 30 seconds while it is not running.
- `~/.local/share/screen-relay-agent/output-ready`: the `ExecCondition` copied from wayvnc. A service skips cleanly while its monitor is unplugged or disabled, and its timer starts it once the monitor is back.
- `~/.local/share/screen-relay-agent/run OUTPUT PORT TAILSCALE_PORT`: waits up to two minutes for Tailscale's name, then runs `screen-relay up --name <output in lower case> --backend wayland --display "$WAYLAND_DISPLAY" --output OUTPUT --port PORT --public https://<name>:TAILSCALE_PORT`. It puts `/usr/bin` first on `PATH`, so the system Node runs screen-relay instead of lerd's shim.

### Set up

1. Install the engine's build library and screen-relay with the system npm into `~/.local`. Do not run `screen-relay install`: it adds sway (not needed to attach) with `pacman -Syu`, a full system upgrade outside `omarchy-update`.

   ```sh
   omarchy-pkg-add libwebsockets
   env PATH=/usr/bin:/bin NPM_CONFIG_PREFIX="$HOME/.local" /usr/bin/npm install -g screen-relay@0.1.5
   ```

   The first session start builds the engine into `~/.local/share/screen-relay/engine/<version>/` without sudo.

2. Add the Tailscale routes once. Tailscale keeps them across restarts. `tailscale serve` without `sudo` needs `sudo tailscale set --operator=$USER` once.

   ```sh
   tailscale serve --bg --https=8444 http://127.0.0.1:8091
   tailscale serve --bg --https=8445 http://127.0.0.1:8090
   ```

3. Apply the dotfiles and enable the units:

   ```sh
   ./scripts/apply-dotfiles
   systemctl --user daemon-reload
   systemctl --user enable --now screen-relay-dp1.service screen-relay-dp2.service screen-relay-dp1.timer screen-relay-dp2.timer
   ```

4. From the Mac, `ssh <omarchy> 'command -v screen-relay jq tailscale'` must print three paths, then run `screen-relay-open --all <omarchy>` and test clicks and typing in a real window, disconnect and reconnect, the locked screen and a monitor off and on cycle.

No UFW rule is needed: Tailscale traffic is accepted by `ts-input` ahead of UFW, and the SSH tunnel uses the existing SSH access.

### Operate

| Task | Command |
| --- | --- |
| Status | `screen-relay status --name dp-1` (or `dp-2`) |
| Restart (new token) | `systemctl --user restart screen-relay-dp1` |
| Stop until next login | `systemctl --user stop screen-relay-dp1.timer screen-relay-dp1` |
| Service log | `journalctl --user -u screen-relay-dp1` |
| Engine log | `screen-relay logs engine --name dp-1` |
| Upgrade | repeat the npm install with the new version, then restart both services |
| Remove the Tailscale routes | `tailscale serve --https=8444 off` and `--https=8445 off` |

### Notes

- If DP-2 stays inactive, check that nothing else listens on its engine port: `ss -ltnp | grep 8090`.
- The cursor image is not streamed (upstream limitation); the pointer still moves.
- wayvnc keeps running alongside on 5900 and 5901. Both capture the same outputs without conflict.
- Like wayvnc and Sunshine, an Omarchy session is unreachable after a reboot until the LUKS passphrase is typed at the PC.
