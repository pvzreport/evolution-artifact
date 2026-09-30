"""Command line: predict a stated scenario, plan a recipe, list a pool, build the plant data.

  python3 -m evolution predict --route E1,E4
  python3 -m evolution predict --route D1x2,E1,E3
  python3 -m evolution predict --level memory-lane-s33-6-hard --route E1x6 --activate 2-2 \\
      --plant sunflower=50@1-3 --plant puffshroom=0@3-1:beach_shore
  python3 -m evolution predict --rank 4 --level egypt13 --activate 2-2
  python3 -m evolution plan --level memory-lane-s33-6-hard --want aeonium@1-1 --want aeonium@1-3 \\
      --source sunflower=50 --source puffshroom=0 --max-sources 9 --cell 3-1=beach_shore
  python3 -m evolution plan --rank 4 --level egypt13 --want kiwifruit@2-1 --want primalwallnut@3-3 \\
      --source wallnut=50 --max-sources 9
  python3 -m evolution plan --level egypt1 --want kernelpult@1-1 --source wallnut=50 --max-sources 9 --done E1x2 \\
      --style shorter
  python3 -m evolution plan --level egypt1 --want kernelpult@1-1 --source wallnut=50 --max-sources 9 --allow E1,E4
  python3 -m evolution pool --level pirate1 --kind pirate_plank --cost 0
  python3 -m evolution pool --preview evolution --cost 47
"""

import argparse
import json
from pathlib import Path
import re
import sys

from .build import build_plants
from .game import Game
from .level import format_cell, load_level, parse_cell
from .model import LEVEL_RANKS, Planting
from .plants import PLANTS
from .route import Steps, format_route, parse_route, scenario
from .search import STYLES, search_recipe

PLATFORMS = ("iOS", "Android")
VERSION = re.compile(r"\d+(\.\d+)+")


def parse_planting(text):
    """ALIAS[=COST]@COLUMN-ROW[:KIND], for example puffshroom=0@3-1:beach_shore."""
    head, _, rest = text.partition("@")
    if not head or not rest:
        raise argparse.ArgumentTypeError("Use ALIAS[=COST]@COLUMN-ROW[:KIND], for example puffshroom=0@3-1:beach_shore")
    alias, _, cost = head.partition("=")
    cell, _, kind = rest.partition(":")
    if cost and not cost.isdigit():
        raise argparse.ArgumentTypeError("The cost must be a non-negative integer")
    return {"source": alias, "cost": int(cost) if cost else None, "cell": parse_cell(cell), "kind": kind or None}


def parse_want(text):
    plant, _, cell = text.partition("@")
    if not plant or not cell:
        raise argparse.ArgumentTypeError("Use PLANT@COLUMN-ROW, for example aeonium@1-1")
    return plant, parse_cell(cell)


def parse_source(text):
    """ALIAS=COST[:KIND,KIND]; the kinds restrict where the planner may put this source."""
    alias, _, rest = text.partition("=")
    cost, _, kinds = rest.partition(":")
    if not alias or not cost.isdigit():
        raise argparse.ArgumentTypeError("Use ALIAS=EFFECTIVE_COST[:KIND,KIND], for example sunflower=50 or puffshroom=0:ground")
    return alias, (int(cost), kinds.split(",")) if kinds else int(cost)


def parse_cost(text):
    """ALIAS=COST, a default effective cost for --plant entries that give none."""
    alias, _, cost = text.partition("=")
    if not alias or not cost.isdigit():
        raise argparse.ArgumentTypeError("Use ALIAS=EFFECTIVE_COST, for example sunflower=50")
    return alias, int(cost)


def merge_sources(pairs):
    """Sources from repeated --source flags; the same alias may be repeated to allow more kinds, not to change its cost."""
    sources = {}
    for alias, spec in pairs or []:
        cost, kinds = (spec, None) if isinstance(spec, int) else spec
        if alias in sources:
            known_cost, known_kinds = (sources[alias], None) if isinstance(sources[alias], int) else sources[alias]
            if known_cost != cost:
                raise ValueError("Source %s is listed with two costs, %d and %d" % (alias, known_cost, cost))
            kinds = None if kinds is None or known_kinds is None else known_kinds + [k for k in kinds if k not in known_kinds]
        sources[alias] = cost if kinds is None else (cost, kinds)
    return sources


def parse_override(text):
    cell, _, kind = text.partition("=")
    if not cell or not kind:
        raise argparse.ArgumentTypeError("Use COLUMN-ROW=KIND, for example 3-1=beach_pad")
    return parse_cell(cell), kind


