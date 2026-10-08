#!/usr/bin/env python3
"""Contract tests for the 1Password approval alert scripts.

The real scripts run in a throwaway HOME with XDG directories, a local fake
ntfy server and stub hyprctl/herdr/curl on PATH, so nothing touches the real
desktop, configuration, token or ntfy server.
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]
LIB = PACKAGE / ".agents/lib/op-approval"
SCRIPTS = PACKAGE / ".agents/skills/op-approval-blocked/scripts"
TOKEN = "tk_TestToken0123456789abcdef"
REAL_CURL = shutil.which("curl")

ENV_DROP = (
    "HERDR_", "TMUX", "ZELLIJ", "HYPRLAND_INSTANCE_SIGNATURE", "XDG_",
    "OP_APPROVAL_", "OPA_", "http_proxy", "https_proxy", "HTTP_PROXY",
    "HTTPS_PROXY", "ALL_PROXY", "all_proxy", "CURL_HOME",
)


class FakeNtfy:
    """Records every request; answers with `status` (and `location`, if set)."""

    def __init__(self, status=200, location=None):
        self.status = status
        self.location = location
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                fake.requests.append({
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body": self.rfile.read(length),
                })
                self.send_response(fake.status)
                if fake.location:
                    self.send_header("Location", fake.location)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def closed_port_url():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}"


def write_exec(path: Path, text: str):
    path.write_text(text)
    path.chmod(0o755)


class OpApprovalTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="op-approval-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.bin = self.tmp / "bin"
        self.runtime = self.tmp / "run"
        for d in (self.home, self.bin, self.runtime):
            d.mkdir(mode=0o700)
        self.config_dir = self.home / ".config/op-approval"
        self.token_file = self.home / ".local/share/op-approval/secrets/ntfy-token"
        self.state_dir = self.home / ".local/state/op-approval"
        self.feed = self.runtime / "op-approval/presence.json"

        # Stubs: no Hyprland and no Herdr unless a test provides fixtures.
        write_exec(self.bin / "hyprctl", "#!/bin/sh\nexit 1\n")
        write_exec(self.bin / "herdr", "#!/bin/sh\nexit 1\n")

        env = {k: v for k, v in os.environ.items() if not k.startswith(ENV_DROP)}
        env.update({
            "HOME": str(self.home),
            "OP_APPROVAL_RUNTIME_DIR": str(self.runtime / "op-approval"),
            "PATH": f"{self.bin}:{env.get('PATH', '/usr/bin:/bin')}",
            "OP_APPROVAL_LIB": str(LIB),
        })
        self.env = env

    # -- fixtures ---------------------------------------------------------

    def write_config(self, config: dict):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        (self.config_dir / "config.json").write_text(json.dumps(config))

    def configure(self, url: str, **extra):
        self.write_config({"machine": "testbox", "ntfy": {"url": url, "topic": "test-topic"}, **extra})
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(TOKEN + "\n")

    def write_feed(self, state="away", age=0, last_present_at=None, raw=None, pending_until=None):
        self.feed.parent.mkdir(parents=True, exist_ok=True)
        if raw is not None:
            self.feed.write_text(raw)
            return
        now = int(time.time())
        feed = {"machine": "testbox", "state": state, "updated_epoch": now - age}
        if last_present_at is not None:
            feed["last_present_at"] = last_present_at
        if pending_until is not None:
            feed["activity_pending_until"] = pending_until
        # Atomic, as the watcher writes it: a reader never sees half a feed.
        tmp = self.feed.with_suffix(".tmp")
        tmp.write_text(json.dumps(feed))
        tmp.replace(self.feed)

    def server(self, status=200, location=None):
        fake = FakeNtfy(status, location)
        self.addCleanup(fake.close)
        return fake

    def make_harness(self, name, project: Path):
        """A process named `name` working in `project`, as a harness would
        be in the agent's ancestry: sh started through a link of that name
        (macOS names a script's process after its interpreter, and kills a
        copied system binary). Returns the command prefix that runs a
        command inside it, and a file with its PID."""
        pid_file = self.tmp / f"{name}.pid"
        (self.bin / name).symlink_to("/bin/sh")
        script = f'echo $$ > "{pid_file}"; cd "{project}"; "$@"'
        return [str(self.bin / name), "-c", script, name], pid_file

    def hold_lock(self):
        """Takes the shared lock through the real helper and keeps it until
        the returned process's stdin is closed."""
        holder = subprocess.Popen(
            ["sh", "-c", '. "$0/common.sh"; opa_lock_acquire; echo held; read _', str(LIB)],
            env=self.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )
        self.addCleanup(holder.kill)
        self.assertEqual(holder.stdout.readline().strip(), "held")
        return holder

    # -- runners ----------------------------------------------------------

    def run_script(self, path: Path, *args, cwd=None):
        return subprocess.run(
            [str(path), *args], env=self.env, cwd=cwd or self.tmp,
            capture_output=True, text=True, timeout=60,
        )

    def notify(self, *args):
        return self.run_script(SCRIPTS / "notify", *args)

    def claim(self, *args):
        return self.run_script(LIB / "claim", *args)


