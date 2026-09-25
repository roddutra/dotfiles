#!/usr/bin/env python3
"""Save a subagent's final reply to a file, from its transcript (JSONL) or a plain text file.

Some harnesses block subagents from writing report files and they return the document as
their reply instead. This pulls the last assistant text from the transcript and writes
everything from the first line matching --start (default: the first "# " heading).

Usage: extract_agent_reply.py <transcript.jsonl|reply.txt> --out <file.md> [--start "# Round 2"] [--contains "text"]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


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
    lines = text.splitlines()
    pat = re.compile(args.start) if args.start else re.compile(r"^# ")
    start = next((i for i, l in enumerate(lines) if pat.search(l)), 0)
    body = "\n".join(lines[start:]).strip()
    body = re.sub(r"\n```\s*$", "", body)
    args.out.write_text(body + "\n")
    dashes = sum(body.count(d) for d in ("–", "—"))
    print(f"Wrote {args.out} ({len(body)} chars, {dashes} em/en dashes)")


if __name__ == "__main__":
    main()
