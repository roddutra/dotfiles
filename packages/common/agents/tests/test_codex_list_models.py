#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "agents/.agents/skills/codex-reviewer/scripts/list_models.py"
SHIMS = [ROOT / f"agents/.agents/skills/{skill}/scripts/list_models.py" for skill in ("codex-reviewer", "delegate-to-codex")]

# Stands in for `codex app-server`: answers JSON-RPC over stdio, emits a
# notification between responses, and serves the model list in two pages.
FAKE_CODEX = r"""#!/usr/bin/env python3
import json, os, sys

config = json.loads(os.environ["FAKE_CODEX_CONFIG"])
models = [
    {"id": "big", "isDefault": True, "hidden": False, "description": "Big model",
     "defaultReasoningEffort": "medium",
     "supportedReasoningEfforts": [{"reasoningEffort": "low"}, {"reasoningEffort": "medium"}]},
    {"id": "secret", "isDefault": False, "hidden": True, "description": "",
     "defaultReasoningEffort": "low", "supportedReasoningEfforts": [{"reasoningEffort": "low"}]},
]
for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    method, params = message["method"], message.get("params", {})
    if method == "initialize":
        result = {}
    elif method == "config/read":
        with open(os.environ["FAKE_CODEX_LOG"], "a") as log:
            log.write(json.dumps(params) + "\n")
        result = {"config": config}
    elif method == "model/list":
        visible = [m for m in models if params.get("includeHidden") or not m["hidden"]]
        page = 1 if params.get("cursor") else 0
        result = {"data": visible[page:page + 1], "nextCursor": None if page or len(visible) < 2 else "next"}
    else:
        print(json.dumps({"id": message["id"], "error": {"message": "unknown"}}), flush=True)
        continue
    print(json.dumps({"method": "noise", "params": {}}), flush=True)
    print(json.dumps({"id": message["id"], "result": result}), flush=True)
"""


class ListModelsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.bin = Path(self.temporary.name) / "bin"
        self.bin.mkdir()
        codex = self.bin / "codex"
        codex.write_text(FAKE_CODEX)
        codex.chmod(0o755)
        self.log = Path(self.temporary.name) / "requests.log"
        self.project = Path(self.temporary.name) / "project"
        (self.project / "nested").mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)

    def tearDown(self):
        self.temporary.cleanup()

    def run_script(self, config, *args, script=SCRIPT):
        env = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "FAKE_CODEX_CONFIG": json.dumps(config),
            "FAKE_CODEX_LOG": str(self.log),
        }
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=self.project / "nested",
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_reports_configured_default_and_compact_models(self):
        result = self.run_script({"model": "secret", "model_reasoning_effort": "high"}, "--include-hidden")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        output = json.loads(result.stdout)
        self.assertEqual(output["default"], {"model": "secret", "effort": "high"})
        self.assertEqual(
            output["models"],
            [
                {"id": "big", "efforts": "low,medium", "default_effort": "medium", "description": "Big model"},
                {"id": "secret", "efforts": "low", "default_effort": "low", "hidden": True},
            ],
        )
        request = json.loads(self.log.read_text())
        self.assertEqual(Path(request["cwd"]).resolve(), self.project.resolve())

    def test_falls_back_to_catalog_defaults(self):
        result = self.run_script({"model": None, "model_reasoning_effort": None})

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["default"], {"model": "big", "effort": "medium"})
        self.assertEqual([model["id"] for model in output["models"]], ["big"])

    def test_every_codex_skill_exposes_the_shared_lister(self):
        for script in SHIMS:
            with self.subTest(script=script.parent.parent.name):
                result = self.run_script({"model": None, "model_reasoning_effort": None}, script=script)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["default"]["model"], "big")

    def test_missing_codex_fails_clearly(self):
        env = {**os.environ, "PATH": str(Path(self.temporary.name) / "empty")}
        result = subprocess.run(
            [sys.executable, str(SCRIPT)], cwd=self.project, env=env, capture_output=True, text=True, timeout=30
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Codex CLI was not found", result.stderr)


if __name__ == "__main__":
    unittest.main()
