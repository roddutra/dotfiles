# dotfiles

My MacOS dotfiles, managed using [GNU Stow](https://www.gnu.org/software/stow/) to easily create symlinks from this repo's dotfiles in a new machine.

## Overview

This repository contains my personal configuration files (dotfiles) for various applications. It uses:
- **GNU Stow** for symlink management - allowing easy installation/uninstallation of configs
- **Git Submodules** for tracking external plugin repositories (e.g., tmux plugins)
- **Homebrew Bundle** for consistent package installation across machines
- **gitleaks** pre-commit hook to prevent accidental secret commits

## Fresh MacOS installation steps

1. Install XCode Command Line Tools:

```shell
xcode-select --install
```

2. Install Homebrew:

```shell
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

3. (Optional) Run the following `brew` command to install all packages from a previous setup:

```shell
brew bundle install --file homebrew/Brewfile
```
> *Otherwise make sure to [install GNU Stow separately](#to-install-gnu-stow-only).*

4. Clone this repository to your MacOS home directory (`~/`) **with submodules**:

```shell
cd ~
git clone --recurse-submodules https://github.com/roddutra/dotfiles.git
```

> **Important:** The `--recurse-submodules` flag ensures that git submodules (like tmux plugins) are automatically downloaded.

5. Run the setup script to configure the repository:

```shell
cd ~/dotfiles
./setup.sh
```

This script creates local config files from templates (`.zshrc`, `.zsh-secrets`) and installs the gitleaks pre-commit hook.

### To install GNU Stow only

To install GNU Stow on a Mac using homebrew, run:

```shell
brew install stow
```

## How GNU Stow Works

GNU Stow creates symlinks from this repository to your home directory, making it easy to manage dotfiles with version control.

### Directory Structure

Each top-level directory in this repo represents an application's configuration:

```
dotfiles/
├── tmux/                   # The "package" name for stow
│   ├── .tmux.conf         # Will be symlinked to ~/.tmux.conf
│   └── .config/
│       └── tmux/          # Will be symlinked to ~/.config/tmux/
│           └── plugins/
├── nvim/
│   └── .config/
│       └── nvim/          # Will be symlinked to ~/.config/nvim/
│           └── lua/
├── zsh/
│   ├── .zshrc.template    # Template for .zshrc (version controlled)
│   ├── .zshrc             # Local copy with tool configs (gitignored, symlinked to ~/.zshrc)
│   ├── .zsh-settings      # Will be symlinked to ~/.zsh-settings (your config)
│   └── .zsh-secrets       # Will be symlinked to ~/.zsh-secrets (gitignored)
└── ghostty/
    └── .config/
        └── ghostty/       # Will be symlinked to ~/.config/ghostty/
            └── config
```

When you run `stow tmux`, it creates symlinks in your home directory that mirror the structure inside the `tmux/` folder.

## Backing up config files to this repo

To add a new application's configuration:

1. Create a folder in the root of this repo named after the application (e.g., `nvim`, `vim`, `alacritty`)
2. Inside this folder, recreate the exact directory structure as it appears in your home directory
3. Place the configuration files in their appropriate locations

Example:
```shell
# If your config lives at ~/.config/nvim/
mkdir -p nvim/.config/nvim/
cp -r ~/.config/nvim/* nvim/.config/nvim/
```

### Backing up Homebrew packages

To backup your Homebrew packages to this repo, use the custom `brew-dump` function included in the `.zshrc`:

```shell
brew-dump
```

This custom function:
- Dumps all Homebrew formulae, casks, and taps to `~/dotfiles/homebrew/Brewfile`
- **Automatically excludes VSCode extensions** to keep the Brewfile clean
- VSCode extensions should be managed through VSCode's built-in Settings Sync instead

#### Why exclude VSCode extensions?

When `brew bundle dump` runs on a system with VSCode installed, it includes all installed extensions as `vscode` entries. This can add 100+ lines to the Brewfile and creates several issues:
- Makes the Brewfile unnecessarily large and hard to read
- Forces the same VSCode setup on all users of these dotfiles
- Duplicates functionality since VSCode has its own sync mechanism

#### Manual alternative (without the custom function):

```shell
cd homebrew
brew bundle dump --describe --force
# Remove VSCode extensions
sed -i '' '/^vscode /d' Brewfile
```

### ZSH Configuration Structure

The zsh configuration is split into three modular files to separate concerns and enable version control without polluting your curated settings:

**How it works:**
- **`.zshrc.template`** - Version-controlled clean loader (the source of truth). Copied to `.zshrc` by `setup.sh` on first run.
- **`.zshrc`** - Local working copy (gitignored). Tools (NVM, pnpm, Herd, etc.) auto-append their configs here without polluting git history.
- **`.zsh-settings`** - Your curated shell configuration (version controlled): Oh My Posh theme, Zinit plugins, aliases, custom functions, history settings, completion styling, etc.
- **`.zsh-secrets`** - Sensitive environment variables (gitignored): API keys, tokens, passwords, etc.

**Why this structure:**
This allows you to version control your personalized shell setup while letting package managers work normally - they'll append to `.zshrc` as expected, but those auto-generated configs won't pollute your git history since `.zshrc` is gitignored. Your curated settings stay clean in `.zsh-settings`, and secrets remain safely gitignored in `.zsh-secrets`.

### Managing Sensitive Environment Variables

The zsh configuration supports a separate `.zsh-secrets` file for storing sensitive environment variables (API keys, tokens, passwords, etc.) that should never be committed to version control.

#### How it works:

- **`.zsh-secrets`**: Your actual file containing sensitive variables (gitignored, never committed)
- **`.zsh-secrets.example`**: A template file showing what variables you can add (version controlled)
- The main `.zshrc` file automatically sources `.zsh-secrets` if it exists

#### Adding sensitive variables:

1. Copy the example file to create your local file (or run `./setup.sh` which does this automatically):
   ```shell
   cd ~/dotfiles/zsh
   cp .zsh-secrets.example .zsh-secrets
   ```

2. Edit `.zsh-secrets` and add your sensitive variables:
   ```shell
   export GITHUB_TOKEN="your_token_here"
   export OPENAI_API_KEY="your_api_key_here"
   ```

3. The file is already symlinked if you've run `stow zsh`, or run it now:
   ```shell
   stow zsh
   ```

The `.zsh-secrets` file lives in your `dotfiles/zsh/` directory, gets symlinked to `~/.zsh-secrets` by stow, but is never committed to GitHub thanks to `.gitignore`.

## Importing config files from this repo

To setup the symlinks for each app in a new machine, make sure you have [GNU Stow installed](#to-install-gnu-stow-only) and run the following command from this project's root directory:

```shell
stow {app_folder_name} # Eg. `stow nvim`
```

### Install ALL configurations at once:
```shell
cd ~/dotfiles
stow */  # Stow all directories (each one is treated as a package)
```

### Install specific configurations:
```shell
cd ~/dotfiles
stow tmux nvim zsh ghostty  # Only stow the packages you want
```

### Remove/Uninstall configurations:
To remove symlinks created by stow, use the `-D` (delete) flag:

```shell
# Remove all symlinks
stow -D */

# Remove specific app symlinks
stow -D nvim
```

### Examples:
- `stow zsh` will symlink `.zshrc`, `.zsh-settings`, and `.zsh-secrets` to the home directory (the `.zshrc.template` is excluded via `.stow-local-ignore`)
- `stow ghostty` will symlink the `config` file to `~/.config/ghostty` as the config file is nested under `./ghostty/.config/ghostty`
- `stow tmux` will symlink both `.tmux.conf` to `~/.tmux.conf` AND the plugins directory to `~/.config/tmux/plugins/`
- `stow */` will symlink ALL application configs at once

### Setting up sensitive environment variables on a new machine:

After running `./setup.sh` and `stow zsh`, you'll need to edit your `.zsh-secrets` file for sensitive environment variables:

```shell
# The setup.sh script already created .zsh-secrets from the template
# Just edit it and add your sensitive variables
cd ~/dotfiles/zsh
# Edit .zsh-secrets (or ~/.zsh-secrets after running stow)

# The file is already symlinked by stow, so changes take effect immediately
```

See the [Managing Sensitive Environment Variables](#managing-sensitive-environment-variables) section for more details.

## Git Submodules

This repository uses git submodules to track external plugin repositories. This allows us to:
- Pin specific versions of plugins
- Update plugins independently
- Ensure consistent plugin versions across machines

### Current Submodules:
- **TPM (Tmux Plugin Manager)**: `tmux/.config/tmux/plugins/tpm`
- **Catppuccin for tmux**: `tmux/.config/tmux/plugins/catppuccin`

### Managing Submodules:

```shell
# Update all submodules to their latest versions
git submodule update --remote --merge

# If you forgot to clone with --recurse-submodules
git submodule init
git submodule update
```

## Tmux Setup

The tmux configuration uses TPM (Tmux Plugin Manager) for plugin management. All plugins are consolidated in `~/.config/tmux/plugins/` for a clean, organized structure.

### Configuration Details:
- **Plugin Path**: The tmux.conf sets `TMUX_PLUGIN_MANAGER_PATH` to `~/.config/tmux/plugins/` to ensure all plugins install to the same location as our submodules
- **No ~/.tmux directory**: Everything is kept under `~/.config/tmux/` following XDG base directory standards

### After running `stow tmux`:

1. Start tmux:
   ```shell
   tmux
   ```

2. Install TPM plugins (inside tmux):
   - Press `Ctrl+Space` (prefix) then `Shift+I`
   - TPM will automatically install all plugins listed in `.tmux.conf` to `~/.config/tmux/plugins/`

### Included Plugins:
- **TPM**: Plugin manager (included as submodule)
- **Catppuccin**: Theme (included as submodule)
- **tmux-sensible**: Sensible defaults
- **tmux-resurrect**: Save/restore sessions
- **tmux-continuum**: Automatic session saving
- **vim-tmux-navigator**: Seamless navigation between vim and tmux panes
- **tmux-yank**: Enhanced copy mode

The first two are included as git submodules for reliability, while the others are automatically installed by TPM on first run.

## Neovim Setup

This configuration uses [LazyVim](https://www.lazyvim.org/) - a Neovim setup powered by lazy.nvim.

### After running `stow nvim`:

1. Start Neovim:
   ```shell
   nvim
   ```
   LazyVim will automatically install all plugins on first launch.

2. **Seamless tmux/nvim navigation**: The configuration includes `vim-tmux-navigator` which allows you to use `Ctrl+h/j/k/l` to navigate between:
   - Neovim splits
   - Tmux panes
   - From Neovim to tmux and vice versa seamlessly

3. **Tmux integration from Neovim**: Custom keymaps are available to control tmux directly from within Neovim using the `<leader>t` prefix:
   - `<leader>tw` - Choose/switch tmux windows (replaces `Ctrl+Space w`)
   - `<leader>ts` - Choose/switch tmux sessions (replaces `Ctrl+Space s`)
   - `<leader>tc` - Create new tmux window
   - `<leader>tx` - Kill current tmux window
   - `<leader>tn` - Next tmux window
   - `<leader>tp` - Previous tmux window
   - `<leader>tr` - Rename tmux window
   - `<leader>td` - Detach from tmux session

   These commands are also accessible via the which-key menu - press `<leader>` and look for the `t → Tmux` submenu.

   **Why this exists**: When running Neovim inside tmux, the tmux prefix key (`Ctrl+Space`) doesn't work because Neovim intercepts the keystroke. These direct tmux commands bypass this limitation and provide seamless tmux control from within Neovim.

### Note:
The `lazy-lock.json` file is automatically generated by LazyVim and excluded from version control.

## Troubleshooting

### Stow Conflicts
If you get errors about existing files when running stow:
```shell
# Check what would be stowed
stow -n -v tmux  # Dry run with verbose output

# Force re-stow (will override existing symlinks)
stow -R tmux
```

### Missing Submodules
If plugin directories are empty:
```shell
git submodule init
git submodule update
```

### Updating Everything
```shell
# Pull latest changes including submodules
git pull --recurse-submodules

# Update submodules to latest upstream versions
git submodule update --remote --merge
```

## Notes

- Once the symlinks are set for a given app, config files can be edited either in this repo's directory or in the target location as the symlinks are bi-directional
- The `.gitignore` file is configured to exclude TPM-installed plugins (but keep the submodules)
- Always use `--recurse-submodules` when cloning to ensure all plugins are available