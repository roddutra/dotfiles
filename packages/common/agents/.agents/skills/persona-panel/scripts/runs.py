#!/usr/bin/env python3
"""Track panel runs: which are done, in progress or pending, and what to launch next.

A run is "done" when its persona file has a scored section for every concept and the final
"Out of character" section; "started" when it has at least one concept section.

Usage:
  runs.py <study-dir> status
  runs.py <study-dir> next [--limit 20] [--running P01-opus,P02-fable]   # prompts to launch now
  runs.py <study-dir> prompt <run-id>                                    # the run's launch prompt
  runs.py <study-dir> mark <run-id> <agent-id>                           # record the subagent id
  runs.py <study-dir> resume [<run-id>]                                  # resume messages for unfinished runs

Record each subagent id with "mark" as soon as you launch it. runs.json survives context
compaction, so an interrupted run (usage limit, crash) can be resumed with SendMessage to the
same agent instead of relaunched, which would duplicate sections or lose its reading.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402


def run_states(sd: Path, cfg: dict) -> list[dict]:
    labels = list(pl.label_map(cfg))
    n = len(cfg["factors"])
    out = []
    for r in json.loads((sd / "runs.json").read_text()):
        f = sd / r["file"]
        p = pl.parse_persona_file(f, labels, n) if f.exists() else None
        scored = len(p["scores"]) if p else 0
        if p and scored == len(labels) and p["has_final"]:
            state = "done"
        elif p and p["sections"]:
            state = "started"
        else:
            state = "pending"
        out.append({**r, "state": state, "scored": scored, "of": len(labels),
                    "written": sorted(p["sections"]) if p else [], "has_final": bool(p and p["has_final"])})
    return out


def resume_message(s: dict) -> str:
    if s["state"] == "pending":
        return ("Your run was interrupted before any concept was written. Start again from step 1 of your "
                "original instructions.")
    done = ", ".join(s["written"])
    if s["scored"] == s["of"] and not s["has_final"]:
        todo = "All concept sections are written. Re-read your persona file, then append the final sections."
    else:
        todo = ("Re-read your persona file, review the remaining concepts in your listed order, append each "
                "section as you finish it, then append the final sections.")
    return (f"Your run was cut off before it finished. Pick up where you left off.\n"
            f"- Already written: {done}. Do not rewrite or repeat those sections.\n"
            f"- {todo}\n- All the original rules still apply. When done, reply with the summary the instructions ask for.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    ap.add_argument("cmd", choices=["status", "next", "prompt", "mark", "resume"])
    ap.add_argument("run", nargs="?")
    ap.add_argument("agent", nargs="?")
    ap.add_argument("--limit", type=int, default=20, help="concurrent subagent cap (Claude Code allows 20)")
    ap.add_argument("--running", default="", help="comma-separated run ids already running")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    cfg = pl.load_study(args.study_dir)
    sd = cfg["_dir"]
    states = run_states(sd, cfg)

    if args.cmd == "status":
        if args.json:
            print(json.dumps(states, indent=2))
            return
        counts = {}
        for s in states:
            counts[s["state"]] = counts.get(s["state"], 0) + 1
            print(f"{s['run']:<16} {s['state']:<8} {s['scored']}/{s['of']}  {s['name']}")
        print(" | ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    elif args.cmd == "next":
        running = {x.strip() for x in args.running.split(",") if x.strip()}
        slots = max(0, args.limit - len(running))
        # A pending run with a recorded agent id was launched and hasn't written yet: count it as running.
        running |= {s["run"] for s in states if s["state"] != "done" and s.get("agent")}
        slots = max(0, args.limit - len(running))
        todo = [s for s in states if s["state"] == "pending" and s["run"] not in running][:slots]
        if args.json:
            print(json.dumps([{**s, "prompt_text": (sd / s["prompt"]).read_text()} for s in todo], indent=2))
            return
        for s in todo:
            print(f"=== {s['run']} (model: {s['model']}, description: Panel {s['run']})")
            print((sd / s["prompt"]).read_text())
        print(f"{len(todo)} to launch; {sum(s['state'] == 'pending' for s in states) - len(todo)} left queued.")
    elif args.cmd == "mark":
        if not (args.run and args.agent):
            raise SystemExit("usage: runs.py <study> mark <run-id> <agent-id>")
        data = json.loads((sd / "runs.json").read_text())
        hit = [r for r in data if r["run"] == args.run]
        if not hit:
            raise SystemExit(f"No run {args.run}")
        hit[0]["agent"] = args.agent
        (sd / "runs.json").write_text(json.dumps(data, indent=2) + "\n")
        print(f"{args.run} -> {args.agent}")
    elif args.cmd == "resume":
        todo = [s for s in states if s["state"] != "done" and (not args.run or s["run"] == args.run)]
        for s in todo:
            print(f"=== {s['run']} ({s['state']}, agent: {s.get('agent') or 'not recorded: relaunch with runs.py prompt'})")
            print(resume_message(s))
        print(f"{len(todo)} unfinished runs.")
    else:
        match = [s for s in states if s["run"] == args.run]
        if not match:
            raise SystemExit(f"No run {args.run}")
        print((sd / match[0]["prompt"]).read_text())


if __name__ == "__main__":
    main()
