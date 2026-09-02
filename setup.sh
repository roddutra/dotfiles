#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$repo_root"

if [[ $(uname -s) == Darwin ]]; then
  zsh_root="$repo_root/packages/macos/zsh"

  if [[ ! -f "$zsh_root/.zshrc" ]]; then
    cp "$zsh_root/.zshrc.template" "$zsh_root/.zshrc"
    echo "Created local macOS .zshrc from its template."
  fi

  if [[ ! -f "$zsh_root/.zsh-secrets" ]]; then
    cp "$zsh_root/.zsh-secrets.example" "$zsh_root/.zsh-secrets"
    echo "Created local macOS .zsh-secrets from its template."
  fi
fi

if [[ -d .git ]]; then
  mkdir -p .git/hooks
  cat > .git/hooks/pre-commit <<'HOOK'
#!/usr/bin/env bash
set -e

if command -v gitleaks >/dev/null 2>&1; then
  gitleaks git --staged --no-banner --redact
else
  echo "Warning: gitleaks is not installed. Skipping secret scan." >&2
fi
HOOK
  chmod +x .git/hooks/pre-commit
  echo "Installed the gitleaks pre-commit hook."
fi

"$repo_root/scripts/apply-dotfiles"

echo "Dotfiles setup complete."
if [[ $(uname -s) == Darwin ]]; then
  echo "Edit ~/.zsh-secrets, then restart the terminal or source ~/.zshrc."
else
  echo "Run ./scripts/bootstrap-omarchy to restore curated Omarchy software."
fi
