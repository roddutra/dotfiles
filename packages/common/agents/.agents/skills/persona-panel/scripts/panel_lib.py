"""Shared helpers for the persona-panel scripts: study config, labels, and persona-file parsing.

Standard library only. Every script takes a study directory laid out as:

    <study>/study.json        lead config (never shown to panellists)
    <study>/key.md            neutral label -> concept key (lead only)
    <study>/runs.json         one entry per persona x model run
    <study>/prompts/          one run prompt per run
    <study>/panel/            the only folder panellists may read
        _panel-instructions.md
        sites/concept-<L>/    neutral copies of each concept
        materials/concept-<L>/<page>/
        personas/<pid>-<slug>--<model>.md
        scratch/<pid>-<model>/
    <study>/analysis/         scores.csv, quant.md, quant.json, checks.md, summaries
"""

from __future__ import annotations

import json
import math
import random
import re
import statistics
import shutil
import string
import subprocess
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
ASSETS = SKILL_DIR / "assets"

DEFAULT_FACTORS = [
    {"key": "first", "label": "First impression", "short": "First",
     "question": "After 5 seconds, do I know what this is, who it's for and what it does for me?"},
    {"key": "relevance", "label": "Relevance to me", "short": "Relevance",
     "question": "Does this feel built for someone in my role and my kind of business?"},
    {"key": "problem", "label": "Problem recognition", "short": "Problem",
     "question": "Does it name problems I actually have, in words I'd use?"},
    {"key": "how", "label": "How it works", "short": "How",
     "question": "Do I understand how it would work in my business, day to day?"},
    {"key": "why_care", "label": "Why care", "short": "Why care",
     "question": "Is the benefit to me clear and big enough to act on?"},
    {"key": "trust", "label": "Trust", "short": "Trust",
     "question": "Do I believe it? Think risk, my brand, my clients' data, and the vendor itself."},
    {"key": "visual", "label": "Visual design", "short": "Visual",
     "question": "Does it look professional, calm and credible, or busy, gimmicky or cheap?"},
    {"key": "structure", "label": "Structure and flow", "short": "Structure",
     "question": "Is it easy to scan and follow, the right length, with things where I expect them?"},
    {"key": "mobile", "label": "Mobile", "short": "Mobile",
     "question": "Judged from the phone screens: would it work if I opened it on my phone?"},
    {"key": "next_step", "label": "Next step", "short": "Next step",
     "question": "How likely am I to book a demo, sign up or pass it on?"},
    {"key": "overall", "label": "Overall", "short": "Overall",
     "question": "Your overall verdict. It doesn't have to be the average of the other scores."},
]

DEFAULT_FIT_FACTORS = ["relevance", "why_care", "next_step"]
DASHES = ("\u2013", "\u2014")
FINAL_MARKER = "## Out of character"


# ---------------------------------------------------------------- config

def load_study(study_dir: Path) -> dict:
    study_dir = Path(study_dir).resolve()
    cfg = json.loads((study_dir / "study.json").read_text())
    cfg.setdefault("factors", DEFAULT_FACTORS)
    cfg.setdefault("fit_factors", [f for f in DEFAULT_FIT_FACTORS if f in {x["key"] for x in cfg["factors"]}])
    cfg.setdefault("models", ["opus", "fable"])
    cfg.setdefault("seed", 1)
    cfg.setdefault("label_style", "letters")
    cfg.setdefault("shuffle_labels", True)
    cfg.setdefault("leak_terms", [])
    cfg.setdefault("find_the_answer", [])
    cfg.setdefault("context_notes", [])
    cfg.setdefault("segments", {})
    cfg["_dir"] = study_dir
    for c in cfg["concepts"]:
        p = Path(c["path"]).expanduser()
        c["_path"] = (p if p.is_absolute() else study_dir / p).resolve()
    if cfg["factors"][-1]["key"] != "overall":
        raise SystemExit("study.json: the last factor must be 'overall'")
    return cfg


def factor_keys(cfg: dict) -> list[str]:
    return [f["key"] for f in cfg["factors"]]


