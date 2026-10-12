#!/usr/bin/env python3
"""Save a subagent's final reply to a file, from its transcript (JSONL) or a plain text file.

Some harnesses block subagents from writing report files and they return the document as
their reply instead. This pulls the last assistant text from the transcript and writes
everything from the first line matching --start (default: the first "# " heading).

For native mode. In a study that runs through runners, launch.py saves each analyst's and the
writer's reply itself, by the same rule (panel_lib.reply_document).

Usage: extract_agent_reply.py <transcript.jsonl|reply.txt> --out <file.md> [--start "# Round 2"] [--contains "text"]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402


def assistant_texts(path: Path) -> list[str]:
    texts = []
    for line in path.read_text().splitlines():
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = o.get("message") or o
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            t = "".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
            if t.strip():
                texts.append(t)
    return texts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--start", default=None, help="regex for the first line to keep (default: first '# ' heading)")
    ap.add_argument("--contains", default=None, help="pick the last reply containing this text")
    args = ap.parse_args()

    texts = assistant_texts(args.source) if args.source.suffix == ".jsonl" else [args.source.read_text()]
    if args.contains:
        texts = [t for t in texts if args.contains in t]
    if not texts:
        raise SystemExit("No assistant text found")
    text = max(texts[-3:], key=len)  # the document is usually the longest of the final replies
    body = pl.reply_document(text, args.start)
    args.out.write_text(body + "\n")
    dashes = sum(body.count(d) for d in pl.DASHES)
    print(f"Wrote {args.out} ({len(body)} chars, {dashes} em/en dashes)")


if __name__ == "__main__":
    main()
