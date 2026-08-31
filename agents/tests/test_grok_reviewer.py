#!/usr/bin/env python3

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "agents/.agents/skills/grok-reviewer/scripts"
SCRIPT = SCRIPT_DIR / "run_review.py"


def load_reviewer():
    spec = importlib.util.spec_from_file_location("grok_reviewer_run_review", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


REVIEWER = load_reviewer()


def process_result(*, returncode=0, stderr="", text="", ended=False):
    state = REVIEWER._StreamState()
    if text:
        state.feed(json.dumps({"type": "text", "data": text}))
    if ended:
        state.feed(json.dumps({"type": "end", "stopReason": "end_turn"}))
    return REVIEWER._ProcessResult(
        returncode=returncode,
        state=state,
        stderr_tail=stderr,
        timed_out=False,
        stalled=False,
    )


class GrokReviewerSandboxFallbackTest(unittest.TestCase):
    def make_session(self, root: Path, **metadata):
        session = root / "session.json"
        session.write_text(json.dumps({
            "project": "test-project",
            "current_round": 1,
            "project_dir": str(root),
            **metadata,
        }))
        (root / "r1-prompt.md").write_text("Review the project without modifying files.\n")
        return session

    def test_recognizes_only_sandbox_bootstrap_failures(self):
        sandbox_error = process_result(
            returncode=1,
            stderr="failed to resolve sandbox deny path /run/user/1000/podman/podman.sock",
        )
        auth_error = process_result(returncode=1, stderr="authentication token expired")
        completed = process_result(
            returncode=1,
            stderr="sandbox initialization failed",
            text="partial review",
        )

        self.assertTrue(REVIEWER._is_sandbox_bootstrap_failure(sandbox_error))
        self.assertFalse(REVIEWER._is_sandbox_bootstrap_failure(auth_error))
        self.assertFalse(REVIEWER._is_sandbox_bootstrap_failure(completed))

    def test_retries_failed_sandbox_startup_in_same_session(self):
        failed = process_result(
            returncode=1,
            stderr="failed to resolve sandbox deny path /run/user/1000/podman/podman.sock",
        )
        succeeded = process_result(text="No findings.\n", ended=True)

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {}, clear=False
        ):
            os.environ.pop("GROK_REVIEWER_SANDBOX", None)
            root = Path(tmp)
            session = self.make_session(root, sandbox=True)
            with patch.object(
                REVIEWER,
                "generate_paths",
                return_value={
                    "prompt_path": str(root / "r1-prompt.md"),
                    "output_path": str(root / "r1-output.md"),
                },
            ), patch.object(
                REVIEWER, "_grok_session_exists", return_value=False
            ), patch.object(
                REVIEWER, "_run_grok_process", side_effect=[failed, succeeded]
            ) as run_process, redirect_stderr(io.StringIO()):
                result = REVIEWER.run_review(session)

            first_cmd = run_process.call_args_list[0].args[0]
            second_cmd = run_process.call_args_list[1].args[0]
            metadata = json.loads(session.read_text())

            self.assertEqual(run_process.call_count, 2)
            self.assertIn("--sandbox", first_cmd)
            self.assertNotIn("--sandbox", second_cmd)
            self.assertIn("Edit", second_cmd)
            self.assertEqual(metadata["sandbox"], False)
            self.assertEqual(metadata["sandbox_source"], "fallback")
            self.assertTrue(result["sandbox_fallback"])
            self.assertEqual(result["sandbox_source"], "fallback")
            self.assertEqual((root / "r1-output.md").read_text(), "No findings.\n")

    def test_forced_sandbox_disables_automatic_downgrade(self):
        failed = process_result(
            returncode=1,
            stderr="sandbox initialization failed while resolving deny path",
        )

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"GROK_REVIEWER_SANDBOX": "1"}
        ):
            root = Path(tmp)
            session = self.make_session(root)
            with patch.object(
                REVIEWER,
                "generate_paths",
                return_value={
                    "prompt_path": str(root / "r1-prompt.md"),
                    "output_path": str(root / "r1-output.md"),
                },
            ), patch.object(
                REVIEWER, "_grok_session_exists", return_value=False
            ), patch.object(
                REVIEWER, "_run_grok_process", return_value=failed
            ) as run_process, redirect_stderr(io.StringIO()):
                with self.assertRaisesRegex(SystemExit, "1"):
                    REVIEWER.run_review(session)

            metadata = json.loads(session.read_text())
            self.assertEqual(run_process.call_count, 1)
            self.assertEqual(metadata["sandbox"], True)
            self.assertEqual(metadata["sandbox_source"], "forced")

    def test_force_off_overrides_stale_profile_before_session_creation(self):
        succeeded = process_result(text="Review complete.\n", ended=True)

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"GROK_REVIEWER_SANDBOX": "0"}
        ):
            root = Path(tmp)
            session = self.make_session(root, sandbox=True)
            with patch.object(
                REVIEWER,
                "generate_paths",
                return_value={
                    "prompt_path": str(root / "r1-prompt.md"),
                    "output_path": str(root / "r1-output.md"),
                },
            ), patch.object(
                REVIEWER, "_grok_session_exists", return_value=False
            ), patch.object(
                REVIEWER, "_run_grok_process", return_value=succeeded
            ) as run_process, redirect_stderr(io.StringIO()):
                result = REVIEWER.run_review(session)

            cmd = run_process.call_args.args[0]
            metadata = json.loads(session.read_text())
            self.assertNotIn("--sandbox", cmd)
            self.assertEqual(metadata["sandbox"], False)
            self.assertEqual(metadata["sandbox_source"], "forced")
            self.assertFalse(result["sandbox_fallback"])


if __name__ == "__main__":
    unittest.main()
