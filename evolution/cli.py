"""Command line: predict a stated scenario, plan a recipe, list a pool, rebuild the plant file.

  python3 -m evolution predict --previews 1,4
  python3 -m evolution predict --level memory-lane-s33-6-hard --previews 1x6 --activate 2-2 \\
      --plant sunflower=50@1-3 --plant puffshroom=0@3-1:beach_shore
  python3 -m evolution plan --level memory-lane-s33-6-hard --want aeonium@1-1 --want aeonium@1-3 \\
      --source sunflower=50 --source puffshroom=0 --cell 3-1=beach_shore
  python3 -m evolution pool --level pirate1 --kind pirate_plank --cost 0
"""

import argparse
import json
from pathlib import Path
import sys

from .build import build_plants
from .level import available_levels, format_cell, load_level, parse_cell
from .plants import DATA, load_plants
from .predict import Planting, scenario
from .previews import Previews, parse_sequence
from .recipe import search_recipe
from .tiles import NONE, tile_kinds


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
    """ALIAS=COST[:KIND,KIND] ; the kinds restrict where the planner may put this source."""
    alias, _, rest = text.partition("=")
    cost, _, kinds = rest.partition(":")
    if not alias or not cost.isdigit():
        raise argparse.ArgumentTypeError("Use ALIAS=EFFECTIVE_COST[:KIND,KIND], for example sunflower=50 or puffshroom=0:ground")
    return alias, (int(cost), kinds.split(",")) if kinds else int(cost)


def parse_override(text):
    cell, _, kind = text.partition("=")
    if not cell or not kind:
        raise argparse.ArgumentTypeError("Use COLUMN-ROW=KIND, for example 3-1=beach_pad")
    return parse_cell(cell), kind


def _context(args):
    document = load_plants(args.plants)
    kinds = tile_kinds(document=document)
    return document, kinds, Previews(document, kinds)


def _print_previews(rows):
    for preview in rows:
        shown = []
        for step in preview["results"]:
            if step["step"] == "evolution":
                shown.append("%s %s" % (format_cell(step["cell"]), step["result"]))
        singles = [s["result"] for s in preview["results"] if s["step"] == "single"]
        spawns = [s["result"] for s in preview["results"] if s["step"] == "spawn"]
        line = "Preview %d (rank %d): %s" % (preview["preview"], preview["rank"], "; ".join(shown))
        if singles:
            line += "; water cells: %s x%d" % (singles[0], len(singles))
        if spawns:
            line += "; spawns in order: " + ", ".join(spawns)
        end = preview["results"][-1]["end"] if preview["results"] else None
        print(line + " (stream at %s after)" % end)


def cmd_predict(args):
    document, kinds, previews = _context(args)
    sequence = parse_sequence(args.previews)
    level = load_level(args.level) if args.level else None
    activation = parse_cell(args.activate) if args.activate else None
    if level and not args.plant and args.rank == 1:
        raise SystemExit("With --level, list the planted sources with --plant")
    if args.plant and not level:
        raise SystemExit("--plant needs --level")
    plantings = []
    for entry in args.plant or []:
        cost = entry["cost"]
        if cost is None:
            spec = dict(args.source or []).get(entry["source"])
            cost = spec if isinstance(spec, int) or spec is None else spec[0]
        if cost is None:
            raise SystemExit("No effective cost for %s: write ALIAS=COST@CELL or add --source ALIAS=COST" % entry["source"])
        plantings.append(Planting(entry["source"], cost, entry["cell"], entry["kind"]))
    result = scenario(document, kinds, previews, sequence, level, plantings, activation,
                      dict(args.cell or []), args.offset, args.rank)
    if args.json:
        print(json.dumps(result, indent=2, default=list))
        return
    if not sequence:
        print("No previews: the stream starts at offset 0.")
    _print_previews(result["previews"])
    if args.offset:
        print("Extra raw outputs consumed: %d" % args.offset)
    if level:
        print("Level %s (stage %s); rank-%d activation at %s; level entry at offset %d." % (
            level.name, level.stage, args.rank, format_cell(activation) if activation else "unspecified", result["level_entry_offset"]))
        for index, row in enumerate(result["results"], start=1):
            source = "%s, cost %d" % (row["source"], row["cost"]) if row["action"] == "evolve" else "rank-4 spawn"
            outcome = row["result"] or "unchanged (empty pool)"
            if row["result"] and not row["placed"]:
                outcome += " (placement blocked)"
            print("  processed %d: %s %s (%s, %d candidates) -> %s" % (
                index, format_cell(row["cell"]), source, row["kind"], row["candidates"], outcome))
        print("Selection stream ends at %d." % result["stream_end"])
    print("\nConditions:")
    for line in result["conditions"]:
        print("  " + line)


