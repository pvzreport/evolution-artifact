"""Command line: predict a stated scenario, plan a recipe, list a pool, build a version's plant data.

  python3 -m evolution predict --previews 1,4
  python3 -m evolution predict --level memory-lane-s33-6-hard --previews 1x6 --activate 2-2 \\
      --plant sunflower=50@1-3 --plant puffshroom=0@3-1:beach_shore
  python3 -m evolution predict --rank 4 --level egypt13 --activate 2-2
  python3 -m evolution plan --level memory-lane-s33-6-hard --want aeonium@1-1 --want aeonium@1-3 \\
      --source sunflower=50 --source puffshroom=0 --cell 3-1=beach_shore
  python3 -m evolution plan --rank 4 --level egypt13 --want kiwifruit@2-1 --want primalwallnut@3-3 --source wallnut=50
  python3 -m evolution pool --level pirate1 --kind pirate_plank --cost 0
  python3 -m evolution pool --game-version 4.2.2 --preview evolution --cost 47
"""

import argparse
import json
from pathlib import Path
import sys

from .build import build_plants
from .game import Game
from .level import format_cell, load_level, parse_cell
from .model import Planting, scenario
from .plants import PLANTS, VERSION, game_versions
from .previews import parse_sequence
from .search import search_recipe

PLATFORMS = ("iOS", "Android")


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


def parse_version(text):
    """A game version such as 4.2.4, which also names the plant file."""
    if not VERSION.fullmatch(text):
        raise argparse.ArgumentTypeError("A game version is numbers separated by dots, for example 4.2.4")
    return text


def format_sequence(sequence):
    """Preview ranks as RANKxCOUNT runs, for example 1x6,4; "none" for an empty sequence."""
    runs = []
    for rank in sequence:
        if runs and runs[-1][0] == rank:
            runs[-1][1] += 1
        else:
            runs.append([rank, 1])
    return ",".join("%dx%d" % (rank, count) if count > 1 else str(rank) for rank, count in runs) or "none"


def _count(number, noun):
    return "%d %s%s" % (number, noun, "" if number == 1 else "s")


def _print_previews(previews):
    for preview in previews:
        evolved, pads, spawns = [], [], []
        for row in preview["results"]:
            text = "%s %s" % (format_cell(row["cell"]), _outcome(row))
            if row["action"] == "evolve":
                evolved.append(text)
            elif row["beneath"]:
                pads.append(format_cell(row["cell"]))
            else:
                spawns.append(text)
        line = "Preview %d (rank %d): %s" % (preview["preview"], preview["rank"], ", ".join(evolved))
        if pads:
            line += "; pads beneath " + ", ".join(pads)
        if spawns:
            line += "; spawns " + ", ".join(spawns)
        for effect in preview["effects"]:
            line += "; %s at %s shuffles %s (%s)" % (
                effect["plant"], format_cell(effect["cell"]), _count(effect["objects"], "plant object"),
                _count(effect["end"] - effect["start"], "draw"))
        if preview["effects"]:
            line += " (selections end at %d; stream at %d after)" % (preview["selection_end"], preview["end"])
        else:
            line += " (stream at %d after)" % preview["end"]
        print(line)


def _note_preview_cost(game, preview_cost, listed_costs, previews):
    """Point out a listed cost of the preview source that differs from the cost the previews assume."""
    cost = game.previews.cost(preview_cost)
    other = sorted({c for c in listed_costs if c is not None and c != cost})
    if previews and other and preview_cost is None:
        print("note: the previews assume %s at effective cost %d, but --plant or --source lists it at %s; pass "
              "--preview-cost if the previews used that cost" % (game.previews.source, cost, ", ".join(str(c) for c in other)),
              file=sys.stderr)


def _outcome(row):
    """What a selection came to: the plant, or why nothing was placed."""
    outcome = row["result"] or "unchanged (empty pool)"
    if row["result"] and not row["placed"]:
        outcome += " (placement blocked)"
    return outcome


def _describe_row(row):
    """One row as 'CELL: SOURCE -> RESULT' with the placement outcome."""
    source = "/".join(row.get("sources") or ([row["source"]] if row["source"] else [])) or "spawn"
    return "%s: %s -> %s" % (format_cell(row["cell"]), source, _outcome(row))


