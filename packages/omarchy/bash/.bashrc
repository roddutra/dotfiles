# Omarchy environment (OMARCHY_PATH + PATH), needed even for non-interactive shells
[[ -r /usr/share/omarchy/default/bash/env-bootstrap ]] && source /usr/share/omarchy/default/bash/env-bootstrap

# Lerd's PHP/Composer/Node shims must also be available to non-interactive
# shells (Make recipes, agent commands, and login-shell subprocesses).
export PATH="$HOME/.local/share/lerd/bin:$PATH"
# Use sharp's prebuilt package rather than Omarchy's system libvips source path.
export SHARP_IGNORE_GLOBAL_LIBVIPS=1

# OMP cannot infer whether Herdr's Kitty graphics renderer is enabled.
# This matches ~/.config/herdr/config.toml and restores inline image previews.
if [[ ${HERDR_ENV:-} == 1 ]]; then
  export PI_FORCE_IMAGE_PROTOCOL=kitty
fi

# If not running interactively, don't do anything else (leave this above the rc source)
[[ $- != *i* ]] && return

# All the default Omarchy aliases and functions
# (don't mess with these directly, just overwrite them here!)
source "$OMARCHY_PATH/default/bash/rc"

# Add your own exports, aliases, and functions here.
alias cc='claude'
alias ccd='claude --dangerously-skip-permissions'
alias cca='claude --enable-auto-mode'
alias cc-viewer='npx @kimuson/claude-code-viewer@latest --port 3400'
alias tree='eza --tree --icons'

# Enable Claude Code task tool
export CLAUDE_CODE_ENABLE_TODO_TOOLS=1

# Keep Pi Markdown Preview images below Herdr's 30 MiB graphics-transaction
# budget. Scale 2 produces 2400px-wide decoded PNGs that long previews exceed.
export PI_MARKDOWN_PREVIEW_DEVICE_SCALE_FACTOR=1

export PATH="$HOME/.config/composer/vendor/bin:$PATH"

# pnpm
export PNPM_HOME="$HOME/.local/share/pnpm"
case ":$PATH:" in
  *":$PNPM_HOME/bin:"*) ;;
  *) export PATH="$PNPM_HOME/bin:$PATH" ;;
esac
# pnpm end
