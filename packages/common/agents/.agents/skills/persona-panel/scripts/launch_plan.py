"""What launch.py says about a study without starting anything: the plan, and the usage record.

launch.py owns the commands (plan, usage); this module works out the facts and words them. It
knows no harness: everything about one comes from its runner's capabilities() and check().

    unfit(cfg, entry)             why a run or job cannot be started on its runner as study.json
                                  has it. The same judgement stops "plan" and "run"
    usage_of(entry)               a run's usage, summed over its sessions
    unreported(entry)             the attempts whose spend is in no figure, because the launcher
                                  stopped the process before its harness reported any
    usage_figures(entries, states)   what the harnesses reported: per run, per model key, per
                                  role and in total
    usage_markdown(figures)       analysis/usage.md
    build(cfg, runs, jobs, states, scaffolded, launcher)   the plan, as one JSON-ready object
    render(plan)                  the plan, as the lines "plan" prints

The estimate and the ceiling are different things. The estimate is what the runs still to go
are likely to use: for each model key, the mean of what its finished runs reported, times the
runs to go. A key with no finished run gets a token figure from references/method.md and no
dollar figure, because prices are harness knowledge and change. The ceiling is what the study
can cost at most: each run's budget cap once (a cap covers all of a run's attempts) plus the
synthesis pool once. It is a maximum only where a harness enforces the cap, and then only as
far as its caveats allow: what a runner says about its cap's precision ("budget_cap_note"), and
the spend of a process that was stopped before it reported any.
"""

from __future__ import annotations

import os

import panel_lib as pl
import runners

# references/method.md, "Budget": images dominate a run's context, at roughly 20k tokens per
# concept page reviewed. It is the size of the context a run builds up, not the tokens a
# harness bills (every turn reads the context again), so it stands in only until a pilot has
# measured the real figure.
TOKENS_PER_CONCEPT_PAGE = 20_000

IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
TO_GO = ("pending", "running", "partial", "blocked", "failed")  # a limited run starts again only with --extend
FIGURES = ("input_tokens", "output_tokens", "cached_tokens", "cost_usd", "duration_s")
LIST_PRICE = ("Dollar figures are list-price equivalents: under a subscription login nothing is charged per "
              "token, so they say how much allowance is used, not what is paid.")
NATIVE = ("Native mode: the lead starts each run with its own subagent tool (runs.py next, mark and resume). "
          "Native mode has no limits, no usage record and no isolation beyond the instructions in the run "
          "prompt, so there is no ceiling and nothing below is enforced.")
CEILING_LABELS = {True: "guaranteed maximum", False: "estimate"}
STOPPED = ("a process the launcher stops, at its time limit or by the stop command, can end before its harness "
           "reports what it spent. That spend is counted when its session is next resumed and reports its total, "
           "so until then the attempt that resumes it can be given more of the cap than is left")


# ---------------------------------------------------------------- wording

def plural(n: int, noun: str) -> str:
    return f"{n:,} {noun}{'' if n == 1 else 's'}"


def money(x) -> str:
    if x is None:
        return "not reported"
    return f"${x:,.2f}" if abs(x * 100 - round(x * 100)) < 1e-9 else f"${x:,.4f}"  # whole cents, or finer


def stop(text: str) -> str:
    """A message from a CLI or a runner as the end of a sentence, with one full stop."""
    return str(text).strip().rstrip(".") + "."


def listed(words: list[str]) -> str:
    return ", ".join(words[:-1]) + (" and " if words[:-1] else "") + words[-1]


def attempts_named(numbers: list[int]) -> str:
    return f"attempt{'' if len(numbers) == 1 else 's'} {listed([str(n) for n in numbers])}"


