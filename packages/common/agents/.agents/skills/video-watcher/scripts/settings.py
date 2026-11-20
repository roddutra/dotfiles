#!/usr/bin/env python3
"""Configuration resolution for the video-watcher skill.

Four settings, with the same names in every layer:

  VIDEO_WATCHER_PROVIDER   gemini | openrouter | openai-compatible
  VIDEO_WATCHER_MODEL      model id as the provider names it
  VIDEO_WATCHER_API_KEY    secret
  VIDEO_WATCHER_BASE_URL   optional endpoint override

Layers, highest priority first, merged per setting:

  1. command-line flags
  2. process environment
  3. .env.local then .env in the invocation directory
  4. .env.local then .env at the git work tree root (when different)
  5. the global file, ~/.config/video-watcher/config.env
  6. the provider's built-in base URL

A project that sets only the model therefore inherits the provider and key
from the global file. Only VIDEO_WATCHER_* names are read from a .env file;
nothing else in it is loaded or exported.

VIDEO_WATCHER_API_KEY_CMD (a command that prints the key) is honoured in the
global file only, because a project file must not be able to run commands.
"""

import hashlib
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from session_paths import git_worktree_root

PREFIX = "VIDEO_WATCHER_"
SETTINGS = ("PROVIDER", "MODEL", "API_KEY", "BASE_URL")
KEY_COMMAND = "API_KEY_CMD"

# Built-in providers. `adapter` names the module in providers/ that speaks the
# protocol. A provider with no base_url needs VIDEO_WATCHER_BASE_URL.
PROVIDERS = {
    "gemini": {
        "adapter": "gemini",
        "base_url": "https://generativelanguage.googleapis.com",
        "key_required": True,
    },
    "openrouter": {
        "adapter": "openai_compat",
        "base_url": "https://openrouter.ai/api/v1",
        "key_required": True,
    },
    "openai-compatible": {
        "adapter": "openai_compat",
        "base_url": None,
        "key_required": False,
    },
}


