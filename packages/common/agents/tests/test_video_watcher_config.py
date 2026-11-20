#!/usr/bin/env python3

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "agents/.agents/skills/video-watcher/scripts"
CONFIG_CLI = SCRIPTS / "config.py"

sys.path.insert(0, str(SCRIPTS))
import settings  # noqa: E402


class Sandbox:
    """A fake home config directory plus a project directory, both empty."""

    def __init__(self, test: unittest.TestCase, git: bool = False):
        root = Path(tempfile.mkdtemp())
        test.addCleanup(lambda: subprocess.run(["rm", "-rf", str(root)], check=False))
        self.project = root / "project"
        self.project.mkdir()
        self.environ = {"XDG_CONFIG_HOME": str(root / "xdg"), "PATH": "/usr/bin:/bin"}
        self.global_file = settings.global_config_path(self.environ)
        self.global_file.parent.mkdir(parents=True)
        if git:
            subprocess.run(["git", "init", "-q", str(self.project)], check=True)

    def write_global(self, text: str) -> None:
        self.global_file.write_text(text)

    def write(self, relative: str, text: str) -> Path:
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def resolve(self, flags=None, cwd=None, extra_env=None, **kwargs):
        return settings.resolve(flags, {**self.environ, **(extra_env or {})}, cwd or self.project, **kwargs)


GLOBAL = "VIDEO_WATCHER_PROVIDER=gemini\nVIDEO_WATCHER_MODEL=global-model\nVIDEO_WATCHER_API_KEY=global-key\n"


class LayeredResolutionTest(unittest.TestCase):
    def test_project_model_override_inherits_provider_and_key_from_global(self):
        box = Sandbox(self)
        box.write_global(GLOBAL)
        box.write(".env", "DATABASE_URL=postgres://x\nVIDEO_WATCHER_MODEL=project-model\n")

        resolved = box.resolve()

        self.assertEqual(resolved.model, "project-model")
        self.assertEqual(resolved.provider, "gemini")
        self.assertEqual(resolved.api_key, "global-key")
        self.assertEqual(resolved.base_url, "https://generativelanguage.googleapis.com")
        self.assertTrue(resolved.sources["MODEL"].startswith("project:"))
        self.assertTrue(resolved.sources["API_KEY"].startswith("global:"))

    def test_each_layer_outranks_the_ones_below_it(self):
        box = Sandbox(self, git=True)
        box.write_global(GLOBAL)
        subdir = box.project / "apps/api"
        subdir.mkdir(parents=True)
        # Layers from lowest to highest; each step adds the next one up.
        steps = [
            ("global-model", lambda: None),
            ("root-env", lambda: box.write(".env", "VIDEO_WATCHER_MODEL=root-env\n")),
            ("root-local", lambda: box.write(".env.local", "VIDEO_WATCHER_MODEL=root-local\n")),
            ("cwd-env", lambda: box.write("apps/api/.env", "VIDEO_WATCHER_MODEL=cwd-env\n")),
            ("cwd-local", lambda: box.write("apps/api/.env.local", "VIDEO_WATCHER_MODEL=cwd-local\n")),
        ]
        for expected, add_layer in steps:
            add_layer()
            with self.subTest(top_layer=expected):
                self.assertEqual(box.resolve(cwd=subdir).model, expected)

        from_env = box.resolve(cwd=subdir, extra_env={"VIDEO_WATCHER_MODEL": "from-env"})
        self.assertEqual(from_env.model, "from-env")
        from_flag = box.resolve({"MODEL": "from-flag"}, cwd=subdir, extra_env={"VIDEO_WATCHER_MODEL": "from-env"})
        self.assertEqual(from_flag.model, "from-flag")

    def test_dotenv_syntax_forms_are_read(self):
        box = Sandbox(self)
        box.write_global("VIDEO_WATCHER_PROVIDER=gemini\n")
        box.write(".env", "\n".join([
            "# VIDEO_WATCHER_MODEL=commented-out",
            "export VIDEO_WATCHER_MODEL='quoted model'",
            'VIDEO_WATCHER_API_KEY="double-quoted"',
            "VIDEO_WATCHER_BASE_URL=https://example.test/v1/ # trailing comment",
            "MODEL=not-ours",
        ]) + "\n")

        resolved = box.resolve()

        self.assertEqual(resolved.model, "quoted model")
        self.assertEqual(resolved.api_key, "double-quoted")
        self.assertEqual(resolved.base_url, "https://example.test/v1")

    def test_empty_value_does_not_mask_a_lower_layer(self):
        box = Sandbox(self)
        box.write_global(GLOBAL)
        box.write(".env", "VIDEO_WATCHER_MODEL=\n")

        self.assertEqual(box.resolve().model, "global-model")


