#!/usr/bin/env python3

import argparse
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "agents/.agents/lib/claude_session.py"
SPEC = importlib.util.spec_from_file_location("claude_session", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def metadata(kind="review", *, started=False):
    return {
        "kind": kind,
        "claude_session_id": "11111111-1111-4111-8111-111111111111",
        "claude_session_started": started,
        "model": None,
        "effort": None,
        "allow_git": False,
    }


def init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "tests@example.test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Tests"], cwd=path, check=True)
    (path / "tracked.txt").write_text("original\n")
    subprocess.run(["git", "add", "tracked.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=path, check=True)


class ClaudeCommandTest(unittest.TestCase):
    def test_review_command_is_read_only_and_uses_preassigned_session(self):
        command = MODULE.claude_command(metadata())

        self.assertEqual(
            command[:5],
            ["claude", "-p", "--output-format", "json", "--strict-mcp-config"],
        )
        self.assertNotIn("Review this", command)
        self.assertIn("--session-id", command)
        self.assertIn("--restricted", command)
        tools = command.index("--tools")
        self.assertEqual(command[tools : tools + 2], ["--tools", "Read,Glob,Grep"])
        permission = command.index("--permission-mode")
        self.assertEqual(command[permission : permission + 2], ["--permission-mode", "dontAsk"])
        self.assertNotIn("acceptEdits", command)
        deny = command.index("--disallowedTools")
        self.assertIn("Write", command[deny + 1])
        self.assertIn("--append-system-prompt", command)

    def test_task_command_resumes_and_honors_overrides(self):
        values = metadata("task", started=True)
        values.update({"model": "haiku", "effort": "low"})
        with mock.patch.object(MODULE, "claude_session_exists", return_value=True):
            command = MODULE.claude_command(values)

        self.assertIn("--resume", command)
        self.assertNotIn("--session-id", command)
        self.assertIn("haiku", command)
        self.assertIn("low", command)
        permission = command.index("--permission-mode")
        self.assertEqual(command[permission : permission + 2], ["--permission-mode", "acceptEdits"])
        self.assertNotIn("--disallowedTools", command)

    def test_missing_session_file_retries_round_one_with_session_id(self):
        values = metadata(started=True)
        with mock.patch.object(MODULE, "claude_session_exists", return_value=False):
            command = MODULE.claude_command(values)
        self.assertIn("--session-id", command)
        self.assertNotIn("--resume", command)

    def test_prompt_is_sent_over_stdin(self):
        command = [sys.executable, "-c", "import sys; print(sys.stdin.read(), end='')"]
        stdout, stderr, returncode = MODULE.run_claude(command, "private prompt", ROOT, 10)

        self.assertEqual(returncode, 0)
        self.assertEqual(stdout, "private prompt")
        self.assertEqual(stderr, "")


class ResultParsingTest(unittest.TestCase):
    def test_parse_result_accepts_final_response(self):
        parsed = MODULE.parse_result(
            '{"session_id":"abc","result":"final response","is_error":false,"noise":"ignored"}'
        )
        self.assertEqual(parsed["session_id"], "abc")
        self.assertEqual(parsed["result"], "final response")

    def test_parse_result_uses_empty_result_exit_code(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            MODULE.parse_result('{"session_id":"abc","is_error":false}')
        self.assertEqual(raised.exception.code, 3)
        self.assertIn('"exit_code": 3', stderr.getvalue())

    def test_status_parser_tolerates_markdown_and_punctuation(self):
        self.assertEqual(MODULE.parse_status("STATUS: DONE\nAll good"), "DONE")
        self.assertEqual(MODULE.parse_status("**STATUS: done.**"), "DONE")
        self.assertEqual(MODULE.parse_status("All good"), "UNKNOWN")


class VerificationTest(unittest.TestCase):
    def test_sanitizer_removes_terminal_noise(self):
        progress = "\x1b[90;1m.\x1b[39;22m" * 100
        raw = f"{progress}\n\x1b[32mTests: 3 passed\x1b[0m\n"
        self.assertEqual(
            MODULE.sanitize_verify_output(raw, passed=True),
            "Tests: 3 passed",
        )

    def test_non_utf8_verification_output_is_replaced(self):
        result = MODULE.verify_commands(
            ["python -c 'import sys; sys.stdout.buffer.write(bytes([255]))'"],
            ROOT,
            10,
        )[0]
        self.assertTrue(result["passed"])
        self.assertEqual(result["output_tail"], "�")

    def test_verification_timeout_kills_process_group(self):
        started = time.monotonic()
        result = MODULE.verify_commands(["sleep 10"], ROOT, 1)[0]

        self.assertLess(time.monotonic() - started, 3)
        self.assertFalse(result["passed"])
        self.assertIsNone(result["exit_code"])
        self.assertIn("timed out after 1s", result["output_tail"])


class WorkspaceAccountingTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        init_git_repo(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_reediting_already_dirty_file_changes_fingerprint(self):
        tracked = self.root / "tracked.txt"
        tracked.write_text("first dirty value\n")
        before = MODULE.workspace_state(self.root)
        tracked.write_text("second dirty value\n")
        after = MODULE.workspace_state(self.root)

        self.assertNotEqual(before["tracked.txt"], after["tracked.txt"])

    def test_committed_changes_are_reported(self):
        before = MODULE.git_state(self.root)["head"]
        (self.root / "tracked.txt").write_text("committed change\n")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "change"], cwd=self.root, check=True)
        after = MODULE.git_state(self.root)["head"]

        paths, commits = MODULE.committed_changes(self.root, before, after)
        self.assertEqual(paths, ["tracked.txt"])
        self.assertTrue(any("change" in commit for commit in commits))


class RoundAndLockTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.session = self.directory / "session.json"
        self.session.write_text(
            json.dumps(
                {
                    **metadata("task"),
                    "round": 1,
                    "project": "test",
                    "project_dir": str(ROOT),
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "verify": [],
                }
            )
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_next_round_blocks_missing_output_unless_forced(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            MODULE.next_round(self.session, False)
        _, round_number = MODULE.next_round(self.session, True)
        self.assertEqual(round_number, 2)

    def test_session_lock_rejects_concurrent_mutator(self):
        with MODULE.SessionLock(self.session):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                with MODULE.SessionLock(self.session):
                    pass

    def test_active_process_detection_checks_leader(self):
        self.assertTrue(MODULE.process_alive(os.getpid()))
        self.assertFalse(MODULE.process_alive(999_999_999))

    def test_initial_task_brief_requires_headings(self):
        self.session.write_text(
            json.dumps(
                {
                    **json.loads(self.session.read_text()),
                    "round": 0,
                }
            )
        )
        args = argparse.Namespace(
            session=str(self.session), kind="task", force=False
        )
        with mock.patch.object(sys, "stdin", io.StringIO("missing headings")), contextlib.redirect_stderr(
            io.StringIO()
        ), self.assertRaises(SystemExit):
            MODULE.write_round(args)


class SessionManagementTest(unittest.TestCase):
    def test_list_skips_corrupt_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            old_home = MODULE.HOME
            MODULE.HOME = Path(temporary)
            try:
                root = MODULE.session_base("review") / "project" / "2026-01-01"
                valid = root / "000001-valid"
                invalid = root / "000002-invalid"
                valid.mkdir(parents=True)
                invalid.mkdir()
                (valid / "session.json").write_text(
                    json.dumps(
                        {
                            **metadata(),
                            "project": "project",
                            "created_at": "2026-01-01T00:00:00+00:00",
                        }
                    )
                )
                (invalid / "session.json").write_text("{")
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    MODULE.list_sessions(argparse.Namespace(kind="review", project=None))
                result = json.loads(stdout.getvalue())
                self.assertEqual(len(result["sessions"]), 1)
                self.assertEqual(len(result["warnings"]), 1)
            finally:
                MODULE.HOME = old_home

    def test_cleanup_rejects_session_outside_managed_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            old_home = MODULE.HOME
            MODULE.HOME = Path(temporary) / "home"
            outside = Path(temporary) / "outside"
            outside.mkdir()
            session = outside / "session.json"
            session.write_text(json.dumps({**metadata(), "round": 0}))
            try:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    MODULE.cleanup(argparse.Namespace(session=str(session)))
                self.assertTrue(session.exists())
            finally:
                MODULE.HOME = old_home


if __name__ == "__main__":
    unittest.main()
