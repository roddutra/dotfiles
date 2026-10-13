#!/usr/bin/env python3
"""Build a study's roster from a grid, and move personas between a study and a roster file.

grid: write skeleton personas into study.json from its "roster":

    "roster": {
      "roles": ["Staff", {"role": "Owner of a 2-site cafe", "segment": "owner"}],
      "personalities": ["Curious sceptic: burned before, needs proof", "Time-poor skimmer"],
      "stages": ["new to the industry", "20 years in"],
      "caps": {"personas": 8, "runs": 48}
    }

  roles          at least one. A string is the role line, and its segment is the same words as a
                 key ("Staff" gives "staff"). An object gives the role line and its segment
  personalities  at least one string
  stages         optional strings. A stage is added to the role line after a comma, so write it
                 as it should read there
  caps           optional. "personas" is the most personas the study may have, "runs" the most
                 runs: personas x model entries x replicates

  A skeleton has an id, the name "TODO", a role, a personality, a segment and an empty bio.
  Write each one's name and bio (references/personas.md): init_study.py refuses a study while a
  persona is named "TODO".

  The full grid is every role x personality x stage. When caps.personas is below it, the
  selection is the same for the same study "seed" and roster, every role and every personality
  appears at least once, and so does every stage when the cap is at least the number of stages
  (below that, as many stages as the cap, and the ones left out are named). The rest of the cap
  is filled one persona at a time, each the combination whose role, personality and stage have
  been used least so far. A cap below the larger of roles and personalities cannot be met: the
  script says what the least is and writes nothing.

  A roster over caps.runs is refused, with the arithmetic. It needs "models" in study.json.

  grid never changes a persona that has been written. Skeletons nobody has touched (the name
  still "TODO" and no bio) are its own, and it replaces them. When study.json holds written
  personas it stops, unless --append: then they stay as they are and the skeletons go after
  them, numbered from the highest id, with caps.personas and caps.runs counting both. A written
  persona whose role line and personality are still the grid's words counts as that
  combination: it is not added again, and it counts towards every role, personality and stage
  appearing. One whose role line was rewritten is not recognised, so check for a double: it
  takes a place under the cap and covers nothing. When what is left of the cap beside the
  written personas cannot cover every role and personality, and every stage where the cap is
  at least the number of stages, the script says what the least cap is and writes nothing.

export: copy every persona of the study into a roster file, a JSON file kept in the project's
own repository so that later studies reuse the same people under the same ids:

    {"personas": [{"id", "name", "slug", "role", "personality", "segment", "bio", "variant_of"}]}

  It merges by id: a persona the file lacks is added, one it holds unchanged is left, and one
  it holds with different content stops the export, unless --update replaces it. While the
  study has a skeleton the export stops and writes nothing: a roster file holds whole personas.
  It also refuses to write a roster file under the study's panel/.

import: copy personas from a roster file into study.json, all of them or the ones --ids names.
  A persona already in the study with the same content is skipped. One with the same id and
  different content stops the import: it never changes a persona in a study. A variant needs
  its parent in the study or among the personas imported with it. To add skeletons to imported
  personas, import first, then grid --append.

Only those eight persona fields ever move, in either direction: no concepts, notes, hypotheses
or results. study.json is rewritten with its keys in their order and a 2-space indent.

Usage: roster.py <study-dir> grid [--append]
       roster.py <study-dir> export --to <file> [--update]
       roster.py <study-dir> import --from <file> [--ids P01,P03]
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402

CARD = ("id", "name", "slug", "role", "personality", "segment", "bio", "variant_of")
ROSTER_SHAPE = ('"roster": {"roles": [...], "personalities": [...], "stages": [...], '
                '"caps": {"personas": n, "runs": n}}')


def stop(msg: str):
    raise SystemExit(msg)


def text(x) -> bool:
    return isinstance(x, str) and bool(x.strip())


plural = pl.plural  # number agreement, the same in every script


def read_json(path: Path, what: str) -> dict:
    try:
        data = json.loads(path.read_text())
    except OSError as err:
        stop(f"Cannot read {path} ({err.strerror}).")
    except ValueError as err:
        stop(f"{path} is not valid JSON: {err}")
    if not isinstance(data, dict):
        stop(f"{path} must be a JSON object: {what}")
    return data


def write_json(path: Path, data: dict):
    pl.write_atomic(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def personas_of(data: dict, where) -> list[dict]:
    """The personas a study or roster file holds, each an object with an id no other has."""
    personas = data.get("personas", [])
    if not isinstance(personas, list) or not all(isinstance(p, dict) and text(p.get("id")) for p in personas):
        stop(f'{where}: "personas" must be a list of objects, each with an "id"')
    twice = sorted(i for i, n in Counter(p["id"] for p in personas).items() if n > 1)
    if twice:
        stop(f"{where}: more than one persona has the id {', '.join(twice)}")
    return personas


def read_study(study_dir: Path) -> tuple[Path, dict, list[dict]]:
    path = Path(study_dir).resolve() / "study.json"
    if not path.is_file():
        stop(f"No study.json in {path.parent}. Pass the study directory, the one that holds study.json.")
    raw = read_json(path, "the study's configuration")
    return path, raw, personas_of(raw, "study.json")


def written(p: dict) -> bool:
    """Whether the lead has started on a persona: anything but a skeleton with no bio."""
    return str(p.get("name") or "").strip() not in ("", pl.SKELETON_NAME) or bool(p.get("bio"))


# ---------------------------------------------------------------- grid

def read_roster(raw: dict) -> dict:
    """study.json "roster", checked: {"roles": [{"role", "segment"}], "personalities", "stages", "caps"}."""
    roster = raw.get("roster")
    if not isinstance(roster, dict):
        stop(f'study.json has no "roster" to build a grid from. Add {ROSTER_SHAPE}: stages and caps are optional.')
    unknown = sorted(set(roster) - {"roles", "personalities", "stages", "caps"})
    if unknown:
        stop(f"study.json: roster has unknown keys: {', '.join(unknown)} (use {ROSTER_SHAPE})")

    def entries(name):
        values = roster.get(name)
        if not isinstance(values, list) or not values:
            stop(f"study.json: roster.{name} must be a list with at least one entry")
        return values

    def unique(name, values):
        twice = sorted(v for v, n in Counter(values).items() if n > 1)
        if twice:
            stop(f"study.json: roster.{name} lists {json.dumps(twice[0])} more than once")
        return values

    roles = []
    for r in entries("roles"):
        shown = json.dumps(r)
        if isinstance(r, str):
            r = {"role": r}
        if (not isinstance(r, dict) or set(r) - {"role", "segment"} or not text(r.get("role"))
                or ("segment" in r and not text(r["segment"]))):
            stop(f"study.json: roster.roles: {shown} must be the role line as a string, or an object "
                 '{"role": "<role line>", "segment": "<segment key>"}')
        role = r["role"].strip()
        roles.append({"role": role, "segment": r.get("segment", pl.slugify(role)).strip()})
    unique("roles", [r["role"] for r in roles])

    def strings(name):
        values = entries(name)
        if not all(text(v) for v in values):
            stop(f"study.json: roster.{name} must be a list of non-empty strings")
        return unique(name, [v.strip() for v in values])

    caps = roster.get("caps", {})
    if not isinstance(caps, dict) or set(caps) - {"personas", "runs"}:
        stop('study.json: roster.caps must be an object with any of "personas" and "runs"')
    for name, v in caps.items():
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            stop(f"study.json: roster.caps.{name} must be a whole number, 1 or more")
    return {"roles": roles, "personalities": strings("personalities"),
            "stages": strings("stages") if "stages" in roster else [], "caps": caps}


def select(seed, sizes: list[int], n: int, have: list[tuple[int, ...]] = ()) -> list[tuple[int, ...]]:
    """n cells of the grid whose axes have these sizes, in grid order, the same for the same seed:
    the cells to add to the ones in have.

    Cells are taken one at a time: the cell that brings the most values no cell has used yet,
    then whose values have been used least, then whose role and personality have met least, ties
    going to an order shuffled by the seed. While any axis has an unused value, a cell with an
    unused value on every such axis is free, so k cells use min(k, size) values of each axis.
    """
    cells = [c for c in itertools.product(*(range(k) for k in sizes)) if c not in set(have)]
    if n >= len(cells):
        return cells
    random.Random(f"{seed}:roster").shuffle(cells)
    used = [Counter(c[axis] for c in have) for axis in range(len(sizes))]
    met = Counter(c[:2] for c in have)
    chosen = []
    while len(chosen) < n:
        cell = min(cells, key=lambda c: (-sum(not used[axis][v] for axis, v in enumerate(c)),
                                         sum(used[axis][v] for axis, v in enumerate(c)), met[c[:2]]))
        cells.remove(cell)
        chosen.append(cell)
        met[cell[:2]] += 1
        for axis, v in enumerate(cell):
            used[axis][v] += 1
    return sorted(chosen)


def count_runs(raw: dict, n_personas: int) -> tuple[int, str]:
    """The runs a roster of n personas makes, and the sum as a sentence would give it."""
    if "models" not in raw:
        stop('study.json: roster.caps.runs counts personas x model entries x replicates, so set "models" first')
    entries = len(pl.model_entries({"models": raw["models"], "runner": raw.get("runner")}))
    reps = raw.get("replicates", 1)
    if not isinstance(reps, int) or isinstance(reps, bool) or reps < 1:
        stop('study.json: "replicates" must be a whole number, 1 or more')
    total = n_personas * entries * reps
    return total, (f"{plural(n_personas, 'persona')} x {plural(entries, 'model entry', 'model entries')} x "
                   f"{plural(reps, 'replicate')} = {plural(total, 'run')}")


def grid(args):
    path, raw, personas = read_study(args.study_dir)
    roster = read_roster(raw)
    roles, kinds, stages, caps = roster["roles"], roster["personalities"], roster["stages"], roster["caps"]
    kept = [p for p in personas if written(p)]
    if kept and not args.append:
        stop(f"study.json already has {plural(len(kept), 'written persona')} ({', '.join(p['id'] for p in kept)}), "
             "and grid never changes one. --append keeps them as they are and adds the skeletons after them.")

    def role_line(cell):
        return roles[cell[0]]["role"] + (f", {stages[cell[2]]}" if stages else "")

    sizes = [len(roles), len(kinds)] + ([len(stages)] if stages else [])
    cells = list(itertools.product(*(range(k) for k in sizes)))
    shape = (f"{plural(len(roles), 'role')} x {plural(len(kinds), 'personality', 'personalities')}"
             + (f" x {plural(len(stages), 'stage')}" if stages else "") + f" = {plural(len(cells), 'combination')}")
    # The combinations a written persona already is: its role line and personality are still the grid's.
    theirs = {(p.get("role"), p.get("personality")): p["id"] for p in kept}
    have = [c for c in cells if (role_line(c), kinds[c[1]]) in theirs]
    # What the new personas have to cover: the roles and personalities no written persona has, and
    # the stages too when the cap is at least the number of stages, which is when every stage is
    # promised. select() covers one unused value of every axis with each persona, so the largest
    # of those counts is the least that will do. A written persona the grid does not recognise
    # takes a place under the cap and covers nothing.
    lacking = [len(roles) - len({c[0] for c in have}), len(kinds) - len({c[1] for c in have})]
    every = "every role and every personality"
    if stages and caps.get("personas", 0) >= len(stages):
        lacking.append(len(stages) - len({c[2] for c in have}))
        every = "every role, every personality and every stage"
    need = max(lacking)
    n = len(cells) - len(have)
    if "personas" in caps:
        n = min(n, caps["personas"] - len(kept))
        if n < need:
            stop(f"roster.caps.personas is {caps['personas']}"
                 + (f", which leaves {max(n, 0)} beside the {plural(len(kept), 'written persona')}" if kept else "")
                 + f": too few for {every} to appear once. {shape}, and covering {every} takes at least "
                 f"{need}{' more' if kept else ''}. Set roster.caps.personas to {need + len(kept)} or more. "
                 "Nothing was written.")
    if n < 1:
        stop("Nothing to add: the written personas already " + ("cover every combination of the grid."
             if len(have) == len(cells) else f"fill roster.caps.personas ({caps['personas']})."))

    new = select(raw.get("seed", 1), sizes, n, have)  # the seed's default is load_study's
    top = max((int(m[1]) for p in kept if (m := re.fullmatch(r"P(\d+)", p["id"]))), default=0)
    skeletons = [{"id": f"P{top + i:02d}", "name": pl.SKELETON_NAME, "role": role_line(c), "personality": kinds[c[1]],
                  "segment": roles[c[0]]["segment"], "bio": []} for i, c in enumerate(new, start=1)]
    runs = None
    if "runs" in caps:
        total, runs = count_runs(raw, len(kept) + len(skeletons))
        if total > caps["runs"]:
            each = total // (len(kept) + len(skeletons))
            stop(f"{runs}, over roster.caps.runs of {caps['runs']}. {caps['runs']} runs is at most "
                 f"{plural(caps['runs'] // each, 'persona')} at {plural(each, 'run')} each: lower "
                 "roster.caps.personas to that, drop a model entry or a replicate, or raise roster.caps.runs. "
                 "Nothing was written.")

    raw["personas"] = [*kept, *skeletons]
    write_json(path, raw)
    capped = len(new) < len(cells) - len(have)
    print(f"Roster grid: {shape}; {len(new)} selected"
          + (f" (roster.caps.personas {caps['personas']}, seed {raw.get('seed', 1)})." if capped else "."))
    absent = [s for i, s in enumerate(stages) if i not in {c[2] for c in [*have, *new]}]
    matched = ", ".join(theirs[role_line(c), kinds[c[1]]] for c in have)
    print("Every role and every personality appears at least once"
          + (", and every stage" if stages and not absent else "")
          + (f", counting the written personas the grid already had ({matched})." if have else "."))
    if absent:
        print(f"Stages left out, because the cap is below the {plural(len(stages), 'stage')}: {', '.join(absent)}")
    for p in skeletons:
        print(f"  {p['id']}  {p['segment']}: {p['role']} | {p['personality']}")
    if kept:
        print(f"Kept as written: {', '.join(p['id'] for p in kept)}")
    if runs:
        print(f"Runs: {runs} (roster.caps.runs {caps['runs']})")
    print(f"Wrote {plural(len(skeletons), 'skeleton persona')} to {path}. Next: write each one's name and bio "
          f'(references/personas.md). init_study.py refuses a study while a persona is named "{pl.SKELETON_NAME}".')
    scaffolded(path.parent)


def scaffolded(sd: Path):
    if (sd / "runs.json").exists():
        print(f"This study is already scaffolded: runs.json follows the old roster until init_study.py {sd} --force "
              "scaffolds it again, which resets every run.")


# ---------------------------------------------------------------- roster files

def card(p: dict) -> dict:
    """A persona as a roster file holds it: the fields of CARD and nothing else, "variant_of" only
    for a variant. Two personas are the same when their cards are equal."""
    out = {"id": p["id"], "name": p.get("name"), "slug": pl.persona_slug(p) if text(p.get("name")) else p.get("slug"),
           "role": p.get("role"), "personality": p.get("personality"), "segment": p.get("segment", ""),
           "bio": p.get("bio", [])}
    return {**out, "variant_of": p["variant_of"]} if p.get("variant_of") is not None else out


def check_cards(cards: list[dict], where):
    """Stop unless every card is a whole persona, and every variant's parent is among them."""
    ids = {c["id"] for c in cards}
    for c in cards:
        who = f"{where}: persona {c['id']}"
        if pl.persona_id_problem(c["id"]):  # the rule study.json is held to when it is loaded
            stop(f"{who}: its id {pl.persona_id_problem(c['id'])}")
        if str(c["name"] or "").strip() in ("", pl.SKELETON_NAME):
            stop(f"{who} is still a skeleton, with no name written. A roster file holds whole personas.")
        for field in ("role", "personality"):
            if not text(c[field]):
                stop(f'{who} needs a "{field}"')
        if not isinstance(c["segment"], str) or not text(c["slug"]):
            stop(f'{who}: "segment" and "slug" must be strings')
        if not isinstance(c["bio"], list) or not all(isinstance(b, str) for b in c["bio"]):
            stop(f'{who}: "bio" must be a list of strings')
        if "variant_of" in c and c["variant_of"] not in ids:
            stop(f"{who} is a variant of {json.dumps(c['variant_of'])}, which is not there with it. A variant "
                 "travels with its parent.")


