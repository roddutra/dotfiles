# Zed Settings Synchronization Options

Status: Undecided. No option has been implemented.

## Problem

The tracked user settings file is linked from:

```text
packages/common/zed/.config/zed/settings.json
```

Zed writes temporary choices directly into that file. Current examples are:

- `vim_mode`
- `agent_servers.omp.default_config_options.model`

Those writes create changes in the dotfiles repository. Committing them propagates temporary choices to every machine; leaving them uncommitted causes the machines to drift.

The desired split is:

- Stable preferences remain tracked and synchronized.
- Temporary choices remain local to each machine.
- Normal Zed usage should create as little Git maintenance as possible.

## Zed constraints

Zed merges built-in defaults, user settings, and eligible project settings. It does not provide a documented `include`, `extends`, or `settings.local.json` directive for composing multiple user-level files.

Project settings are not a solution for these examples. `vim_mode` is global, and the OMP agent model belongs to the user-level agent server configuration.

The normal `workspace: toggle vim mode` action writes `vim_mode` back into the user settings file. Changing settings through the Settings Editor also saves to that file.

References:

- [Zed settings profiles](https://zed.dev/docs/reference/all-settings#settings-profiles)
- [Zed Vim toggle implementation](https://github.com/zed-industries/zed/blob/main/crates/vim/src/vim.rs)
- [Zed settings profile selector implementation](https://github.com/zed-industries/zed/blob/main/crates/settings_profile_selector/src/settings_profile_selector.rs)

## Option 1: Zed settings profiles

Keep the current tracked settings file and define named temporary profiles inside it:

```json
{
  "profiles": {
    "Vim with Terra": {
      "settings": {
        "vim_mode": true,
        "agent_servers": {
          "omp": {
            "default_config_options": {
              "model": "openai-codex/gpt-5.6-terra"
            }
          }
        }
      }
    },
    "Standard with Terra": {
      "settings": {
        "vim_mode": false,
        "agent_servers": {
          "omp": {
            "default_config_options": {
              "model": "openai-codex/gpt-5.6-terra"
            }
          }
        }
      }
    }
  }
}
```

Select a profile from the command palette with `settings profile selector: toggle`.

### How it works

- Profiles are tracked as part of the shared settings file.
- A selected profile temporarily overlays the normal user settings.
- Selecting a profile does not rewrite `settings.json`.
- Selecting `Disabled` returns to the normal user settings.
- The active selection is held in Zed's process state and should be expected to reset when Zed restarts.

### Pros

- Native Zed feature.
- No custom merge script.
- No generated file.
- Profile selection does not dirty the repository.
- Named combinations are explicit and easy to inspect.

### Cons

- Only one profile is active at a time.
- Independent Vim and model choices require a profile for every useful combination.
- The normal Vim toggle and settings controls still modify the tracked file.
- The active profile is not a durable per-machine preference.
- Frequently changing model choices can make the profile list large.

### Best fit

Use profiles when the number of combinations is small and selecting a named profile instead of using the normal controls is acceptable.

## Option 2: Tracked shared settings plus a local generated file

Move stable preferences into a tracked manifest and make Zed's live file machine-local:

```text
manifests/zed/settings.shared.json       # Tracked
~/.config/zed/settings.json              # Untracked, regular file
scripts/apply-zed-settings               # Tracked merge command
```

The Zed Stow package would continue managing portable assets such as themes, but it would stop linking `settings.json`.

### How it works

The merge command would:

1. Read the tracked shared settings.
2. Read the current live settings when present.
3. Capture an explicit allowlist of local values.
4. Build a new file from the shared settings.
5. Reapply the captured local values.
6. Write the live file atomically.

Initial local paths would be:

```text
vim_mode
agent_servers.omp.default_config_options.model
```

The command could run from `setup.sh` and after pulling shared settings. Zed would continue writing temporary changes to its normal live file, which would no longer be inside the Git repository.

### Pros

- Existing Vim and model controls continue to work normally.
- Temporary values remain independently local on every machine.
- Stable settings retain one tracked source of truth.
- No profile combinations are required.
- The local allowlist documents exactly which settings may drift.

### Cons

- Requires custom merge code and tests.
- The merge must handle nested objects correctly.
- JSON comments require a JSONC-aware parser or a policy that generated settings contain strict JSON.
- Running the merge can discard unlisted local changes.
- Shared updates reach a machine only after the merge command runs.
- Promoting a local change into shared settings is an explicit manual action.

### Best fit

Use this when normal Zed controls should remain unchanged and only a small, explicit set of settings should vary per machine. This most closely matches the current workflow.

## Option 3: Entire settings file remains local

Stop tracking and linking `settings.json`. Keep a tracked example or snapshot for rebuilding a machine manually.

### How it works

- Add the live settings file to the relevant Git and Stow ignores.
- Store a reviewed `settings.example.json` or setup note in the repository.
- Copy the example when provisioning a machine.
- Allow every machine to diverge afterward.

### Pros

- Simplest implementation.
- Zed can rewrite the file freely.
- No Git noise from temporary or permanent settings changes.
- No merge tooling or profile management.

### Cons

- Stable improvements no longer synchronize automatically.
- Machines can drift in settings that were intended to remain shared.
- Rebuilding the shared example requires manual comparison.
- The repository stops being the source of truth for active Zed settings.

### Best fit

Use this only if independent per-machine Zed configuration is more important than synchronization.

## Option 4: Git `skip-worktree`

Keep tracking the file but hide local modifications with:

```sh
git update-index --skip-worktree packages/common/zed/.config/zed/settings.json
```

### Pros

- Minimal setup.
- Local edits usually disappear from `git status`.
- No Zed or file-layout changes.

### Cons

- The flag exists only in each clone's local Git index.
- Pulling shared changes can fail or leave the file stale.
- Hidden changes are easy to forget.
- New machines require manual index configuration.
- This hides drift instead of defining which settings are local.

### Best fit

Not recommended. It is an index workaround, not configuration composition.

## Comparison

| Option | Normal Zed controls | Custom tooling | Stable settings sync | Main cost |
| --- | --- | --- | --- | --- |
| Settings profiles | No, use profile selector | None | Yes | Combination growth and session-only selection |
| Shared plus local merge | Yes | Required | Yes | Merge ownership and JSON handling |
| Entire file local | Yes | Minimal | No | Uncontrolled drift |
| `skip-worktree` | Yes | Git setup per clone | Unreliable | Hidden state and pull problems |

## Decision criteria

Choose settings profiles if native behavior and a small set of named combinations matter most.

Choose the shared plus local merge if normal Zed controls and explicit per-machine values matter most.

Choose an entirely local file only if cross-machine synchronization is no longer a goal.

Do not use `skip-worktree` as the long-term design.
