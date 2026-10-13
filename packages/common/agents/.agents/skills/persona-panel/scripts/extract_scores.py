#!/usr/bin/env python3
"""Extract every run's scores, ranking and progress into three files in analysis/.

scores.csv:   persona_id, persona, model, replicate, complete, segment, concept, position,
              <factor keys...>
rankings.csv: persona_id, model, replicate, complete, segment, rank, concept
runs.csv:     run, persona_id, model, replicate, segment, state, complete, written, scored,
              has_final

"model" is the model key. "position" is where the concept sat in that persona's review order
(1-based), for order-effect checks. In a usability study the unit is a task: the "concept" column
of scores.csv is named "task" and holds the task id, "position" is the task's place in the order
study.json lists the tasks, and rankings.csv is the header alone, because tasks are not ranked.
A study with one concept has no ranking: rankings.csv is then the header alone, whatever a
panellist wrote. "complete" is 1 when panel_lib.run_progress says the run is complete and 0
otherwise: analyze.py keeps the rows of incomplete runs out of its headline tables.

runs.csv has one row per expected run (panel_lib.run_records), whether or not it wrote anything.
"state" is its lifecycle state (panel_lib.run_state); "written" and "scored" are the concept
labels with a section and with a score row, separated by spaces; "has_final" is 1 when the final
sections exist.

A run whose latest follow-up question is not settled yet is read as it stood before the question
(panel_lib.read_persona), so nothing a follow-up changed reaches a CSV before a launcher has
accepted it. One line names each such run.

A usability study gets two files more, and three columns more in runs.csv, so that analyze.py
still reads nothing but analysis/*.csv:

tasks.csv: run, persona_id, model, replicate, segment, complete, state, task, position, limit,
           written, claimed, checked, mismatch, stopped, steps, attempts, last_step,
           last_screenshot, last_page
steps.csv: run, persona_id, model, replicate, segment, complete, task, attempt, step, done, on,
           to, screenshot, sensitive
runs.csv:  ... limited_by, step_entries, step_notes

tasks.csv has one row for each expected run and task, attempted or not:
  written    1 when the persona file has the task's section
  claimed    what the panellist says became of the task, from the section's "Outcome" field
             (panel_lib.claimed_outcome): completed, gave up, ran out of steps, or unparsed.
             Empty without a section
  checked    what the task's success check said, from the run's entry in runs.json: yes
             (completed), no (not completed), error (the check failed to run: no verdict),
             "not run" (the task has a check, and the run none on record: checks run when a run
             is done, limited or failed) or none (the task has no check)
  mismatch   check_denies (claimed completed, and the check says not completed), check_passes
             (claimed gave up or ran out of steps, and the check says completed), else empty. A
             check that failed to run is never a mismatch
  stopped    where the run's attempt of the task ended: completed, gave up, ran out of steps or
             unparsed (its section is written: the claim); "step limit", "time limit" or "budget
             limit" (the run was stopped as limited with this task under way, by the launcher's
             backstop, at its time limit, or by its harness's spend cap); unfinished (the run
             stopped some other way with the task under way); "not reached"
  steps      the complete steps of the task's latest attempt in the step log: those with both
             their intent and their result entry (panel_lib.task_steps). "limit" is the task's
             step limit and "attempts" how many attempts the log has for it, 0 with no entry.
             Only entries that count are read (panel_lib.counted): one that is not in the form
             of an entry, or carries an attempt number the launcher did not issue for its task
             (runs.json, "task_attempts"), supersedes nothing and is no step
  last_step, last_screenshot   the last complete step of that attempt and its screenshot
  last_page  the page the run was on when it left the task: where its last complete step left
             it, or the task's start page before any step. Empty when the log does not say,
             or has no entry for the task

steps.csv has one row for each step of each task's latest attempt. "done" is 1 for a complete
step. "to" is the page its result entry says the action left the run on, from the entry's "url"
(page_of()), and "on" the page it was taken on: the "to" of the step before, or the task's start
page. "sensitive" is 1 when the result entry says the step entered a secret. The sentences a
panellist wrote (sees, expects, action, happened) stay in the step log, which is the evidence.

runs.csv: "limited_by" is what stopped a limited run (time, budget or steps, from runs.json),
"step_entries" how many entries its step log has (0 with no log), and "step_notes" what is wrong
with the log's form (panel_lib.step_notes), separated by "; ".

What these files repeat of a step log is little, and none of it unchecked: a page, a screenshot's
name and a task id the study does not have each go through panel_lib.shown(), which describes
a value that holds a known secret, is long or has other characters than a name has, and does
not repeat it. So a secret in a step log, which check_runs.py fails the run for, is not copied
into a CSV on the way. A step log that cannot be read as the run's (a symbolic link, at its
name or at its folder's) is read as no log, and check_runs.py says why.

Usage: extract_scores.py <study-dir>
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import accounts  # noqa: E402
import panel_lib as pl  # noqa: E402

CHECKED = {True: "yes", False: "no", None: "error"}  # a success check's record -> the "checked" column
LIMITS = {"steps": "step limit", "time": "time limit", "budget": "budget limit"}  # limited_by -> "stopped"


def page_of(cfg: dict, url) -> str:
    """The page an address names, as the analysis groups steps by it: the path, without the
    target's scheme and host, without the query, and with a fragment only when it reads as a
    route ("#/settings"). An address on another host keeps the host. Empty when there is none."""
    if not isinstance(url, str) or not url.strip():
        return ""
    try:
        parts, base = urlsplit(url.strip()), urlsplit(cfg["target"]["base_url"])
    except ValueError:
        return ""
    route = f"#{parts.fragment}" if parts.fragment.startswith(("/", "!/")) else ""
    return ("" if parts.netloc in ("", base.netloc) else parts.netloc) + (parts.path or "/") + route


def task_rows(cfg: dict, run: dict, entry: dict, logged: dict, known: dict | None) -> tuple[list[list], list[list]]:
    """The rows of tasks.csv and steps.csv for one run, without the columns that say whose they
    are. run is its pl.run_records() record, entry its entry in runs.json ({} when it has none)
    and logged its step log as pl.task_steps() has it. known is what a scan knows the study's
    secrets by: the page and the screenshot name of a step are the panellist's own text, and
    are written as pl.shown() allows."""
    def page(url):
        named = page_of(cfg, url)
        return pl.shown(known, named, "an address that is not shown", pl.PAGE_MOST) if named else ""

    def shot(name):
        return pl.shown(known, name, "a screenshot name that is not shown") if isinstance(name, str) and name else ""

    sections = run["parsed"]["sections"] if run["parsed"] else {}
    checks, limited_by = entry.get("checks") or {}, entry.get("limited_by") if run["state"] == "limited" else None
    stop = next((a["stop"] for a in reversed(entry.get("attempts") or []) if a.get("stop")), {})
    unwritten = [t["id"] for t in cfg["tasks"] if t["id"] not in sections]
    under_way = (unwritten or [None])[0]  # the first task with no section, unless the step limit names another
    if limited_by == "steps" and stop.get("task") in unwritten:
        under_way = stop["task"]
    tasks, steps = [], []
    for position, t in enumerate(cfg["tasks"], start=1):
        tid, log = t["id"], logged.get(t["id"]) or {"attempt": 1, "attempts": 0, "steps": []}
        claimed, check = pl.claimed_outcome(sections.get(tid)), checks.get(tid)
        checked = ("none" if "success_check" not in t else "not run" if not isinstance(check, dict)
                   else CHECKED[check.get("checked")])
        mismatch = ("check_denies" if claimed == "completed" and checked == "no"
                    else "check_passes" if claimed in pl.USABILITY_OUTCOMES[1:] and checked == "yes" else "")
        on, last = page_of(cfg, pl.task_url(cfg, t)), None
        for step in log["steps"]:
            result = step["result"] or {}
            done, to = bool(step["intent"] and step["result"]), page(result.get("url"))
            steps.append([tid, log["attempt"], step["step"], int(done), on, to if done else "",
                          shot(result.get("screenshot")), int(result.get("sensitive") is True)])
            if done:
                last = steps[-1]
            on = to if done else on  # a step that did not finish left the run where it was, as far as the log says
        began = log["steps"] or (tid == under_way and run["state"] not in ("pending", "running"))
        stopped = (claimed if tid in sections else LIMITS[limited_by] if limited_by and tid == under_way
                   else "unfinished" if began else "not reached")
        tasks.append([run["state"], tid, position, t["steps"], int(tid in sections), claimed, checked, mismatch,
                      stopped, sum(row[3] for row in steps if row[0] == tid), log["attempts"],
                      last[2] if last else "", last[6] if last else "", on if log["attempts"] else ""])
    return tasks, steps


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    cfg = pl.load_study(ap.parse_args().study_dir)
    sd = cfg["_dir"]
    labels, unit = pl.study_units(cfg), pl.unit_nouns(cfg)[0]
    keys = pl.factor_keys(cfg)
    runs = pl.run_records(sd, cfg)
    (sd / "analysis").mkdir(exist_ok=True)
    n_rows = incomplete = 0
    usability = cfg["type"] == "usability"
    entries = {e["run"]: e for e in pl.read_runs(sd)} if usability and (sd / "runs.json").exists() else {}
    known = accounts.known(cfg) if usability else None  # what pl.shown() looks for in a panellist's own text
    task_table, step_table = [], []  # the rows of tasks.csv and steps.csv
    with open(sd / "analysis" / "scores.csv", "w", newline="") as f, \
            open(sd / "analysis" / "rankings.csv", "w", newline="") as g, \
            open(sd / "analysis" / "runs.csv", "w", newline="") as h:
        w = csv.writer(f)
        w.writerow(["persona_id", "persona", "model", "replicate", "complete", "segment", unit, "position",
                    *keys])
        rw = csv.writer(g)
        rw.writerow(["persona_id", "model", "replicate", "complete", "segment", "rank", unit])
        sw = csv.writer(h)
        sw.writerow(["run", "persona_id", "model", "replicate", "segment", "state", "complete", "written",
                     "scored", "has_final", *(["limited_by", "step_entries", "step_notes"] if usability else [])])
        for run in runs:
            prog, r = run["progress"], run["parsed"]
            complete = int(prog["complete"])
            incomplete += not complete
            who = [run["pid"], run["model"], run["replicate"]]
            more = []
            if usability and run["run"] not in entries:  # named by a file's name alone, which may be a panellist's own
                run = {**run, **{k: pl.shown(known, run[k], "a name that is not shown")
                                 for k in ("run", "pid", "model")}}
                who = [run["pid"], run["model"], run["replicate"]]
            if usability:
                entry, (logged, odd) = entries.get(run["run"]) or {}, pl.read_steps(sd, run["run"])
                issued = pl.issued_attempts(entry)
                tasks, steps = task_rows(cfg, run, entry, pl.task_steps(logged, issued), known)
                whose = [run["run"], *who, run["segment"], complete]
                task_table += [[*whose, *row] for row in tasks]
                step_table += [[*whose, *row] for row in steps]
                more = [(entry.get("limited_by") or "") if run["state"] == "limited" else "", len(logged),
                        "; ".join(pl.step_notes(cfg, logged, odd, issued, known))]
            sw.writerow([run["run"], *who, run["segment"], run["state"], complete, " ".join(prog["written"]),
                         " ".join(prog["scored"]), int(prog["has_final"]), *more])
            if not r:
                continue
            order = r["order"] or pl.unit_order(cfg, run["pid"])
            for label in labels:
                if label in r["scores"]:
                    pos = order.index(label) + 1 if label in order else ""
                    slug = pl.shown(known, r["slug"], "a name that is not shown") if usability else r["slug"]
                    w.writerow([run["pid"], slug, *who[1:], complete, run["segment"], label, pos,
                                *[f"{x:g}" for x in r["scores"][label]]])
                    n_rows += 1
            for i, label in enumerate(r["ranking"] if pl.ranked(cfg) else [], start=1):
                rw.writerow([*who, complete, run["segment"], i, label])
    if usability:
        whose = ["run", "persona_id", "model", "replicate", "segment", "complete"]
        for name, head, table in (
                ("tasks.csv", ["state", "task", "position", "limit", "written", "claimed", "checked", "mismatch",
                               "stopped", "steps", "attempts", "last_step", "last_screenshot", "last_page"],
                 task_table),
                ("steps.csv", ["task", "attempt", "step", "done", "on", "to", "screenshot", "sensitive"], step_table)):
            with open(sd / "analysis" / name, "w", newline="") as f:
                csv.writer(f).writerows([[*whose, *head], *table])
    print(*pl.unsettled_lines(runs), f"{pl.plural(n_rows, 'score row')} from {pl.plural(len(runs), 'run')}; "
          f"{pl.plural(incomplete, 'run')} incomplete "
          "(run check_runs.py for details)",
          *([f"{pl.plural(len(task_table), 'task row')} and {pl.plural(len(step_table), 'step row')}, in "
             "analysis/tasks.csv and analysis/steps.csv"] if usability else []), sep="\n")


if __name__ == "__main__":
    main()
