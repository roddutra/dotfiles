#!/usr/bin/env python3
"""List the models the installed Grok CLI accepts and its default model.

Shared by the Grok skills; each exposes it as scripts/list_models.py.

Wraps `grok models`, which sends no prompt and costs no tokens. That command
has no JSON output, so its text is parsed here. It does not report reasoning
effort levels; Grok itself rejects an unsupported --reasoning-effort and lists
the levels the model accepts.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_RE = re.compile(r"^\s*Default model:\s*(\S+)", re.MULTILINE)
ENTRY_RE = re.compile(r"^\s*(?:[*-]\s+)?(\S+)(?:\s+\(([^)]*)\))?\s*$")


def project_root() -> Path:
    try:
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    except FileNotFoundError:
        return Path.cwd()
    return Path(result.stdout.strip()) if result.returncode == 0 else Path.cwd()


def parse(output: str) -> dict:
    default = DEFAULT_RE.search(output)
    models = []
    lines = output.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip().rstrip(":").lower() == "available models")
    except StopIteration:
        start = None
    if start is not None:
        for line in lines[start + 1 :]:
            if not line.strip():
                if models:
                    break
                continue
            match = ENTRY_RE.match(line)
            if not match:
                break
            models.append(match.group(1))
    if default is None or not models:
        raise ValueError("unrecognized `grok models` output")
    result = {"default": {"model": default.group(1)}, "models": models}
    if "not authenticated" in output.lower():
        result["note"] = "Grok is not signed in, so only the fallback model is listed"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--timeout", type=int, default=60, help="Seconds to wait for grok (default: 60)")
    args = parser.parse_args()
    env = {**os.environ, "GROK_DISABLE_AUTOUPDATER": "1"}
    try:
        completed = subprocess.run(
            ["grok", "models"],
            cwd=project_root(),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
    except FileNotFoundError:
        print("Error: Grok CLI was not found", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"Error: `grok models` timed out after {args.timeout} seconds", file=sys.stderr)
        sys.exit(1)
    output = completed.stdout + "\n" + completed.stderr
    if completed.returncode:
        print(f"Error: `grok models` exited {completed.returncode}: {output.strip()[-500:]}", file=sys.stderr)
        sys.exit(1)
    try:
        result = parse(output)
    except ValueError as error:
        print(f"Error: {error}:\n{output.strip()[-500:]}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