class KeySafetyTest(unittest.TestCase):
    def test_provider_switch_without_its_own_key_is_refused(self):
        box = Sandbox(self)
        box.write_global(GLOBAL)
        box.write(".env", "VIDEO_WATCHER_PROVIDER=openrouter\n")

        with self.assertRaises(settings.ConfigError) as caught:
            box.resolve()
        self.assertEqual(caught.exception.code, "key_provider_mismatch")

        box.write(".env", "VIDEO_WATCHER_PROVIDER=openrouter\nVIDEO_WATCHER_API_KEY=project-key\n")
        resolved = box.resolve()
        self.assertEqual((resolved.provider, resolved.api_key), ("openrouter", "project-key"))
        self.assertEqual(resolved.base_url, "https://openrouter.ai/api/v1")

    def test_key_command_runs_from_the_global_file_only(self):
        box = Sandbox(self)
        marker = box.project / "ran"
        command = f"VIDEO_WATCHER_API_KEY_CMD=touch {marker}\n"
        box.write_global("VIDEO_WATCHER_PROVIDER=gemini\nVIDEO_WATCHER_MODEL=m\n")
        box.write(".env", command)

        with self.assertRaises(settings.ConfigError) as caught:
            box.resolve(extra_env={"VIDEO_WATCHER_API_KEY_CMD": f"touch {marker}"})
        self.assertEqual(caught.exception.missing, ["VIDEO_WATCHER_API_KEY"])
        self.assertFalse(marker.exists(), "a project file or the environment ran a key command")

        box.write(".env", "")
        box.write_global("VIDEO_WATCHER_PROVIDER=gemini\nVIDEO_WATCHER_MODEL=m\n"
                         "VIDEO_WATCHER_API_KEY_CMD=printf key-from-command\n")
        self.assertEqual(box.resolve().api_key, "key-from-command")

    def test_plain_http_is_allowed_for_localhost_only(self):
        box = Sandbox(self)
        base = "VIDEO_WATCHER_PROVIDER=openai-compatible\nVIDEO_WATCHER_MODEL=m\nVIDEO_WATCHER_API_KEY=k\n"

        box.write_global(base + "VIDEO_WATCHER_BASE_URL=http://models.example.test/v1\n")
        with self.assertRaises(settings.ConfigError) as caught:
            box.resolve()
        self.assertEqual(caught.exception.code, "insecure_base_url")

        box.write_global(base + "VIDEO_WATCHER_BASE_URL=http://localhost:8000/v1\n")
        self.assertEqual(box.resolve().base_url, "http://localhost:8000/v1")

    def test_missing_settings_are_named(self):
        box = Sandbox(self)

        with self.assertRaises(settings.ConfigError) as caught:
            box.resolve()

        self.assertEqual(caught.exception.code, "config_missing")
        self.assertEqual(caught.exception.missing, ["VIDEO_WATCHER_PROVIDER", "VIDEO_WATCHER_MODEL"])


class ConfigCliTest(unittest.TestCase):
    def run_cli(self, box: Sandbox, *args: str, stdin: str | None = None):
        return subprocess.run(
            [sys.executable, str(CONFIG_CLI), *args],
            cwd=box.project, env=box.environ, input=stdin, capture_output=True, text=True,
        )

    def test_key_is_stored_privately_and_never_printed(self):
        box = Sandbox(self)
        self.run_cli(box, "init", "--scope", "global", "--provider", "gemini", "--model", "m")

        stored = self.run_cli(box, "set-key", "--scope", "global", stdin="sk-test-SECRET\n")
        shown = self.run_cli(box, "show")

        self.assertEqual(stored.returncode, 0, stored.stderr)
        self.assertEqual(box.global_file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(settings.parse_dotenv(box.global_file.read_text())["API_KEY"], "sk-test-SECRET")
        summary = json.loads(shown.stdout)
        self.assertTrue(summary["ready"])
        self.assertTrue(summary["api_key"]["set"])
        for output in (stored.stdout, stored.stderr, shown.stdout, shown.stderr):
            self.assertNotIn("SECRET", output)

    def test_project_key_is_refused_unless_git_ignores_the_file(self):
        box = Sandbox(self, git=True)
        box.write(".gitignore", ".env.local\n")

        refused = self.run_cli(box, "set-key", "--scope", "project", stdin="sk-test-SECRET\n")
        accepted = self.run_cli(box, "set-key", "--scope", "project", "--file", ".env.local", stdin="sk-test-SECRET\n")

        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(json.loads(refused.stdout)["error"]["code"], "unsafe_key_location")
        self.assertFalse((box.project / ".env").exists())
        self.assertEqual(accepted.returncode, 0, accepted.stdout)
        self.assertIn("VIDEO_WATCHER_API_KEY=sk-test-SECRET", (box.project / ".env.local").read_text())


if __name__ == "__main__":
    unittest.main()
