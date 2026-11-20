#!/usr/bin/env python3
"""Set up and inspect the video-watcher configuration.

  config.py show                      resolved settings and where each came from
  config.py init --scope global       create or update the global file
  config.py init --scope project      add overrides to the project's .env
  config.py set-key --scope global    store the API key without showing it
  config.py check                     confirm the key, endpoint and model work

The key is never accepted as an argument and never printed. `set-key` reads it
from standard input, or prompts without echo when run in a terminal.
"""

import argparse
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path

import settings
from providers import ProviderError, make_adapter
from session_paths import git_worktree_root

GLOBAL_TEMPLATE = """\
# video-watcher skill: machine-wide defaults.
# A project's .env or .env.local, and environment variables, override these
# one setting at a time.

# gemini | openrouter | openai-compatible
VIDEO_WATCHER_PROVIDER=
# Model id as the provider names it (list_models.py lists them)
VIDEO_WATCHER_MODEL=
VIDEO_WATCHER_API_KEY=
# Endpoint override; required for openai-compatible
# VIDEO_WATCHER_BASE_URL=
# Global file only: a command that prints the key, used when no key is set
# VIDEO_WATCHER_API_KEY_CMD=
"""


def emit(payload: dict, code: int = 0) -> None:
    print(json.dumps(payload, indent=2))
    sys.exit(code)


def fail(code: str, message: str, exit_code: int = 1, **extra) -> None:
    emit({"ok": False, "error": {"code": code, "message": message, **extra}}, exit_code)


def format_value(value: str) -> str:
    if any(ch in value for ch in " #\"'") and "'" not in value:
        return f"'{value}'"
    return value


def set_values(text: str, values: dict) -> str:
    """Set NAME=value lines, reusing an existing or commented-out line."""
    lines = text.splitlines()
    for name, value in values.items():
        full = f"{settings.PREFIX}{name}"
        new_line = f"{full}={format_value(value)}"
        active = [i for i, line in enumerate(lines) if line.strip().removeprefix("export ").startswith(f"{full}=")]
        commented = [i for i, line in enumerate(lines) if line.strip().lstrip("#").strip().startswith(f"{full}=")]
        if active:
            lines[active[0]] = new_line
        elif commented:
            lines[commented[0]] = new_line
        else:
            lines.append(new_line)
    return "\n".join(lines) + "\n"


def write_private(path: Path, text: str) -> None:
    """Write through a temp file so a failure cannot truncate the original."""
    temp = path.with_name(path.name + ".tmp")
    descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(text)
    temp.replace(path)


def git_state(path: Path) -> str:
    """'outside', 'tracked', 'ignored' or 'untracked' for a file."""
    directory = path.parent
    if git_worktree_root(directory) is None:
        return "outside"

    def run(*args: str) -> int:
        return subprocess.run(["git", *args], cwd=directory, capture_output=True).returncode

    if run("ls-files", "--error-unmatch", path.name) == 0:
        return "tracked"
    if run("check-ignore", "-q", path.name) == 0:
        return "ignored"
    return "untracked"


def project_file(args) -> Path:
    if args.file:
        return Path(args.file).expanduser().resolve()
    root = git_worktree_root() or Path.cwd()
    return (root / ".env").resolve()


def chosen_values(args) -> dict:
    values = {}
    if args.provider:
        if args.provider not in settings.PROVIDERS:
            fail("unknown_provider", f"Use one of: {', '.join(settings.PROVIDERS)}.")
        values["PROVIDER"] = args.provider
    if args.model:
        values["MODEL"] = args.model
    if args.base_url:
        values["BASE_URL"] = args.base_url.rstrip("/")
    return values


def cmd_init(args) -> None:
    values = chosen_values(args)
    if args.scope == "global":
        path = settings.global_config_path()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        created = not path.exists()
        text = GLOBAL_TEMPLATE if created else path.read_text()
        write_private(path, set_values(text, values) if values else text)
        os.chmod(path, 0o600)
        emit({
            "ok": True,
            "scope": "global",
            "path": str(path),
            "created": created,
            "set": sorted(f"{settings.PREFIX}{name}" for name in values),
            "next": f"Add the key: run `python3 {Path(__file__).resolve()} set-key --scope global` "
                    "in a terminal, or edit the file.",
        })

    path = project_file(args)
    if not values:
        fail("nothing_to_set", "Pass at least one of --provider, --model, --base-url for a project override.")
    if path.exists() and not path.is_file():
        fail(
            "not_a_regular_file",
            f"{path} is not a regular file (a mounted secrets file, perhaps), so it cannot be edited here. "
            "Pass --file with another file such as .env.local.",
        )
    state = git_state(path)
    notes = []
    if state == "tracked":
        notes.append(f"{path.name} is tracked by git, so never put the key in it. Keep the key in the "
                     "global file or in an ignored file such as .env.local.")
    elif state == "untracked":
        notes.append(f"{path.name} is not ignored by git. Add it to .gitignore before putting a key in it.")
    created = not path.exists()
    text = "" if created else path.read_text()
    if text and not text.endswith("\n"):
        text += "\n"
    if not any(line.strip().removeprefix("export ").startswith(settings.PREFIX) for line in text.splitlines()):
        text += ("\n" if text else "") + "# video-watcher skill overrides (unset values fall back to the global config)\n"
    path.write_text(set_values(text, values))
    emit({
        "ok": True,
        "scope": "project",
        "path": str(path),
        "created": created,
        "git": state,
        "set": sorted(f"{settings.PREFIX}{name}" for name in values),
        "notes": notes,
    })


