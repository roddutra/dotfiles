#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHIMS = [ROOT / f"agents/.agents/skills/{skill}/scripts/list_models.py" for skill in ("grok-reviewer", "delegate-to-grok")]

# Stands in for `grok models`, printing whatever FAKE_GROK_OUTPUT holds.
FAKE_GROK = r"""#!/usr/bin/env python3
import os, sys
assert sys.argv[1:] == ["models"], sys.argv
sys.stdout.write(os.environ["FAKE_GROK_OUTPUT"])
sys.exit(int(os.environ.get("FAKE_GROK_EXIT", "0")))
"""

SIGNED_IN = """You are logged in with grok.com.

Default model: grok-4.7

Available models:
  * grok-4.7 (default)
    grok-4.6
    my-custom (custom)
"""


class ListModelsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.bin = Path(self.temporary.name) / "bin"
        self.bin.mkdir()
        grok = self.bin / "grok"
        grok.write_text(FAKE_GROK)
        grok.chmod(0o755)

    def tearDown(self):
        self.temporary.cleanup()

    def run_script(self, output, script=SHIMS[0], exit_code=0):
        env = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "FAKE_GROK_OUTPUT": output,
            "FAKE_GROK_EXIT": str(exit_code),
        }
        return subprocess.run(
            [sys.executable, str(script)], cwd=self.temporary.name, env=env, capture_output=True, text=True, timeout=30
        )

    def test_every_grok_skill_reports_default_and_models(self):
        for script in SHIMS:
            with self.subTest(script=script.parent.parent.name):
                result = self.run_script(SIGNED_IN, script)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout),
                    {"default": {"model": "grok-4.7"}, "models": ["grok-4.7", "grok-4.6", "my-custom"]},
                )

    def test_signed_out_output_is_flagged(self):
        result = self.run_script(SIGNED_IN.replace("You are logged in with grok.com.", "You are not authenticated."))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not signed in", json.loads(result.stdout)["note"])

    def test_unrecognized_output_fails_instead_of_guessing(self):
        result = self.run_script("Something new entirely\n")

        self.assertEqual(result.returncode, 1)
        self.assertIn("unrecognized", result.stderr)

    def test_cli_failure_is_reported(self):
        result = self.run_script("boom\n", exit_code=2)

        self.assertEqual(result.returncode, 1)
        self.assertIn("exited 2", result.stderr)


if __name__ == "__main__":
    unittest.main()
