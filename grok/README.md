# Grok CLI Configuration

Config for the [Grok CLI](https://x.ai). `stow grok` symlinks the tracked files into `~/.grok/`.

## What is tracked

- `.grok/config.toml` — user config. The `[skills]` block points Grok at the shared skills in `~/.agents/skills` (see `stow agents`) and ignores `~/.claude/skills`, which Grok would otherwise scan by default.
- `.grok/skills/` — Grok-only skills (real directories). Anything shared with other agents belongs in `agents/.agents/skills/` instead; Grok already sees those via `[skills].paths`.
- `.grok/agents/` — Grok-only user-scoped agent definitions.
- `.grok/hooks/` — herdr integration hook (installed by `herdr`; it overwrites this file on reinstall/update). `herdr.json` contains an absolute path to the hook script, so on a new machine either run the herdr integration installer or fix the path.

Everything else in `~/.grok/` (`auth.json`, `sessions/`, caches, `bundled/`, `vendor/`) is machine-local and gitignored via the allowlist in the root `.gitignore`.

## Setup on a new machine

```shell
mkdir -p ~/.grok/hooks ~/.grok/skills   # so stow links files individually rather than folding whole dirs
stow agents grok
```
