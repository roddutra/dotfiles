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

## Apply

From the repository root:

```sh
./scripts/apply-dotfiles
```

`.stow-local-ignore` prevents this README and `.mcp.json` from reaching the home directory.
