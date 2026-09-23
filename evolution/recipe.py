"""Plan a recipe: which sources to plant on which cells, after how many previews.

The search walks the fixed stream. For each preview count it tries source sequences in
processing order, breadth first, until every wanted plant has been produced by a shuffle
whose pool belongs to the wanted cell's kind. Sources whose pools are identical, because
they share a cost and their cells' kinds reject the same plants, are one option. The
planting order is the reverse of the processing order.
"""

from collections import Counter

from .activation import Activation, Planting
from .level import format_cell
from .predict import CONDITIONS, area_around
from .shuffle import Mt19937, random_shuffle
from .tiles import NONE


def search_recipe(document, kinds, previews, level, wants, sources, activation=(2, 2), *, overrides=None,
                  preview_rank=1, min_previews=0, max_previews=99, max_sources=9, node_budget=20000, rank=1):
    """Fewest previews of one rank, then fewest sources, putting every wanted plant on its wanted cell.

    wants: list of (plant, cell). sources: {alias: cost} or {alias: (cost, [kinds])} when a
    source may only be planted on cells of those kinds. overrides: {cell: kind} for this
    activation. node_budget caps the shuffles tried per preview count.
    """
    if rank not in (1, 4):
        raise ValueError("Supported activation ranks are 1 and 4")
    area = area_around(activation, level.width, level.height)
    model = Activation(document, kinds, level, activation, overrides)
    kind_of = {cell: level.kind_at(cell, overrides) for cell in area}
    usable = [cell for cell in area if kind_of[cell] != NONE]
    wanted_cells = [cell for _, cell in wants]
    wanted_layers = [(cell, plant == "lilypad") for plant, cell in wants]
    if (len(set(wanted_layers)) != len(wants) or any(cell not in usable for cell in wanted_cells)
            or (rank == 1 and len(set(wanted_cells)) != len(wants))):
        raise ValueError("Wanted plants must have distinct cells/layers inside the usable activation area")
    max_sources = min(max_sources, len(usable))
    if not wants or max_sources < 0:
        raise ValueError("Request at least one wanted plant and a non-negative max_sources")
    if rank == 1 and not 1 <= len(wants) <= max_sources:
        raise ValueError("Require 1 <= wanted plants <= max_sources (%d usable cells)" % len(usable))
    if min_previews < 0 or max_previews < min_previews or node_budget < 1:
        raise ValueError("Require 0 <= min_previews <= max_previews and a positive node budget")
    if not sources and rank == 1:
        raise ValueError("List at least one source plant with its effective cost")
    capacity = Counter(kind_of[cell] for cell in usable)
    options = _options(document, kinds, level, sources, capacity)
    needed = Counter((plant, kind_of[cell]) for plant, cell in wants)
    for plant, kind in needed:
        if not (any(plant in option["pool"] for option in options if kind in option["kinds"])
                or (rank == 4 and plant in model.pool(kind))):
            raise ValueError("%s is not obtainable on a %s cell from any listed source in this level" % (plant, kind))
    result = {
        "level": level.describe(), "activation": {"column": activation[0], "row": activation[1]},
        "cell_kinds": {format_cell(cell): kind_of[cell] for cell in area},
        "wants": [{"plant": plant, "cell": format_cell(cell), "kind": kind_of[cell]} for plant, cell in wants],
        "options": [{"sources": o["sources"], "cost": o["cost"], "kinds": o["kinds"], "candidates": len(o["pool"])} for o in options],
        "rank": rank, "preview_rank": preview_rank, "min_previews": min_previews, "max_previews": max_previews,
        "max_sources": max_sources, "node_budget": node_budget, "budget_exhausted_counts": 0,
        "conditions": list(CONDITIONS), "match": None,
    }
    engine = Mt19937()
    for count in range(max_previews + 1):
        if count >= min_previews:
            if rank == 4:
                path, exhausted = _rank4_search(engine, model, options, max_sources, node_budget, wants, usable, kind_of)
            else:
                path, exhausted = _breadth_first(engine, options, needed, capacity, max_sources, node_budget, wants, usable, kind_of)
            result["budget_exhausted_counts"] += exhausted
            if path is not None:
                result["match"] = _recipe(count, preview_rank, engine.draws, path)
                return result
        if count < max_previews:
            previews.run(engine, preview_rank)
    return result