class PublishPayloadTest(OpApprovalTestCase):
    def test_hostile_labels_produce_a_clean_fixed_template_and_the_token_stays_private(self):
        fake = self.server()
        project = self.tmp / "client-repo"
        project.mkdir()
        hostile_alias = 'Acme "Q4"\n$(touch PWNED)`touch PWNED`\x1b[31m\u00e9\u202e;|&'
        self.configure(fake.url, project_aliases={"client-repo": hostile_alias})
        self.write_feed("away")

        codex, pid_file = self.make_harness("codex", project)
        clients = self.tmp / "clients.json"
        clients.write_text(json.dumps([{
            "pid": 0, "class": "com.mitchellh.ghostty",
            "workspace": {"name": '2"; $(touch PWNED)\n'},
        }]))
        write_exec(self.bin / "hyprctl", (
            "#!/bin/sh\n"
            f'jq --argjson pid "$(cat "{pid_file}")" \'map(.pid = $pid)\' "{clients}"\n'
        ))

        fixtures = self.tmp / "herdr"
        fixtures.mkdir()
        for name, payload in {
            "pane-process-info": {"result": {"process_info": {"shell_pid": 1}}},
            "pane-list": {"result": {"panes": []}},
            "pane-get": {"result": {"pane": {"workspace_id": "w1", "tab_id": "w1:t1"}}},
            "workspace-get": {"result": {"workspace": {"label": "ops'\"\r\n`id`\u0000"}}},
            "tab-get": {"result": {"tab": {"label": "agents " + "x" * 60}}},
            "agent-get": {"result": {"agent": {"name": "$(touch PWNED)"}}},
        }.items():
            (fixtures / f"{name}.json").write_text(json.dumps(payload))
        write_exec(self.bin / "herdr", f'#!/bin/sh\ncat "{fixtures}/$1-$2.json"\n')
        self.env.update({"HERDR_ENV": "1", "HERDR_PANE_ID": "w1:p1"})

        argv_log = self.tmp / "curl-argv"
        env_log = self.tmp / "curl-env"
        write_exec(self.bin / "curl", (
            "#!/bin/sh\n"
            f'printf "%s\\n" "$@" >> "{argv_log}"\n'
            f'env >> "{env_log}"\n'
            f'exec "{REAL_CURL}" "$@"\n'
        ))

        # A caller that exports variables with the names publish uses must
        # not get the token passed on to curl's environment.
        self.env.update({"token": "caller-value", "opa_secret": "caller-value"})

        result = self.run_script(
            *codex, str(SCRIPTS / "notify"),
            "--harness", "codex", "--category", "git", "--state", "continuing",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["result"], "sent")
        self.assertEqual(len(fake.requests), 1)
        request = fake.requests[0]
        self.assertEqual(request["headers"]["Authorization"], f"Bearer {TOKEN}")
        request["body"].decode("ascii")
        body = json.loads(request["body"])
        message = body.pop("message")
        self.assertEqual(body, {
            "topic": "test-topic",
            "title": "[testbox] Agent blocked on 1Password",
            "priority": 3,
            "tags": ["lock"],
        })
        herdr_part = f"herdr ops id/agents {'x' * 33} touch PWNED"
        tail = f". Continuing other work. Git over SSH approval not given. Ref {output['ref']}"
        if sys.platform == "linux":
            # The hostile Hyprland workspace name, from the stub.
            app_part = "ws 2 touch PWNED Ghostty, "
            self.assertEqual(message, f"codex in Acme Q4 touch PWNEDtouch PWNED31m, {app_part}{herdr_part}{tail}")
        else:
            # The app comes from the real process ancestry of this test run.
            self.assertRegex(message, (
                r"^codex in Acme Q4 touch PWNEDtouch PWNED31m, (?:[A-Za-z0-9 ._:/@+-]+, )?"
                + re.escape(herdr_part + tail) + "$"
            ))
        self.assertRegex(output["ref"], r"^[a-z0-9]{4}$")
        self.assertEqual(list(self.tmp.rglob("PWNED")), [])
        self.assertFalse(TOKEN in argv_log.read_text(), "token found in curl's arguments")
        self.assertFalse(TOKEN in env_log.read_text(), "token found in curl's environment")


    def test_fallback_names_the_agent_when_known_and_else_the_approval_type(self):
        fake = self.server()
        self.configure(fake.url)
        agent_tail = "1Password prompt expired with no report from the agent."
        agent_title = "[testbox] Agent blocked on 1Password"
        other_title = "[testbox] 1Password approval not given"
        cases = (
            ({"harness": "codex", "project": "proj", "location": "ws 2 Ghostty", "process": "ssh"}, "ssh",
             agent_title, f"codex in proj, ws 2 Ghostty, or check the machine. {agent_tail}"),
            ({"harness": "agent", "project": "proj", "location": "Ghostty", "process": "ssh"}, "ssh",
             other_title, "SSH approval not given, with no report from an agent, ssh in proj, Ghostty."),
            ({"project": "proj"}, "op-cli",
             other_title, "1Password CLI approval not given, with no report from an agent, in proj."),
            ({}, "environment", other_title, "Environment approval not given, with no report from an agent."),
            ({}, None, other_title, "1Password approval not given, with no report from an agent."),
        )
        for identity, category, title, message in cases:
            with self.subTest(identity=identity, category=category):
                fake.requests.clear()
                args = ["--template", "fallback", "--identity", json.dumps(identity)]
                if category:
                    args += ["--category", category]
                result = self.run_script(LIB / "publish", *args)
                self.assertEqual(result.returncode, 0, result.stderr)
                body = json.loads(fake.requests[0]["body"])
                self.assertEqual(body["title"], title)
                self.assertEqual(body["message"], message)
                self.assertEqual(body["tags"], ["key"])