def cmd_predict(args):
    game = Game(args.game_version)
    sequence = parse_sequence(args.previews)
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
    _note_preview_cost(game, args.preview_cost, [p.cost for p in plantings if p.source == game.previews.source],
                       bool(sequence))
    result = scenario(game, sequence, level, plantings, activation, dict(args.cell or []), args.offset, args.rank,
                      preview_cost=args.preview_cost)
    if args.json:
        print(json.dumps(result, indent=2))
        return
    if not sequence:
        print("No previews: the stream starts at offset 0.")
    else:
        print("Previews with %s at effective cost %d:" % (game.previews.source, result["preview_cost"]))
    _print_previews(result["previews"])
    if args.offset:
        print("Extra raw outputs consumed: %d" % args.offset)
    if level:
        print("Level %s (stage %s); rank-%d activation at %s; level entry at offset %d." % (
            level.name, level.stage, args.rank, format_cell(activation) if activation else "unspecified",
            result["level_entry_offset"]))
        for index, row in enumerate(result["results"], start=1):
            what = "%s, cost %d" % (row["source"], row["cost"]) if row["action"] == "evolve" else "rank-4 spawn"
            print("  processed %d: %s %s (%s, %d candidates) -> %s" % (
                index, format_cell(row["cell"]), what, row["kind"], row["candidates"], _outcome(row)))
        print("Selection stream ends at %d." % result["stream_end"])
    print("\nConditions:")
    for line in result["conditions"]:
        print("  " + line)


def cmd_plan(args):
    game = Game(args.game_version)
    level = load_level(args.level)
    sources = merge_sources(args.source)
    listed = sources.get(game.previews.source)
    _note_preview_cost(game, args.preview_cost, [listed[0] if isinstance(listed, tuple) else listed],
                       bool(parse_sequence(args.previews)) or args.max_previews > 0)
    result = search_recipe(game, level, args.want, sources, parse_cell(args.activate),
                           overrides=dict(args.cell or []), rank=args.rank, prefix=parse_sequence(args.previews),
                           preview_rank=args.preview_rank, min_previews=args.min_previews,
                           max_previews=args.max_previews, offset=args.offset, max_sources=args.max_sources,
                           budget=args.budget, preview_cost=args.preview_cost)
    if args.json:
        print(json.dumps(result, indent=2))
        return
    options = ["%s on %s: %d candidates" % ("/".join(o["sources"]), "/".join(o["kinds"]), o["candidates"])
               for o in result["options"]]
    print("; ".join(["Level %s (stage %s)" % (level.name, level.stage)] + options))
    print("Cells: " + ", ".join("%s %s" % (cell, kind) for cell, kind in result["cell_kinds"].items()))
    if result["unusable_sources"]:
        print("Not plantable in this level or on any cell of this area, so not planned: " + ", ".join(result["unusable_sources"]))
    if result["budget_exhausted"]:
        print("Shuffle budget %d exhausted at preview count(s) %s; deeper mixes there were not searched."
              % (result["budget"], ", ".join(str(c) for c in result["budget_exhausted"])))
    match = result["match"]
    prefix = " after the previews %s" % format_sequence(result["prefix"]) if result["prefix"] else ""
    if match is None:
        print("No recipe within %d..%d rank-%d previews%s and up to %d sources."
              % (result["min_previews"], result["max_previews"], args.preview_rank, prefix, result["max_sources"]))
    else:
        print("\n1. Fully quit and relaunch the game.")
        if match["preview_sequence"]:
            print("2. Run these previews, each one complete, with %s at effective cost %d: %s."
                  % (game.previews.source, result["preview_cost"], format_sequence(match["preview_sequence"])))
        else:
            print("2. Run no previews.")
        if result["extra_offset"]:
            print("   Then let the engine consume the %d further outputs stated with --offset." % result["extra_offset"])
        print("3. Enter the level directly" + (" and plant, in this order:" if match["planting_order"] else "; leave the activation area empty."))
        for step in match["planting_order"]:
            print("   %d. %s at %s" % (step["step"], "/".join(step["sources"]), format_cell(step["cell"])))
        print("4. Start the waves, then activate rank-%d Evolution once at %s." % (args.rank, args.activate))
        print("\nPredicted selections, in processing order:")
        for row in match["processing_order"]:
            print("   " + _describe_row(row) + ("  <- wanted" if row["wanted"] else ""))
        print("\nStream: level entry at offset %d; selections end at %d." % (match["level_entry_offset"], match["stream_end"]))
    print("\nConditions:")
    for line in result["conditions"]:
        print("  " + line)