def parse_allowed(text):
    """STEP,STEP: the steps a planned route may use, for example E1,E4 or E1,E3,E4,D1,D4."""
    allowed = [name for name in text.replace(" ", "").split(",") if name]
    if not allowed:
        raise argparse.ArgumentTypeError("List at least one step, for example E1,E4")
    return allowed


def parse_version(text):
    """A game version such as 4.2.4."""
    if not VERSION.fullmatch(text):
        raise argparse.ArgumentTypeError("A game version is numbers separated by dots, for example 4.2.4")
    return text


def _count(number, noun):
    return "%d %s%s" % (number, noun, "" if number == 1 else "s")


def _evolution_line(entry):
    evolved, pads, spawns = [], [], []
    for row in entry["results"]:
        text = "%s %s" % (format_cell(row["cell"]), _outcome(row))
        if row["action"] == "evolve":
            evolved.append(text)
        elif row["beneath"]:
            pads.append(format_cell(row["cell"]))
        else:
            spawns.append(text)
    line = ", ".join(evolved)
    if pads:
        line += "; pads beneath " + ", ".join(pads)
    if spawns:
        line += "; spawns " + ", ".join(spawns)
    line += "".join(_effect(effect) for effect in entry["effects"])
    if entry["effects"]:
        return line + " (selections end at %d; stream at %d after)" % (entry["selection_end"], entry["end"])
    return line + " (stream at %d after)" % entry["end"]


def _devolution_line(entry):
    shuffles = entry["shuffles"]
    sizes = list(dict.fromkeys(str(shuffle["objects"]) for shuffle in shuffles))
    return "%s of %s objects, %s (stream at %d after)" % (
        _count(len(shuffles), "shuffle"), " and ".join(sizes), _count(entry["end"] - entry["start"], "draw"), entry["end"])


def _effect(effect):
    return "; %s at %s shuffles %s (%s)" % (effect["plant"], format_cell(effect["cell"]),
                                           _count(effect["objects"], "plant object"),
                                           _count(effect["end"] - effect["start"], "draw"))


_STEP_LINES = {"evolution": _evolution_line, "devolution": _devolution_line}


def _print_steps(entries):
    for entry in entries:
        print("Step %d, %s: %s" % (entry["step"], entry["name"], _STEP_LINES[entry["artifact"]](entry)))


def _note_preview_cost(game, preview_cost, listed_costs, evolution):
    """Point out a listed cost of the preview source that differs from the cost the Evolution previews, when there
    are any, assume."""
    cost = game.previews.cost(preview_cost)
    other = sorted({c for c in listed_costs if c is not None and c != cost})
    if evolution and other and preview_cost is None:
        print("note: the previews assume %s at effective cost %d, but --plant or --source lists it at %s; pass "
              "--preview-cost if the previews used that cost" % (game.previews.source, cost, ", ".join(str(c) for c in other)),
              file=sys.stderr)


def _outcome(row):
    """What a selection came to: the plant, or why nothing was placed."""
    outcome = row["result"] or "unchanged (empty pool)"
    if row["result"] and not row["placed"]:
        outcome += " (placement blocked)"
    return outcome


def _describe_entry(effects, start):
    """What entering the level draws: its gravestone-bag shuffles, and the offset the activation starts from."""
    if not effects:
        return "Entering the level draws nothing; the activation starts at offset %d." % start
    bags = ("a gravestone bag of %s" % _count(effects[0]["objects"], "object") if len(effects) == 1
            else "gravestone bags of %s objects" % ", ".join(str(e["objects"]) for e in effects))
    return "Entering the level shuffles %s (%s); the activation starts at offset %d." % (
        bags, _count(start - effects[0]["start"], "draw"), start)


def _describe_row(row):
    """One row as 'CELL: SOURCE -> RESULT' with the placement outcome."""
    source = "/".join(row.get("sources") or ([row["source"]] if row["source"] else [])) or "spawn"
    return "%s: %s -> %s" % (format_cell(row["cell"]), source, _outcome(row))


