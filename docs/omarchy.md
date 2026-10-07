# Omarchy Notes

Verified configuration, recovery steps, and lessons from this workstation.

## Restore this workstation

Apply portable dotfiles:

```sh
./scripts/apply-dotfiles
```

Preview link changes first:

```sh
./scripts/apply-dotfiles --dry-run
```

Install curated packages, plugins, and the saved theme:

```sh
./scripts/bootstrap-omarchy --hardware
```

Use `--dry-run` to inspect bootstrap commands. Omit `--hardware` on a machine without the same AMD CPU and NVIDIA GPU profile.

## Configuration ownership

Tracked Omarchy packages live under `packages/omarchy/`:

- `claude-desktop/` contains Claude Desktop launch flags. See [Electron apps cannot reach the keyring](#electron-apps-cannot-reach-the-keyring).
- `ghostty/` contains the Linux Ghostty configuration.
- `hypr/` contains personal Hyprland overrides.
- `nvim/` contains the Linux-specific Neovim override.
- `omarchy/` contains selected shell and plugin preference files.
- `voxtype/` contains managed dictation configuration, vocabulary, and Groq cleanup commands. See `docs/voxtype.md`.

Do not edit `/usr/share/omarchy/`. Omarchy owns it and may replace it during updates. Personal configuration belongs under `~/.config/` and is linked from this repository.

Generated monitor files, backups, secrets, downloaded plugins, and downloaded themes are intentionally excluded. Plugins and the theme are restored from `manifests/omarchy/`.

## Alt+Tab switcher

`manifests/omarchy/plugins.txt` restores [omalt-tab](https://github.com/Codesmith28/omalt-tab). The tracked `shell.json` enables its overlay, and the tracked Hyprland bindings load the plugin's own shortcuts when it is installed. `socat` supports its socket client; the binding calls the bundled client directly, so no `make prod` step or helper symlinks are needed.

Alt+Tab selects the previously focused window in recent-use order, which may move left on the workspace display. Shift+Alt+Tab reverses that order. With the switcher open, the arrow keys navigate spatially.

## OMP updates blocked by mise

Mise ignores releases younger than 24 hours by default. Override that protection for one OMP update:

```sh
MISE_MINIMUM_RELEASE_AGE=0s omp update
```

The setting applies only to that command. Verify afterward with:

```sh
omp --version
```

## Codex usage panel says Initialize

The AI app's Codex usage widget starts a separate read-only Codex app-server process to retrieve plan and rate-limit data. `Initialize` means that process timed out during its initial RPC. It does not mean Codex authentication is missing.

Local usage charts can still work because they read local Codex and OMP session records. Do not re-authenticate solely because this widget shows `Initialize`.

## Electron apps cannot reach the keyring

Chromium selects its credential backend from `XDG_CURRENT_DESKTOP`. It does not recognise `Hyprland`, so Electron apps fall back to the `basic_text` backend and report encryption as unavailable even when gnome-keyring is running and unlocked. Claude Desktop reports this as `Your sign-in won't be saved on this device.` and asks you to sign in again after every restart (`For your security, sign in again to keep using Claude.`).

Confirm the cause before reinstalling or unlocking anything:

```sh
grep -i "safeStorage\|backend=" ~/.config/Claude/logs/main.log
busctl --user list | grep org.freedesktop.secrets
```

`backend=basic_text` alongside a live `org.freedesktop.secrets` means desktop detection failed, not the keyring.

Force the backend in `~/.config/claude-desktop-flags.conf`, tracked as the `claude-desktop` package. The packaged `/usr/bin/claude-desktop` wrapper reads this file on every launch, so the flag applies however the app is started.

Quit the app and relaunch it, then sign in once more. A fixed session logs no `safeStorage` warnings.

Do not use a `~/.local/share/applications/com.anthropic.Claude.desktop` override. Claude Desktop now writes its own entry there (marked `X-Claude-Generated=true`) on every launch and silently drops any added `Exec` flags.

Any Electron application on Hyprland can hit this. Pass the same flag through that app's flags file or desktop entry.

## Type Portuguese accents

`packages/omarchy/hypr/.config/hypr/input.lua` maps Right Ctrl as the Compose key. Tap each key in sequence rather than holding them together.

| Character | Sequence |
|---|---|
| `é` | Right Ctrl, `'`, `e` |
| `á` | Right Ctrl, `'`, `a` |
| `ç` | Right Ctrl, `,`, `c` |
| `ã` | Right Ctrl, `~`, `a` |
| `õ` | Right Ctrl, `~`, `o` |
| `ê` | Right Ctrl, `^`, `e` |
| `à` | Right Ctrl, `` ` ``, `a` |

Use Shift with the final letter for capitals. On a US keyboard, `~` is Shift plus backtick and `^` is Shift plus `6`.

## Universal Select All

`SUPER + A` is defined in `~/.config/hypr/bindings.lua`:

- GUI surfaces receive `CTRL + A`.
- Terminal-tagged surfaces receive Ghostty's select-all chord.
- `hl.unbind("SUPER + A")` ensures the personal binding wins if a future Omarchy release assigns the same chord.

Hyprland captures this compositor-level shortcut before the focused application sees `SUPER + A`.

## Bar widgets and system tray items

A system-tray application must publish a StatusNotifierItem over D-Bus. Omarchy can pin, place in the drawer, or hide an item only after the application publishes it.

- Right-click the tray chevron to manage actual tray items.
- Unpin places a tray item in the expandable drawer.
- Hide removes a tray item from the tray.
- A separate Omarchy bar widget cannot be moved into the tray drawer.

## LAN access and UFW

A coding app accessed from the Mac required an explicit LAN rule because UFW denied incoming traffic by default. Scope any replacement rule to:

- Interface: `<lan-interface>`
- Source subnet: `<lan-subnet>`
- Destination: `<workstation-ip>`
- TCP port: `<application-port>`
- Comment: `<descriptive-rule-name>`

Network addresses and interfaces may change after reinstalling. Confirm the current interface, subnet, host address, listening process, and threat boundary before recreating the rule. Firewall state is documented rather than applied automatically.

### SSH to a LAN IP times out with Tailscale running

Before adding a UFW rule, check the listener, firewall, and return route. Replace `<client-lan-ip>` with the Mac or phone's address on the local network:

```sh
ss -ltn '( sport = :22 )'
sudo ufw status verbose
ip -4 route get <client-lan-ip>
ip -4 route show table 52
```

If `sshd` listens on port 22 and UFW already allows or limits `22/tcp`, but `ip route get` selects `tailscale0` instead of the LAN interface, Tailscale may have accepted an advertised subnet route that overlaps the local LAN. The incoming SSH connection reaches this machine, but its replies take the wrong path. A local route in the main table does not override Tailscale's higher-priority policy-routing table.

If this machine does not need advertised Tailscale subnet routes, disable their acceptance for the current Tailscale profile:

```sh
tailscale set --accept-routes=false
ip -4 route get <client-lan-ip>
```

The route should now use the LAN interface. This preference survives disconnects and restarts, but check it again after switching Tailscale profiles or explicitly changing Tailscale settings. Disabling route acceptance also removes access to any other subnet routes advertised to that profile; do not use this fix if those routes are needed.

## Internet drops when switching or disconnecting Tailscale

Symptom: public sites stop resolving after switching to a work tailnet or running `tailscale down`, then recover the moment the personal tailnet reconnects.

Check what the LAN interface and lerd's dnsmasq use as upstream:

```sh
resolvectl dns
cat ~/.local/share/lerd/dnsmasq/lerd.conf
```

If the LAN interface lists `100.100.100.100` or `fd7a:115c:a1e0::53`, or `lerd.conf` has `server=100.100.100.100`, public DNS depends on Tailscale's resolver. That works only on a tailnet whose DNS settings forward public names. A tailnet with split DNS only returns SERVFAIL (`journalctl -u tailscaled` logs `no upstream resolvers set`), and with Tailscale down the address is unreachable.

Cause: lerd's DNS repair (watcher log `DNS resolution broken, repairing`, or `lerd dns:repair`) takes the first nameservers in `/run/systemd/resolve/resolv.conf` as the upstream. While MagicDNS is active, those are Tailscale's.

Fix: pin lerd's upstream to the LAN resolvers in `~/.config/lerd/config.yaml`, then re-apply:

```yaml
dns:
    upstream:
        - <lan-dns-1>
        - <lan-dns-2>
```

```sh
lerd dns:repair --no-pull
```

Both the repair and lerd's NetworkManager dispatcher prefer `dns.upstream` over detection, so a later repair keeps the LAN resolvers. Verify by switching tailnets and running `tailscale down`: `getent ahostsv4 google.com.au` and `lerd.test` should still resolve.

`lerd dns:repair` re-runs lerd's whole installer, which rewrites tracked files in this repository: it appends an absolute-path `PATH` line to `packages/omarchy/bash/.bashrc` and strips the quotes from the lerd skill's `description`, which makes its frontmatter invalid YAML. Revert both afterwards:

```sh
git checkout -- packages/omarchy/bash/.bashrc packages/common/agents/.agents/skills/lerd/SKILL.md
```

## Symbols render as boxes in Ghostty

When JetBrains Mono lacks a symbol, Ghostty falls back to its built-in monochrome Noto Emoji. That font draws some symbols as boxed or heavy shapes that spill over the next cell. Claude Code shows three of them:

- `⏺` (U+23FA): message bullet, sent only by Claude Code running on macOS, so it appears in SSH and remote Herdr sessions to a Mac.
- `⏸` (U+23F8): plan mode indicator, on every platform.
- `✳` (U+2733): spinner frame, sent only when `TERM=xterm-ghostty`.

`packages/omarchy/ghostty/.config/ghostty/config` maps these to Noto Sans Symbols 2 with `font-codepoint-map`. Herdr and SSH do not change these symbols; the same text renders the same way in a local Ghostty pane.

Check which font draws a symbol:

```sh
ghostty +show-face --cp=0x23fa
```

Only map symbols that tools print without the emoji selector VS16. A mapped codepoint followed by VS16 (`❤️`, `✔️`) renders as a replacement mark instead of a colour emoji, so a blanket mapping of every Noto Emoji fallback breaks emoji in ordinary text. Reload Ghostty with `pkill -USR2 -x ghostty` after editing the map.

## Hyprland checks

Hyprland normally reloads after configuration changes. Validate explicitly:

```sh
hyprctl reload
hyprctl configerrors
```

A successful reload with empty `configerrors` is the required check.

## Useful Omarchy commands

```sh
omarchy commands
omarchy version
omarchy debug --no-sudo --print
omarchy restart shell
omarchy restart terminal
```

Use `omarchy debug` with `--no-sudo --print` so it cannot block on an interactive privilege prompt.
