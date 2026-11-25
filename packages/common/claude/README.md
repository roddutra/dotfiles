# Claude Code configuration

This package links reviewed Claude Code configuration into `~/.claude/`.

Tracked content:

- `.claude/CLAUDE.md` links to the shared `AGENTS.md`.
- `.claude/agents/` contains custom agent definitions.
- `.claude/commands/` contains slash commands.
- `.claude/hooks/` contains event hooks.
- `.claude/skills/` contains Claude-only skills and links to shared skills.

Session history, caches, credentials, and other runtime data remain local through the root `.gitignore` allowlist.

## MCP configuration

`.mcp.json` is maintainer configuration and is excluded from Stow. Copy it into a project that should use those MCP servers:

```sh
cp ~/dotfiles/packages/common/claude/.mcp.json /path/to/project/.mcp.json
```

Project-level configuration expands environment variables such as `${CONTEXT7_API_KEY}` and `${BRAVE_API_KEY}`. Keep their values in the machine's secret store or shell secrets, never in this repository.

Configured servers are documented directly in `.mcp.json`.

## skill-creator

`.claude/skills/skill-creator/` is Anthropic's skill from `anthropics/skills` (`skills/skill-creator`), matching upstream as of 16 November 2026 apart from one local patch.

`scripts/run_eval.py` runs each trigger-test query in its own empty temporary project. Upstream runs them all in one project, so parallel runs see each other's temporary command files and score real triggers as misses (upstream issue #1352, open fixes in pull requests #908 and #2198). Drop the patch when upstream merges a fix, and reapply it after any sync before then.

The trigger test still under-reports when the skill being tested is already installed, because the agent can pick the installed copy over the test copy. Move the skill's link out of `~/.claude/skills/` for the run and put it back afterwards.

## Apply

From the repository root:

```sh
./scripts/apply-dotfiles
```

`.stow-local-ignore` prevents this README and `.mcp.json` from reaching the home directory.
