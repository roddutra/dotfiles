# Shared agent configuration

`stow agents` symlinks `.agents/` into `~/.agents/`. `AGENTS.md` is the canonical global instruction file. `claude/.claude/CLAUDE.md` links to it so Claude Code reads the same instructions.

Shared skills also live in `.agents/skills/`. Claude links to them from `claude/.claude/skills/`; Grok reads them through `[skills].paths` in `grok/.grok/config.toml`. See the root README, section *Agent skills: one source of truth*.

This file holds maintenance notes for humans. It is excluded from stow via `agents/.stow-local-ignore`.

## herdr

Not version-controlled: the herdr skill (`agents/.agents/skills/herdr/`, symlinked as `claude/.claude/skills/herdr`) and its Claude hook (`claude/.claude/hooks/herdr-agent-state.sh`) are gitignored because the herdr binary manages them and rewrites them on update; tracking them caused conflicts between machines. They live in these paths on disk so the stow layout still exposes them to every agent.

Install/refresh on each machine:

```bash
herdr integration                                  # installs the hooks (Claude, Grok)
mkdir -p agents/.agents/skills/herdr
herdr --skill > agents/.agents/skills/herdr/SKILL.md
ln -sfn ../../../agents/.agents/skills/herdr claude/.claude/skills/herdr
stow -R claude agents
```

Repeat the `herdr --skill` step after `herdr update`. Upstream docs: <https://herdr.dev/docs/agent-skill/>.
