#!/usr/bin/env python3

import csv
import json
import os
import re
import secrets
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import venv
import zlib
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "agents/.agents/skills/persona-panel/scripts"
FACTORS = 11

sys.path[:0] = [str(SCRIPTS), str(Path(__file__).resolve().parent)]
import persona_panel_fakes as fakes  # noqa: E402
import interview  # noqa: E402
import run_watchdog  # noqa: E402
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


def png(width, height):
    """A white PNG image of that size."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def pdf(pages):
    """A PDF with one page for each line of text given."""
    font = "<< /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >>"
    objects = ["<< /Type /Catalog /Pages 2 0 R >>",
               f"<< /Type /Pages /Kids [{' '.join(f'{3 + 2 * i} 0 R' for i in range(len(pages)))}] "
               f"/Count {len(pages)} >>"]
    for i, text in enumerate(pages):
        stream = f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET"
        objects += [f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
                    f"/Resources {font} >>", f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"]
    out, offsets = "%PDF-1.4\n", []
    for n, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{body}\nendobj\n"
    table = "".join(f"{offset:010d} 00000 n \n" for offset in offsets)
    return (f"{out}xref\n0 {len(objects) + 1}\n0000000000 65535 f \n{table}trailer\n<< /Size {len(objects) + 1} "
            f"/Root 1 0 R >>\nstartxref\n{len(out)}\n%%EOF\n").encode("latin-1")


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
        """A study directory holding the base config with overrides, not yet scaffolded. A key
        overridden with None is left out."""
        sd = Path(self.tmp.name) / name
        sd.mkdir()
        (sd / "study.json").write_text(json.dumps({k: v for k, v in {**self.cfg, **overrides}.items()
                                                   if v is not None}))
        return sd

    def interview(self, guide=None, **more):
        """The overrides that make the base config an interview study, which has a guide and no concepts:
        for self.study(). guide changes keys of the guide."""
        held = {"about": "how a cafe is run from day to day", "interviewer": {"model": "opus"},
                "goals": [{"id": "G1", "learn": "What takes most of the week, and what was done about it"}],
                "topics": [{"id": "T1", "area": "the working week", "goals": ["G1"],
                            "opener": "What took most of your time at work last week?"}], **(guide or {})}
        return {"type": "interview", "runner": "claude", "product": None, "concepts": None,
                "find_the_answer": None, "interview": held, **more}

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
        self.assertNotIn("\u2014", instructions)
        self.assertFalse((panel / "key.md").exists())
        self.assertEqual(len(self.runs), 4)
        orders = {}
        for f in (panel / "personas").glob("*.md"):
            line = next(l for l in f.read_text().splitlines() if l.startswith("| Review order"))
            orders.setdefault(f.name.split("-")[0], set()).add(line)
        self.assertTrue(all(len(v) == 1 for v in orders.values()), orders)
        # The study's lock file is there from the scaffold on, and a new scaffold leaves it where it is: it is
        # what a shell that cannot write the study locks to keep a launcher away while it reads (archive.py).
        lock_file = self.sd / ".launch.lock"
        self.assertTrue(lock_file.is_file())
        first_key = self.key
        run("init_study.py", self.sd, "--force")
        self.assertEqual((first_key, True), (self.sd.joinpath("key.md").read_text(), lock_file.is_file()))
        self.assertIn("Read nothing outside", self.sd.joinpath(self.runs[0]["prompt"]).read_text())
        # Where there is no lock file and none can be made, the scaffold says so and fails, with the study
        # scaffolded. What is at the name is left there, and --force scaffolds again once the lead has removed it.
        outside = Path(self.tmp.name) / "elsewhere"
        outside.write_text("not the study's")
        cases = {"a folder": (Path.mkdir, Path.rmdir, "The system refused to write {at} (Is a directory).",
                              "Put that right, then"),
                 "a symbolic link": (lambda at: at.symlink_to(outside), Path.unlink,
                                     "{at} is a symbolic link, so it is no lock a launcher made.",
                                     "Look at what is there, delete it, then")}
        for i, (name, (put, remove, why, first)) in enumerate(cases.items()):
            with self.subTest(name):
                sd = self.study(f"no-lock-{i}").resolve()
                at = sd / ".launch.lock"
                put(at)
                r = run("init_study.py", sd, check=False)
                self.assertEqual((r.returncode, "Traceback" in r.stderr), (1, False), r.stderr)
                self.assertIn(
                    f"{why.format(at=at)} The study is scaffolded, but it has no lock file, and until one can be "
                    "made a shell that cannot write the study has nothing to lock to keep a launcher out while it "
                    f"archives. {first} scaffold again: init_study.py {sd} --force\n", r.stderr)
                self.assertEqual((sd.joinpath("runs.json").exists(), at.is_file() and not at.is_symlink(),
                                  outside.read_text()), (True, False, "not the study's"))
                remove(at)
                run("init_study.py", sd, "--force")
                self.assertTrue(at.is_file())

    def test_scaffold_and_plan_warn_when_every_persona_reviews_in_the_same_order(self):
        warning, seen = "every persona reviews in the same order", set()
        for seed in range(1, 7):
            sd = self.study(f"seed-{seed}", seed=seed, concepts=self.cfg["concepts"][:2])
            scaffolded = run("init_study.py", sd).stdout
            same = len(set(re.findall(r"^\| P0\d [^|]+\| (.+) \|$", sd.joinpath("key.md").read_text(), re.M))) == 1
            planned = run("launch.py", sd, "plan").stdout
            self.assertEqual((f"WARNING: {warning}" in scaffolded, f"Note: {warning}" in planned), (same, same),
                             f"seed {seed}")
            seen.add(same)
        self.assertEqual(seen, {True, False})  # the seeds cover an order shared by all, and orders that differ
        dana = self.cfg["personas"][0]  # a variant takes its parent's order on purpose
        sd = self.study("pair", personas=[dana, {**dana, "id": "P02", "personality": "Blunt", "variant_of": "P01"}])
        self.assertNotIn(warning, run("init_study.py", sd).stdout)

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
        # --force replaces the run state, and the record of follow-ups answered in the files it rewrites.
        self.sd.joinpath("followups.json").write_text("[]\n")
        run("init_study.py", self.sd, "--force")
        self.assertFalse(self.sd.joinpath("followups.json").exists())
        # A turn log is the only record of an interview. One alone is guarded, and --force starts every
        # interview again by moving the logs and transcripts aside, never by deleting them or leaving them.
        sd = self.study("interviews", **self.interview())
        run("init_study.py", sd)
        # What belongs to the interviews held goes with them: the files their processes left, which the new
        # interviews would otherwise number their attempts into, and the two reports written from them.
        held = {"interviews/P01-opus.jsonl": '{"t": "start"}\n', "interviews/P01-opus.md": "The transcript.\n",
                "analysis/transcripts/P01-opus.md": "The analysts' copy.\n",
                "logs/P01-opus.2.in": "A question.\n", "logs/interviewer-P01-opus.3.out": "A reply.\n",
                "logs/P01-opus.interview-1.jsonl": '{"t": "start"}\n',
                "analysis/usage.md": "What they used.\n", "analysis/checks.md": "What was checked.\n"}
        kept = {"logs/notes.txt": "The lead's own.\n"}  # named for no entry of runs.json: not the scaffold's to move
        for path, text in {**held, **kept}.items():
            sd.joinpath(path).parent.mkdir(exist_ok=True)
            sd.joinpath(path).write_text(text)
        scaffolded = sd.joinpath("runs.json").read_text()
        sd.joinpath("runs.json").unlink()
        r = run("init_study.py", sd, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--force", r.stderr)
        self.assertFalse(sd.joinpath("runs.json").exists())
        sd.joinpath("runs.json").write_text(scaffolded)
        run("init_study.py", sd, "--force")
        self.assertEqual(([p for p in held if sd.joinpath(p).exists()], [p for p in kept if sd.joinpath(p).exists()]),
                         ([], list(kept)))
        aside, = sd.glob("logs/interviews-*")
        where = {p: p.replace("interviews/", "").replace("analysis/transcripts/", "transcripts/") for p in held}
        self.assertEqual({p: aside.joinpath(where[p]).read_text() for p in held}, held)

    def test_invalid_model_entries_and_options_are_refused(self):
        dana, sam = self.cfg["personas"]
        look = {"id": "T1", "goal": "See what it costs."}

        def usability(target, **more):  # a usability study, which has tasks and no concepts
            return {"type": "usability", "runner": "claude", "concepts": None, "find_the_answer": None,
                    "target": target, "tasks": [look], **more}
        remote = {"base_url": "https://bank.example.com", "allow_remote": True}
        topic = self.interview()["interview"]["topics"][0]
        cases = {
            "variant of no persona": ({"personas": [dana, {**sam, "variant_of": "P09"}]}, '"P09" is not a persona id'),
            "variant of itself": ({"personas": [dana, {**sam, "variant_of": "P02"}]}, "names the persona itself"),
            "variant of a variant": ({"personas": [dana, {**sam, "variant_of": "P01"},
                                                   {**sam, "id": "P03", "variant_of": "P02"}]},
                                     "is itself a variant of P01"),
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
            "the study brief as a file for the analysts": (
                {"synthesis": {"context_files": ["notes/Study-Brief.md"]}}, "is the study brief"),
            "unknown concept kind": ({"concepts": [{"id": "x", "kind": "figma", "path": "../concepts/01-plain"}]},
                                     'unknown "kind" "figma"'),
            "a url that is not http or https": (
                {"concepts": [{"id": "x", "kind": "url", "url": "file:///srv/site/index.html"}]},
                "must be a full http:// or https:// URL"),
            "a url whose first page is not the home page": (
                {"concepts": [{"id": "x", "kind": "url", "pages": [{"name": "pricing", "url": "https://a.test/p"}]}]},
                'named "index"'),
            "a file of a type no panellist can open": (
                {"concepts": [{"id": "x", "kind": "files", "files": ["../mock/home.psd"]}]},
                '"../mock/home.psd" is not a file type a panel can review'),
            "a file that is not there": ({"concepts": [{"id": "x", "kind": "files", "files": ["../mock/gone.png"]}]},
                                         "Concept x: no file"),
            "only images in a text-only study": (
                {"materials": "text", "concepts": [{"id": "x", "kind": "files", "files": ["../mock/home.png"]}]},
                "it has only images, and a text-only study"),
            "one concept and no singular for what it is": (
                {"concepts": self.cfg["concepts"][:1], "artefact_plural": "pricing pages"},
                'a study with one concept needs "artefact"'),
            # Names that become part of a path: none may leave the folder it is put in.
            "a state name that leaves its folder": (
                {"concepts": [{**self.cfg["concepts"][0], "states": [{"name": "../../x", "js": "1"}]}]},
                'the state name "../../x" must be letters, digits, hyphens and underscores only'),
            "a concept id that leaves the archive": (
                {"concepts": [{"id": "../x", "path": "../concepts/01-plain"}]},
                'the concept id "../x" must be one part of a file name'),
            "a persona id that leaves the personas folder": (
                {"personas": [{**dana, "id": "../../P01"}, sam]}, 'the persona id "../../P01" must be one part of'),
            "a persona id with a hyphen, which file names split on": (
                {"personas": [{**dana, "id": "P-01"}, sam]}, 'the persona id "P-01" cannot hold a hyphen'),
            "a persona whose name gives no file name": (
                {"personas": [{**dana, "name": "\u674e\u96f7"}, sam]}, 'has no letter from a to z and no digit'),
            "two personas with one id": ({"personas": [dana, {**sam, "id": "p01"}]}, 'two personas have the id "p01"'),
            "a pinned label that leaves the materials folder": (
                {"labels": {"A/../../x": "01-plain", "B": "02-story", "C": "03-console"}},
                'the label "A/../../x" must be letters and digits only'),
            # The local-host rule of a usability study.
            "a usability target that is not a local host": (
                usability({"base_url": "https://bank.example.com"}), "is not a local development host"),
            "a host that only begins like a local one": (
                usability({"base_url": "http://localhost.example.com:8080"}), "is not a local development host"),
            # An address a browser would take somewhere else than it reads, or read as another host.
            "a target with a backslash, which a browser reads as a slash": (
                usability({"base_url": "http://example.com\\.localhost"}), "is not http:// or https://, a host and"),
            "a target with a user name before another host": (
                usability({"base_url": "http://localhost@example.com"}), "is not http:// or https://, a host and"),
            "a target whose host ends in a dot": (
                usability({"base_url": "http://localhost."}), "has a host that is not a plain name"),
            "a local name with a punycode label": (
                usability({"base_url": "http://xn--pp-fka.localhost"}), '"xn--", is never taken as one'),
            "a target that is one number": (
                usability({"base_url": "http://2130706433"}), "has a host that ends in a number"),
            "a target in hexadecimal": (
                usability({"base_url": "http://0x7f.1"}), "has a host that ends in a number"),
            "a start that leaves the target": (
                usability({"base_url": "http://app.localhost:8080"}, tasks=[{**look, "start": "//example.com/login"}]),
                'must be a path on the target, beginning with one "/"'),
            "a remote target, allowed, with a task that may change something": (
                usability(remote), 'task T1: it must say "read_only": true'),
            "a remote target, allowed, with test accounts": (
                usability(remote, tasks=[{**look, "read_only": True}], accounts={"provision": "make-account.sh"}),
                '"accounts" cannot be used with a remote target'),
            "a usability study with a phrase for its product and no name": (
                usability({"base_url": "http://app.localhost:8080"}, product=None, product_phrase="a bank's site"),
                'a usability study needs "product"'),
            # An interview study has a guide and nothing of the other two types, and they have none of its guide.
            "a guide in a review study": (
                {"interview": self.interview()["interview"]},
                '"interview" belongs to an interview study, and this is a review study'),
            "a guide in a usability study": (
                usability({"base_url": "http://app.localhost:8080"}, interview=self.interview()["interview"]),
                '"interview" belongs to an interview study, and this is a usability study'),
            "concepts in an interview study": (
                self.interview(concepts=self.cfg["concepts"]),
                '"concepts" belongs to a review study, and this is an interview study'),
            "tasks in an interview study": (
                self.interview(tasks=[look]), '"tasks" belongs to a usability study, and this is an interview study'),
            "factors to score in an interview study": (
                self.interview(factors=[{"key": "overall", "label": "Overall", "question": "Your verdict."}]),
                'an interview study has no "factors"'),
            "a product named in an interview study": (
                self.interview(product="Acme"), 'an interview study has no "product"'),
            "an interview study in native mode": (
                self.interview(runner=None), "an interview study cannot run in native mode"),
            "a topic whose id is what a reply writes to close": (
                self.interview({"topics": [{**topic, "id": "Close"}]}), 'the topic id "Close" is taken'),
            "an interview cap with no room for the opening and the close": (
                self.interview({"turns": 2}), "interview.turns is 2, but 1 topic needs at least 3"),
            "a follow-up allowance in an interview study": (
                self.interview(limits={"followup": {"minutes": 5}}),
                '"limits" must be an object with any of run, interviewer, turn, synthesis and overrides'),
            # What the interviewer would say aloud, and whom the guide leaves out: found when the study is scaffolded.
            "a leak term in a topic's opener": (
                self.interview({"topics": [{**topic, "opener": "What do you make of Secret Codename?"}]}),
                'topic T1: its opener holds the leak term "secret codename"'),
            "a leak term in a learning goal": (
                self.interview({"goals": [{"id": "G1", "learn": "Whether the secret codename would sell"}]}),
                'goal G1: its "learn" holds the leak term "secret codename"'),
            "a persona whose segment no topic is for": (
                self.interview({"topics": [{**topic, "segments": ["owner"]}]}),
                'persona P02 (segment "staff") is left with no topic'),
            # What the plan would refuse of study.json alone is refused before anything is scaffolded.
            "two analysts for one persona": ({"personas": [dana], "synthesis": {"analysts": 2}},
                                             "synthesis.analysts is 2, but the study has 1 persona"),
        }
        for i, (name, (overrides, message)) in enumerate(cases.items()):
            with self.subTest(name):
                sd = self.study(f"bad-{i}", **overrides)
                r = run("init_study.py", sd, check=False)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(message, r.stderr)
                self.assertFalse((sd / "runs.json").exists())
        # A local name is local in any case, and panellists are given the address as its parts say, not as written.
        sd = self.study("mixed-case", **usability({"base_url": "HTTP://App.LocalHost:8080/"}))
        run("init_study.py", sd)
        instructions = sd.joinpath("panel/_panel-instructions.md").read_text()
        self.assertEqual(("`http://app.localhost:8080/`" in instructions, "LocalHost" in instructions), (True, False))

    def test_folder_of_images_alone_in_a_text_only_study_is_refused_and_the_plan_says_why(self):
        mock_ups = Path(self.tmp.name) / "mock"
        mock_ups.mkdir()
        (mock_ups / "home.png").write_bytes(png(40, 30))
        sd = self.study("words", materials="text",
                        concepts=[*self.cfg["concepts"][:1], {"id": "mock-ups", "kind": "files", "path": "../mock"}])
        why = "Concept mock-ups: it has only images, and a text-only study"
        planned = run("launch.py", sd, "plan")  # read before anything is scaffolded, and it starts nothing
        self.assertIn(f"Missing: {why}", planned.stdout)
        refused = run("init_study.py", sd, check=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn(why, refused.stderr)
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
        # Every runner of the skill can drive a browser, so one that cannot is added to a copy of the skill.
        skill = Path(self.tmp.name) / "skill"
        shutil.copytree(SCRIPTS.parent, skill, ignore=shutil.ignore_patterns("__pycache__"))
        (skill / "scripts/runners/plain.py").write_text(
            "from . import codex\nfrom .codex import *  # noqa: F401,F403\n\n\ndef capabilities():\n"
            "    return {**codex.capabilities(), 'browser': False, 'browse_gaps': []}\n")
        both = [{"key": "a", "runner": "claude"}, {"key": "b", "runner": "plain"}]
        # Whose browser session a run uses: one it starts and closes itself, in native mode, where there is
        # no launcher, or the one a launcher has open for it. (What the instructions say, what a run prompt says.)
        own = ("Use your own session: `agent-browser --session <your run id> ...`", "Use it as the session name")
        given = ("A browser session is already open for you", "Your browser session is open already")
        cases = {  # study settings: (the session the instructions offer, {model key: what its run prompt says})
            "native study, browsing by default": ({}, own, {"opus": offered, "fable": offered}),
            "browsing switched off": ({"browse": False, "models": both}, None, {"a": None, "b": None}),
            "a runner that cannot drive a browser": ({"models": both}, given, {"a": offered, "b": ruled_out}),
            "a live URL beside a site, with browsing not asked for": (
                {"concepts": [*self.cfg["concepts"][:1], {"id": "live", "kind": "url", "url": "https://a.test/"}]},
                None, {"opus": None, "fable": None}),
        }
        for i, (name, (settings, session, prompts)) in enumerate(cases.items()):
            with self.subTest(name):
                sd = self.study(f"browse-{i}", **settings)
                subprocess.run([sys.executable, str(skill / "scripts/init_study.py"), str(sd)], check=True,
                               capture_output=True, text=True)
                instructions, in_instructions = sd.joinpath("panel/_panel-instructions.md").read_text(), bool(session)
                self.assertEqual("agent-browser" in instructions, in_instructions)
                self.assertEqual([said for said in (own, given) if said[0] in instructions],
                                 [session] if session else [])
                self.assertIn("3. **Write only to your own persona file.**", instructions)
                for key, says in prompts.items():
                    prompt = sd.joinpath(f"prompts/P01-{key}.md").read_text()
                    self.assertEqual([x for x in (offered, ruled_out) if x in prompt], [says] if says else [])
                    self.assertEqual("agent-browser" in prompt, bool(says))
                    self.assertEqual([said for said in (own, given) if said[1] in prompt],
                                     [session] if says == offered else [])
                    # A run allowed agent-browser and no other command cannot make its screenshot folder.
                    self.assertEqual((sd / f"panel/scratch/P01-{key}").is_dir(), says == offered)
                # A site copy is the page source under its own file names: it is inside panel/, which a
                # panellist may read, only where the browser opens it, and no instruction names it elsewhere.
                copies = {str(f.relative_to(sd).parent.parent) for f in sd.rglob("pricing.html")}
                self.assertEqual(copies, {"panel/sites" if in_instructions else "sites"})
                self.assertEqual("/sites/concept-" in instructions, in_instructions)
        sd = Path(self.tmp.name) / "browse-0"  # scaffolded with browsing on: the copies follow the setting
        for browse in (False, True):
            sd.joinpath("study.json").write_text(json.dumps({**self.cfg, "browse": browse}))
            run("init_study.py", sd, "--force")
            self.assertEqual(((sd / "panel/sites").exists(), (sd / "sites").exists()), (browse, not browse))

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
        self.assertIn("2 score rows from 2 runs; 1 run incomplete", run("extract_scores.py", sd).stdout)

    def test_single_concept_study_passes_checks_and_analysis_with_nothing_ranked_or_compared(self):
        sd = self.study("one", concepts=self.cfg["concepts"][:1], artefact="pricing page",
                        artefact_plural="pricing pages", models=["opus", "haiku"])  # haiku has default notes
        run("init_study.py", sd)
        runs = json.loads(sd.joinpath("runs.json").read_text())
        told = [sd.joinpath("panel/_panel-instructions.md").read_text(),
                *(sd.joinpath(r[k]).read_text() for r in runs for k in ("prompt", "file"))]
        self.assertIn("give honest feedback on one pricing page for", told[0])
        self.assertIn("There is one concept to review, Concept A:", told[0])
        for text in told:  # one design: nothing to compare it with, rank it against or order it among
            for word in ("alternative", "anking", "Comparison", "Score summary", "Review order", "the order",
                         "each concept", "top concept", "pricing pages", "1 concepts"):
                self.assertNotIn(word, text)
        # Four runs that disagree, none with a ranking, since the template asks for none.
        for r, overall in zip(runs, (8, 6, 9, 4)):
            f = sd / r["file"]
            f.write_text(f.read_text() + filled_section("A", [*range(1, FACTORS), overall])
                         + "## Out of character: researcher notes\nNotes.\n")
        checked = run("check_runs.py", sd)
        self.assertNotIn("ranking", checked.stdout)
        self.assertIn("4 run files of 4 expected; 0 with blocking problems", checked.stdout)
        self.assertIn("4 score rows from 4 runs; 0 runs incomplete", run("extract_scores.py", sd).stdout)
        self.assertEqual(sd.joinpath("analysis/rankings.csv").read_text().splitlines(),
                         ["persona_id,model,replicate,complete,segment,rank,concept"])
        printed = run("analyze.py", sd).stdout
        report = sd.joinpath("analysis/quant.md").read_text()
        self.assertIn("- Mean Overall 6.75 across 4 runs (median 7.0, SD 2.22, lowest 4, highest 9).", printed)
        self.assertIn("| Overall | 4 | 6.75 | 7.0 | 2.22 | 4 | 9 |", report)
        self.assertIn("Spearman across concepts is not available with one concept", printed)
        for text in (printed, report):
            for heading in ("## Leaderboard", "Winner", "Ranked", "| Borda", "## Order effect", "Top 1", "Same top"):
                self.assertNotIn(heading, text)
            self.assertIsNone(re.search(r"\bnan\b", text, re.I))
        lines = report.splitlines()  # no table is a header alone
        for i, line in enumerate(lines):
            if line.startswith("|---"):
                self.assertTrue(lines[i + 1].startswith("| "), lines[i - 1])

        def strict(constant):
            raise AssertionError(f"quant.json holds {constant}, which is not JSON")
        quant = json.loads(sd.joinpath("analysis/quant.json").read_text(), parse_constant=strict)
        self.assertEqual((quant["concept"], "leaderboard" in quant, "order" in quant), ("A", False, False))
        # Model agreement on the one concept: each persona's two models, 2 and 5 points apart.
        self.assertEqual(quant["models"]["pair_difference"]["opus-haiku"]["overall"], 3.5)

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

    def test_analysis_says_when_concepts_of_different_forms_are_compared_and_no_panellist_is_told(self):
        base = Path(self.tmp.name)
        (base / "screenshot.png").write_bytes(png(40, 40))
        (base / "deck.pdf").write_bytes(pdf(["One page"]))
        # An image beside a PDF where Poppler is installed, which a PDF needs, and beside a site where it is not.
        other = ({"id": "02-story", "kind": "files", "files": ["../deck.pdf"]}
                 if all(shutil.which(tool) for tool in ("pdftotext", "pdftoppm")) else self.cfg["concepts"][1])
        sd = self.study("forms", concepts=[{"id": "01-plain", "kind": "files", "files": ["../screenshot.png"]}, other,
                                           {"id": "03-console", "kind": "files", "files": ["../screenshot.png"]}])
        run("init_study.py", sd)
        self.key = sd.joinpath("key.md").read_text()
        self.fill_all(json.loads(sd.joinpath("runs.json").read_text()), sd)
        run("extract_scores.py", sd)
        run("analyze.py", sd)
        report, filed = sd.joinpath("analysis/quant.md").read_text(), self.labels_for("03-console")
        top, by_factor = report.index("Format caution: the concepts did not all reach the panel in one form"), \
            report.index("## By factor")
        self.assertLess(top, report.index("## Key numbers"))
        self.assertIn(f"{filed} is image files", report[top:report.index("## Key numbers")])
        self.assertIn("Visual design and Mobile are the factors most exposed", report[by_factor:])
        told = "".join(f.read_text() for folder in ("panel", "prompts") for f in (sd / folder).rglob("*.md"))
        self.assertNotIn("image files", told)
        # An archive without --concepts has no source file left to tell a PDF from an image.
        dest = base / "archive/forms"
        run("archive.py", sd, "--dest", dest)
        run("analyze.py", dest)
        self.assertIn(report[top:report.index("## Key numbers")], dest.joinpath("analysis/quant.md").read_text())
        self.fill_all()  # concepts all of one form have no format to tell apart
        run("extract_scores.py", self.sd)
        run("analyze.py", self.sd)
        self.assertNotIn("Format caution", self.sd.joinpath("analysis/quant.md").read_text())

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
        text = f.read_text() + filled_section(a, [9] * FACTORS) + "Mentions the secret codename \u2014 oops.\n"
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
        # A section written without its score row counts for nothing, so the run is asked for the row.
        unscored = self.labels_for("02-story")
        f.write_text(f.read_text() + f"### Concept {unscored}\n**5-second take (in my words):** fine.\n")
        out = run("runs.py", self.sd, "resume", r0["run"]).stdout
        self.assertIn(f"Written, but with no score row: {unscored}.", out)
        self.assertIn("add the score table at the end of that section", out)

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
        from panel_lib import NOTICE
        t = Path(self.tmp.name) / "out.jsonl"
        doc = "Here it is.\n\n# Round 1 synthesis\n\n- point\n"
        t.write_text("\n".join(json.dumps(x) for x in [
            {"message": {"role": "user", "content": "go"}},
            {"message": {"role": "assistant", "content": [{"type": "text", "text": doc}]}},
        ]))
        out = Path(self.tmp.name) / "s.md"
        run("extract_agent_reply.py", t, "--out", out)
        self.assertEqual(out.read_text(), f"# Round 1 synthesis\n\n{NOTICE}\n\n- point\n")

    def test_archive_keeps_findings_and_drops_bulk(self):
        self.fill_all()
        run("extract_scores.py", self.sd)
        (self.sd / "panel/materials/concept-A/index").mkdir(parents=True)
        (self.sd / "panel/materials/concept-A/index/page-text.txt").write_text("x")
        (self.sd / "study-brief.md").write_text("# Study brief\n\nWhat was agreed.\n")
        # Folders with nothing in them that is kept: one holds only a name that is left out, one holds nothing.
        (self.sd / "panel/personas/drafts/__pycache__").mkdir(parents=True)
        (self.sd / "panel/personas/drafts/__pycache__/notes.pyc").write_bytes(b"x")
        (self.sd / "prompts/unused").mkdir()
        dest = Path(self.tmp.name) / "archive/customer-research/2026-09-25-t/panel/round-1"
        run("archive.py", self.sd, "--dest", dest)
        self.assertIn("What was agreed.", (dest / "study-brief.md").read_text())
        self.assertTrue((dest / "personas").is_dir())
        self.assertTrue((dest / "panel-instructions.md").exists())
        self.assertTrue((dest / "analysis/scores.csv").exists())
        self.assertTrue((dest / "key.md").exists())
        self.assertFalse((dest / "materials").exists())
        self.assertFalse((dest / "sites").exists())

        def held():
            return {f.relative_to(dest).as_posix(): f.read_bytes() for f in dest.rglob("*") if f.is_file()}

        def empty():  # a folder is in the archive only to hold a file, so none of it is empty
            return [d.relative_to(dest).as_posix() for d in dest.rglob("*") if d.is_dir() and not any(d.iterdir())]

        self.assertEqual(empty(), [])
        # Archiving again replaces what has the same name and keeps the rest: what the lead put beside the round,
        # and a file the study no longer has. A folder with nothing in it goes, one an older archive left too.
        first = held()
        (dest / "scripts").mkdir()
        (dest / "scripts/rescore.py").write_text("# one-off\n")
        (dest / "prompts/unused/deeper").mkdir(parents=True)
        stuck = []  # an empty folder that cannot be removed is named and left, and the round is archived all the same
        if os.geteuid():  # root removes it whatever the modes say
            (dest / "shut/leaf").mkdir(parents=True)
            (dest / "shut").chmod(0o555)
            stuck = ["shut/leaf"]
        gone = self.sd / self.runs[0]["prompt"]
        gone.unlink()
        (self.sd / "study-brief.md").write_text("# Study brief\n\nAgreed since.\n")
        try:
            r = run("archive.py", self.sd, "--dest", dest, check=False)
        finally:  # before tearDown(), so that the test's directory can be removed
            if stuck:
                (dest / "shut").chmod(0o755)
        self.assertEqual((r.returncode, "Traceback" in r.stderr, f"Archived {self.sd.name} to " in r.stdout),
                         (0, False, True), r.stderr)
        self.assertEqual(r.stderr.splitlines(), [
            f"An empty folder was left in the archive, because it could not be removed (Permission denied): "
            f"{dest.resolve() / name}" for name in stuck])
        again = held()
        self.assertIn(b"Agreed since.", again.pop("study-brief.md"))
        self.assertEqual(again.pop("scripts/rescore.py", None), b"# one-off\n")
        self.assertEqual(again, {name: content for name, content in first.items() if name != "study-brief.md"})
        self.assertIn(gone.relative_to(self.sd).as_posix(), again)
        self.assertEqual(empty(), stuck)

    def test_archive_reads_nothing_through_a_link_or_a_special_file_and_one_that_fails_leaves_no_part_of_itself(self):
        self.fill_all()
        base = Path(self.tmp.name)
        personas, dest, outside = self.sd / "panel/personas", base / "archive/topic/panel/round-1", base / "outside.md"
        outside.write_text("Not the study's.\n")
        odd = "what I saw; $(id) & more.md"  # a panellist's own text, which no message repeats

        def linked():  # what it points at is not the study's, and copying through it would bring that in
            personas.joinpath("link.md").symlink_to(outside)
            return personas / "link.md"

        def piped():  # opening one waits for whoever writes to it
            os.mkfifo(personas / "pipe.md")
            return personas / "pipe.md"

        def shut():  # a review study scans nothing, so the copy is the first to open it, with files already copied
            personas.joinpath(odd).write_text("A note.\n")
            personas.joinpath(odd).chmod(0)
            return personas / odd

        def archive():
            return subprocess.run([sys.executable, str(SCRIPTS / "archive.py"), str(self.sd), "--dest", str(dest)],
                                  capture_output=True, text=True, timeout=60)

        def held():  # every file under the archive's root, what a failed archive left beside the round included
            return {f.relative_to(base).as_posix(): f.read_bytes() for f in base.joinpath("archive").rglob("*")
                    if f.is_file()}

        cases = {"a symbolic link": (linked, "panel/personas/link.md: it is a symbolic link"),
                 "a FIFO": (piped, "panel/personas/pipe.md: it is neither a regular file nor a folder"),
                 "a file that may not be read": (shut, f"panel/personas/(a name that is not shown, {len(odd)} "
                                                       "characters): Permission denied")}
        for name, (plant, said) in cases.items():
            if plant is shut and not os.geteuid():
                continue  # nothing is unreadable to root
            with self.subTest(name):
                planted = plant()
                r = archive()
                planted.unlink()
                self.assertIn(said, r.stderr)
                self.assertEqual((r.returncode, "Traceback" in r.stderr, "$(id)" in r.stdout + r.stderr,
                                  base.joinpath("archive").exists()), (1, False, False, False), r.stderr)
        if os.geteuid():  # and an earlier archive at the destination stays whole, as it was
            run("archive.py", self.sd, "--dest", dest)
            earlier = held()
            (self.sd / "study-brief.md").write_text("# Study brief\n\nAgreed since.\n")  # copied before the personas
            # What an archive that was killed left beside the round goes with the next one, which fails too.
            stale = dest.with_name(f".{dest.name}.archive-left")
            stale.joinpath(dest.name).mkdir(parents=True)
            stale.joinpath(dest.name, "study-brief.md").write_text("Half of a round.\n")
            planted = shut()
            self.assertEqual((archive().returncode, held()), (1, earlier))
            self.assertEqual([f.name for f in dest.parent.iterdir()], [dest.name])
            planted.unlink()

    def test_archive_keeps_every_file_of_a_concept_when_files_from_different_folders_share_a_name(self):
        base = Path(self.tmp.name)
        sources = {"a/foo.png": png(1, 1), "b/foo.png": png(2, 2), "c/item-02-foo.png": png(3, 3)}
        for name, image in sources.items():
            (base / name).parent.mkdir()
            (base / name).write_bytes(image)
        sd = self.study("clash", concepts=[{"id": "shots", "kind": "files", "files": [f"../{name}" for name in sources]}])
        run("init_study.py", sd)
        run("archive.py", sd, "--dest", base / "archive/topic/panel/round-1", "--concepts")
        self.assertEqual({f.name: f.read_bytes() for f in (base / "archive/topic/concepts/shots").iterdir()},
                         dict(zip(("item-01-foo.png", "item-02-foo.png", "item-03-item-02-foo.png"), sources.values())))

    def test_capture_refuses_a_path_that_leaves_the_materials_directory_before_it_writes_or_deletes(self):
        base, sd = Path(self.tmp.name), self.study("leaving", materials="text")  # words alone need no ImageMagick
        materials, study_json = sd / "panel/materials", sd / "study.json"
        run("init_study.py", sd)
        fakes.install(base, "agent-browser")

        def planted(folder):  # the sheets of an earlier capture, which a capture of the page replaces
            for name in ("raw/d-00.png", "desktop-sheet-01.png"):
                (folder / name).parent.mkdir(parents=True, exist_ok=True)
                (folder / name).write_bytes(png(1, 1))
            return folder

        def refused(why, outside):
            captured = subprocess.run([sys.executable, str(SCRIPTS / "capture.py"), str(sd)],
                                      env={"PATH": str(base)}, capture_output=True, text=True)
            self.assertEqual(len(list(outside.rglob("*.png"))), 2)
            self.assertEqual(list(materials.rglob("page-text.txt")), [])
            self.assertNotEqual(captured.returncode, 0)
            self.assertIn(why, captured.stderr)

        # A state is captured to the folder <page>@<name>: this name would make that <tmp>/external.
        scaffolded = json.loads(study_json.read_text())
        climbing = {**self.cfg["concepts"][0], "states": [{"name": "x/../../../../../external", "js": "1"}]}
        study_json.write_text(json.dumps({**scaffolded, "concepts": [climbing, *self.cfg["concepts"][1:]]}))
        refused('the state name "x/../../../../../external" must be letters', planted(base / "external"))
        # With every name in order, a folder under panel/materials that links elsewhere still leads out.
        study_json.write_text(json.dumps(scaffolded))
        (materials / "concept-A").symlink_to(base / "linked")
        refused("Refusing to write or delete", planted(base / "linked/index").parent)

    def test_capture_killed_while_it_published_a_page_leaves_one_whole_capture_of_it_to_the_next(self):
        base, sd = Path(self.tmp.name), self.study("killed", materials="text")  # words alone need no ImageMagick
        run("init_study.py", sd)
        fakes.install(base, "agent-browser")
        ended = subprocess.Popen([sys.executable, "-c", ""])
        ended.wait()
        page, folders = "panel/materials/concept-A/index", {"new": "000", "earlier": "000.earlier"}
        # What a capture of concept A's index left: its record of the publication, the new capture and the
        # earlier one, each in the scratch folder, in place or nowhere. The next capture is of concept B.
        for case, pid, place, held, before, after, stays, says in (
                ("killed with the earlier capture moved aside", ended.pid, page, ("new", "earlier"), None, "new", False,
                 f"Finished publishing {page}"),
                ("killed with the new capture moved in", ended.pid, page, ("earlier",), "new", "new", False, None),
                ("left with the earlier capture alone", ended.pid, page, ("earlier",), None, "earlier", False,
                 f"Put back the earlier capture of {page}"),
                ("still at work", os.getpid(), page, ("new", "earlier"), None, None, True, None),
                ("recorded for a place outside the materials", ended.pid, "../outside/index", ("new", "earlier"), None,
                 None, True, "Refusing to move a capture to")):
            with self.subTest(case):
                scratch, dest = sd / f".capture-{pid}-left", sd / place
                for folder, text in [*((scratch / folders[kept], kept) for kept in held),
                                     *([(dest, before)] if before else [])]:
                    folder.mkdir(parents=True)
                    (folder / "page-text.txt").write_text(text)
                (scratch / "000.publish").write_text(json.dumps({"dest": place, **folders}))
                captured = subprocess.run([sys.executable, str(SCRIPTS / "capture.py"), str(sd), "--label", "B"],
                                          env={"PATH": str(base)}, capture_output=True, text=True)
                self.assertEqual(captured.returncode == 0, place == page, captured.stderr)
                if says:
                    self.assertIn(says, captured.stdout + captured.stderr)
                self.assertEqual({f.parent.name: f.read_text() for f in sd.glob("panel/materials/concept-A/*/*")},
                                 {"index": after} if after else {})
                self.assertFalse((base / "outside").exists())
                self.assertEqual(sorted(f.read_text() for f in scratch.glob("*/page-text.txt")),
                                 sorted(held) if stays else [])
                self.assertEqual(scratch.exists(), stays)
                shutil.rmtree(scratch, True)
                shutil.rmtree(sd / page, True)

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

    # ---- the roster grid and roster files, the study brief and the synthetic panel notice

    def test_roster_grid_is_deterministic_covers_every_role_and_personality_and_refuses_what_it_cannot_meet(self):
        roles = ["Staff", {"role": "Owner of a 2-site cafe", "segment": "owner"}, "Accountant"]
        kinds = ["Curious sceptic", "Early adopter", "Time-poor skimmer", "Critic"]
        written = self.cfg["personas"]

        def study(name, caps, personas=(), grid=(), **settings):
            grid = {"roles": roles, "personalities": kinds, "stages": ["new to the industry", "20 years in"],
                    **dict(grid)}
            return self.study(name, personas=list(personas), roster={**grid, "caps": caps}, **settings)

        def personas(sd):
            return json.loads(sd.joinpath("study.json").read_text())["personas"]

        sd = study("grid", {"personas": 5, "runs": 10})
        before = json.loads(sd.joinpath("study.json").read_text())
        run("roster.py", sd, "grid")
        text = sd.joinpath("study.json").read_text()
        after = json.loads(text)
        self.assertEqual(list(after), list(before))
        self.assertEqual(text, json.dumps({**before, "personas": after["personas"]}, indent=2) + "\n")
        skeletons = after["personas"]
        self.assertEqual([p["id"] for p in skeletons], ["P01", "P02", "P03", "P04", "P05"])
        self.assertEqual({p["role"].split(", ")[0] for p in skeletons},
                         {"Staff", "Owner of a 2-site cafe", "Accountant"})
        self.assertEqual({p["personality"] for p in skeletons}, set(kinds))
        self.assertEqual({p["role"].split(", ")[1] for p in skeletons}, {"new to the industry", "20 years in"})
        self.assertEqual({p["segment"] for p in skeletons}, {"staff", "owner", "accountant"})
        self.assertEqual(len({(p["role"], p["personality"]) for p in skeletons}), 5)
        self.assertTrue(all(p["name"] == "TODO" and p["bio"] == [] for p in skeletons))
        again = study("grid-again", {"personas": 5, "runs": 10})
        run("roster.py", again, "grid")
        self.assertEqual(personas(again), skeletons)
        # A skeleton is never scaffolded: the lead has to write it first.
        r = run("init_study.py", sd, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("still a roster skeleton", r.stderr)
        self.assertFalse((sd / "runs.json").exists())

        one_of_each = {"roles": ["Staff"], "personalities": ["Curious sceptic"]}
        refused = {  # caps, the personas already there, study settings, arguments, what the refusal says
            "a cap too small for every role and personality": ({"personas": 3}, [], {}, [], "takes at least 4"),
            "more runs than the cap": (
                {"personas": 5, "runs": 19}, [], {"replicates": 2}, [],
                "5 personas x 2 model entries x 2 replicates = 20 runs, over roster.caps.runs of 19"),
            "personas already written": ({}, written, {}, [], "--append"),
            "written personas that leave too little of the cap": (
                {"personas": 5}, written, {}, ["--append"], "takes at least 4 more"),
            # One role and one personality, so one more persona covers both, and not the two stages.
            "written personas that leave too little of the cap for every stage": (
                {"personas": 2}, written[:1], {"grid": one_of_each}, ["--append"],
                "every stage to appear once. 1 role x 1 personality x 2 stages = 2 combinations, and covering every "
                "role, every personality and every stage takes at least 2 more. Set roster.caps.personas to 3"),
        }
        for i, (name, (caps, there, settings, arguments, message)) in enumerate(refused.items()):
            with self.subTest(name):
                sd = study(f"refused-{i}", caps, there, **settings)
                was = sd.joinpath("study.json").read_text()
                r = run("roster.py", sd, "grid", *arguments, check=False)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(message, r.stderr)
                self.assertEqual(was, sd.joinpath("study.json").read_text())

        sd = study("append", {"personas": 6}, written)
        run("roster.py", sd, "grid", "--append")
        self.assertEqual(personas(sd)[:2], written)
        self.assertEqual([(p["id"], p["name"]) for p in personas(sd)[2:]],
                         [("P03", "TODO"), ("P04", "TODO"), ("P05", "TODO"), ("P06", "TODO")])
        # A written persona that is still a combination of the grid covers its stage: one more will do.
        new_hire = {**written[0], "role": "Staff, new to the industry", "personality": "Curious sceptic"}
        sd = study("append-to-a-stage", {"personas": 2}, [new_hire], grid=one_of_each)
        run("roster.py", sd, "grid", "--append")
        self.assertEqual([p["role"] for p in personas(sd)], ["Staff, new to the industry", "Staff, 20 years in"])

    def test_roster_file_carries_personas_between_studies_and_refuses_a_clash(self):
        dana, sam = self.cfg["personas"]
        first = self.study("first", personas=[dana, {**sam, "variant_of": "P01"}])
        file = Path(self.tmp.name) / "project/roster.json"
        run("roster.py", first, "export", "--to", file)
        held = json.loads(file.read_text())
        self.assertEqual(list(held), ["personas"])  # nothing else of the study leaves it
        self.assertEqual(held["personas"], [
            {"id": "P01", "name": "Dana Kowalski", "slug": "dana-kowalski", "role": "Owner", "personality": "Sceptic",
             "segment": "owner", "bio": ["Runs two cafes."]},
            {"id": "P02", "name": "Sam Lee", "slug": "sam-lee", "role": "Staff", "personality": "Early adopter",
             "segment": "staff", "bio": ["Uses the tools daily."], "variant_of": "P01"}])
        second = self.study("second", personas=[], product="Another product")
        before = json.loads(second.joinpath("study.json").read_text())
        run("roster.py", second, "import", "--from", file)
        self.assertEqual(json.loads(second.joinpath("study.json").read_text()),
                         {**before, "personas": held["personas"]})

        third = self.study("third", personas=[{**dana, "bio": ["Sold the cafes."]}])
        clashes = [("export", ["--to", file], file), ("import", ["--from", file, "--ids", "P01"], third / "study.json")]
        for command, arguments, target in clashes:
            with self.subTest(command):
                was = target.read_text()
                r = run("roster.py", third, command, *arguments, check=False)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("P01 (bio)", r.stderr)
                self.assertEqual(was, target.read_text())
        run("roster.py", third, "export", "--to", file, "--update")
        self.assertEqual([p["bio"] for p in json.loads(file.read_text())["personas"]],
                         [["Sold the cafes."], ["Uses the tools daily."]])

    def test_scaffold_refuses_a_copy_of_the_study_brief_inside_the_panel_folder(self):
        brief = "# Study brief\n\n## Hypotheses\n\nThe story concept wins with owners.\n"
        cases = {"under its own name": ("panel/notes/study-brief.md", "An older draft.\n", {}),
                 "under another name with the same content": ("panel/materials/background.md", brief, {}),
                 "in a concept folder, which is copied into the panel": ("../concepts/01-plain/notes.md", brief, {}),
                 "in the folder an interviewer starts in": ("interviewer/P01-opus/notes.md", brief, self.interview())}
        for i, (name, (path, content, overrides)) in enumerate(cases.items()):
            with self.subTest(name):
                sd = self.study(f"brief-{i}", **overrides)
                (sd / "study-brief.md").write_text(brief)
                copy = (sd / path).resolve()
                copy.parent.mkdir(parents=True, exist_ok=True)
                copy.write_text(content)
                r = run("init_study.py", sd, check=False)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(f"{copy} is a copy of the study brief", r.stderr)
                self.assertFalse((sd / "runs.json").exists())
                copy.unlink()
                run("init_study.py", sd)  # beside study.json is where the brief belongs

    def test_synthetic_panel_notice_is_on_every_persona_file_and_brief_and_the_archive_adds_it_where_missing(self):
        import panel_lib as pl
        notice = pl.NOTICE
        self.assertRegex(notice, "generated by AI personas.*not user research")
        for name in ("synthesis-brief.md", "qual-brief.md"):
            tokens = set(pl.PLACEHOLDER.findall((pl.ASSETS / name).read_text())) - {"NOTICE"}
            self.assertIn(f"\n{notice}\n", pl.fill_brief(name, dict.fromkeys(tokens, "x")))
        self.fill_all()
        files = sorted((self.sd / "panel/personas").glob("*.md"))
        for f in files:
            self.assertEqual(f.read_text().splitlines()[2], notice)  # under the title
        # What an older round holds: a persona file and a lead's note without the line.
        old = files[0]
        old.write_text(old.read_text().replace(notice + "\n\n", ""))
        run("extract_scores.py", self.sd)
        (self.sd / "analysis/lead-notes.md").write_text("Checked one claim.\n")
        dest = Path(self.tmp.name) / "archive/round-1"

        def archived():
            said = run("archive.py", self.sd, "--dest", dest).stdout
            held = {f.relative_to(dest).as_posix(): f.read_text() for f in sorted(dest.rglob("*")) if f.is_file()}
            # The closing line counts the files that carry the notice, the second time as the first.
            self.assertIn(f"{sum(name.endswith('.md') for name in held)} markdown files of this round carry the "
                          "synthetic panel notice.", said)
            return held

        first = archived()
        self.assertEqual([name for name, text in first.items() if name.endswith(".md") and text.count(notice) != 1], [])
        self.assertEqual(first[f"personas/{old.name}"].splitlines()[2], notice)
        self.assertEqual(first["analysis/lead-notes.md"], f"{notice}\n\nChecked one claim.\n")
        for name in ("analysis/scores.csv", "runs.json", "study.json"):  # data files are copied as they are
            self.assertEqual(first[name], self.sd.joinpath(name).read_text())
        self.assertEqual(archived(), first)
        self.assertIn("12 score rows from 4 runs; 0 runs incomplete", run("extract_scores.py", dest).stdout)
        self.assertIn("4 of 4 runs complete", run("analyze.py", dest).stdout)

    def template_section(self, sd, label, answers, fields):
        """A concept section as a panellist writes one: the template in the study's own instructions,
        filled in. answers are given in question order, and fields maps a word of a field's label to
        what the panellist wrote there."""
        blocks = sd.joinpath("panel/_panel-instructions.md").read_text().split("```")
        template = next(b for b in blocks if b.lstrip().startswith("### Concept <label>"))
        answers, used, out = iter(answers), set(), []
        for line in template.strip().splitlines():
            bold = re.match(r"\*\*(.+?)\*\*", line)
            if line.startswith("- "):
                line += " " + next(answers)
            elif bold:
                word = next((w for w in fields if w in bold[1]), None)
                used.add(word)
                line = bold[0] + (" " + fields[word] if word else "" if "find the answer" in bold[1] else " fine.")
            elif line.startswith("| n "):
                line = line.replace("n", "7")
            out.append(line.replace("<label>", label))
        self.assertEqual(used - {None}, set(fields), "the template no longer has a field the tallies read")
        return "\n".join(out) + "\n\n"

    def test_answers_and_lines_are_tallied_and_what_cannot_be_read_is_listed_as_unparsed(self):
        works, costs = questions = ["Does it work with my accounting software?", "What does it cost each month?"]
        sd = self.study("tallies", find_the_answer=questions)
        run("init_study.py", sd)
        clean, varied, patchy, stopped = json.loads(sd.joinpath("runs.json").read_text())
        x, y, z = (self.labels_for(c) for c in ("01-plain", "02-story", "03-console"))

        def write(r, *sections, done=True):
            f = sd / r["file"]
            f.write_text(f.read_text() + "".join(sections) + (finals([x, z, y]) if done else ""))

        def section(label, *fields):  # written by hand: the fields this panellist filled in, then the scores
            return filled_section(label, [7] * FACTORS).replace("fine.\n", "\n".join(["fine.", *fields, ""]), 1)

        # The template as given, filled in the way it asks.
        write(clean, *(self.template_section(sd, label, ["Found (FAQ, first answer).", "Not found"], {
            "keep": '"Know what every job made."', "cut": '"Set up in an afternoon."', "believe": '"none"',
            "forward": 'Yes, to my bookkeeper: "Have a look at this."'}) for label in (x, y, z)))
        # The ways real runs departed from it: questions reworded to a label, a verdict in bold or
        # in a nested bullet, curly quotes, a comment after a line, verdicts alone in question order,
        # a forward answer that announces its message.
        write(varied, section(
            x, "**Could I find the answer?**",
            "- Accounting software: **Found**, index, Good questions names Xero.",
            "- Monthly cost:",
            "  - Partly (Simple plans: $29 for 1 user; nothing for nine people).",
            "",
            "**One line to keep:** “Know what every job made.”",
            '**One line to cut:** "Set up in an afternoon" (vague, I\'d want a number)',
            '**One line I don’t believe:** "Know what every job made."',
            '**Would I forward it?** Maybe to my bookkeeper. "Worth a look?"',
        ), section(y), section(
            z, "**Could I find the answer?**", "- Found (pricing section)", "- Not found.",
            '**Would I forward it?** Yes, to a client who has asked me about job costing, with the message: '
            '"Check the learning step."'))
        # An answer that is no verdict, a question skipped, two lines where one was asked for, a
        # field left out, a forward answer that is neither yes nor no, and questions out of order.
        write(patchy, section(
            x, "**Could I find the answer?**", f"- {works} Yes, it says so in the FAQ.", f"- {costs}",
            '**One line to keep:** "Know your numbers." and "No more guessing."',
            "**One line I don't believe:** None.",
            "**Would I forward it?** Not yet. Maybe once it has prices.",
        ), section(y, "**Could I find the answer?**", f"- {costs} Not found", f"- {works} Partially, FAQ only."),
            section(z))
        # Cut off after one concept, with entries that would change every count below.
        write(stopped, section(
            x, "**Could I find the answer?**", f"- {works} Not found", f"- {costs} Not found",
            '**One line to keep:** "Know what every job made."', "**Would I forward it?** No.",
        ), done=False)

        run("extract_scores.py", sd)
        out = run("extract_answers.py", sd).stdout
        self.assertIn("20 answers (5 Found, 2 Partly, 7 Not found, 5 missing, 1 unparsed)", out)
        self.assertIn("40 line and forward entries (18 missing, 2 unparsed)", out)

        def rows(name, entry):
            with open(sd / "analysis" / name) as f:
                return {(r["run"], r["concept"], r[entry]): r for r in csv.DictReader(f)}

        answers = rows("answers.csv", "question")
        said = {k: (r["verdict"], r["where"]) for k, r in answers.items()}
        self.assertEqual([said[clean["run"], x, q] for q in "12"],
                         [("Found", "(FAQ, first answer)."), ("Not found", "")])
        self.assertEqual([said[varied["run"], x, q] for q in "12"], [
            ("Found", "index, Good questions names Xero."),
            ("Partly", "(Simple plans: $29 for 1 user; nothing for nine people).")])
        self.assertEqual([said[varied["run"], z, q][0] for q in "12"], ["Found", "Not found"])
        self.assertEqual([said[patchy["run"], y, q][0] for q in "12"], ["Partly", "Not found"])
        self.assertEqual([said[patchy["run"], x, q][0] for q in "12"], ["unparsed", "missing"])
        self.assertEqual(answers[patchy["run"], x, "1"]["raw"], f"{works} Yes, it says so in the FAQ.")
        self.assertEqual({(r["concept"], r["verdict"], r["complete"]) for r in answers.values()
                          if r["run"] == stopped["run"]}, {(x, "Not found", "0")})

        lines = rows("lines.csv", "entry")
        wrote = {k: (r["status"], r["text"], r["forward_to"], r["note"]) for k, r in lines.items()}
        self.assertEqual(wrote[clean["run"], x, "forward"], ("yes", "Have a look at this.", "my bookkeeper", ""))
        self.assertEqual(wrote[clean["run"], x, "not_believed"], ("none", "", "", ""))
        self.assertEqual(wrote[varied["run"], x, "keep"], ("quoted", "Know what every job made.", "", ""))
        self.assertEqual(wrote[varied["run"], x, "cut"],
                         ("quoted", "Set up in an afternoon", "", "(vague, I'd want a number)"))
        self.assertEqual(wrote[varied["run"], x, "forward"], ("maybe", "Worth a look?", "my bookkeeper", ""))
        self.assertEqual(wrote[varied["run"], z, "forward"],
                         ("yes", "Check the learning step.", "a client who has asked me about job costing", ""))
        self.assertEqual([wrote[patchy["run"], x, e][0] for e in ("keep", "cut", "not_believed", "forward")],
                         ["unparsed", "missing", "none", "unparsed"])
        self.assertEqual(lines[patchy["run"], x, "keep"]["raw"], '"Know your numbers." and "No more guessing."')

        # The analysis counts the three complete runs and leaves the one that was cut off out.
        run("analyze.py", sd)
        quant = self.quant(sd)

        def counted(tally):
            return {c: {k: n for k, n in tally[c].items() if n} for c in (x, y, z)}

        asked = {q["text"]: counted(q["concepts"]) for q in quant["answers"]["questions"]}
        self.assertEqual(asked[works], {x: {"found": 2, "unparsed": 1}, y: {"found": 1, "partly": 1, "missing": 1},
                                        z: {"found": 2, "missing": 1}})
        self.assertEqual(asked[costs], {x: {"partly": 1, "not_found": 1, "missing": 1},
                                        y: {"not_found": 2, "missing": 1}, z: {"not_found": 2, "missing": 1}})
        self.assertEqual(counted(quant["lines"]["forward"]), {
            x: {"yes": 1, "maybe": 1, "unparsed": 1}, y: {"yes": 1, "missing": 2}, z: {"yes": 2, "missing": 1}})
        self.assertEqual(quant["lines"]["recurring"], {y: [], z: [], x: [
            {"line": "Know what every job made.", "runs": 2, "keep": 2, "cut": 0, "not_believed": 1},
            {"line": "Set up in an afternoon.", "runs": 2, "keep": 0, "cut": 2, "not_believed": 0}]})
        md = sd.joinpath("analysis/quant.md").read_text()
        self.assertIn(f"| {x} | 2 | 0 | 0 | 0 | 1 |", md[md.index("## Find the answer"):md.index("## Forward test")])
        self.assertIn(f"| {x} | 1 | 0 | 1 | 0 | 1 |", md[md.index("## Forward test"):md.index("## Lines that recur")])

    def test_replicates_of_a_persona_on_one_model_are_compared_with_each_other(self):
        sd = self.study("spread", replicates=2)
        run("init_study.py", sd)
        plain_first = ({"01-plain": [9] * FACTORS, "02-story": [5] * FACTORS, "03-console": [7] * FACTORS},
                       ["01-plain", "03-console", "02-story"])
        story_first = ({"01-plain": [5] * FACTORS, "02-story": [9] * FACTORS, "03-console": [7] * FACTORS},
                       ["02-story", "03-console", "01-plain"])
        # One replicate differs from the seven other runs: only P01's pair on opus is apart.
        for r in json.loads(sd.joinpath("runs.json").read_text()):
            self.fill(r, *(plain_first if r["run"] == "P01-opus" else story_first), sd=sd)
        run("extract_scores.py", sd)
        run("analyze.py", sd)
        quant = self.quant(sd)
        pairs = {(d["persona"], d["model"]): d for d in quant["replicates"]["by_persona"]}
        self.assertEqual(sorted(pairs), [("P01", "fable"), ("P01", "opus"), ("P02", "fable"), ("P02", "opus")])
        apart = pairs.pop(("P01", "opus"))
        self.assertEqual((apart["replicates"], apart["same_top"]), ([1, 2], False))
        for figure, expected in (("spearman", -1), ("same_score", 1 / 3), ("mean_abs_diff", 8 / 3)):
            self.assertAlmostEqual(apart[figure], expected, msg=figure)
        self.assertEqual({(round(d["spearman"], 6), d["same_score"], d["mean_abs_diff"], d["same_top"])
                          for d in pairs.values()}, {(1, 1, 0, True)})
        by_model = quant["replicates"]["by_model"]
        self.assertEqual((by_model["opus"]["same_top"], by_model["fable"]["same_top"]), (1, 2))
        self.assertAlmostEqual(by_model["opus"]["mean_abs_diff"], 4 / 3)
        self.assertIn("## Replicate spread", sd.joinpath("analysis/quant.md").read_text())
        self.assertNotIn("variants", quant)  # no persona here is a variant

    def test_variant_is_shown_under_its_parent_with_its_difference_from_it(self):
        dana, sam = self.cfg["personas"]
        sd = self.study("variants", models=["opus"], personas=[
            dana, sam, {**dana, "id": "P03", "personality": "Blunt", "variant_of": "P01"}])
        run("init_study.py", sd)
        parent, other, variant = json.loads(sd.joinpath("runs.json").read_text())

        def order(r):
            return next(l for l in sd.joinpath(r["file"]).read_text().splitlines() if l.startswith("| Review order"))

        self.assertEqual(order(variant), order(parent))  # so that order is no part of the difference between them
        self.fill_all([parent, other], sd)
        self.fill(variant, {"01-plain": [5] * FACTORS, "02-story": [9] * FACTORS, "03-console": [7] * FACTORS},
                  ["02-story", "03-console", "01-plain"], sd=sd)
        run("extract_scores.py", sd)
        run("analyze.py", sd)
        quant = self.quant(sd)
        plain, story, console = (self.labels_for(c) for c in ("01-plain", "02-story", "03-console"))
        [pair] = quant["variants"]
        self.assertEqual((pair["variant"], pair["parent"], pair["differs_in"], pair["models"]),
                         ("P03", "P01", ["personality"], ["opus"]))
        self.assertEqual({c: pair["concepts"][c]["diff"] for c in (plain, story, console)},
                         {plain: -3, story: 4, console: 0})
        self.assertEqual(pair["top"], {"parent": plain, "variant": story})
        md = sd.joinpath("analysis/quant.md").read_text()
        matrix = md[md.index("## Persona x concept"):].splitlines()
        cells = {plain: "5.0 (-3.0)", story: "9.0 (+4.0)", console: "7.0 (+0.0)"}
        row = "| P03 Dana Kowalski (variant of P01) | " + " | ".join(cells[c] for c in sorted(cells)) + " |"
        self.assertEqual(matrix.index(row), next(i for i, line in enumerate(matrix) if line.startswith("| P01 ")) + 1)
        self.assertEqual(sorted(quant["persona_matrix"]), ["P01", "P02", "P03"])  # a persona of its own elsewhere
        self.assertNotIn("replicates", quant)  # no run here was repeated
        # A variant written only to test a trait is kept out of the headline, in a view of its own.
        self.assertIn("2 of 2 runs complete", run("analyze.py", sd, "--exclude-persona", "P03").stdout)
        headline = json.loads(sd.joinpath("analysis/quant-no-P03.json").read_text())
        self.assertEqual((sorted(headline["persona_matrix"]), headline["leaderboard"][0]["concept"]),
                         (["P01", "P02"], plain))
        self.assertNotIn("variants", headline)
        self.assertEqual(self.quant(sd), quant)


class InterviewRulesTest(unittest.TestCase):
    """The rules of an interview that are pure: text in, what a launcher makes of it out."""

    def test_interviewer_reply_is_read_by_one_grammar_and_every_failure_is_named(self):
        question = {"form": "question", "topic": "T2", "move": "anchor", "why": "A general claim.",
                    "say": "When did that last happen?", "reason": None}
        plain = "TOPIC: T2\nMOVE: anchor\nWHY: A general claim.\nSAY:\nWhen did that last happen?"
        usable = {
            "a question": (plain, question),
            "a question outside every topic": (plain.replace("T2", "open"), {**question, "topic": "open"}),
            "a closing question": (plain.replace("T2", "close"), {**question, "topic": "close"}),
            # Everything under SAY: is the participant's, whatever it looks like.
            "words of several lines": (plain + "\n\nMOVE: this is said too.\n", {
                **question, "say": "When did that last happen?\n\nMOVE: this is said too."}),
            "a reason that runs on to a second line": (
                plain.replace("A general claim.", "A general\n  claim."), question),
            "an end with its closing line": ("END: Both closing questions are answered.\nSAY:\nThanks.", {
                "form": "end", "topic": None, "move": None, "why": None, "say": "Thanks.",
                "reason": "Both closing questions are answered."}),
            "an end with no closing line": ("END: She ended the conversation.", {
                "form": "end", "topic": None, "move": None, "why": None, "say": None,
                "reason": "She ended the conversation."}),
            # The two things forgiven: one code fence around the whole reply, and blank space around it.
            "a code fence around the reply": (f"```\n{plain}\n```", question),
            "a code fence with a language word, and blank lines": (f"\n\n```text\n{plain}\n```\n\n", question),
            "blank space around the reply, to its left too": (
                "\r\n" + "".join(f"    {line}\r\n" for line in plain.split("\n")) + "  \r\n", question),
        }
        for name, (reply, read) in usable.items():
            with self.subTest(name):
                self.assertEqual(interview.parse_reply(reply, ["T1", "T2"]), {**read, "problems": []})

        unusable = {
            # Nothing else is forgiven: each of these is a reply the participant never sees.
            "a key in another case": (plain.replace("TOPIC:", "Topic:"), [
                ["format", "text before the first key"], ["missing", "TOPIC"]]),
            "markdown around a key": (plain.replace("MOVE:", "**MOVE:**"), [
                ["missing", "MOVE"], ["topic", "T2 **MOVE:** anchor"]]),
            "words on the SAY: line": (plain.replace("SAY:\n", "SAY: "), [["format", "words on the SAY: line"]]),
            "text before the first key": ("Here is my next question.\n\n" + plain, [
                ["format", "text before the first key"]]),
            "a code fence around a part of the reply": (plain.replace("SAY:\n", "SAY:\n```\n") + "\n```", [
                ["format", "a code fence inside the reply"]]),
            "a key twice": (plain.replace("MOVE:", "TOPIC: T1\nMOVE:"), [["format", "TOPIC twice"]]),
            "an end that is a question too": ("END: Done.\nTOPIC: close\nSAY:\nThanks.", [
                ["format", "END beside TOPIC"]]),
            "a field left out": (plain.replace("WHY: A general claim.\n", ""), [["missing", "WHY"]]),
            "a field with nothing in it": (plain.replace("A general claim.", ""), [["missing", "WHY"]]),
            "no SAY": ("TOPIC: T2\nMOVE: anchor\nWHY: A general claim.", [["missing", "SAY"]]),
            "nothing under SAY": ("TOPIC: T2\nMOVE: anchor\nWHY: A general claim.\nSAY:\n  \n", [["say", ""]]),
            "an end with no reason": ("END:\nSAY:\nThanks.", [["missing", "the reason after END"]]),
            "a topic that is not in this persona's guide": (plain.replace("T2", "T3"), [["topic", "T3"]]),
            "a topic id in another case": (plain.replace("T2", "t2"), [["topic", "t2"]]),
            "a move that is not one of the sixteen": (plain.replace("anchor", "probe"), [["move", "probe"]]),
            "no reply at all": ("", [["missing", "TOPIC, MOVE, WHY, SAY"]]),
            # Every problem is found in one pass, so that one repair can name them all.
            "several problems at once": ("Sure.\nTOPIC: T9\nMOVE: probe\nSAY:\n", [
                ["format", "text before the first key"], ["missing", "WHY"], ["topic", "T9"], ["move", "probe"],
                ["say", ""]]),
        }
        repairs = interview.notices()
        for name, (reply, problems) in unusable.items():
            with self.subTest(name):
                self.assertEqual(interview.parse_reply(reply, ["T1", "T2"])["problems"], problems)
                # What a failure is called is the key of the sentence that tells the interviewer of it.
                self.assertLessEqual({f"repair-{key}" for key, _ in problems}, set(repairs))

    def test_question_counts_for_the_topic_whose_opener_it_holds_whatever_its_label_says(self):
        openers = {"T1": "What took most of your time last week?", "T2": "Who decides what you \u201cbuy\u201d?",
                   "T3": "Walk me through the last order."}
        guide = {"turns": 6, "card": True, "topics": [{"id": t, "area": t, "goals": [], "turns": 8, "opener": o}
                                                     for t, o in openers.items()]}

        def recorded(label, say, asked=("T1",), answers=1):
            """The question record made of a reply labelled so, after one question for each topic of asked."""
            log = [{"t": "start", "at": 0, "v": 1, "kind": "interview", "run": "P01-opus"},
                   {"t": "card", "at": 0, "side": "participant", "attempt": 1, "text": "A card."}]
            for n, topic in enumerate(asked, start=1):
                log.append({"t": "question", "at": 0, "side": "interviewer", "attempt": n, "n": n, "topic": topic,
                            "move": "open", "why": "W.", "say": "Q?"})
                log += [{"t": "answer", "at": 0, "side": "participant", "attempt": n + 1, "n": n, "text": "A."}
                        ] * (n <= answers)
            [record] = interview.taken(interview.fold(log), guide, "interviewer", 9, {
                "reply": f"TOPIC: {label}\nMOVE: accept\nWHY: Moving on.\nSAY:\n{say}", "ending": None}, [], 1.0)
            return record["t"], record.get("topic"), record.get("labelled")

        cases = {
            # The mistake seen in real interviews: the next topic is opened under the label of the one it leaves.
            "the next topic's opener under the old label": (("T1", f"Fair enough. {openers['T2']}"), ("T2", "T1")),
            "the same in other case, spacing and quotation marks": (
                ("T1", 'Moving on:  who decides\nwhat you "buy"?'), ("T2", "T1")),
            "an opener under its own label": (("T2", openers["T2"]), ("T2", None)),
            "an opener under open": (("open", openers["T2"]), ("T2", "open")),
            "an opener under close, which is then no close": (("close", openers["T3"]), ("T3", "close")),
            # Only the opener of a topic that no question has carried: T1 was opened by the first question.
            "the opener of a topic already opened": (("T2", openers["T1"]), ("T2", None)),
            "no opener, so the label stands": (("T1", "When did that last happen?"), ("T1", None)),
            "an opener that is not word for word": (("T1", "Who decides what to buy?"), ("T1", None)),
            # Word for word is as words of its own: an opener whose first or last word is a part of a longer word
            # of the question is not held.
            "an opener whose last word begins a longer one": (
                ("T1", "Walk me through the last ordering mistake?"), ("T1", None)),
            "an opener whose first word ends a longer one": (
                ("T1", "On the catwalk me through the last order."), ("T1", None)),
            # Two unopened topics' openers in one reply: the one its label names, else the first in its words.
            "two openers, and the label names one": (("T3", f"{openers['T2']} {openers['T3']}"), ("T3", None)),
            "two openers under another label": (("T1", f"{openers['T3']} {openers['T2']}"), ("T3", "T1")),
        }
        for name, (reply, (topic, labelled)) in cases.items():
            with self.subTest(name):
                self.assertEqual(recorded(*reply), ("question", topic, labelled))
        # The gate of the last exchange reads the label, as the interviewer is told to write it: a reply that
        # is not labelled close is sent back there, and one that is passes, whatever its words open.
        last = dict(asked=("T1", "T1", "T1", "T1", "T1"), answers=5)
        self.assertEqual((recorded("T2", openers["T2"], **last), recorded("close", openers["T2"], **last)),
                         (("rejected", None, None), ("question", "T2", "close")))


# The options each runner passes on every launch, written out: they are its contract with the CLI.
CLAUDE_ISOLATION = ["--safe-mode", "--restricted", "--strict-mcp-config", "--disable-slash-commands",
                    "--settings", '{"includeGitInstructions":false}']
CLAUDE_OUTPUT = ["--permission-mode", "dontAsk", "--output-format", "stream-json", "--verbose"]
CLAUDE_FILES = "Read,Write,Edit,Glob,Grep"
CODEX_OPTIONS = ["exec", "--json", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules",
                 "-c", "project_doc_max_bytes=0", "-c", "skills.include_instructions=false",
                 "-c", "approval_policy=never", "--disable", "plugins", "--disable", "tool_suggest",
                 "--disable", "apps", "-c", 'web_search="disabled"', "--disable", "image_generation",
                 "-s", "workspace-write"]
# With no tools, as each side of an interview runs: Claude Code has a switch for it, and Codex only one for
# each feature that gives a session a tool to read, run or reach something with.
CLAUDE_NO_TOOLS = ["--tools", ""]
CODEX_NO_TOOLS = ["--disable", "shell_tool", "--disable", "unified_exec", "--disable", "view_image",
                  "--disable", "multi_agent", "--disable", "sleep_tool", "--disable", "browser_use",
                  "--disable", "computer_use", "--disable", "goals"]
# With browsing: one allow rule for each agent-browser command a panellist may run, and for Codex a way
# out of its sandbox to the session's socket, with no temporary directory to start a session of its own in.
CLAUDE_BROWSER = ",".join(
    [f"Bash(agent-browser {c}:*)" for c in (
        "open", "back", "forward", "reload", "snapshot", "screenshot", "click", "dblclick", "fill", "type", "press",
        "keyboard", "select", "check", "uncheck", "hover", "focus", "scroll", "scrollintoview", "wait", "dialog")]
    + ["Bash(agent-browser get url)", "Bash(agent-browser get title)"])
CODEX_BROWSER = ["-c", "sandbox_workspace_write.network_access=true",
                 "-c", "sandbox_workspace_write.exclude_slash_tmp=true",
                 "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true"]
PI_ISOLATION = ["-nc", "-ns", "-ne", "-np", "--no-themes", "--no-mcp", "--no-approve",
                "--system-prompt", "", "--append-system-prompt", ""]
PI_GUARD = ["-e", str(SCRIPTS / "runners/pi_guard.ts"), "--panel-guard"]  # then what the guard allows
PI_FILES = "read,write,edit,grep,find,ls"
PI_MODEL = "openai-codex/gpt-6-luna"  # a row of the fake's model listing, as of the real one
PI_RECORDED = "785dfece-625f-4319-b88f-a6c95bbfc39f"  # the session of the pi/*.jsonl recordings
SESSION = "937a3347-a2b1-41c3-a9d3-8be11344d2a6"
RUN = {"run": "P01-opusHigh", "model": "opus", "effort": "high", "role": "panellist", "browse": True}
RUNS = {"pi": {**RUN, "model": PI_MODEL}}  # the same run on a runner whose models are named differently
BARE = {"run": "analyst-1", "model": None, "effort": None, "role": "analyst"}
TALKER = {"run": "P01-opus", "model": "opus", "effort": None, "role": "panellist", "tools": "none"}
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
               if not k.startswith(("CLAUDE", "ANTHROPIC", "CODEX", "OPENAI", "PI_", "AI_AGENT", "FAKE_"))}
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
        return runner.parse_result(r.stdout, r.stderr, r.returncode, command["session_id"])

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def session_file(self, thread_id):
        d = self.tmp / "codex-home/sessions/2026/10/12"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"rollout-2026-10-12T20-22-31-{thread_id}.jsonl").write_text(fakes.recorded("codex", "session-file"))

    def pi_session(self, session_id, entries):
        """Put a session file where Pi keeps the sessions of a working directory. Returns its path."""
        d = self.tmp / "home/.pi/agent/sessions/--study-panel--"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"2026-10-12T19-49-16-390Z_{session_id}.jsonl").write_text(entries.replace(PI_RECORDED, session_id))
        return d / f"2026-10-12T19-49-16-390Z_{session_id}.jsonl"

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
        self.assertEqual(runners.names(), ["claude", "codex", "echo", "half", "pi"])
        self.assertEqual(runners.get("echo").capabilities(), {"effort_levels": []})
        note = runners.check_effort({"runner": "echo", "effort": "high"})
        self.assertEqual((note["effort"], note["error"]), (None, None))
        self.assertIn("ignored", note["note"])
        refusals = {"half": "launch_command", "nope": "claude, codex, echo, half, pi", "_shared": "Unknown"}
        for name, message in refusals.items():
            with self.subTest(name), self.assertRaises(SystemExit) as refused:
                runners.get(name)
            self.assertIn(message, str(refused.exception))

    def test_runner_commands_for_a_run(self):
        panel = str(self.workdir)
        left = {"minutes": 4, "budget_usd": 0.75}
        browsing = ["--tools", CLAUDE_FILES + ",Bash", "--allowed-tools", CLAUDE_FILES + "," + CLAUDE_BROWSER]
        files_only = ["--tools", CLAUDE_FILES, "--allowed-tools", CLAUDE_FILES]
        # Pi's own folder for the sessions of this working directory, whatever its settings say.
        pi_sessions = str(self.tmp / "home/.pi/agent/sessions"
                          / f"--{os.path.realpath(self.workdir).strip('/').replace('/', '-')}--")
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
            ("claude", "no tools", False): (TALKER, LIMITS, [
                "-p", "--session-id", "<new>", "--model", "opus", "--max-budget-usd", "2",
                *CLAUDE_ISOLATION, *CLAUDE_NO_TOOLS, *CLAUDE_OUTPUT]),
            ("claude", "resumed, with no tools again", True): (TALKER, left, [
                "-p", "--resume", SESSION, "--model", "opus", "--max-budget-usd", "0.75",
                *CLAUDE_ISOLATION, *CLAUDE_NO_TOOLS, *CLAUDE_OUTPUT]),
            ("codex", "model, effort, browsing", False): (RUN, LIMITS, [
                *CODEX_OPTIONS, *CODEX_BROWSER, "-C", panel, "-m", "opus", "-c", "model_reasoning_effort=high", "-"]),
            ("codex", "resumed, options before the word resume", True): (RUN, left, [
                *CODEX_OPTIONS, *CODEX_BROWSER, "-C", panel, "-m", "opus", "-c", "model_reasoning_effort=high",
                "resume", SESSION, "-"]),
            ("codex", "default model, no effort, no browsing", False): (
                BARE, LIMITS, [*CODEX_OPTIONS, "-C", panel, "-"]),
            ("codex", "no tools", False): (TALKER, LIMITS, [
                *CODEX_OPTIONS, *CODEX_NO_TOOLS, "-C", panel, "-m", "opus", "-"]),
            ("codex", "resumed, with no tools again", True): (TALKER, left, [
                *CODEX_OPTIONS, *CODEX_NO_TOOLS, "-C", panel, "-m", "opus", "resume", SESSION, "-"]),
            ("pi", "model, effort, browsing", False): (RUNS["pi"], LIMITS, [
                "-p", "--mode", "text", "--session-id", "<new>", "--session-dir", pi_sessions,
                "--provider", "openai-codex", "--model", PI_MODEL, "--thinking", "high",
                *PI_ISOLATION, *PI_GUARD, "browse", "--tools", PI_FILES + ",bash"]),
            ("pi", "resumed by the flag that fails when the session is gone", True): (RUNS["pi"], left, [
                "-p", "--mode", "text", "--session", SESSION, "--session-dir", pi_sessions,
                "--provider", "openai-codex", "--model", PI_MODEL, "--thinking", "high",
                *PI_ISOLATION, *PI_GUARD, "browse", "--tools", PI_FILES + ",bash"]),
            ("pi", "no effort, no browsing", False): ({**BARE, "model": PI_MODEL}, LIMITS, [
                "-p", "--mode", "text", "--session-id", "<new>", "--session-dir", pi_sessions,
                "--provider", "openai-codex", "--model", PI_MODEL,
                *PI_ISOLATION, *PI_GUARD, "files", "--tools", PI_FILES]),
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
        for name in ("claude", "codex"):  # a browser is a tool: a run is never given one because it asked for both
            with self.subTest(f"{name}: no tools and browsing"), self.assertRaises(ValueError):
                runners.get(name).launch_command({**TALKER, "browse": True}, PROMPT, self.workdir, LIMITS)

    def test_runner_refuses_an_effort_or_budget_it_cannot_launch(self):
        for name in ("claude", "codex", "pi"):
            with self.subTest(name):
                entry = RUNS.get(name, RUN)
                self.assertEqual(runners.check_effort({"runner": name, "effort": "high"}),
                                 {"effort": "high", "error": None, "note": None})
                self.assertIn('"ultra"', runners.check_effort({"runner": name, "effort": "ultra"})["error"])
                with self.assertRaises(ValueError):
                    runners.get(name).launch_command({**entry, "effort": "ultra"}, PROMPT, self.workdir, LIMITS)
                with self.assertRaises(ValueError):
                    runners.get(name).resume_command(entry, "--last", PROMPT, self.workdir, LIMITS)
        with self.assertRaises(ValueError):
            runners.get("claude").resume_command(RUN, SESSION, PROMPT, self.workdir, {"minutes": 1, "budget_usd": 0})
        # Pi matches a model name loosely and falls back to the user's default model, so its
        # runner launches nothing but an exact row of the listing.
        for model in (None, "gpt-6-luna", "openai-codex/luna"):
            with self.subTest(f"pi: model {model}"), self.assertRaises(ValueError):
                runners.get("pi").launch_command({**RUNS["pi"], "model": model}, PROMPT, self.workdir, LIMITS)
        # Pi also ignores case and drops a leading "<provider>/" from a model name. A listed row it would
        # take for another listed row is refused at the plan and at launch, and both rows are named.
        taken_for = {"custom/custom/foo": "custom/foo", "custom/bar": "custom/Bar"}  # model: the row Pi would pick
        for model, other in taken_for.items():
            with self.subTest(f"pi: model {model}"):
                status = runners.get("pi").model_status({"model": model})
                self.assertEqual((status["known"], f'lists "{model}"' in status["message"],
                                  f'the row "{other}"' in status["message"]), (False, True, True), status)
                with self.assertRaisesRegex(ValueError, f'the row "{other}"'):
                    runners.get("pi").launch_command({**RUNS["pi"], "model": model}, PROMPT, self.workdir, LIMITS)
        plain = runners.get("pi").launch_command({**RUNS["pi"], "model": "custom/foo"}, PROMPT, self.workdir, LIMITS)
        self.assertIn(["--provider", "custom", "--model", "custom/foo"],  # the row "foo" resolves to itself
                      [plain["argv"][i:i + 4] for i in range(len(plain["argv"]))])

    def test_runner_command_runs_and_resumes_through_the_cli(self):
        self.steer(CLAUDECODE="1", CLAUDE_CODE_ENTRYPOINT="claude-desktop", CLAUDE_CODE_SESSION_ID="host",
                   CLAUDE_EFFORT="max", CLAUDE_AGENT_SDK_VERSION="1", AI_AGENT="host",
                   ANTHROPIC_BASE_URL="https://api.example.test", CLAUDE_CODE_USE_BEDROCK="1")
        used = {}
        for name in ("claude", "codex", "pi"):
            with self.subTest(name):
                runner, entry = runners.get(name), RUNS.get(name, RUN)
                command = runner.launch_command(entry, PROMPT, self.workdir, LIMITS)
                first = self.invoke(runner, command)
                self.assertEqual((first["outcome"], first["message"]), ("ok", ""))
                self.assertEqual(first["session_id"], command["session_id"] or first["session_id"])
                again = runner.resume_command(entry, first["session_id"], "Carry on.", self.workdir, LIMITS)
                second = self.invoke(runner, again)
                self.assertEqual((second["outcome"], second["session_id"]), ("ok", first["session_id"]))
                seen = [c for c in self.calls() if c["cli"] == name and c["stdin"] is not None]
                self.assertEqual([(c["stdin"], c["model_call"]) for c in seen], [(PROMPT, True), ("Carry on.", True)])
                used[name] = [(r["reply"], r["usage"]["input_tokens"], r["usage"]["scope"]) for r in (first, second)]
        # Pi prints the reply alone, and its figures are read from the session file the run left:
        # the launch's two requests, then the same again with the resume's one.
        self.assertEqual(used["pi"], [("Reviewed 3 concepts. Ranking: B, A, C.", 2967, "session"),
                                      ("OK", 4503, "session")])
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
        now = 1_800_000_000  # Pi says how long a limit lasts, not when it lifts
        pi_ok, pi_resumed = (fakes.recorded("pi", name).splitlines(keepends=True) for name in ("ok", "resume"))
        pi_ids = {what: SESSION[:-1] + str(i) for i, what in enumerate(("ok", "limit", "refused", "killed"))}
        self.pi_session(pi_ids["ok"], "".join(pi_ok))
        self.pi_session(pi_ids["limit"], "".join(pi_ok + pi_resumed[:1]) + fakes.recorded("pi", "usage-limit.inferred"))
        self.pi_session(pi_ids["refused"], "".join(pi_ok[:5]) + fakes.recorded("pi", "error"))
        self.pi_session(pi_ids["killed"], "".join(pi_ok[:-1]) + cut)  # the last request never came back
        pi_reply, pi_limit = "Reviewed 3 concepts. Ranking: B, A, C.", (
            "You have hit your ChatGPT usage limit (plus plan). Try again in ~42 min.")
        pi_created = (f"Warning: No project session found with id '{SESSION}'; creating a new session with "
                      "that id.\n")
        pi_refused = ('Warning: Model "zz-none" not found for provider "openai-codex". Using custom model id.\n'
                      "Codex error: The 'zz-none' model is not supported when using Codex with a ChatGPT account.\n")
        none = {"input_tokens": None, "output_tokens": None, "cached_tokens": None, "cost_usd": None}
        # What the real CLIs printed in a sandboxed shell on 13 October 2026: Claude Code with no network, and
        # Codex inside another Codex sandbox, where it cannot build its own.
        unreachable = "API Error: Can't reach the API server \u2014 check your internet or DNS (EAI_AGAIN)"
        no_sandbox = ("error building bubblewrap command: app-server socket directory must be a user-owned "
                      "directory with mode 0700")
        kept = self.tmp / "claude-home/projects/-study-panel/1bb4f919-145f-470d-a5b8-97f90a6a8095.jsonl"
        kept.parent.mkdir(parents=True)
        kept.write_text("{}\n")  # the transcript of claude/ok: the other recorded sessions left none
        cases = [  # runner, what, stdout, stderr, exit code, expected fields, expected usage figures
            ("claude", "ok", fakes.recorded("claude", "ok"), "", 0,
             {"outcome": "ok", "session_id": "1bb4f919-145f-470d-a5b8-97f90a6a8095", "message": "",
              "reply": "Reviewed 3 concepts. Ranking: B, A, C.", "reset_at": None, "session_saved": True,
              "cannot_run": ""},
             {"input_tokens": 2956, "output_tokens": 597, "cached_tokens": 2234, "cost_usd": 0.00046504,
              "duration_s": 3.441, "scope": "session"}),
            ("claude", "usage limit", fakes.recorded("claude", "usage-limit.inferred"), "", 1,
             {"outcome": "usage_limit", "reset_at": 1789377600, "reply": None,
              "message": "You've hit your session limit · resets 3:30am (Australia/Brisbane)"}, none),
            ("claude", "budget reached, in a session that left no transcript", fakes.recorded("claude", "budget"),
             "", 1,
             {"outcome": "budget", "reply": None, "message": "Reached maximum budget ($0.001)",
              "session_saved": False},
             {"input_tokens": 7179, "output_tokens": 151, "cached_tokens": 0, "cost_usd": 0.0015111}),
            ("claude", "error that calls itself a success", fakes.recorded("claude", "error"), "", 1,
             {"outcome": "error", "reply": None, "reset_at": None, "message": "Not logged in · Please run /login",
              "cannot_run": ""}, none),
            ("claude", "provider out of reach after its own ten retries", fakes.recorded("claude", "unreachable"), "",
             1, {"outcome": "error", "reply": None, "message": unreachable,
                 "cannot_run": f"it could not reach its provider ({unreachable})"}, none),
            ("claude", "killed part-way", fakes.recorded("claude", "killed") + cut, "", 143,
             {"outcome": "error", "session_id": "c3a8c385-cb68-47a7-bd67-468f6474c8a3", "reply": None,
              "message": "claude ended without a result (exit code 143)", "session_lost": False},
             {**none, "duration_s": None}),
            ("claude", "resume of a session that is gone", "", f"No conversation found with session ID: {SESSION}\n",
             1, {"outcome": "error", "session_id": None, "session_lost": True,
                 "message": f"No conversation found with session ID: {SESSION}"}, none),
            ("codex", "ok", fakes.recorded("codex", "ok"), "", 0,  # one shell command, which ran
             {"outcome": "ok", "session_id": "01a12fa7-d29f-7d11-8724-e3d666a19ca3", "message": "",
              "reply": "codename=NONE; skills=0; agents=yes", "reset_at": None, "cannot_run": ""},
             {"input_tokens": 82346, "output_tokens": 297, "cached_tokens": 67968, "cost_usd": None,
              "duration_s": None, "scope": "session"}),
            ("codex", "a turn that ended well with every shell command refused a sandbox",
             fakes.recorded("codex", "nested"), "", 0,
             {"outcome": "ok", "session_id": "01a13362-adad-79d1-bdaa-e44992d41d04", "session_saved": None,
              "cannot_run": f"it could not build its sandbox ({no_sandbox})"},
             {"input_tokens": 80423, "output_tokens": 238}),
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
            # Pi prints the reply and nothing else, so each case has the session file its process left,
            # found by the session id the launcher passes back (the last item).
            ("pi", "ok", f"{pi_reply}\n", pi_created, 0,
             {"outcome": "ok", "session_id": pi_ids["ok"], "message": "", "reply": pi_reply, "reset_at": None,
              "session_saved": True},
             {"input_tokens": 2967, "output_tokens": 43, "cached_tokens": 0, "cost_usd": 0.0001594 + 0.0001588,
              "duration_s": None, "scope": "session"}, pi_ids["ok"]),
            ("pi", "a reply from a process that left no session file (inferred)", f"{pi_reply}\n", pi_created, 0,
             {"outcome": "ok", "session_id": None, "reply": pi_reply, "session_saved": False}, none, SESSION),
            ("pi", "usage limit met by a resume (inferred text)", "", f"{pi_limit}\n", 1,
             {"outcome": "usage_limit", "reset_at": now + 42 * 60, "reply": None, "message": pi_limit},
             {"input_tokens": 2967, "output_tokens": 43}, pi_ids["limit"]),
            ("pi", "request refused by the API", "", pi_created + pi_refused, 1,
             {"outcome": "error", "session_id": pi_ids["refused"], "reply": None, "reset_at": None,
              "message": "Codex error: The 'zz-none' model is not supported when using Codex with a ChatGPT account."},
             none, pi_ids["refused"]),
            ("pi", "killed part-way", "", pi_created, 143,
             {"outcome": "error", "session_id": pi_ids["killed"], "reply": None, "session_lost": False,
              "message": "pi ended before finishing its turn (exit code 143)"},
             {"input_tokens": 1464, "output_tokens": 26, "cost_usd": 0.0001594}, pi_ids["killed"]),
            ("pi", "resume of a session that is gone", "", f"No session found matching '{SESSION}'\n", 1,
             {"outcome": "error", "session_id": None, "session_lost": True,
              "message": f"No session found matching '{SESSION}'"}, none, SESSION),
            ("pi", "stopped before its session, with no login for the provider", "",
             "No API key found for openrouter.\n\nUse /login to log into a provider via OAuth or API key.\n", 1,
             {"outcome": "error", "session_id": None, "session_lost": False,
              "message": "No API key found for openrouter."}, none, SESSION),
            ("pi", "resumed from another directory, which exits 0 without a turn",
             "Session found in different project: /study/panel\nAborted.\n",
             "Fork this session into current directory? [y/N] ", 0,
             {"outcome": "error", "reply": None, "session_lost": False,
              "message": "Session found in different project: /study/panel, so pi asked whether to fork it "
                         "and stopped"}, {}, pi_ids["ok"]),
            ("pi", "no output at all", None, None, None, {"outcome": "error", "session_id": None}, none),
        ]
        for name, what, stdout, stderr, code, fields, figures, *session in cases:
            with self.subTest(f"{name}: {what}"), mock.patch("time.time", return_value=now):
                parsed = runners.get(name).parse_result(stdout, stderr, code, *session)
                self.assertEqual(sorted(parsed), ["cannot_run", "message", "outcome", "reply", "reset_at",
                                                  "session_id", "session_lost", "session_saved", "usage"])
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
        cases = {"claude": ("--restricted", "2.1.296", "Not logged in"),  # an option, the version, signed out
                 "codex": ("--ignore-rules", "codex-cli 0.162.1", "Not logged in"),
                 "pi": ("--no-approve", "1.1.0", "No models available")}
        for name, (option, version, no_login) in cases.items():
            with self.subTest(name):
                runner, mode = runners.get(name), f"FAKE_{name.upper()}"
                ready = runner.check()
                self.assertTrue(ready["ok"], ready)
                self.assertIn(version, ready["message"])
                self.assertNotIn("example.com", ready["message"])  # the account's email is not passed on
                with mock.patch.dict(os.environ, {mode: "signed_out"}):
                    signed_out = runner.check()
                self.assertEqual((signed_out["ok"], no_login in signed_out["message"]), (False, True), signed_out)
                with mock.patch.dict(os.environ, {mode: f"no_flag:{option}"}):
                    changed = runner.check()
                self.assertEqual((changed["ok"], option in changed["message"]), (False, True), changed)
                self.assertFalse([c for c in self.calls() if c["model_call"]])
                with mock.patch.dict(os.environ, {"PATH": str(self.tmp / "empty")}):
                    missing = runner.check()
                self.assertEqual((missing["ok"], name in missing["message"]), (False, True), missing)
        with mock.patch.dict(os.environ, {"FAKE_CODEX": "warns"}):  # a sandboxed CLI warns before it answers
            self.assertEqual(runners.get("codex").check()["message"], "codex-cli 0.162.1, Logged in using ChatGPT")
        # Pi has no sandbox of its own: a guard extension that does not load must stop its runs.
        with mock.patch.dict(os.environ, {"FAKE_PI": "no_guard"}):
            unguarded = runners.get("pi").check()
        self.assertEqual((unguarded["ok"], "Failed to load extension" in unguarded["message"]), (False, True),
                         unguarded)

    def test_runner_says_what_its_cli_cannot_do_from_a_sandboxed_shell_without_calling_a_model(self):
        if os.geteuid() == 0:
            self.skipTest("root can write to a read-only directory")
        # Where each harness keeps its sessions: none is there yet, so each would be made under self.tmp. Codex
        # keeps them in a folder of its home, and either can be the one that cannot be written. With each is a
        # file to put where a folder belongs: at the folder's own name, or for Pi at a folder on the way to it.
        homes = {"claude": [(self.tmp / "claude-home/projects", self.tmp / "claude-home/projects")],
                 "codex": [(self.tmp / "codex-home", self.tmp / "codex-home"),
                           (self.tmp / "codex-home/sessions", self.tmp / "codex-home/sessions")],
                 "pi": [(self.tmp / "home/.pi/agent/sessions", self.tmp / "home/.pi")]}
        for name, folders in homes.items():
            runner = runners.get(name)
            for sessions, blocked in folders:
                with self.subTest(name, sessions=sessions.name):
                    self.assertEqual(runner.shell_check(), {"ok": True, "message": ""})
                    blocked.parent.mkdir(parents=True, exist_ok=True)
                    blocked.write_text("")  # no folder can be made there, though the one above it can be written
                    refused = runner.shell_check()
                    blocked.unlink()
                    self.assertEqual((refused["ok"], refused["message"]), (
                        False, f"cannot write to {sessions}, where it keeps its sessions (Not a directory)"))
                    sessions.mkdir(parents=True)
                    sessions.chmod(0o555)  # what a sandbox that keeps the home directory read-only leaves of it
                    self.addCleanup(sessions.chmod, 0o755)
                    refused = runner.shell_check()
                    self.assertEqual((refused["ok"], refused["message"]), (
                        False, f"cannot write to {sessions}, where it keeps its sessions (Permission denied)"))
                    self.assertEqual(list(sessions.iterdir()), [])  # the test of it left nothing there
                    sessions.chmod(0o755)
        # Inside another Codex sandbox the CLI cannot build its own: its words, from a command that calls no model.
        with mock.patch.dict(os.environ, {"FAKE_CODEX": "nested"}):
            nested = runners.get("codex").shell_check()
        self.assertEqual((nested["ok"], nested["message"]), (
            False, "cannot build its own sandbox (error building bubblewrap command: app-server socket directory "
                   "must be a user-owned directory with mode 0700)"))
        self.assertFalse([c for c in self.calls() if c["model_call"]])

    def test_runner_purge_commands_name_one_session(self):
        claude, codex, pi = (runners.get(name) for name in ("claude", "codex", "pi"))
        transcript = self.tmp / "claude-home/projects/-study-panel" / f"{SESSION}.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text("{}\n")
        self.assertEqual(claude.purge_command(SESSION, self.workdir),
                         ["rm", "-rf", "--", str(transcript), str(transcript.with_suffix(""))])
        self.assertIsNone(claude.purge_command("1bb4f919-145f-470d-a5b8-97f90a6a8095", self.workdir))  # no transcript
        self.assertEqual(codex.purge_command(SESSION, self.workdir), ["codex", "delete", "--force", SESSION])
        kept = self.pi_session(SESSION, fakes.recorded("pi", "ok"))
        self.assertEqual(pi.purge_command(SESSION, self.workdir), ["rm", "-f", "--", str(kept)])
        self.assertIsNone(pi.purge_command("1bb4f919-145f-470d-a5b8-97f90a6a8095", self.workdir))  # no session file
        for runner in (claude, codex, pi):
            self.assertIsNone(runner.purge_command("../../projects", self.workdir))


def most_at_once(steps):
    """The peak of a running count, from its +1 and -1 steps in order."""
    peak = count = 0
    for step in steps:
        count += step
        peak = max(peak, count)
    return peak


class BrowserSessionTest(unittest.TestCase):
    """browser_session.py stop run as a subprocess, on records written by hand. PATH holds the
    fake agent-browser, whose `close` signals whatever a pid file names, as the real one can."""

    def test_stop_signals_and_removes_only_what_is_proven_to_be_its_sessions(self):
        base = Path(tempfile.mkdtemp(prefix="persona-panel-browser-"))
        self.addCleanup(shutil.rmtree, base, True)
        fakes.install(base, "agent-browser")
        bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])  # not of any session
        self.addCleanup(bystander.wait)
        self.addCleanup(bystander.kill)
        unrelated = base / "unrelated.txt"
        unrelated.write_text("the user's own")
        cases = {  # what is wrong: (the record's changes, a token in the socket directory, what the record is,
            #                       exit code, what stop says, the socket directory and the policy are still there)
            "the daemon on record has gone, and another process has its id": (
                {}, True, "file", 0, "no browser session was running", False),
            "the record names another file as its policy": (
                {"policy": str(unrelated)}, True, "file", 2, "cannot be trusted, so nothing was stopped or removed: "
                ".* is not as \"start\" wrote it: its policy", True),
            "the record is a symbolic link": (
                {}, True, "link", 2, "cannot be trusted, so nothing was stopped or removed: .* is a symbolic link",
                True),
            "the record is a FIFO, which no one ever writes to": (
                {}, True, "fifo", 2, "cannot be trusted, so nothing was stopped or removed: .* is not a regular file",
                True),
            "the socket directory does not hold the session's token": (
                {}, False, "file", 1, "Left in place: .*: it does not hold this session's token", True),
        }
        for i, (name, (changed, token, kind, code, says, stays)) in enumerate(cases.items()):
            with self.subTest(name):
                log = base / f"logs-{i}" / "P01-opus.1"
                log.parent.mkdir()
                record, policy = Path(f"{log}.browser"), Path(f"{log}.policy")
                sockets = Path(tempfile.gettempdir()) / f"pp-{secrets.token_hex(4)}"
                sockets.mkdir(mode=0o700)
                self.addCleanup(shutil.rmtree, sockets, True)
                # As a start left them, with the daemon killed since and its id given to the bystander: the
                # pid file still names it, and the record holds the start identity of the daemon that was.
                (sockets / "P01-opus.pid").write_text(str(bystander.pid))
                (sockets / ".pp-session").write_text("0" * 32 if token else "another session's")
                policy.write_text(json.dumps({"default": "deny", "allow": []}))
                written = json.dumps({
                    "session": "P01-opus", "socket_dir": str(sockets), "policy": str(policy), "token": "0" * 32,
                    "cwd": str(base), "started": 1.0, "launching": False, "daemon": [bystander.pid, "another's start"],
                    "browser": None, "profile": None, "stopped": None, **changed})
                kept = base / f"record-{i}.json"
                if kind == "fifo":
                    os.mkfifo(record)
                else:
                    (kept if kind == "link" else record).write_text(written)
                if kind == "link":
                    record.symlink_to(kept)
                try:  # a stop that waits for a record, as an open of a FIFO to read it does, never ends
                    r = subprocess.run(
                        [sys.executable, str(SCRIPTS / "browser_session.py"), "stop", "--log", str(log)],
                        env={**os.environ, "PATH": f"{base}{os.pathsep}{os.environ['PATH']}"},
                        capture_output=True, text=True, timeout=60)
                except subprocess.TimeoutExpired:
                    self.fail("stop did not end within 60 s")
                self.assertEqual(r.returncode, code, r.stdout + r.stderr)
                self.assertRegex(r.stdout + r.stderr, says)
                self.assertIsNone(bystander.poll())
                self.assertEqual(unrelated.read_text(), "the user's own")
                self.assertEqual(((sockets / "P01-opus.pid").exists(), policy.exists()), (stays, stays))
                if kind == "fifo":  # refused: still the FIFO it was
                    self.assertTrue(stat.S_ISFIFO(os.lstat(record).st_mode))
                elif code == 2:  # refused: the record is as it was, and so is what a link to it points at
                    self.assertEqual((kept if kind == "link" else record).read_text(), written)


# What every refusal that a sandboxed shell tool can cause ends with: both ways out, in one sentence.
SANDBOX_HINT = ("If your shell tool is sandboxed, ask your harness to run this command outside its sandbox, or run "
                "launch.py from a terminal.")
NO_SANDBOX = ("error building bubblewrap command: app-server socket directory must be a user-owned directory with "
              "mode 0700")  # what codex-cli 0.162.1 says inside another Codex sandbox


class LauncherTest(unittest.TestCase):
    """launch.py run as a subprocess, with the fake CLIs playing whole runs from a plan (see
    persona_panel_fakes/panellist.py). PATH holds the fakes and nothing else, so no real CLI
    can be reached. Two personas on two model entries give P01-opus, P01-cx, P02-opus, P02-cx.
    The analyst and writer jobs are analyst-1, analyst-2 and writer."""

    CLAUDE = {"key": "opus", "runner": "claude", "model": "opus"}
    CODEX = {"key": "cx", "runner": "codex"}
    PI = {"key": "local", "runner": "pi", "model": PI_MODEL}
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
        # The browser sessions a failed test left: each fake daemon names its socket directory in its command.
        used = {x["env"].get("AGENT_BROWSER_SOCKET_DIR") for x in self.logged() if x.get("cli") == "agent-browser"}
        for e in self.events("open hung"):  # an `open` that a test left hanging
            try:
                os.kill(e["pid"], signal.SIGKILL)
            except OSError:
                pass
        for sockets in used - {None}:
            for pid_file in Path(sockets).glob("*.pid"):
                r = subprocess.run(["ps", "-o", "command=", "-p", pid_file.read_text()], capture_output=True, text=True)
                if sockets in r.stdout:
                    os.kill(int(pid_file.read_text()), signal.SIGKILL)
            shutil.rmtree(sockets, True)

    def study(self, plan=None, personas=2, models=None, name="study", **settings):
        """Scaffold a study, with the text of each site page standing in for its capture, and set the
        plan the fakes follow. Becomes self.sd."""
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
        for page in [*self.sd.glob("panel/sites/concept-*/*.html"), *self.sd.glob("sites/concept-*/*.html")]:
            captured = self.sd / "panel/materials" / page.parent.name / page.stem
            captured.mkdir(parents=True)
            (captured / "page-text.txt").write_text(page.stem)
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

    def logged(self):
        """Every line the fake CLIs have logged, in order. What follows the last line break is a line a
        fake is still writing, and is left for the next look."""
        return [json.loads(line) for line in (self.log.read_text().split("\n")[:-1] if self.log.exists() else [])]

    def events(self, kind):
        return [e for e in self.logged() if e.get("event") == kind]

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

    def browser_sessions(self):
        """The record of the browser session of each run's attempt, logs/<run id>.<attempt>.browser."""
        return {p.name.split(".")[0]: json.loads(p.read_text()) for p in sorted(self.sd.glob("logs/*.browser"))}

    def left_of(self, record):
        """What is still there of a browser session: its socket directory, its policy file."""
        return [name for name in ("socket_dir", "policy") if os.path.exists(record[name])]

    def holding(self, how):
        """A process that holds the study's lock as flock gives it, LOCK_EX or LOCK_SH, and writes
        nothing: the lock file goes on naming whoever it named. let_go() ends it."""
        held = subprocess.Popen(
            [sys.executable, "-c", "import fcntl, os, sys\nfd = os.open(sys.argv[1], os.O_RDONLY)\n"
             "fcntl.flock(fd, getattr(fcntl, sys.argv[2]))\nprint('held', flush=True)\nsys.stdin.read()\n",
             str(self.sd / ".launch.lock"), how], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.background.append(held)
        self.assertEqual(held.stdout.readline(), "held\n")
        return held

    def let_go(self, held):
        held.communicate()

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
        browsing = runners.get("claude").capabilities()["browse_gaps"][0]  # what browsing opens, where runs browse
        self.assertIn(browsing, printed.stdout)
        # Each run in flight that may browse holds a browser: two at once on each of the two runners.
        self.assertIn("Each holds about 330 MiB while its run is in flight: about 1.3 GiB with 4 such runs at once",
                      printed.stdout)
        self.assertIn("Each session refuses, whatever its harness allows: running JavaScript in the page",
                      printed.stdout)

        # Every run and job capped: a maximum, and never called one without what can take a run past its cap.
        self.study(name="capped", models=[self.CLAUDE], synthesis=synthesis, browse=False)
        note = runners.get("claude").capabilities()["budget_cap_note"]
        capped, ceiling = self.launch("plan").stdout, self.plan()["ceiling"]
        self.assertNotIn(browsing, capped)
        self.assertNotIn("Browser sessions", capped)
        self.assertIn("Ceiling: $9.00, a guaranteed maximum apart from the caveats below", capped)
        self.assertIn(f"Caveat: on claude, {note}.", capped)
        self.assertEqual((ceiling["label"], ceiling["caveats"][0]), ("guaranteed maximum", f"on claude, {note}"))

    def test_usage_record_counts_a_resumed_session_once_and_the_next_plan_estimates_from_it(self):
        twice = [["write:1"], ["write:all"]]
        self.study({"P01-opus": twice, "P01-local": twice}, models=[self.CLAUDE, self.CODEX, self.PI])
        self.launch("pilot")
        self.launch("resume")  # P01-opus and P01-local again, in sessions that have already reported their usage once
        self.assertEqual(self.states(), {"P01-opus": "done", "P02-opus": "pending", "P01-cx": "done",
                                         "P02-cx": "pending", "P01-local": "done", "P02-local": "pending"})
        record = self.sd.joinpath("analysis/usage.md").read_text()  # as the launcher left it
        figures = json.loads(self.launch("usage", "--json").stdout)
        reported = {r["run"]: (r["attempts"], r["input_tokens"], r["output_tokens"], r["cost_usd"])
                    for r in figures["runs"]}
        pi_cost = 0.0001594 + 0.0001588 + 0.00015610000000000003  # the three requests of pi/ok and pi/resume
        self.assertEqual(reported, {  # the totals of claude/ok and codex/ok, each once, and of Pi's session file
            "P01-opus": (2, 2956, 597, 0.00046504), "P01-cx": (1, 82346, 297, None),
            "P01-local": (2, 4503, 48, pi_cost), "P02-opus": (0, None, None, None),
            "P02-cx": (0, None, None, None), "P02-local": (0, None, None, None)})
        total = figures["total"]
        self.assertEqual((total["input_tokens"], total["output_tokens"]), (89805, 942))
        self.assertAlmostEqual(total["cost_usd"], 0.00046504 + pi_cost)
        self.assertIn("| P01-opus | panellist | opus | done | 2 |", record)
        for cells in ("| 2,956 | 597 | 2,234 | $0.0005 |", "| 82,346 | 297 | 67,968 | not reported |",
                      "| 4,503 | 48 | 0 | $0.0005 |", "| 89,805 | 942 | 70,202 | $0.0009 (1 not reported) |"):
            self.assertIn(cells, record)
        # One finished run on each key and one to go: the estimate is what the finished one reported.
        estimate = {e["entry"]: e for e in self.plan()["estimate"]["entries"]}
        self.assertEqual({k: (e["basis"], e["measured_runs"], e["to_go"], e["tokens"], e["cost_usd"], e["cost"])
                          for k, e in estimate.items()},
                         {"opus": ("measured", 1, 1, 3553, 0.00046504, "measured"),
                          "cx": ("measured", 1, 1, 82643, None, "not reported"),
                          "local": ("measured", 1, 1, 4551, pi_cost, "measured")})
        self.assertGreater(estimate["cx"]["seconds"], 0)  # with no cost reported, the time is what is left
        self.assertIn("cost not reported", self.launch("plan").stdout)

    def test_full_materials_study_with_a_model_that_reads_no_images_is_refused_at_the_plan_step(self):
        text_only = {**self.PI, "model": "openai-codex/gpt-5.3-codex-spark"}  # listed as taking no images
        self.study(models=[self.CLAUDE, text_only])
        planned = self.launch("plan")
        self.assertEqual(planned.returncode, 1, planned.stdout + planned.stderr)
        self.assertIn("local: openai-codex/gpt-5.3-codex-spark on pi cannot open images", planned.stdout)
        started = self.launch("run")
        self.assertEqual(started.returncode, 1)
        self.assertIn("P01-local: openai-codex/gpt-5.3-codex-spark on pi cannot open images", started.stdout)
        self.assertEqual(self.starts(), [])
        self.settings({"materials": "text"})  # the same model is welcome where there is nothing to look at
        self.assertEqual(self.launch("plan").returncode, 0)

    def test_model_its_harness_does_not_list_or_cannot_sign_in_for_is_refused_before_any_run_starts(self):
        loose = {**self.PI, "model": "openai-codex/luna"}  # the CLI itself would run some model that matches
        self.study(models=[self.CLAUDE, loose])
        for command in ("plan", "run"):
            with self.subTest(command):
                refused = self.launch(command)
                self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
                self.assertIn('pi lists no model "openai-codex/luna"', refused.stdout)
        self.study(name="dead", models=[self.CLAUDE, self.PI])
        refused = self.launch("run", FAKE_PI="dead_login")
        self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
        self.assertIn("P01-local: pi lists openai-codex/gpt-6-luna, its provider openai-codex is not signed in "
                      "(invalid_state)", refused.stdout)
        self.assertEqual(self.starts(), [])

    def test_text_only_study_gives_panellists_the_words_alone_and_scores_no_design_factor(self):
        self.study(models=[self.CLAUDE], materials="text", browse=True, fit_factors=["relevance", "visual"],
                   synthesis={"analyst": {"runner": "claude"}, "writer": {"runner": "claude"}})
        panel = self.sd / "panel"
        # Capture: the page text alone. Sheets left by an earlier capture go, and nothing of a
        # page that a run could open is inside panel/.
        earlier = panel / "materials/concept-A/index"
        (earlier / "raw").mkdir(parents=True)
        for image in ("raw/d-00.png", "desktop-sheet-01.png", "mobile-first-screens.png"):
            (earlier / image).touch()
        captured = subprocess.run([sys.executable, str(self.scripts / "capture.py"), str(self.sd)], env=self.env,
                                  capture_output=True, text=True)
        self.assertEqual(captured.returncode, 0, captured.stderr)
        self.assertEqual(sorted(str(f.relative_to(panel)) for f in panel.rglob("*")
                                if f.is_file() and f.parent.name != "personas"),
                         ["_panel-instructions.md", *(f"materials/concept-{x}/index/page-text.txt" for x in "ABC")])
        browser = [json.loads(line)["argv"] for line in self.log.read_text().splitlines()]
        self.assertEqual((any("open" in argv for argv in browser), any("screenshot" in argv for argv in browser)),
                         (True, False))
        # What panellists are told: they read the words, and nothing points them at the design.
        instructions = panel.joinpath("_panel-instructions.md").read_text()
        prompts = [f.read_text() for f in self.sd.glob("prompts/P*.md")]
        for told in (instructions, *prompts):
            self.assertIn("You cannot see the design", told)
            for word in ("sheet", "screenshot", "raw/", ".png", "browser", "Visual", "Mobile"):
                self.assertNotIn(word, told)
        self.assertIn("flattened page", instructions)
        self.assertIn("\n|---|---|---|---|---|---|---|---|---|\n| n | n | n | n | n | n | n | n | n |\n", instructions)
        # The plan says what "materials": "text" overrode in study.json.
        plan = self.plan()
        self.assertEqual(plan["materials"]["text_only"], {
            "dropped_factors": ["visual", "mobile"], "dropped_fit_factors": ["visual"], "fit_factors": ["relevance"],
            "browse_ignored": True})
        self.assertEqual([('"fit_factors" names visual' in n, '"browse": true' in n) for n in plan["notes"]],
                         [(True, False), (False, True)])
        self.assertIn("panellists receive the page text only", self.launch("plan").stdout)
        # The runs: nine scores a section make a run done, and no run is given the browser.
        r = self.launch("run")
        self.assertEqual((r.returncode, set(self.states().values())), (0, {"done"}), r.stdout + r.stderr)
        self.assertFalse([e["run"] for e in self.starts() if "Bash" in " ".join(e["argv"])])
        self.assertEqual(run("check_runs.py", self.sd).returncode, 0)
        run("extract_scores.py", self.sd)
        with open(self.sd / "analysis/scores.csv") as f:
            self.assertEqual(next(csv.reader(f))[8:], ["first", "relevance", "problem", "how", "why_care", "trust",
                                                       "structure", "next_step", "overall"])
        run("analyze.py", self.sd)
        quant = json.loads(self.sd.joinpath("analysis/quant.json").read_text())
        self.assertEqual((quant["fit"]["factors"], sorted(set(quant["factors"]["A"]) & {"visual", "mobile"})),
                         (["relevance"], []))
        report = self.sd.joinpath("analysis/quant.md").read_text()
        self.assertEqual(("Structure and flow" in report, "Visual design" in report, "Mobile" in report),
                         (True, False, False))
        # The analysts and the writer are told what the panel could not see.
        self.launch("run", "--role", "analyst")
        self.launch("run", "--role", "writer")
        self.assertIn("text-only study", self.sd.joinpath("prompts/analyst-1.md").read_text())
        self.assertIn("flattened pages", self.sd.joinpath("prompts/writer.md").read_text())
        # A section scored on the full set of factors is an unscored one, as any wrong count is.
        f = self.sd / self.entries()["P01-opus"]["file"]
        f.write_text(f.read_text().replace("| 7 | 7 |", "| 7 | 7 | 7 | 7 |", 1))
        checked = run("check_runs.py", self.sd, check=False)
        self.assertEqual(checked.returncode, 1)
        self.assertIn("| P01-opus | no parseable score row:", checked.stdout)

    def test_url_and_files_concepts_reach_panellists_under_neutral_names_and_a_url_only_when_the_study_browses(self):
        poppler = all(shutil.which(tool) for tool in ("pdftotext", "pdftoppm"))
        mock = self.tmp / "mock"
        mock.mkdir()
        (mock / "hero-shot-final.png").write_bytes(png(40, 3000))  # far taller than a screen
        (mock / "sales-deck.pdf").write_bytes(pdf(["Books done by Friday", "Lorem ipsum pricing"]))
        address = "http://shop.example.test/launch-offer"
        self.study(personas=1, models=[self.CLAUDE], leak_terms=["secret codename"], forbidden_terms=["lorem ipsum"],
                   concepts=[{"id": "live-pricing", "kind": "url", "url": address},
                             {"id": "investor-mockups", "kind": "files",
                              "files": ["../mock/hero-shot-final.png", *(["../mock/sales-deck.pdf"] if poppler else [])]}])
        key = self.sd.joinpath("key.md").read_text()
        live, filed = (re.search(rf"^\| (\w) \| {cid} \|", key, re.M).group(1)
                       for cid in ("live-pricing", "investor-mockups"))
        named = ["live-pricing", "investor-mockups", "hero-shot", "sales-deck", "shop.example.test", "launch-offer"]

        def leaked():  # everything a panellist can read, and the name of every file it could list
            seen = [f for folder in ("panel", "prompts") for f in sorted((self.sd / folder).rglob("*"))]
            return {str(f.relative_to(self.sd)) for f in seen for word in named
                    if word in str(f.relative_to(self.sd)) or (f.is_file() and word.encode() in f.read_bytes())}

        def argv_of_a_run():
            started = len(self.starts())
            self.launch("pilot")
            return " ".join(self.starts(started)[0]["argv"])

        # Scaffolded: key.md maps what no panellist is told, and a live URL is not browsed unless the study says so.
        for word in (address, "hero-shot-final.png", *(["sales-deck.pdf"] if poppler else [])):
            self.assertIn(word, key)
        self.assertEqual(leaked(), set())
        self.assertFalse((self.sd / "panel/sites").exists())
        self.assertNotIn("agent-browser", self.sd.joinpath("panel/_panel-instructions.md").read_text())

        # Captured: the live page as a page, each file as a numbered item, and the term scan over both.
        tools = self.tmp / "tools"
        tools.mkdir()
        for tool in ("magick", "convert", "identify", "montage", "pdftotext", "pdftoppm"):
            if shutil.which(tool):
                os.symlink(shutil.which(tool), tools / tool)
        if not ((tools / "magick").exists() or all((tools / t).exists() for t in ("convert", "identify", "montage"))):
            self.skipTest("ImageMagick is not installed, so nothing can be captured")
        captured = subprocess.run(
            [sys.executable, str(self.scripts / "capture.py"), str(self.sd)], capture_output=True, text=True,
            env={**self.env, "PATH": f"{self.bin}:{tools}", "FAKE_PAGE_TEXT": "Our secret codename is Atlas."})
        self.assertEqual(captured.returncode, 0, captured.stderr)
        materials = self.sd / "panel/materials"
        self.assertEqual(sorted(str(f.relative_to(materials)) for f in materials.rglob("*") if f.is_file()), sorted([
            f"concept-{live}/index/page-text.txt",
            *(f"concept-{filed}/item-01/{name}" for name in ("image.png", "part-01.png", "part-02.png")),
            *((f"concept-{filed}/item-02/{name}" for name in ("page-01.png", "page-02.png", "page-text.txt"))
              if poppler else [])]))
        self.assertIn(f"panel/materials/concept-{live}/index/page-text.txt: 'secret codename'", captured.stdout)
        if poppler:
            self.assertEqual(materials.joinpath(f"concept-{filed}/item-02/page-text.txt").read_text(),
                             "[Page 1]\nBooks done by Friday\n\n[Page 2]\nLorem ipsum pricing\n")
            self.assertIn(f"panel/materials/concept-{filed}/item-02/page-text.txt: 'lorem ipsum'", captured.stdout)
        self.assertEqual(leaked(), set())
        # The plan counts a PDF by its pages and a tall image once, and estimates from what a run opens.
        plan = self.plan()
        counted = next(c for c in plan["materials"]["concepts"] if c["concept"] == f"concept-{filed}")
        self.assertEqual(({k: counted[k] for k in ("pdfs", "pdf_pages", "images", "parts")}, plan["estimate"]["pages"]),
                         ({"pdfs": 1, "pdf_pages": 2, "images": 1, "parts": 2}, 4) if poppler else
                         ({"pdfs": 0, "pdf_pages": 0, "images": 1, "parts": 2}, 2))
        self.assertNotIn("Bash", argv_of_a_run())

        # "browse": true puts the address in the instructions' browser rules and nowhere else.
        self.settings({"browse": True})
        subprocess.run([sys.executable, str(self.scripts / "init_study.py"), str(self.sd), "--force"], check=True,
                       capture_output=True, text=True)
        instructions = self.sd.joinpath("panel/_panel-instructions.md").read_text()
        rules = instructions[instructions.index("   - Optional: open a page in a real browser"):
                             instructions.index("3. **Write only to your own persona file.**")]
        self.assertIn(f"Concept {live}: `index` is at `{address}`.", rules)
        self.assertIn(f"Concept {filed} cannot be opened in a browser", rules)
        self.assertEqual(instructions.count("shop.example.test"), 1)
        self.assertEqual(leaked(), {"panel/_panel-instructions.md"})
        self.assertIn("Bash(agent-browser open:*)", argv_of_a_run())
        self.assertIn("External hosts the instructions send panellists to: shop.example.test.", self.launch("plan").stdout)

    def test_item_that_cannot_be_captured_leaves_no_folder_keeps_an_earlier_capture_and_holds_the_runs_back(self):
        if not all(shutil.which(tool) for tool in ("pdftotext", "pdftoppm")):
            self.skipTest("Poppler is not installed, so no PDF can be captured")
        deck, appendix = self.tmp / "deck.pdf", self.tmp / "appendix.pdf"
        deck.write_bytes(pdf(["Books done by Friday"]))
        appendix.write_bytes(b"%PDF-1.4\nnothing a reader can open\n")
        self.study(personas=1, models=[self.CLAUDE],
                   concepts=[{"id": "deck", "kind": "files", "files": ["../deck.pdf", "../appendix.pdf"]}])
        items = self.sd / "panel/materials/concept-A"

        def capture():
            done = subprocess.run([sys.executable, str(self.scripts / "capture.py"), str(self.sd)],
                                  capture_output=True, text=True)
            return done.returncode, done.stdout + done.stderr

        # The item that failed has no folder, the rest are captured, and the script says so by its exit code.
        code, said = capture()
        self.assertNotEqual(code, 0)
        self.assertIn("FAILED A/item-02: pdftotext could not read the PDF", said)
        self.assertIn("1 of 2 pages and items could not be captured", said)
        self.assertEqual(sorted(d.name for d in items.iterdir()), ["item-01"])
        text = items.joinpath("item-01/page-text.txt").read_text()
        self.assertEqual(text, "[Page 1]\nBooks done by Friday\n")
        # The plan names what is missing, and no run starts on a concept short of an item.
        why = "concept-A has no capture of item-02, so a run would review it with that missing"
        self.assertEqual(self.plan()["materials"]["incomplete"], [{"concept": "concept-A", "lacks": ["item-02"]}])
        self.assertIn(f"Missing: the materials: {why}", self.launch("plan").stdout)
        held_back = self.launch("run")
        self.assertIn(f"Nothing was started: {why}", held_back.stdout + held_back.stderr)
        self.assertEqual(self.starts(), [])
        # A capture that fails where an earlier one succeeded leaves the earlier one as it was.
        deck.write_bytes(appendix.read_bytes())
        self.assertNotEqual(capture()[0], 0)
        self.assertEqual(sorted(str(f.relative_to(items)) for f in items.rglob("*") if f.is_file()),
                         ["item-01/page-01.png", "item-01/page-text.txt"])
        self.assertEqual(items.joinpath("item-01/page-text.txt").read_text(), text)

    def test_pdf_concept_without_poppler_is_refused_before_anything_is_scaffolded(self):
        (self.tmp / "deck.pdf").write_bytes(pdf(["One page"]))
        self.sd = self.tmp / "study"
        self.sd.mkdir()
        self.settings({"product": "Acme", "models": [self.CLAUDE],
                       "concepts": [{"id": "deck", "kind": "files", "files": ["../deck.pdf"]}],
                       "personas": [{"id": "P01", "name": "Person 1", "role": "Owner", "personality": "Sceptic"}]})
        refused = subprocess.run([sys.executable, str(self.scripts / "init_study.py"), str(self.sd)], env=self.env,
                                 capture_output=True, text=True)  # PATH holds the fake CLIs and no Poppler
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("Poppler is required for the PDF of concept deck: pdftotext and pdftoppm are not on PATH",
                      refused.stderr)
        self.assertEqual(sorted(f.name for f in self.sd.iterdir()), ["study.json"])

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

    def deleted(self):
        """The sessions the codex CLI was asked to delete."""
        lines = self.log.read_text().splitlines()
        return sorted(c["argv"][-1] for c in map(json.loads, lines) if c.get("argv", [""])[0] == "delete")

    def test_purge_sessions_deletes_only_with_yes_and_never_while_a_launcher_has_the_study(self):
        self.study({"P01-cx": [["write:1", "wait:hold"]]}, models=[self.CODEX])
        deleted = self.deleted
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

    def test_sessions_of_runs_that_a_new_scaffold_replaced_can_still_be_purged(self):
        self.study(models=[self.CODEX])
        self.assertEqual(self.launch("run").returncode, 0)
        self.assertEqual(self.launch("purge-sessions", "--runs", "P02-cx", "--yes").returncode, 0)
        held, gone = (self.entries()[run_id]["session"] for run_id in ("P01-cx", "P02-cx"))
        again = run("init_study.py", self.sd, "--force")  # as after a pilot: runs.json forgets both sessions
        self.assertEqual([e.get("session") for e in self.entries().values()], [None, None])
        self.assertIn("still held by their harnesses: 1", again.stdout)
        record = self.sd / "logs/earlier-sessions.json"
        kept, = json.loads(record.read_text())
        self.assertEqual({k: kept[k] for k in ("run", "runner", "session", "workdir")},
                         {"run": "P01-cx", "runner": "codex", "session": held,
                          "workdir": str(self.sd.resolve() / "panel")})
        self.assertEqual((self.status()["earlier_sessions"], self.plan()["earlier_sessions"]), (1, 1))
        listed = self.launch("purge-sessions")
        self.assertIn(f"codex delete --force {held}", listed.stdout)
        self.assertEqual((self.deleted(), record.exists()), ([gone], True))
        self.assertEqual(self.launch("purge-sessions", "--yes").returncode, 0)
        self.assertEqual((self.deleted(), record.exists(), self.status()["earlier_sessions"]),
                         (sorted([gone, held]), False, 0))

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

    def test_persona_file_that_cannot_be_read_as_the_runs_own_is_no_persona_file_and_nothing_waits_for_it(self):
        self.study(personas=1)
        self.assertEqual((self.launch("run").returncode, self.states()), (0, {"P01-opus": "done", "P01-cx": "done"}))
        named = self.entries()["P01-opus"]["file"]
        file, outside = self.sd / named, self.tmp / "outside.md"
        file.rename(outside)  # complete, and no longer the study's: read through a link, it would pass for the run's
        cases = {"a symbolic link to a complete persona file outside the study":
                 (lambda: file.symlink_to(outside), "it is a symbolic link"),
                 "a FIFO": (lambda: os.mkfifo(file), "it is not a regular file")}  # an open of one to read it waits

        def reader(script):  # a reader that waits for the file is stopped, and fails the test
            return subprocess.run([sys.executable, str(self.scripts / script), str(self.sd)], capture_output=True,
                                  text=True, timeout=60)

        for name, (plant, why) in cases.items():
            with self.subTest(name):
                plant()
                states = {r["run"]: r["state"] for r in self.status()["runs"]}
                checked, extracted = reader("check_runs.py"), reader("extract_scores.py")
                file.unlink()
                # The run is not done to the launcher, the checks block it with the reason, and no score is taken.
                self.assertEqual(states, {"P01-opus": "pending", "P01-cx": "done"})
                self.assertEqual(checked.returncode, 1, checked.stdout + checked.stderr)
                self.assertIn(f"| P01-opus | its persona file {named} cannot be read as the run's own ({why}) | - |\n\n"
                              "1 run file of 2 expected; 1 with blocking problems.", checked.stdout)
                self.assertIn("3 score rows from 2 runs; 1 run incomplete", extracted.stdout)
                with open(self.sd / "analysis/scores.csv") as f:
                    self.assertEqual({r["model"] for r in csv.DictReader(f)}, {"cx"})

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

    def test_run_that_may_browse_has_a_browser_session_of_its_own_from_before_its_cli_until_after_it(self):
        # One run on each runner, each ending another way: by itself, at its time limit, on a request to stop.
        self.study({"P01-opus": [["write:all"]], "P01-cx": [["stubborn", "write:1", "hang"]],
                    "P01-local": [["write:1", "wait:never"]]},
                   personas=1, models=[self.CLAUDE, self.CODEX, self.PI],
                   limits={"overrides": {"cx": {"minutes": 1.5 / 60}}})
        self.env["AGENT_BROWSER_HEADED"] = "1"  # the user's own setting, for other work: no run's browser gets it
        launcher, output = self.launch_in_background("run")
        self.wait_for(lambda: self.waiting() == {"P01-local"} and "P01-opus: done" in output.read_text()
                      and "P01-cx: limited" in output.read_text(), "two runs to end and the third to wait")
        self.assertEqual({r["run"]: r["browser"] for r in self.status()["runs"]},
                         {"P01-opus": None, "P01-cx": None, "P01-local": "up"})
        self.assertEqual(self.launch("stop").returncode, 0)
        self.assertEqual(launcher.wait(timeout=30), 1)
        self.assertEqual(self.states(), {"P01-opus": "done", "P01-cx": "limited", "P01-local": "partial"})
        records, lines = self.browser_sessions(), [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(len({record["socket_dir"] for record in records.values()}), 3)
        for started in self.starts():
            with self.subTest(started["run"]):
                seen, record = started["browser"], records[started["run"]]
                # Its CLI found the session running, reached it by three variables and was given no other.
                self.assertEqual(seen["env"], {"AGENT_BROWSER_SOCKET_DIR": record["socket_dir"],
                                               "AGENT_BROWSER_SESSION": started["run"],
                                               "AGENT_BROWSER_ACTION_POLICY": record["policy"]})
                self.assertTrue(seen["up"])
                # The session was told to refuse what a visitor could not do before the CLI ran.
                refused = next(i for i, x in enumerate(lines) if x.get("argv") == ["eval", "1"]
                               and x["env"] == seen["env"])
                self.assertLess(refused, lines.index(started))
                # However the CLI ended, nothing of the session is left.
                self.wait_for(lambda: self.gone(seen["daemon"]), "the session's daemon to end")
                self.assertEqual((self.left_of(record), bool(record["stopped"])), ([], True))
        # The session was closed after the CLI that used it had ended.
        closed = lines.index({"event": "session closed", "session": "P01-opus"})
        self.assertLess(next(i for i, x in enumerate(lines) if x.get("event") == "end"), closed)
        # It was asked through its socket: agent-browser's own "close" can signal whatever a pid file names.
        self.assertEqual([x["argv"] for x in lines if "close" in x.get("argv", [])], [])

        # A run that may not browse has no session, and its environment is as the launcher's.
        del self.env["AGENT_BROWSER_HEADED"]
        self.study(name="files-alone", personas=1, models=[self.CLAUDE], browse=False)
        self.log.unlink()
        self.assertEqual(self.launch("run").returncode, 0)
        [alone] = self.starts()
        self.assertEqual((alone["browser"]["env"], self.browser_sessions(),
                          [line for line in self.log.read_text().splitlines() if '"agent-browser"' in line]),
                         ({}, {}, []))

    def test_run_whose_browser_session_cannot_be_started_never_runs_its_cli_and_is_not_marked_failed(self):
        self.study(models=[self.CLAUDE])
        r = self.launch("run", FAKE_AGENT_BROWSER="no_launch")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"P01-opus: could not be started\. Its browser session could not be started: .*"
                                   r"agent-browser open about:blank failed \(exit code 1\): . Chrome exited early.*"
                                   r"Nothing was marked as failed")
        # No CLI ran, for this run or the next on its runner, and what the start had made is gone again.
        self.assertEqual((self.starts(), self.states()), ([], {"P01-opus": "pending", "P02-opus": "pending"}))
        self.assertNotIn("attempts", self.entries()["P01-opus"])
        [record] = self.browser_sessions().values()
        self.assertEqual(self.left_of(record), [])

    def test_watchdog_killed_while_the_browser_session_starts_leaves_no_command_and_no_session_behind(self):
        self.study(personas=1, models=[self.CLAUDE])
        self.env["FAKE_AGENT_BROWSER"] = "hang"  # the session's daemon is up, and its start never returns
        first, _ = self.launch_in_background("run")
        self.wait_for(lambda: self.events("open hung"), "the start of the browser session to hang")
        first.kill()
        first.wait()
        watchdog, _, starting = [int(line.split()[0]) for line in
                                 self.sd.joinpath("logs/P01-opus.1.pid").read_text().splitlines() if line[0].isdigit()]
        os.kill(watchdog, signal.SIGKILL)
        self.wait_for(lambda: self.gone(watchdog), "the watchdog to go")
        [opening] = [e["pid"] for e in self.events("open hung")]
        [record] = self.browser_sessions().values()
        daemon = int(Path(record["socket_dir"], "P01-opus.pid").read_text())
        # No one waits for the command that starts the session, and it has not got as far as recording a daemon.
        self.assertEqual(([self.gone(pid) for pid in (starting, opening, daemon)], record["daemon"]),
                         ([False, False, False], None))

        r = self.launch("stop")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for pid in (starting, opening, daemon):
            self.wait_for(lambda: self.gone(pid), "the command and the session it had started to go")
        [record] = self.browser_sessions().values()
        self.assertEqual((self.left_of(record), bool(record["stopped"]), record["left"], record["kept"]),
                         ([], True, [], []))
        # Its CLI never ran: the run is as it was before the attempt, and nothing is marked failed.
        self.assertRegex(r.stdout, r"P01-opus: could not be started\. Its browser session could not be started: .*"
                                   r"its watchdog was killed while the session was being started.*"
                                   r"Nothing was marked as failed")
        self.assertEqual((self.starts(), self.states()), ([], {"P01-opus": "pending"}))
        self.assertNotIn("attempts", self.entries()["P01-opus"])

    def test_browser_session_record_that_is_a_fifo_is_refused_once_and_no_command_waits_for_it(self):
        self.study({"P01-opus": [["write:1", "wait:never"]]}, personas=1, models=[self.CLAUDE])
        launcher, output = self.launch_in_background("run")
        self.wait_for(lambda: self.waiting() == {"P01-opus"}, "the run to be under way")
        record = self.sd / "logs/P01-opus.1.browser"
        session = json.loads(record.read_text())
        record.unlink()
        os.mkfifo(record)  # an open of it to read it waits for a writer, and none ever comes
        # Neither status nor the launcher that settles the attempt waits for it: launch() gives a command 60 s.
        self.assertEqual([(r["process"], r["browser"]) for r in self.status()["runs"]], [("alive", "down")])
        self.assertEqual(self.launch("stop").returncode, 0)
        self.assertEqual(launcher.wait(timeout=30), 1)
        said = output.read_text()
        self.assertEqual(said.count("P01-opus: the record of its browser session cannot be trusted"), 1, said)
        self.assertRegex(said, r"P01-opus\.1\.browser is not a regular file of this user\), so nothing of the session "
                               r"was stopped or removed")
        # The attempt is settled as any other, with the refusal on record for status, and the session is untouched.
        self.assertEqual(self.states(), {"P01-opus": "partial"}, said)
        self.assertRegex(self.launch("status").stdout, r"THE RECORD OF ITS BROWSER SESSION CANNOT BE TRUSTED \(.*"
                                                       r"P01-opus\.1\.browser is not a regular file of this user\)")
        self.assertEqual((self.left_of(session), self.gone(session["daemon"][0])), (["socket_dir", "policy"], False))

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
            # Prints as it starts, ends quietly and unwatched. Resumed later, to be killed with its watchdog.
            "P01-opus": [["write:1", "wait:die", "exit:1"], ["wait:never"]],
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
        # No launcher has the study now, and its processes are still at work: no new scaffold under them.
        scaffold_again = run("init_study.py", self.sd, "--force", check=False)
        self.assertEqual(scaffold_again.returncode, 1)
        self.assertRegex(scaffold_again.stderr, r"still at work \(.*P02-opus.*Stop them first: launch.py \S+ stop")
        # runs.json as a launcher killed between starting P02-opus and noting its pid leaves it:
        # the attempt is on record without one, and only the attempt's own pid file says where it is.
        as_left = self.entries()
        as_left["P02-opus"].update(pid=None, pid_identity=None)
        self.sd.joinpath("runs.json").write_text(json.dumps(list(as_left.values())))
        self.wait_for(lambda: self.processes() == {"P01-opus": "alive", "P02-opus": "alive", "P01-cx": "gone",
                                                   "P02-cx": "gone"}, "the time limit to end two runs unwatched")
        # A shell in another process namespace, as inside a harness's sandbox, sees no process of the study.
        # What it does see is the lock each watchdog holds for as long as it lives: the two runs still alive
        # are at work where it cannot look, and the two that ended are over. Here that shell is this one, with
        # the record of each live run naming a process that is not there. No launcher holds the study's lock to
        # tell by, and still nothing is said of a live run's process, and none is settled, stopped, started
        # again or scaffolded over.
        hidden = ("P01-opus", "P02-opus")
        as_recorded = {path: path.read_text() for path in map(self.sd.joinpath, (f"logs/{x}.1.pid" for x in hidden))}
        for path, text in as_recorded.items():  # its watchdog, then its CLI, each under the id of a process long gone
            path.write_text(re.sub(r"(?m)^\d+ ", f"{first.pid} ", text))
        alive, before = [e["pid"] for e in self.starts() if e["run"] in hidden], self.tree()
        self.assertEqual({r["run"]: (r["state"], r["process"], r["browser"]) for r in self.status()["runs"]},
                         {**dict.fromkeys(as_left, ("running", "gone", None)),
                          **dict.fromkeys(hidden, ("running", "unseen", None))})
        said = self.launch("status").stdout
        self.assertIn("Launcher: not running\nThis shell cannot see the launcher's processes, as inside a sandbox: "
                      "run states are as last recorded.\nMarked running, but the process is gone: P01-cx, P02-cx. ",
                      said)
        for line in said.splitlines():
            if line.startswith(hidden):
                self.assertNotRegex(line, "process|browser session")
        refused = {"init_study --force": lambda: run("init_study.py", self.sd, "--force", check=False),
                   **{name: lambda name=name: self.launch(name) for name in ("stop", "resume", "run")}}

        def unseen(command):
            return (f"This shell cannot see the processes of {', '.join(hidden)}, as inside a sandbox: their watchdogs "
                    "hold their locks, so those runs are still at work where this shell cannot look. "
                    f'"{command}" changed nothing and signalled nothing. {SANDBOX_HINT} Runs that were started '
                    "inside a sandbox end when it does, and any shell settles them then.\n")

        for command, attempt in refused.items():
            r = attempt()
            self.assertEqual((r.returncode, r.stderr), (1, unseen(command)), r.stdout)
            self.assertEqual((self.tree() == before, len(self.starts()), [self.gone(pid) for pid in alive]),
                             (True, 4, [False, False]), f"{command}: {r.stdout}")
        # A sandbox may show the study read-only as well. No command is given the study's lock there, and
        # archive.py goes on without it, for a round that was archived read-only. It asks the locks of the
        # watchdogs first, which a shell that only reads can ask, and goes no further than the others did.
        if os.geteuid():  # root writes to a directory whatever its mode says
            modes = {path: stat.S_IMODE(path.stat().st_mode) for path in (self.sd, self.sd / ".launch.lock")}
            try:
                for path, mode in modes.items():
                    path.chmod(mode & ~0o222)
                r = run("archive.py", self.sd, "--dest", self.tmp / "archived", check=False)
            finally:
                for path, mode in modes.items():
                    path.chmod(mode)
            self.assertEqual((r.returncode, r.stderr, self.tmp.joinpath("archived").exists(), self.tree() == before),
                             (1, unseen("archive"), False, True), r.stdout)
        for path, text in as_recorded.items():  # as the shell that started them reads it: from here on, as it was
            path.write_text(text)
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

        # A launcher that was started inside a sandbox and killed there takes its watchdogs and CLIs with it. What
        # is left is no end record, a pid file that names processes of a namespace that has gone, and a lock that
        # nothing holds: so the watchdog has ended, to any shell, and the next command settles the run. It looks
        # for nothing under ids that are not this shell's, and says that it could not.
        third, _ = self.launch_in_background("resume", "--poll", 30)
        self.wait_for(lambda: "never" in [e["gate"] for e in self.events("waiting")], "P01-opus to be resumed")
        third.kill()
        third.wait()
        pid_file = self.sd / "logs/P01-opus.2.pid"
        as_recorded = pid_file.read_text()
        for pid in [int(line.split()[0]) for line in as_recorded.splitlines()[:2]]:  # its watchdog, then its CLI
            os.kill(pid, signal.SIGKILL)
            self.wait_for(lambda: self.gone(pid), "a process of P01-opus to have gone")
        # Where the system names no process namespace a watchdog records none, and the run is settled without the note.
        apart = re.sub(r"(?m)^namespace .*$", "namespace pid:[0]", as_recorded)
        pid_file.write_text(apart)
        # The daemon of its browser session is on record under an id of that namespace too. Here that id, and
        # its start identity, are those of a process of this shell, which is not signalled for the daemon. The
        # session is still stopped: it answers at its socket, where the system names the process that listens.
        bystander = subprocess.Popen([sys.executable, "-c", "import sys\nsys.stdin.read()"], stdin=subprocess.PIPE)
        self.addCleanup(bystander.communicate)  # which ends it
        session = self.sd / "logs/P01-opus.2.browser"
        if apart != as_recorded:
            session.write_text(json.dumps({**json.loads(session.read_text()),
                                           "daemon": [bystander.pid, run_watchdog.identity(bystander.pid)]}))
        self.assertEqual(self.processes(), {"P01-opus": "gone"})
        stop = self.launch("stop")
        self.assertEqual((stop.returncode, stop.stderr), (0, ""), stop.stdout)
        note = "its CLI could not be checked from this shell because it ran in another process namespace"
        settled = self.entries()["P01-opus"]
        self.assertEqual((settled["state"], f"not on record, and {note})" in settled["reason"],
                          f"P01-opus: its watchdog was killed, and {note}. " in stop.stdout),
                         ("partial", apart != as_recorded, apart != as_recorded), stop.stdout)
        self.assertEqual((bystander.poll(), settled["attempts"][-1]["browser_left"]),
                         (None, {"found": True, "left": [], "kept": []}), stop.stdout)

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
        browsers = [e["browser"]["daemon"] for e in self.starts()]  # no watchdog is left to stop them
        self.assertEqual([self.gone(daemon) for daemon in browsers], [False, False])

        r = self.launch("stop")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # The browser session of each run is the launcher's own to stop, and it says that it did.
        for daemon in browsers:
            self.wait_for(lambda: self.gone(daemon), "a browser session to be stopped")
        self.assertEqual([self.left_of(record) for record in self.browser_sessions().values()], [[], []])
        self.assertEqual(r.stdout.count("its watchdog left its browser session running, and the launcher stopped it."),
                         2)
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
        self.assertEqual({row["run"]: (row["leftover"], row["browser_left"]) for row in self.status()["runs"]},
                         {"P01-opus": (None, {"found": True, "left": [], "kept": []}),
                          "P02-opus": ({"group": cli["P02-opus"], "pids": [left]},
                                       {"found": True, "left": [], "kept": []})})
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
        scaffold_again = run("init_study.py", self.sd, "--force", check=False)  # would replace runs.json under it
        self.assertEqual(scaffold_again.returncode, 1)
        self.assertIn(f"Another launcher has this study (pid {first.pid}", scaffold_again.stderr)
        self.assertIn(f"launch.py {self.sd.resolve()} stop", scaffold_again.stderr)

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

    def test_held_lock_is_a_launcher_running_and_status_says_nothing_of_processes_it_cannot_see(self):
        self.study({"P01-opus": [["write:1", "wait:never"]], "P02-opus": [["write:1", "wait:never"]]},
                   models=[self.CLAUDE])
        first, _ = self.launch_in_background("run", "--poll", 30)
        self.wait_for(lambda: self.waiting() == {"P01-opus", "P02-opus"}, "both runs to be under way")
        first.kill()
        first.wait()
        cli = {e["run"]: e["pid"] for e in self.starts()}
        # What a shell in another process namespace sees of a run, as a sandboxed shell does: no process.
        for line in self.sd.joinpath("logs/P02-opus.1.pid").read_text().splitlines()[:2]:  # its watchdog, then its CLI
            os.kill(int(line.split()[0]), signal.SIGKILL)
        seen = {"P01-opus": "alive", "P02-opus": "gone"}
        self.wait_for(lambda: self.processes() == seen, "the processes of P02-opus to have gone")
        self.assertIsNone(self.status()["launcher"])
        # And of the launcher: the lock is held, and the file names a process that is not there to be seen.
        elsewhere = self.holding("LOCK_EX")
        status = self.status()
        self.assertEqual({k: (status["launcher"] or {}).get(k) for k in ("pid", "command", "seen")},
                         {"pid": first.pid, "command": "run", "seen": False})
        self.assertEqual({r["run"]: (r["state"], r["process"], r["browser"]) for r in status["runs"]},
                         dict.fromkeys(seen, ("running", "unseen", None)))
        said = self.launch("status").stdout
        self.assertIn(f'Launcher: running "run" (pid {first.pid})\nThis shell cannot see the launcher\'s processes, '
                      "as inside a sandbox: run states are as last recorded.\n", said)
        for claim in ("process gone", "process alive", "browser session", "settles them"):
            self.assertNotIn(claim, said)
        self.assertIn(f'A launcher is running "run" on this study (pid {first.pid}).', self.launch("plan").stdout)
        # No command takes the lock for stale because its holder cannot be seen, and none signals the process
        # id on record, which may be another process's here.
        second = self.launch("run")
        self.assertEqual((second.returncode, len(self.starts())), (1, 2), second.stdout + second.stderr)
        self.assertIn(f"Another launcher has this study (pid {first.pid}", second.stderr)
        self.assertNotIn("Cleared a stale lock", second.stdout)
        unsignalled = "This shell cannot see the launcher's processes, as inside a sandbox, so nothing was signalled"
        stop = self.launch("stop")
        self.assertEqual(stop.returncode, 1, stop.stdout)
        self.assertIn(unsignalled, stop.stderr)
        self.assertEqual((self.gone(cli["P01-opus"]), set(self.states().values())), (False, {"running"}))
        # Nor is a process of this shell the launcher because it holds the id on record. A launcher records the
        # process namespace it runs in, where the system names one, and an id recorded in another names no
        # process here. With the id and start identity of a process this shell does see, the one holding the
        # lock, the launcher is seen under this shell's namespace, and under another is not seen or signalled.
        try:
            here = os.readlink("/proc/self/ns/pid")
        except OSError:
            here = None  # none is named where there is no /proc, as on macOS: a launcher records none there
        if here:
            lock_file = self.sd / ".launch.lock"
            as_recorded = lock_file.read_text()
            named = {**json.loads(as_recorded), "pid": elsewhere.pid, "identity": run_watchdog.identity(elsewhere.pid)}
            self.assertEqual(named.get("namespace"), here)
            for within, seen_here in ((here, True), ("pid:[0]", False)):
                lock_file.write_text(json.dumps({**named, "namespace": within}))
                self.assertEqual({k: self.status()["launcher"].get(k) for k in ("pid", "seen")},
                                 {"pid": elsewhere.pid, "seen": seen_here}, within)
            stop = self.launch("stop")
            self.assertEqual((stop.returncode, unsignalled in stop.stderr, elsewhere.poll()), (1, True, None),
                             stop.stdout + stop.stderr)
            lock_file.write_text(as_recorded)
        self.let_go(elsewhere)
        self.assertEqual((self.status()["launcher"], self.processes()), (None, seen))  # with no lock held, as before

        # A command that asks whether a launcher has the study holds a shared lock for an instant. A launcher
        # that finds one in its way waits for it, and is not turned away as by another launcher.
        asking = self.holding("LOCK_SH")
        stopping = subprocess.Popen(self.command("stop"), env=self.env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
        self.background.append(stopping)
        time.sleep(0.5)
        self.assertIsNone(stopping.poll(), "turned away by a lock that no launcher holds")
        self.let_go(asking)
        said = stopping.communicate(timeout=30)[0]
        self.assertEqual((stopping.returncode, "Stopped." in said), (0, True), said)
        self.assertEqual((self.gone(cli["P01-opus"]), self.states()),
                         (True, {"P01-opus": "partial", "P02-opus": "partial"}))

    def test_hang_up_stops_the_runs_unless_the_launcher_was_started_ignoring_it(self):
        self.study({"P01-opus": [["wait:finish", "write:all"]]}, personas=1, models=[self.CLAUDE])
        heeding, _ = self.launch_in_background("run")
        self.wait_for(lambda: self.waiting() == {"P01-opus"}, "the run to be under way")
        heeding.send_signal(signal.SIGHUP)
        self.assertEqual(heeding.wait(timeout=30), 1)  # a clean stop, not a launcher killed by the signal
        # It leaves the study's lock file where it is, for the next launcher and for a shell that only reads to
        # lock. The file names no launcher: none is running, and none was killed and left a stale lock.
        lock_file, shown = self.sd / ".launch.lock", self.launch("status").stdout
        self.assertEqual((self.states(), lock_file.is_file(), self.status()["launcher"],
                          "Launcher: not running\n" in shown),
                         ({"P01-opus": "pending"}, True, None, True), shown)

        under_nohup, output = self.launch_in_background("run", ignoring_hang_up=True)
        self.wait_for(lambda: len(self.events("waiting")) == 2, "the run to be under way again")
        under_nohup.send_signal(signal.SIGHUP)
        time.sleep(0.5)  # 25 polls: a launcher that heeded the signal has stopped its run by now
        self.release("finish")
        self.assertEqual(under_nohup.wait(timeout=30), 0)
        self.assertEqual((self.states(), "Cleared a stale lock" in output.read_text(), lock_file.is_file()),
                         ({"P01-opus": "done"}, False, True))

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

        # A CLI that is signed in and cannot do a run from this shell, as Codex inside another Codex sandbox,
        # is refused by name before anything starts, with the CLI's words and both ways out. The other
        # runner is judged on its own.
        self.study(personas=1, name="nested")
        cannot = (f"codex-cli 0.162.1, Logged in using ChatGPT, but from this shell it cannot build its own sandbox "
                  f"({NO_SANDBOX}). {SANDBOX_HINT}")
        planned = self.launch("plan", FAKE_CODEX="nested")
        self.assertEqual(planned.returncode, 1, planned.stdout + planned.stderr)
        self.assertIn(f"  codex: CANNOT BE USED: {cannot} Up to 4 runs at once.", planned.stdout)
        refused = self.launch("run", FAKE_CODEX="nested")
        self.assertEqual((refused.returncode, self.starts(1)), (1, []), refused.stdout + refused.stderr)
        self.assertIn(f"codex: cannot be used: {cannot}", refused.stdout)
        self.assertEqual(self.launch("run", "--allow-missing", FAKE_CODEX="nested").returncode, 1)
        self.assertEqual([e["run"] for e in self.starts(1)], ["P01-opus"])  # claude can run here, and did

        self.study(personas=1, name="bad-effort", models=[self.CLAUDE, {**self.CODEX, "effort": "ultra"}])
        refused = self.launch("run")
        self.assertEqual(refused.returncode, 1)
        self.assertIn('P01-cx: codex has no effort "ultra"', refused.stdout)
        self.assertEqual(self.starts(2), [])

        # A concept with nothing captured would be reviewed from nothing: it is named, with the command.
        self.study(personas=1, name="uncaptured")
        shutil.rmtree(self.sd / "panel/materials/concept-B")
        refused = self.launch("run")
        self.assertEqual((refused.returncode, self.starts(2)), (1, []))
        self.assertIn(f"Nothing was started: nothing is captured for concept-B, so a run would review it from "
                      f"nothing. Run capture.py {self.sd}", refused.stdout)

    def test_process_that_cannot_be_started_is_reported_and_nothing_is_marked_failed(self):
        cases = [  # what the sandbox does, the runner it hits, what the launcher says about the first run
            ({"FAKE_CODEX": "sandboxed"}, "cx",  # passes the check, then every run dies before printing a line
             "P01-cx: could not be started. Its CLI exited with code 1 before printing anything: codex exec --json "
             "--skip-git-repo-check ... (Error: failed to initialize in-process app-server client: Read-only file "
             f"system (os error 30)). Nothing was marked as failed. {SANDBOX_HINT}"),
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

    def test_run_that_shows_its_cli_cannot_work_from_this_shell_is_not_retried_and_closes_its_runner(self):
        unreachable = "API Error: Can't reach the API server \u2014 check your internet or DNS (EAI_AGAIN)"
        cases = [  # how the first run on a runner ends, that runner's key, and what the launcher gives as the reason
            ("end:nested", "cx", f"it could not build its sandbox ({NO_SANDBOX})"),  # the turn ended well, exit code 0
            ("end:unreachable", "opus", f"it could not reach its provider ({unreachable}) (exit code 1)"),
        ]
        for step, shut, reason in cases:
            with self.subTest(step):
                other, runner = ("opus", "codex") if shut == "cx" else ("cx", "claude")
                self.study({f"P01-{shut}": [[step]]}, name=f"shut-{shut}",
                           runners={"claude": {"concurrency": 1}, "codex": {"concurrency": 1}})
                self.log.unlink(missing_ok=True)
                r = self.launch("run")  # the check of the shell passed: the run itself is what shows it
                self.assertIn(f"P01-{shut}: failed: the process ended with nothing written: {reason}; not retried\n"
                              f"{runner}: its CLI cannot do a run from this shell. No more launches on this runner "
                              f"in this command, and 1 queued run stays as it is (P02-{shut}). Other runners carry "
                              f"on. {SANDBOX_HINT}\n", r.stdout)
                # One process showed it: no retry and no second run on that runner, and the other carried on.
                started = {e["run"]: e["session"] for e in self.starts()}
                self.assertEqual(sorted(started), sorted([f"P01-{shut}", f"P01-{other}", f"P02-{other}"]))
                self.assertEqual(self.states(), {f"P01-{shut}": "failed", f"P02-{shut}": "pending",
                                                 f"P01-{other}": "done", f"P02-{other}": "done"}, r.stdout)
                # The attempt stays on record with its session, which the harness holds and purge-sessions can delete.
                entry = self.entries()[f"P01-{shut}"]
                self.assertEqual((len(entry["attempts"]), entry["session"]), (1, started[f"P01-{shut}"]))
                self.assertIn(reason, entry["reason"])

    def test_run_whose_session_its_harness_did_not_keep_is_said_once_and_cannot_be_resumed_or_asked(self):
        self.study({"P02-opus": [["write:1"]]}, models=[self.CLAUDE])
        said = "session not saved: this run cannot be resumed or asked a follow-up"
        r = self.launch("run", FAKE_CLAUDE="unsaved")  # runs as usual, and keeps no transcript
        self.assertEqual(self.states(), {"P01-opus": "done", "P02-opus": "partial"}, r.stdout + r.stderr)
        self.assertEqual([r.stdout.count(f"{run_id}: {said}") for run_id in ("P01-opus", "P02-opus")], [1, 1])
        shown = self.launch("status").stdout.splitlines()
        self.assertEqual([said in line for line in shown[:2]], [True, True], shown)
        started = len(self.starts())
        asked = self.ask("Would you pay for it?", "--runs", "P01-opus")
        self.assertIn("P01-opus: cannot be asked: its session was not saved.", asked.stdout)
        resumed = self.launch("resume")
        self.assertIn("P02-opus: partial with sections written, but its session was not saved, so it cannot be "
                      "continued", resumed.stdout)
        self.assertEqual((len(self.starts()), self.sd.joinpath("followups.json").exists()), (started, False))

    def test_study_directory_that_cannot_be_written_is_refused_in_a_sentence(self):
        if os.geteuid() == 0:
            self.skipTest("root can write to a read-only directory")
        self.study()
        self.assertEqual(self.launch("run").returncode, 0)
        run("extract_scores.py", self.sd)
        sd = self.sd.resolve()
        for folder in (sd, sd / "analysis"):  # what a sandboxed shell tool sees
            folder.chmod(0o555)
            self.addCleanup(folder.chmod, 0o755)
        sd.joinpath("analysis/scores.csv").chmod(0o444)
        started = len(self.starts())
        r = self.launch("run", "--runs", "P01-opus")
        self.assertEqual((r.returncode, "Traceback" in r.stderr), (1, False), r.stderr)
        self.assertIn(f"The system refused to write {sd}/.launch.lock (Permission denied). The launcher records every "
                      f'run in the study directory, so "run" did nothing. {SANDBOX_HINT}', r.stderr)
        self.assertEqual(len(self.starts()), started)
        planned = self.launch("plan")  # says so before anyone tries
        self.assertEqual(planned.returncode, 1, planned.stdout + planned.stderr)
        self.assertIn(f"This shell cannot write to the study directory {sd} (Permission denied)", planned.stdout)
        self.assertIn(f"so no run can be started from it. {SANDBOX_HINT}", planned.stdout)
        used = self.launch("usage")  # still reports, and says the file was not written
        self.assertEqual((used.returncode, "## By run" in used.stdout, "could not be written" in used.stderr),
                         (0, True, True), used.stderr)
        # The checks are printed all the same, with one sentence for the file, and the table decides the exit code.
        checked = run("check_runs.py", self.sd, check=False)
        self.assertEqual((checked.returncode, checked.stderr),
                         (0, f"The system refused to write {sd}/analysis/checks.md (Permission denied).\n"))
        self.assertIn("4 run files of 4 expected; 0 with blocking problems.", checked.stdout)
        for script, file in (("extract_scores.py", "scores.csv"), ("extract_answers.py", "answers.csv"),
                             ("analyze.py", "quant.md")):
            with self.subTest(script):
                refused = run(script, self.sd, check=False)
                self.assertEqual((refused.returncode, refused.stderr),
                                 (1, f"The system refused to write {sd}/analysis/{file} (Permission denied).\n"))

    def test_analysts_then_the_writer_run_on_their_own_models_within_a_share_of_the_pool(self):
        from panel_lib import NOTICE
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
        for output in ("qual-1.md", "qual-2.md", "SYNTHESIS.md"):  # as the job wrote it, plus the notice it left out
            self.assertEqual(self.sd.joinpath("analysis", output).read_text(),
                             f"# Findings\n\n{NOTICE}\n\n- Written to {output} by the job itself.\n")
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
        from panel_lib import NOTICE
        self.study({"writer": [["reply"]]}, personas=1, synthesis={"writer": {"runner": "codex"}})
        self.sd.joinpath("analysis/qual-1.md").write_text("# Findings\n")  # the analysis, done by hand
        r = self.launch("run", "--role", "writer")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([e["run"] for e in self.starts()], ["writer"])
        self.assertEqual(self.sd.joinpath("analysis/SYNTHESIS.md").read_text(),
                         f"# Findings\n\n{NOTICE}\n\n- From the reply.\n")
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

    # ---- usability studies

    ACCOUNT_SCRIPT = """#!{python}
import json, os, signal, sys, time
from pathlib import Path
study, (what, *task, run) = Path(__file__).resolve().parents[1], sys.argv[1:]
def note(what):
    with open(study / "accounts.log", "a") as log:
        log.write(what + " " + run + "\\n")
if what == "check":  # a task's success check: what is left of the run's account, then the verdict it is told to give
    held, verdicts = study / "accounts" / (run + ".json"), study / "checks.json"
    what += ":" + task[0] + ":" + ("held" if held.exists() and json.loads(held.read_text())["secrets"] else "gone")
note(what)
if task:
    sys.exit(json.loads(verdicts.read_text()).get(run, {{}}).get(task[0], 0) if verdicts.exists() else 0)
if what == "teardown" and (study / "teardown-fails").exists():
    sys.exit("the product said no to pw-" + run)
if what == "provision" and (study / "provision-waits").exists():  # the first to find it never gets further
    if (study / "worker-stays").exists():  # and has a process of its own, in its group, that no SIGTERM ends
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        worker = os.fork()
        if not worker:
            if (study / "worker-leaves").exists():  # for a session of its own: no list of the group names it
                os.setsid()
            time.sleep(30)
            os._exit(0)
        (study / "worker.pid").write_text(str(worker))
    signal.signal(signal.SIGTERM, lambda *_: (note("stopped"), sys.exit(1)))
    (study / "provision.pid").write_text(str(os.getpid()))
    (study / "provision-waits").unlink()
    time.sleep(30)
    sys.exit(3)
if what == "provision":
    (study / "states").mkdir(exist_ok=True)
    (study / "states" / (run + ".json")).write_text(json.dumps({{"cookies": [{{"name": "sid", "value": "cookie-" + run}}]}}))
    print(json.dumps({{"identifiers": {{"username": "test-" + run}}, "secrets": {{"password": "pw-" + run}},
                      "state": "states/" + run + ".json"}}))
"""

    def usability(self, plan=None, personas=1, accounts=None, **settings):
        """Scaffold a usability study of two tasks, T1 and T2, and set the plan the fakes follow.
        Becomes self.sd. accounts: its "accounts" besides the commands, which are one script,
        scripts/account.py, that notes each call in accounts.log as "<command> <run id>" and, to
        provision, saves a browser state and prints an account whose every value names the run.
        Its teardown fails while the study has a file teardown-fails, and says the account's
        password as it does. The first provision to find a file provision-waits takes the file
        away, notes its pid in provision.pid and waits to be stopped, which it notes as
        "stopped <run id>". While the study has a file worker-stays it first starts a process in
        its own process group that ignores SIGTERM, and notes that one's pid in worker.pid. With
        a file worker-leaves as well, that process leaves the group for a session of its own. A
        study that gives a "map" has its accounts from that, and no commands. None for a study
        without accounts."""
        self.sd = self.tmp / "usability"
        (self.sd / "scripts").mkdir(parents=True)
        script = self.sd / "scripts/account.py"
        script.write_text(self.ACCOUNT_SCRIPT.format(python=sys.executable))
        script.chmod(0o755)
        commands = {name: f"scripts/account.py {name}" for name in ("provision", "teardown")}
        self.settings({
            "type": "usability", "study": "u", "product": "Acme", "models": [self.CLAUDE, self.CODEX],
            "target": {"base_url": "http://app.localhost:8080"},
            "tasks": [{"id": "T1", "goal": "Find out what you could borrow."},
                      {"id": "T2", "goal": "Change your email address.", "start": "/account", "steps": 10}],
            "personas": [{"id": f"P{i:02d}", "name": f"Person {i}", "role": "Owner", "personality": "Sceptic"}
                         for i in range(1, personas + 1)],
            **({} if accounts is None else {"accounts": {**({} if "map" in accounts else commands), **accounts}}),
            **settings})
        subprocess.run([sys.executable, str(self.scripts / "init_study.py"), str(self.sd)], check=True,
                       capture_output=True, text=True)
        shutil.rmtree(self.fake, True)
        (self.fake / "go").mkdir(parents=True)
        (self.fake / "plan.json").write_text(json.dumps(plan or {}))

    def tasks(self, checked=False, steps=None):
        """The two tasks of usability(), to pass as its `tasks`: with a step limit of `steps` each,
        and when checked with a success check each, "scripts/account.py check <task>". That script
        notes "check:<task>:<held or gone> <run id>" in accounts.log, by whether the run's account
        still has its secrets, and exits with the code the study's checks.json has for the run and
        the task, {run id: {task id: exit code}}, else with 0."""
        return [{"id": task, "goal": goal, "start": start, **({"steps": steps} if steps else {}),
                 **({"success_check": f"scripts/account.py check {task}"} if checked else {})}
                for task, goal, start in (("T1", "Find out what you could borrow.", "/"),
                                          ("T2", "Change your email address.", "/account"))]

    def account_calls(self, run_id=None):
        """What the study's account script was called for, in order: for one run, or for all."""
        log = self.sd / "accounts.log"
        calls = log.read_text().splitlines() if log.exists() else []
        return [c.split()[0] for c in calls if c.endswith(f" {run_id}")] if run_id else calls

    def interview(self, plan=None, personas=1, models=None, guide=None, **settings):
        """Scaffold an interview study and set the plan the fakes follow (persona_panel_fakes/talker.py).
        Becomes self.sd. One interview for each persona and model entry, P01-opus and P01-cx unless models
        says otherwise, each with an interviewer on claude, entry interviewer-<run id>. The guide has two
        topics, T1 and T2, a cap of 6 exchanges and the situation card on, and guide changes keys of it.
        Planted, for a test to look for where it must not be: ZQGOAL in the goal, ZQAREA and ZQOPENER in
        each topic, ZQBIO in each persona's bio. An interview nobody plans runs to its end: T1, T2, a
        close, then the interviewer ends it."""
        self.sd = self.tmp / "interview"
        self.sd.mkdir()
        held = {"about": "how a cafe is run from day to day", "interviewer": {"runner": "claude", "model": "opus"},
                "goals": [{"id": "G1", "learn": "ZQGOAL what takes most of the week"}],
                "topics": [{"id": "T1", "area": "ZQAREA the working week", "goals": ["G1"],
                            "opener": "ZQOPENER what took most of your time last week?"},
                           {"id": "T2", "area": "ZQAREA the tools", "goals": ["G1"],
                            "opener": "ZQOPENER what do you keep track of things with?"}],
                "turns": 6, "situation_card": True, **(guide or {})}
        self.settings({
            "type": "interview", "study": "i", "models": models or [self.CLAUDE, self.CODEX], "interview": held,
            "leak_terms": ["secret codename"],
            "personas": [{"id": f"P{i:02d}", "name": f"Person {i}", "role": "Owner", "personality": "Sceptic",
                          "bio": ["Keeps the books in a notebook, under the name ZQBIO."]}
                         for i in range(1, personas + 1)], **settings})
        subprocess.run([sys.executable, str(self.scripts / "init_study.py"), str(self.sd)], check=True,
                       capture_output=True, text=True)
        shutil.rmtree(self.fake, True)
        (self.fake / "go").mkdir(parents=True)
        (self.fake / "plan.json").write_text(json.dumps(plan or {}))

    def turns(self, run_id, *types):
        """The records of an interview's turn log, in order: all of them, or the ones of those types."""
        log = self.sd / "interviews" / f"{run_id}.jsonl"
        records = [json.loads(line) for line in log.read_text().split("\n")[:-1]] if log.exists() else []
        return [r for r in records if not types or r["t"] in types]

    def sent(self, entry):
        """What each process of an entry was sent on its standard input, in order: its prompt, then one
        message for each later turn."""
        return [e["stdin"] for e in self.starts() if e["run"] == entry]

    def reads(self):
        """The state each interview reads as, from status, which has a row for nothing else. On the way,
        what holds at every moment: runs.json records no state for an entry of an interview."""
        for entry in self.entries().values():
            self.assertEqual([k for k in ("state", "reason", "reset_at", "limited_by") if k in entry], [], entry["run"])
        return {r["run"]: r["state"] for r in self.status()["runs"]}

    def whole(self, run_id):
        """An interview's turn log, after checking that it has every turn once: questions and answers
        numbered 1, 2, 3 with none repeated, and no two records of one attempt of a side."""
        records = self.turns(run_id)
        for kind in ("question", "answer"):
            numbers = [r["n"] for r in records if r["t"] == kind]
            self.assertEqual(numbers, list(range(1, len(numbers) + 1)), kind)
        attempts = [(r["side"], r["attempt"]) for r in records if "attempt" in r]
        self.assertEqual(len(attempts), len(set(attempts)), attempts)
        return records

    def test_usability_run_is_done_by_its_task_sections_and_a_resumed_run_is_told_which_tasks_are_left(self):
        self.usability({"P01-opus": [["write:1", "act:1"], ["write:all"]],  # cut off one step into its second task
                        "P01-cx": [["write:2"], ["final"]]})                # every task scored, no final sections
        r = self.launch("run")
        self.assertEqual(self.states(), {"P01-opus": "partial", "P01-cx": "partial"}, r.stdout + r.stderr)
        r = self.launch("resume")
        self.assertEqual((r.returncode, self.states()), (0, {"P01-opus": "done", "P01-cx": "done"}), r.stdout)
        told = {e["run"]: e["stdin"] for e in self.starts() if e["resumed"]}
        for said in ("Tasks already written: T1.", "Tasks left, in this order: T2.", "Your browser was restarted"):
            self.assertIn(said, told["P01-opus"])
        # The task that was under way starts again, as an attempt the step log can tell from the first.
        self.assertRegex(told["P01-opus"], r'Task T2 was under way.*`http://app\.localhost:8080/account`.*'
                                           r'"attempt": 2.*`T2-a2-<step>\.png`')
        self.assertIn("Every task has its section.", told["P01-cx"])
        self.assertNotIn("was under way", told["P01-cx"])
        evidence = self.sd / "panel/evidence/P01-opus"
        steps = [json.loads(line) for line in evidence.joinpath("steps.jsonl").read_text().splitlines()]
        self.assertEqual([(x["task"], x["attempt"], x["step"]) for x in steps if x["phase"] == "result"],
                         [("T1", 1, 1), ("T1", 1, 2), ("T2", 1, 1), ("T2", 2, 1), ("T2", 2, 2)])
        self.assertEqual(sorted(f.name for f in evidence.glob("*.png")),
                         ["T1-1.png", "T1-2.png", "T2-1.png", "T2-a2-1.png", "T2-a2-2.png"])
        # The checks, the scores and the analysis take the task as their unit.
        checks = run("check_runs.py", self.sd).stdout  # nothing blocking, and no ranking or review order missed
        self.assertIn("| P01-opus | - | flat scoring (sd 0.00) |\n\n2 run files of 2 expected; 0 with blocking", checks)
        run("extract_scores.py", self.sd)
        with open(self.sd / "analysis/scores.csv") as f:
            self.assertEqual([(r["model"], r["task"], r["position"], r["complete"], r["overall"])
                              for r in csv.DictReader(f)],
                             [("opus", "T1", "1", "1", "7"), ("opus", "T2", "2", "1", "7"),
                              ("cx", "T1", "1", "1", "7"), ("cx", "T2", "2", "1", "7")])
        run("analyze.py", self.sd)
        self.assertRegex(self.sd.joinpath("analysis/quant.md").read_text(), r"\| T1 \| 2 \| 7\.0 .*\n\| T2 \| 2 \|")

    def test_usability_run_has_a_test_account_of_its_own_that_is_torn_down_once_at_every_final_state(self):
        self.usability({"P01-opus": [["write:all"]],              # done
                        "P01-cx": [["write:1", "end:budget"]],    # limited
                        # Failed two steps into T1, retried once, and failed again one step in, with a message
                        # of its harness that says the password of its account.
                        "P02-opus": [["act:2", "end:error"], ["act:1", "fail:The page said pw-P02-opus and closed."]]},
                       personas=2, accounts={}, tasks=self.tasks(checked=True))
        before = self.tree()
        self.assertEqual(self.launch("plan").returncode, 0)
        self.assertEqual((self.tree(), self.account_calls()), (before, []))  # the plan provisions nothing
        r = self.launch("run", "--runs", "P01-opus,P01-cx,P02-opus")
        self.assertEqual(self.states(), {"P01-opus": "done", "P01-cx": "limited", "P02-opus": "failed",
                                         "P02-cx": "pending"}, r.stdout + r.stderr)
        # One provisioning for each start from nothing, each with its teardown, and none for a run not started.
        # A run in a final state has its tasks checked first, while its account is whole: not one about to be retried.
        checked = ["check:T1:held", "check:T2:held"]
        self.assertEqual({run_id: self.account_calls(run_id) for run_id in self.states()},
                         {"P01-opus": ["provision", *checked, "teardown"],
                          "P01-cx": ["provision", *checked, "teardown"],
                          "P02-opus": ["provision", "teardown", "provision", *checked, "teardown"], "P02-cx": []})
        loaded = {x["env"]["AGENT_BROWSER_SESSION"]: x for x in map(json.loads, self.log.read_text().splitlines())
                  if x.get("cli") == "agent-browser" and x["argv"][:1] == ["--state"]}
        for started in self.starts():
            with self.subTest(started["run"]):
                # The panellist was told who it is signed in as, and was given no secret.
                self.assertEqual({k: v for k, v in started["account"].items() if k != "note"},
                                 {"signed_in": True, "identifiers": {"username": f"test-{started['run']}"}})
                # Its browser session started from its own account's saved state, in a copy that is gone again.
                state = loaded[started["run"]]
                self.assertEqual(state["state"], {"cookies": [{"name": "sid", "value": f"cookie-{started['run']}"}]})
                self.assertTrue(state["argv"][1].startswith(str(self.sd / "logs")), state["argv"])
        self.assertEqual(list(self.sd.glob("logs/*.state")), [])

        def held(folder):  # (the lines of the step log in a folder, None without one, and its screenshots)
            log = folder / "steps.jsonl"
            return len(log.read_text().splitlines()) if log.exists() else None, sorted(f.name for f in folder.glob("*.png"))

        # The retry is a new session, which logs T1 as attempt 1 again. It begins with evidence that is only its
        # own: what the first session logged was set aside for the lead, so no step of the two mixes and no
        # screenshot is written over.
        self.assertEqual((held(self.sd / "panel/evidence/P02-opus"), held(self.sd / "logs/P02-opus.1.evidence")),
                         ((2, ["T1-1.png"]), (4, ["T1-1.png", "T1-2.png"])), r.stdout + r.stderr)
        # What its harness said as it failed held the password. The launcher neither prints nor keeps that
        # message: it says where the lead can read it.
        self.assertIn("the harness's message is withheld because it holds a secret of a test account: it is in "
                      "logs/P02-opus.2.err or logs/P02-opus.2.out", self.entries()["P02-opus"]["reason"])
        self.assertEqual(("pw-P02-opus" in self.sd.joinpath("logs/P02-opus.2.err").read_text(),
                          "pw-" in r.stdout + r.stderr + self.sd.joinpath("runs.json").read_text()), (True, False))
        # Torn down: the secrets are gone from the lead's record, and the identifiers stay.
        record = json.loads(self.sd.joinpath("accounts/P01-opus.json").read_text())
        self.assertEqual((record["identifiers"], record["secrets"], record["state"], bool(record["torn_down"])),
                         ({"username": "test-P01-opus"}, {}, None, True))
        self.assertFalse(self.sd.joinpath("states/P01-opus.json").exists())

        # A launcher that is killed before its run has ended leaves the teardown to the next command.
        first, _ = self.launch_in_background("run", "--runs", "P02-cx", "--poll", 30)
        self.wait_for(lambda: any(e["run"] == "P02-cx" for e in self.events("end")), "P02-cx to end unwatched")
        first.kill()
        first.wait()
        self.assertEqual(self.account_calls("P02-cx"), ["provision"])
        # While the account is in force, its secrets are in the lead's record alone.
        held = self.sd / "accounts/P02-cx.json"
        self.assertEqual((json.loads(held.read_text())["secrets"], held.stat().st_mode & 0o777),
                         ({"password": "pw-P02-cx"}, 0o600))
        self.assertEqual([str(f) for f in self.sd.joinpath("panel").rglob("*") if f.is_file()
                          and (b"pw-P02-cx" in f.read_bytes() or b"cookie-P02-cx" in f.read_bytes())], [])
        # A teardown that fails is said aloud and leaves the account in force, for the next command to try again.
        self.sd.joinpath("teardown-fails").touch()
        r = self.launch("stop")
        wrote = self.sd / "accounts/P02-cx.teardown.output"
        self.assertIn("P02-cx: TEARDOWN OF ITS TEST ACCOUNT FAILED: accounts.teardown exited with code 1 "
                      "(scripts/account.py teardown P02-cx). What it wrote is in accounts/P02-cx.teardown.output",
                      r.stdout)
        self.assertEqual((self.states()["P02-cx"], json.loads(held.read_text())["secrets"]),
                         ("done", {"password": "pw-P02-cx"}))
        # The command said the password as it failed. That is in a file for the lead alone, and in nothing the
        # launcher prints or keeps: not its own lines, runs.json, status or the usage record.
        self.assertEqual(("no to pw-P02-cx" in wrote.read_text(), wrote.stat().st_mode & 0o777), (True, 0o600))
        self.assertIn("exited with code 1", next(x for x in self.status()["runs"] if x["run"] == "P02-cx")
                      ["account"]["teardown_error"])
        kept = [self.sd / "runs.json", *self.sd.glob("analysis/*")]
        self.assertNotIn("pw-", r.stdout + r.stderr + self.launch("status").stdout
                         + self.launch("status", "--json").stdout + "".join(f.read_text() for f in kept))
        self.sd.joinpath("teardown-fails").unlink()
        self.assertIn("P02-cx: its test account was torn down", self.launch("resume").stdout)
        self.assertFalse(wrote.exists())  # of a try that failed: it goes when the command has worked
        self.launch("resume")  # and once it has worked, never again: the checks ran once, before the first try
        self.assertEqual(self.account_calls("P02-cx"), ["provision", *checked, "teardown", "teardown"])
        self.assertEqual((self.entries()["P02-cx"]["account"]["teardown_error"], json.loads(held.read_text())["secrets"]),
                         (None, {}))

    def test_sequential_usability_study_runs_one_panellist_at_a_time_and_resets_the_product_between_them(self):
        # Signing in is the task under test here, so each panellist is handed its secrets.
        self.usability({"P01-opus": [["wait:go", "write:all"]], "P01-cx": [["wait:go", "write:all"]]},
                       sequential=True, accounts={"reset": "scripts/account.py reset", "signin": "panellist"})
        launcher, _ = self.launch_in_background("run")
        self.wait_for(lambda: self.waiting(), "a run to be under way")
        self.assertEqual(len(self.starts()), 1)
        self.release("go")
        self.assertEqual(launcher.wait(timeout=30), 0)
        order = [e["event"] for e in map(json.loads, self.log.read_text().splitlines())
                 if e.get("event") in ("start", "end")]
        self.assertEqual(order, ["start", "end", "start", "end"])
        first, second = (e["run"] for e in self.starts())
        self.assertEqual(self.account_calls(), [f"provision {first}", f"teardown {first}", f"reset {second}",
                                                f"provision {second}", f"teardown {second}"])
        for started in self.starts():
            # Handed the secrets to type, with no saved state loaded for it, and marked for good as a run
            # whose screenshots may show one. Once the account is torn down the secrets are gone again.
            self.assertEqual((started["account"]["signed_in"], started["account"]["secrets"]),
                             (False, {"password": f"pw-{started['run']}"}))
            self.assertTrue(self.entries()[started["run"]]["account"]["secrets_given"])
            self.assertNotIn("pw-", self.sd.joinpath(f"panel/scratch/{started['run']}/account.json").read_text())
        self.assertNotIn('"--state"', self.log.read_text())

    def analysed(self):
        """Extract and analyse the study: (the rows of tasks.csv by run and task, quant.json, quant.md)."""
        run("extract_scores.py", self.sd)
        run("analyze.py", self.sd)
        with open(self.sd / "analysis/tasks.csv") as f:
            rows = {(r["run"], r["task"]): r for r in csv.DictReader(f)}
        return rows, json.loads(self.sd.joinpath("analysis/quant.json").read_text()), \
            self.sd.joinpath("analysis/quant.md").read_text()

    def test_task_that_uses_its_step_limit_keeps_its_last_step_and_a_run_that_passes_the_limit_is_stopped(self):
        self.usability({
            # Keeps to the limit itself: three steps of T1, the last of them off to look for help, then on to T2.
            "P01-opus": [["steps:3", "outcome:ran out of steps", "leave", "write:1", "steps:2", "outcome:completed",
                          "write:all"]],
            # Begins a fourth step of T2, in a step log that already holds what none should: an entry of T2 that is
            # no step, under attempt 999, among it.
            "P01-cx": [["write:1", "scribble", "act:3", "intent:4", "hang"], ["write:all"]],
            # Begins a fourth step of T1 as step 1 of an attempt the launcher never gave it, and is slow to stop.
            "P02-opus": [["act:3", "intent:1@2", "deaf", "hang"]],
        }, personas=2, tasks=self.tasks(steps=3))
        r = self.launch("run", "--runs", "P01-opus,P01-cx")
        entries, evidence = self.entries(), self.sd / "panel/evidence"

        def logged(run_id, phase):  # the (task, step) of each entry of that phase a run's step log holds
            lines = evidence.joinpath(run_id, "steps.jsonl").read_text().splitlines()
            return [(x["task"], x["step"]) for x in map(json.loads, filter(lambda line: line[:1] == "{", lines))
                    if x["phase"] == phase and x["task"] != "T99"]

        # At the limit the panellist stops the task itself: the last step it was allowed has its result and its
        # screenshot, and the run goes on to the next task.
        self.assertEqual((entries["P01-opus"]["state"], logged("P01-opus", "result")),
                         ("done", [("T1", 1), ("T1", 2), ("T1", 3), ("T2", 1), ("T2", 2)]), r.stdout + r.stderr)
        self.assertTrue(evidence.joinpath("P01-opus/T1-3.png").is_file())
        # A run that begins a step beyond the limit is stopped as limited, and keeps everything it wrote. The
        # line that is no entry and the entry for a task the study does not have, numbered 99, stop nothing,
        # and the entry under attempt 999 does not pass for a later attempt that the limit would then be read in.
        stopped = entries["P01-cx"]
        self.assertEqual((stopped["state"], stopped["reason"], stopped["limited_by"]),
                         ("limited", "step limit: task T2, step 4 of 3", "steps"), r.stdout + r.stderr)
        self.assertIn("P01-cx: its step log has 1 line that cannot be read as an entry (line 5)", r.stdout)
        self.assertEqual((self.sd.joinpath(stopped["file"]).read_text().count("### Task "),
                          logged("P01-cx", "result")[-1], logged("P01-cx", "intent")[-1],
                          evidence.joinpath("P01-cx/T2-3.png").is_file()), (1, ("T2", 3), ("T2", 4), True))

        # The reason is on record before the run is asked to stop, so a launcher killed after asking loses none of it.
        first, _ = self.launch_in_background("run", "--runs", "P02-opus", "--grace", 2)
        self.wait_for(lambda: any(e["run"] == "P02-opus" for e in self.events("term")), "P02-opus to be asked to stop")
        first.kill()
        first.wait()
        before, cli = len(self.starts()), self.starts()[-1]["pid"]
        self.wait_for(lambda: self.gone(cli), "P02-opus to be ended by its watchdog")
        r = self.launch("run")
        # A step under an attempt number of the panellist's own is one more step of the task: the count goes on.
        self.assertIn("P02-opus: limited: step limit: task T1, step 4 of 3", r.stdout)
        self.assertEqual([e["run"] for e in self.starts(before)], ["P02-cx"])  # "run" restarts no limited run
        # It is continued like any limited run, and the task that was under way starts again as a new attempt.
        r = self.launch("resume", "--runs", "P01-cx", "--extend")
        self.assertEqual((self.states()["P01-cx"], '"attempt": 2' in self.starts()[-1]["stdin"]), ("done", True),
                         r.stdout + r.stderr)
        # A log whose form earns two notes, one of them with a ";" of its own: steps that go backwards twice.
        log = evidence / "P02-cx/steps.jsonl"
        log.write_text(log.read_text() + "not an entry\n" + "".join(
            json.dumps({"task": "T1", "attempt": 1, "step": n, "phase": "intent"}) + "\n" for n in (1, 2, 1)))

        rows, quant, report = self.analysed()
        self.assertEqual({k: (x["stopped"], x["steps"], x["attempts"]) for k, x in rows.items()}, {
            ("P01-opus", "T1"): ("ran out of steps", "3", "1"), ("P01-opus", "T2"): ("completed", "2", "1"),
            ("P01-cx", "T1"): ("completed", "2", "1"), ("P01-cx", "T2"): ("completed", "2", "2"),
            ("P02-opus", "T1"): ("step limit", "3", "1"), ("P02-opus", "T2"): ("not reached", "0", "0"),
            ("P02-cx", "T1"): ("completed", "2", "1"), ("P02-cx", "T2"): ("completed", "2", "1")})
        # Both ways of running out of steps on T1 make its form the first stuck point: the screen that held each
        # run, with the steps that left it there. The run that went for help last did not end on that screen.
        top = quant["stuck_points"]["points"][0]
        self.assertEqual((top["task"], top["page"], [(e["run"], e["end"], e["ended_on"], e["steps"], e["screenshots"])
                                                    for e in top["evidence"]]),
                         ("T1", "/T1/form", [
                             ("P01-opus", "ran out of steps", "/help", [1, 2], ["T1-1.png", "T1-2.png"]),
                             ("P02-opus", "step limit", "/T1/form", [1, 2, 3], ["T1-1.png", "T1-2.png", "T1-3.png"])]))
        self.assertIn("- P01-opus: ran out of steps after step 3 on `/help`, reached from here. 2 of its last 3 "
                      "steps left it here: steps 1, 2 (`T1-1.png`, `T1-2.png`)", report)
        self.assertIn("| T1 | 3 | 4 | 2 of 4 (50%) | no check |", report)  # the stopped run counts against the task
        self.assertIn("- P01-cx: entries for a task this study does not have (T99).", report)
        # What is not a step, or is of an attempt the launcher never gave, hides none of the steps above.
        self.assertIn("- P02-opus: 1 entry with an attempt number the launcher did not give its task", report)
        # Each note reaches the analysis whole, whatever it holds: two notes are two problems.
        self.assertEqual([p["problem"] for p in quant["step_logs"]["problems"] if p["run"] == "P02-cx"],
                         ["1 line that cannot be read as an entry (line 9)", "step numbers that go backwards "
                          "(task T1, step 1 after step 2; task T1, step 1 after step 2)"])

    def test_step_log_that_is_emptied_or_cannot_be_read_as_the_runs_own_does_not_switch_the_step_backstop_off(self):
        self.usability({
            # Begins two steps of T1, empties its step log, and begins two more under numbers the limit allows.
            "P01-opus": [["act:2", "wait:read", "empty", "intent:3", "intent:1", "hang"]],
            # Puts a link where its step log was, so that nothing it does from then on can be read as its own.
            "P01-cx": [["act:1", "link", "hang"]],
        }, tasks=self.tasks(steps=3))
        launcher, output = self.launch_in_background("run")

        def begun(run_id):  # the steps of each task that the launcher has counted in the run's attempt
            attempts = self.entries()[run_id].get("attempts") or [{}]
            return (attempts[-1].get("steps") or {}).get("begun")

        self.wait_for(lambda: begun("P01-opus") == {"T1": 2}, "the launcher to have counted the first two steps")
        self.release("read")
        self.assertEqual(launcher.wait(timeout=30), 1)
        entries, said = self.entries(), output.read_text()
        # The count is the launcher's own, so it goes on from the two steps it had read: four begun, of three.
        # And a log that cannot be read as the run's own leaves nothing to count, so that run is stopped too.
        self.assertEqual({run_id: (e["state"], e.get("limited_by"), e["reason"]) for run_id, e in entries.items()}, {
            "P01-opus": ("limited", "steps", "step limit: task T1, step 4 of 3"),
            "P01-cx": ("limited", "steps", "step limit: its step log cannot be read as the run's own (it is a "
                                           "symbolic link), so its steps cannot be counted")}, said)
        self.assertRegex(said, r"P01-opus: its step log was (cut short, to 0 of|changed at line 1, among) the 4 "
                               r"lines the launcher had read")
        self.assertIn("P01-cx: stopping, step limit: its step log cannot be read as the run's own", said)

    def test_claim_that_the_success_check_denies_is_flagged_and_a_check_that_fails_to_run_is_no_verdict(self):
        self.usability({"P01-cx": [["write:1", "outcome:gave up", "write:all"]]}, tasks=self.tasks(checked=True),
                       accounts={}, synthesis={"analyst": {"runner": "claude"}, "writer": {"runner": "claude"}})
        verdicts = self.sd / "checks.json"  # exit codes: 1 says not completed, 3 is no verdict at all
        verdicts.write_text(json.dumps({"P01-opus": {"T1": 1}, "P01-cx": {"T1": 3}}))
        r = self.launch("run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("P01-cx: SUCCESS CHECK FAILED TO RUN: the success check of task T1 exited with code 3", r.stdout)
        # A success check is the lead's: no panellist can read of one.
        self.assertEqual([str(f) for f in self.sd.joinpath("panel").rglob("*")
                          if f.is_file() and b"account.py" in f.read_bytes()], [])
        rows, quant, report = self.analysed()
        self.assertEqual({k: (x["claimed"], x["checked"], x["mismatch"]) for k, x in rows.items()}, {
            ("P01-opus", "T1"): ("completed", "no", "check_denies"), ("P01-opus", "T2"): ("completed", "yes", ""),
            ("P01-cx", "T1"): ("completed", "error", ""), ("P01-cx", "T2"): ("gave up", "yes", "check_passes")})
        t1 = quant["completion"]["by_task"]["T1"]  # two claims, one verdict, and the check that failed is in neither
        self.assertEqual((t1["claimed"], t1["checked"], t1["verdicts"], t1["check_errors"], t1["mismatches"]),
                         (2, 0, 1, 1, 1))
        self.assertEqual([(m["run"], m["task"], m["mismatch"]) for m in quant["completion"]["mismatches"]],
                         [("P01-opus", "T1", "check_denies"), ("P01-cx", "T2", "check_passes")])
        self.assertIn("| P01-opus | Person 1 | opus | T1 | completed | not completed | claimed completed, and the "
                      "check says it was not |", report)
        # Once the check is mended, the lead runs it again by hand. The run's account is torn down by then, so
        # only the task with no verdict is tried: a verdict made while the account was there is kept.
        verdicts.write_text(json.dumps({"P01-cx": {"T2": 3}}))
        r = self.launch("check", "--runs", "P01-cx")
        self.assertEqual((r.returncode, self.entries()["P01-cx"]["checks"]["T1"]["checked"]), (0, True), r.stdout)
        self.assertIn("P01-cx: task T2 kept: the account is gone, so the check cannot be run again", r.stdout)
        self.assertEqual((self.entries()["P01-cx"]["checks"]["T2"]["checked"], self.account_calls("P01-cx")[-2:]),
                         (True, ["teardown", "check:T1:gone"]))
        r = self.launch("check", "--runs", "P01-cx", "--force")  # unless the lead says to run it all the same
        self.assertIn("The earlier verdict, completed, was replaced", r.stdout)
        self.assertEqual((r.returncode, self.entries()["P01-cx"]["checks"]["T2"]["checked"]), (1, None), r.stdout)

        # The writer waits for the analysts, and an analyst is given each run's step log and screenshots to read.
        refused = self.launch("run", "--role", "writer")
        self.assertIn("The writer waits for the analysts: analyst-1 is pending", refused.stderr)
        r = self.launch("run", "--role", "analyst")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        brief = self.sd.joinpath("prompts/analyst-1.md").read_text()
        for run_id, e in self.entries().items():
            if e["role"] == "panellist":
                self.assertIn(f"- `{self.sd / e['file']}`, with its step log and screenshots in "
                              f"`{self.sd}/panel/evidence/{run_id}/`", brief)
        r = self.launch("run", "--role", "writer")
        self.assertEqual((r.returncode, self.states()["writer"]), (0, "done"), r.stdout + r.stderr)

    def test_release_lets_go_of_the_account_of_an_unfinished_run_which_is_then_started_only_when_asked_to(self):
        self.usability({"P01-opus": [["write:1", "end:error"], ["act:1", "end:error"], ["act:1", "end:error"],
                                     ["write:all"]]}, accounts={}, tasks=self.tasks(checked=True))
        self.launch("run")
        self.assertEqual((self.states()["P01-opus"], self.account_calls("P01-opus")), ("partial", ["provision"]))
        self.launch("resume")  # cut off again: an unfinished run keeps its account, and is told so
        self.assertEqual((self.states()["P01-opus"], self.account_calls("P01-opus")), ("partial", ["provision"]))
        self.assertIn("signed in to the same test account again", self.starts()[-1]["stdin"])
        # What it got done is checked while the account is whole, then the account goes, once.
        finished = ["check:T1:held", "check:T2:held", "teardown"]
        r = self.launch("release", "--runs", "P01-opus")
        self.assertEqual((r.returncode, self.account_calls("P01-opus")), (0, ["provision", *finished]), r.stdout)
        before = len(self.starts())
        r = self.launch("resume")
        self.assertIn("P01-opus: released by the lead", r.stdout)
        self.assertEqual((self.starts(before), self.states()["P01-opus"], self.account_calls("P01-opus")),
                         ([], "partial", ["provision", *finished]))
        self.assertTrue(next(x for x in self.status()["runs"] if x["run"] == "P01-opus")["released"])
        # Named with --released it is continued after all, with an account of its own again, and its panellist
        # is told the account is another one.
        self.launch("resume", "--runs", "P01-opus", "--released")  # cut off once more
        told = self.starts()[-1]["stdin"]
        self.assertIn("Your test account is a new one", told)
        self.assertNotIn("the same test account", told)
        # The task it had written up is not attempted again, so its check stands as it was made, with the
        # account that is gone, through every later attempt: only the other task is checked on the new one.
        r = self.launch("resume")
        self.assertEqual((self.states()["P01-opus"], "released" in self.entries()["P01-opus"],
                          self.account_calls("P01-opus")),
                         ("done", False, ["provision", *finished, "provision", "check:T2:held", "teardown"]), r.stdout)
        self.assertEqual(sorted(self.entries()["P01-opus"]["checks"]), ["T1", "T2"])

    # ---- usability: secrets and the archive (check_runs.py, archive.py)

    def test_secret_value_in_a_persona_file_or_step_log_fails_its_run_and_is_never_printed(self):
        self.usability(personas=2, accounts={})
        r = self.launch("run", "--runs", "P01-opus,P01-cx,P02-opus")
        self.assertEqual(self.states(), {"P01-opus": "done", "P01-cx": "done", "P02-opus": "done", "P02-cx": "pending"},
                         r.stdout + r.stderr)
        # Each run's account is torn down by now, and its secrets are off every record: the scan knows them all the same.
        self.assertEqual([json.loads(f.read_text())["secrets"] for f in self.sd.glob("accounts/P*.json")], [{}] * 3)
        files = {run_id: self.sd / e["file"] for run_id, e in self.entries().items()}
        log = self.sd / "panel/evidence/P01-cx/steps.jsonl"
        # One run was shown another's password, one logged its own, and the synthesis quotes a third.
        files["P01-opus"].write_text(files["P01-opus"].read_text() + "The page said the password is pw-P01-cx.\n")
        log.write_text(log.read_text().replace("It moved on.", "The field showed pw-P01-cx.", 1))
        # And a password where a task id belongs, which a note on the log's form would repeat.
        log.write_text(log.read_text() + json.dumps({"task": "pw-P02-opus", "step": 1, "phase": "intent"}) + "\n")
        self.sd.joinpath("analysis/SYNTHESIS.md").write_text("# Findings\n\nOne run read out pw-P02-opus.\n")
        # An identifier may be seen: a run's own says nothing, and another run's is worth a look.
        files["P02-opus"].write_text(files["P02-opus"].read_text() + "I was test-P02-opus, and saw test-P01-opus.\n")

        def checked():
            r = run("check_runs.py", self.sd, check=False)
            return r.returncode, r.stdout + r.stderr + self.sd.joinpath("analysis/checks.md").read_text()

        code, said = checked()
        self.assertEqual(code, 1, said)
        self.assertRegex(said, r"\| P01-opus \| a secret value in its persona file: line \d+ "
                               r"\(a secret of P01-cx's account \(\"password\"\)\) \|")
        self.assertRegex(said, r"\| P01-cx \| a secret value in its step log: line 2 "
                               r"\(a secret of P01-cx's account \(\"password\"\)\); line 9 "
                               r"\(a secret of P02-opus's account \(\"password\"\)\) \|")
        self.assertIn("entries for a task this study does not have ((a value that is not a task id, 11 characters))",
                      said)
        self.assertRegex(said, r"\| P02-opus \| - \| .*names an identifier of P01-opus's test account "
                               r"\(\"test-P01-opus\"\)")
        self.assertIn("A secret value in analysis/SYNTHESIS.md: line 3 (a secret of P02-opus's account", said)
        self.assertNotIn("pw-", said)
        run("extract_scores.py", self.sd)  # nor is it copied into what the analysis reads
        self.assertNotIn("pw-", "".join(f.read_text() for f in self.sd.glob("analysis/*.csv")))

    def test_evidence_that_cannot_be_read_as_the_runs_own_fails_the_checks_and_is_never_archived(self):
        self.usability()
        self.launch("run")
        self.assertEqual(self.states(), {"P01-opus": "done", "P01-cx": "done"})
        evidence, outside, dest = self.sd / "panel/evidence", self.tmp / "outside", self.tmp / "archive/panel/round-1"

        def unreadable():  # a step log that may not be read: nothing says it holds no secret
            evidence.joinpath("P01-cx/steps.jsonl").chmod(0)
            return lambda: evidence.joinpath("P01-cx/steps.jsonl").chmod(0o644)

        def linked():  # a panellist put a link where its evidence folder was: what it points at is not the study's
            evidence.joinpath("P01-cx").rename(outside)
            evidence.joinpath("P01-cx").symlink_to(outside)
            return lambda: (evidence.joinpath("P01-cx").unlink(), outside.rename(evidence / "P01-cx"))

        cases = {"a step log that may not be read": (unreadable, "panel/evidence/P01-cx/steps.jsonl: Permission denied"),
                 "an evidence folder that is a link": (linked, "panel/evidence/P01-cx is a symbolic link")}
        for name, (change, named) in cases.items():
            if name.startswith("a step log") and not os.geteuid():
                continue  # nothing is unreadable to root
            with self.subTest(name):
                undo = change()
                checked = run("check_runs.py", self.sd, check=False)
                archived = subprocess.run([sys.executable, str(self.scripts / "archive.py"), str(self.sd), "--dest",
                                           str(dest)], capture_output=True, text=True)
                undo()
                self.assertRegex(checked.stdout, r"\| P01-cx \| its step log could not be scanned for secrets \(")
                self.assertEqual((checked.returncode, archived.returncode, dest.exists()), (1, 1, False),
                                 archived.stdout + archived.stderr)
                self.assertIn(named, archived.stderr)
        self.assertEqual(run("check_runs.py", self.sd, check=False).returncode, 0)  # as it was: nothing blocks

    def test_teardown_that_failed_or_was_cut_short_is_finished_before_its_run_gets_another_account(self):
        self.usability({"P01-opus": [["end:error"], ["write:all"]],  # failed, and its account cannot be torn down
                        "P01-cx": [["write:1", "end:error"]]},       # partial: it keeps its account
                       accounts={})
        self.sd.joinpath("teardown-fails").touch()
        r = self.launch("run")
        # A failed run is retried with a new account. While the old one cannot be torn down it is not retried.
        self.assertEqual((self.states(), [e["run"] for e in self.starts()].count("P01-opus"),
                          self.account_calls("P01-opus"), self.account_calls("P01-cx")),
                         ({"P01-opus": "failed", "P01-cx": "partial"}, 1, ["provision", "teardown"], ["provision"]),
                         r.stdout + r.stderr)
        # The other run's teardown was begun by a command that was killed after the product had removed the
        # account and before the files were seen to: what such a kill leaves on record.
        record, state = self.sd / "accounts/P01-cx.json", self.sd / "states/P01-cx.json"
        left = json.loads(record.read_text())
        record.write_text(json.dumps({**left, "cleanup": {"began": 1, "remove": [left["state"]], "rewrite": []}}))
        self.sd.joinpath("teardown-fails").unlink()
        before = len(self.starts())
        r = self.launch("run", "--runs", "P01-opus")
        # Any launcher command finishes it first, though its run is unfinished: the account is not one to resume in.
        after = json.loads(record.read_text())
        self.assertEqual((self.account_calls("P01-cx"), bool(after["torn_down"]), after["secrets"], "cleanup" in after,
                          state.exists()), (["provision", "teardown"], True, {}, False, False), r.stdout + r.stderr)
        # And the failed run is torn down again first, then given a new account and started.
        self.assertEqual((self.states()["P01-opus"], self.account_calls("P01-opus"),
                          [e["run"] for e in self.starts(before)], self.entries()["P01-opus"]["account"]["times"]),
                         ("done", ["provision", "teardown", "teardown", "provision", "teardown"], ["P01-opus"], 2),
                         r.stdout + r.stderr)

    def test_provision_command_that_outlived_its_launcher_is_stopped_before_the_run_is_provisioned_again(self):
        self.usability({"P01-opus": [["write:1", "end:error"], ["wait:hold", "write:all"]]}, personas=3, accounts={},
                       models=[self.CLAUDE])
        gate, noted = self.sd / "provision-waits", self.sd / "provision.pid"
        gate.touch()
        first, _ = self.launch_in_background("run", "--runs", "P01-opus")
        self.wait_for(lambda: noted.exists() and not gate.exists(), "the provision command to be under way")
        command = int(noted.read_text())
        self.addCleanup(lambda: self.gone(command) or os.kill(command, signal.SIGKILL))
        first.kill()
        first.wait()
        self.assertFalse(self.gone(command))  # in a session of its own, it outlives its launcher
        r = self.launch("run", "--runs", "P01-opus")
        # Stopped and waited for, then cleared up after, and only then is the run provisioned again: the two
        # never run side by side, and one account is in force for the run that follows.
        self.assertEqual((self.gone(command), self.account_calls("P01-opus"), self.states()["P01-opus"]),
                         (True, ["provision", "stopped", "teardown", "provision"], "partial"), r.stdout + r.stderr)
        self.assertIn(f"accounts.provision for P01-opus ran. It was still running (pid {command}) and was stopped",
                      r.stdout)
        records = [json.loads(f.read_text()) for f in self.sd.glob("accounts/P*.json")]
        self.assertEqual([(x["run"], x["times"], bool(x["secrets"])) for x in records], [("P01-opus", 1, True)])

        # A run that is alive under its watchdog, with no launcher, when the next command is left behind.
        resumed, _ = self.launch_in_background("resume", "--runs", "P01-opus")
        self.wait_for(lambda: self.waiting() == {"P01-opus"}, "P01-opus to be under way again")
        resumed.kill()
        resumed.wait()
        alive = self.starts()[-1]["pid"]
        # A command can leave a process of its own behind: here it ends on a SIGTERM that its worker ignores. With
        # the command gone nothing proves whose the worker is, so it is not killed, and nothing is run beside it.
        gate.touch()
        self.sd.joinpath("worker-stays").touch()
        noted.unlink()
        second, _ = self.launch_in_background("run", "--runs", "P02-opus")
        self.wait_for(lambda: noted.exists() and not gate.exists(), "the second provision command to be under way")
        command, worker = int(noted.read_text()), int(self.sd.joinpath("worker.pid").read_text())
        for pid in (command, worker):
            self.addCleanup(lambda pid=pid: self.gone(pid) or os.kill(pid, signal.SIGKILL))
        second.kill()
        second.wait()
        os.killpg(command, signal.SIGTERM)
        self.wait_for(lambda: self.gone(command), "the second provision command to end")
        record, calls = self.sd / "accounts/command.running", self.account_calls()
        on_record = record.read_bytes()
        r = self.launch("run", "--runs", "P02-opus")
        self.assertEqual((r.returncode, self.gone(worker), self.account_calls(),
                          record.read_bytes() if record.exists() else None), (1, False, calls, on_record),
                         r.stdout + r.stderr)
        self.assertIn(f"process group {command} still holds pid {worker}", r.stderr)
        self.assertIn(f"ps -o pid,pgid,command -p {worker} ", r.stderr)
        # "stop" stops the run that is alive all the same. It starts no command of the study beside the worker
        # either, and then says what holds the study up.
        r = self.launch("stop")
        self.assertEqual((self.gone(alive), self.states()["P01-opus"], r.returncode,
                          f"process group {command} still holds pid {worker}" in r.stderr, self.gone(worker),
                          self.account_calls(), record.read_bytes() if record.exists() else None),
                         (True, "partial", 1, True, False, calls, on_record), r.stdout + r.stderr)
        # Once the lead has stopped it the group is empty, and the next command carries on from the record.
        os.kill(worker, signal.SIGKILL)
        self.wait_for(lambda: self.gone(worker), "the worker to end")
        r = self.launch("run", "--runs", "P02-opus")
        self.assertEqual((record.exists(), self.account_calls("P02-opus"), self.states()["P02-opus"]),
                         (False, ["provision", "stopped", "teardown", "provision", "teardown"], "done"),
                         r.stdout + r.stderr)

        # A command holds a lock for as long as it or anything it started lives, which every shell sees whatever
        # processes it sees. Here its worker leaves the command's group for a session of its own, and keeps the lock.
        gate.touch()
        self.sd.joinpath("worker-leaves").touch()
        noted.unlink()
        third, _ = self.launch_in_background("run", "--runs", "P03-opus")
        self.wait_for(lambda: noted.exists() and not gate.exists(), "the third provision command to be under way")
        command, worker = int(noted.read_text()), int(self.sd.joinpath("worker.pid").read_text())
        for pid in (command, worker):
            self.addCleanup(lambda pid=pid: self.gone(pid) or os.kill(pid, signal.SIGKILL))
        third.kill()
        third.wait()
        on_record, calls = record.read_bytes(), self.account_calls()
        try:
            here = os.readlink("/proc/self/ns/pid")
        except OSError:
            here = None  # none is named where there is no /proc, as on macOS: a command's record names none there
        self.assertEqual(json.loads(on_record).get("namespace"), here)
        # To a shell in another process namespace, as on the other side of a sandbox, the id on record names no
        # process, or someone else's. Here that shell is this one, with the record naming another namespace. The
        # lock is held, so the command is running where this shell cannot look: nothing is looked up or
        # signalled under its id, and nothing is run beside it.
        if here:
            apart = json.dumps({**json.loads(on_record), "namespace": "pid:[0]"}).encode()
            record.write_bytes(apart)
            r = self.launch("run", "--runs", "P03-opus")
            self.assertEqual((r.returncode, self.gone(command), self.account_calls(),
                              record.read_bytes() if record.exists() else None), (1, False, calls, apart),
                             r.stdout + r.stderr)
            self.assertIn("accounts.provision for P03-opus ran, and that command, or something it started, is still "
                          "running where this shell cannot look: it holds the command's lock", r.stderr)
            self.assertIn(f"Run the launcher from the shell that started that command. {SANDBOX_HINT}", r.stderr)
            record.write_bytes(on_record)
        # The shell that started it stops the command. The worker is in no group the launcher can list, and its
        # lock says that it is there all the same: it holds up the next command, as one found in the group does.
        r = self.launch("run", "--runs", "P03-opus")
        self.assertEqual((r.returncode, self.gone(command), self.gone(worker), self.account_calls(),
                          record.read_bytes() if record.exists() else None),
                         (1, True, False, [*calls, "stopped P03-opus"], on_record), r.stdout + r.stderr)
        self.assertIn(f"process group {command} is empty, but the command's lock "
                      f"({self.sd.resolve() / 'accounts/command.lock'}) is still held", r.stderr)
        # Once nothing holds the lock the command has probably ended, with all it started: a sandbox that ends
        # takes every process in it. That is no proof, as a process that closed the file it was given holds no
        # lock, and this shell cannot look where the command ran. So a record of another namespace is never
        # cleared from here: it is kept as it is, nothing is run beside what may be left, and its ids are not
        # looked up or signalled, which here are those of a process of this shell that has nothing to do with
        # the study. The message says what the lead is to do, and the lead does it.
        os.kill(worker, signal.SIGKILL)
        self.wait_for(lambda: self.gone(worker), "the worker to end")
        bystander = subprocess.Popen([sys.executable, "-c", "import sys\nsys.stdin.read()"], stdin=subprocess.PIPE,
                                     start_new_session=True)  # the leader of a group, which a signal would reach
        self.addCleanup(bystander.communicate)  # which ends it
        if here:
            apart = json.dumps({**json.loads(on_record), "namespace": "pid:[0]", "pid": bystander.pid,
                                "identity": run_watchdog.identity(bystander.pid)}).encode()
            record.write_bytes(apart)
            calls, lock = self.account_calls(), self.sd.resolve() / "accounts/command.lock"
            r = self.launch("run", "--runs", "P03-opus")
            self.assertEqual((r.returncode, bystander.poll(), self.account_calls(),
                              record.read_bytes() if record.exists() else None), (1, None, calls, apart),
                             r.stdout + r.stderr)
            self.assertIn(f"accounts.provision for P03-opus ran. Nothing holds the command's lock ({lock}), so it "
                          "has probably ended, but this shell cannot look where it ran to be sure", r.stderr)
            self.assertIn(f"Run the launcher from the shell that started that command, which can look. {SANDBOX_HINT} "
                          "If that shell was in a sandbox that has ended, the command ended with it: delete "
                          f"{self.sd.resolve() / 'accounts/command.running'} (and {lock}, when it is there) and run "
                          "this again.", r.stderr)
            record.unlink()
            lock.unlink()
        # With no record the command is over, and what it left is cleared up as after any that was cut short:
        # the run's own record says that its provisioning did not finish, so it is torn down before the next.
        r = self.launch("run", "--runs", "P03-opus")
        self.assertEqual((bystander.poll(), record.exists(), self.account_calls("P03-opus"), self.states()["P03-opus"]),
                         (None, False, ["provision", "stopped", "teardown", "provision", "teardown"], "done"),
                         r.stdout + r.stderr)

    def test_usability_archive_keeps_the_evidence_without_a_secret_or_a_screenshot_that_could_show_one(self):
        runs = ("P01-opus", "P01-cx", "P02-opus", "P02-cx")
        accounts = {x: {"identifiers": {"username": f"user-{x}"}, "secrets": {"password": f"pw-{x}"}} for x in runs}
        self.usability({"P02-cx": [["write:1"], ["write:all"]]}, personas=2, accounts={"map": accounts})
        self.launch("run", "--runs", "P01-opus,P01-cx,P02-opus")  # these three are given no secret
        self.settings({"accounts": {"map": accounts, "signin": "panellist"}})
        self.launch("run", "--runs", "P02-cx")  # this one is given its password to type, and stops after one task
        self.assertEqual(self.states(), {**dict.fromkeys(runs, "done"), "P02-cx": "partial"})
        dest = self.tmp / "archive/panel/round-1"

        def archive(path=os.environ.get("PATH", "")):
            return subprocess.run([sys.executable, str(self.scripts / "archive.py"), str(self.sd), "--dest", str(dest)],
                                  env={**os.environ, "PATH": path}, capture_output=True, text=True)

        # Refused while a run still has its account, and while a step log holds a secret value: nothing is copied.
        r = archive()
        self.assertIn("The test account of P02-cx is still in force", r.stderr)
        self.assertEqual(self.launch("resume", "--runs", "P02-cx").returncode, 0)
        evidence = self.sd / "panel/evidence"
        log = evidence / "P02-opus/steps.jsonl"
        clean = log.read_text()
        log.write_text(clean.replace("It moved on.", "The field showed pw-P02-cx.", 1))
        r = archive()
        self.assertIn("panel/evidence/P02-opus/steps.jsonl: line 2 (a secret of P02-cx's account", r.stderr)
        self.assertNotIn("pw-", r.stdout + r.stderr)
        self.assertEqual((r.returncode, dest.exists()), (1, False))
        # A panellist can name a folder with one too, and put a link in it that cannot be read. Neither refusal
        # repeats the path: each says where to look as far down as the path may be shown.
        log.write_text(clean)
        named = self.sd / "panel/personas/pw-P02-cx"
        named.mkdir()
        named.joinpath("note.md").write_text("A note.\n")
        named.joinpath("link.md").symlink_to(self.log)
        where = "panel/personas/(a path of 2 names that is not shown, 17 characters): "
        for said in ("it is a symbolic link", "the name of the file or of a folder above it (a secret of P02-cx's"):
            r = archive()
            self.assertIn(where + said, r.stderr)
            self.assertNotIn("pw-", r.stdout + r.stderr)
            self.assertEqual((r.returncode, dest.exists()), (1, False))
            named.joinpath("link.md").unlink(missing_ok=True)  # which leaves the folder's name for the next
        # Nor is a folder passed over that cannot be read: one that cannot be listed is not known to be clean, and
        # nor is a file in one that can be listed and not searched. Each is refused in a sentence.
        self.addCleanup(lambda: named.is_dir() and named.chmod(0o755))  # so that the test's directory can be removed
        for mode, where in ((0, "panel/personas/(a name that is not shown, 9 characters): "),
                            (0o400, "panel/personas/(a path of 2 names that is not shown, 17 characters): ")):
            if not os.geteuid():
                continue  # nothing is unreadable to root
            named.chmod(mode)
            r = archive()
            self.assertIn(where + "Permission denied", r.stderr)
            self.assertNotIn("pw-", r.stdout + r.stderr)
            self.assertEqual((r.returncode, "Traceback" in r.stderr, dest.exists()), (1, False, False))
        # A folder with nothing in it that is kept is not archived, so the secret in its name goes nowhere: it
        # stays there, holding only a name that is left out, for the archive that follows.
        named.chmod(0o755)
        named.joinpath("note.md").unlink()
        named.joinpath(".DS_Store").write_bytes(b"")

        # The second step of P02-opus's first task entered something secret, and its panellist said so.
        entries = [json.loads(line) for line in clean.splitlines()]
        marked = next(e for e in entries if (e["task"], e["step"], e["phase"]) == ("T1", 2, "result"))
        marked["sensitive"] = True
        log.write_text("".join(json.dumps(e) + "\n" for e in entries))
        for shot in evidence.glob("*/*.png"):
            shot.write_bytes(png(40, 20))
        for stray in ("notes.txt", "what I saw (2).txt"):  # the second is not a name that a message repeats
            evidence.joinpath("P01-opus", stray).write_text("Not evidence.\n")
        # What a panellist saw after scrolling is a further view of its step, and evidence like the step's own.
        for view in ("P01-opus/T2-1b.png", "P02-opus/T1-2b.png"):
            evidence.joinpath(view).write_bytes(png(40, 20))
        run("extract_scores.py", self.sd)
        r = archive(str(self.bin))  # a PATH without ImageMagick
        self.assertEqual(r.returncode, 0, r.stderr)
        shots = ["T1-1.png", "T1-2.png", "T2-1.png", "T2-2.png"]
        whole = {f"{x}/{name}" for x in ("P01-opus", "P01-cx") for name in ["steps.jsonl", *shots]}
        self.assertEqual(
            {f.relative_to(dest / "evidence").as_posix() for f in dest.joinpath("evidence").rglob("*") if f.is_file()},
            whole | {"P01-opus/T2-1b.png", "P02-opus/steps.jsonl", "P02-opus/T1-1.png", "P02-opus/T1-2.png.left-out.txt",
                     "P02-opus/T1-2b.png.left-out.txt", "P02-opus/T2-1.png", "P02-opus/T2-2.png", "P02-cx/steps.jsonl",
                     *(f"P02-cx/{name}.left-out.txt" for name in shots)})
        self.assertEqual(dest.joinpath("evidence/P02-opus/steps.jsonl").read_bytes(), log.read_bytes())  # still citable
        self.assertIn("T1-2.png was left out of this archive: task T1, step 2, is marked sensitive",
                      dest.joinpath("evidence/P02-opus/T1-2.png.left-out.txt").read_text())
        self.assertIn("the panellist of P02-cx was given a secret to type",
                      dest.joinpath("evidence/P02-cx/T2-1.png.left-out.txt").read_text())
        # What was passed over is said with its run, which is the study's own word, whatever its name is.
        self.assertIn("(P01-opus/notes.txt, P01-opus/(a name that is not shown, 18 characters))", r.stdout)
        # The folder named with a secret held nothing to keep: it is not in the archive, nor is any empty folder,
        # and no line names it.
        self.assertEqual([str(f) for f in dest.rglob("*") if "pw-" in f.name or f.is_dir() and not any(f.iterdir())],
                         [])
        self.assertNotIn("pw-", r.stdout + r.stderr)
        # Nothing of the accounts travels but the identifiers, and the archive still loads, checks and scores.
        self.assertEqual([f.name for f in dest.iterdir() if f.name in ("panel", "scratch", "accounts", "logs")], [])
        self.assertEqual([str(f) for f in dest.rglob("*") if f.is_file()
                          and (b"pw-" in f.read_bytes() or f.name == "account.json")], [])
        self.assertEqual(json.loads(dest.joinpath("study.json").read_text())["accounts"]["map"]["P02-cx"],
                         {"identifiers": {"username": "user-P02-cx"},
                          "secrets": {"password": "(removed from the archive)"}})
        self.assertIn("study.json: the 4 secrets of accounts.map were replaced", r.stdout)
        checks = run("check_runs.py", dest).stdout
        self.assertIn("4 run files of 4 expected; 0 with blocking problems", checks)
        self.assertNotIn("evidence folder", checks)  # a note in place of a screenshot is no stray file, and none is missing
        self.assertIn("8 score rows from 4 runs; 0 runs incomplete", run("extract_scores.py", dest).stdout)
        # Without ImageMagick each screenshot is copied whole, and with it each is brought down to half its size.
        self.assertIn("ImageMagick is not installed", r.stdout)
        self.assertEqual(dest.joinpath("evidence/P01-opus/T1-1.png").read_bytes(), png(40, 20))
        if shutil.which("magick") or shutil.which("convert"):
            self.assertEqual(archive().returncode, 0)
            self.assertEqual(struct.unpack(">II", dest.joinpath("evidence/P01-opus/T1-1.png").read_bytes()[16:24]),
                             (20, 10))

    def test_archive_of_a_study_it_cannot_write_turns_launchers_away_until_the_round_is_copied(self):
        if not os.geteuid():
            self.skipTest("root can write to a read-only directory")
        self.usability({"P01-opus": [["write:all", "wait:never"]]}, models=[self.CLAUDE])
        first, _ = self.launch_in_background("run", "--poll", 30)
        self.wait_for(lambda: self.waiting() == {"P01-opus"}, "the run to have written its file")
        first.kill()
        first.wait()
        # The launcher was killed, and its run with it, as a sandbox that ends takes them: nothing of the study
        # is alive, and the run is still on record as running.
        for line in self.sd.joinpath("logs/P01-opus.1.pid").read_text().splitlines()[:2]:  # its watchdog, then its CLI
            os.kill(int(line.split()[0]), signal.SIGKILL)
        self.wait_for(lambda: self.processes() == {"P01-opus": "gone"}, "the processes of the run to have gone")
        for shot in self.sd.glob("panel/evidence/*/*.png"):
            shot.write_bytes(png(40, 20))
        # An ImageMagick that waits to be told to go on, and says that it was asked: the archive is then in the
        # middle of its copy, for as long as the test likes. It reads no screenshot, so each is copied whole.
        tools, lock_file, dest = self.tmp / "tools", self.sd / ".launch.lock", self.tmp / "archive/panel/round-1"
        tools.mkdir()
        tools.joinpath("magick").write_text(
            f"#!{sys.executable}\nimport sys, time\nfrom pathlib import Path\nhere = Path(__file__).parent\n"
            "(here / 'copying').touch()\ngive_up = time.time() + 30\n"
            "while not (here / 'go').exists() and time.time() < give_up:\n    time.sleep(0.01)\nsys.exit(1)\n")
        tools.joinpath("magick").chmod(0o755)

        def archive(path):
            return subprocess.Popen(
                [sys.executable, str(self.scripts / "archive.py"), str(self.sd), "--dest", str(dest)],
                env={**os.environ, "PATH": str(path)}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # What a sandbox that shows the study read-only gives the archive: nothing of it can be written, the lock
        # file least of all, so the launcher's lock is not to be had.
        modes = {path: stat.S_IMODE(path.stat().st_mode) for path in (self.sd, lock_file)}
        aside = self.tmp / "lock-aside"
        try:
            # With no lock file to share, as in a study from before a study kept its lock file, nothing would
            # keep a launcher from a study that may be at work: one with a run on record as running.
            lock_file.rename(aside)
            self.sd.chmod(modes[self.sd] & ~0o222)
            unprotected = archive(self.bin)
            said = unprotected.communicate(timeout=30)[1]
            self.sd.chmod(modes[self.sd])
            aside.rename(lock_file)
            self.assertEqual((unprotected.returncode, dest.exists()), (1, False), said)
            self.assertIn("1 run of this study is on record as running (P01-opus), and this shell can neither write "
                          f"the study nor hold a lock on {lock_file.resolve()}, so the study cannot be protected from "
                          "a launcher while it is copied. Nothing was archived.", said)
            # A launcher that settles the run and ends by itself leaves the study at rest, with the lock file
            # still there: the archive keeps a shared lock on it while it copies.
            r = self.launch("stop")
            self.assertEqual((r.returncode, self.states()["P01-opus"] == "running", lock_file.is_file()),
                             (0, False, True), r.stdout + r.stderr)
            before, settled = len(self.starts()), self.states()
            for path, mode in modes.items():
                path.chmod(mode & ~0o222)
            copying = archive(tools)
            self.background.append(copying)
            self.wait_for(lambda: tools.joinpath("copying").exists() or copying.poll() is not None,
                          "the archive to be copying the round")
            # A launcher outside the sandbox can write the study, as this one can from here on. It is not given
            # the study while the round is copied: it waits, starts nothing, and says what is in its way.
            for path, mode in modes.items():
                path.chmod(mode)
            r = self.launch("run")
            self.assertEqual((r.returncode, len(self.starts()) - before, self.states(), copying.poll()),
                             (1, 0, settled, None), r.stdout + r.stderr)
            self.assertEqual(r.stderr, "Something is reading this study and keeps a shared lock on "
                                       f"{lock_file.resolve()} meanwhile, as archive.py does while it copies a study "
                                       'from a shell that cannot write it, so "run" did nothing. Try again once it '
                                       "has finished.\n")
        finally:
            tools.joinpath("go").touch()
            for path, mode in modes.items():
                if path.exists():
                    path.chmod(mode)
            if aside.exists():
                aside.rename(lock_file)
        said = "".join(copying.communicate(timeout=30))
        # The round is archived as it was when the archive looked. The lock file is left where it was found, as
        # it is the study's, and is no part of the round. The next launcher command has the study.
        self.assertEqual((copying.returncode, dest.joinpath("evidence/P01-opus/T1-1.png").read_bytes(),
                          json.loads(dest.joinpath("runs.json").read_text())[0]["state"], lock_file.is_file(),
                          dest.joinpath(".launch.lock").exists()),
                         (0, png(40, 20), settled["P01-opus"], True, False), said)
        r = self.launch("status")
        self.assertIn("Launcher: not running\n", r.stdout)

    # ---- follow-up questions (followup.py)

    def followup(self, *args):
        return [self.python, str(self.scripts / "followup.py"), str(self.sd), *map(str, args)]

    def ask(self, question, *args, wait=True):
        """Put a follow-up question with followup.py, to its end. With wait false, start it and
        leave it running: returns the process."""
        file = self.tmp / "question.md"
        file.write_text(question)
        command = self.followup("ask", "--question-file", file, *args, "--poll", "0.02", "--grace", "0.3")
        if wait:
            return subprocess.run(command, env=self.env, capture_output=True, text=True, timeout=60)
        self.background.append(subprocess.Popen(command, env=self.env, stdout=subprocess.DEVNULL,
                                                stderr=subprocess.DEVNULL))
        return self.background[-1]

    def asked(self):
        return json.loads(self.sd.joinpath("followups.json").read_text())

    def extracted(self):
        """What extract_scores.py writes: every score and ranking, and each run's state and progress.
        What it printed is kept in self.extract_said."""
        self.extract_said = run("extract_scores.py", self.sd).stdout
        return {name: self.sd.joinpath("analysis", name).read_text()
                for name in ("scores.csv", "rankings.csv", "runs.csv")}

    def test_follow_up_reaches_the_original_session_and_appends_one_section_without_changing_a_score(self):
        self.study({"P01-opus": [["write:all"], ["followup"]],  # writes its section
                    "P01-cx": [["write:all"], ["end:ok"]]},     # only replies
                   personas=1, leak_terms=["tenant", "it depends"],
                   synthesis={"analyst": {"runner": "claude"}, "writer": {"runner": "claude"}})
        self.assertEqual(self.launch("run").returncode, 0)
        sessions = {run_id: e["session"] for run_id, e in self.entries().items()}
        scores = self.extracted()
        first = "Would you pay for it \u2014 as a tenant?"  # the lead's dash and leak term, not the panellist's
        r = self.ask(f"{first}\nSay how much.\n", "--runs", "all")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # Each run was continued in the session it reviewed in, and got the question word for word.
        sent = self.starts(since=2)
        self.assertEqual({e["run"]: (e["resumed"], e["session"]) for e in sent},
                         {run_id: (True, session) for run_id, session in sessions.items()})
        self.assertTrue(all(f"\n{first}\nSay how much.\n" in e["stdin"] for e in sent))
        # One section each, by the panellist or, for the one that only replied, from its reply.
        files = {run_id: self.sd.joinpath(e["file"]).read_text() for run_id, e in self.entries().items()}
        self.assertEqual({run_id: text.count("## Follow-up") for run_id, text in files.items()},
                         {"P01-opus": 1, "P01-cx": 1})
        self.assertIn(f"## Follow-up 1\n\n> {first}\n> Say how much.\n\ncodename=NONE; skills=0; "
                      "agents=yes\n\n(Taken from the panellist's reply", files["P01-cx"])
        # No score moved, and the runs are as finished as they were, to the launcher and to the analysis.
        self.assertEqual(self.extracted(), scores)
        self.assertEqual(self.states(), {"P01-opus": "done", "P01-cx": "done"})
        self.assertEqual({r["run"]: (r["state"], r["attempts"], r["followups"]) for r in self.status()["runs"]},
                         {"P01-opus": ("done", 1, [1]), "P01-cx": ("done", 1, [1])})
        # The checks read the answers and not the question quoted above them: nothing is noted of the
        # follow-up or of the lead's words, and no file was changed by a run not its own.
        checked = run("check_runs.py", self.sd)
        self.assertNotRegex(checked.stdout, "dashes|tenant|follow-up|changed while")
        self.assertRegex(checked.stdout, r"P01-opus \|.*leak terms: it depends \|")
        followup, = self.asked()
        self.assertEqual((followup["n"], followup["question"]), (1, f"{first}\nSay how much."))
        self.assertAlmostEqual(followup["asked"], time.time(), delta=60)
        self.assertEqual({x["run"]: (x["outcome"], x["attempt"], x["session"]) for x in followup["runs"]},
                         {"P01-opus": ("answered", 2, sessions["P01-opus"]),
                          "P01-cx": ("answered from the reply", 2, sessions["P01-cx"])})
        # The follow-up attempts are in the usage record under a role of their own, and in no run's row.
        usage = json.loads(self.launch("usage", "--json").stdout)
        self.assertEqual(({r["run"]: r["attempts"] for r in usage["runs"]},
                          {r["run"]: (r["attempts"], r["followups"]) for r in usage["followups"]}),
                         ({"P01-opus": 1, "P01-cx": 1}, {"P01-opus": (1, [1]), "P01-cx": (1, [1])}))
        self.assertEqual([(r["role"], r["runs"], r["attempts"]) for r in usage["roles"]],
                         [("panellist", 2, 2), ("follow-up", 2, 2)])
        self.assertIn("| follow-up | 2 | - | 2 |", self.sd.joinpath("analysis/usage.md").read_text())
        self.assertEqual((self.plan()["followups"]["asked"], self.status()["followups"]), (1, 1))
        # The analyst and the writer are told what was asked, and that an answer is cited as prompted.
        jobs = len(self.starts())
        self.assertEqual((self.launch("run", "--role", "analyst").returncode,
                          self.launch("run", "--role", "writer").returncode), (0, 0))
        for brief in (e["stdin"] for e in self.starts(since=jobs)):
            self.assertIn(f"\n- Follow-up 1, asked of P01-opus and P01-cx: {first} Say how much.\n", brief)
            self.assertIn("prompted by a question", brief)
        # An archived round keeps the record of what was asked, so its checks read the same.
        dest = self.tmp / "archive"
        run("archive.py", self.sd, "--dest", dest)
        self.assertEqual(run("check_runs.py", dest).stdout, checked.stdout)

    def test_follow_up_that_changes_a_score_is_rejected_and_the_persona_file_is_put_back(self):
        self.study({"P01-opus": [["write:all"], ["rescore", "followup"]]}, personas=1, models=[self.CLAUDE])
        self.assertEqual(self.launch("run").returncode, 0)
        file = self.sd / self.entries()["P01-opus"]["file"]
        before, scores = file.read_text(), self.extracted()
        r = self.ask("Why that score?", "--runs", "P01-opus")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("P01-opus: FOLLOW-UP 1 REJECTED", r.stdout)
        self.assertEqual((file.read_text(), self.extracted(), self.states()), (before, scores, {"P01-opus": "done"}))
        kept = self.sd.joinpath("logs/P01-opus.2.rejected.md").read_text()  # what the panellist left, score and all
        self.assertIn("| 8 | 7 |", kept)
        self.assertIn("## Follow-up 1", kept)
        answer, = self.asked()[0]["runs"]
        self.assertEqual(answer["outcome"], "rejected")
        self.assertIn("it changed the scores of concept", answer["reason"])

    def test_follow_up_cut_short_by_a_killed_launcher_changes_no_score_and_is_settled_as_it_was_decided(self):
        rewrites = [["write:all"], ["rescore", "cut", "wait:hold"]]  # a score raised and a section lost, then a reply
        self.study({"P01-opus": rewrites, "P02-opus": rewrites}, personas=3, models=[self.CLAUDE],
                   runners={"claude": {"concurrency": 2}},  # so the third run is still queued when the launcher dies
                   synthesis={"analyst": {"runner": "claude"}, "writer": {"runner": "claude"}})
        self.assertEqual(self.launch("run").returncode, 0)
        files = {run_id: self.sd / e["file"] for run_id, e in self.entries().items()}
        before, scores = {run_id: file.read_text() for run_id, file in files.items()}, self.extracted()
        unsettled = [f"{run_id}: a follow-up is unsettled, so its file was read as it stood before the question"
                     for run_id in ("P01-opus", "P02-opus")]
        asker = self.ask("Why that score?", "--runs", "all", wait=False)
        self.wait_for(lambda: self.waiting() == {"P01-opus", "P02-opus"}, "two runs to have rewritten their files")
        self.assertNotEqual(files["P01-opus"].read_text(), before["P01-opus"])
        # While the question is out, the runs are read as they stood before it: done, with every
        # score as it was, and each script that read a copy says so.
        self.assertEqual((self.extracted(), self.extract_said.splitlines()[:2]), (scores, unsettled))
        self.assertEqual({r["run"]: (r["state"], r["scored"], r["unsettled"], r["asking"], r["followups"])
                          for r in self.status()["runs"]},
                         {"P01-opus": ("done", 3, True, 1, []), "P02-opus": ("done", 3, True, 1, []),
                          "P03-opus": ("done", 3, False, None, [])})

        def archived():
            r = run("archive.py", self.sd, "--dest", self.tmp / "archive", check=False)
            return r.returncode, self.tmp.joinpath("archive").exists(), r.stderr

        # An archive has no copy to read, so nothing is archived: not under a launcher, which could
        # start or settle a follow-up while the files are copied, and not while one is unsettled.
        code, copied, why = archived()
        self.assertEqual((code, copied), (1, False), why)
        self.assertIn(f"Another launcher has this study (pid {asker.pid}", why)
        asker.kill()
        asker.wait()
        code, copied, why = archived()
        self.assertEqual((code, copied), (1, False), why)
        self.assertIn("A follow-up question to P01-opus, P02-opus, P03-opus is not settled", why)
        analysts = self.launch("run", "--role", "analyst")  # they would read files that may yet be put back
        self.assertEqual((analysts.returncode, len(self.starts())), (1, 5), analysts.stdout + analysts.stderr)
        self.assertIn("the one put to P01-opus and P02-opus is not settled", analysts.stderr)
        self.assertIn(f"followup.py {self.sd.resolve()} list", analysts.stderr)
        self.release("hold")
        self.wait_for(lambda: self.processes() == {"P01-opus": "gone", "P02-opus": "gone"}, "both processes to end")
        # The two states a launcher killed while settling a rejection leaves: its decision is on
        # record, and the file is either still as the panellist left it (P01-opus) or already put
        # back, with what the panellist left kept beside it (P02-opus). A file put back reads, on
        # its own, as a panellist that only replied.
        logs, decided = self.sd / "logs", "as decided before the launcher was killed"
        record = self.asked()
        for answer in record[0]["runs"][:2]:
            answer["settling"] = {"attempt": 2, "outcome": "rejected", "reason": decided, "action": "restore",
                                  "section": None}
        self.sd.joinpath("followups.json").write_text(json.dumps(record))
        shutil.copyfile(files["P02-opus"], logs / "P02-opus.2.rejected.md")
        shutil.copyfile(logs / "P02-opus.2.before", files["P02-opus"])

        listed = subprocess.run(self.followup("list"), env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
        # Every run asked has its outcome: the decisions were carried out, not made again, and the
        # run whose turn never came is not left as if the question were still with it.
        self.assertEqual([(x["run"], x["outcome"], x["reason"] == decided, "settling" in x)
                          for x in self.asked()[0]["runs"]],
                         [("P01-opus", "rejected", True, False), ("P02-opus", "rejected", True, False),
                          ("P03-opus", "not asked", False, False)])
        self.assertIn("P03-opus         not asked", listed.stdout)
        self.assertEqual({run_id: file.read_text() for run_id, file in files.items()}, before)  # no section added
        for run_id in ("P01-opus", "P02-opus"):  # what each left is kept, and not replaced by the file put back
            self.assertIn("| 8 | 7 |", logs.joinpath(f"{run_id}.2.rejected.md").read_text())
        self.assertEqual((self.extracted(), self.extract_said.count("unsettled"), list(logs.glob("*.before"))),
                         (scores, 0, []))

    def test_follow_up_to_a_run_that_was_stopped_before_reporting_its_usage_leaves_the_estimate_as_it_was(self):
        self.study({"P01-opus": [["write:all", "hang"], ["followup"]]}, personas=1, models=[self.CLAUDE])
        file = self.sd / self.entries()["P01-opus"]["file"]
        launcher, _ = self.launch_in_background("run")
        self.wait_for(lambda: file.read_text().endswith("Notes.\n"), "the run to have written everything")
        self.assertEqual(self.launch("stop").returncode, 0)  # stopped before its harness reported anything
        launcher.wait(timeout=30)
        self.assertEqual(self.states(), {"P01-opus": "done"})

        def measured():
            estimate, = self.plan()["estimate"]["entries"]
            return estimate

        was = measured()
        self.assertEqual((was["basis"], was["per_run"]["tokens"], was["left_out"]),
                         ("duration", None, {"unallocated": 0, "unreported": 1}))
        self.assertEqual(self.ask("Anything missing?", "--runs", "P01-opus").returncode, 0)
        # The follow-up's result is the session's total: the review's spend and its own, in one figure.
        # It is neither's, so the run measures as it did, and the figure is counted once, apart.
        now = measured()
        self.assertEqual(({**now, "left_out": None}, now["left_out"]),
                         ({**was, "left_out": None}, {"unallocated": 1, "unreported": 0}))
        usage = json.loads(self.launch("usage", "--json").stdout)
        self.assertEqual([[(r["run"], r["input_tokens"], r["cost_usd"]) for r in usage[rows]]
                          for rows in ("runs", "followups", "unallocated")],
                         [[("P01-opus", None, None)], [("P01-opus", None, None)], [("P01-opus", 2956, 0.00046504)]])
        self.assertEqual((usage["total"]["input_tokens"], usage["total"]["cost_usd"]), (2956, 0.00046504))
        self.assertIn("| unallocated | 1 | - | - | - | 2,956 | 597 | 2,234 | $0.0005 | - |",
                      self.sd.joinpath("analysis/usage.md").read_text())
        self.assertIn("2,956 in and 597 out tokens and $0.0005 unallocated between the run and a follow-up",
                      self.launch("status").stdout)
        self.assertIn("1 whose usage cannot be told apart from a follow-up's", self.launch("plan").stdout)

    def test_follow_up_asks_nothing_unless_every_run_named_can_be_asked(self):
        refusals = {"P01-cx": "it is partial",                     # unfinished: a question would pass for its resume
                    "P02-cx": "its session was purged",            # done, with no session left to continue
                    "analyst-1": "it is an analyst job",
                    # done and resumable, on a model whose provider's login has stopped working since
                    "P01-local": "pi lists openai-codex/gpt-6-luna, its provider openai-codex is not signed in"}
        self.study({"P01-cx": [["write:1"]], "P03-cx": [["write:all"], ["followup"]]}, personas=3,
                   models=[self.CODEX, self.PI],
                   synthesis={"analyst": {"runner": "claude"}, "writer": {"runner": "claude"}})
        self.launch("run")
        self.assertEqual(self.launch("purge-sessions", "--runs", "P02-cx", "--yes").returncode, 0)
        self.assertEqual(self.launch("run", "--role", "analyst").returncode, 0)
        self.assertEqual(self.states(), {"P01-cx": "partial", "P02-cx": "done", "P03-cx": "done", "analyst-1": "done",
                                         **dict.fromkeys(("P01-local", "P02-local", "P03-local"), "done")})
        self.env["FAKE_PI"] = "dead_login"
        started, everyone = len(self.starts()), ",".join([*refusals, "P03-cx"])
        r = self.ask("Anything missing?", "--runs", everyone)
        self.assertEqual(r.returncode, 1)
        for run_id, why in refusals.items():
            self.assertIn(f"{run_id}: cannot be asked: {why}", r.stdout)
        self.assertEqual(self.ask(" \n", "--runs", "P03-cx").returncode, 1)  # an empty question
        dry = self.ask("Anything missing?", "--runs", everyone, "--skip-unfit", "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
        self.assertIn("Follow-up 1: would ask 1 run (P03-cx).", dry.stdout)
        self.assertIn("It has up to 5 min and $0.50 for this question", dry.stdout)
        self.assertIn("No budget cap for the 1 run on codex", dry.stdout)
        self.assertEqual((len(self.starts()), self.sd.joinpath("followups.json").exists()), (started, False))
        r = self.ask("Anything missing?", "--runs", everyone, "--skip-unfit")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([(x["run"], x["outcome"]) for x in self.asked()[0]["runs"]], [("P03-cx", "answered")])
        self.assertEqual([e["run"] for e in self.starts(since=started)], ["P03-cx"])

    def test_follow_up_on_a_native_study_is_printed_for_the_lead_to_send_and_recorded_as_sent_by_hand(self):
        self.study(personas=1, models=["opus"])
        file = self.sd / self.entries()["P01-opus"]["file"]
        file.write_text(file.read_text() + "".join(filled_section(c, [7] * FACTORS) for c in "ABC") + finals("ABC"))
        run("runs.py", self.sd, "mark", "P01-opus", "agent-7")
        before = file.read_text()
        r = self.ask("Would you pay for it?", "--runs", "P01-opus")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("=== P01-opus (subagent: agent-7)", r.stdout)
        self.assertIn("\nWould you pay for it?\n", r.stdout)
        self.assertIn("`## Follow-up 1`", r.stdout)
        followup, = self.asked()
        self.assertEqual((followup["mode"], [(x["run"], x["outcome"], x["session"]) for x in followup["runs"]]),
                         ("native", [("P01-opus", "sent by hand", "agent-7")]))
        self.assertEqual((file.read_text(), self.starts()), (before, []))


    def test_interview_is_carried_turn_by_turn_and_only_the_words_under_say_reach_the_participant(self):
        card = "**On my mind:** ZQCARD the roster.\n**What really bothers me:** stocktake, last Tuesday.\n" \
               "**Not a problem:** the till.\n**What I use and pay for:** a notebook."
        self.interview({
            "P01-opus": [[f"say:{card}"], []],
            # Its notes carry a marker from its first reply on, and the process that ends the interview exits with 3.
            "interviewer-P01-opus": [["why:ZQWHY it said so"], [], [], ["finish:ZQREASON nothing is left", "code:3"]],
        }, guide={"topics": [{"id": "ZQT1", "area": "ZQAREA the working week", "goals": ["G1"],
                              "opener": "ZQOPENER what took most of your time?"},
                             {"id": "ZQT2", "area": "ZQAREA the tools", "goals": ["G1"],
                              "opener": "ZQOPENER what do you keep track with?"}]})
        r = self.launch("run")
        self.assertEqual((r.returncode, r.stderr), (0, ""), r.stdout)
        # One row for each interview, and nothing but an end record decides that it is done: not the exit code
        # of the process that wrote it. The interview nobody planned, with its participant on Codex, is done too.
        self.assertEqual(self.reads(), {"P01-opus": "done", "P01-cx": "done"}, r.stdout)
        for run_id in ("P01-opus", "P01-cx"):
            records = self.whole(run_id)
            self.assertEqual([x["t"] for x in records], ["start", "card", "question", "answer", "question", "answer",
                                                         "question", "answer", "end"], run_id)
            self.assertEqual([x.get("topic") for x in records if x["t"] == "question"], ["ZQT1", "ZQT2", "close"])
            # One process for each record of a turn, the sides alternating, and never two alive at once.
            sides = {run_id: "participant", f"interviewer-{run_id}": "interviewer"}
            order = [(sides[e["run"]], e["event"]) for e in self.logged()
                     if e.get("run") in sides and e.get("event") in ("start", "end")]
            self.assertEqual(order[::2], [(x["side"], "start") for x in records[1:]], run_id)
            self.assertEqual(order[1::2], [(x["side"], "end") for x in records[1:]], run_id)
        self.assertEqual((self.turns("P01-opus", "end")[0]["reason"],
                          self.entries()["interviewer-P01-opus"]["attempts"][-1],
                          json.loads(self.sd.joinpath("logs/interviewer-P01-opus.4.end").read_text())["exit_code"]),
                         ("ZQREASON nothing is left",
                          {"n": 4, "kind": "turn", "ended": mock.ANY, "seconds": mock.ANY}, 3))
        # The participant is sent its prompt, then the words under SAY of each question and nothing else: no
        # goal, topic, opener or note of the interviewer's is in anything it was started with.
        prompt, *questions = self.sent("P01-opus")
        self.assertEqual(questions, ["Question 1?", "Question 2?", "Question 3?"])
        self.assertIn("ZQBIO", prompt)
        given = json.dumps([e for e in self.starts() if e["run"] == "P01-opus"])
        self.assertEqual([m for m in ("ZQGOAL", "ZQT", "ZQAREA", "ZQOPENER", "ZQWHY", "ZQREASON") if m in given], [])
        # The interviewer is sent its prompt, then each answer under a status line: nothing of the persona's bio
        # or of the card, which the log does hold.
        brief, *answers = self.sent("interviewer-P01-opus")
        self.assertEqual(answers, [f"----------\nAnswer {n}.\n----------\n{status}" for n, status in enumerate((
            "Exchange 1 of 6. ZQT1: 1 of 8. Not opened: ZQT2.", "Exchange 2 of 6. ZQT2: 1 of 8.",
            "Exchange 3 of 6."), 1)])
        self.assertTrue(all(m in brief for m in ("ZQGOAL", "ZQT1", "ZQAREA", "ZQOPENER")), brief)
        # Every topic id the brief shows is one of this guide's, its examples included, so that none gives the
        # interviewer an id to copy that its guide does not have. Its first reply is asked for by the first id.
        own, notes = brief.split("\n# Reference notes")
        shown = ("`TOPIC: ZQT1` and `MOVE: open`", "    TOPIC: ZQT2\n", "`Exchange 4 of 6. ZQT2: 3 of 8.`")
        self.assertEqual((re.findall(r"\bT\d+\b", own), [x in own for x in shown]), ([], [True] * 3))
        given = json.dumps([e for e in self.starts() if e["run"] == "interviewer-P01-opus"])
        self.assertEqual(([m for m in ("ZQBIO", "ZQCARD") if m in given],
                          "ZQCARD" in self.turns("P01-opus", "card")[0]["text"]), ([], True))
        # The reference notes are in the interviewer's prompt as it was sent, since it has no file to open: a
        # line of one of them, as the asset has it, is there, and in nothing a participant was sent.
        note = max(self.scripts.parent.joinpath("assets/interview-reference/recovery.md").read_text().splitlines(),
                   key=len)
        self.assertEqual((note in brief, [e["run"] for e in self.starts() if e["side"] == "participant"
                                          and note in e["stdin"]]), (True, []))
        # Both transcripts are written when the interview ends. The whole one has the card and the notes, and
        # the analysts' copy has the questions and answers and nothing of either.
        whole = self.sd.joinpath("interviews/P01-opus.md").read_text()
        copy = self.sd.joinpath("analysis/transcripts/P01-opus.md").read_text()
        self.assertTrue(all(m in whole for m in ("ZQCARD", "ZQWHY", "ZQT1", "ZQREASON", "**Q:** Question 2?")), whole)
        self.assertEqual(([m for m in ("ZQCARD", "ZQWHY", "ZQT", "ZQAREA", "ZQREASON", "card") if m in copy],
                          copy.count("**Q:** Question"), copy.count("**A:** Answer")), ([], 3, 3), copy)
        # The usage record names each side of an interview as that, and its interviewer's model entry has a
        # row beside the panel's, so that the rows by model key add up to everything the interviews used.
        usage = json.loads(self.launch("usage", "--json").stdout)
        self.assertEqual(([r["side"] for r in usage["roles"]], sorted(k["key"] for k in usage["keys"]),
                          sum(k["attempts"] for k in usage["keys"])),
                         (["participant", "interviewer"], ["cx", "interviewer", "opus"], usage["total"]["attempts"]))

    def test_launcher_killed_at_any_point_of_a_turn_loses_no_turn_and_records_none_twice(self):
        self.interview({"P01-opus": [[], ["wait:a", "say:First answer."], ["wait:b", "say:Second answer."],
                                     ["wait:c", "say:Third answer."]]}, models=[self.CLAUDE])
        log = self.sd / "interviews/P01-opus.jsonl"

        def waits_at(gate):
            return lambda: gate in [e["gate"] for e in self.events("waiting")]

        def carried():
            return [run_id for run_id, e in self.entries().items() if e.get("carried")]

        # Before its process started. runs.json as a launcher leaves it that died between saving the
        # participant's first attempt and starting its process: the log begun, the interview carried, the
        # attempt on record and nothing in its pid file. No launcher is alive to make that state by chance.
        as_left = self.entries()
        for entry in as_left.values():
            entry["carried"] = True
        session = "0b5e4b1e-6f0c-4c58-9d0c-3f6a1d2c7e11"
        as_left["P01-opus"].update(pid=None, pid_identity=None, session=session, attempts=[{
            "n": 1, "kind": "turn", "started": round(time.time(), 3), "allowed": 180.0, "ended": None, "seconds": None,
            "exit_code": None, "outcome": None, "bound": "turn", "session": session, "was": {}}])
        self.sd.joinpath("runs.json").write_text(json.dumps(list(as_left.values())))
        log.parent.mkdir(exist_ok=True)
        log.write_text(json.dumps({"t": "start", "at": round(time.time(), 3), "v": 1, "kind": "interview",
                                   "run": "P01-opus"}) + "\n")
        self.sd.joinpath("logs").mkdir(exist_ok=True)
        self.sd.joinpath("logs/P01-opus.1.pid").write_text("")
        # "carried" counts only while a launcher has the study. What a dead one left reads as its log does.
        self.assertEqual(self.reads(), {"P01-opus": "pending"})
        # While it ran. The launcher that finds the state above takes the attempt back, puts the interview
        # down and starts it with attempt 1. It is killed while the participant's second process waits, and
        # the next launcher has adopted that turn before the process is let go on.
        first, output = self.launch_in_background("run")
        self.wait_for(waits_at("a"), "the first answer to be under way")
        first.kill()
        first.wait()
        self.assertIn("P01-opus: a turn of the participant was never started", output.read_text())
        # With no launcher nothing waits for one: the interview is partial to status and to the checks alike,
        # which name resume, though runs.json still has it as carried and its turn is alive.
        self.assertEqual((carried(), self.reads()), (["P01-opus", "interviewer-P01-opus"], {"P01-opus": "partial"}))
        checked = run("check_runs.py", self.sd, check=False).stdout
        self.assertIn("| P01-opus | no end record: it reads partial, after 0 of 6 exchanges |", checked)
        self.assertEqual((f"P01-opus (partial): launch.py {self.sd} resume\n" in checked, "is carrying" in checked),
                         (True, False), checked)
        second, output = self.launch_in_background("resume")
        self.wait_for(lambda: "adopted from an earlier launcher" in output.read_text(), "the turn to be adopted")
        self.assertEqual(self.reads(), {"P01-opus": "running"})  # a launcher has the study, and carries it
        self.release("a")
        # After it ended, before the log. The launcher is killed while the third process waits, and that
        # process ends with no launcher alive: its reply is in logs/ alone.
        self.wait_for(waits_at("b"), "the second answer to be under way")
        second.kill()
        second.wait()
        self.release("b")
        self.wait_for(lambda: self.processes() == {"P01-opus": "gone"}, "the second answer to end unwatched")
        self.assertEqual([x["text"] for x in self.whole("P01-opus") if x["t"] == "answer"], ["First answer."])
        third, output = self.launch_in_background("resume")
        # After the log, before runs.json. The fourth process waits with its attempt on record. runs.json is
        # kept as it is then, the launcher records the answer and the end, and runs.json is put back.
        self.wait_for(lambda: waits_at("c")() and self.entries()["P01-opus"].get("pid"),
                      "the third answer to be under way")
        open_attempt = self.sd.joinpath("runs.json").read_bytes()
        self.assertEqual([x["text"] for x in self.whole("P01-opus") if x["t"] == "answer"],
                         ["First answer.", "Second answer."])
        self.assertIn("Second answer.", self.sd.joinpath("logs/P01-opus.3.out").read_text())
        self.release("c")
        self.assertEqual(third.wait(timeout=30), 0, output.read_text())
        self.assertEqual((carried(), self.reads()), ([], {"P01-opus": "done"}))
        ended = log.read_bytes()
        self.sd.joinpath("runs.json").write_bytes(open_attempt)
        self.assertEqual((carried(), self.entries()["P01-opus"]["attempts"][-1]["ended"]),
                         (["P01-opus", "interviewer-P01-opus"], None))
        r = self.launch("resume")
        self.assertEqual((r.returncode, r.stderr), (0, ""), r.stdout)
        # Nothing was lost and nothing was said or recorded twice: each side was sent each message once, the
        # log has each turn once and is as the launcher that ended the interview left it, and no attempt is open.
        self.assertEqual((log.read_bytes() == ended, carried(), self.reads()), (True, [], {"P01-opus": "done"}))
        records = self.whole("P01-opus")
        self.assertEqual([x["text"] for x in records if x["t"] == "answer"],
                         ["First answer.", "Second answer.", "Third answer."])
        prompt, *questions = self.sent("P01-opus")
        self.assertEqual((questions, len(self.sent("interviewer-P01-opus"))),
                         (["Question 1?", "Question 2?", "Question 3?"], 4))
        self.assertEqual([a["ended"] is None for a in self.entries()["P01-opus"]["attempts"]], [False] * 4)

    def test_reply_that_cannot_be_used_is_never_delivered_and_is_sent_back_or_put_again_once(self):
        headed = "## On my mind\nThe roster.\n\n## What really bothers me\nStocktake.\n\n## Not a problem\nThe till."
        self.interview({
            # A card of three of the four parts, under headings. Its interviewer's first reply has no WHY and a
            # leak term, its repair is a question, and then two replies in a row follow no format.
            "P01-cx": [[f"say:{headed}"], []],
            "interviewer-P01-cx": [["say:TOPIC: T1\nMOVE: open\nSAY:\nHave you heard of Secret Codename?"],
                                   ["ask:T1:open"], ["say:I would ask about pricing next."], ["say:Still no format."]],
            "P02-cx": [[], ["say:"]],                                        # answers with nothing, twice
            "P03-cx": [["say:I am an AI model and cannot play a person."]],  # refuses the role, each time
        }, personas=3, models=[self.CODEX])
        r = self.launch("run")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(self.reads(), {"P01-cx": "partial", "P02-cx": "partial", "P03-cx": "failed"}, r.stdout)
        reasons = {x["run"]: x["reason"] for x in self.status()["runs"]}
        # Sent back once with every problem named, and the question that came back is delivered. The second
        # reply in one slot that cannot be used ends the carrying. No leak term reached the participant.
        self.assertEqual([(x["t"], [key for key, _ in x.get("problems", [])]) for x in self.whole("P01-cx")[1:]],
                         [("card", []), ("rejected", ["missing", "leak"]), ("question", []), ("answer", []),
                          ("rejected", ["format", "missing"]), ("rejected", ["format", "missing"])])
        _, repair, turn, again = self.sent("interviewer-P01-cx")
        self.assertIn('It is missing: WHY.\nSAY holds "secret codename", which must not reach the participant', repair)
        self.assertIn("It does not follow the reply format.", again)
        self.assertEqual((self.sent("P01-cx")[1:], "ecret" in json.dumps(self.sent("P01-cx")).lower(),
                          reasons["P01-cx"]),
                         (["Question 1?"], False, "the interviewer's reply could not be used twice"))
        # An empty answer: the question is put once more, and said to be, and then the interview is put down.
        _, asked, asked_again = self.sent("P02-cx")
        self.assertEqual((asked, asked_again.endswith("\n\nQuestion 1?"), asked_again != asked,
                          [(x["t"], x.get("why")) for x in self.whole("P02-cx")[3:]], reasons["P02-cx"]),
                         ("Question 1?", True, True, [("lost", "empty"), ("lost", "empty")],
                          "the participant replied with nothing twice"))
        # A first reply that is no card: failed, with the reply on its log, launched afresh once by the same
        # run and no more, and no interviewer was ever started for it.
        refused = self.whole("P03-cx")
        self.assertEqual([(x["t"], x.get("why") or x.get("state") or x.get("by")) for x in refused[1:]],
                         [("lost", "role"), ("halt", "failed"), ("resume", "run"), ("lost", "role"),
                          ("halt", "failed")])
        self.assertEqual((refused[1]["reply"], [e["resumed"] for e in self.starts() if e["run"] == "P03-cx"],
                          self.sent("interviewer-P03-cx")),
                         ("I am an AI model and cannot play a person.", [False, False], []))
        self.assertIn("did not write its situation card: this model may be too small to hold the role",
                      reasons["P03-cx"])
        self.assertIn("  failed: P03-cx. Next: run.", r.stdout)

    def test_interview_ends_short_of_its_cap_without_a_close_and_an_early_end_is_asked_about_once(self):
        self.interview({
            # T1 reaches its cap of two, and at the last exchange the cap allows it asks about T2 again, twice.
            "interviewer-P01-opus": [["ask:T1:open"], ["ask:T1"], ["ask:T2:open"], ["ask:T2"]],
            # Ends after one exchange, with T2 not opened, and says so again when asked.
            "interviewer-P02-opus": [["ask:T1:open"], ["finish:She has no more time."], ["finish:She said it again."]],
        }, personas=2, models=[self.CLAUDE], guide={
            "turns": 4, "topics": [{"id": "T1", "area": "the working week", "goals": ["G1"], "turns": 2,
                                    "opener": "What took most of your time last week?"},
                                   {"id": "T2", "area": "the tools", "goals": ["G1"],
                                    "opener": "What do you keep track of things with?"}]})
        r = self.launch("run")
        self.assertEqual((r.returncode, self.reads()), (0, {"P01-opus": "done", "P02-opus": "done"}), r.stdout)
        capped = self.whole("P01-opus")
        _, _, at_topic_cap, last, repair = self.sent("interviewer-P01-opus")
        self.assertEqual((at_topic_cap.split("\n")[-2:], last.split("\n")[-2:]),
                         (["Exchange 2 of 4. T1: 2 of 2. Not opened: T2.", "T1 has used its turns: move on or close."],
                          ["Exchange 3 of 4. T2: 1 of 8.", "This is your last question: close the interview."]))
        self.assertIn("This is the last exchange: reply with TOPIC: close.", repair)
        self.assertEqual([(x["t"], [key for key, _ in x.get("problems", [])]) for x in capped[-3:]],
                         [("rejected", ["last-exchange"]), ("rejected", ["last-exchange"]), ("end", [])])
        self.assertEqual(({k: capped[-1].get(k) for k in ("by", "exchanges", "short", "close", "unopened")},
                          self.sent("P01-opus")[1:]),
                         ({"by": "cap", "exchanges": 3, "short": True, "close": False, "unopened": []},
                          ["Question 1?", "Question 2?", "Question 3?"]))
        self.assertIn("one short of the cap of 4", self.sd.joinpath("interviews/P01-opus.md").read_text())
        early = self.whole("P02-opus")
        _, _, check = self.sent("interviewer-P02-opus")
        self.assertIn("T2 was not opened. Open it, or confirm the end with your reason.", check)
        self.assertEqual([(x["t"], x.get("reason")) for x in early[-2:]],
                         [("end-offered", "She has no more time."), ("end", "She said it again.")])
        self.assertEqual({k: early[-1][k] for k in ("by", "exchanges", "unopened")},
                         {"by": "interviewer", "exchanges": 1, "unopened": ["T2"]})

    def test_interview_turn_at_the_turn_limit_waits_for_resume_and_a_side_out_of_its_allowance_for_extend(self):
        # The participant's second process hangs and its fourth reaches its budget. Nothing is timed but the
        # turn limit, which outlasts the start of a process many times over, as does what is left of the
        # participant's time after the turn that hung: 0.8 of a turn limit, for a turn that takes a moment.
        turn = 3.0
        self.interview({"P01-opus": [[], ["hang"], [], ["end:budget"], [], ["end:budget"], []]}, models=[self.CLAUDE],
                       limits={"turn": {"minutes": turn / 60}, "run": {"minutes": 1.8 * turn / 60, "budget_usd": 1}})
        r = self.launch("run")
        # Stopped at limits.turn: partial and never limited, and the command that lost the turn does not put it
        # again. The usage record says partial too: it is written again when an interview is put down, which
        # is after the record that the end of its last turn wrote.
        self.assertEqual((r.returncode, self.reads()), (1, {"P01-opus": "partial"}), r.stdout)
        by_run = self.sd.joinpath("analysis/usage.md").read_text().split("## By run")[1]
        self.assertEqual((by_run.count("| partial |"), "running" in by_run), (2, False), by_run)
        self.assertIn("P01-opus: partial after 0 exchanges: the participant's turn was stopped at limits.turn",
                      r.stdout)
        self.assertEqual(([x["t"] for x in self.whole("P01-opus")[-2:]], self.turns("P01-opus", "lost")[0]["why"],
                          self.sent("P01-opus")[1:]), (["question", "lost"], "time", ["Question 1?"]))
        # resume puts that turn again, once, and says that it does. Two turns on, the participant's process
        # reaches its budget: limited, with the side at its limit named and the answer it gave kept.
        r = self.launch("resume")
        self.assertEqual((r.returncode, self.reads()), (1, {"P01-opus": "limited"}), r.stdout)
        _, asked, again, second = self.sent("P01-opus")
        self.assertEqual((asked, again.endswith("\n\nQuestion 1?"), again != asked, second),
                         ("Question 1?", True, True, "Question 2?"))
        [limited], kept = self.status()["runs"], self.whole("P01-opus")
        self.assertEqual(({k: kept[-1].get(k) for k in ("t", "state", "side", "limited_by")},
                          limited["interview"]["exchanges"]),
                         ({"t": "halt", "state": "limited", "side": "participant", "limited_by": "budget"}, 1))
        # Each side's limits are its own and add up over its turns. Spend: a later turn is given the cap less
        # what its own side's session has reported. Time: the turn that hung was allowed a whole turn limit and
        # is charged to the participant alone, and a later turn of the participant is allowed only what is left.
        caps = {entry: [e["argv"][e["argv"].index("--max-budget-usd") + 1] for e in self.starts() if e["run"] == entry]
                for entry in ("P01-opus", "interviewer-P01-opus")}
        self.assertEqual(caps, {"P01-opus": ["1", "0.999535", "0.999535", "0.999535"],
                                "interviewer-P01-opus": ["1", "0.999535"]})
        attempts = {a["n"]: a for a in self.entries()["P01-opus"]["attempts"]}
        self.assertEqual((attempts[2]["bound"], attempts[2]["allowed"], attempts[4]["bound"]),
                         ("turn", turn, "allowance"))
        self.assertLess(attempts[4]["allowed"], 0.8 * turn)
        self.assertGreaterEqual(limited["seconds_used"], turn)
        self.assertLess(limited["interview"]["interviewer"]["seconds_used"], turn)
        # A limited interview is left alone until it is named with --extend, which gives the side at its limit
        # one more allowance and goes on at the turn the log reached: every turn it had is kept, and nothing is
        # asked again but the two turns that were lost.
        self.assertIn("P01-opus: limited, so resume leaves it alone. Next: resume --runs <ids> --extend",
                      self.launch("resume", "--runs", "P01-opus").stdout)
        r = self.launch("resume", "--runs", "P01-opus", "--extend")
        self.assertEqual((r.returncode, self.reads()), (1, {"P01-opus": "limited"}), r.stdout)
        self.assertIn("P01-opus: extended, one more allowance of the participant's limits", r.stdout)
        records, status = self.whole("P01-opus"), self.status()
        self.assertEqual((records[:len(kept)], [x.get("extended") for x in records if x["t"] == "resume"],
                          [x["n"] for x in records if x["t"] == "answer"]), (kept, [None, "participant"], [1, 2]))
        self.assertEqual(({k: e.get("extended") for k, e in self.entries().items()}, status["extended"],
                          status["ceiling_holds"]),
                         ({"P01-opus": 1, "interviewer-P01-opus": None}, ["P01-opus"], False))
        # The grant is the record on the log. A launcher killed after writing it and before saving runs.json
        # leaves the log as below and runs.json as it was: the halt is cleared, so the interview is partial, and
        # the resume that takes it up brings the entry level with the log, once, before the turn is started.
        with open(self.sd / "interviews/P01-opus.jsonl", "a") as log:
            log.write(json.dumps({"t": "resume", "at": round(time.time(), 3), "by": "resume",
                                  "extended": "participant"}) + "\n")
        self.assertEqual((self.reads(), self.entries()["P01-opus"]["extended"]), ({"P01-opus": "partial"}, 1))
        r = self.launch("resume")
        self.assertEqual((r.returncode, self.reads()), (0, {"P01-opus": "done"}), r.stdout)
        self.assertEqual(([x.get("extended") for x in self.whole("P01-opus") if x["t"] == "resume"],
                          {k: e.get("extended") for k, e in self.entries().items()}),
                         ([None, "participant", "participant", None], {"P01-opus": 2, "interviewer-P01-opus": None}))
        self.assertEqual([m.rsplit("\n", 1)[-1] for m in self.sent("P01-opus")[1:]],
                         ["Question 1?", "Question 1?", "Question 2?", "Question 2?", "Question 3?", "Question 3?"])
        caps = {e["attempt"]: float(e["argv"][e["argv"].index("--max-budget-usd") + 1])
                for e in self.starts() if e["run"] == "P01-opus"}
        self.assertEqual((1 < caps[5] < 2, 2 < caps[7] < 3), (True, True), caps)

    def test_usage_limit_on_either_side_blocks_an_interview_and_on_the_interviewers_runner_stops_every_one(self):
        others = ("P03-cx", "P04-cx")
        self.interview({
            "P01-cx": [[], ["wait:turned", "end:usage_limit"], []],          # its first answer is turned away
            "interviewer-P02-cx": [["wait:limit", "end:usage_limit"], []],   # its first question is
            **{run_id: [[], ["wait:hold"], []] for run_id in others},        # their first answers wait to be let go
        }, personas=4, models=[self.CODEX], runners={"claude": {"concurrency": 3}, "codex": {"concurrency": 1}})
        log, runs = self.sd / "interviews/P01-cx.jsonl", self.sd / "runs.json"
        # The participant's side. Its harness turns a turn away: blocked, in the harness's own words.
        launcher, output = self.launch_in_background("run", "--runs", "P01-cx")
        self.wait_for(lambda: "P01-cx" in self.waiting() and self.entries()["P01-cx"].get("pid"),
                      "the first answer to be under way")
        under_way = runs.read_bytes()
        self.release("turned")
        self.assertEqual(launcher.wait(timeout=30), 1, output.read_text())
        self.assertIn("P01-cx: blocked after 0 exchanges: the participant's turn was turned away by its harness: "
                      "You've hit your usage limit", output.read_text())
        self.assertEqual(self.reads(), {"P01-cx": "blocked", "P02-cx": "pending", **dict.fromkeys(others, "pending")})
        # A launcher killed while it wrote that leaves the first of the two records and a part of the second,
        # and the attempt open. Neither record is read, and the next launcher writes both from the files of
        # the attempt, so the interview is blocked still, not merely partial. resume then goes on at the turn the
        # log reached, and puts the question that was turned away again.
        log.write_bytes(log.read_bytes()[:-20])
        runs.write_bytes(under_way)
        self.assertEqual(self.reads()["P01-cx"], "partial")  # as its log reads with neither record, and no launcher
        r = self.launch("resume", "--runs", "P01-cx")
        self.assertEqual((r.returncode, self.reads()["P01-cx"]), (0, "done"), r.stdout)
        self.assertIn("P01-cx: blocked after 0 exchanges: the participant's turn was turned away", r.stdout)
        self.assertEqual([(x["t"], x.get("state") or x.get("side")) for x in self.whole("P01-cx")[3:6]],
                         [("lost", "participant"), ("halt", "blocked"), ("resume", None)])
        self.assertEqual([m.rsplit("\n", 1)[-1] for m in self.sent("P01-cx")[1:]],
                         ["Question 1?", "Question 1?", "Question 2?", "Question 3?"])
        # The interviewer's side, which every interview shares. Three are carried. One participant holds the
        # only slot of its runner with its first answer, so the first answer of another waits for that slot,
        # when the interviewer of the third is turned away.
        launcher, output = self.launch_in_background("run")
        self.wait_for(lambda: "interviewer-P02-cx" in self.waiting() and any(x in self.waiting() for x in others)
                      and all(self.turns(x, "question") for x in others), "two answers to be due and one under way")
        held = next(x for x in others if x in self.waiting())
        queued = next(x for x in others if x != held)
        self.release("limit")
        # The turn that waited is never started: its interview is put down at once, and the command goes on
        # only for the turn in flight on the other runner, which is recorded before its interview is put down.
        self.wait_for(lambda: f"{queued}: blocked" in output.read_text(), "the interview whose turn waited")
        self.assertEqual((launcher.poll(), len(self.sent(queued))), (None, 1))
        self.release("hold")
        self.assertEqual(launcher.wait(timeout=30), 1, output.read_text())
        lifts = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.LIMIT_RESET))
        self.assertIn(f"claude: the harness is turning requests away, and said its limit lifts at {lifts}. No more "
                      "launches on this runner for now", output.read_text())
        self.assertEqual(self.reads(), {"P01-cx": "done", "P02-cx": "blocked", held: "blocked", queued: "blocked"})
        # Each says which side's harness it waits for, the one it did not hear from itself in that harness's
        # words too, and when the limit lifts.
        rows = {r["run"]: r for r in self.status()["runs"]}
        for run_id, before in (("P02-cx", "lost"), (held, "answer"), (queued, "question")):
            last, halt = self.turns(run_id)[-2:]
            self.assertEqual((last["t"], {k: halt.get(k) for k in ("t", "state", "side", "reset_at")},
                              rows[run_id]["reset_at"], "You've hit your session limit" in rows[run_id]["reason"]),
                             (before, {"t": "halt", "state": "blocked", "side": "interviewer",
                                       "reset_at": self.LIMIT_RESET}, self.LIMIT_RESET, True), run_id)
        # resume continues all three where each stopped: no question is put twice, and none is lost.
        r = self.launch("resume")
        self.assertEqual((r.returncode, set(self.reads().values())), (0, {"done"}), r.stdout)
        for run_id in ("P02-cx", held, queued):
            self.assertEqual(([x["n"] for x in self.whole(run_id) if x["t"] == "answer"], self.sent(run_id)[1:]),
                             ([1, 2, 3], ["Question 1?", "Question 2?", "Question 3?"]), run_id)

    def test_interview_with_a_session_that_is_gone_starts_afresh_only_while_it_has_no_answer_on_record(self):
        first, second, third = "P01-cx", "P02-cx", "P03-cx"
        self.interview({first: [[], ["end:usage_limit"], []], second: [[], [], ["end:usage_limit"], []],
                        third: [[], ["end:budget"], [], ["end:budget"], []]}, personas=3, models=[self.CODEX])
        for run_id in (first, second):  # one at a time: a runner that is turned away stops every interview on it
            self.launch("run", "--runs", run_id)
        self.assertEqual((self.reads(), [len(self.turns(x, "answer")) for x in (first, second)]),
                         ({first: "blocked", second: "blocked", third: "pending"}, [0, 1]))
        # purge-sessions takes an interview by its run id, which names the sessions of both its sides.
        sessions = {entry: e.get("session") for entry, e in self.entries().items()}
        listed = self.launch("purge-sessions", "--runs", first).stdout
        named = [entry for entry, session in sessions.items() if f"  {entry} (" in listed and session in listed]
        self.assertEqual(named, [first, f"interviewer-{first}"], listed)
        # The harness loses the session of both participants.
        for e in self.starts():
            if e["run"] in (first, second):
                self.fake.joinpath("sessions", f"{e['session']}.json").unlink(missing_ok=True)
        had = {x: self.sd.joinpath(f"interviews/{x}.jsonl").read_bytes() for x in (first, second)}
        r = self.launch("resume")
        self.assertEqual((r.returncode, self.reads()), (1, {first: "done", second: "partial", third: "pending"}),
                         r.stdout)
        # With no answer on record nothing would be lost: the log it had is moved to logs/, whole, and the
        # interview is held again from its start, both sides in new sessions.
        self.assertIn(f"{first}: the participant's session no longer exists and no answer is on record, so the "
                      f"interview starts afresh. The turn log it had is logs/{first}.interview-1.jsonl.", r.stdout)
        fresh, now = self.whole(first), self.entries()
        self.assertEqual((self.sd.joinpath(f"logs/{first}.interview-1.jsonl").read_bytes()[:len(had[first])],
                          [x["t"] for x in fresh[:2]], [x["n"] for x in fresh if x["t"] == "answer"],
                          [now[x]["session"] in (None, sessions[x]) for x in (first, f"interviewer-{first}")]),
                         (had[first], ["start", "card"], [1, 2, 3], [False, False]))
        # With an answer on record it is the lead's to decide: nothing is moved, the answer stays, and the
        # next resume knows the session is gone and does not take the interview up to find it out.
        left = (f"{second}: partial after 1 exchange: the participant's session no longer exists, so it cannot be "
                "continued")
        again = self.launch("resume")
        self.assertEqual((left in r.stdout, left in again.stdout, f"{second}: running" in again.stdout,
                          again.returncode), (True, True, False, 1), again.stdout)
        moved = sorted(p.name for p in self.sd.glob("logs/*.interview-*"))
        self.assertEqual((self.sd.joinpath(f"interviews/{second}.jsonl").read_bytes()[:len(had[second])],
                          len(self.turns(second, "answer")), moved), (had[second], 1, [f"{first}.interview-1.jsonl"]))
        # A fresh start gives no allowance back and takes none away. The third participant is at its budget
        # with no answer on record and its sessions are purged, so the next command starts it afresh. A grant
        # that a killed launcher recorded and never brought to runs.json is on the log that goes: the new log
        # begins with it, and the entry has it.

        def granted():
            """What the turn log's "start" record says each side brought, and the copy on each entry."""
            return self.turns(third, "start")[0].get("extended"), {
                x: self.entries()[x].get("extended") for x in (third, f"interviewer-{third}")}

        self.launch("run", "--runs", third)
        self.assertEqual((self.reads()[third], len(self.turns(third, "answer")), granted()),
                         ("limited", 0, (None, {third: None, f"interviewer-{third}": None})))
        self.launch("purge-sessions", "--runs", third, "--yes")
        with open(self.sd / f"interviews/{third}.jsonl", "a") as log:
            log.write(json.dumps({"t": "resume", "at": round(time.time(), 3), "by": "resume",
                                  "extended": "participant"}) + "\n")
        r = self.launch("resume", "--runs", third)
        self.assertIn(f"{third}: the participant's session was purged (purge-sessions) and no answer is on record, "
                      "so the interview starts afresh.", r.stdout)
        self.assertEqual((self.reads()[third], len(self.turns(third, "answer")), granted()),
                         ("limited", 0, ({"participant": 1}, {third: 1, f"interviewer-{third}": None})), r.stdout)
        # The same when "resume --extend" is the command that finds the log must begin again: the allowance it
        # says it gives is in the new log's "start" record, with the one from before, and on the entry.
        self.launch("purge-sessions", "--runs", third, "--yes")
        r = self.launch("resume", "--runs", third, "--extend")
        self.assertIn(f"{third}: extended, one more allowance of the participant's limits", r.stdout)
        self.assertEqual((r.returncode, self.reads()[third], granted()),
                         (0, "done", ({"participant": 2}, {third: 2, f"interviewer-{third}": None})), r.stdout)

    def test_plan_of_an_interview_study_caps_both_sides_of_each_interview_and_refuses_a_runner_that_carries_none(self):
        synthesis = {"analyst": {"runner": "claude", "model": "sonnet"}, "writer": {"runner": "claude"}}
        self.interview(personas=2, synthesis=synthesis,
                       limits={"run": {"budget_usd": 0.5}, "interviewer": {"budget_usd": 2}})
        before = self.tree()
        printed, as_json = self.launch("plan"), self.launch("plan", "--json")
        self.assertEqual((printed.returncode, as_json.returncode), (0, 0), printed.stdout + printed.stderr)
        # The CLIs were asked whether they are installed and signed in. Nothing was started, and nothing written.
        self.assertFalse([c for c in self.logged() if c.get("model_call") or c.get("event")])
        self.assertEqual(self.tree(), before)
        # Four interviews. Each has an interviewer on claude, capped at $2, and two have a participant on claude,
        # capped at $0.50: $9 for six sides, and the $5 pool. The two participants on codex have no cap.
        plan = json.loads(as_json.stdout)
        ceiling = plan["ceiling"]
        self.assertEqual((ceiling["usd"], ceiling["capped_runs"], ceiling["uncapped"], ceiling["label"]),
                         (14.0, 6, ["P01-cx", "P02-cx"], "estimate"))
        self.assertIn("$9.00 for 6 sides with an enforced cap, each side of each interview counted once",
                      printed.stdout)
        self.assertEqual([(i["run"], i["participant"]["limits"]["budget_usd"], i["interviewer"]["limits"]["budget_usd"])
                          for i in plan["interview"]["interviews"]],
                         [("P01-opus", 0.5, 2), ("P01-cx", 0.5, 2), ("P02-opus", 0.5, 2), ("P02-cx", 0.5, 2)])
        # No interview has finished, and none is forecast as a review of pages. A participant on claude, to the
        # cap of 6 exchanges: 6 processes of 4,300 tokens and 200 more for each exchange so far, in 2 interviews.
        opus = next(e for e in plan["estimate"]["entries"] if e["entry"] == "opus")
        self.assertEqual((opus["basis"], opus["tokens"], opus["cost_usd"]), ("exchanges", 60000, None))
        # An allowance that --extend gave an interviewer is on the interviewer's entry, and breaks the ceiling too.
        entries = self.entries()
        entries["interviewer-P01-cx"]["extended"] = 1
        self.sd.joinpath("runs.json").write_text(json.dumps(list(entries.values())))
        ceiling = self.plan()["ceiling"]
        self.assertEqual((ceiling["holds"], ceiling["extended"], ceiling["with_extensions_usd"]),
                         (False, ["interviewer-P01-cx"], 16.0))

        # A runner that does not declare itself verified for interviews carries neither side of one.
        shutil.rmtree(self.sd)
        self.interview(models=[self.CLAUDE, self.PI], guide={"interviewer": {"runner": "pi", "model": PI_MODEL}})
        refusal = "pi is not verified for interviews, and an interview is carried turn by turn through its runner"
        planned = self.launch("plan")
        self.assertEqual(planned.returncode, 1, planned.stdout + planned.stderr)
        self.assertIn(f"local: {refusal}", planned.stdout)        # as a participant
        self.assertIn(f"interviewer: {refusal}", planned.stdout)  # and as the interviewer
        started = self.launch("run")
        self.assertEqual((started.returncode, self.starts()), (1, []), started.stdout)
        self.assertIn(f"P01-local: {refusal}", started.stdout)
        self.assertIn(f"interviewer: {refusal}", started.stdout)

    def test_checks_block_an_interview_with_no_end_record_and_note_a_topic_that_was_never_opened(self):
        opener = "ZQOPENER what do you keep track of things with?"
        self.interview({
            # Ends after one exchange with T2 not opened, and says so again when asked: done, with T2 unopened.
            "interviewer-P01-opus": [["ask:T1:open"], ["finish:She has no more time."], ["finish:She said it again."]],
            # The participant's second process dies in the middle of its turn: partial, with one question asked.
            "P01-cx": [[], ["exit:1"], []],
            # Its interviewer then opens T2 with its opener, in other case, under the label of the topic it leaves.
            "interviewer-P01-cx": [[], [f"ask:T1:accept:Fair enough. {opener.upper()}"], []]})
        self.launch("run")
        self.assertEqual(self.reads(), {"P01-opus": "done", "P01-cx": "partial"})
        checked = run("check_runs.py", self.sd, check=False)
        rows = {line.split(" | ")[0][2:]: line.split(" | ")[1:] for line in checked.stdout.splitlines()
                if line.startswith("| P")}
        self.assertEqual(checked.returncode, 1, checked.stdout + checked.stderr)
        self.assertEqual((rows["P01-cx"][0], rows["P01-opus"]),
                         ("no end record: it reads partial, after 0 of 6 exchanges", ["-", "topic never opened: T2 |"]))
        # What the lead does about the blocking row is said under the table, and the file has what was printed.
        self.assertIn(f"P01-cx (partial): launch.py {self.sd} resume\n", checked.stdout)
        self.assertEqual(self.sd.joinpath("analysis/checks.md").read_text(), checked.stdout)
        self.assertEqual(self.launch("resume").returncode, 0)
        checked = run("check_runs.py", self.sd, check=False)
        self.assertEqual(checked.returncode, 0, checked.stdout)  # an unopened topic is a finding, and blocks nothing
        self.assertIn("| P01-opus | - | topic never opened: T2 |", checked.stdout)
        # A question counts for the topic whose opener its words hold. The launcher went by that, so T2 was
        # never reported to the interviewer as unopened, and the log, the transcript and the checks say both.
        asked = self.turns("P01-cx", "question")
        self.assertEqual(([(x["topic"], x.get("labelled")) for x in asked],
                          self.sent("interviewer-P01-cx")[-1].split("\n")[-1]),
                         ([("T1", None), ("T2", "T1"), ("close", None)], "Exchange 3 of 6."))
        self.assertIn("- Topic: T2, ZQAREA the tools (the interviewer labelled it T1)",
                      self.sd.joinpath("interviews/P01-cx.md").read_text())
        self.assertIn("| P01-cx | - | question 2 holds the opener of T2 and was labelled T1: it is counted under T2; "
                      "1 turn of the participant left no reply and was put again |", checked.stdout)
        # A record that lacks a field every launcher writes, or holds another kind of value there than one
        # writes, makes the log one of the wrong form, which blocks, and nothing else of that log is checked:
        # an answer with no text is not an empty answer that passes, and a topic that is no text stops no reader.
        # "unread" is a reader's name for a record it set aside and no type of one: a line that calls itself
        # that is of no known type, whatever well-formed record it holds inside.
        log = self.sd / "interviews/P01-cx.jsonl"
        records = self.turns("P01-cx")[:-1]  # and with no "end", so that it reads as one to go on with
        asked = next(i for i, x in enumerate(records) if x["t"] == "question")
        at = max(i for i, x in enumerate(records) if x["t"] == "answer")  # the participant's last turn
        records[asked]["topic"] = []
        del records[at]["text"]
        records.append({"t": "unread", "record": {"t": "resume", "at": time.time(), "by": "resume"}})
        log.write_text("".join(json.dumps(x) + "\n" for x in records))
        wrong = (f'Record {asked + 1} (question) lacks "topic", which a launcher always writes. Record {at + 1} '
                 f'(answer) lacks "text", which a launcher always writes. Record {len(records)} is not a record of '
                 "a known type")
        checked = run("check_runs.py", self.sd, check=False)
        self.assertEqual(checked.returncode, 1, checked.stdout)
        self.assertIn(f"| P01-cx | turn log of the wrong form: {wrong} | - |", checked.stdout)
        # No command goes on with such a log: resume says which record is wrong and what to do, and adds nothing.
        # Not for a turn it finds to settle either. runs.json is as a launcher leaves it that was killed between
        # the log and runs.json, with the attempt of that answer open: the attempt is on the log, though no
        # reader counts its record, so it is settled and nothing is recorded of it a second time.
        as_left = self.entries()
        for entry in (as_left["P01-cx"], as_left["interviewer-P01-cx"]):
            entry["carried"] = True
        turn = as_left["P01-cx"]["attempts"][-1]
        turn.update(started=turn["ended"] - turn["seconds"], allowed=180.0, ended=None, seconds=None, exit_code=None,
                    outcome=None, bound="turn", session=as_left["P01-cx"]["session"], was={})
        self.sd.joinpath("runs.json").write_text(json.dumps(list(as_left.values())))
        self.assertEqual(turn["n"], records[at]["attempt"])
        r = self.launch("resume", "--runs", "P01-cx")
        settled = self.entries()["P01-cx"]
        self.assertEqual((r.returncode, self.turns("P01-cx"), settled["attempts"][-1]["ended"] is None,
                          settled.get("carried")), (1, records, False, None), r.stdout + r.stderr)
        self.assertIn(f"P01-cx: its turn log is of the wrong form ({wrong}), so resume leaves it alone. Put "
                      "interviews/P01-cx.jsonl right, or to hold the interview again from its start move that file "
                      "into logs/", r.stdout)



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