def cmd_predict(args):
    game = Game()
    level = load_level(args.level) if args.level else None
    activation = parse_cell(args.activate) if args.activate else None
    if not level and (args.plant or args.cell or activation or args.rank != 1):
        raise ValueError("--plant, --cell, --activate and --rank need --level")
    if level and args.rank == 4 and not activation:
        raise ValueError("A rank-4 activation needs --activate")
    if level and args.rank == 1 and not args.plant:
        raise ValueError("With --level at rank 1, list the planted sources with --plant")
    plantings = []
    for entry in args.plant or []:
        cost = entry["cost"]
        if cost is None:
            cost = dict(args.source or []).get(entry["source"])
        if cost is None:
            raise ValueError("No effective cost for %s: write ALIAS=COST@CELL or add --source ALIAS=COST" % entry["source"])
        plantings.append(Planting(entry["source"], cost, entry["cell"], entry["kind"]))
    result = scenario(game, parse_route(args.route), level, plantings, activation, dict(args.cell or []), args.offset,
                      args.rank, preview_cost=args.preview_cost)
    evolution = any(entry["artifact"] == "evolution" for entry in result["steps"])
    _note_preview_cost(game, args.preview_cost, [p.cost for p in plantings if p.source == game.previews.source], evolution)
    if args.json:
        print(json.dumps(result, indent=2))
        return
    if not result["steps"]:
        print("No steps: the stream starts at offset 0.")
    elif evolution:
        print("Route after a full restart, with %s at effective cost %d:" % (game.previews.source, result["preview_cost"]))
    else:
        print("Route after a full restart:")
    _print_steps(result["steps"])
    if args.offset:
        print("Extra raw outputs consumed: %d" % args.offset)
    if level:
        print("Level %s (stage %s); rank-%d activation at %s; level entry at offset %d." % (
            level.name, level.stage, args.rank, format_cell(activation) if activation else "unspecified",
            result["level_entry_offset"]))
        print("  " + _describe_entry(result["entry_effects"], result["activation_offset"]))
        for index, row in enumerate(result["results"], start=1):
            what = "%s, cost %d" % (row["source"], row["cost"]) if row["action"] == "evolve" else "rank-4 spawn"
            print("  processed %d: %s %s (%s, %d candidates) -> %s" % (
                index, format_cell(row["cell"]), what, row["cell_kind"], row["candidates"], _outcome(row)))
        print("Selection stream ends at %d." % result["stream_end"])
    print("\nConditions:")
    for line in result["conditions"]:
        print("  " + line)


def _switches(style):
    """What a route style allows, for example "at most 1 switch"."""
    limit = STYLES[style]
    return "any number of switches" if limit is None else "at most %d switch%s" % (limit, "" if limit == 1 else "es")


def _run_steps(game, match, cost):
    """Step 2 of a recipe: the planned steps, the Evolution previews' cost, and how each artifact's previews start."""
    done = len(match["route"]) - len(match["planned"])
    entries = match["steps"][done:]
    artifacts = [entry["artifact"] for entry in match["steps"][max(done - 1, 0):]]  # from the last done step on
    switches = any(before != after for before, after in zip(artifacts, artifacts[1:]))
    source = ""
    if any(entry["artifact"] == "evolution" for entry in entries):
        whose = "the Evolution previews' " if "devolution" in artifacts else ""
        source = ", with %s%s at effective cost %d" % (whose, game.previews.source, cost)
    if switches or (not done and "devolution" in artifacts):
        start = "; tapping an artifact plays its rank-1 preview, which counts as the next one"
    elif not done:
        start = "; the first is the rank-1 preview that plays when the artifact is tapped"
    else:
        start = ""
    print("2. Run these %ssteps, each one complete%s: %s%s." % ("further " if done else "", source,
                                                                 format_route(match["planned"]), start))