def _options(document, kinds, level, sources, capacity):
    """One option per distinct pool: sources of one cost on the kinds whose pools coincide."""
    by_pool = {}
    for alias, spec in sources.items():
        cost, allowed = (spec, None) if isinstance(spec, int) else (int(spec[0]), list(spec[1]))
        for kind in sorted(capacity):
            if allowed is not None and kind not in allowed:
                continue
            pool = tuple(level.pool(kind, cost, document, kinds))
            option = by_pool.setdefault((cost, pool), {"cost": cost, "pool": list(pool), "kinds": [],
                                                     "sources": [], "sources_by_kind": {}})
            if kind not in option["kinds"]:
                option["kinds"].append(kind)
            if alias not in option["sources"]:
                option["sources"].append(alias)
            option["sources_by_kind"].setdefault(kind, []).append(alias)
    return sorted(by_pool.values(), key=lambda o: (o["cost"], o["kinds"]))


def _rank4_search(engine, model, options, max_sources, node_budget, wants, usable, kind_of):
    """Search concrete source cells: their occupancy determines the later spawn pass."""
    wanted = set(wants)
    wanted_main = {cell: plant for plant, cell in wants if plant != "lilypad"}

    def accepted(rows):
        produced = {(row["result"], row["cell"]) for row in rows if row["placed"]}
        if wanted <= produced:
            return [dict(row, source_cost=row["cost"], kinds=[row["kind"]],
                         sources=row.get("sources", [row["source"]] if row["source"] else []),
                         wanted=(row["result"], row["cell"]) in wanted and row["placed"])
                    for row in rows]
        return None

    # If every wanted plant needs a transformation, retain the existing grouped
    # pool search. Concrete filler positions cannot make a spawn produce it.
    if all(plant not in model.pool(kind_of[cell]) for plant, cell in wants):
        def complete_transformations(path):
            originals = [Planting(step["sources"][0], step["source_cost"], step["cell"], step["kind"])
                         for step in reversed(path)]
            rows = model.run(originals, engine.clone(), 4)
            choices = {step["cell"]: step["sources"] for step in path}
            for row in rows:
                if row["action"] == "evolve":
                    row["sources"] = choices[row["cell"]]
            return accepted(rows)

        needed = Counter((plant, kind_of[cell]) for plant, cell in wants)
        capacity = Counter(kind_of[cell] for cell in usable)
        return _breadth_first(engine, options, needed, capacity, max_sources, node_budget,
                              wants, usable, kind_of, complete_transformations)

    def complete(state, plantings, prefix):
        return accepted(model.finish(plantings, prefix, state.clone(), 4))

    match = complete(engine, [], [])
    if match is not None:
        return match, False
    nodes = 1
    frontier = [(engine, [], [])]
    for _ in range(max_sources):
        following = []
        for state, plantings, prefix in frontier:
            occupied = {p.cell for p in plantings}
            for option in options:
                cells = [cell for cell in usable if cell not in occupied and kind_of[cell] in option["kinds"]]
                if not cells:
                    continue
                trial = state.clone()
                selection = model.select(option["pool"], trial, cells[0], kind_of[cells[0]],
                                         option["sources"][0], option["cost"])
                for cell in cells:
                    kind = kind_of[cell]
                    if cell in wanted_main and selection["result"] != wanted_main[cell]:
                        continue
                    if nodes >= node_budget:
                        return None, True
                    nodes += 1
                    aliases = option["sources_by_kind"][kind]
                    planting = Planting(aliases[0], option["cost"], cell, kind)
                    row = dict(selection, cell=cell, kind=kind, source=aliases[0], sources=aliases)
                    originals = plantings + [planting]
                    steps = prefix + [row]
                    match = complete(trial, originals, steps)
                    if match is not None:
                        return match, False
                    following.append((trial, originals, steps))
        frontier = following
    return None, False


