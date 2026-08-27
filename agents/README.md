# Shared agent skills

`stow agents` symlinks `.agents/` into `~/.agents/`, which is the canonical home for every skill shared across agents (Codex, Claude Code, Grok, Pi, ...). Claude links to these skills from `claude/.claude/skills/`; Grok reads them via `[skills].paths` in `grok/.grok/config.toml`. See the root README, section *Agent skills: one source of truth*.

This file holds maintenance notes for humans. It is excluded from stow via `agents/.stow-local-ignore`, and it lives at the package root rather than inside a skill directory because stow folds each skill into a single directory symlink, so anything inside a skill directory is visible to agents.

## herdr

#

`SKILL.md` is the release-matched copy printed by the installed herdr binary, not a hand-edited file. Upstream: <https://herdr.dev/docs/agent-skill/> (source at `skills/herdr/SKILL.md` in <https://github.com/herdrdev/herdr>).

### Updating after `herdr update`

```shell
cd ~/dotfiles
herdr --version                                   # note the new version
herdr --skill > agents/.agents/skills/herdr/SKILL.md
git diff --stat agents/.agents/skills/herdr       # sanity-check the change
git commit -am "chore(herdr): refresh skill for herdr <version>"
```

No re-stow is needed: every agent reads the skill through a symlink into this repo, so the new content is live immediately (`~/.agents/skills/herdr`, `~/.claude/skills/herdr`, `~/.codex/skills/herdr`; Grok via `[skills].paths` in `grok/.grok/config.toml`).

Do not edit `SKILL.md` by hand — the next refresh overwrites it. If a local tweak is ever needed, record it in this file and reapply after refreshing.

### Related

- `.skill-lock.json` in `agents/.agents/` records the upstream source (`herdrdev/herdr`) for `npx skills` tooling; `herdr --skill` is preferred over `npx skills update` because it always matches the installed binary.
- The herdr *integration hooks* (`claude/.claude/hooks/herdr-agent-state.sh`; `~/.grok/hooks/`, untracked — see `grok/README.md`) are separate from this skill and are managed by `herdr integration`.
