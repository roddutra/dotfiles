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

- `ghostty/` contains the Linux Ghostty configuration.
- `hypr/` contains personal Hyprland overrides.
- `nvim/` contains the Linux-specific Neovim override.
- `omarchy/` contains selected shell and plugin preference files.

Do not edit `/usr/share/omarchy/`. Omarchy owns it and may replace it during updates. Personal configuration belongs under `~/.config/` and is linked from this repository.

Generated monitor files, OmaSettings state, backups, secrets, downloaded plugins, and downloaded themes are intentionally excluded. Plugins and the theme are restored from `manifests/omarchy/`.

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

OmaSettings is a bar widget plus a service. Its gear can be removed from `bar.layout.right` while keeping `io.github.twiking.omasettings` enabled in the top-level plugin list so the launcher entry remains available.

## LAN access and UFW

A coding app accessed from the Mac required an explicit LAN rule because UFW denied incoming traffic by default. Scope any replacement rule to:

- Interface: `<lan-interface>`
- Source subnet: `<lan-subnet>`
- Destination: `<workstation-ip>`
- TCP port: `<application-port>`
- Comment: `<descriptive-rule-name>`

Network addresses and interfaces may change after reinstalling. Confirm the current interface, subnet, host address, listening process, and threat boundary before recreating the rule. Firewall state is documented rather than applied automatically.

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
