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
        system_prompt = command[command.index("--append-system-prompt") + 1]
        self.assertIn("REVIEW STANDARD", system_prompt)
        self.assertIn("APPROVE WITH NOTES", system_prompt)

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


def control_response(request_id, response=None, error=None):
    body = {"request_id": request_id, "subtype": "error" if error else "success"}
    if error:
        body["error"] = error
    else:
        body["response"] = response
    return json.dumps({"type": "control_response", "response": body})


class ModelListTest(unittest.TestCase):
    def run_models(self, stdout):
        output = io.StringIO()
        with mock.patch.object(MODULE, "run_claude", return_value=(stdout, "", 0)) as run, contextlib.redirect_stdout(output):
            MODULE.list_models(argparse.Namespace(timeout=60))
        return run, json.loads(output.getvalue())

    def test_reports_effective_default_and_compact_models(self):
        stdout = "\n".join(
            [
                json.dumps({"type": "system", "subtype": "hook_started"}),
                control_response(
                    "models",
                    {
                        "models": [
                            {"value": "default", "resolvedModel": "claude-opus-5-5[1m]", "displayName": "Default"},
                            {
                                "value": "sonnet",
                                "resolvedModel": "claude-sonnet-5",
                                "displayName": "Sonnet",
                                "description": "Sonnet 5",
                                "supportedEffortLevels": ["low", "high"],
                                "supportsFastMode": True,
                            },
                            {"value": "haiku", "resolvedModel": "claude-haiku-4-5-20251001"},
                        ]
                    },
                ),
                control_response(
                    "settings",
                    {"applied": {"model": "claude-sonnet-5", "effort": "high"}, "effective": {"hooks": {}}},
                ),
            ]
        )
        run, result = self.run_models(stdout)

        command, requests = run.call_args.args[:2]
        self.assertIn("--no-session-persistence", command)
        self.assertEqual(
            [json.loads(line)["request"]["subtype"] for line in requests.splitlines()],
            ["initialize", "get_settings"],
        )
        self.assertEqual(result["default"], {"model": "claude-sonnet-5", "effort": "high"})
        self.assertEqual(
            result["models"],
            [
                {
                    "value": "sonnet",
                    "resolves_to": "claude-sonnet-5",
                    "efforts": "low,high",
                    "description": "Sonnet 5",
                },
                {"value": "haiku", "resolves_to": "claude-haiku-4-5-20251001"},
            ],
        )

    def test_rejected_control_request_fails(self):
        stdout = "\n".join(
            [
                control_response("models", {"models": []}),
                control_response("settings", error="Unsupported control request subtype: get_settings"),
            ]
        )
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            self.run_models(stdout)
        self.assertIn("get_settings", stderr.getvalue())


class EffortValidationTest(unittest.TestCase):
    CATALOG = (
        [
            {"value": "sonnet", "supportedEffortLevels": ["low", "high"]},
            {"value": "fable", "supportedEffortLevels": ["high", "ultra"]},
            {"value": "haiku"},
        ],
        {},
    )

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name) / "home"
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        init_git_repo(self.repo)
        self.old_home = MODULE.HOME
        MODULE.HOME = self.home

    def tearDown(self):
        MODULE.HOME = self.old_home
        self.temporary.cleanup()

    def init(self, effort):
        args = argparse.Namespace(
            kind="review", title="t", project=None, force_project=None, model=None, effort=effort
        )
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(MODULE, "harness_state", return_value=self.CATALOG) as harness, mock.patch.object(
            MODULE.Path, "cwd", return_value=self.repo
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                MODULE.init_session(args)
            except SystemExit:
                pass
        return harness, stdout.getvalue(), stderr.getvalue()

    def test_level_supported_by_any_model_is_accepted(self):
        harness, stdout, _ = self.init("ultra")

        harness.assert_called_once()
        session = Path(json.loads(stdout)["session"])
        self.assertEqual(json.loads(session.read_text())["effort"], "ultra")

    def test_unsupported_level_is_rejected_before_session_is_created(self):
        _, stdout, stderr = self.init("bogus")

        self.assertEqual(stdout, "")
        self.assertIn("low, high, ultra", stderr)
        self.assertFalse(MODULE.session_base("review").exists())

    def test_omitted_effort_skips_harness_query(self):
        harness, stdout, _ = self.init(None)

        harness.assert_not_called()
        self.assertIn("session", json.loads(stdout))

    def test_run_rejects_unsupported_override_before_invoking_claude(self):
        session = self.home / "session.json"
        self.home.mkdir()
        session.write_text(json.dumps({**metadata(), "round": 1, "project_dir": str(self.repo)}))
        (session.parent / "r1-prompt.md").write_text("Review this")
        args = argparse.Namespace(
            session=str(session), kind="review", effort="bogus", rerun=False, timeout=60, skip_verify=False
        )
        with mock.patch.object(MODULE, "harness_state", return_value=self.CATALOG), mock.patch.object(
            MODULE, "run_claude"
        ) as run, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            MODULE.run_round(args)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