def make_labels(n: int, style: str) -> list[str]:
    if style == "numbers":
        return [f"{i + 1:02d}" for i in range(n)]
    if n > 26:
        raise SystemExit("More than 26 concepts: use label_style 'numbers'")
    return list(string.ascii_uppercase[:n])


def label_map(cfg: dict) -> dict[str, dict]:
    """Deterministic neutral label -> concept. Shuffled with the study seed unless disabled."""
    concepts = list(cfg["concepts"])
    if cfg.get("labels"):  # explicit {"A": "<concept id>"} mapping, e.g. to reproduce an earlier study
        by_id = {c["id"]: c for c in concepts}
        return {label: by_id[cid] for label, cid in cfg["labels"].items()}
    if cfg["shuffle_labels"]:
        random.Random(f"{cfg['seed']}:labels").shuffle(concepts)
    labels = make_labels(len(concepts), cfg["label_style"])
    return dict(zip(labels, concepts))


def review_order(cfg: dict, pid: str, labels: list[str]) -> list[str]:
    """Per-persona random order, identical across that persona's models."""
    order = list(labels)
    random.Random(f"{cfg['seed']}:order:{pid}").shuffle(order)
    return order


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def persona_slug(p: dict) -> str:
    return p.get("slug") or slugify(p["name"])


def run_id(pid: str, model: str) -> str:
    return f"{pid}-{model}"


def persona_file(study_dir: Path, p: dict, model: str) -> Path:
    return Path(study_dir) / "panel" / "personas" / f"{p['id']}-{persona_slug(p)}--{model}.md"


def render_template(name: str, **values) -> str:
    return string.Template((ASSETS / name).read_text()).substitute(**values)


# ---------------------------------------------------------------- parsing

NUM = re.compile(r"\d+(?:\.\d+)?")
FILE_RE = re.compile(r"^(?P<pid>[^-]+)-(?P<slug>.+)--(?P<model>[^-]+)\.md$")


def parse_persona_file(path: Path, labels: list[str], n_factors: int) -> dict:
    """Parse one run file. Returns scores per label, ranking, order, and structural problems."""
    path = Path(path)
    m = FILE_RE.match(path.name)
    text = path.read_text()
    lines = text.split("\n")
    out = {
        "file": path.name, "pid": m["pid"] if m else path.stem, "model": m["model"] if m else "",
        "slug": m["slug"] if m else "", "scores": {}, "sections": {}, "ranking": [], "order": [],
        "unknown_labels": [], "duplicates": [], "missing_scores": [], "has_final": FINAL_MARKER in text,
        "dash_count": sum(text.count(d) for d in DASHES), "text": text,
    }
    label_set = set(labels)
    for line in lines:
        mo = re.match(r"^\|\s*Review order\s*\|\s*(.+?)\s*\|\s*$", line)
        if mo:
            out["order"] = [x.strip() for x in mo.group(1).split(",") if x.strip()]
            break
    for i, line in enumerate(lines):
        mc = re.match(r"^###\s+Concept\s+([A-Za-z0-9]+)\b", line)
        if not mc:
            continue
        label = mc.group(1)
        if label not in label_set:
            out["unknown_labels"].append(label)
            continue
        if label in out["sections"]:
            out["duplicates"].append(label)
        end = next((j for j in range(i + 1, len(lines))
                    if lines[j].startswith("### ") or lines[j].startswith("## ")), len(lines))
        out["sections"][label] = "\n".join(lines[i:end])
        for j in range(i + 1, end):
            cells = [c.strip().strip("*") for c in lines[j].strip().strip("|").split("|")]
            if len(cells) == n_factors and all(NUM.fullmatch(c) for c in cells):
                out["scores"][label] = [float(c) for c in cells]
                break
    out["missing_scores"] = [lab for lab in out["sections"] if lab not in out["scores"]]
    in_rank = False
    for line in lines:
        if re.match(r"^#{2,4}\s+My ranking", line):
            in_rank = True
            continue
        if in_rank and line.startswith("#"):
            break
        if in_rank:
            mr = re.match(r"^\s*\d+[.)]\s*\**\s*Concept\s+([A-Za-z0-9]+)", line)
            if mr and mr.group(1) in label_set and mr.group(1) not in out["ranking"]:
                out["ranking"].append(mr.group(1))
    return out


