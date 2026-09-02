#!/usr/bin/env python3
"""Build a dependency-free HTML gallery for comparing interface concepts."""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from urllib.parse import quote


def parse_item(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("item must use LABEL=PATH")

    label, raw_path = value.split("=", 1)
    label = label.strip()
    path = Path(raw_path.strip()).expanduser()
    if not label or not raw_path.strip():
        raise argparse.ArgumentTypeError("item must include both a label and path")
    return label, path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an HTML gallery for side-by-side concept evaluation."
    )
    parser.add_argument("--title", default="Interface concepts")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--item",
        action="append",
        required=True,
        type=parse_item,
        metavar="LABEL=PATH",
        help="Concept label and entry file. Repeat for each concept.",
    )
    return parser.parse_args()


def concept_data(items: list[tuple[str, Path]], output_dir: Path) -> list[dict[str, str]]:
    concepts: list[dict[str, str]] = []
    for label, raw_path in items:
        path = raw_path.resolve()
        if not path.is_file():
            raise SystemExit(f"Concept file does not exist: {raw_path}")
        relative = Path(os.path.relpath(path, output_dir))
        concepts.append({"label": label, "url": quote(relative.as_posix(), safe="/")})
    return concepts


def render(title: str, concepts: list[dict[str, str]]) -> str:
    safe_title = html.escape(title)
    data = json.dumps(concepts, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    :root {{ color-scheme: dark; font-family: ui-sans-serif, system-ui, sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; background: #11110f; color: #f3f0e8; }}
    button, a {{ font: inherit; }}
    .shell {{ display: grid; grid-template-columns: 250px minmax(0, 1fr); min-height: 100vh; }}
    .sidebar {{ padding: 22px 16px; border-right: 1px solid #2d2c27; background: #171713; }}
    .eyebrow {{ margin: 0 6px 7px; color: #9b988e; font-size: 11px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }}
    h1 {{ margin: 0 6px 24px; font-size: 20px; line-height: 1.15; text-wrap: balance; }}
    .concepts {{ display: grid; gap: 7px; }}
    .concept {{ width: 100%; padding: 11px 12px; border: 0; border-radius: 8px; background: transparent; color: #aaa79d; cursor: pointer; text-align: left; transition: background-color 140ms, color 140ms; }}
    .concept:hover {{ background: #22221d; color: #f3f0e8; }}
    .concept[aria-current="true"] {{ background: #f0cc69; color: #1a1811; }}
    .main {{ min-width: 0; display: grid; grid-template-rows: auto minmax(0, 1fr); }}
    .toolbar {{ min-height: 64px; display: flex; gap: 18px; align-items: center; justify-content: space-between; padding: 12px 18px; border-bottom: 1px solid #2d2c27; }}
    .selected {{ min-width: 0; font-size: 14px; font-weight: 650; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .actions, .viewports {{ display: flex; gap: 6px; align-items: center; }}
    .control, .open {{ min-height: 36px; padding: 8px 11px; border: 1px solid #36352f; border-radius: 7px; background: #1d1d19; color: #c7c4ba; cursor: pointer; text-decoration: none; transition: border-color 140ms, color 140ms, background-color 140ms; }}
    .control:hover, .open:hover {{ border-color: #69665b; color: #fff; }}
    .control[aria-pressed="true"] {{ border-color: #f0cc69; background: #28251b; color: #f0cc69; }}
    .stage {{ min-height: 0; display: grid; place-items: start center; overflow: auto; padding: 20px; background: #0b0b09; }}
    .frame {{ width: 100%; height: calc(100vh - 105px); min-height: 620px; border: 0; border-radius: 10px; background: white; box-shadow: 0 0 0 1px #33322d, 0 18px 60px rgba(0, 0, 0, .45); transition: width 180ms ease; }}
    @media (max-width: 760px) {{
      .shell {{ grid-template-columns: 1fr; grid-template-rows: auto minmax(0, 1fr); }}
      .sidebar {{ border-right: 0; border-bottom: 1px solid #2d2c27; padding: 14px; }}
      .eyebrow, h1 {{ display: none; }}
      .concepts {{ display: flex; overflow-x: auto; }}
      .concept {{ width: auto; white-space: nowrap; }}
      .toolbar {{ align-items: flex-start; flex-direction: column; gap: 10px; }}
      .actions {{ width: 100%; justify-content: space-between; }}
      .stage {{ padding: 12px; }}
      .frame {{ height: 72vh; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <p class="eyebrow">Concept review</p>
      <h1>{safe_title}</h1>
      <nav class="concepts" aria-label="Concepts" id="concepts"></nav>
    </aside>
    <main class="main">
      <header class="toolbar">
        <div class="selected" id="selected"></div>
        <div class="actions">
          <div class="viewports" aria-label="Preview width">
            <button class="control" data-width="100%" aria-pressed="true">Desktop</button>
            <button class="control" data-width="1024px" aria-pressed="false">Tablet</button>
            <button class="control" data-width="390px" aria-pressed="false">Mobile</button>
          </div>
          <a class="open" id="open" target="_blank" rel="noopener">Open</a>
        </div>
      </header>
      <section class="stage">
        <iframe class="frame" id="frame" title="Selected interface concept"></iframe>
      </section>
    </main>
  </div>
  <script>
    const concepts = {data};
    const nav = document.querySelector('#concepts');
    const frame = document.querySelector('#frame');
    const selected = document.querySelector('#selected');
    const open = document.querySelector('#open');

    function selectConcept(index) {{
      const concept = concepts[index] || concepts[0];
      frame.src = concept.url;
      selected.textContent = concept.label;
      open.href = concept.url;
      document.querySelectorAll('.concept').forEach((button, buttonIndex) => {{
        button.setAttribute('aria-current', String(buttonIndex === index));
      }});
      const url = new URL(window.location.href);
      url.searchParams.set('concept', String(index));
      history.replaceState(null, '', url);
    }}

    concepts.forEach((concept, index) => {{
      const button = document.createElement('button');
      button.className = 'concept';
      button.type = 'button';
      button.textContent = concept.label;
      button.addEventListener('click', () => selectConcept(index));
      nav.appendChild(button);
    }});

    document.querySelectorAll('[data-width]').forEach((button) => {{
      button.addEventListener('click', () => {{
        frame.style.width = button.dataset.width;
        document.querySelectorAll('[data-width]').forEach((candidate) => {{
          candidate.setAttribute('aria-pressed', String(candidate === button));
        }});
      }});
    }});

    const requested = Number(new URLSearchParams(location.search).get('concept'));
    selectConcept(Number.isInteger(requested) && requested >= 0 && requested < concepts.length ? requested : 0);
  </script>
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    concepts = concept_data(args.item, output.parent)
    output.write_text(render(args.title, concepts), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
