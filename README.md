# dotfiles

My MacOS dotfiles, managed using GNU Stow.

## Installation

To install GNU Stow on a Mac using homebrew, run:

```shell
brew install stow
```

## Configuration

Create a folder in the root of this repo for each app that you'd like to store config files for. It can be named anything you like such as `neovim`, `nvim`, `vim`. The name you set for this folder is the name you will need to pass to Stow later.

Then **inside** this new app's folder, create the directory structure and config files as if this app's folder was the home directory (`~/`).

```shell
# Example folder in Stow
./nvim/.config/nvim/

# This will map to the following directory on the target machine
~/.config/nvim/
```

## Usage

To setup the symlinks for each app in a new machine, run the following command from this project's directory:

```shell
 stow {app_folder_name} # Eg. `stow nvim`
 ```

Examples:
- `stow zsh` will symlink the `.zshrc` file to the home directory `~/.zshrc` as the config file is nested directly under the `./zsh` folder in this repo
- `stow ghostty` will symlink the `config` file to `~/.config/ghostty` as the config file is nested under `./ghostty/.config/ghostty`

## Note

Once the symlinks are set for a given app, then the config files can be edited either in this repo or in the target location as the symlinks are bi-directional.