def differences(pairs: list[tuple[dict, dict]]) -> str:
    """For pairs of cards with one id and different content: "P01 (bio), P03 (name, role)"."""
    return ", ".join(f"{a['id']} ({', '.join(k for k in CARD if a.get(k) != b.get(k))})" for a, b in pairs)


def left_out(personas: list[dict]) -> str:
    extra = {p["id"]: sorted(set(p) - set(CARD)) for p in personas}
    return "; ".join(f"{pid}: {', '.join(keys)}" for pid, keys in extra.items() if keys)


def read_roster_file(path: Path) -> tuple[dict, list[dict]]:
    data = read_json(path, 'a roster file is {"personas": [...]}')
    cards = [card(p) for p in personas_of(data, path)]
    check_cards(cards, path)
    return data, cards


def export(args):
    path, _, personas = read_study(args.study_dir)
    dest = args.to.resolve()
    if path.parent / "panel" in dest.parents:
        stop(f"{dest} is under the study's panel/, where panellists read. Keep the roster file in the project, "
             "outside any study's panel/.")
    if not personas:
        stop("study.json has no personas to export.")
    cards = [card(p) for p in personas]
    check_cards(cards, "study.json")
    data, held = read_roster_file(dest) if dest.exists() else ({}, [])
    by_id = {c["id"]: c for c in held}
    changed = [(c, by_id[c["id"]]) for c in cards if c["id"] in by_id and by_id[c["id"]] != c]
    if changed and not args.update:
        stop(f"{dest} already holds {plural(len(changed), 'persona')} with the same id and different content: "
             f"{differences(changed)}. Nothing was written. An id means one person across studies: give the "
             "study's persona a new id, or pass --update to replace the roster file's with the study's.")
    new = [c for c in cards if c["id"] not in by_id]
    mine = {c["id"]: c for c in cards}
    merged = [mine.get(c["id"], c) for c in held] + new
    check_cards(merged, dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    write_json(dest, {**data, "personas": merged})
    print(f"Exported to {dest}: {len(new)} added, {len(changed)} updated, "
          f"{len(cards) - len(new) - len(changed)} unchanged. It holds {plural(len(merged), 'persona')}.")
    extra = left_out(personas)
    if extra:
        print(f"Fields a roster file does not hold were left behind: {extra}")


def import_(args):
    path, raw, personas = read_study(args.study_dir)
    source = args.source.resolve()
    if not source.is_file():
        stop(f"No roster file at {source}.")
    data, cards = read_roster_file(source)
    wanted = [i.strip() for i in args.ids.split(",") if i.strip()] if args.ids else [c["id"] for c in cards]
    unknown = [i for i in wanted if i not in {c["id"] for c in cards}]
    if unknown:
        stop(f"{source} has no persona {', '.join(unknown)}. It holds: {', '.join(c['id'] for c in cards)}")
    chosen = [c for c in cards if c["id"] in wanted]
    by_id = {p["id"]: card(p) for p in personas}
    clashes = [(c, by_id[c["id"]]) for c in chosen if c["id"] in by_id and by_id[c["id"]] != c]
    if clashes:
        stop(f"study.json already has {plural(len(clashes), 'persona')} with the same id and different content: "
             f"{differences(clashes)}. Nothing was written. Import never changes a persona in a study: take the "
             "study's one out or give it a new id, or leave that id out with --ids.")
    new = [c for c in chosen if c["id"] not in by_id]
    for c in new:
        if "variant_of" in c and c["variant_of"] not in {*by_id, *(x["id"] for x in new)}:
            stop(f"{c['id']} is a variant of {c['variant_of']}, which is neither in study.json nor among the "
                 f"personas being imported. Import {c['variant_of']} with it. Nothing was written.")
    if new:
        raw["personas"] = [*personas, *new]
        write_json(path, raw)
    there = ", ".join(c["id"] for c in chosen if c["id"] in by_id)
    print(f"Imported {plural(len(new), 'persona')} into {path}"
          + (f": {', '.join(c['id'] for c in new)}" if new else "")
          + (f". Already there, unchanged: {there}" if there else "") + ".")
    extra = left_out([p for p in data.get("personas", []) if p["id"] in wanted])
    if extra:
        print(f"Fields a study's persona does not take from a roster file were left behind: {extra}")
    if new:
        scaffolded(path.parent)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    sub = ap.add_subparsers(dest="command", required=True, metavar="{grid,export,import}")
    g = sub.add_parser("grid", help='write skeleton personas into study.json from its "roster"')
    g.add_argument("--append", action="store_true",
                   help="keep the personas already written and add the skeletons after them")
    g.set_defaults(run=grid)
    e = sub.add_parser("export", help="copy the study's personas into a roster file, merging by id")
    e.add_argument("--to", type=Path, required=True, metavar="FILE", help="the roster file, created if missing")
    e.add_argument("--update", action="store_true",
                   help="replace a persona the roster file holds with different content")
    e.set_defaults(run=export)
    i = sub.add_parser("import", help="copy personas from a roster file into study.json")
    i.add_argument("--from", dest="source", type=Path, required=True, metavar="FILE", help="the roster file")
    i.add_argument("--ids", help="only these persona ids, comma-separated (default: every persona in the file)")
    i.set_defaults(run=import_)
    args = ap.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