class LocateHarnessTest(OpApprovalTestCase):
    def test_only_an_exact_known_harness_name_is_accepted(self):
        project = self.tmp / "proj"
        project.mkdir()
        codex, _ = self.make_harness("codex", project)
        cases = (
            ("grok", "grok"),
            ("claude codex", "codex"),
            ("codex pi", "codex"),
            ("laude", "codex"),
            ("Claude", "codex"),
            ("claude ", "codex"),
        )
        for given, expected in cases:
            with self.subTest(given=given):
                result = self.run_script(*codex, str(LIB / "locate"), "--harness", given)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["harness"], expected)


class LocatePidTest(OpApprovalTestCase):
    @unittest.skipUnless(sys.platform == "darwin", "another process's environment is readable on Linux")
    def test_a_herdr_pane_is_found_from_the_ancestry_without_the_targets_environment(self):
        project = self.tmp / "proj"
        project.mkdir()
        # A process named herdr (the server) runs the harness, which waits.
        server_dir = self.tmp / "server"
        server_dir.mkdir()
        (server_dir / "herdr").symlink_to("/bin/sh")
        server_pid = self.tmp / "server.pid"
        codex, codex_pid = self.make_harness("codex", project)
        tree = subprocess.Popen(
            [str(server_dir / "herdr"), "-c", f'echo $$ > "{server_pid}"; "$@"', "herdr", *codex, "sleep", "30"],
            env=self.env,
        )
        self.addCleanup(lambda: (tree.kill(), tree.wait()))
        deadline = time.time() + 10
        while not (server_pid.exists() and codex_pid.exists() and codex_pid.read_text().strip()):
            self.assertLess(time.time(), deadline, "process tree did not start")
            time.sleep(0.05)

        fixtures = self.tmp / "herdr"
        fixtures.mkdir()
        for name, payload in {
            "pane-list": {"result": {"panes": [{"pane_id": "w9:p1"}, {"pane_id": "w1:p1"}]}},
            "pane-get": {"result": {"pane": {"workspace_id": "w1", "tab_id": "w1:t1"}}},
            "workspace-get": {"result": {"workspace": {"label": "ops"}}},
            "tab-get": {"result": {"tab": {"label": "agents"}}},
            "agent-get": {"result": {}},
        }.items():
            (fixtures / f"{name}.json").write_text(json.dumps(payload))
        # Only pane w1:p1's shell is an ancestor of the harness.
        write_exec(self.bin / "herdr", (
            "#!/bin/sh\n"
            'if [ "$1 $2" = "pane process-info" ]; then\n'
            f'  if [ "$4" = w1:p1 ]; then pid=$(cat "{server_pid}"); else pid=1; fi\n'
            '  printf \'{"result":{"process_info":{"shell_pid":%s}}}\' "$pid"\n'
            "  exit 0\n"
            "fi\n"
            f'cat "{fixtures}/$1-$2.json"\n'
        ))

        result = self.run_script(LIB / "locate", "--pid", codex_pid.read_text().strip())

        self.assertEqual(result.returncode, 0, result.stderr)
        identity = json.loads(result.stdout)
        self.assertEqual(identity["harness"], "codex")
        self.assertEqual(identity["project"], "proj")
        self.assertRegex(identity["location"], r"(^|, )herdr ops/agents$")