class ConfigError(Exception):
    """A configuration problem the caller can act on."""

    def __init__(self, code: str, message: str, missing: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.missing = missing or []


@dataclass
class Resolved:
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    sources: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    files: list = field(default_factory=list)

    @property
    def adapter(self) -> str | None:
        return PROVIDERS[self.provider]["adapter"] if self.provider in PROVIDERS else None

    @property
    def key_fingerprint(self) -> str:
        """Short, non-reversible id of the key, for scoping cached uploads."""
        return hashlib.sha256((self.api_key or "").encode()).hexdigest()[:12]

    def describe(self) -> dict:
        """Everything about the resolved config that is safe to print."""
        return {
            "provider": {"value": self.provider, "source": self.sources.get("PROVIDER")},
            "model": {"value": self.model, "source": self.sources.get("MODEL")},
            "base_url": {"value": self.base_url, "source": self.sources.get("BASE_URL")},
            "api_key": {"set": bool(self.api_key), "source": self.sources.get("API_KEY")},
            "files": self.files,
            "notes": self.notes,
        }


def global_config_path(environ=None) -> Path:
    environ = os.environ if environ is None else environ
    base = environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "video-watcher" / "config.env"


def parse_dotenv(text: str) -> dict:
    """Read VIDEO_WATCHER_* assignments from dotenv text. Other names are ignored.

    Supports `export NAME=value`, single or double quotes, and a trailing
    ` # comment` after an unquoted value. No interpolation or multi-line values.
    """
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        name, sep, value = line.partition("=")
        name = name.strip()
        if not sep or not name.startswith(PREFIX):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            hash_at = value.find(" #")
            if hash_at != -1:
                value = value[:hash_at].rstrip()
        values[name[len(PREFIX):]] = value
    return values


def _read_env_file(path: Path) -> dict | None:
    try:
        return parse_dotenv(path.read_text())
    except (OSError, UnicodeDecodeError):
        return None


def project_env_files(cwd: Path | None = None) -> list[Path]:
    """Candidate project files, highest priority first."""
    cwd = (cwd or Path.cwd()).resolve()
    directories = [cwd]
    root = git_worktree_root(cwd)
    if root is not None and root.resolve() != cwd:
        directories.append(root.resolve())
    return [directory / name for directory in directories for name in (".env.local", ".env")]


def _run_key_command(command: str) -> str:
    try:
        result = subprocess.run(shlex.split(command), capture_output=True, text=True, timeout=120)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise ConfigError("key_command_failed", f"{PREFIX}{KEY_COMMAND} could not run: {exc}") from exc
    if result.returncode != 0 or not result.stdout.strip():
        raise ConfigError(
            "key_command_failed",
            f"{PREFIX}{KEY_COMMAND} exited {result.returncode} without printing a key.",
        )
    return result.stdout.strip()


def collect_layers(flags: dict | None = None, environ=None, cwd: Path | None = None):
    """Return (layers, files, notes). Each layer is (source label, values)."""
    environ = os.environ if environ is None else environ
    notes, files, layers = [], [], []

    flag_values = {name: value for name, value in (flags or {}).items() if value}
    layers.append(("flag", flag_values))

    env_values = {
        name[len(PREFIX):]: value
        for name, value in environ.items()
        if name.startswith(PREFIX) and value
    }
    if env_values.pop(KEY_COMMAND, None):
        notes.append(f"{PREFIX}{KEY_COMMAND} in the environment is ignored; it is honoured in the global file only.")
    layers.append(("environment", env_values))

    for path in project_env_files(cwd):
        # Not is_file(): a mounted secrets file can be a named pipe.
        exists = path.exists() and not path.is_dir()
        files.append({"path": str(path), "scope": "project", "exists": exists})
        if not exists:
            continue
        values = _read_env_file(path)
        if values is None:
            notes.append(f"Could not read {path}; skipped.")
            continue
        values = {name: value for name, value in values.items() if value}
        if values.pop(KEY_COMMAND, None):
            notes.append(f"{PREFIX}{KEY_COMMAND} in {path} is ignored; it is honoured in the global file only.")
        layers.append((f"project:{path}", values))

    global_path = global_config_path(environ)
    exists = global_path.is_file()
    files.append({"path": str(global_path), "scope": "global", "exists": exists})
    if exists:
        values = _read_env_file(global_path)
        if values is None:
            notes.append(f"Could not read {global_path}; skipped.")
        else:
            layers.append((f"global:{global_path}", {name: value for name, value in values.items() if value}))

    return layers, files, notes


def _is_loopback(host: str | None) -> bool:
    return host in ("localhost", "127.0.0.1", "::1")


def resolve(
    flags: dict | None = None,
    environ=None,
    cwd: Path | None = None,
    require: tuple = ("provider", "model", "api_key"),
) -> Resolved:
    """Merge the layers per setting and validate the result.

    `require` names what the caller needs. Raises ConfigError when something
    required is missing or the combination cannot work.
    """
    layers, files, notes = collect_layers(flags, environ, cwd)
    resolved = Resolved(files=files, notes=notes)
    found = {}
    for index, (source, values) in enumerate(layers):
        for name in SETTINGS:
            if name not in found and values.get(name):
                found[name] = (values[name], source, index)

    if "PROVIDER" in found:
        resolved.provider = found["PROVIDER"][0].strip().lower()
        resolved.sources["PROVIDER"] = found["PROVIDER"][1]
    if "MODEL" in found:
        resolved.model = found["MODEL"][0].strip()
        resolved.sources["MODEL"] = found["MODEL"][1]

    if resolved.provider is not None and resolved.provider not in PROVIDERS:
        raise ConfigError(
            "unknown_provider",
            f"Unknown provider {resolved.provider!r} (from {resolved.sources['PROVIDER']}). "
            f"Use one of: {', '.join(PROVIDERS)}.",
        )

    key_layer = None
    if "API_KEY" in found:
        resolved.api_key, resolved.sources["API_KEY"], key_layer = found["API_KEY"]
    else:
        for index, (source, values) in enumerate(layers):
            if source.startswith("global:") and values.get(KEY_COMMAND):
                resolved.api_key = _run_key_command(values[KEY_COMMAND])
                resolved.sources["API_KEY"] = f"{source} (command)"
                key_layer = index

    # A key belongs to the provider that was in effect where the key was set.
    # If a more local layer switched provider without supplying its own key,
    # sending the inherited key would hand it to the wrong service and fail.
    if resolved.api_key and resolved.provider:
        home_provider = next(
            (values["PROVIDER"].strip().lower() for _, values in layers[key_layer:] if values.get("PROVIDER")),
            None,
        )
        if home_provider and home_provider != resolved.provider:
            raise ConfigError(
                "key_provider_mismatch",
                f"Provider is {resolved.provider!r} (from {resolved.sources['PROVIDER']}) but the API key "
                f"comes from {resolved.sources['API_KEY']}, where the provider is {home_provider!r}. "
                f"Set {PREFIX}API_KEY alongside the provider override.",
            )

    if "BASE_URL" in found:
        resolved.base_url = found["BASE_URL"][0].strip().rstrip("/")
        resolved.sources["BASE_URL"] = found["BASE_URL"][1]
    elif resolved.provider and PROVIDERS[resolved.provider]["base_url"]:
        resolved.base_url = PROVIDERS[resolved.provider]["base_url"]
        resolved.sources["BASE_URL"] = "default"

    if resolved.base_url:
        parts = urlsplit(resolved.base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ConfigError("invalid_base_url", f"{PREFIX}BASE_URL is not an http(s) URL: {resolved.base_url}")
        if parts.scheme == "http" and not _is_loopback(parts.hostname):
            raise ConfigError(
                "insecure_base_url",
                f"{PREFIX}BASE_URL uses plain http for a remote host ({parts.hostname}); "
                "the key and the video would travel unencrypted. Use https.",
            )

    missing = []
    if "provider" in require and not resolved.provider:
        missing.append(f"{PREFIX}PROVIDER")
    if "model" in require and not resolved.model:
        missing.append(f"{PREFIX}MODEL")
    if resolved.provider:
        if not resolved.base_url:
            missing.append(f"{PREFIX}BASE_URL")
        if "api_key" in require and not resolved.api_key and PROVIDERS[resolved.provider]["key_required"]:
            missing.append(f"{PREFIX}API_KEY")
    if missing:
        raise ConfigError(
            "config_missing",
            "Missing configuration: " + ", ".join(missing)
            + ". Set provider, model or endpoint with config.py init, and the key with config.py set-key.",
            missing=missing,
        )
    return resolved
