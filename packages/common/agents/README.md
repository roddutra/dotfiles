# Shared agent configuration

The `agents` package links `.agents/` into `~/.agents/`. `AGENTS.md` is the canonical global instruction file. Claude Code reads the same instructions through `packages/common/claude/.claude/CLAUDE.md`.

Shared skills live in `.agents/skills/`. Most are linked into Claude's package, and Grok reads them through `[skills].paths` in `packages/common/grok/.grok/config.toml`.

Skills that invoke the Claude Code CLI, including `claude-reviewer`, `delegate-to-claude`, and workflows built on them, are `.agents`-only. Never link them into `.claude/skills/`: Claude Code would discover skills that delegate back to itself. Their shared wrapper library lives in `.agents/lib/`, outside the skill discovery directory.

This maintainer file is excluded through `.stow-local-ignore`.

## Herdr

The Herdr binary manages its skill and integration hooks. They remain untracked because updates rewrite them.

Install or refresh them from the repository root:

```sh
herdr integration
mkdir -p packages/common/agents/.agents/skills/herdr
herdr --skill > packages/common/agents/.agents/skills/herdr/SKILL.md
ln -sfn ../../../agents/.agents/skills/herdr packages/common/claude/.claude/skills/herdr
./scripts/apply-dotfiles
```

Repeat the `herdr --skill` command after `herdr update`. See <https://herdr.dev/docs/agent-skill/>.
