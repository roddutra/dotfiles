# ============================================================================
# ZSH Configuration Loader
# ============================================================================
# This file sources modular zsh configuration files:
#   - .zsh-settings: Curated shell settings (themes, plugins, aliases, etc.)
#   - .zsh-secrets:  Sensitive environment variables (API keys, tokens, etc.)
#
# Tools like NVM, pnpm, Herd, etc. will auto-append their configs below.
# These auto-generated configs are NOT version controlled (git assume-unchanged).
# ============================================================================

# Load curated shell settings
[ -f ~/.zsh-settings ] && source ~/.zsh-settings

# Load sensitive environment variables
[ -f ~/.zsh-secrets ] && source ~/.zsh-secrets

# ============================================================================
# Auto-generated tool configurations will appear below this line
# ============================================================================