def size(n: int) -> str:
    for unit, scale in (("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if n >= scale:
            return f"{n / scale:.1f} {unit}"
    return f"{n} bytes"


def span(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f}s"
    return f"{seconds / 60:.1f} min" if seconds < 5400 else f"{seconds / 3600:.1f} h"


def table(rows: list[list], indent: str = "  ") -> list[str]:
    rows = [[str(c) for c in r] for r in rows]
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return [(indent + "  ".join(c.ljust(w) for c, w in zip(r, widths))).rstrip() for r in rows]


# ---------------------------------------------------------------- what a runner cannot do

def label(entry: dict) -> str:
    """The name of an entry's model entry: its model key for a panellist run, its role for a job
    (synthesis.analyst and synthesis.writer are one model entry each)."""
    return entry["key"] if entry["role"] == "panellist" else entry["role"]


def unfit(cfg: dict, entry: dict) -> tuple[list[str], str | None]:
    """Why a run or job cannot be started on its runner as study.json has it, and a note where
    something it asks for is left out instead: (errors, note). An error refuses the launch."""
    caps, effort = runners.get(entry["runner"]).capabilities(), runners.check_effort(entry)
    errors = [effort["error"]] if effort["error"] else []
    if entry["role"] == "panellist" and cfg["materials"] == "full" and not caps["images_by_path"]:
        errors.append(f'{entry["runner"]} cannot open images, and this study\'s "materials" is "full", so its '
                      'runs would review designs they cannot see. A model that reads no images is for '
                      'text-only studies: set "materials": "text", or take the model entry out')
    return errors, effort["note"]


def lacks(cfg: dict, entry: dict, caps: dict) -> list[dict]:
    """The capabilities a model entry's runner does not have, each with what that means here."""
    panellist, out = entry["role"] == "panellist", []
    if panellist and not caps["images_by_path"]:
        out.append(("images", "it cannot open an image file" + (
            ", which a text-only study does not need" if cfg["materials"] == "text" else "")))
    if not caps["budget_cap"]:
        out.append(("budget cap", "the harness enforces no spend cap, so the time limit is what bounds its runs"))
    if not caps["resume"]:
        out.append(("resume", "an interrupted run cannot be continued in its session"))
    if panellist and cfg["browse"] and not caps["browser"]:
        out.append(("browser", "the study allows browsing, but its runs review from the files alone"))
    if not caps["purge"]:
        out.append(("purge", "its sessions cannot be deleted, so purge-sessions leaves them in place"))
    figures = {"tokens": "token", "cost": "cost", "duration": "duration"}  # what the harness reports: its figure
    silent = [name for k, name in figures.items() if not caps["usage"].get(k)]
    told = [k for k in figures if caps["usage"].get(k)]
    if silent:
        out.append((f"{listed(silent)} figures",
                    f"its harness reports {listed(told)} only" if told else "its harness reports no usage at all"))
    return [{"capability": c, "means": m} for c, m in out]


# ---------------------------------------------------------------- materials

def materials(cfg: dict) -> dict:
    """What is under panel/materials, per concept and in all: pages (one folder per captured
    page or state), images, text files and bytes. When nothing is captured yet, "pages" is
    counted from the site copies or the concept folders, and "pages_from" says which."""
    sd = cfg["_dir"]
    root = sd / "panel" / "materials"
    concepts = []
    for folder in sorted(root.glob("concept-*")) if root.is_dir() else []:
        files = [f for f in folder.rglob("*") if f.is_file()]
        text = [f for f in files if f.suffix == ".txt"]
        concepts.append({
            "concept": folder.name, "pages": sum(p.is_dir() for p in folder.iterdir()),
            "images": sum(f.suffix.lower() in IMAGE_TYPES for f in files), "text_files": len(text),
            "bytes": sum(f.stat().st_size for f in files), "text_bytes": sum(f.stat().st_size for f in text)})
    out = {k: sum(c[k] for c in concepts) for k in ("pages", "images", "text_files", "bytes", "text_bytes")}
    out.update(mode=cfg["materials"], captured=out["pages"] > 0, pages_from="panel/materials", concepts=concepts)
    if not out["captured"]:
        states = sum(len(c.get("states", [])) for c in cfg["concepts"])
        copies = list((sd / "panel" / "sites").glob("concept-*/*.html"))
        sources = [p for c in cfg["concepts"] for p in c["_path"].glob("*.html")]
        out.update(pages=len(copies or sources) + states, pages_from="panel/sites" if copies else "the concept folders")
    return out


# ---------------------------------------------------------------- usage

def usage_of(entry: dict) -> dict:
    return runners.total_usage(list((entry.get("sessions") or {}).values()))


def unreported(entry: dict) -> list[int]:
    """The numbers of the attempts whose spend is in no figure: the launcher stopped the process
    before its harness reported anything, and the session has reported no total since."""
    return [a["n"] for a in entry.get("attempts") or [] if a.get("usage_reported") is False]


def summed(rows: list[dict]) -> dict:
    """The figures of a group of runs. A figure is None when no run that was started reported
    it, and "unreported" counts, per figure, the started runs that did not."""
    started = [r for r in rows if r["attempts"]]
    out = {"runs": len(rows), "started": len(started), "done": sum(r["state"] == "done" for r in rows),
           "attempts": sum(r["attempts"] for r in rows), "seconds": round(sum(r["seconds"] or 0 for r in rows), 3),
           "unreported": {}}
    for f in FIGURES:
        reported = [r[f] for r in started if r[f] is not None]
        out[f] = sum(reported) if reported else None
        if reported and len(reported) < len(started):
            out["unreported"][f] = len(started) - len(reported)
    return out


def usage_figures(entries: list[dict], states: dict) -> dict:
    """What the harnesses reported, as stored in runs.json: {"runs", "keys", "roles", "total"}.

    entries are runs.json entries of any role and states maps a run id to its state. "runs"
    has one row per run or job, "keys" one per model key of the panel, "roles" one per role.
    A row's "unreported_attempts" are the attempts that unreported() names: their spend is
    missing from the row's figures, which is not the same as none.
    This is the one reading of the stored usage: the usage record and the plan's estimate both
    come from it, so a session that was resumed counts once in each.
    """
    rows = []
    for e in entries:
        used, attempts = usage_of(e), len(e.get("attempts") or [])
        rows.append({"run": e["run"], "role": e["role"], "key": e.get("key"), "runner": e.get("runner"),
                     "model": e.get("model"), "state": states[e["run"]], "attempts": attempts,
                     "seconds": (e.get("seconds_used") or 0) if attempts else None, **{f: used[f] for f in FIGURES},
                     "unreported_attempts": unreported(e)})
    keys = list(dict.fromkeys((r["key"], r["runner"], r["model"]) for r in rows if r["role"] == "panellist"))
    return {
        "runs": rows,
        "keys": [{"key": k, "runner": runner, "model": model,
                  **summed([r for r in rows if r["role"] == "panellist" and r["key"] == k])}
                 for k, runner, model in keys],
        "roles": [{"role": role, **summed([r for r in rows if r["role"] == role])}
                  for role in dict.fromkeys(r["role"] for r in rows)],
        "total": summed(rows)}


def usage_markdown(figures: dict) -> str:
    def cell(row, f, started, missing=0):
        stopped = row.get("unreported_attempts")  # a run's row only
        if not started:
            return "-"
        if row[f] is None:
            return "not reported" + (" (process was stopped)" if stopped else "")
        shown = f"${row[f]:.4f}" if f == "cost_usd" else f"{row[f]:,.1f} s" if f == "duration_s" else f"{row[f]:,}"
        return shown + (f" ({missing} not reported)" if missing else "") + (
            f" ({attempts_named(stopped)} not reported)" if stopped else "")

    def figures_of(row, started):
        return [cell(row, f, started, row.get("unreported", {}).get(f, 0)) for f in FIGURES]

    def clock(row, started):
        return f"{row['seconds']:,.1f} s" if started else "-"

    heads = ["Attempts", "Time", "Tokens in", "Tokens out", "Cached", "Cost", "Harness time"]  # the last five: FIGURES

    def line(lead, row, started):
        return "| " + " | ".join([*map(str, lead), str(row["attempts"]), clock(row, started),
                                  *figures_of(row, started)]) + " |"

    def block(title, lead_heads, rows):
        head = [*lead_heads, *heads]
        return ["", f"## {title}", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head), *rows]

    total = figures["total"]
    out = [
        "# Usage", "",
        "What each harness reported for the runs and jobs of this study, as stored in runs.json. launch.py "
        "rewrites this file after every process that ends, and `launch.py <study-dir> usage` rewrites it "
        "on request.", "",
        "- Tokens in counts all input, the cached part included. Tokens out includes thinking.",
        "- Time is the launcher's own clock over every attempt of a run. Harness time is what the harness "
        "reported for its processes.",
        '- "not reported" means the harness gave no such figure. "-" means nothing was started.',
        '- "not reported (process was stopped)" means the launcher stopped the process, at its time limit or '
        "by the stop command, before the harness reported anything for it. What it used is unknown, not zero, "
        "and is counted when its session is next resumed and reports its total.",
        "- A session that was resumed is counted once: a harness that reports running totals for a session "
        "has its latest total taken, not the sum of them.",
        f"- {LIST_PRICE}",
    ]
    stopped = [f"{r['run']} {attempts_named(r['unreported_attempts'])}" for r in figures["runs"]
               if r["unreported_attempts"]]
    if stopped:
        out += ["", f"Stopped before the harness reported anything, and so missing from every figure below: "
                    f"{', '.join(stopped)}."]
    out += block("Total", ["Runs and jobs", "Done"], [line([total["runs"], total["done"]], total, total["started"])])
    out += block("By role", ["Role", "Runs", "Done"],
                 [line([r["role"], r["runs"], r["done"]], r, r["started"]) for r in figures["roles"]])
    out += block("By model key", ["Key", "Runner", "Model", "Runs", "Done"],
                 [line([k["key"], k["runner"] or "-", k["model"] or "default", k["runs"], k["done"]], k, k["started"])
                  for k in figures["keys"]])
    out += block("By run", ["Run", "Role", "Key", "State"],
                 [line([r["run"], r["role"], r["key"] or "-", r["state"]], r, r["attempts"]) for r in figures["runs"]])
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- the plan

def estimate(rows: list[dict], pages: int, text_only: bool) -> dict:
    """What the runs still to go are likely to use, per model entry and in all. rows are
    usage_figures() rows with "entry" added, the name of each run's model entry."""
    entries = []
    for name, role in dict.fromkeys((r["entry"], r["role"]) for r in rows):
        own = [r for r in rows if (r["entry"], r["role"]) == (name, role)]
        done = [r for r in own if r["state"] == "done" and r["attempts"]]
        to_go = sum(r["state"] in TO_GO for r in own)
        tokens = [r["input_tokens"] + (r["output_tokens"] or 0) for r in done if r["input_tokens"] is not None]
        costs = [r["cost_usd"] for r in done if r["cost_usd"] is not None]
        per = {"tokens": None, "cost_usd": None, "seconds": None}
        if done:
            basis = "measured" if tokens else "duration"
            per.update(tokens=round(sum(tokens) / len(tokens)) if tokens else None,
                       cost_usd=sum(costs) / len(costs) if costs else None,
                       seconds=sum(r["seconds"] or 0 for r in done) / len(done))
        elif role == "panellist" and not text_only:
            basis, per["tokens"] = "method", TOKENS_PER_CONCEPT_PAGE * pages
        else:
            basis = "none"  # the method has no figure for a text-only run or for a synthesis job
        entries.append({
            "entry": name, "role": role, "runner": own[0]["runner"], "runs": len(own),
            "done": sum(r["state"] == "done" for r in own), "to_go": to_go, "basis": basis,
            "measured_runs": len(done), "per_run": per, "reports_cost": own[0].get("reports_cost", True),
            "tokens": per["tokens"] * to_go if per["tokens"] is not None else None,
            "cost_usd": per["cost_usd"] * to_go if per["cost_usd"] is not None else None,
            "seconds": per["seconds"] * to_go if per["seconds"] is not None else None,
            "cost": "measured" if per["cost_usd"] is not None else "not reported" if done
                    else "a pilot will provide one" if role == "panellist" else "a first job will provide one"})
    going = [e for e in entries if e["to_go"]]

    def total(field):
        known = [e[field] for e in going if e[field] is not None]
        return sum(known) if known else None

    return {"entries": entries, "tokens": total("tokens"), "cost_usd": total("cost_usd"), "seconds": total("seconds"),
            "no_tokens_for": [e["entry"] for e in going if e["tokens"] is None],
            "no_cost_for": [e["entry"] for e in going if e["cost_usd"] is None],
            "tokens_per_concept_page": TOKENS_PER_CONCEPT_PAGE, "pages": pages}


def ceiling(runs: list[dict], jobs: list[dict], pool: dict) -> dict:
    """The sum of the enforced budget caps plus the synthesis budget. runs and jobs are the
    plan's rows. Each run's cap counts once and the pool counts once."""
    capped = [r for r in runs if r["budget_enforced"]]
    uncapped, loose = ([r for r in rows if not r["budget_enforced"]] for rows in (runs, jobs))
    extended = [r for r in runs + jobs if r["extended"]]
    enforced = [r for r in runs + jobs if r["budget_enforced"]]
    caveats = [f"on {runner}, {note}" for runner, note in dict.fromkeys(
        (r["runner"], r["budget_cap_note"]) for r in enforced) if note]
    if enforced:
        silent = [f"{r['run']} {attempts_named(r['unreported_attempts'])}" for r in enforced
                  if r["unreported_attempts"]]
        caveats.append(STOPPED + (f". Not reported so far: {', '.join(silent)}" if silent else ""))
    runs_usd = round(sum(r["limits"]["budget_usd"] for r in capped), 6)
    more = sum(r["limits"]["budget_usd"] * r["extended"] for r in extended if r["budget_enforced"])
    return {
        "usd": round(runs_usd + pool["budget_usd"], 6), "guaranteed": not (uncapped or loose),
        "label": CEILING_LABELS[not (uncapped or loose)],
        "caveats": caveats,  # how the capped part of the figure can still be passed
        "capped_runs": len(capped), "capped_runs_usd": runs_usd,
        "synthesis_usd": pool["budget_usd"],
        "uncapped": [r["run"] for r in uncapped],  # runs: no cap, and so no part of the figure
        "uncapped_minutes": round(sum(r["limits"]["minutes"] for r in uncapped), 3),
        "uncapped_jobs": [r["run"] for r in loose],  # jobs: their share of the pool is counted, not enforced
        "uncapped_job_minutes": round(sum(r["limits"]["minutes"] for r in loose), 3),
        "holds": not extended, "extended": [r["run"] for r in extended],
        "with_extensions_usd": round(runs_usd + pool["budget_usd"] + more, 6)}


def build(cfg: dict, runs: list[dict], jobs: list[dict], states: dict, scaffolded: bool, launcher: dict | None) -> dict:
    """The plan as one JSON-ready object. Starts nothing and writes nothing: the only processes
    are each runner's check(), which makes no model call.

    runs are the panellist entries (runs.json's, or the ones study.json plans when scaffolded
    is false), jobs the analyst and writer entries study.json plans with anything a launcher
    recorded about them, and states maps each run and job id to its state.
    """
    sd, native = cfg["_dir"], all(e["runner"] is None for e in runs)
    mat = materials(cfg)
    planned = [] if native else [j for j in jobs if j["runner"]]
    pool, missing, notes, problems = pl.synthesis_pool(cfg), [], [], []

    if not scaffolded:
        missing.append(f"runs.json: run init_study.py {sd} first. The runs below are the ones it will create.")
    else:
        expected, found = {e["run"] for e in pl.planned_runs(cfg)}, {e["run"] for e in runs}
        if expected != found:
            notes.append("study.json no longer plans the runs that runs.json holds (they differ in "
                         + ", ".join(sorted(expected ^ found)[:6]) + (", ..." if len(expected ^ found) > 6 else "")
                         + f"). This plan follows runs.json. init_study.py {sd} --force scaffolds the study again, "
                         "and resets every run.")
    gone = [e["prompt"] for e in runs if not (sd / e["prompt"]).is_file()]
    if scaffolded and gone:
        missing.append(f"{plural(len(gone), 'run prompt')} ({', '.join(gone[:3])}{', ...' if len(gone) > 3 else ''})")
    if not mat["captured"]:
        missing.append(f"the materials: panel/materials has no captured page. Run capture.py {sd} before the "
                       f"runs. The estimate counts the pages in {mat['pages_from']}.")

    # One row per model entry: a model key of the panel, synthesis.analyst or synthesis.writer.
    groups = {}
    for e in runs + planned:
        groups.setdefault((e["role"], label(e)), []).append(e)
    models, by_entry = [], {}
    for (role, name), own in groups.items():
        first = own[0]
        row = {"entry": name, "role": role, "runner": first["runner"], "model": first["model"],
               "effort": first["effort"], "runs": len(own), "provider": None, "limits": None,
               "budget_enforced": False, "budget_cap_note": None, "lacks": [], "effort_note": None}
        if not native:
            caps = runners.get(first["runner"]).capabilities()
            errors, note = unfit(cfg, first)
            row.update(provider=caps["provider"], limits=pl.limits_for(cfg, role, first.get("key")),
                       budget_enforced=caps["budget_cap"], lacks=lacks(cfg, first, caps), effort_note=note,
                       budget_cap_note=(caps["budget_cap_note"] or None) if caps["budget_cap"] else None)
            problems += [f"{name}: {err}" for err in errors]
        models.append(row)
        by_entry[role, name] = row

    def run_row(e):
        m = by_entry[e["role"], label(e)]
        return {"run": e["run"], "role": e["role"], "persona": e.get("persona"), "name": e.get("name", ""),
                "key": e.get("key"), "runner": e["runner"], "model": e["model"], "effort": e["effort"],
                "limits": m["limits"], "budget_enforced": m["budget_enforced"],
                "budget_cap_note": m["budget_cap_note"], "unreported_attempts": unreported(e), "prompt": e["prompt"],
                "prompt_exists": (sd / e["prompt"]).is_file(), "file": e["file"], "state": states[e["run"]],
                "extended": e.get("extended") or 0}

    run_rows, job_rows = [run_row(e) for e in runs], [run_row(e) for e in planned]

    checked = []
    for name in dict.fromkeys(m["runner"] for m in models if not native):
        caps = runners.get(name).capabilities()
        check = runners.get(name).check()
        checked.append({
            "runner": name, "provider": caps["provider"], "ok": bool(check["ok"]), "message": check["message"],
            "concurrency": pl.runner_concurrency(cfg, name, caps["default_concurrency"]),
            "entries": [m["entry"] for m in models if m["runner"] == name],
            "billing_env_set": [v for v in caps["billing_env"] if os.environ.get(v)],  # names, never values
            "isolation_gaps": list(caps["isolation_gaps"])})
        if not check["ok"]:
            problems.append(f"{name}: cannot be used: {check['message']}")

    held = (f"{plural(mat['pages'], 'page')}, {plural(mat['images'], 'image')}, {size(mat['bytes'])}"
            if mat["captured"] else "not captured yet")
    receives = {
        "full": f"its run prompt, the panel instructions and everything under panel/materials ({held})",
        "text": "its run prompt, the panel instructions and the page text under panel/materials ("
                + (f"{plural(mat['text_files'], 'file')}, {size(mat['text_bytes'])}" if mat["captured"] else held)
                + "), with no images",
    }[cfg["materials"]]
    providers = []
    for provider in dict.fromkeys(m["provider"] for m in models if not native):
        entries = []
        for m in (m for m in models if m["provider"] == provider):
            browses = (m["role"] == "panellist" and cfg["browse"]
                       and runners.get(m["runner"]).capabilities()["browser"])
            entries.append({
                "entry": m["entry"], "role": m["role"], "runner": m["runner"], "runs": m["runs"],
                "receives": (receives + (", and any page of panel/sites it opens in the browser" if browses else "")
                             if m["role"] == "panellist" else
                             "the persona files it is given, analysis/ and whatever else in the study "
                             "directory it opens, where it works")})
        providers.append({"provider": provider, "entries": entries})

    usage = usage_figures([*runs, *planned], states)
    names = {e["run"]: label(e) for e in [*runs, *planned]}
    costed = {name: runners.get(name).capabilities()["usage"]["cost"] for name in {e["runner"] for e in runs + planned}
              if name}
    rows = [{**r, "entry": names[r["run"]], "reports_cost": costed.get(r["runner"], False)} for r in usage["runs"]]
    return {
        "study": cfg.get("study") or sd.name, "dir": str(sd), "native": native, "launcher": launcher,
        "missing": missing, "notes": notes,
        "materials": mat, "models": models, "runs": run_rows, "runners": checked, "providers": providers,
        "synthesis": None if native else {
            "pool": pool, "share": pl.synthesis_share(cfg), "shares": cfg["synthesis"].get("analysts", 1) + 1,
            "jobs": job_rows,
            "missing": [role for role in pl.JOB_ROLES if not any(j["role"] == role for j in planned)]},
        "estimate": estimate(rows, mat["pages"], cfg["materials"] == "text"),
        "used": usage["total"],
        "ceiling": None if native else ceiling(run_rows, job_rows, pool),
        "problems": problems, "ok": not problems}


def render(plan: dict) -> list[str]:
    """The plan as the lines the plan command prints."""
    sd, native, mat = plan["dir"], plan["native"], plan["materials"]
    out = [f"Plan for {plan['study']} ({sd}). This command starts nothing and changes nothing."]
    if plan["launcher"]:
        out.append(f'A launcher is running "{plan["launcher"].get("command")}" on this study '
                   f'(pid {plan["launcher"]["pid"]}).')
    out += [f"Missing: {m}" for m in plan["missing"]] + [f"Note: {n}" for n in plan["notes"]]
    if native:
        out += ["", NATIVE]

    def limits_of(row):
        if row["limits"] is None:
            return ["-", "-"]
        return [f"{row['limits']['minutes']:g} min",
                money(row["limits"]["budget_usd"]) + (" cap" if row["budget_enforced"] else ", not enforced")]

    def entry_cells(row):
        return [row["runner"] or "-", row["model"] or "default", row["effort"] or "-"]

    out += ["", "Materials, what each run can read under panel/materials:"]
    if not mat["captured"]:
        out.append(f"  Not captured yet. {plural(mat['pages'], 'page')} to capture, counted from {mat['pages_from']}.")
    elif mat["mode"] == "text":
        out.append(f"  Text-only study: {plural(mat['text_files'], 'page text file')}, {size(mat['text_bytes'])}, and "
                   f"no images ({plural(mat['pages'], 'page')}).")
    else:
        out.append(f"  {plural(mat['pages'], 'page')}, {plural(mat['images'], 'image')}, {size(mat['bytes'])} in all, "
                   f"of which page text {size(mat['text_bytes'])}.")
        out += table([[c["concept"], plural(c["pages"], "page"), plural(c["images"], "image"), size(c["bytes"])]
                      for c in mat["concepts"]], "    ")

    panel = [m for m in plan["models"] if m["role"] == "panellist"]
    out += ["", f"Model entries ({len(panel)})"
            + (":" if native else ", with the limits in force for each of their runs:")]
    out += table([["Key", "Runner", "Model", "Effort", "Runs", "Time limit", "Budget", "Provider"],
                  *([m["entry"], *entry_cells(m), m["runs"], *limits_of(m), m["provider"] or "-"] for m in panel)])
    for m in plan["models"]:
        for lack in m["lacks"]:
            out.append(f"  {m['entry']} lacks {lack['capability']}: {stop(lack['means'])}")
        if m["budget_cap_note"]:
            out.append(f"  {m['entry']}: {stop(m['budget_cap_note'])}")
        if m["effort_note"]:
            out.append(f"  {m['entry']}: {stop(m['effort_note'])}")

    out += ["", f"Runs ({len(plan['runs'])}):"]
    out += table([["Run", "Persona", "Key", "Runner", "Model", "Effort", "Time limit", "Budget", "State", "Prompt"],
                  *([r["run"], f"{r['persona']} {r['name']}".strip(), r["key"], *entry_cells(r), *limits_of(r),
                     r["state"], r["prompt"] + ("" if r["prompt_exists"] else " (missing)")] for r in plan["runs"])])
    if native:
        out += ["", *estimate_lines(plan), ""]
        return out

    out += ["", "Runners:"]
    for r in plan["runners"]:
        said = f"ready: {r['message']}" if r["ok"] else f"CANNOT BE USED: {r['message']}"
        out.append(f"  {r['runner']}: {stop(said)} Up to {plural(r['concurrency'], 'run')} at once.")
        if r["billing_env_set"]:
            out.append("    Set in this environment, and able to change who is billed: "
                       f"{', '.join(r['billing_env_set'])}.")
        if r["isolation_gaps"]:
            out.append("    Not switched off for its runs:")
            out += [f"      - {gap}" for gap in r["isolation_gaps"]]

    out += ["", "What each provider receives:"]
    for p in plan["providers"]:
        out.append(f"  {p['provider']}")
        for e in p["entries"]:
            unit = "run" if e["role"] == "panellist" else "job"
            out.append(f"    {e['entry']} ({e['runner']}, {plural(e['runs'], unit)}): from each {unit}, "
                       f"{e['receives']}.")

    syn = plan["synthesis"]
    out += ["", f"Analysts and writer, under limits.synthesis ({syn['pool']['minutes']:g} min for each job, "
                f"{money(syn['pool']['budget_usd'])} as one pool):"]
    if syn["jobs"]:
        out += table([["Job", "Runner", "Model", "Effort", "Time limit", "Budget", "State", "Prompt"],
                      *([j["run"], *entry_cells(j), *limits_of(j), j["state"], j["prompt"]] for j in syn["jobs"])])
        out.append(f"  Each job's budget is its share of the pool, divided equally among the {syn['shares']} jobs "
                   "study.json plans. A brief is written to prompts/ when its job is started.")
    for role in syn["missing"]:
        out.append(f'  synthesis.{role} is missing from study.json: there is no default, so "run --role {role}" '
                   f'will refuse. Add "synthesis": {{"{role}": {{"runner": "<runner>", "model": "<model>"}}}}.')

    out += ["", *estimate_lines(plan), "", *ceiling_lines(plan["ceiling"], syn), "", LIST_PRICE]
    if plan["problems"]:
        out += ["", 'Problems, which stop "run" as they stop this plan:', *(f"  {stop(p)}" for p in plan["problems"])]
    out.append("")
    return out


def estimate_lines(plan: dict) -> list[str]:
    est, used = plan["estimate"], plan["used"]
    out = ["Estimate of what the runs still to go will use (a forecast, not a limit):"]
    for e in est["entries"]:
        per, unit = e["per_run"], "run" if e["role"] == "panellist" else "job"
        go = plural(e["to_go"], unit) + " to go"
        if e["basis"] in ("measured", "duration"):
            cost = money(per["cost_usd"]) if per["cost_usd"] is not None else "cost not reported"
            tokens = f"{per['tokens']:,} tokens" if per["tokens"] is not None else "tokens not reported"
            line = (f"measured on {plural(e['measured_runs'], 'finished ' + unit)}: {tokens}, {cost} and "
                    f"{span(per['seconds'])} a {unit}. ")
            if not e["to_go"]:
                line += f"No {unit} to go."
            else:
                parts = ([f"{e['tokens']:,} tokens"] if e["tokens"] is not None else []) + (
                    [money(e["cost_usd"])] if e["cost_usd"] is not None else []) + [
                    f"{span(e['seconds'])} of run time"]
                line += f"{go}: about {', '.join(parts)}" + (
                    "." if e["cost_usd"] is not None else ". No dollar figure, so judge it by the time.")
        elif e["basis"] == "method":
            line = (f"no finished run to measure. From the method's figure of about {est['tokens_per_concept_page']:,} "
                    f"tokens of context per concept page per run, and {plural(est['pages'], 'page')}: about "
                    f"{per['tokens']:,} tokens a run, {e['tokens']:,} for {go}. No dollar figure: "
                    + ("native mode records no usage." if plan["native"]
                       else "a pilot will provide one." if e["reports_cost"]
                       else "its harness reports no cost, so judge it by the time."))
        else:
            line = (f"no finished {unit} to measure, and the method has no figure for it. {go.capitalize()}. "
                    f"No token or dollar figure: {e['cost']}.")
        out.append(f"  {e['entry']}: {line}")
    if est["tokens"] is not None or est["cost_usd"] is not None:
        parts = ([f"{est['tokens']:,} tokens"] if est["tokens"] is not None else []) + (
            [money(est["cost_usd"])] if est["cost_usd"] is not None else [])
        out.append(f"  In all: about {' and '.join(parts)}"
                   + (f". No dollar figure for {', '.join(est['no_cost_for'])}" if est["no_cost_for"] else "") + ".")
    if used["started"]:
        tokens = (f"{used['input_tokens'] + (used['output_tokens'] or 0):,} tokens"
                  if used["input_tokens"] is not None else "tokens not reported")
        out.append(f"  Used so far, by {plural(used['started'], 'run')} and jobs started: {tokens}, "
                   f"{money(used['cost_usd']) if used['cost_usd'] is not None else 'cost not reported'}.")
    elif not plan["native"]:
        out.append("  Nothing has run yet: launch.py pilot runs one persona on each model entry, and the next plan "
                   "estimates from what it measured.")
    return out


def ceiling_lines(c: dict, syn: dict) -> list[str]:
    out = [f"Ceiling: {money(c['usd'])}, " + (
        f"a guaranteed maximum{' apart from the caveats below' if c['caveats'] else ''}: every run and job has a "
        "budget cap that its harness enforces." if c["guaranteed"]
        else "an estimate, not a guaranteed maximum: some runs or jobs have no budget cap.")]
    out.append(f"  {money(c['capped_runs_usd'])} for {plural(c['capped_runs'], 'run')} with an enforced cap, each "
               "counted once, because a cap covers all of a run's attempts.")
    out.append(f"  {money(c['synthesis_usd'])} for the synthesis pool, counted once, because it is split into the "
               "jobs' caps. Panellist runs never spend it.")
    if c["uncapped"]:
        shown = ", ".join(c["uncapped"][:8]) + (", ..." if len(c["uncapped"]) > 8 else "")
        out.append(f"  {plural(len(c['uncapped']), 'run')} on a runner without a budget cap are left out of the figure "
                   f"({shown}). The time limit is what bounds them: at most {span(c['uncapped_minutes'] * 60)} of "
                   "run time between them.")
    if c["uncapped_jobs"]:
        out.append(f"  {plural(len(c['uncapped_jobs']), 'job')} on a runner without a budget cap have their share "
                   f"of the pool counted, but nothing enforces it ({', '.join(c['uncapped_jobs'])}). The time limit "
                   f"is what bounds them: at most {span(c['uncapped_job_minutes'] * 60)} of run time between them.")
    out += [f"  Caveat: {stop(caveat)}" for caveat in c["caveats"]]
    if not c["holds"]:
        out.append(f"  The ceiling no longer holds: resume --extend gave more than one allowance of the limits to "
                   f"{', '.join(c['extended'])}. With those allowances it comes to {money(c['with_extensions_usd'])}.")
    return out
