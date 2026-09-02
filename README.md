# dotfiles

Personal configuration for macOS, Omarchy, and Windows, managed with GNU Stow.

## Layout

```text
packages/
├── common/     # Shared CLI, editor, and coding-agent configuration
├── macos/      # macOS packages
├── omarchy/    # Omarchy, Hyprland, and Linux-specific packages
└── windows/    # Windows packages
manifests/
├── macos/      # Homebrew bundle
└── omarchy/    # Curated packages, plugins, theme, and hardware profile
docs/           # Notes that are never processed by Stow
scripts/        # Platform-aware apply and bootstrap commands
```

Each directory below a platform root is a normal Stow package. Its contents mirror paths below the home directory.

## Clone

Keep the repository at `~/dotfiles` on every machine:

```sh
cd ~
git clone --recurse-submodules https://github.com/roddutra/dotfiles.git
cd dotfiles
```

Do not add machine-specific absolute home paths to tracked files. Use `~`, `$HOME`, or repository-relative paths.

## Apply dotfiles

Preview the links for the current platform:

```sh
./scripts/apply-dotfiles --dry-run
```

Apply them:

```sh
./scripts/apply-dotfiles
```

The wrapper always applies `packages/common/`, then exactly one platform root:

- Darwin applies `packages/macos/`.
- Omarchy applies `packages/omarchy/`.
- Git Bash, MSYS, and Cygwin apply `packages/windows/`.
- Other Linux distributions and unknown platforms are refused.

The wrapper passes `--no-folding` so application-owned runtime directories remain real directories. Do not replace it with `stow */`; that can process documentation or packages for the wrong operating system.

## Initial setup

Run:

```sh
./setup.sh
```

This creates local macOS Zsh files when needed, installs the gitleaks pre-commit hook, and applies the correct Stow packages.

### macOS packages

Install Homebrew dependencies with:

```sh
brew bundle install --file manifests/macos/Brewfile
```

Local files remain untracked:

- `packages/macos/zsh/.zshrc`
- `packages/macos/zsh/.zsh-secrets`

### Omarchy packages

Restore curated packages, plugins, and the saved theme:

```sh
./scripts/bootstrap-omarchy
```

On the workstation with the matching AMD CPU and NVIDIA GPU profile:

```sh
./scripts/bootstrap-omarchy --hardware
```

Preview either command by adding `--dry-run`. See `docs/omarchy.md` for configuration ownership, exclusions, recovery notes, and verified lessons.

### Windows packages

Oh My Posh configuration lives under `packages/windows/ohmyposh/`. The platform wrapper can apply it from Git Bash, MSYS, or Cygwin when GNU Stow is available.

## Package ownership

### Common

- `agents`
- `claude`
- `grok`
- `omp`
- `pnpm`
- `tmux`
- `zed`

### macOS

- `ghostty`
- `karabiner`
- `nvim`
- `zsh`

### Omarchy

- `ghostty`
- `hypr`
- `nvim`
- `omarchy`

### Windows

- `ohmyposh`

Ghostty remains platform-specific because the macOS and Omarchy configurations differ in theme integration, font sizing, keybindings, shell integration, and toolkit settings.

Zed settings synchronization alternatives are documented in `docs/zed-settings.md`. The current tracked-file behavior remains unchanged until an option is selected.

## Add a configuration

1. Choose `packages/common/`, `packages/macos/`, `packages/omarchy/`, or `packages/windows/`.
2. Create an application package below that root.
3. Reproduce the path relative to `$HOME` inside the package.
4. Add the package name to the matching array in `scripts/apply-dotfiles`.
5. Run the wrapper with `--dry-run`, then without it.

Example for `~/.config/example/config.toml`:

```text
packages/common/example/.config/example/config.toml
```

Use a package-level `.stow-local-ignore` for maintainer files inside a package. Keep general documentation under `docs/` instead.

## Sensitive and generated files

Do not track:

- Authentication data, API keys, or credentials
- Shell secrets
- Caches, logs, runtime state, or backups
- Generated monitor output
- Downloaded Omarchy plugins or themes restored by manifests
- Machine-specific files that cannot safely load elsewhere

The root `.gitignore` and package-level Stow ignores enforce known exclusions. Review every new file before committing it.

## Submodules

Tmux Plugin Manager and the Catppuccin Tmux theme are Git submodules. Initialize or repair them with:

```sh
git submodule update --init --recursive
```

## Gitleaks

`setup.sh` installs a pre-commit hook that runs gitleaks when available. Install it before committing on a new machine:

```sh
brew install gitleaks
```

On Omarchy it is included in `manifests/omarchy/packages.txt`.