def _breadth_first(engine, options, needed, capacity, max_sources, node_budget, wants, usable, kind_of, accept=None):
    frontier = [(engine.clone(), [], Counter(), Counter())]
    nodes = 0
    for _ in range(max_sources):
        following = []
        for state, path, matched, used in frontier:
            for index, option in enumerate(options):
                if not option["pool"]:
                    continue
                if used[index] + 1 > sum(capacity[k] for k in option["kinds"]):
                    continue
                if nodes >= node_budget:
                    return None, True
                nodes += 1
                trial = state.clone()
                start = trial.draws
                selected = random_shuffle(option["pool"], trial)[0]
                step = {"sources": option["sources"], "sources_by_kind": option["sources_by_kind"],
                        "source_cost": option["cost"], "kinds": option["kinds"],
                        "result": selected, "start": start, "end": trial.draws}
                counts = matched.copy()
                for kind in option["kinds"]:
                    if counts[(selected, kind)] < needed[(selected, kind)]:
                        counts[(selected, kind)] += 1
                        break
                if counts == needed:
                    assigned = _assign(path + [step], wants, usable, kind_of)
                    if assigned is not None:
                        result = accept(assigned) if accept else assigned
                        if result is not None:
                            return result, False
                following.append((trial, path + [step], counts, used + Counter({index: 1})))
        frontier = following
    return None, False


def _assign(path, wants, usable, kind_of):
    """Give every step a cell: wanted results on their wanted cells, the rest anywhere their kinds allow."""
    pending = {}
    for plant, cell in wants:
        pending.setdefault(plant, []).append(cell)
    steps = [dict(step) for step in path]
    taken = set()
    for step in steps:
        cells = [cell for cell in pending.get(step["result"], []) if kind_of[cell] in step["kinds"] and cell not in taken]
        if cells:
            step["cell"] = cells[0]
            step["wanted"] = True
            taken.add(cells[0])
    free = [cell for cell in usable if cell not in taken]
    fillers = [step for step in steps if "cell" not in step]
    match = _matching(fillers, free, kind_of)
    if match is None:
        return None
    for step, cell in zip(fillers, match):
        step["cell"] = cell
        step["wanted"] = False
    for step in steps:
        step["kind"] = kind_of[step["cell"]]
        step["sources"] = step.pop("sources_by_kind")[step["kind"]]
    return steps


def _matching(steps, cells, kind_of):
    """Bipartite matching of steps to cells whose kind the step allows; None if impossible."""
    owner = {}

    def place(index, seen):
        for cell in cells:
            if kind_of[cell] in steps[index]["kinds"] and cell not in seen:
                seen.add(cell)
                if cell not in owner or place(owner[cell], seen):
                    owner[cell] = index
                    return True
        return False

    for index in range(len(steps)):
        if not place(index, set()):
            return None
    result = [None] * len(steps)
    for cell, index in owner.items():
        result[index] = cell
    return result


def _recipe(preview_count, preview_rank, level_entry_offset, path):
    for position, step in enumerate(path, start=1):
        step["position"] = position
        step.setdefault("action", "evolve")
        step.setdefault("kind", step["kinds"][0] if len(step["kinds"]) == 1 else None)
        step["column"], step["row"] = step["cell"]
        step["cell"] = format_cell(step["cell"])
        step["source"] = step["sources"][0] if step["sources"] else None
    sources = [step for step in path if step["action"] == "evolve"]
    planting = [dict(step, step=index) for index, step in enumerate(reversed(sources), start=1)]
    return {"preview_count": preview_count, "preview_rank": preview_rank, "level_entry_offset": level_entry_offset,
            "source_count": len(sources), "processing_order": path, "planting_order": planting,
            "stream_end": path[-1]["end"] if path else level_entry_offset}
