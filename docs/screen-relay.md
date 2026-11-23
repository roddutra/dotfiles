# Remote desktop with screen-relay

[screen-relay](https://screen-relay.dev/docs) streams a machine's existing desktop to a browser as H.264 and takes keyboard and mouse input back. It is used to reach the GUI of the coding machines (the Mac and Omarchy) from each other, for dialogs, settings and approvals that a terminal over SSH cannot answer. Terminal work still goes over SSH.

screen-relay is experimental: version 0.1.5, no audio, text-only clipboard.

| Host | Status | Started by |
| --- | --- | --- |
| macOS | Set up and verified | LaunchAgent `local.screen-relay` (package `packages/macos/screen-relay`) |
| Omarchy | Not set up yet | See [Omarchy host](#omarchy-host) |

## How a session is reached

Each host runs one session that captures its real display. The engine listens only on `127.0.0.1:8080`. A browser on another machine reaches it one of two ways:

| Route | Viewer address | Needs |
| --- | --- | --- |
| Tailscale Serve (normal) | `https://<host>.<tailnet>.ts.net:8444/#token=...` | Both machines on the tailnet |
| SSH tunnel (LAN, no Tailscale) | `http://127.0.0.1:8080/#token=...` | SSH to the host's LAN IP |

There is no plain `http://<lan-ip>:8080` route. The viewer decodes video with WebCodecs and only sends the token from a secure page (HTTPS or loopback), so it cannot work there.

Port 8444 is used instead of 443 because lerd's podman proxy (`gvproxy`) already listens on `*:443` on the Mac. Omarchy uses the same port so links look the same on both.

### Tokens

- Every session start creates a new token: login, reboot, crash, or a display change.
- The token is the only credential. Anyone holding a viewer link controls that desktop. Keep links out of chat, notes and screenshots.
- `screen-relay-link` on the host prints the current link.

## Connect

The shared package `packages/common/screen-relay` installs two commands on every machine:

- `screen-relay-open HOST`: runs `screen-relay-link` on `HOST` over SSH and opens the viewer in the default browser, without printing the token.
- `screen-relay-link`: prints this machine's own current link. `screen-relay-open` calls it on the host.

`HOST` is anything `ssh` accepts: an SSH alias, `<user>@<lan-ip>` or a Tailscale name.

| Goal | Command |
| --- | --- |
| Open over Tailscale | `screen-relay-open HOST` |
| Open over the LAN | `screen-relay-open --tunnel HOST` |
| Print the link instead | add `--print` |

`--tunnel` starts `ssh -f -N -L 8080:127.0.0.1:8080 HOST` in the background, then opens `http://127.0.0.1:8080/#token=...`. The local port must be 8080, because the engine accepts a loopback page only when its origin matches the address it connects to. If something already listens on local port 8080, it is reused as the tunnel. The command prints how to close the tunnel.

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
- Lock-screen behaviour and a full reboot have not been tested.
- If `screen-relay status` reports missing permissions after a change to `host.c`, repeat step 6 for the new `screen-relay-host-<hash>`.

## Omarchy host

Not set up. Upstream lists Hyprland, and so Omarchy, as **untested** for attaching to a running Wayland session. The steps below come from the [Linux docs](https://screen-relay.dev/docs/linux) and have not been run on this machine. Once a manual session works, track it as an Omarchy package with a systemd user unit tied to `graphical-session.target`, like `wayvnc`, and update this section.

### Pilot

1. Install and build the Wayland backend. The installer also adds sway, XWayland and foot, even though attaching to Hyprland does not start them.

   ```sh
   npm install -g screen-relay@0.1.5
   screen-relay install --backend wayland
   ```

2. From a terminal inside the Hyprland session (not an SSH shell, not `sudo`), attach to the running compositor. Pick the monitor with `--output`; `hyprctl monitors` lists the names (`DP-1` is the ASUS, `DP-2` the Dell).

   ```sh
   screen-relay up -d --backend wayland --display "$WAYLAND_DISPLAY" --output DP-1 \
     --public "https://$(tailscale status --json | jq -r '.Self.DNSName' | sed 's/\.$//'):8444"
   ```

3. Add the Tailscale route. Running `tailscale serve` without `sudo` needs `sudo tailscale set --operator=$USER` once.

   ```sh
   tailscale serve --bg --https=8444 http://127.0.0.1:8080
   ```

4. Apply the dotfiles, which install `screen-relay-link` and `screen-relay-open` from the shared package. Remote Login on the Mac lets `screen-relay-open` reach it from Omarchy. `screen-relay-link` runs in a non-interactive SSH shell, so check from the Mac that it can find its tools: `ssh <omarchy> 'command -v screen-relay jq tailscale'` must print three paths. If `screen-relay` is missing, the npm global bin directory is only on the interactive `PATH`.
5. From the Mac, run `screen-relay-open <omarchy>` and test:
   - a real Hyprland window, clicks and typed text
   - disconnect and reconnect
   - the locked screen
   - a monitor off and on cycle

No UFW rule is needed: Tailscale traffic is accepted by `ts-input` ahead of UFW, and the SSH tunnel uses the existing SSH access.

### What counts as working

`screen-relay doctor` does not test the compositor's protocols. A stream without input, or a blank headless sway desktop, means attach mode is not working on Hyprland. Hyprland must provide `wlr-screencopy` v3, the virtual keyboard protocol and virtual pointer v2. If it does not, keep using wayvnc (see `docs/omarchy.md`) for Omarchy and screen-relay for the Mac.

Like wayvnc and Sunshine, an Omarchy session is unreachable after a reboot until the LUKS passphrase is typed at the PC.
