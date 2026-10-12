#!/usr/bin/env python3

import csv
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import venv
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "agents/.agents/skills/persona-panel/scripts"
FACTORS = 11

sys.path[:0] = [str(SCRIPTS), str(Path(__file__).resolve().parent)]
import persona_panel_fakes as fakes  # noqa: E402
import runners  # noqa: E402


def run(script, *args, check=True):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                          capture_output=True, text=True, check=check)


def filled_section(label, scores):
    return "\n".join([
        f"### Concept {label}",
        "**5-second take (in my words):** fine.",
        "",
        "| " + " | ".join(["F"] * FACTORS) + " |",
        "|" + "---|" * FACTORS,
        "| " + " | ".join(str(s) for s in scores) + " |",
        "",
    ])


def finals(ranking):
    lines = ["## Comparison", "### My ranking (best to worst)"]
    lines += [f"{i + 1}. Concept {l} - reason" for i, l in enumerate(ranking)]
    lines += ["", "## Out of character: researcher notes", "Notes."]
    return "\n".join(lines) + "\n"


class PersonaPanelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        for cid in ("01-plain", "02-story", "03-console"):
            d = base / "concepts" / cid
            d.mkdir(parents=True)
            (d / "index.html").write_text(f"<h1>{cid}</h1>")
            (d / "notes.bak").write_text("skip me")
        (base / "concepts/01-plain/pricing.html").write_text("<h1>price</h1>")
        self.cfg = {
            "study": "t", "product": "Acme", "seed": 7, "models": ["opus", "fable"],
            "concepts": [{"id": c, "path": f"../concepts/{c}"} for c in ("01-plain", "02-story", "03-console")],
            "find_the_answer": ["What does it cost?"],
            "leak_terms": ["secret codename"],
            "personas": [
                {"id": "P01", "name": "Dana Kowalski", "role": "Owner", "personality": "Sceptic",
                 "segment": "owner", "bio": ["Runs two cafes."]},
                {"id": "P02", "name": "Sam Lee", "role": "Staff", "personality": "Early adopter",
                 "segment": "staff", "bio": ["Uses the tools daily."]},
            ],
        }
        self.sd = self.study("round-1")
        run("init_study.py", self.sd)
        self.key = self.sd.joinpath("key.md").read_text()
        self.runs = json.loads(self.sd.joinpath("runs.json").read_text())

    def tearDown(self):
        self.tmp.cleanup()

    def study(self, name, **overrides):
        """A study directory holding the base config with overrides, not yet scaffolded."""
        sd = Path(self.tmp.name) / name
        sd.mkdir()
        (sd / "study.json").write_text(json.dumps({**self.cfg, **overrides}))
        return sd

    def labels_for(self, cid):
        for line in self.key.splitlines():
            if f"| {cid} |" in line:
                return line.split("|")[1].strip()
        raise AssertionError(cid)

    def fill(self, run_entry, scores_by_cid, ranking_cids, extra="", sd=None):
        f = (sd or self.sd) / run_entry["file"]
        body = f.read_text()
        for cid, s in scores_by_cid.items():
            body += filled_section(self.labels_for(cid), s)
        body += extra + finals([self.labels_for(c) for c in ranking_cids])
        f.write_text(body)

    def fill_all(self, runs=None, sd=None):
        for r in runs or self.runs:
            self.fill(r, {"01-plain": [8] * FACTORS, "02-story": [6] * 10 + [5], "03-console": [7] * FACTORS},
                      ["01-plain", "03-console", "02-story"], sd=sd)

    def runs_before_model_entries(self):
        """runs.json entries as written before key, runner, effort, replicate and role existed."""
        return [{k: r[k] for k in ("run", "persona", "name", "segment", "model", "file", "prompt")}
                for r in self.runs]

    def quant(self, sd=None):
        return json.loads((sd or self.sd).joinpath("analysis/quant.json").read_text())

    def test_scaffold_is_neutral_and_deterministic(self):
        panel = self.sd / "panel"
        sites = sorted(p.name for p in (panel / "sites").iterdir())
        self.assertEqual(sites, ["concept-A", "concept-B", "concept-C"])
        self.assertFalse(any((panel / "sites").rglob("*.bak")))
        instructions = (panel / "_panel-instructions.md").read_text()
        for cid in ("01-plain", "02-story", "03-console"):
            self.assertNotIn(cid, instructions)
            self.assertNotIn(cid, "".join(p.read_text() for p in (panel / "personas").glob("*.md")))
        self.assertIn("What does it cost?", instructions)
        self.assertIn("**Pages I looked at:**", instructions)
        self.assertNotIn("—", instructions)
        self.assertFalse((panel / "key.md").exists())
        self.assertEqual(len(self.runs), 4)
        orders = {}
        for f in (panel / "personas").glob("*.md"):
            line = next(l for l in f.read_text().splitlines() if l.startswith("| Review order"))
            orders.setdefault(f.name.split("-")[0], set()).add(line)
        self.assertTrue(all(len(v) == 1 for v in orders.values()), orders)
        first_key = self.key
        run("init_study.py", self.sd, "--force")
        self.assertEqual(first_key, self.sd.joinpath("key.md").read_text())
        self.assertIn("Read nothing outside", self.sd.joinpath(self.runs[0]["prompt"]).read_text())

    def test_init_refuses_to_overwrite_runs(self):
        r = run("init_study.py", self.sd, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--force", r.stderr)
        # runs.json alone is guarded too: it holds run state that the persona files do not.
        for f in (self.sd / "panel/personas").glob("*.md"):
            f.unlink()
        before = self.sd.joinpath("runs.json").read_text()
        r = run("init_study.py", self.sd, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--force", r.stderr)
        self.assertEqual(before, self.sd.joinpath("runs.json").read_text())

    def test_invalid_model_entries_and_options_are_refused(self):
        cases = {
            "name unusable as a key": ({"models": ["claude-opus-4"]}, 'needs a "key"'),
            "key with a hyphen": ({"models": [{"key": "opus-high", "model": "opus"}]}, "letters and digits"),
            "duplicate key": ({"models": ["opus", {"key": "opus", "model": "opus", "effort": "high"}]},
                              'repeats the key "opus"'),
            "native and runner entries": ({"models": ["opus", {"key": "cx", "runner": "codex"}]},
                                          "one or the other"),
            "unknown study type": ({"type": "survey"}, 'unknown "type"'),
            "runner that does not exist": ({"runner": "nope"}, 'Unknown runner "nope". Available runners: claude'),
            "override for an unknown key": ({"limits": {"overrides": {"sonnet": {"minutes": 5}}}},
                                            '"sonnet" is not a model key'),
        }
        for i, (name, (overrides, message)) in enumerate(cases.items()):
            with self.subTest(name):
                sd = self.study(f"bad-{i}", **overrides)
                r = run("init_study.py", sd, check=False)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(message, r.stderr)
                self.assertFalse((sd / "runs.json").exists())

    def test_model_entries_and_replicates_name_runs_and_files(self):
        sd = self.study("entries", runner="claude", replicates=2, models=[
            "opus",
            {"key": "haikuLow", "model": "haiku", "effort": "low"},
            {"key": "haikuHigh", "model": "haiku", "effort": "high"},
            {"key": "other", "runner": "codex"},
        ], model_notes={"haiku": ["Note by model name."], "haikuHigh": ["Note by key."]})
        run("init_study.py", sd)
        runs = {r["run"]: r for r in json.loads(sd.joinpath("runs.json").read_text())}
        self.assertEqual([r for r in runs if r.startswith("P01-")], [
            "P01-opus", "P01-opus-r2", "P01-haikuLow", "P01-haikuLow-r2",
            "P01-haikuHigh", "P01-haikuHigh-r2", "P01-other", "P01-other-r2"])
        self.assertEqual(len(runs), 16)
        first, second = runs["P01-opus"], runs["P01-haikuLow-r2"]
        self.assertEqual(first["file"], "panel/personas/P01-dana-kowalski--opus.md")
        self.assertEqual(second["file"], "panel/personas/P01-dana-kowalski--haikuLow-r2.md")
        self.assertEqual(second["prompt"], "prompts/P01-haikuLow-r2.md")
        self.assertTrue(all((sd / r["file"]).exists() and (sd / r["prompt"]).exists() for r in runs.values()))
        fields = ("key", "runner", "model", "effort", "replicate", "role")
        self.assertEqual([first[k] for k in fields], ["opus", "claude", "opus", None, 1, "panellist"])
        self.assertEqual([second[k] for k in fields], ["haikuLow", "claude", "haiku", "low", 2, "panellist"])
        self.assertEqual([runs["P01-other"][k] for k in fields], ["other", "codex", None, None, 1, "panellist"])
        low = sd.joinpath(second["prompt"]).read_text()
        high = sd.joinpath(runs["P01-haikuHigh"]["prompt"]).read_text()
        self.assertIn("Note by model name.", low)
        self.assertIn("Note by key.", high)
        self.assertNotIn("Note by model name.", high)
        self.assertNotIn("Note by", sd.joinpath(first["prompt"]).read_text())

    def test_browse_setting_decides_what_panellists_are_told_about_the_browser(self):
        offered, ruled_out = "If you use agent-browser, your run id is `P01-", "agent-browser CLI is not available"
        both = [{"key": "a", "runner": "claude"}, {"key": "b", "runner": "codex"}]
        cases = {  # study settings: (the instructions offer the browser, {model key: what its run prompt says})
            "native study, browsing by default": ({}, True, {"opus": offered, "fable": offered}),
            "browsing switched off": ({"browse": False, "models": both}, False, {"a": None, "b": None}),
            "a runner that cannot drive a browser": ({"models": both}, True, {"a": offered, "b": ruled_out}),
        }
        for i, (name, (settings, in_instructions, prompts)) in enumerate(cases.items()):
            with self.subTest(name):
                sd = self.study(f"browse-{i}", **settings)
                run("init_study.py", sd)
                instructions = sd.joinpath("panel/_panel-instructions.md").read_text()
                self.assertEqual("agent-browser" in instructions, in_instructions)
                self.assertIn("3. **Write only to your own persona file.**", instructions)
                for key, says in prompts.items():
                    prompt = sd.joinpath(f"prompts/P01-{key}.md").read_text()
                    self.assertEqual([x for x in (offered, ruled_out) if x in prompt], [says] if says else [])
                    self.assertEqual("agent-browser" in prompt, bool(says))

    def test_native_and_runner_studies_keep_to_their_own_tools(self):
        through_runners = self.study("through-runners", runner="claude")
        run("init_study.py", through_runners)
        cases = [  # script, study, arguments, what the refusal points at
            ("launch.py", self.sd, ["run"], "runs.py"),
            ("launch.py", self.sd, ["resume"], "runs.py"),
            ("launch.py", self.sd, ["pilot"], "runs.py"),
            ("runs.py", through_runners, ["next"], "launch.py"),
            ("runs.py", through_runners, ["mark", "P01-opus", "agent-123"], "launch.py"),
            ("runs.py", through_runners, ["resume"], "launch.py"),
        ]
        for script, sd, arguments, points_at in cases:
            with self.subTest(f"{script} {arguments[0]}"):
                before = sd.joinpath("runs.json").read_text()
                r = run(script, sd, *arguments, check=False)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(points_at, r.stderr)
                self.assertEqual(before, sd.joinpath("runs.json").read_text())
        self.assertIn("pending: 4", run("runs.py", through_runners, "status").stdout)

    def test_replicates_count_as_separate_runs(self):
        sd = self.study("replicates", replicates=2)
        run("init_study.py", sd)
        runs = json.loads(sd.joinpath("runs.json").read_text())
        self.fill_all(runs, sd)
        self.assertIn("done: 8", run("runs.py", sd, "status").stdout)
        out = run("extract_scores.py", sd).stdout
        self.assertIn("24 score rows from 8 runs; 0 runs incomplete", out)
        self.assertIn("- 8 runs,", run("analyze.py", sd).stdout)
        quant = self.quant(sd)
        self.assertEqual(quant["leaderboard"][0]["first"], 8)
        second = next(r for r in runs if r["run"] == "P01-opus-r2")
        f = sd / second["file"]
        f.write_text(f.read_text() + "### Concept Z\nInvented.\n")
        r = run("check_runs.py", sd, check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("| P01-opus-r2 | unknown concept labels: Z |", r.stdout)
        self.assertIn("8 run files of 8 expected; 1 with blocking problems", r.stdout)

    def test_single_concept_run_is_done_by_its_persona_file(self):
        sd = self.study("single", models=["opus"], concepts=self.cfg["concepts"][:1])
        run("init_study.py", sd)
        whole, cut_off = json.loads(sd.joinpath("runs.json").read_text())
        section = filled_section("A", [7] * FACTORS)
        for r, tail in ((whole, "## Out of character: researcher notes\nNotes.\n"), (cut_off, "")):
            f = sd / r["file"]
            f.write_text(f.read_text() + section + tail)
        out = run("runs.py", sd, "status").stdout
        self.assertIn(f"{whole['run']:<16} done", out)
        self.assertIn(f"{cut_off['run']:<16} started", out)
        self.assertIn("2 score rows from 2 runs; 1 runs incomplete", run("extract_scores.py", sd).stdout)

    def test_runs_status_and_next(self):
        out = run("runs.py", self.sd, "next", "--limit", "3", "--running", "P01-opus").stdout
        self.assertIn("2 to launch", out)
        self.assertNotIn("=== P01-opus", out)
        self.fill_all()
        out = run("runs.py", self.sd, "status").stdout
        self.assertIn("done: 4", out)

    def test_pipeline_scores_checks_and_analysis(self):
        self.fill_all()
        self.assertEqual(run("check_runs.py", self.sd).returncode, 0)
        out = run("extract_scores.py", self.sd).stdout
        self.assertIn("12 score rows from 4 runs; 0 runs incomplete", out)
        run("analyze.py", self.sd)
        quant = self.quant()
        top = quant["leaderboard"][0]
        self.assertEqual(top["concept"], self.labels_for("01-plain"))
        self.assertEqual(top["first"], 4)
        self.assertEqual(top["borda"], 12)
        self.assertEqual(quant["leaderboard"][-1]["concept"], self.labels_for("02-story"))
        self.assertEqual(len(quant["fit"]["personas"]), 2)
        self.assertIn("| Top 1 | Bottom 1 |", self.sd.joinpath("analysis/quant.md").read_text())
        seg = run("analyze.py", self.sd, "--segment", "owner").stdout
        self.assertIn("2 runs", seg)

    def test_run_stopped_by_a_limit_is_listed_apart_from_the_headline_tables(self):
        stopped, *whole = self.runs
        self.fill_all(whole)
        plain, story = self.labels_for("01-plain"), self.labels_for("02-story")
        # Cut off before its last concept, with scores and a ranking that would change every table.
        f = self.sd / stopped["file"]
        f.write_text(f.read_text() + filled_section(story, [10] * FACTORS) + filled_section(plain, [1] * FACTORS)
                     + f"## Comparison\n### My ranking (best to worst)\n1. Concept {story} - reason\n")
        stopped["state"] = "limited"
        self.sd.joinpath("runs.json").write_text(json.dumps(self.runs))
        run("extract_scores.py", self.sd)
        self.assertIn("3 of 4 runs complete", run("analyze.py", self.sd).stdout)
        quant = self.quant()
        self.assertEqual((quant["runs"]["complete"], quant["runs"]["expected"]), (3, 4))
        board = {d["concept"]: d for d in quant["leaderboard"]}
        self.assertEqual([(board[c]["n"], board[c]["first"], board[c]["mean"]) for c in (plain, story)],
                         [(3, 3, 8), (3, 0, 5)])
        self.assertEqual(quant["factors"][story]["overall"], 5)
        self.assertEqual(quant["segments"][stopped["segment"]][story], 5)
        self.assertEqual(quant["models"]["per_model"][stopped["key"]][story], 5)
        self.assertEqual(quant["persona_matrix"][stopped["persona"]][story], 5)
        [listed] = quant["runs"]["incomplete"]
        self.assertEqual((listed["run"], listed["state"], listed["overall"]),
                         (stopped["run"], "limited", {story: 10, plain: 1}))
        md = self.sd.joinpath("analysis/quant.md").read_text()
        self.assertIn(f"| {stopped['run']} | {stopped['name']} | limited | 2 of 3 | 2 of 3 | no |",
                      md[md.index("## Incomplete runs"):])

    def test_analysis_with_no_complete_run_ranks_nothing(self):
        started = self.runs[0]
        f = self.sd / started["file"]
        f.write_text(f.read_text() + filled_section(self.labels_for("01-plain"), [8] * FACTORS))
        run("extract_scores.py", self.sd)
        out = run("analyze.py", self.sd).stdout
        self.assertIn("0 of 4 runs complete", out)
        self.assertIn("nothing to rank", out)
        quant = self.quant()
        self.assertNotIn("leaderboard", quant)
        self.assertEqual(quant["runs"]["not_started"], 3)
        self.assertEqual([(d["run"], d["state"]) for d in quant["runs"]["incomplete"]], [(started["run"], "partial")])

    def test_checks_flag_problems(self):
        self.fill_all()
        f = self.sd / self.runs[0]["file"]
        a = self.labels_for("01-plain")
        text = f.read_text() + filled_section(a, [9] * FACTORS) + "Mentions the secret codename — oops.\n"
        text += "### Concept Z\nInvented.\n"
        f.write_text(text)
        r = run("check_runs.py", self.sd, check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("duplicate sections", r.stdout)
        self.assertIn("unknown concept labels: Z", r.stdout)
        self.assertIn("leak terms: secret codename", r.stdout)
        self.assertIn("em/en dashes", r.stdout)

    def test_ranking_contradiction_flagged(self):
        r0 = self.runs[0]
        self.fill(r0, {"01-plain": [9] * FACTORS, "02-story": [3] * FACTORS, "03-console": [6] * FACTORS},
                  ["02-story", "01-plain", "03-console"])
        out = run("check_runs.py", self.sd, check=False).stdout
        self.assertIn("ranking puts", out)

    def test_mark_and_resume(self):
        r0, r1 = self.runs[0], self.runs[1]
        run("runs.py", self.sd, "mark", r0["run"], "agent-123")
        f = self.sd / r0["file"]
        f.write_text(f.read_text() + filled_section(self.labels_for("01-plain"), [8] * FACTORS))
        out = run("runs.py", self.sd, "resume").stdout
        self.assertIn(f"=== {r0['run']} (started, agent: agent-123)", out)
        self.assertIn(f"Already written: {self.labels_for('01-plain')}", out)
        self.assertIn(f"=== {r1['run']} (pending, agent: not recorded", out)
        nxt = run("runs.py", self.sd, "next", "--limit", "20").stdout
        self.assertNotIn(f"=== {r0['run']}", nxt)

    def test_runs_json_from_before_model_entries_still_works(self):
        old = self.runs_before_model_entries()
        old[0]["session"] = "kept"  # a field these scripts know nothing about
        self.sd.joinpath("runs.json").write_text(json.dumps(old))
        run("runs.py", self.sd, "mark", old[0]["run"], "agent-123")
        saved = json.loads(self.sd.joinpath("runs.json").read_text())
        self.assertEqual((saved[0]["session"], saved[0]["agent"]), ("kept", "agent-123"))
        states = json.loads(run("runs.py", self.sd, "status", "--json").stdout)
        self.assertEqual([s["run"] for s in states], [r["run"] for r in old])
        for s in states:
            self.assertEqual((s["key"], s["runner"], s["replicate"], s["role"], s["state"]),
                             (s["model"], None, 1, "panellist", "pending"))

    def test_persona_model_agreement(self):
        for r in self.runs:
            if r["model"] == "opus":
                self.fill(r, {"01-plain": [9] * FACTORS, "02-story": [5] * FACTORS, "03-console": [7] * FACTORS},
                          ["01-plain", "03-console", "02-story"])
            else:
                self.fill(r, {"01-plain": [5] * FACTORS, "02-story": [9] * FACTORS, "03-console": [7] * FACTORS},
                          ["02-story", "03-console", "01-plain"])
        run("extract_scores.py", self.sd)
        run("analyze.py", self.sd)
        q = self.quant()
        agree = q["models"]["persona_agreement"]
        self.assertTrue(all(not a["same_top"] for a in agree))
        self.assertAlmostEqual(agree[0]["spearman"], -1.0)
        self.assertIn("Unsettled personas", self.sd.joinpath("analysis/quant.md").read_text())

    def test_extract_agent_reply(self):
        t = Path(self.tmp.name) / "out.jsonl"
        doc = "Here it is.\n\n# Round 1 synthesis\n\n- point\n"
        t.write_text("\n".join(json.dumps(x) for x in [
            {"message": {"role": "user", "content": "go"}},
            {"message": {"role": "assistant", "content": [{"type": "text", "text": doc}]}},
        ]))
        out = Path(self.tmp.name) / "s.md"
        run("extract_agent_reply.py", t, "--out", out)
        self.assertEqual(out.read_text(), "# Round 1 synthesis\n\n- point\n")

    def test_archive_keeps_findings_and_drops_bulk(self):
        self.fill_all()
        run("extract_scores.py", self.sd)
        (self.sd / "panel/materials/concept-A/index").mkdir(parents=True)
        (self.sd / "panel/materials/concept-A/index/page-text.txt").write_text("x")
        dest = Path(self.tmp.name) / "archive/customer-research/2026-09-25-t/panel/round-1"
        run("archive.py", self.sd, "--dest", dest)
        self.assertTrue((dest / "personas").is_dir())
        self.assertTrue((dest / "panel-instructions.md").exists())
        self.assertTrue((dest / "analysis/scores.csv").exists())
        self.assertTrue((dest / "key.md").exists())
        self.assertFalse((dest / "materials").exists())
        self.assertFalse((dest / "sites").exists())

    def test_archived_study_from_before_run_completeness_still_analyses(self):
        self.fill_all()
        run("extract_scores.py", self.sd)
        dest = Path(self.tmp.name) / "archive/round-1"
        run("archive.py", self.sd, "--dest", dest)
        # Put the archive back to what an older round holds: no runs.csv, no replicate or complete
        # columns, and runs.json entries with the original fields.
        (dest / "analysis/runs.csv").unlink()
        for name in ("scores.csv", "rankings.csv"):
            with open(dest / "analysis" / name) as f:
                rows = list(csv.DictReader(f))
            with open(dest / "analysis" / name, "w", newline="") as f:
                w = csv.DictWriter(f, [c for c in rows[0] if c not in ("replicate", "complete")],
                                   extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
        (dest / "runs.json").write_text(json.dumps(self.runs_before_model_entries()))

        def top():
            self.assertIn("4 of 4 runs complete", run("analyze.py", dest).stdout)
            return self.quant(dest)["leaderboard"][0]

        as_archived = top()
        self.assertEqual((as_archived["concept"], as_archived["first"]), (self.labels_for("01-plain"), 4))
        self.assertIn("12 score rows from 4 runs; 0 runs incomplete", run("extract_scores.py", dest).stdout)
        self.assertEqual(top(), as_archived)


# The options each runner passes on every launch, written out: they are its contract with the CLI.
CLAUDE_ISOLATION = ["--safe-mode", "--restricted", "--strict-mcp-config", "--disable-slash-commands",
                    "--settings", '{"includeGitInstructions":false}']
CLAUDE_OUTPUT = ["--permission-mode", "dontAsk", "--output-format", "stream-json", "--verbose"]
CLAUDE_FILES = "Read,Write,Edit,Glob,Grep"
CODEX_OPTIONS = ["exec", "--json", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules",
                 "-c", "project_doc_max_bytes=0", "-c", "skills.include_instructions=false",
                 "-c", "approval_policy=never", "--disable", "plugins", "--disable", "tool_suggest",
                 "-s", "workspace-write"]
SESSION = "937a3347-a2b1-41c3-a9d3-8be11344d2a6"
RUN = {"run": "P01-opusHigh", "model": "opus", "effort": "high", "role": "panellist", "browse": True}
BARE = {"run": "analyst-1", "model": None, "effort": None, "role": "analyst"}
LIMITS = {"minutes": 15, "budget_usd": 2.0}
PROMPT = "--not-an-option\nYou are P01. Read panel/_panel-instructions.md.\n"


class RunnerTest(unittest.TestCase):
    """The runner adapters, against fake CLIs on PATH and output recorded from the real ones."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="persona-panel-runners-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin, self.workdir, self.log = self.tmp / "bin", self.tmp / "study/panel", self.tmp / "cli.log"
        self.bin.mkdir()
        self.workdir.mkdir(parents=True)
        fakes.install(self.bin)
        # Only the fakes, throwaway homes and none of a host session's variables reach a runner.
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("CLAUDE", "ANTHROPIC", "CODEX", "OPENAI", "AI_AGENT", "FAKE_"))}
        env.update(PATH=f"{self.bin}{os.pathsep}{env.get('PATH', '/usr/bin:/bin')}", HOME=str(self.tmp / "home"),
                   CLAUDE_CONFIG_DIR=str(self.tmp / "claude-home"), CODEX_HOME=str(self.tmp / "codex-home"),
                   FAKE_CLI_LOG=str(self.log))
        self.steer(clear=True, **env)

    def steer(self, clear=False, **env):
        patch = mock.patch.dict(os.environ, env, clear=clear)
        patch.start()
        self.addCleanup(patch.stop)
        return patch

    def invoke(self, runner, command):
        """Start a runner's command the way a launcher would, and parse what comes back."""
        r = subprocess.run(command["argv"], input=command["stdin"], env=command["env"], cwd=self.workdir,
                           capture_output=True, text=True, timeout=30)
        return runner.parse_result(r.stdout, r.stderr, r.returncode)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def session_file(self, thread_id):
        d = self.tmp / "codex-home/sessions/2026/10/12"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"rollout-2026-10-12T20-22-31-{thread_id}.jsonl").write_text(fakes.recorded("codex", "session-file"))

    def test_runners_are_found_by_listing_the_package(self):
        more = self.tmp / "more"
        more.mkdir()
        (more / "_shared.py").write_text("")
        (more / "half.py").write_text("def capabilities():\n    return {}\n")
        (more / "echo.py").write_text("".join(
            f"def {f}(*args):\n    return {{'effort_levels': []}}\n" for f in runners.INTERFACE))
        runners.__path__.append(str(more))
        self.addCleanup(runners.__path__.remove, str(more))
        self.addCleanup(lambda: [sys.modules.pop(f"runners.{m}", None) for m in ("echo", "half")])
        self.assertEqual(runners.names(), ["claude", "codex", "echo", "half"])
        self.assertEqual(runners.get("echo").capabilities(), {"effort_levels": []})
        note = runners.check_effort({"runner": "echo", "effort": "high"})
        self.assertEqual((note["effort"], note["error"]), (None, None))
        self.assertIn("ignored", note["note"])
        refusals = {"half": "launch_command", "nope": "claude, codex, echo, half", "_shared": "Unknown"}
        for name, message in refusals.items():
            with self.subTest(name), self.assertRaises(SystemExit) as refused:
                runners.get(name)
            self.assertIn(message, str(refused.exception))

    def test_runner_commands_for_a_run(self):
        panel = str(self.workdir)
        left = {"minutes": 4, "budget_usd": 0.75}
        browsing = ["--tools", CLAUDE_FILES + ",Bash", "--allowed-tools", CLAUDE_FILES + ",Bash(agent-browser:*)"]
        files_only = ["--tools", CLAUDE_FILES, "--allowed-tools", CLAUDE_FILES]
        cases = {  # (runner, run, limits, resumed): the argv after the executable; "<new>" is a fresh session id
            ("claude", "model, effort, budget, browsing", False): (RUN, LIMITS, [
                "-p", "--session-id", "<new>", "--model", "opus", "--effort", "high", "--max-budget-usd", "2",
                *CLAUDE_ISOLATION, *browsing, *CLAUDE_OUTPUT]),
            ("claude", "resumed with what is left of the budget", True): (RUN, left, [
                "-p", "--resume", SESSION, "--model", "opus", "--effort", "high", "--max-budget-usd", "0.75",
                *CLAUDE_ISOLATION, *browsing, *CLAUDE_OUTPUT]),
            ("claude", "default model, no effort, no cap, no browsing", False): (
                BARE, {"minutes": 30, "budget_usd": None},
                ["-p", "--session-id", "<new>", *CLAUDE_ISOLATION, *files_only, *CLAUDE_OUTPUT]),
            ("codex", "model and effort", False): (RUN, LIMITS, [
                *CODEX_OPTIONS, "-C", panel, "-m", "opus", "-c", "model_reasoning_effort=high", "-"]),
            ("codex", "resumed, options before the word resume", True): (RUN, left, [
                *CODEX_OPTIONS, "-C", panel, "-m", "opus", "-c", "model_reasoning_effort=high",
                "resume", SESSION, "-"]),
            ("codex", "default model, no effort", False): (BARE, LIMITS, [*CODEX_OPTIONS, "-C", panel, "-"]),
        }
        for (name, what, resumed), (entry, limits, expected) in cases.items():
            with self.subTest(f"{name}: {what}"):
                runner = runners.get(name)
                command = (runner.resume_command(entry, SESSION, PROMPT, self.workdir, limits) if resumed
                           else runner.launch_command(entry, PROMPT, self.workdir, limits))
                expected = [command["session_id"] if x == "<new>" else x for x in expected]
                self.assertEqual(command["argv"], [name, *expected])
                self.assertEqual(command["stdin"], PROMPT)
                if resumed:
                    self.assertEqual(command["session_id"], SESSION)
        ids = {runners.get("claude").launch_command(RUN, PROMPT, self.workdir, LIMITS)["session_id"] for _ in range(2)}
        self.assertEqual(len(ids), 2)  # the CLI refuses an id that already has a transcript

    def test_runner_refuses_an_effort_or_budget_it_cannot_launch(self):
        for name in ("claude", "codex"):
            with self.subTest(name):
                self.assertEqual(runners.check_effort({"runner": name, "effort": "high"}),
                                 {"effort": "high", "error": None, "note": None})
                self.assertIn('"ultra"', runners.check_effort({"runner": name, "effort": "ultra"})["error"])
                with self.assertRaises(ValueError):
                    runners.get(name).launch_command({**RUN, "effort": "ultra"}, PROMPT, self.workdir, LIMITS)
                with self.assertRaises(ValueError):
                    runners.get(name).resume_command(RUN, "--last", PROMPT, self.workdir, LIMITS)
        with self.assertRaises(ValueError):
            runners.get("claude").resume_command(RUN, SESSION, PROMPT, self.workdir, {"minutes": 1, "budget_usd": 0})

    def test_runner_command_runs_and_resumes_through_the_cli(self):
        self.steer(CLAUDECODE="1", CLAUDE_CODE_ENTRYPOINT="claude-desktop", CLAUDE_CODE_SESSION_ID="host",
                   CLAUDE_EFFORT="max", CLAUDE_AGENT_SDK_VERSION="1", AI_AGENT="host",
                   ANTHROPIC_BASE_URL="https://api.example.test", CLAUDE_CODE_USE_BEDROCK="1")
        for name in ("claude", "codex"):
            with self.subTest(name):
                runner = runners.get(name)
                command = runner.launch_command(RUN, PROMPT, self.workdir, LIMITS)
                first = self.invoke(runner, command)
                self.assertEqual((first["outcome"], first["message"]), ("ok", ""))
                self.assertEqual(first["session_id"], command["session_id"] or first["session_id"])
                again = runner.resume_command(RUN, first["session_id"], "Carry on.", self.workdir, LIMITS)
                second = self.invoke(runner, again)
                self.assertEqual((second["outcome"], second["session_id"]), ("ok", first["session_id"]))
                seen = [c for c in self.calls() if c["cli"] == name]
                self.assertEqual([(c["stdin"], c["model_call"]) for c in seen], [(PROMPT, True), ("Carry on.", True)])
        # A panel started from inside a Claude Code session runs as it would from a terminal: the
        # host's session variables are gone, the ones that choose the login and the provider stay.
        child = next(c for c in self.calls() if c["cli"] == "claude")["env"]
        self.assertEqual(sorted(child), ["ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CONFIG_DIR"])

    def test_runner_parses_recorded_outcomes(self):
        cut = '\n{"type":"assist'  # a killed process can stop in the middle of a line
        codex_failed = fakes.recorded("codex", "error").splitlines()[:2]

        def codex_turn_failed(message):
            return "\n".join([*codex_failed, json.dumps({"type": "turn.failed", "error": {"message": message}})])

        capacity = "Selected model is at capacity. Please try a different model."
        codex_lost = ("Error: thread/resume: thread/resume failed: no rollout found for thread id "
                      f"{SESSION} (code -32600)")
        self.session_file("01a12fa4-7711-7c80-81b0-602e1088a61b")  # the thread of codex/usage-limit and codex/error
        none = {"input_tokens": None, "output_tokens": None, "cached_tokens": None, "cost_usd": None}
        cases = [  # runner, what, stdout, stderr, exit code, expected fields, expected usage figures
            ("claude", "ok", fakes.recorded("claude", "ok"), "", 0,
             {"outcome": "ok", "session_id": "1bb4f919-145f-470d-a5b8-97f90a6a8095", "message": "",
              "reply": "Reviewed 3 concepts. Ranking: B, A, C.", "reset_at": None},
             {"input_tokens": 2956, "output_tokens": 597, "cached_tokens": 2234, "cost_usd": 0.00046504,
              "duration_s": 3.441, "scope": "session"}),
            ("claude", "usage limit", fakes.recorded("claude", "usage-limit.inferred"), "", 1,
             {"outcome": "usage_limit", "reset_at": 1789377600, "reply": None,
              "message": "You've hit your session limit · resets 3:30am (Australia/Brisbane)"}, none),
            ("claude", "budget reached", fakes.recorded("claude", "budget"), "", 1,
             {"outcome": "budget", "reply": None, "message": "Reached maximum budget ($0.001)"},
             {"input_tokens": 7179, "output_tokens": 151, "cached_tokens": 0, "cost_usd": 0.0015111}),
            ("claude", "error that calls itself a success", fakes.recorded("claude", "error"), "", 1,
             {"outcome": "error", "reply": None, "reset_at": None, "message": "Not logged in · Please run /login"},
             none),
            ("claude", "killed part-way", fakes.recorded("claude", "killed") + cut, "", 143,
             {"outcome": "error", "session_id": "c3a8c385-cb68-47a7-bd67-468f6474c8a3", "reply": None,
              "message": "claude ended without a result (exit code 143)", "session_lost": False},
             {**none, "duration_s": None}),
            ("claude", "resume of a session that is gone", "", f"No conversation found with session ID: {SESSION}\n",
             1, {"outcome": "error", "session_id": None, "session_lost": True,
                 "message": f"No conversation found with session ID: {SESSION}"}, none),
            ("codex", "ok", fakes.recorded("codex", "ok"), "", 0,
             {"outcome": "ok", "session_id": "01a12fa7-d29f-7d11-8724-e3d666a19ca3", "message": "",
              "reply": "codename=NONE; skills=0; agents=yes", "reset_at": None},
             {"input_tokens": 82346, "output_tokens": 297, "cached_tokens": 67968, "cost_usd": None,
              "duration_s": None, "scope": "session"}),
            ("codex", "ok with a warning item", fakes.recorded("codex", "resume-2"), "", 0,
             {"outcome": "ok", "reply": "OK"}, {"input_tokens": 168428}),
            ("codex", "usage limit, reset time from the session file",
             fakes.recorded("codex", "usage-limit.inferred"), "", 1,
             {"outcome": "usage_limit", "reset_at": 1792307493, "reply": None}, {}),
            ("codex", "model at capacity", codex_turn_failed(capacity), "", 1,
             {"outcome": "usage_limit", "reset_at": None, "message": capacity}, {}),
            ("codex", "budget reached", fakes.recorded("codex", "budget"), "", 1,
             {"outcome": "budget", "reply": None, "message": "shared rollout token budget exhausted"}, none),
            ("codex", "turn refused by the API, usage from the session file", fakes.recorded("codex", "error"), "", 1,
             {"outcome": "error", "reset_at": None, "reply": None,
              "message": "Invalid response.create payload: Invalid value: 'bogus'. Supported values are: "
                         "'none', 'minimal', 'low', 'medium', 'high', 'xhigh', and 'max'."},
             {"input_tokens": 168428, "output_tokens": 410, "cached_tokens": 125696}),
            ("codex", "killed part-way", fakes.recorded("codex", "killed") + cut, "", 143,
             {"outcome": "error", "session_id": "01a12fa3-d891-7951-8317-db9ab75fac57", "reply": None,
              "message": "codex ended before finishing its turn (exit code 143)"}, none),
            ("codex", "refused before starting", "",
             "Not inside a trusted directory and --skip-git-repo-check was not specified.\n", 1,
             {"outcome": "error", "session_id": None, "session_lost": False,
              "message": "Not inside a trusted directory and --skip-git-repo-check was not specified."}, none),
            ("codex", "resume of a session that is gone", "", f"{codex_lost}\n", 1,
             {"outcome": "error", "session_id": None, "session_lost": True, "message": codex_lost}, none),
            ("claude", "no output at all", "", "", None, {"outcome": "error", "session_id": None}, none),
            ("codex", "no output at all", None, None, None, {"outcome": "error", "session_id": None}, none),
        ]
        for name, what, stdout, stderr, code, fields, figures in cases:
            with self.subTest(f"{name}: {what}"):
                parsed = runners.get(name).parse_result(stdout, stderr, code)
                self.assertEqual(sorted(parsed), ["message", "outcome", "reply", "reset_at", "session_id",
                                                  "session_lost", "usage"])
                self.assertEqual({k: parsed[k] for k in fields}, fields)
                self.assertEqual({k: parsed["usage"][k] for k in figures}, figures)

    def test_usage_of_a_resumed_session_is_not_counted_twice(self):
        totals = {"claude": (66946, 0.0018137100000000003), "codex": (168428, None)}
        sessions = {}
        for name, expected in totals.items():
            with self.subTest(name):
                for part in ("resume-1", "resume-2"):  # two results of one session, each a running total
                    reported = runners.get(name).parse_result(fakes.recorded(name, part), "", 0)["usage"]
                    sessions[name] = runners.merge_usage(sessions.get(name), reported)
                killed = runners.get(name).parse_result(fakes.recorded(name, "killed"), "", 143)["usage"]
                sessions[name] = runners.merge_usage(sessions[name], killed)  # reports nothing, loses nothing
                self.assertEqual((sessions[name]["input_tokens"], sessions[name]["cost_usd"]), expected)
        self.assertAlmostEqual(sessions["claude"]["duration_s"], 1.822 + 4.877)  # each process's own wall time
        run_total = runners.total_usage(list(sessions.values()))  # a run restarted in a second session
        self.assertEqual((run_total["input_tokens"], run_total["cost_usd"]), (66946 + 168428, 0.0018137100000000003))
        per_process = runners.merge_usage({"input_tokens": 5}, runners.usage("process", input_tokens=7))
        self.assertEqual(per_process["input_tokens"], 12)

    def test_runner_check_reports_what_the_cli_says(self):
        cases = {"claude": ("--restricted", "2.1.296"), "codex": ("--ignore-rules", "codex-cli 0.162.1")}
        for name, (option, version) in cases.items():
            with self.subTest(name):
                runner, mode = runners.get(name), f"FAKE_{name.upper()}"
                ready = runner.check()
                self.assertTrue(ready["ok"], ready)
                self.assertIn(version, ready["message"])
                self.assertNotIn("example.com", ready["message"])  # the account's email is not passed on
                with mock.patch.dict(os.environ, {mode: "signed_out"}):
                    signed_out = runner.check()
                self.assertEqual((signed_out["ok"], "Not logged in" in signed_out["message"]), (False, True),
                                 signed_out)
                with mock.patch.dict(os.environ, {mode: f"no_flag:{option}"}):
                    changed = runner.check()
                self.assertEqual((changed["ok"], option in changed["message"]), (False, True), changed)
                self.assertFalse([c for c in self.calls() if c["model_call"]])
                with mock.patch.dict(os.environ, {"PATH": str(self.tmp / "empty")}):
                    missing = runner.check()
                self.assertEqual((missing["ok"], name in missing["message"]), (False, True), missing)
        with mock.patch.dict(os.environ, {"FAKE_CODEX": "warns"}):  # a sandboxed CLI warns before it answers
            self.assertEqual(runners.get("codex").check()["message"], "codex-cli 0.162.1, Logged in using ChatGPT")

    def test_runner_purge_commands_name_one_session(self):
        claude, codex = runners.get("claude"), runners.get("codex")
        transcript = self.tmp / "claude-home/projects/-study-panel" / f"{SESSION}.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text("{}\n")
        self.assertEqual(claude.purge_command(SESSION, self.workdir),
                         ["rm", "-rf", "--", str(transcript), str(transcript.with_suffix(""))])
        self.assertIsNone(claude.purge_command("1bb4f919-145f-470d-a5b8-97f90a6a8095", self.workdir))  # no transcript
        self.assertEqual(codex.purge_command(SESSION, self.workdir), ["codex", "delete", "--force", SESSION])
        for runner in (claude, codex):
            self.assertIsNone(runner.purge_command("../../projects", self.workdir))


def most_at_once(steps):
    """The peak of a running count, from its +1 and -1 steps in order."""
    peak = count = 0
    for step in steps:
        count += step
        peak = max(peak, count)
    return peak


class LauncherTest(unittest.TestCase):
    """launch.py run as a subprocess, with the fake CLIs playing whole runs from a plan (see
    persona_panel_fakes/panellist.py). PATH holds the fakes and nothing else, so no real CLI
    can be reached. Two personas on two model entries give P01-opus, P01-cx, P02-opus, P02-cx.
    The analyst and writer jobs are analyst-1, analyst-2 and writer."""

    CLAUDE = {"key": "opus", "runner": "claude", "model": "opus"}
    CODEX = {"key": "cx", "runner": "codex"}
    LIMIT_RESET = 1789377600  # when the recorded claude usage limit lifts
    python = sys.executable   # what runs the launcher, and so its watchdogs

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="persona-panel-launch-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(self.kill_leftovers)
        self.bin, self.fake, self.log = self.tmp / "bin", self.tmp / "fake", self.tmp / "cli.log"
        self.scripts = SCRIPTS  # a test that adds a runner works on its own copy of the skill
        self.bin.mkdir()
        fakes.install(self.bin)
        if shutil.which("ps"):  # the one system program the launcher may need
            os.symlink(shutil.which("ps"), self.bin / "ps")
        self.env = {"PATH": str(self.bin), "HOME": str(self.tmp / "home"), "FAKE_CLI_LOG": str(self.log),
                    "FAKE_PANEL": str(self.fake), "CLAUDE_CONFIG_DIR": str(self.tmp / "claude-home"),
                    "CODEX_HOME": str(self.tmp / "codex-home")}
        self.background = []

    def kill_leftovers(self):
        for proc in self.background:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
        for e in self.events("start") + self.events("spawn"):  # still alive, and ours only if its command
            try:                                                # names our folder
                os.kill(e["pid"], 0)
                r = subprocess.run(["ps", "-o", "command=", "-p", str(e["pid"])], capture_output=True, text=True)
                if str(self.tmp) in r.stdout:
                    os.kill(e["pid"], signal.SIGKILL)
            except OSError:
                pass

    def study(self, plan=None, personas=2, models=None, name="study", **settings):
        """Scaffold a study and set the plan the fakes follow. Becomes self.sd."""
        for cid in ("one", "two", "three"):
            d = self.tmp / "concepts" / cid
            d.mkdir(parents=True, exist_ok=True)
            (d / "index.html").write_text(f"<h1>{cid}</h1>")
        self.sd = self.tmp / name
        self.sd.mkdir()
        self.settings({
            "study": "t", "product": "Acme", "seed": 7, "models": models or [self.CLAUDE, self.CODEX],
            "concepts": [{"id": c, "path": f"../concepts/{c}"} for c in ("one", "two", "three")],
            "personas": [{"id": f"P{i:02d}", "name": f"Person {i}", "role": "Owner", "personality": "Sceptic"}
                         for i in range(1, personas + 1)], **settings})
        subprocess.run([sys.executable, str(self.scripts / "init_study.py"), str(self.sd)], check=True,
                       capture_output=True, text=True)
        shutil.rmtree(self.fake, True)
        (self.fake / "go").mkdir(parents=True)
        (self.fake / "plan.json").write_text(json.dumps(plan or {}))

    def settings(self, changed):
        """Merge keys into study.json, as a lead editing it between commands would."""
        path = self.sd / "study.json"
        path.write_text(json.dumps({**(json.loads(path.read_text()) if path.exists() else {}), **changed}))

    def command(self, *args):
        quick = [x for option, value in (("--poll", "0.02"), ("--grace", "0.3")) if option not in args
                 for x in (option, value)]
        return [self.python, str(self.scripts / "launch.py"), str(self.sd), *map(str, args), *quick]

    def launch(self, *args, **env):
        """Run a launcher command to its end."""
        return subprocess.run(self.command(*args), env={**self.env, **env}, capture_output=True, text=True, timeout=60)

    def launch_in_background(self, *args, ignoring_hang_up=False):
        """Start a launcher and leave it running. Returns the process and the file its output goes to.
        ignoring_hang_up starts it the way nohup does, with SIGHUP already ignored."""
        output = self.tmp / f"launcher-{len(self.background)}.out"
        with open(output, "w") as f:
            proc = subprocess.Popen(
                self.command(*args), env=self.env, stdout=f, stderr=subprocess.STDOUT,
                preexec_fn=(lambda: signal.signal(signal.SIGHUP, signal.SIG_IGN)) if ignoring_hang_up else None)
        self.background.append(proc)
        return proc, output

    def wait_for(self, condition, what):
        give_up = time.time() + 30
        while not condition():
            if time.time() > give_up:
                self.fail(f"Timed out waiting for {what}")
            time.sleep(0.01)

    def release(self, gate):
        (self.fake / "go" / gate).touch()

    def events(self, kind):
        lines = self.log.read_text().splitlines() if self.log.exists() else []
        return [e for e in map(json.loads, lines) if e.get("event") == kind]

    def starts(self, since=0):
        """The processes started for runs, in order, after the first `since` of them."""
        return self.events("start")[since:]

    def waiting(self):
        return {e["run"] for e in self.events("waiting")}

    def entries(self):
        return {e["run"]: e for e in json.loads(self.sd.joinpath("runs.json").read_text())}

    def status(self):
        return json.loads(self.launch("status", "--json").stdout)

    def processes(self):
        """What status says of the process of each run recorded as running: alive or gone."""
        return {r["run"]: r["process"] for r in self.status()["runs"] if r["process"]}

    def gone(self, pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        return False

    def states(self):
        """The state the launcher recorded for each run. One it never touched has none: pending."""
        return {run_id: e.get("state", "pending") for run_id, e in self.entries().items()}

    def sections(self, run_id):
        return self.sd.joinpath(self.entries()[run_id]["file"]).read_text().count("### Concept ")

    def tree(self):
        """Every file and folder of the study with its content, to show what a command changed."""
        return {str(p): p.read_bytes() if p.is_file() else None for p in sorted(self.sd.rglob("*"))}

    def plan(self):
        return json.loads(self.launch("plan", "--json").stdout)

    def test_plan_starts_nothing_and_labels_its_ceiling_by_whether_every_run_has_a_cap(self):
        synthesis = {"analyst": {"runner": "claude", "model": "sonnet"}, "writer": {"runner": "claude"}}
        self.study(limits={"run": {"minutes": 10}, "overrides": {"opus": {"budget_usd": 1.5}}}, synthesis=synthesis)
        before = self.tree()
        printed = self.launch("plan", ANTHROPIC_API_KEY="sk-never-shown")
        as_json = self.launch("plan", "--json", ANTHROPIC_API_KEY="sk-never-shown")
        self.assertEqual((printed.returncode, as_json.returncode), (0, 0), printed.stdout + printed.stderr)
        # The CLIs were asked whether they are installed and signed in, and nothing else happened.
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual({c.get("cli") for c in calls}, {"claude", "codex"})
        self.assertFalse([c for c in calls if c.get("model_call") or c.get("event")])
        self.assertEqual(self.tree(), before)
        plan = json.loads(as_json.stdout)
        limits = {r["run"]: r["limits"] for r in plan["runs"]}
        self.assertEqual((limits["P01-opus"], limits["P02-cx"]),  # the budget of cx is the default, shown all the same
                         ({"minutes": 10, "budget_usd": 1.5}, {"minutes": 10, "budget_usd": 2.0}))
        # No run has finished: 3 pages at the method's 20,000 tokens each, for 2 runs, and no dollar figure.
        opus = next(e for e in plan["estimate"]["entries"] if e["entry"] == "opus")
        self.assertEqual((opus["basis"], opus["tokens"], opus["cost_usd"]), ("method", 120000, None))
        ceiling = plan["ceiling"]  # two caps of $1.50 and the $5 pool: the runs on codex have no cap
        self.assertEqual((ceiling["label"], ceiling["usd"], ceiling["uncapped"]),
                         ("estimate", 8.0, ["P01-cx", "P02-cx"]))
        self.assertIn("Ceiling: $8.00, an estimate, not a guaranteed maximum", printed.stdout)
        # A variable that can change who is billed is named, and its value is never printed.
        self.assertIn("ANTHROPIC_API_KEY", plan["runners"][0]["billing_env_set"])
        self.assertIn("ANTHROPIC_API_KEY", printed.stdout)
        self.assertNotIn("sk-never-shown", printed.stdout + as_json.stdout)

        # Every run and job capped: a maximum, and never called one without what can take a run past its cap.
        self.study(name="capped", models=[self.CLAUDE], synthesis=synthesis)
        note = runners.get("claude").capabilities()["budget_cap_note"]
        capped, ceiling = self.launch("plan").stdout, self.plan()["ceiling"]
        self.assertIn("Ceiling: $9.00, a guaranteed maximum apart from the caveats below", capped)
        self.assertIn(f"Caveat: on claude, {note}.", capped)
        self.assertEqual((ceiling["label"], ceiling["caveats"][0]), ("guaranteed maximum", f"on claude, {note}"))

    def test_usage_record_counts_a_resumed_session_once_and_the_next_plan_estimates_from_it(self):
        self.study({"P01-opus": [["write:1"], ["write:all"]]})
        self.launch("pilot")
        self.launch("resume")  # P01-opus again, in the session that has already reported its usage once
        self.assertEqual(self.states(), {"P01-opus": "done", "P02-opus": "pending", "P01-cx": "done",
                                         "P02-cx": "pending"})
        record = self.sd.joinpath("analysis/usage.md").read_text()  # as the launcher left it
        figures = json.loads(self.launch("usage", "--json").stdout)
        reported = {r["run"]: (r["attempts"], r["input_tokens"], r["output_tokens"], r["cost_usd"])
                    for r in figures["runs"]}
        self.assertEqual(reported, {  # the totals of claude/ok and codex/ok, each once
            "P01-opus": (2, 2956, 597, 0.00046504), "P01-cx": (1, 82346, 297, None),
            "P02-opus": (0, None, None, None), "P02-cx": (0, None, None, None)})
        total = figures["total"]
        self.assertEqual((total["input_tokens"], total["output_tokens"], total["cost_usd"]), (85302, 894, 0.00046504))
        self.assertIn("| P01-opus | panellist | opus | done | 2 |", record)
        for cells in ("| 2,956 | 597 | 2,234 | $0.0005 |", "| 82,346 | 297 | 67,968 | not reported |",
                      "| 85,302 | 894 | 70,202 | $0.0005 (1 not reported) |"):
            self.assertIn(cells, record)
        # One finished run on each key and one to go: the estimate is what the finished one reported.
        estimate = {e["entry"]: e for e in self.plan()["estimate"]["entries"]}
        self.assertEqual({k: (e["basis"], e["measured_runs"], e["to_go"], e["tokens"], e["cost_usd"], e["cost"])
                          for k, e in estimate.items()},
                         {"opus": ("measured", 1, 1, 3553, 0.00046504, "measured"),
                          "cx": ("measured", 1, 1, 82643, None, "not reported")})
        self.assertGreater(estimate["cx"]["seconds"], 0)  # with no cost reported, the time is what is left
        self.assertIn("cost not reported", self.launch("plan").stdout)

    def test_full_materials_study_with_a_model_that_reads_no_images_is_refused_at_the_plan_step(self):
        skill = self.tmp / "skill"
        shutil.copytree(SCRIPTS.parent, skill, ignore=shutil.ignore_patterns("__pycache__"))
        (skill / "scripts/runners/textonly.py").write_text(
            "from . import claude\nfrom .claude import *  # noqa: F401,F403\n\n\n"
            "def capabilities():\n"
            "    return {**claude.capabilities(), 'images_by_path': False, 'provider': 'A local endpoint'}\n")
        self.scripts = skill / "scripts"
        self.study(models=[self.CLAUDE, {"key": "local", "runner": "textonly", "model": "small"}])
        planned = self.launch("plan")
        self.assertEqual(planned.returncode, 1, planned.stdout + planned.stderr)
        self.assertIn("local: textonly cannot open images", planned.stdout)
        started = self.launch("run")
        self.assertEqual(started.returncode, 1)
        self.assertIn("P01-local: textonly cannot open images", started.stdout)
        self.assertEqual(self.starts(), [])
        self.settings({"materials": "text"})  # the same model is welcome where there is nothing to look at
        self.assertEqual(self.launch("plan").returncode, 0)

    def test_persona_file_changed_by_another_run_is_flagged_and_a_lead_edit_is_not(self):
        self.study({"P02-opus": [["meddle:P01-opus", "write:all"]]}, personas=3, models=[self.CLAUDE],
                   runners={"claude": {"concurrency": 1}})  # one at a time: P01-opus has ended when P02-opus writes
        r = self.launch("run", "--runs", "P01-opus,P02-opus")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        own = self.sd / self.entries()["P02-opus"]["file"]
        own.write_text(own.read_text() + "A note from the lead, added while nothing was running.\n")
        self.assertEqual(self.launch("run", "--runs", "P03-opus").returncode, 0)
        checked = run("check_runs.py", self.sd, check=False)
        self.assertEqual(checked.returncode, 1)
        self.assertIn("| P01-opus | changed while P02-opus was running, not by its own run", checked.stdout)
        self.assertEqual(checked.stdout.count("changed while"), 1)

    def test_purge_sessions_deletes_only_with_yes_and_never_while_a_launcher_has_the_study(self):
        self.study({"P01-cx": [["write:1", "wait:hold"]]}, models=[self.CODEX])

        def deleted():
            lines = self.log.read_text().splitlines()
            return sorted(c["argv"][-1] for c in map(json.loads, lines) if c.get("argv", [""])[0] == "delete")

        launcher, _ = self.launch_in_background("run")
        self.wait_for(lambda: self.waiting() == {"P01-cx"} and self.entries()["P02-cx"].get("state") == "done",
                      "one run done and one under way")
        refused = self.launch("purge-sessions", "--yes")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("Another launcher has this study", refused.stderr)
        self.release("hold")
        launcher.wait(timeout=30)
        self.assertEqual(self.states(), {"P01-cx": "partial", "P02-cx": "done"})
        sessions = sorted(e["session"] for e in self.entries().values())

        listed = self.launch("purge-sessions")
        self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
        for session in sessions:
            self.assertIn(f"codex delete --force {session}", listed.stdout)
        self.assertIn("Nothing was deleted", listed.stdout)
        self.assertEqual((deleted(), [e.get("purged") for e in self.entries().values()]), ([], [None, None]))

        self.assertEqual(self.launch("purge-sessions", "--yes").returncode, 0)
        self.assertEqual(deleted(), sessions)
        self.assertEqual(sorted(s for e in self.entries().values() for s in e["purged"]), sessions)
        resumed = self.launch("resume")  # the partial run has sections and no session left to continue in
        self.assertIn("P01-cx: partial with sections written, but its session was purged", resumed.stdout)
        self.assertEqual(len(self.starts()), 2)

    def test_done_is_decided_by_the_persona_file_and_a_failed_run_is_retried_once(self):
        cases = {  # run: (what each of its processes does, the state it ends in, processes started)
            "P01-opus": ([["write:all", "end:error"]], "done", 1),       # complete file, exit code 1
            "P01-cx": ([["write:1"]], "partial", 1),                     # clean exit, two concepts short
            "P02-opus": ([["write:3"]], "partial", 1),                   # clean exit, no final sections
            "P02-cx": ([["end:error"]], "failed", 2),                    # nothing written, twice
            "P03-opus": ([["end:error"], ["write:all"]], "done", 2),     # nothing written, then everything
            "P03-cx": ([["write:2", "end:budget"]], "limited", 1),       # stopped by the harness's spend cap
        }
        self.study({k: v[0] for k, v in cases.items()}, personas=3)
        r = self.launch("run")
        self.assertEqual(self.states(), {k: v[1] for k, v in cases.items()}, r.stdout + r.stderr)
        started = [e["run"] for e in self.starts()]
        self.assertEqual({k: started.count(k) for k in cases}, {k: v[2] for k, v in cases.items()})
        self.assertFalse([e for e in self.starts() if e["resumed"]])
        self.assertEqual(r.returncode, 1)
        self.assertIn("Finished: done 2, partial 2, limited 1, failed 1.", r.stdout)
        # The launch prompt is the file in prompts/, verbatim, and a panellist starts in panel/.
        first = next(e for e in self.starts() if e["run"] == "P01-opus")
        self.assertEqual(first["stdin"], self.sd.joinpath("prompts/P01-opus.md").read_text())
        self.assertEqual(first["cwd"], str(self.sd / "panel"))

    def test_run_and_resume_start_only_the_states_they_own(self):
        self.study({
            "P01-opus": [["write:all"]],
            "P02-opus": [["write:1"], ["write:all"]],
            "P03-opus": [["end:error"], ["end:error"], ["write:all"]],
            "P01-cx": [["write:1", "end:budget"], ["write:all"]],
            "P02-cx": [["write:1", "end:usage_limit"], ["write:all"]],
        }, personas=3, runners={"codex": {"concurrency": 1}})
        self.launch("run")
        self.assertEqual(self.states(), {"P01-opus": "done", "P02-opus": "partial", "P03-opus": "failed",
                                         "P01-cx": "limited", "P02-cx": "blocked", "P03-cx": "pending"})
        first_session = {e["run"]: e["session"] for e in self.starts()}
        steps = [  # command, the processes it starts as (run, resumed), exit code, states it changes, what it says
            (["run"], [("P03-opus", False), ("P03-cx", False)], 1, {"P03-opus": "done", "P03-cx": "done"}, ""),
            (["resume"], [("P02-opus", True), ("P02-cx", True)], 1, {"P02-opus": "done", "P02-cx": "done"}, ""),
            (["run", "--runs", "P01-cx"], [], 1, {}, "P01-cx: limited, so run leaves it alone"),
            (["resume", "--runs", "P01-cx"], [], 1, {}, "resume --runs <ids> --extend"),
            (["resume", "--extend"], [], 1, {}, "--extend goes with resume --runs"),
            (["pilot", "--runs", "P03-cx"], [], 1, {}, "pilot takes no --runs"),
            (["resume", "--runs", "P01-cx", "--extend"], [("P01-cx", True)], 0, {"P01-cx": "done"}, "P01-cx: extended"),
        ]
        states = self.states()
        for args, expected, code, changes, says in steps:
            with self.subTest(" ".join(args)):
                before = len(self.starts())
                r = self.launch(*args)
                started = self.starts(before)
                self.assertEqual(sorted((e["run"], e["resumed"]) for e in started), sorted(expected), r.stdout)
                self.assertEqual(r.returncode, code, r.stdout + r.stderr)
                self.assertIn(says, r.stdout + r.stderr)
                states.update(changes)
                self.assertEqual(self.states(), states)
                for e in started:
                    if e["resumed"]:  # in its original session, told what it has already written
                        self.assertEqual(e["session"], first_session[e["run"]])
                        self.assertIn("Already written: ", e["stdin"])
        status = self.status()
        self.assertEqual((status["extended"], status["ceiling_holds"]), (["P01-cx"], False))
        self.assertIn("ceiling no longer holds", self.launch("status").stdout)

    def test_usage_limit_blocks_one_runner_and_resume_finishes_its_run(self):
        self.study({
            "P01-opus": [["write:1", "end:usage_limit"], ["write:all"]],
            "P01-cx": [["wait:limit-seen", "write:all"]],
        }, runners={"claude": {"concurrency": 1}, "codex": {"concurrency": 1}})
        launcher, output = self.launch_in_background("run")
        self.wait_for(lambda: self.entries()["P01-opus"].get("state") == "blocked", "the usage limit")
        self.release("limit-seen")
        self.assertEqual(launcher.wait(timeout=30), 1)
        # The limited runner started nothing more; the other started its second run after the limit.
        self.assertEqual(sorted(e["run"] for e in self.starts()), ["P01-cx", "P01-opus", "P02-cx"])
        logged = [(e.get("event"), e.get("run")) for e in map(json.loads, self.log.read_text().splitlines())]
        self.assertLess(logged.index(("end", "P01-opus")), logged.index(("start", "P02-cx")))
        self.assertEqual(self.states(), {"P01-opus": "blocked", "P02-opus": "pending", "P01-cx": "done",
                                         "P02-cx": "done"})
        # The harness's own words say why, and the launcher's do not call every refusal a usage limit.
        lifts, said = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.LIMIT_RESET)), output.read_text()
        self.assertIn("P01-opus: blocked: the harness is turning requests away (You've hit your session limit", said)
        self.assertIn(f"claude: the harness is turning requests away, and said its limit lifts at {lifts}. "
                      "No more launches on this runner for now", said)
        blocked = next(r for r in self.status()["runs"] if r["run"] == "P01-opus")
        self.assertEqual(blocked["reset_at"], self.LIMIT_RESET)
        self.launch("resume")
        resumed = self.starts(3)
        self.assertEqual([(e["run"], e["resumed"]) for e in resumed], [("P01-opus", True)])
        self.assertEqual(self.states()["P01-opus"], "done")

    def test_runs_on_a_runner_stay_within_its_concurrency(self):
        hold_until_two_run = [["starts:2", "write:all"]]  # so two really are alive at the same time
        self.study({f"P0{p}-opus{r}": hold_until_two_run for p in (1, 2) for r in ("", "-r2")},
                   models=[self.CLAUDE], replicates=2, runners={"claude": {"concurrency": 2}})
        r = self.launch("run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.starts()), 4)
        lines = self.log.read_text().splitlines()
        seen_by_the_clis = [{"start": 1, "end": -1}.get(json.loads(line).get("event"), 0) for line in lines]
        told_by_the_launcher = [1 if ": running (" in line else -1 if line.endswith(": done") else 0
                                for line in r.stdout.splitlines()]
        self.assertEqual((most_at_once(seen_by_the_clis), most_at_once(told_by_the_launcher)), (2, 2))

    def test_run_over_its_time_limit_is_stopped_and_keeps_what_it_wrote(self):
        # One section, then a process that hangs. It answers SIGTERM by writing one more section
        # at once, and does not exit. Nothing here is timed but the two waits under test, and both
        # are far longer than what has to fit in them: the limit outlasts the start of the process
        # and its first write, the grace outlasts the one write made on SIGTERM.
        limit, grace = 3.0, 1.5
        self.study({"P01-opus": [["stubborn", "write:1", "hang"]]}, personas=1, models=[self.CLAUDE],
                   limits={"run": {"minutes": limit / 60}})
        r = self.launch("run", "--grace", grace)
        self.assertEqual(r.returncode, 1)
        self.assertIn("P01-opus: limited: time limit reached", r.stdout)
        [limited] = self.status()["runs"]
        self.assertEqual((limited["state"], limited["attempts"], self.sections("P01-opus")), ("limited", 1, 2))
        self.assertGreaterEqual(limited["seconds_used"], limit)
        self.assertEqual([e["run"] for e in self.events("term")], ["P01-opus"])
        [started] = self.starts()
        self.assertEqual(limited["session"], started["session"])
        self.assertTrue(self.gone(started["pid"]))  # it never left by itself: it was killed
        self.assertEqual(self.entries()["P01-opus"]["attempts"][0]["exit_code"], -signal.SIGKILL)
        closed = [json.loads(line) for line in self.log.read_text().splitlines() if '"agent-browser"' in line]
        self.assertEqual([c["argv"] for c in closed if c.get("cli") == "agent-browser"],
                         [["--session", "P01-opus", "close"]])

    def test_limits_add_up_across_a_runs_attempts(self):
        self.study({"P01-opus": [["write:1"], ["write:1"], ["write:all"]], "P01-cx": [["write:1"], ["write:all"]]},
                   personas=1, limits={"run": {"budget_usd": 1}})
        self.launch("run")
        self.launch("resume", "--runs", "P01-opus")
        caps = [e["argv"][e["argv"].index("--max-budget-usd") + 1] for e in self.starts() if e["cli"] == "claude"]
        self.assertEqual(caps, ["1", "0.999535"])  # the cap, then the cap less the $0.00046504 already reported
        self.assertEqual(self.states(), {"P01-opus": "partial", "P01-cx": "partial"})
        # With less allowed than is already used, a run has nothing left: it is limited, not started.
        self.settings({"limits": {"overrides": {"opus": {"budget_usd": 0.0004}, "cx": {"minutes": 0.000001}}}})
        r = self.launch("resume")
        self.assertIn("P01-cx: limited without starting", r.stdout)
        after = {r["run"]: r for r in self.status()["runs"]}
        self.assertEqual({k: (r["state"], r["attempts"]) for k, r in after.items()},
                         {"P01-opus": ("limited", 2), "P01-cx": ("limited", 1)})
        self.assertIn("$0.0004", after["P01-opus"]["reason"])
        self.assertIn("min", after["P01-cx"]["reason"])

    def test_killed_launcher_loses_no_work_and_starts_no_duplicate(self):
        limit = 1.0
        self.study({
            "P01-opus": [["write:1", "wait:die", "exit:1"]],   # prints as it starts, ends quietly and unwatched
            "P02-opus": [["wait:finish", "write:all"]],        # still alive when the next launcher starts
            "P01-cx": [["hang"]], "P02-cx": [["hang"]],        # never end by themselves: only their limit stops them
        }, limits={"overrides": {"cx": {"minutes": limit / 60}}})
        # A launcher that looks at its runs every 30 seconds starts them and sees nothing after:
        # whatever happens to them from here on happens without it.
        first, _ = self.launch_in_background("run", "--poll", 30)
        self.wait_for(lambda: len(self.starts()) == 4 and self.waiting() == {"P01-opus", "P02-opus"},
                      "four runs to be under way")
        first.kill()
        first.wait()
        # runs.json as a launcher killed between starting P02-opus and noting its pid leaves it:
        # the attempt is on record without one, and only the attempt's own pid file says where it is.
        as_left = self.entries()
        as_left["P02-opus"].update(pid=None, pid_identity=None)
        self.sd.joinpath("runs.json").write_text(json.dumps(list(as_left.values())))
        self.wait_for(lambda: self.processes() == {"P01-opus": "alive", "P02-opus": "alive", "P01-cx": "gone",
                                                   "P02-cx": "gone"}, "the time limit to end two runs unwatched")
        went_quiet_for = time.time() - as_left["P01-opus"]["attempts"][0]["started"]
        self.release("die")
        self.wait_for(lambda: self.processes()["P01-opus"] == "gone", "P01-opus to exit")

        second, output = self.launch_in_background("run")
        self.wait_for(lambda: "P02-opus: running, adopted" in output.read_text(), "the live run to be adopted")
        self.release("finish")
        self.assertEqual(second.wait(timeout=30), 1)
        said = output.read_text()
        self.assertIn("Cleared a stale lock", said)
        self.assertEqual(self.states(), {"P01-opus": "partial", "P02-opus": "done", "P01-cx": "limited",
                                         "P02-cx": "limited"}, said)
        self.assertEqual(sorted(e["run"] for e in self.starts()), ["P01-cx", "P01-opus", "P02-cx", "P02-opus"])
        self.assertEqual(self.sections("P01-opus"), 1)
        # Time used is how long each process ran, whenever it last printed and whoever was watching.
        # Times are recorded to the millisecond, hence the hundredth of a second allowed for.
        after = self.entries()
        self.assertGreaterEqual(after["P01-opus"]["seconds_used"], went_quiet_for - 0.01)
        for run_id in ("P01-cx", "P02-cx"):
            self.assertGreaterEqual(after[run_id]["seconds_used"], limit)
            self.assertIn("time limit reached", after[run_id]["reason"])

    def test_killed_watchdog_has_its_live_cli_killed_and_what_a_cli_that_has_gone_left_is_only_reported(self):
        self.study({"P01-opus": [["write:1", "wait:never"]],          # its CLI is alive when the next launcher looks
                    "P02-opus": [["spawn", "wait:die", "exit:0"]]},   # its CLI has ended, and left a process behind
                   models=[self.CLAUDE])
        first, _ = self.launch_in_background("run", "--poll", 30)
        self.wait_for(lambda: self.waiting() == {"P01-opus", "P02-opus"}, "both runs to be under way")
        first.kill()
        first.wait()
        for pid_file in self.sd.glob("logs/*.pid"):  # the watchdog is the first process recorded in it
            os.kill(int(pid_file.read_text().split()[0]), signal.SIGKILL)
        self.release("die")
        self.wait_for(lambda: self.processes()["P02-opus"] == "gone", "P02-opus to exit")
        unwatched_for = time.time() - self.entries()["P01-opus"]["attempts"][0]["started"]
        cli = {e["run"]: e["pid"] for e in self.starts()}
        [left] = [e["pid"] for e in self.events("spawn")]

        r = self.launch("stop")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # The CLI that is still there is its group for certain, and is killed. A group that has
        # lost its CLI cannot be proved to be the run's: it is named and not signalled.
        # kill_leftovers() ends that process when the test is over.
        self.assertEqual((self.gone(cli["P01-opus"]), self.gone(left)), (True, False))
        self.assertIn(f"P02-opus: its watchdog was killed, and process group {cli['P02-opus']} still holds pid {left}, "
                      "which may be left over from this run. The launcher cannot prove that, so it has left the group "
                      f"untouched: check with ps -o pid,pgid,command -p {left} and stop what is the run's.", r.stdout)
        self.assertNotIn("P01-opus: its watchdog was killed, and", r.stdout)
        after = self.entries()
        self.assertEqual({k: e["state"] for k, e in after.items()}, {"P01-opus": "partial", "P02-opus": "failed"})
        for e in after.values():
            self.assertIn("its watchdog was killed, so how it ended is not on record", e["reason"])
        self.assertGreaterEqual(after["P01-opus"]["seconds_used"], unwatched_for - 0.01)
        self.assertEqual({row["run"]: row["leftover"] for row in self.status()["runs"]},
                         {"P01-opus": None, "P02-opus": {"group": cli["P02-opus"], "pids": [left]}})
        self.assertIn(f"process group {cli['P02-opus']} still holds pid {left}", self.launch("status").stdout)

    def test_resume_of_a_session_that_is_gone_restarts_only_a_run_that_wrote_nothing(self):
        self.study({"P01-opus": [["write:1"]], "P02-opus": [["end:usage_limit"], ["write:all"]],
                    "P03-opus": [["write:1"], ["write:all"]]},
                   personas=3, models=[self.CLAUDE], runners={"claude": {"concurrency": 1}})
        self.launch("run", "--runs", "P01-opus,P03-opus")
        self.launch("run", "--runs", "P02-opus")
        self.assertEqual(self.states(), {"P01-opus": "partial", "P02-opus": "blocked", "P03-opus": "partial"})
        for e in self.starts():  # the harness loses the sessions of the first two runs
            if e["run"] != "P03-opus":
                self.fake.joinpath("sessions", f"{e['session']}.json").unlink()
        r = self.launch("resume")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("P01-opus: partial with sections written, but its session no longer exists, so it cannot be "
                      "continued", r.stdout)
        self.assertIn("P02-opus: its session no longer exists and it has written nothing, so it is started afresh",
                      r.stdout)
        self.assertNotIn("could not be started", r.stdout)
        # The run that wrote nothing got a new session, and the runner went on to its next run.
        self.assertEqual([(e["run"], e["resumed"]) for e in self.starts(3)], [("P02-opus", False), ("P03-opus", True)])
        self.assertEqual(self.states(), {"P01-opus": "partial", "P02-opus": "done", "P03-opus": "done"})
        self.assertEqual({k: len(e["attempts"]) for k, e in self.entries().items()},
                         {"P01-opus": 1, "P02-opus": 2, "P03-opus": 2})
        again = self.launch("resume")  # known now: no process is started to find it out
        self.assertIn("P01-opus: partial with sections written, but its session no longer exists", again.stdout)
        self.assertEqual(len(self.starts()), 5)

    def test_one_launcher_per_study_and_stop_leaves_its_runs_resumable(self):
        self.study({"P01-opus": [["write:1", "wait:never"], ["write:all"]], "P02-opus": [["spawn", "wait:never"]]},
                   models=[self.CLAUDE])
        first, _ = self.launch_in_background("run")
        self.wait_for(lambda: self.waiting() == {"P01-opus", "P02-opus"}, "both runs to be under way")
        second = self.launch("run")
        self.assertEqual(second.returncode, 1)
        self.assertIn(f"Another launcher has this study (pid {first.pid}", second.stderr)
        self.assertEqual(len(self.starts()), 2)

        self.assertEqual(self.launch("stop").returncode, 0)
        self.assertEqual(first.wait(timeout=30), 1)
        # Nothing is left behind: not the CLIs, and not the process one of them started, which
        # ignores the signal that ended its parent.
        self.assertEqual([self.gone(e["pid"]) for e in self.starts() + self.events("spawn")], [True, True, True])
        self.assertEqual(self.states(), {"P01-opus": "partial", "P02-opus": "pending"})

        def unreported():
            return {r["run"]: r["unreported_attempts"] for r in self.status()["runs"]}

        # A stopped process reported nothing: what it used is unknown, and is not shown as nothing.
        self.assertEqual(unreported(), {"P01-opus": [1], "P02-opus": [1]})
        self.assertIn("usage of attempt 1 not reported (process was stopped)", self.launch("status").stdout)
        self.assertRegex(self.sd.joinpath("analysis/usage.md").read_text(),
                         r"\| P01-opus \| panellist \| opus \| partial \| 1 \| [\d.]+ s "
                         r"\| not reported \(process was stopped\) \|")
        self.assertIn("Not reported so far: P01-opus attempt 1, P02-opus attempt 1", self.launch("plan").stdout)
        session = next(e["session"] for e in self.starts() if e["run"] == "P01-opus")
        self.launch("resume")
        [resumed] = self.starts(2)
        self.assertEqual((resumed["run"], resumed["resumed"], resumed["session"]), ("P01-opus", True, session))
        self.assertEqual(self.states(), {"P01-opus": "done", "P02-opus": "pending"})
        self.assertEqual(unreported(), {"P01-opus": [], "P02-opus": [1]})  # the session has reported its total

    def test_hang_up_stops_the_runs_unless_the_launcher_was_started_ignoring_it(self):
        self.study({"P01-opus": [["wait:finish", "write:all"]]}, personas=1, models=[self.CLAUDE])
        heeding, _ = self.launch_in_background("run")
        self.wait_for(lambda: self.waiting() == {"P01-opus"}, "the run to be under way")
        heeding.send_signal(signal.SIGHUP)
        self.assertEqual(heeding.wait(timeout=30), 1)  # a clean stop, not a launcher killed by the signal
        self.assertEqual((self.states(), self.sd.joinpath(".launch.lock").exists()), ({"P01-opus": "pending"}, False))

        under_nohup, _ = self.launch_in_background("run", ignoring_hang_up=True)
        self.wait_for(lambda: len(self.events("waiting")) == 2, "the run to be under way again")
        under_nohup.send_signal(signal.SIGHUP)
        time.sleep(0.5)  # 25 polls: a launcher that heeded the signal has stopped its run by now
        self.release("finish")
        self.assertEqual(under_nohup.wait(timeout=30), 0)
        self.assertEqual(self.states(), {"P01-opus": "done"})

    def test_run_refuses_to_start_a_panel_it_cannot_run_whole(self):
        self.study(personas=1)
        signed_out = self.launch("run", FAKE_CODEX="signed_out")
        self.assertEqual(signed_out.returncode, 1)
        self.assertIn("codex: cannot be used: Not logged in", signed_out.stdout)
        self.assertEqual((self.starts(), self.sd.joinpath("logs").exists()), ([], False))
        allowed = self.launch("run", "--allow-missing", FAKE_CODEX="signed_out")
        self.assertEqual(allowed.returncode, 1)
        self.assertEqual([e["run"] for e in self.starts()], ["P01-opus"])
        self.assertEqual(self.states(), {"P01-opus": "done", "P01-cx": "pending"})
        self.assertNotIn("state", self.entries()["P01-cx"])  # left untouched

        self.study(personas=1, name="bad-effort", models=[self.CLAUDE, {**self.CODEX, "effort": "ultra"}])
        refused = self.launch("run")
        self.assertEqual(refused.returncode, 1)
        self.assertIn('P01-cx: codex has no effort "ultra"', refused.stdout)
        self.assertEqual(self.starts(1), [])

    def test_process_that_cannot_be_started_is_reported_and_nothing_is_marked_failed(self):
        cases = [  # what the sandbox does, the runner it hits, what the launcher says about the first run
            ({"FAKE_CODEX": "sandboxed"}, "cx",  # passes the check, then every run dies before printing a line
             "P01-cx: could not be started. Its CLI exited with code 1 before printing anything: codex exec --json "
             "--skip-git-repo-check ... (Error: failed to initialize in-process app-server client: Read-only file "
             "system (os error 30)). Nothing was marked as failed. Run launch.py from a terminal"),
            ({"FAKE_CLAUDE": "lockout"}, "opus",  # passes the check, then cannot be executed
             "P01-opus: could not be started. The system refused this command: claude -p"),
        ]
        for env, refused, says in cases:
            with self.subTest(**env):
                other = "opus" if refused == "cx" else "cx"
                self.study(name=f"refused-{refused}",
                           runners={"claude": {"concurrency": 1}, "codex": {"concurrency": 1}})
                self.log.unlink(missing_ok=True)
                r = self.launch("run", **env)
                self.assertEqual(r.returncode, 1)
                self.assertIn(says, r.stdout)
                self.assertEqual(self.states(), {f"P01-{refused}": "pending", f"P02-{refused}": "pending",
                                                 f"P01-{other}": "done", f"P02-{other}": "done"}, r.stdout)
                self.assertNotIn("attempts", self.entries()[f"P01-{refused}"])
                # One refusal is enough: nothing more was started on that runner, and the other carried on.
                self.assertEqual(r.stdout.count("could not be started"), 2)  # the run, then its runner
                self.assertEqual(sorted(e["run"] for e in self.starts()), [f"P01-{other}", f"P02-{other}"])

    def test_study_directory_that_cannot_be_written_is_refused_in_a_sentence(self):
        if os.geteuid() == 0:
            self.skipTest("root can write to a read-only directory")
        self.study()
        for folder in (self.sd, self.sd / "analysis"):  # what a sandboxed shell tool sees
            folder.chmod(0o555)
            self.addCleanup(folder.chmod, 0o755)
        r = self.launch("run")
        self.assertEqual((r.returncode, "The system refused to write" in r.stderr, "Traceback" in r.stderr),
                         (1, True, False), r.stderr)
        self.assertIn(".launch.lock", r.stderr)
        self.assertEqual(self.starts(), [])
        used = self.launch("usage")  # still reports, and says the file was not written
        self.assertEqual((used.returncode, "## By run" in used.stdout, "could not be written" in used.stderr),
                         (0, True, True), used.stderr)

    def test_analysts_then_the_writer_run_on_their_own_models_within_a_share_of_the_pool(self):
        self.study({"analyst-2": [["end:usage_limit"], ["write"]]}, personas=3, limits={"synthesis": {"budget_usd": 5}},
                   synthesis={"analysts": 2, "analyst": {"runner": "claude", "model": "sonnet"},
                              "writer": {"runner": "claude", "model": "fable", "effort": "high"}})
        self.launch("run")
        panel = len(self.starts())
        steps = [  # command, the job processes it starts as (job, resumed), exit code, what it says
            (["run", "--role", "writer"], [], 1, "analyst-1 is pending, analyst-2 is pending"),
            (["run", "--role", "analyst"], [("analyst-1", False), ("analyst-2", False)], 1, "analyst-2: blocked"),
            (["run", "--role", "writer"], [], 1, "analyst-1 is done, analyst-2 is blocked"),
            (["resume", "--role", "analyst"], [("analyst-2", True)], 0, "run --role writer"),
            (["run", "--role", "writer"], [("writer", False)], 0, "writer: done"),
        ]
        for args, expected, code, says in steps:
            with self.subTest(" ".join(args)):
                before = len(self.starts())
                r = self.launch(*args)
                self.assertEqual(sorted((e["run"], e["resumed"]) for e in self.starts(before)), expected,
                                 r.stdout + r.stderr)
                self.assertEqual(r.returncode, code, r.stdout + r.stderr)
                self.assertIn(says, r.stdout + r.stderr)
                if args[-1] == "writer" and code:  # a writer that is refused is not planned either
                    self.assertNotIn("writer", self.entries())
        jobs = {(e["run"], e["resumed"]): e for e in self.starts(panel)}
        launched = {job: e for (job, resumed), e in jobs.items() if not resumed}

        def option(e, name):
            return e["argv"][e["argv"].index(name) + 1]

        self.assertEqual({k: option(e, "--model") for k, e in jobs.items()}, {
            ("analyst-1", False): "sonnet", ("analyst-2", False): "sonnet", ("analyst-2", True): "sonnet",
            ("writer", False): "fable"})
        self.assertEqual(option(launched["writer"], "--effort"), "high")
        self.assertEqual({option(e, "--max-budget-usd") for e in jobs.values()}, {"1.666666"})  # $5 between three
        self.assertEqual({e["cwd"] for e in jobs.values()}, {str(self.sd)})
        self.assertEqual(jobs["analyst-2", True]["session"], launched["analyst-2"]["session"])
        # Each brief is the prompt, verbatim and with nothing left to fill in. The analysts split
        # the personas in halves, each with every model of its personas.
        owned = {}
        for job, e in launched.items():
            self.assertEqual(e["stdin"], self.sd.joinpath(f"prompts/{job}.md").read_text())
            self.assertNotRegex(e["stdin"], r"<[A-Z][A-Z0-9_]*>")
            owned[job] = sorted(set(re.findall(r"/personas/(P\d+)-[^`]*--(\w+)\.md`", e["stdin"])))
        self.assertEqual(owned, {"analyst-1": [("P01", "cx"), ("P01", "opus"), ("P02", "cx"), ("P02", "opus")],
                                 "analyst-2": [("P03", "cx"), ("P03", "opus")], "writer": []})
        for output in ("qual-1.md", "qual-2.md", "SYNTHESIS.md"):
            self.assertIn("by the job itself", self.sd.joinpath("analysis", output).read_text())
        # Jobs have their own group in the launcher's status, and are no part of the panel's runs.
        status = self.status()
        self.assertEqual([(j["run"], j["state"], j["file"]) for j in status["jobs"]], [
            ("analyst-1", "done", "analysis/qual-1.md"), ("analyst-2", "done", "analysis/qual-2.md"),
            ("writer", "done", "analysis/SYNTHESIS.md")])
        self.assertEqual(len(status["runs"]), 6)
        tracked = run("runs.py", self.sd, "status").stdout
        self.assertEqual(("done: 6" in tracked, "analyst" in tracked or "writer" in tracked), (True, False))
        self.assertIn("18 score rows from 6 runs", run("extract_scores.py", self.sd).stdout)

    def test_analysts_wait_for_the_panel_unless_allowed_and_are_told_which_runs_did_not_finish(self):
        self.study({"P01-cx": [["write:1"]], "P02-opus": [["end:usage_limit"]]},
                   synthesis={"analyst": {"runner": "codex", "model": "gpt-test"}})
        self.launch("run")
        self.assertEqual(self.states(), {"P01-opus": "done", "P02-opus": "blocked", "P01-cx": "partial",
                                         "P02-cx": "done"})
        panel = len(self.starts())
        refused = self.launch("run", "--role", "analyst")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("1 panellist run of 4 has not finished (P02-opus blocked)", refused.stderr)
        self.assertEqual((self.starts(panel), "analyst-1" in self.entries(),
                          self.sd.joinpath("prompts/analyst-1.md").exists()), ([], False, False))
        allowed = self.launch("run", "--role", "analyst", "--allow-incomplete")
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
        [started] = self.starts(panel)
        self.assertEqual((started["run"], started["cli"], started["argv"][started["argv"].index("-m") + 1]),
                         ("analyst-1", "codex", "gpt-test"))
        files = {k: Path(e["file"]).name for k, e in self.entries().items() if e["role"] == "panellist"}
        self.assertIn(f"- `{files['P01-cx']}` (P01-cx): partial, 1 of 3 concepts written", started["stdin"])
        self.assertIn(f"- `{files['P02-opus']}` (P02-opus): blocked, nothing written", started["stdin"])
        self.assertEqual([k for k in files if f"({k})" in started["stdin"]], ["P01-cx", "P02-opus"])
        self.assertTrue(self.sd.joinpath("analysis/qual-1.md").read_text().strip())  # one analyst writes qual-1 too

    def test_job_that_could_not_write_its_file_gets_it_from_its_reply(self):
        self.study({"writer": [["reply"]]}, personas=1, synthesis={"writer": {"runner": "codex"}})
        self.sd.joinpath("analysis/qual-1.md").write_text("# Findings\n")  # the analysis, done by hand
        r = self.launch("run", "--role", "writer")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([e["run"] for e in self.starts()], ["writer"])
        self.assertEqual(self.sd.joinpath("analysis/SYNTHESIS.md").read_text(), "# Findings\n\n- From the reply.\n")
        self.assertIn("I could not write the file", self.sd.joinpath("analysis/writer-reply.md").read_text())
        [job] = self.status()["jobs"]
        self.assertEqual((job["state"], "from its reply" in job["note"]), ("done", True))

    def test_pilot_runs_the_first_persona_on_each_model_entry(self):
        self.study()
        r = self.launch("pilot")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(e["run"] for e in self.starts()), ["P01-cx", "P01-opus"])
        self.assertEqual(self.states(), {"P01-opus": "done", "P02-opus": "pending", "P01-cx": "done",
                                         "P02-cx": "pending"})


class LauncherWithoutWaitidTest(LauncherTest):
    """What a watchdog does to its CLI's processes, under a Python that has no os.waitid, as on
    macOS before Python 3.13: run_watchdog.py then learns that its CLI has ended another way.
    The Python is a virtual environment whose sitecustomize takes the function away."""

    WATCHDOG = {"test_run_over_its_time_limit_is_stopped_and_keeps_what_it_wrote",
                "test_one_launcher_per_study_and_stop_leaves_its_runs_resumable",
                "test_killed_launcher_loses_no_work_and_starts_no_duplicate",
                "test_done_is_decided_by_the_persona_file_and_a_failed_run_is_retried_once"}

    @classmethod
    def setUpClass(cls):
        home = Path(tempfile.mkdtemp(prefix="persona-panel-python-"))
        cls.addClassCleanup(shutil.rmtree, home, True)
        venv.create(home, symlinks=True)
        next(home.glob("lib/python*/site-packages")).joinpath("sitecustomize.py").write_text(
            "import os\nvars(os).pop('waitid', None)\n")
        cls.python = str(home / "bin" / "python")
        has = subprocess.run([cls.python, "-I", "-c", "import os; print(hasattr(os, 'waitid'))"],  # as a watchdog is
                             capture_output=True, text=True)
        assert has.stdout.strip() == "False", f"os.waitid is still there: {has.stdout}{has.stderr}"


for _name in set(vars(LauncherTest)) - LauncherWithoutWaitidTest.WATCHDOG:
    if _name.startswith("test_"):
        setattr(LauncherWithoutWaitidTest, _name, None)  # the other tests would say nothing new here


if __name__ == "__main__":
    unittest.main()