def cmd_pool(args):
    game = Game(args.game_version)
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
    output = PLANTS / (args.game_version + ".json")
    output.write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n")
    print("Wrote %s: game %s (%s), %d plant types, %d configured registry names, %d black-listed plants." % (
        output, args.game_version, args.platform, len(document["plants"]),
        len(document["registry_order"]["configured_types"] or ()), len(document["artifact"]["plant_black_list"])))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m evolution", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    data = argparse.ArgumentParser(add_help=False)
    data.add_argument("--game-version", choices=game_versions(),
                      help="Game version whose plant data to use (default: the newest)")

    predict = commands.add_parser("predict", parents=[data], help="Replay a stated scenario and print what the game shows")
    predict.add_argument("--previews", default="", help="Preview ranks in order, for example 1x6 or 1,4 (default: none)")
    predict.add_argument("--preview-cost", type=int, metavar="COST",
                         help="Effective cost of the previews' Sunflowers (default: the declared cost)")
    predict.add_argument("--offset", type=int, default=0, help="Extra raw engine outputs consumed before the level")
    predict.add_argument("--level", help="Level id from data/levels, or a path to a description")
    predict.add_argument("--rank", type=int, choices=(1, 4), default=1, help="Artifact rank of the activation (default: 1)")
    predict.add_argument("--activate", help="Activation cell COLUMN-ROW")
    predict.add_argument("--plant", type=parse_planting, action="append", metavar="ALIAS[=COST]@CELL[:KIND]",
                         help="A planted source, in planting order; repeatable")
    predict.add_argument("--source", type=parse_cost, action="append", metavar="ALIAS=COST",
                         help="Default effective cost for an alias used in --plant")
    predict.add_argument("--cell", type=parse_override, action="append", metavar="CELL=KIND",
                         help="Kind of a cell for this activation; repeatable")
    predict.add_argument("--json", action="store_true")
    predict.set_defaults(run=cmd_predict)

    plan = commands.add_parser("plan", parents=[data], help="Find previews and a planting order that put wanted plants on wanted cells")
    plan.add_argument("--level", required=True, help="Level id from data/levels, or a path to a description")
    plan.add_argument("--rank", type=int, choices=(1, 4), default=1, help="Artifact rank of the activation (default: 1)")
    plan.add_argument("--want", type=parse_want, action="append", required=True, metavar="PLANT@CELL")
    plan.add_argument("--source", type=parse_source, action="append", metavar="ALIAS=COST[:KIND,KIND]",
                      help="An available source and its effective cost; optional at rank 4")
    plan.add_argument("--activate", default="2-2", help="Activation cell COLUMN-ROW (default 2-2)")
    plan.add_argument("--cell", type=parse_override, action="append", metavar="CELL=KIND",
                      help="Kind of a cell for this activation; repeatable")
    plan.add_argument("--previews", default="", help="Previews run first, before the counted ones, for example 1 (default: none)")
    plan.add_argument("--preview-rank", type=int, choices=(1, 4), default=1, help="Rank of the counted previews (default 1)")
    plan.add_argument("--preview-cost", type=int, metavar="COST",
                      help="Effective cost of the previews' Sunflowers (default: the declared cost)")
    plan.add_argument("--min-previews", type=int, default=0, help="Fewest counted previews to try")
    plan.add_argument("--max-previews", type=int, default=99, help="Most counted previews to try")
    plan.add_argument("--offset", type=int, default=0, help="Extra raw engine outputs consumed between the previews and the level")
    plan.add_argument("--max-sources", type=int, default=9)
    plan.add_argument("--budget", type=int, default=30000, help="Shuffles tried per preview count (default 30000)")
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(run=cmd_plan)

    pool = commands.add_parser("pool", parents=[data], help="Print an ordered candidate pool")
    pool.add_argument("--level", help="Level id or path")
    pool.add_argument("--kind", default="ground")
    pool.add_argument("--cost", type=int, help="Effective source cost: default 0 for a level pool, the declared cost for the "
                                                "preview evolution pool; the spawn pool has none")
    pool.add_argument("--preview", choices=("evolution", "spawn"), help="A preview pool instead of a level pool")
    pool.set_defaults(run=cmd_pool)

    build = commands.add_parser("build-plants", help="Build one game version's plant data from decoded game files into data/plants")
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