class AlertClaimTest(OpApprovalTestCase):
    def set_last_alert(self, epoch):
        (self.runtime / "op-approval/last-alert").write_text(f"{epoch}\n")

    def test_fresh_feed_allows_one_alert_per_absence(self):
        now = int(time.time())
        self.write_feed("away", last_present_at=now - 600)

        self.assertEqual(self.claim("take", "--source", "skill").returncode, 0)
        second = self.claim("take", "--source", "watcher")
        self.assertEqual(second.returncode, 3)
        self.assertEqual(second.stdout.strip(), "already alerted during this absence")

        # Rod came back after that alert and left again: a new absence.
        self.set_last_alert(now - 120)
        self.write_feed("away", last_present_at=now - 60)
        self.assertEqual(self.claim("take", "--source", "skill").returncode, 0)

    def test_without_a_fresh_feed_the_time_limit_applies(self):
        for name, write in (
            ("missing", lambda: None),
            ("stale", lambda: self.write_feed("away", age=31, last_present_at=0)),
        ):
            with self.subTest(feed=name):
                shutil.rmtree(self.runtime / "op-approval", ignore_errors=True)
                write()
                self.assertEqual(self.claim("take", "--source", "skill").returncode, 0)
                second = self.claim("take", "--source", "skill")
                self.assertEqual(second.returncode, 3)
                self.assertEqual(second.stdout.strip(), "rate limited")
                self.set_last_alert(int(time.time()) - 301)
                self.assertEqual(self.claim("take", "--source", "skill").returncode, 0)

    def test_watcher_fallback_respects_the_expiry(self):
        now = int(time.time())
        expired_at = now - 130
        cases = (
            ("absent throughout", now - 600, None, 0, None),
            ("back since expiry", now - 10, None, 3, "present since the expiry"),
            ("agent alerted after expiry", now - 600, now - 100, 3, "already alerted after the expiry"),
        )
        for name, last_present, last_alert, code, reason in cases:
            with self.subTest(name):
                shutil.rmtree(self.runtime / "op-approval", ignore_errors=True)
                self.write_feed("away", last_present_at=last_present)
                if last_alert is not None:
                    self.set_last_alert(last_alert)
                result = self.claim("take", "--source", "watcher", "--expired-at", str(expired_at))
                self.assertEqual(result.returncode, code, result.stdout)
                if reason:
                    self.assertEqual(result.stdout.strip(), reason)

    def test_unconfirmed_activity_refuses_an_away_claim(self):
        now = int(time.time())
        # The marker counts until the watcher removes it, even past its time.
        for name, pending_until in (("ahead", now + 30), ("time passed", now - 5)):
            with self.subTest(name):
                self.write_feed("idle", last_present_at=now - 600, pending_until=pending_until)
                result = self.claim("take", "--source", "skill", "--require-away")
                self.assertEqual(result.returncode, 6, result.stdout)
                self.assertEqual(result.stdout.strip(), "activity pending: Rod may be back")
                self.assertFalse((self.runtime / "op-approval/last-alert").exists())

    def test_concurrent_claims_grant_exactly_one(self):
        self.write_feed("away", last_present_at=0)
        procs = [
            subprocess.Popen(
                [str(LIB / "claim"), "take", "--source", "skill"], env=self.env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            for _ in range(8)
        ]
        codes = sorted(p.wait(timeout=60) for p in procs)
        self.assertEqual(codes, [0] + [3] * 7)

    def test_waiters_recover_a_dead_holders_lock_exactly_once(self):
        for attempt in range(5):
            with self.subTest(attempt=attempt):
                shutil.rmtree(self.runtime / "op-approval", ignore_errors=True)
                self.write_feed("away", last_present_at=0)
                # A holder killed while holding the lock leaves it behind.
                subprocess.run(
                    ["sh", "-c", '. "$0/common.sh"; opa_lock_acquire; kill -9 $$', str(LIB)],
                    env=self.env, check=False,
                )
                self.assertTrue((self.runtime / "op-approval/lock").is_symlink())
                procs = [
                    subprocess.Popen(
                        [str(LIB / "claim"), "take", "--source", "skill"], env=self.env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    for _ in range(8)
                ]
                codes = sorted(p.wait(timeout=60) for p in procs)
                self.assertEqual(codes, [0] + [3] * 7)
                leftovers = sorted(p.name for p in (self.runtime / "op-approval").glob("lock*"))
                self.assertEqual(leftovers, [])


class NotifyOutcomeTest(OpApprovalTestCase):
    ARGS = ("--harness", "codex", "--category", "ssh", "--state", "continuing")

    def assert_outcome(self, result, code, name):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(json.loads(result.stdout)["result"], name)

    def test_presence_outside_the_alert_states_sends_nothing(self):
        cases = (
            ("present", {}, 10, "present"),
            ("away", {"alerts": {"presence_states": ["locked"]}}, 13, "excluded_by_config"),
        )
        for state, extra, code, name in cases:
            with self.subTest(state=state):
                fake = self.server()
                self.configure(fake.url, **extra)
                self.write_feed(state, last_present_at=int(time.time()))
                self.assert_outcome(self.notify(*self.ARGS), code, name)
                self.assertEqual(fake.requests, [])

    def notify_while_activity_is_held(self, then_state):
        """Starts notify while the feed holds unconfirmed activity, then
        resolves it to then_state the way the watcher would."""
        fake = self.server()
        self.configure(fake.url)
        now = int(time.time())
        # Its time has already passed; only the watcher removing it counts.
        self.write_feed("idle", last_present_at=now - 600, pending_until=now - 1)
        started = time.monotonic()
        notify = subprocess.Popen(
            [str(SCRIPTS / "notify"), *self.ARGS], env=self.env, cwd=self.tmp,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.addCleanup(notify.kill)
        time.sleep(1.5)
        self.assertIsNone(notify.poll(), "notify decided before the activity was resolved")
        resolved = int(time.time())
        self.write_feed(then_state, last_present_at=resolved if then_state == "present" else now - 600)
        stdout, stderr = notify.communicate(timeout=60)
        self.assertLess(time.monotonic() - started, 9)
        return notify.returncode, json.loads(stdout), stderr, fake

    def test_activity_discarded_as_synthetic_still_alerts(self):
        code, out, stderr, fake = self.notify_while_activity_is_held("idle")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(out["result"], "sent")
        self.assertEqual(len(fake.requests), 1)

    def test_activity_confirmed_as_rod_sends_nothing(self):
        code, out, stderr, fake = self.notify_while_activity_is_held("present")
        self.assertEqual(code, 10, stderr)
        self.assertEqual(out["result"], "present")
        self.assertEqual(fake.requests, [])

    def test_return_while_waiting_for_the_claim_sends_nothing(self):
        if not Path("/proc/self/environ").exists():
            self.skipTest("needs /proc to see the waiting claim")
        fake = self.server()
        self.configure(fake.url)
        self.write_feed("away", last_present_at=0)
        holder = self.hold_lock()

        notify = subprocess.Popen(
            [str(SCRIPTS / "notify"), *self.ARGS], env=self.env, cwd=self.tmp,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.addCleanup(notify.kill)
        self.wait_for_waiting_claim()
        # Rod comes back after notify's early presence check.
        self.write_feed("present", last_present_at=int(time.time()))
        holder.stdin.close()
        holder.wait(timeout=10)

        stdout, stderr = notify.communicate(timeout=60)
        self.assertEqual(notify.returncode, 10, stderr)
        self.assertEqual(json.loads(stdout)["result"], "present")
        self.assertEqual(fake.requests, [])

    def test_a_live_holder_is_waited_on_and_never_evicted(self):
        fake = self.server()
        self.configure(fake.url)
        self.write_feed("away", last_present_at=0)
        holder = self.hold_lock()

        # notify gives up after its bounded wait; the holder is still running.
        blocked = self.notify(*self.ARGS)

        self.assert_outcome(blocked, 1, "failed")
        self.assertIn("lock unavailable", json.loads(blocked.stdout)["reason"])
        self.assertEqual(fake.requests, [])
        # The holder still owns the lock, so its own release removes it.
        holder.stdin.close()
        holder.wait(timeout=10)
        self.assertFalse(os.path.lexists(self.runtime / "op-approval/lock"))
        # The failed attempt recorded no claim.
        self.assert_outcome(self.notify(*self.ARGS), 0, "sent")

    def wait_for_waiting_claim(self):
        claim = str(LIB / "claim").encode()
        home = f"HOME={self.home}".encode()
        deadline = time.time() + 10
        while time.time() < deadline:
            for proc in Path("/proc").iterdir():
                try:
                    if (claim in (proc / "cmdline").read_bytes().split(b"\0")
                            and home in (proc / "environ").read_bytes().split(b"\0")):
                        return
                except OSError:
                    continue
            time.sleep(0.02)
        self.fail("notify never reached the claim")

    def test_alerts_when_stopped_skips_a_continuing_agent(self):
        fake = self.server()
        self.configure(fake.url, alerts={"when": "stopped"})
        self.write_feed("away")
        self.assert_outcome(self.notify(*self.ARGS), 12, "skipped_by_config")
        self.assertEqual(fake.requests, [])

    def test_missing_configuration_fails_soft(self):
        self.write_feed("away")
        for name, setup in (
            ("no config", lambda: None),
            ("no token", lambda: self.write_config({"ntfy": {"url": "http://127.0.0.1:9", "topic": "t"}})),
        ):
            with self.subTest(name):
                (self.runtime / "op-approval" / "last-alert").unlink(missing_ok=True)
                setup()
                self.assert_outcome(self.notify(*self.ARGS), 2, "not_configured")

    def test_failed_publish_consumes_the_claim(self):
        elsewhere = self.server()
        for name, url in (
            ("server error", lambda: self.server(status=500).url),
            ("redirect", lambda: self.server(status=302, location=elsewhere.url).url),
            ("connection refused", closed_port_url),
        ):
            with self.subTest(name):
                (self.runtime / "op-approval" / "last-alert").unlink(missing_ok=True)
                self.configure(url())
                self.write_feed("away", last_present_at=0)
                self.assert_outcome(self.notify(*self.ARGS), 1, "failed")
                second = self.notify(*self.ARGS)
                self.assert_outcome(second, 11, "suppressed")
        self.assertEqual(elsewhere.requests, [])

    def test_every_call_is_listed_and_a_torn_last_line_is_ignored(self):
        self.write_feed("present")
        first = json.loads(self.notify(*self.ARGS).stdout)
        index = self.state_dir / "blocked.jsonl"
        with index.open("a") as handle:
            handle.write('{"ref":"zzzz","time":')

        listing = self.run_script(SCRIPTS / "blocked", "list")

        self.assertEqual(listing.returncode, 0, listing.stderr)
        lines = listing.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn(first["ref"], lines[0])
        self.assertIn("ssh, continuing, present", lines[0])
        self.assertEqual(index.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.state_dir.stat().st_mode & 0o777, 0o700)


class PresenceTest(OpApprovalTestCase):
    def test_feed_is_unknown_unless_fresh_and_well_formed(self):
        now = int(time.time())
        local_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now))
        local_iso = f"{local_iso[:-2]}:{local_iso[-2:]}"
        cases = (
            ("missing", None, "unknown"),
            ("malformed", "{not json", "unknown"),
            ("stale", json.dumps({"state": "away", "updated_epoch": now - 31}), "unknown"),
            ("future", json.dumps({"state": "away", "updated_epoch": now + 60}), "unknown"),
            ("invalid state", json.dumps({"state": "asleep", "updated_epoch": now}), "unknown"),
            ("fresh epoch", json.dumps({"state": "locked", "updated_epoch": now}), "locked"),
            ("fresh ISO with offset", json.dumps({"state": "idle", "updated_at": local_iso}), "idle"),
        )
        for name, raw, state in cases:
            with self.subTest(name):
                self.feed.unlink(missing_ok=True)
                if raw is not None:
                    self.write_feed(raw=raw)
                result = self.run_script(SCRIPTS / "presence")
                self.assertEqual(result.returncode, 0)
                output = json.loads(result.stdout)
                self.assertEqual(output["state"], state)
                self.assertEqual("reason" in output, state == "unknown")

    def test_presence_names_the_watchers_engine_revision(self):
        self.write_feed(raw=json.dumps({"state": "away", "updated_epoch": int(time.time()), "engine": "1a47e90b"}))
        output = json.loads(self.run_script(SCRIPTS / "presence").stdout)
        self.assertEqual(output["engine"], "1a47e90b")


if __name__ == "__main__":
    unittest.main()