def cmd_set_key(args) -> None:
    if args.scope == "global":
        path = settings.global_config_path()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    else:
        path = project_file(args)
        state = git_state(path)
        if state in ("tracked", "untracked"):
            fail(
                "unsafe_key_location",
                f"{path} is {'tracked by' if state == 'tracked' else 'not ignored by'} git, so a key there "
                "could be committed. Use --scope global, or --file with a git-ignored file such as .env.local.",
            )
    if sys.stdin.isatty():
        key = getpass.getpass("API key (input hidden): ")
    else:
        key = sys.stdin.read()
    key = key.strip()
    if not key or any(ch.isspace() for ch in key):
        fail("invalid_key", "No key was provided, or it contains whitespace.")
    if path.exists():
        text = path.read_text()
    else:
        text = GLOBAL_TEMPLATE if args.scope == "global" else ""
    write_private(path, set_values(text, {"API_KEY": key}))
    os.chmod(path, 0o600)
    emit({"ok": True, "scope": args.scope, "path": str(path), "set": [f"{settings.PREFIX}API_KEY"]})


def resolve_or_fail(args, require) -> settings.Resolved:
    flags = {"PROVIDER": args.provider, "MODEL": args.model, "BASE_URL": args.base_url}
    try:
        return settings.resolve(flags, require=require)
    except settings.ConfigError as exc:
        fail(exc.code, exc.message, exit_code=2, missing=exc.missing)


def cmd_show(args) -> None:
    flags = {"PROVIDER": args.provider, "MODEL": args.model, "BASE_URL": args.base_url}
    try:
        resolved = settings.resolve(flags, require=())
    except settings.ConfigError as exc:
        fail(exc.code, exc.message, exit_code=2, missing=exc.missing)
    summary = resolved.describe()
    missing = []
    if not resolved.provider:
        missing.append(f"{settings.PREFIX}PROVIDER")
    if not resolved.model:
        missing.append(f"{settings.PREFIX}MODEL")
    if not resolved.api_key and (not resolved.provider or settings.PROVIDERS[resolved.provider]["key_required"]):
        missing.append(f"{settings.PREFIX}API_KEY")
    if resolved.provider and not resolved.base_url:
        missing.append(f"{settings.PREFIX}BASE_URL")
    emit({"ok": True, "ready": not missing, "missing": missing, **summary})


def cmd_check(args) -> None:
    resolved = resolve_or_fail(args, ("provider", "model", "api_key"))
    adapter = make_adapter(resolved)
    try:
        limits = adapter.model_limits()
    except ProviderError as exc:
        fail("provider_error", exc.message, exit_code=4, status=exc.status, **resolved.describe())
    if limits is None:
        fail(
            "model_not_listed",
            f"The endpoint answered, but {resolved.model!r} is not in its model list.",
            exit_code=4,
            **resolved.describe(),
        )
    emit({"ok": True, "model_limits": limits, **resolved.describe()})


def main():
    parser = argparse.ArgumentParser(description="Configure the video-watcher skill")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_value_flags(target):
        target.add_argument("--provider", help="gemini | openrouter | openai-compatible")
        target.add_argument("--model", help="Model id as the provider names it")
        target.add_argument("--base-url", help="Endpoint override")

    init = sub.add_parser("init", help="Create or update a config file (never the key)")
    init.add_argument("--scope", choices=("global", "project"), required=True)
    init.add_argument("--file", help="Project scope: file to write (default: .env at the git root)")
    add_value_flags(init)
    init.set_defaults(func=cmd_init)

    set_key = sub.add_parser("set-key", help="Store the API key from stdin or a hidden prompt")
    set_key.add_argument("--scope", choices=("global", "project"), required=True)
    set_key.add_argument("--file", help="Project scope: a git-ignored file to write")
    set_key.set_defaults(func=cmd_set_key)

    show = sub.add_parser("show", help="Print the resolved settings and their sources")
    add_value_flags(show)
    show.set_defaults(func=cmd_show)

    check = sub.add_parser("check", help="Confirm the key, endpoint and model with a live call")
    add_value_flags(check)
    check.set_defaults(func=cmd_check)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