def personas_dir(study_dir: Path) -> Path:
    """panel/personas in a live study; personas/ in an archived round (archive.py flattens panel/)."""
    live = Path(study_dir) / "panel" / "personas"
    return live if live.is_dir() else Path(study_dir) / "personas"


def load_runs(study_dir: Path, cfg: dict) -> list[dict]:
    labels = list(label_map(cfg))
    n = len(cfg["factors"])
    seg = {p["id"]: p.get("segment", "") for p in cfg["personas"]}
    runs = []
    for p in sorted(personas_dir(study_dir).glob("*--*.md")):
        r = parse_persona_file(p, labels, n)
        r["segment"] = seg.get(r["pid"], "")
        runs.append(r)
    return runs


# ---------------------------------------------------------------- stats

def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else float("nan")


def sd(xs):
    xs = [x for x in xs if x is not None]
    return statistics.stdev(xs) if len(xs) > 1 else 0.0


def ranks(values: list[float]) -> list[float]:
    """Average ranks, 1 = smallest."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    r = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(x: list[float], y: list[float]) -> float:
    if len(x) < 3:
        return float("nan")
    mx, my = mean(x), mean(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def spearman(x: list[float], y: list[float]) -> float:
    return pearson(ranks(x), ranks(y))


def fmt(x, nd=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    return f"{x:.{nd}f}"


# ---------------------------------------------------------------- browser

# Expands collapsed content and forces common scroll-reveal patterns visible, so captured
# text and screenshots show what a reader who scrolled and clicked would see.
REVEAL_JS = (
    "document.querySelectorAll('details').forEach(d=>d.open=true);"
    "document.querySelectorAll('[aria-expanded=\"false\"]').forEach(b=>{try{b.click()}catch(e){}});"
    "document.querySelectorAll('.reveal,[data-reveal],[data-animate],.fade-in,.animate-in')"
    ".forEach(e=>{e.classList.add('is-visible','in','visible','revealed','in-view');"
    "e.style.opacity='1';e.style.transform='none';});1"
)


def which_montage() -> list[str]:
    if shutil.which("magick"):
        return ["magick", "montage"]
    if shutil.which("montage"):
        return ["montage"]
    raise SystemExit("ImageMagick is required (magick or montage on PATH)")


def which_convert() -> list[str]:
    if shutil.which("magick"):
        return ["magick"]
    if shutil.which("convert"):
        return ["convert"]
    raise SystemExit("ImageMagick is required (magick or convert on PATH)")


class Browser:
    """Thin wrapper over the agent-browser CLI with one named session."""

    def __init__(self, session: str):
        if not shutil.which("agent-browser"):
            raise SystemExit("agent-browser CLI is required")
        self.session = re.sub(r"[^A-Za-z0-9_-]", "-", session)

    def run(self, *args: str, check: bool = False) -> str:
        r = subprocess.run(["agent-browser", "--session", self.session, *args],
                           capture_output=True, text=True, timeout=180)
        if check and r.returncode != 0:
            raise RuntimeError(f"agent-browser {' '.join(args)}: {r.stderr.strip()}")
        return r.stdout.strip()

    def eval(self, js: str) -> str:
        out = self.run("eval", js)
        try:
            return json.loads(out)
        except (json.JSONDecodeError, ValueError):
            return out

    def open(self, url: str, width: int, height: int, settle_ms: int = 2500, media: str = ""):
        self.run("set", "viewport", str(width), str(height))
        if media:  # e.g. "light" or "light reduced-motion": stops captures landing mid-animation
            self.run("set", "media", *media.split())
        self.run("open", url, check=True)
        self.run("wait", str(settle_ms))

    def scroll_height(self) -> int:
        v = self.eval("document.documentElement.scrollHeight")
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return 0

    def close(self):
        self.run("close")
