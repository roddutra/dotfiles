# Grok CLI configuration

The `grok` package links reviewed files into `~/.grok/`.

Tracked content:

- `.grok/config.toml` points Grok at shared skills in `~/.agents/skills`.
- `.grok/skills/` contains Grok-only skills.
- `.grok/agents/` contains Grok-only user agents.

Authentication, sessions, caches, bundled files, and vendor data remain machine-local through the root `.gitignore` allowlist.

## Hooks remain local

`~/.grok/hooks/` must contain real files. Grok rejects sandboxed profiles when a hook source has a symlink component. `herdr integration` therefore installs its Grok hooks directly instead of using Stow.

## Setup

```sh
./scripts/apply-dotfiles
herdr integration
```

## Capture a Grok setting change

Grok may replace the `config.toml` symlink with a regular file when it saves settings. Adopt only this package, then review the change:

```sh
stow --dir packages/common --target "$HOME" --no-folding --adopt grok
git diff -- packages/common/grok/.grok/config.toml
```

Do not use `--adopt` across every package.