def cmd_plan(args):
    game = Game()
    level = load_level(args.level)
    sources = merge_sources(args.source)
    if sources and args.max_sources is None:
        raise ValueError("Give with --max-sources the most sources a recipe may plant")
    done = parse_route(args.done)
    listed = sources.get(game.previews.source)
    steps = Steps(game, args.preview_cost)
    involved = done + ((args.allow or steps.names()) if args.max_length > 0 else [])
    _note_preview_cost(game, args.preview_cost, [listed[0] if isinstance(listed, tuple) else listed],
                       any(steps.get(name).artifact == "evolution" for name in involved))
    result = search_recipe(game, level, args.want, sources, parse_cell(args.activate),
                           overrides=dict(args.cell or []), rank=args.rank, done=done, style=args.style,
                           allowed=args.allow, max_length=args.max_length, offset=args.offset,
                           max_sources=args.max_sources or 0, preview_cost=args.preview_cost)
    if args.json:
        print(json.dumps(result, indent=2))
        return
    options = ["%s on %s: %d candidates" % ("/".join(o["sources"]), "/".join(o["kinds"]), o["candidates"])
               for o in result["options"]]
    print("; ".join(["Level %s (stage %s)" % (level.name, level.stage)] + options))
    print("Cells: " + ", ".join("%s %s" % (cell, kind) for cell, kind in result["cell_kinds"].items()))
    if result["unusable_sources"]:
        print("Not plantable in this level or on any cell of this area, so not planned: " + ", ".join(result["unusable_sources"]))
    after = " after the done steps %s" % format_route(result["done"]) if done else ""
    print("Routes of the %s style (%s) with the steps %s, up to length %d%s: %s searched." % (
        args.style, _switches(args.style), ", ".join(result["allowed"]), result["max_length"], after,
        _count(result["entry_positions_searched"], "distinct entry position")))
    for capped in result["state_cap_reached"]:
        print("The state cap (%d) stopped the search at level entry %d, after %s, among recipes of %s: a recipe there "
              "with that many sources or more may have been missed." % (
                  result["max_states"], capped["level_entry_offset"],
                  "the route " + format_route(capped["route"]) if capped["route"] else "no steps",
                  _count(capped["sources"], "source")))
    match = result["match"]
    if match is None:
        print("No recipe within length %d of the %s style%s and up to %s%s." % (
            result["max_length"], args.style, after, _count(result["max_sources"], "source"),
            ", apart from where the state cap stopped the search" if result["state_cap_reached"] else ""))
    else:
        if done:
            print("\n1. Continue from the steps already run since a full relaunch: %s." % format_route(result["done"]))
        else:
            print("\n1. Fully quit and relaunch the game.")
        if match["planned"]:
            _run_steps(game, match, result["preview_cost"])
        else:
            print("2. Run no %ssteps." % ("further " if done else ""))
        if result["extra_offset"]:
            print("   Then let the engine consume the %d further outputs stated with --offset." % result["extra_offset"])
        if match["planting_order"]:
            print("3. Enter the level directly and plant %s, in this order:" % _count(match["source_count"], "source"))
        else:
            print("3. Enter the level directly; leave the activation area empty.")
        for step in match["planting_order"]:
            print("   %d. %s at %s" % (step["step"], "/".join(step["sources"]), format_cell(step["cell"])))
        print("4. Start the waves, then activate rank-%d Evolution once at %s." % (args.rank, args.activate))
        print("\nPredicted selections, in processing order:")
        for row in match["processing_order"]:
            print("   " + _describe_row(row) + ("  <- wanted" if row["wanted"] else ""))
        print("\nStream: level entry at offset %d; the activation starts at %d; selections end at %d." % (
            match["level_entry_offset"], match["activation_offset"], match["stream_end"]))
    print("\nConditions:")
    for line in result["conditions"]:
        print("  " + line)


def cmd_pool(args):
    game = Game()
    if args.cost is not None and args.cost < 0:
        raise ValueError("The source cost cannot be negative")
    if args.preview == "spawn":
        pool = game.previews.spawn_pool()
        print("Preview spawn pool, game %s: %d candidates" % (game.version, len(pool)))
    elif args.preview == "evolution":
        cost = game.previews.cost(args.cost)
        pool = game.previews.evolution_pool(cost)
        print("Preview evolution pool at source cost %d, game %s: %d candidates" % (cost, game.version, len(pool)))
    else:
        level = load_level(args.level)
        cost = args.cost if args.cost is not None else 0
        pool = level.pool(args.kind, cost, game.plants, game.kinds)
        print("%s, %s cell, source cost %d, game %s: %d candidates" % (level.name, args.kind, cost, game.version, len(pool)))
    for index, alias in enumerate(pool):
        print("  %3d  %s" % (index, alias))


