#!/usr/bin/env python3

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPERS = {
    "codex": ROOT / "agents/.agents/skills/delegate-to-codex/scripts/delegate_common.py",
    "grok": ROOT / "agents/.agents/skills/delegate-to-grok/scripts/delegate_common.py",
}


def load_helper(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(f"delegate_common_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULES = {name: load_helper(name, path) for name, path in HELPERS.items()}


class VerifyOutputSanitizerTest(unittest.TestCase):
    def test_removes_terminal_noise_and_keeps_summary(self):
        progress = "\x1b[90;1m.\x1b[39;22m" * 1_367
        raw = (
            f"{progress}\n"
            "  \x1b[90mTests:\x1b[39m    \x1b[32;1m1367 passed\x1b[39;22m (6266 assertions)\n"
            "  \x1b[90mDuration:\x1b[39m 169.92s\n"
            "\x1b]8;;https://example.test\x1b\\details\x1b]8;;\x1b\\\n"
        )

        for name, module in MODULES.items():
            with self.subTest(helper=name):
                self.assertEqual(
                    module._sanitize_verify_output(raw, passed=True),
                    "  Tests:    1367 passed (6266 assertions)\n"
                    "  Duration: 169.92s\n"
                    "details",
                )

    def test_success_output_is_bounded(self):
        raw = "\n".join(f"successful line {i}: {'x' * 250}" for i in range(40))

        for name, module in MODULES.items():
            with self.subTest(helper=name):
                output = module._sanitize_verify_output(raw, passed=True)
                self.assertLessEqual(len(output), module._VERIFY_PASS_MAX_CHARS)
                self.assertTrue(output.startswith("[... verification output truncated ...]\n"))
                self.assertIn("successful line 39", output)
                self.assertNotIn("successful line 0", output)

    def test_failure_output_retains_larger_diagnostic_tail(self):
        raw = "\n".join(f"failure line {i}: {'y' * 100}" for i in range(50))

        for name, module in MODULES.items():
            with self.subTest(helper=name):
                output = module._sanitize_verify_output(raw, passed=False)
                self.assertLessEqual(len(output), module._VERIFY_FAIL_MAX_CHARS)
                self.assertTrue(output.startswith("[... verification output truncated ...]\n"))
                self.assertIn("failure line 49", output)
                self.assertNotIn("failure line 0", output)

    def test_run_verify_returns_sanitized_output(self):
        command = "printf '\\033[90;1m.\\033[39;22m\\nTests: 1 passed\\n'"

        for name, module in MODULES.items():
            with self.subTest(helper=name):
                result = module.run_verify([command], ROOT)[0]
                self.assertTrue(result["passed"])
                self.assertEqual(result["output_tail"], "Tests: 1 passed")


if __name__ == "__main__":
    unittest.main()