def cmd_plan(args):
    document, kinds, previews = _context(args)
    level = load_level(args.level)
    result = search_recipe(document, kinds, previews, level, args.want, dict(args.source or []), parse_cell(args.activate),
                           overrides=dict(args.cell or []), preview_rank=args.preview_rank,
                           min_previews=args.min_previews, max_previews=args.max_previews,
                           max_sources=args.max_sources, node_budget=args.node_budget, rank=args.rank)
    if args.json:
        print(json.dumps(result, indent=2))
        return
    options = [
        "%s at cost %d on %s: %d candidates" % ("/".join(o["sources"]), o["cost"], "/".join(o["kinds"]), o["candidates"])
        for o in result["options"]]
    print("; ".join(["Level %s (stage %s)" % (level.name, level.stage)] + options))
    if result["budget_exhausted_counts"]:
        print("Node budget %d exhausted for %d preview count(s); deeper mixes there were not searched."
              % (result["node_budget"], result["budget_exhausted_counts"]))
    match = result["match"]
    if match is None:
        print("No recipe within %d..%d previews (first rank 1, later rank %d) and up to %d sources."
              % (result["min_previews"], result["max_previews"], args.preview_rank, result["max_sources"]))
    else:
        print("\n1. Fully quit and relaunch the game.")
        if match["preview_count"] > 1 and match["preview_rank"] != 1:
            print("2. Complete one rank-1 preview, then %d rank-%d preview(s), each one full run." % (
                match["preview_count"] - 1, match["preview_rank"]))
        else:
            print("2. Complete %d rank-1 preview(s), each one full run of the preview." % match["preview_count"])
        print("3. Enter the level directly" + (" and plant, in this order:" if match["planting_order"] else "; leave the activation area empty."))
        for step in match["planting_order"]:
            print("   %d. %s at %s" % (step["step"], "/".join(step["sources"]), step["cell"]))
        print("4. Start the waves, then activate rank-%d Evolution once at %s." % (args.rank, args.activate))
        print("\nPredicted selections (transformations first, then rank-4 placements):" if args.rank == 4
              else "\nPredicted transformations:")
        for step in match["processing_order"]:
            print("   %s: %s -> %s%s%s" % (step["cell"], "/".join(step["sources"]) or "spawn",
                  step["result"] or "unchanged (empty pool)",
                  " (placement blocked)" if step.get("placed") is False and step["result"] else "",
                  "  <- wanted" if step["wanted"] else ""))
        print("\nStream: level entry at raw offset %d, selections end at %d." % (match["level_entry_offset"], match["stream_end"]))
    print("\nConditions:")
    for line in result["conditions"]:
        print("  " + line)


def cmd_pool(args):
    document, kinds, previews = _context(args)
    if args.preview:
        pool = previews.pools[args.preview]
        print("Preview %s pool: %d candidates" % (args.preview, len(pool)))
    else:
        level = load_level(args.level)
        pool = level.pool(args.kind, args.cost, document, kinds)
        print("%s, %s cell, source cost %d: %d candidates" % (level.name, args.kind, args.cost, len(pool)))
    for index, alias in enumerate(pool):
        print("  %3d  %s" % (index, alias))


def cmd_build_plants(args):
    document = build_plants(args.planttypes, args.propertysheets, args.artifact)
    Path(args.output).write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n")
    print("Wrote %s: %d plant types, %d configured registry names, %d black-listed plants." % (
        args.output, len(document["plants"]), len(document["registry_order"]["configured_types"] or ()),
        len(document["artifact"]["plant_black_list"])))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m evolution", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plants", type=Path, default=DATA / "plants.json", help="Plant file (default: data/plants.json)")
    commands = parser.add_subparsers(dest="command", required=True)

    predict = commands.add_parser("predict", help="Replay a stated scenario and print what the game shows")
    predict.add_argument("--previews", default="", help="Preview ranks in order, for example 1x6 or 1,4 (default: none)")
    predict.add_argument("--offset", type=int, default=0, help="Extra raw engine outputs consumed before the level")
    predict.add_argument("--rank", type=int, choices=(1, 4), default=1, help="Artifact rank for the level activation (default: 1)")
    predict.add_argument("--level", help="Level id from data/levels, or a path to a description")
    predict.add_argument("--activate", help="Activation cell COLUMN-ROW")
    predict.add_argument("--plant", type=parse_planting, action="append", metavar="ALIAS[=COST]@CELL[:KIND]",
                         help="A planted source, in planting order; repeatable")
    predict.add_argument("--source", type=parse_source, action="append", metavar="ALIAS=COST",
                         help="Default effective cost for an alias used in --plant")
    predict.add_argument("--cell", type=parse_override, action="append", metavar="CELL=KIND",
                         help="Kind of a cell for this activation; repeatable")
    predict.add_argument("--json", action="store_true")
    predict.set_defaults(run=cmd_predict)

    plan = commands.add_parser("plan", help="Find previews and a planting order that put wanted plants on wanted cells")
    plan.add_argument("--level", required=True)
    plan.add_argument("--rank", type=int, choices=(1, 4), default=1, help="Artifact rank for the level activation (default: 1)")
    plan.add_argument("--want", type=parse_want, action="append", required=True, metavar="PLANT@CELL")
    plan.add_argument("--source", type=parse_source, action="append", metavar="ALIAS=COST",
                      help="Available source and effective cost; optional for an empty rank-4 area")
    plan.add_argument("--activate", default="2-2", help="Activation cell COLUMN-ROW (default 2-2)")
    plan.add_argument("--cell", type=parse_override, action="append", metavar="CELL=KIND")
    plan.add_argument("--preview-rank", type=int, choices=(1, 4), default=1,
                      help="Rank after the mandatory first rank-1 preview (default 1); counts include that first preview")
    plan.add_argument("--min-previews", type=int, default=0)
    plan.add_argument("--max-previews", type=int, default=99)
    plan.add_argument("--max-sources", type=int, default=9)
    plan.add_argument("--node-budget", type=int, default=20000, help="Search nodes tried per preview count")
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(run=cmd_plan)

    pool = commands.add_parser("pool", help="Print an ordered candidate pool")
    pool.add_argument("--level", help="Level id or path")
    pool.add_argument("--kind", default="ground")
    pool.add_argument("--cost", type=int, default=0, help="Effective source cost")
    pool.add_argument("--preview", choices=("evolution", "spawn"), help="A preview pool instead of a level pool")
    pool.set_defaults(run=cmd_pool)

    build = commands.add_parser("build-plants", help="Rebuild data/plants.json from decoded game files")
    build.add_argument("planttypes", type=Path)
    build.add_argument("propertysheets", type=Path)
    build.add_argument("artifact", type=Path)
    build.add_argument("--output", type=Path, default=DATA / "plants.json")
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
