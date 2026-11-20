#!/usr/bin/env python3
"""Local facts about a video file, and the cache of uploads kept on a provider."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from session_paths import REMOTE_FILES_PATH, ensure_store


@dataclass
class Video:
    path: Path

    @cached_property
    def size(self) -> int:
        return self.path.stat().st_size

    @cached_property
    def sha256(self) -> str:
        digest = hashlib.sha256()
        with self.path.open("rb") as handle:
            for block in iter(lambda: handle.read(4 * 1024 ** 2), b""):
                digest.update(block)
        return digest.hexdigest()

    @cached_property
    def duration(self) -> float | None:
        """Length in seconds from ffprobe, or None when ffprobe is unavailable."""
        if shutil.which("ffprobe") is None:
            return None
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(self.path)],
                capture_output=True, text=True, timeout=60,
            )
            return float(result.stdout.strip())
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None


def parse_timestamp(value: str | None) -> float | None:
    """Accept seconds ("90", "12.5") or clock time ("1:30", "01:02:03")."""
    if value is None:
        return None
    parts = value.strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"Not a timestamp: {value!r}")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    if seconds < 0:
        raise ValueError(f"Negative timestamp: {value!r}")
    return seconds


def format_timestamp(seconds: float) -> str:
    whole = int(seconds)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def remote_key(adapter: str, base_url: str, key_fingerprint: str, sha256: str) -> str:
    """Cache key for an upload: only the same service, account and bytes may reuse it."""
    return hashlib.sha256(f"{adapter}|{base_url}|{key_fingerprint}|{sha256}".encode()).hexdigest()


def load_remote_files() -> dict:
    try:
        return json.loads(REMOTE_FILES_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def save_remote_files(entries: dict) -> None:
    """Replace the cache atomically. Each writer uses its own temp file, so
    parallel runs never collide; the last writer wins, which only costs a
    re-upload check later."""
    ensure_store()
    descriptor, temp_name = tempfile.mkstemp(dir=REMOTE_FILES_PATH.parent, prefix=".remote-files-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(json.dumps(entries, indent=2))
        os.replace(temp_name, REMOTE_FILES_PATH)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
