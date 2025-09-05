eval "$(/opt/homebrew/bin/brew shellenv)"

# Setup Oh My Posh, skipping Apple Terminal
if [ "$TERM_PROGRAM" != "Apple_Terminal" ]; then
  # eval "$(oh-my-posh init zsh)"
  eval "$(oh-my-posh init zsh --config $HOME/.config/ohmyposh/roddutra.yaml)"
  # eval "$(oh-my-posh init zsh --config $HOME/.config/ohmyposh/zen.toml)"
fi

# Set the directory we want to store zinit and plugins
ZINIT_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}/zinit/zinit.git"

# Download Zinit, if it's not there yet
if [ ! -d "$ZINIT_HOME" ]; then
  mkdir -p "$(dirname $ZINIT_HOME)"
  git clone https://github.com/zdharma-continuum/zinit.git "$ZINIT_HOME"
fi

# Source/Load zinit
source "${ZINIT_HOME}/zinit.zsh"

# Add in zsh plugins with zinit
zinit light zsh-users/zsh-syntax-highlighting
zinit light zsh-users/zsh-completions
zinit light zsh-users/zsh-autosuggestions
zinit light Aloxaf/fzf-tab

# Add in snippets
zinit snippet OMZL::git.zsh
zinit snippet OMZP::git
zinit snippet OMZP::aws
zinit snippet OMZP::command-not-found

# Load completions
autoload -Uz compinit && compinit

zinit cdreplay -q

# History
HISTSIZE=5000
HISTFILE=~/.zsh_history
SAVEHIST=$HISTSIZE
HISTDUP=erase
setopt appendhistory
setopt sharehistory
setopt hist_ignore_space
setopt hist_ignore_all_dups
setopt hist_save_no_dups
setopt hist_ignore_dups
setopt hist_find_no_dups

# Aliases
alias ls='ls --color'
alias python='python3'
alias pip='pip3'
alias lg='lazygit'

# Custom Functions
# Brew bundle dump without VSCode extensions
# This prevents VSCode extensions from cluttering the Brewfile
# VSCode extensions should be managed through VSCode's built-in sync
brew-dump() {
    echo "Dumping Homebrew packages..."
    brew bundle dump --describe --force --file=~/dotfiles/homebrew/Brewfile
    # Remove all vscode lines from the Brewfile
    sed -i '' '/^vscode /d' ~/dotfiles/homebrew/Brewfile
    echo "✓ Brewfile updated (VSCode extensions excluded)"
}

# Completion styling
zstyle ':completion:*' matcher-list 'm:{a-z}={A-Za-z}'
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"
zstyle ':completion:*' menu no
zstyle ':fzf-tab:complete:cd:*' fzf-preview 'ls --color $realpath'
zstyle ':fzf-tab:complete:__zoxide_z:*' fzf-preview 'ls --color $realpath'

# NVM
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion

# Python & UV
eval "$(uv generate-shell-completion zsh)"
eval "$(uvx --generate-shell-completion zsh)"

# PHP & Laravel
export PATH="/Users/roddutra/.config/herd-lite/bin:$PATH"
export PHP_INI_SCAN_DIR="/Users/roddutra/.config/herd-lite/bin:$PHP_INI_SCAN_DIR"

# Shell integrations
source <(fzf --zsh)
eval "$(zoxide init --cmd cd zsh)"

# Herd injected PHP 8.4 configuration.
export HERD_PHP_84_INI_SCAN_DIR="/Users/roddutra/Library/Application Support/Herd/config/php/84/"

# Herd injected PHP binary.
export PATH="/Users/roddutra/Library/Application Support/Herd/bin/":$PATH
