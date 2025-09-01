# dotfiles

My MacOS dotfiles, managed using GNU Stow.

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

4. Clone this repository to your MacOS home directory (`~/`):

```shell
cd ~
git clone https://github.com/roddutra/dotfiles.git
```

### To install GNU Stow only

To install GNU Stow on a Mac using homebrew, run:

```shell
brew install stow
```

## Backing up config files to this repo

Create a folder in the root of this repo for each app that you'd like to store config files for. It can be named anything you like such as `neovim`, `nvim`, `vim`. The name you set for this folder is the name you will need to pass to Stow later.

Then **inside** this new app's folder, create the directory structure and config files as if this app's folder was the home directory (`~/`).

```shell
# Example folder in Stow
./nvim/.config/nvim/

# This will map to the following directory on the target machine
~/.config/nvim/
```

### Backing up Homebrew packages

To backup an existing machine's Homebrew packages, `cd` into the relevant directory you'd like to dump the Brewfile to (eg. `/homebrew`) and run:

```shell
cd homebrew
brew bundle dump --describe
```

*If you'd like to overwrite an existing Brewfile, add the `--force` flag.*

## Importing config files from this repo

To setup the symlinks for each app in a new machine, make sure you have [GNU Stow installed](#to-install-gnu-stow-only) and run the following command from this project's root directory:

```shell
 stow {app_folder_name} # Eg. `stow nvim`
 ```

Examples:
- `stow zsh` will symlink the `.zshrc` file to the home directory `~/.zshrc` as the config file is nested directly under the `./zsh` folder in this repo
- `stow ghostty` will symlink the `config` file to `~/.config/ghostty` as the config file is nested under `./ghostty/.config/ghostty`

## Note

Once the symlinks are set for a given app, then the config files can be edited either in this repo's directory or in the target location as the symlinks are bi-directional.