def cmd_build_plants(args):
    document = build_plants(args.planttypes, args.propertysheets, args.artifact, args.game_version, args.platform)
    PLANTS.write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n")
    print("Wrote %s: game %s (%s), %d plant types, %d configured registry names, %d black-listed plants." % (
        PLANTS, args.game_version, args.platform, len(document["plants"]),
        len(document["registry_order"]["configured_types"] or ()), len(document["artifact"]["plant_black_list"])))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m evolution", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    predict = commands.add_parser("predict", help="Replay a stated scenario and print what the game shows")
    predict.add_argument("--route", default="",
                         help="Steps after a full restart, in order: the previews E1, E3, E4, D1 and D4, each optionally "
                              "repeated as xCOUNT, for example E1x6, E1,E4 or D1x2,E1,E3 (default: none)")
    predict.add_argument("--preview-cost", type=int, metavar="COST",
                         help="Effective cost of the previews' Sunflowers (default: the declared cost)")
    predict.add_argument("--offset", type=int, default=0, help="Extra raw engine outputs consumed between the route and the level")
    predict.add_argument("--level", help="Level id from data/levels, or a path to a description")
    predict.add_argument("--rank", type=int, choices=LEVEL_RANKS, default=1, help="Artifact rank of the activation (default: 1)")
    predict.add_argument("--activate", help="Activation cell COLUMN-ROW")
    predict.add_argument("--plant", type=parse_planting, action="append", metavar="ALIAS[=COST]@CELL[:KIND]",
                         help="A planted source, in planting order; repeatable")
    predict.add_argument("--source", type=parse_cost, action="append", metavar="ALIAS=COST",
                         help="Default effective cost for an alias used in --plant")
    predict.add_argument("--cell", type=parse_override, action="append", metavar="CELL=KIND",
                         help="Kind of a cell for this activation; repeatable")
    predict.add_argument("--json", action="store_true")
    predict.set_defaults(run=cmd_predict)

    plan = commands.add_parser("plan", help="Find a route and a planting order that put wanted plants on wanted cells")
    plan.add_argument("--level", required=True, help="Level id from data/levels, or a path to a description")
    plan.add_argument("--rank", type=int, choices=LEVEL_RANKS, default=1, help="Artifact rank of the activation (default: 1)")
    plan.add_argument("--want", type=parse_want, action="append", required=True, metavar="PLANT@CELL")
    plan.add_argument("--source", type=parse_source, action="append", metavar="ALIAS=COST[:KIND,KIND]",
                      help="An available source and its effective cost; optional at rank 4")
    plan.add_argument("--activate", default="2-2", help="Activation cell COLUMN-ROW (default 2-2)")
    plan.add_argument("--cell", type=parse_override, action="append", metavar="CELL=KIND",
                      help="Kind of a cell for this activation; repeatable")
    plan.add_argument("--done", default="", metavar="ROUTE",
                      help="Steps already run since a full restart, in order, for example E1x3,E4 or D1,E1 (default: none)")
    plan.add_argument("--style", choices=tuple(STYLES), default="shorter",
                      help="Switches between steps the route may make after the done steps: simple at most one, "
                           "shorter at most three, shortest any (default shorter)")
    plan.add_argument("--allow", type=parse_allowed, metavar="STEPS",
                      help="The steps the planned route may use, for example E1,E4 (default: every known preview, "
                           "E1,E3,E4,D1,D4)")
    plan.add_argument("--max-length", type=int, default=100,
                      help="Most length to plan after the done steps, a preview counting 1 (default 100)")
    plan.add_argument("--preview-cost", type=int, metavar="COST",
                      help="Effective cost of the previews' Sunflowers (default: the declared cost)")
    plan.add_argument("--offset", type=int, default=0, help="Extra raw engine outputs consumed between the route and the level")
    plan.add_argument("--max-sources", type=int, metavar="N",
                      help="The most sources a recipe may plant; required with --source")
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(run=cmd_plan)

    pool = commands.add_parser("pool", help="Print an ordered candidate pool")
    pool.add_argument("--level", help="Level id or path")
    pool.add_argument("--kind", default="ground")
    pool.add_argument("--cost", type=int, help="Effective source cost: default 0 for a level pool, the declared cost for the "
                                                "preview evolution pool; the spawn pool has none")
    pool.add_argument("--preview", choices=("evolution", "spawn"), help="A preview pool instead of a level pool")
    pool.set_defaults(run=cmd_pool)

    build = commands.add_parser("build-plants", help="Build the plant data from decoded game files, replacing data/plants.json")
    build.add_argument("planttypes", type=Path)
    build.add_argument("propertysheets", type=Path)
    build.add_argument("artifact", type=Path)
    build.add_argument("--game-version", type=parse_version, required=True, help="The version the files come from, for example 4.2.4")
    build.add_argument("--platform", choices=PLATFORMS, required=True, help="The platform of the package the files come from")
    build.set_defaults(run=cmd_build_plants)

    args = parser.parse_args(argv)
    if getattr(args, "run", None) is cmd_pool and not args.preview and not args.level:
        parser.error("pool needs --level or --preview")
    try:
        args.run(args)
    except ValueError as error:
        print("error: %s" % error, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
