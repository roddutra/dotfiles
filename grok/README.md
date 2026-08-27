# Grok CLI Configuration

Config for the [Grok CLI](https://x.ai). `stow grok` symlinks the tracked files into `~/.grok/`.

## What is tracked

- `.grok/config.toml` — user config. The `[skills]` block points Grok at the shared skills in `~/.agents/skills` (see `stow agents`) and ignores `~/.claude/skills`, which Grok would otherwise scan by default.
- `.grok/skills/` — Grok-only skills (real directories). Anything shared with other agents belongs in `agents/.agents/skills/` instead; Grok already sees those via `[skills].paths`.
- `.grok/agents/` — Grok-only user-scoped agent definitions.

Everything else in `~/.grok/` (`auth.json`, `sessions/`, caches, `bundled/`, `vendor/`) is machine-local and gitignored via the allowlist in the root `.gitignore`.

## Hooks are intentionally untracked

`~/.grok/hooks/` must contain real files, not symlinks: Grok refuses to start any `--sandbox` profile when a hook source has a symlink component (it treats a retargetable hook as a sandbox escape). The `grok-reviewer` skill relies on `--sandbox read-only` for kernel-enforced read-only reviews, so the herdr hook (`herdr.json` + `herdr-agent-state.sh`) is installed directly by `herdr integration` and never stowed.

## Setup on a new machine

```shell
mkdir -p ~/.grok/skills   # so stow links files individually rather than folding whole dirs
cd ~/dotfiles
stow agents grok
herdr integration       # installs ~/.grok/hooks/ as real files (see below)
```

## After changing Grok settings

Grok saves `config.toml` by writing a new file over the path, which replaces the stow symlink with a plain file (confirmed on Linux). Pull the change back into the repo and relink with:

```shell
cd ~/dotfiles
stow --adopt grok
git diff grok/.grok/config.toml   # review, then commit
```
