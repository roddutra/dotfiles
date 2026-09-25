#!/usr/bin/env python3

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "agents/.agents/skills/persona-panel/scripts"
FACTORS = 11


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
        self.sd = base / "round-1"
        self.sd.mkdir()
        cfg = {
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
        (self.sd / "study.json").write_text(json.dumps(cfg))
        run("init_study.py", self.sd)
        self.key = self.sd.joinpath("key.md").read_text()
        self.runs = json.loads(self.sd.joinpath("runs.json").read_text())

    def tearDown(self):
        self.tmp.cleanup()

    def labels_for(self, cid):
        for line in self.key.splitlines():
            if f"| {cid} |" in line:
                return line.split("|")[1].strip()
        raise AssertionError(cid)

    def fill(self, run_entry, scores_by_cid, ranking_cids, extra=""):
        f = self.sd / run_entry["file"]
        body = f.read_text()
        for cid, s in scores_by_cid.items():
            body += filled_section(self.labels_for(cid), s)
        body += extra + finals([self.labels_for(c) for c in ranking_cids])
        f.write_text(body)

    def fill_all(self):
        for r in self.runs:
            self.fill(r, {"01-plain": [8] * FACTORS, "02-story": [6] * 10 + [5], "03-console": [7] * FACTORS},
                      ["01-plain", "03-console", "02-story"])

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
        quant = json.loads(self.sd.joinpath("analysis/quant.json").read_text())
        top = quant["leaderboard"][0]
        self.assertEqual(top["concept"], self.labels_for("01-plain"))
        self.assertEqual(top["first"], 4)
        self.assertEqual(top["borda"], 12)
        self.assertEqual(quant["leaderboard"][-1]["concept"], self.labels_for("02-story"))
        self.assertEqual(len(quant["fit"]["personas"]), 2)
        seg = run("analyze.py", self.sd, "--segment", "owner").stdout
        self.assertIn("2 runs", seg)

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


if __name__ == "__main__":
    unittest.main()
