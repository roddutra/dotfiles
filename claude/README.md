# Claude Code Configuration

This directory contains configuration files for [Claude Code](https://claude.com/claude-code) and related Claude AI tools.

## Directory Structure

```
claude/
├── .claude/                    # Claude Code project configs
│   ├── agents/                # Custom agents (version controlled)
│   ├── commands/              # Slash commands (version controlled)
│   ├── hooks/                 # Event hooks (version controlled)
│   └── skills/                # Custom skills (version controlled)
├── .mcp.json                  # MCP server configurations (version controlled)
├── .stow-local-ignore         # Files to exclude from symlinking
└── README.md                  # This file
```

## What Gets Version Controlled

### ✅ Version Controlled (committed to GitHub):
- `.claude/agents/` - Custom agent definitions
- `.claude/commands/` - Custom slash commands
- `.claude/hooks/` - Event hooks (e.g., pre-commit, user-prompt-submit)
- `.claude/skills/` - Custom skills and workflows
- `.mcp.json` - MCP server configurations (uses environment variable expansion)
- `README.md` - Documentation

### ❌ NOT Version Controlled (gitignored):
- All other files/directories within `.claude/` - These contain:
  - Session history and state
  - Cached data
  - User-specific preferences
  - Potentially sensitive information

This is configured in the main `.gitignore`:
```gitignore
claude/.claude/*
!claude/.claude/agents/
!claude/.claude/commands/
!claude/.claude/hooks/
!claude/.claude/skills/
```

## MCP Server Configuration

The `.mcp.json` file contains Model Context Protocol (MCP) server configurations. This file uses **environment variable expansion** (e.g., `${BRAVE_API_KEY}`) to avoid committing API keys and secrets to version control.

### Prerequisites

Before using the MCP configurations, ensure you have set the required environment variables in your shell. See the [Managing Sensitive Environment Variables](../README.md#managing-sensitive-environment-variables) section in the main README for instructions.

**Required environment variables for the included MCP servers:**
- `CONTEXT7_API_KEY` - For the Context7 MCP server
- `BRAVE_API_KEY` - For the Brave Search MCP server

Add these to your `~/.zshrc.local` file:
```shell
export CONTEXT7_API_KEY="your_context7_api_key"
export BRAVE_API_KEY="your_brave_api_key"
```

### Usage Method 1: Global Configuration (All Projects)

To use these MCP servers across **all** Claude Code projects on your machine:

1. Open your global Claude configuration file:
   ```shell
   nvim ~/.claude.json
   ```

2. Copy the `mcpServers` object from this `.mcp.json` file and paste it into your `~/.claude.json` file

3. **IMPORTANT**: Replace the environment variable placeholders with your actual API keys:
   ```json
   {
     "mcpServers": {
       "context7": {
         "type": "http",
         "url": "https://mcp.context7.com/mcp",
         "headers": {
           "CONTEXT7_API_KEY": "your_api_key"
         }
       },
       "brave-search": {
         "type": "stdio",
         "command": "npx",
         "args": ["-y", "@brave/brave-search-mcp-server"],
         "env": {
           "BRAVE_API_KEY": "your_api_key"
         }
       }
     }
   }
   ```

   **Why?** Environment variable expansion (`${VAR_NAME}`) only works in project-level `.mcp.json` files, not in the global `~/.claude.json` file.

### Usage Method 2: Project-Specific Configuration

To use these MCP servers in a **specific project only**:

1. Copy the entire `.mcp.json` file to your project's root directory:
   ```shell
   cp ~/dotfiles/claude/.mcp.json /path/to/your/project/
   ```

2. Ensure the required environment variables are set in your shell (see Prerequisites above)

3. The environment variables will be automatically expanded when Claude Code reads the file

**Benefits of this method:**
- Environment variable expansion works automatically
- Keeps API keys out of the config file
- Different projects can use different MCP server configurations
- Safe to commit to version control (as long as you use `${VAR_NAME}` syntax)

## Using with GNU Stow

The `.mcp.json` and `README.md` files are excluded from symlinking via `.stow-local-ignore`. When you run `stow claude`, only the `.claude/` directory contents will be symlinked to `~/.claude/`.

This is intentional:
- **`.mcp.json`**: Should be copied to specific projects or `~/.claude.json`, not symlinked to your home directory
- **`README.md`**: Documentation for the repo, not needed in your home directory

## Available MCP Servers

The included `.mcp.json` configures the following MCP servers:

1. **context7** - Access up-to-date library documentation
2. **fetch** - Fetch and process web content with a flag to ignore the website's robots.txt file
3. **brave-search** - Search the web using Brave Search API

Refer to the `.mcp.json` file for the complete configuration details.
