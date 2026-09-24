#!/usr/bin/env python3
"""List the models the installed Codex CLI accepts and its effective default.

Shared by the Codex skills; each exposes it as scripts/list_models.py.

Queries `codex app-server` over JSON-RPC (`config/read` and `model/list`), so
no prompt is sent and no tokens are spent. The default reflects the effective
config for the current project (user config, profiles, and project layers).
"""

import argparse
import json
import os
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path



class AppServer:
    def __init__(self, timeout: int) -> None:
        self.deadline = time.monotonic() + timeout
        self.stderr = tempfile.TemporaryFile()
        try:
            self.process = subprocess.Popen(
                ["codex", "app-server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self.stderr,
                start_new_session=True,
            )
        except FileNotFoundError:
            print("Error: Codex CLI was not found", file=sys.stderr)
            sys.exit(1)
        self.buffer = b""
        self.next_id = 0

    def notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method})

    def request(self, method: str, params: dict) -> dict:
        self.next_id += 1
        request_id = self.next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            message = self._read_message()
            if message.get("id") != request_id or "method" in message:
                continue
            if "error" in message:
                self._fail(f"{method} failed: {message['error'].get('message', message['error'])}")
            return message.get("result", {})

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.stderr.close()

    def _send(self, message: dict) -> None:
        try:
            self.process.stdin.write((json.dumps(message) + "\n").encode())
            self.process.stdin.flush()
        except BrokenPipeError:
            self._fail("codex app-server exited unexpectedly")

    def _read_message(self) -> dict:
        stdout = self.process.stdout.fileno()
        while b"\n" not in self.buffer:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                self._fail("timed out waiting for codex app-server")
            ready, _, _ = select.select([stdout], [], [], remaining)
            if not ready:
                continue
            chunk = os.read(stdout, 65536)
            if not chunk:
                self._fail("codex app-server exited unexpectedly")
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return {}

    def _fail(self, message: str) -> None:
        self.stderr.seek(0)
        detail = self.stderr.read().decode(errors="replace").strip()[-500:]
        self.close()
        print(f"Error: {message}" + (f"\n{detail}" if detail else ""), file=sys.stderr)
        sys.exit(1)


def project_root() -> Path:
    try:
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    except FileNotFoundError:
        return Path.cwd()
    return Path(result.stdout.strip()) if result.returncode == 0 else Path.cwd()


def list_models(project_dir: Path, include_hidden: bool, timeout: int) -> dict:
    server = AppServer(timeout)
    try:
        server.request("initialize", {"clientInfo": {"name": "agent-skills", "version": "1"}})
        server.notify("initialized")
        config = server.request("config/read", {"cwd": str(project_dir), "includeLayers": False})
        catalog = []
        cursor = None
        while True:
            params = {"includeHidden": include_hidden}
            if cursor:
                params["cursor"] = cursor
            page = server.request("model/list", params)
            catalog.extend(page.get("data", []))
            cursor = page.get("nextCursor")
            if not cursor:
                break
    finally:
        server.close()

    settings = config.get("config", {})
    catalog_default = next((m for m in catalog if m.get("isDefault")), None)
    default_model = settings.get("model") or (catalog_default or {}).get("id")
    default_effort = settings.get("model_reasoning_effort") or next(
        (m.get("defaultReasoningEffort") for m in catalog if m.get("id") == default_model),
        None,
    )

    models = []
    for model in catalog:
        efforts = [level.get("reasoningEffort") for level in model.get("supportedReasoningEfforts", [])]
        entry = {"id": model.get("id")}
        if efforts:
            entry["efforts"] = ",".join(e for e in efforts if e)
            entry["default_effort"] = model.get("defaultReasoningEffort")
        if model.get("hidden"):
            entry["hidden"] = True
        if model.get("description"):
            entry["description"] = model["description"]
        models.append(entry)
    return {"default": {"model": default_model, "effort": default_effort}, "models": models}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--include-hidden", action="store_true", help="Also list models hidden from the picker")
    parser.add_argument("--timeout", type=int, default=60, help="Seconds to wait for codex app-server (default: 60)")
    args = parser.parse_args()
    result = list_models(project_root(), args.include_hidden, args.timeout)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
