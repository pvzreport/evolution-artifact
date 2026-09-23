"""Plan a recipe: which sources to plant on which cells, after which previews.

An activation's outcome depends on two independent things. Transformation results depend
only on the sequence of pools shuffled, in processing order, from the level's starting
offset, never on cells. At rank 4 the spawn pass then depends only on which cells are
occupied: it shuffles once per free cell in area order and adds a zero-draw Lily Pad on
each occupied shore or water cell.

The search walks sequences of pool options breadth first, fewest sources first; sources
with the same pool are one option, whatever their aliases or costs. Whenever a sequence's
results cover every wanted plant that no spawn could provide, the area is walked in its
order deciding each cell occupied or free while carrying the spawn offset, so a free
wanted cell whose draw misses ends that branch at once. At a leaf, a matching assigns the
steps to the occupied cells by kind, reserving a wanted cell for the step that produced
its plant, and the rows are accepted only when every wanted plant is placed. A found
recipe is then replayed through `activate` before it is returned. Preview counts are
tried in increasing order, so the first recipe found has the fewest previews, then the
fewest sources. The budget counts shuffles.

A source whose pool is empty transforms into nothing, but at rank 4 it still occupies its
cell and so moves the spawns; all such sources form one option, planned only after every
real source of a sequence, which keeps each sequence unique.
"""

from collections import Counter

from .level import LILYPAD, format_cell
from .model import CONDITIONS, PAD, RANKS, Board, Pools, activate, check_board, place, select, selection_row
from .stream import shared
from .tiles import NONE


class _Exhausted(Exception):
    pass


def parse_spec(spec):
    """A source's cost and allowed kinds: `cost` or `(cost, [kinds])`."""
    return (int(spec), None) if isinstance(spec, int) else (int(spec[0]), list(spec[1]))


def search_recipe(document, kinds, previews, level, wants, sources, activation=(2, 2), *, overrides=None, rank=1,
                  prefix=(), preview_rank=1, min_previews=0, max_previews=99, offset=0, max_sources=9,
                  budget=30000, stream=None):
    """Fewest previews of `preview_rank` after the fixed `prefix`, then fewest sources, placing every want.

    wants: list of (plant, cell). sources: {alias: cost} or {alias: (cost, [kinds])} when a source
    may only be planted on cells of those kinds. overrides: {cell: kind} for this activation.
    offset: extra raw outputs consumed between the previews and the level. budget: shuffles
    tried per preview count.
    """
    if rank not in RANKS:
        raise ValueError("Supported activation ranks are 1 and 4")
    if min_previews < 0 or max_previews < min_previews or budget < 1 or max_sources < 0 or offset < 0:
        raise ValueError("Require 0 <= min_previews <= max_previews, max_sources >= 0, offset >= 0 and a positive budget")
    prefix = list(prefix)
    for preview in prefix + [preview_rank]:
        if preview not in previews.ranks():
            raise ValueError("No measured structure for a rank-%s preview; known ranks: %s"
                             % (preview, ", ".join(str(r) for r in previews.ranks())))
    board = Board(level, overrides, activation)
    check_board(board, kinds)
    pools = Pools(document, kinds, level, previews.spawn_max_cost)
    kind_of = {cell: board.kind_at(cell) for cell in board.area}
    usable = [cell for cell in board.area if kind_of[cell] != NONE]
    wants = [(plant, tuple(cell)) for plant, cell in wants]
    _check_wants(wants, usable, pools, rank)
    options, unusable = _options(pools, sources, kind_of, usable, rank)
    spawnable = _spawnable(wants, pools, kind_of, rank)
    for plant, cell in wants:
        kind = kind_of[cell]
        if spawnable[(plant, cell)]:
            continue
        if not any(plant in option["pool"] for option in options if kind in option["kinds"]):
            raise ValueError("%s is not obtainable on %s (%s) from any listed source in this level"
                             % (plant, format_cell(cell), kind))
        if rank == 4 and pools.spawn(kind, occupied=True) and not kinds[PAD].admits(plant):
            raise ValueError("%s can never be placed on %s at rank 4: the Lily Pad added beneath its source rejects it"
                             % (plant, format_cell(cell)))
    required = Counter(plant for (plant, cell), ok in spawnable.items() if not ok)
    max_sources = min(max_sources, len(usable))
    if sum(required.values()) > max_sources:
        raise ValueError("%d wanted plants need a transformation, more than max_sources allows (%d)"
                         % (sum(required.values()), max_sources))
    stream = stream or shared()
    result = {
        "level": level.describe(), "activation": {"column": activation[0], "row": activation[1]}, "rank": rank,
        "cell_kinds": {format_cell(cell): kind_of[cell] for cell in board.area},
        "wants": [{"plant": plant, "cell": cell, "kind": kind_of[cell]} for plant, cell in wants],
        "options": [{"sources": sorted({alias for pairs in o["aliases"].values() for alias, _ in pairs}),
                     "kinds": o["kinds"], "candidates": len(o["pool"])} for o in options],
        "unusable_sources": unusable, "prefix": prefix, "preview_rank": preview_rank, "min_previews": min_previews,
        "max_previews": max_previews, "extra_offset": offset, "max_sources": max_sources, "budget": budget,
        "budget_exhausted": [],
        "conditions": list(CONDITIONS), "match": None,
    }
    searcher = _Search(stream, pools, board, kind_of, usable, options, wants, required, spawnable, rank, budget)
    _, position = previews.advance(stream, 0, prefix)
    for count in range(max_previews + 1):
        if count >= min_previews:
            entry = position + offset
            rows, exhausted = searcher.run(entry, max_sources)
            if exhausted:
                result["budget_exhausted"].append(count)
            if rows is not None:
                _verify(board, pools, rank, stream, entry, rows)
                result["match"] = _recipe(count, prefix + [preview_rank] * count, entry, rows)
                return result
        if count < max_previews:
            _, position = previews.run(stream, position, preview_rank)
    return result


def _check_wants(wants, usable, pools, rank):
    if not wants:
        raise ValueError("Request at least one wanted plant")
    layers = [(cell, plant == LILYPAD) for plant, cell in wants]
    if len(set(layers)) != len(wants) or (rank == 1 and len({cell for _, cell in wants}) != len(wants)):
        raise ValueError("Wanted plants must be on distinct cells, except a Lily Pad under an ordinary plant at rank 4")
    for plant, cell in wants:
        if plant not in pools.costs:
            raise ValueError("Unknown wanted plant: %r" % plant)
        if cell not in usable:
            raise ValueError("Cell %s is outside the usable activation area" % format_cell(cell))


def _spawnable(wants, pools, kind_of, rank):
    """Which wants a spawn on a free cell could provide; a plant wanted together with a Lily Pad on its cell cannot be,
    because that cell must be occupied for the pad to be added beneath a source."""
    with_pad = {cell for plant, cell in wants if plant == LILYPAD}
    return {(plant, cell): rank == 4 and plant in pools.spawn(kind_of[cell]) and (plant == LILYPAD or cell not in with_pad)
            for plant, cell in wants}


def _options(pools, sources, kind_of, usable, rank):
    """One option per distinct pool: the sources that produce it, per kind, with their costs.

    Also returns the sources that cannot be planted in this level or on any cell of this area, which are not planned.
    """
    present = sorted({kind_of[cell] for cell in usable})
    by_pool, unusable = {}, []
    for alias, spec in sources.items():
        cost, allowed = parse_spec(spec)
        if alias not in pools.costs:
            raise ValueError("Unknown source plant: %r" % alias)
        for kind in allowed or ():
            if not isinstance(kind, str) or kind not in pools.kinds:
                raise ValueError("Unknown cell kind %r for source %s; known: %s" % (kind, alias, ", ".join(sorted(pools.kinds))))
        if alias == LILYPAD:
            raise ValueError("A Lily Pad is a cell kind here, not a source; describe it with beach_pad")
        kinds = [kind for kind in present if (allowed is None or kind in allowed) and pools.plantable(alias, kind)]
        if not kinds:
            unusable.append(alias)
            continue
        for kind in kinds:
            pool = pools.transformation(kind, cost)
            if not pool and rank == 1:
                continue
            option = by_pool.setdefault(pool, {"pool": pool, "kinds": [], "aliases": {}})
            if kind not in option["kinds"]:
                option["kinds"].append(kind)
            option["aliases"].setdefault(kind, []).append((alias, cost))
    for option in by_pool.values():
        option["kinds"].sort()
    return sorted(by_pool.values(), key=lambda o: (-len(o["pool"]), o["kinds"])), unusable


class _Search:
    def __init__(self, stream, pools, board, kind_of, usable, options, wants, required, spawnable, rank, budget):
        self.stream, self.pools, self.area, self.kind_of, self.usable = stream, pools, board.area, kind_of, usable
        self.options, self.wants, self.required, self.spawnable, self.rank = options, wants, required, spawnable, rank
        self.budget = budget
        self.reserved = {cell: plant for plant, cell in wants if rank == 1 or plant != LILYPAD}
        self.wants_at = {}
        for plant, cell in wants:
            self.wants_at.setdefault(cell, []).append(plant)
        self.capacity = Counter(kind_of[cell] for cell in usable)
        self.usable_from = [sum(1 for cell in board.area[index:] if kind_of[cell] != NONE)
                            for index in range(len(board.area) + 1)]
        self.shuffles = 0
        self.spawns = {}

    def run(self, entry, max_sources):
        """The accepted rows at this entry offset, or None; the flag says the budget ran out."""
        self.shuffles, self.spawns = 0, {}
        try:
            return self._run(entry, max_sources), False
        except _Exhausted:
            return None, True

    def _run(self, entry, max_sources):
        if not self.required:
            rows = self._evaluate([], entry)
            if rows is not None:
                return rows
        frontier = [(entry, [], Counter())]
        for _ in range(max_sources):
            following = []
            for position, steps, used in frontier:
                blocked = bool(steps) and not steps[-1]["candidates"]
                for index, option in enumerate(self.options):
                    if blocked and option["pool"]:
                        continue
                    if used[index] + 1 > sum(self.capacity[kind] for kind in option["kinds"]):
                        continue
                    self._spend(1)
                    shuffled, end = self.stream.shuffle(option["pool"], position)
                    step = {"option": index, "candidates": len(option["pool"]), "shuffled": shuffled,
                            "result": shuffled[0] if shuffled else None, "start": position, "end": end}
                    path = steps + [step]
                    if self._covers(path):
                        rows = self._evaluate(path, end)
                        if rows is not None:
                            return rows
                    following.append((end, path, used + Counter({index: 1})))
            frontier = following
        return None

    def _spend(self, shuffles):
        if self.shuffles + shuffles > self.budget:
            raise _Exhausted()
        self.shuffles += shuffles

    def _covers(self, path):
        counts = Counter(step["result"] for step in path)
        return all(counts[plant] >= needed for plant, needed in self.required.items())

    def _evaluate(self, path, position):
        """Rows of an accepted recipe for this pool sequence, or None."""
        if self.rank == 1:
            cells = self._match(path, self.usable, spare=len(self.usable) - len(path))
            return self._accept(path, cells, []) if cells is not None else None
        return self._walk(path, 0, [], [], position)

    def _walk(self, path, index, occupied, spawned, offset):
        """Decide the cells from `index` on, occupied or free, and return the first accepted leaf."""
        slots = len(path) - len(occupied)
        if slots > self.usable_from[index]:
            return None
        if index == len(self.area):
            cells = self._match(path, occupied, spare=0)
            return self._accept(path, cells, spawned) if cells is not None else None
        cell = self.area[index]
        if self.kind_of[cell] == NONE:
            return self._walk(path, index + 1, occupied, spawned, offset)
        wants = self.wants_at.get(cell, ())
        if all(self.spawnable[(plant, cell)] for plant in wants):
            row = self._spawn(cell, offset, occupied=False)
            if row is None or all(plant == row["result"] for plant in wants):
                rows = self._walk(path, index + 1, occupied, spawned + [row] if row else spawned,
                                  row["end"] if row else offset)
                if rows is not None:
                    return rows
        if slots and self._may_occupy(cell, path):
            row = self._spawn(cell, offset, occupied=True)
            return self._walk(path, index + 1, occupied + [cell], spawned + [row] if row else spawned,
                              row["end"] if row else offset)
        return None

    def _may_occupy(self, cell, path):
        """A wanted cell may hold a source only if some step made its plant, or the pad beneath it is its want."""
        for plant in self.wants_at.get(cell, ()):
            if cell in self.reserved and self.reserved[cell] == plant:
                if not any(step["result"] == plant for step in path):
                    return False
            elif not self.pools.spawn(self.kind_of[cell], occupied=True):
                return False
        return True

    def _spawn(self, cell, offset, occupied):
        """The spawn row of one cell at an offset, or None when its pool is empty; memoised per search."""
        key = (cell, offset, occupied)
        if key not in self.spawns:
            pool = self.pools.spawn(self.kind_of[cell], occupied)
            if pool:
                self._spend(1)
                row, _ = select(self.stream, offset, pool, "spawn", cell, self.kind_of[cell])
                row["sources"] = []
                self.spawns[key] = row
            else:
                self.spawns[key] = None
        return self.spawns[key]

    def _match(self, path, cells, spare):
        """Assign each step a distinct cell its option's kinds allow, reserving wanted cells; None if impossible.

        `spare` unused slots take any cell that is not reserved, so every cell is matched.
        """
        reserved, kind_of = self.reserved, self.kind_of
        allowed = [self.options[step["option"]]["kinds"] for step in path] + [None] * spare
        results = [step["result"] for step in path] + [None] * spare
        owner = {}

        def place_slot(index, seen):
            for cell in cells:
                if cell in seen:
                    continue
                if cell in reserved and results[index] != reserved[cell]:
                    continue
                if allowed[index] is not None and kind_of[cell] not in allowed[index]:
                    continue
                seen.add(cell)
                if cell not in owner or place_slot(owner[cell], seen):
                    owner[cell] = index
                    return True
            return False

        for index in range(len(allowed)):
            if not place_slot(index, set()):
                return None
        assigned = [None] * len(allowed)
        for cell, index in owner.items():
            assigned[index] = cell
        return assigned[:len(path)]

    def _accept(self, path, cells, spawned):
        """The placed rows of this assignment if every want is met, else None."""
        rows = []
        for step, cell in zip(path, cells):
            kind = self.kind_of[cell]
            pairs = self.options[step["option"]]["aliases"][kind]
            source, cost = pairs[0]
            row = selection_row("evolve", cell, kind, source, cost, step["candidates"], step["shuffled"],
                                step["start"], step["end"])
            row["sources"] = [alias for alias, _ in pairs]
            rows.append(row)
        rows.extend(dict(row) for row in spawned)
        place(rows, self.kind_of, self.pools.kinds)
        placed = {(row["result"], row["cell"]) for row in rows if row["placed"]}
        if not all(want in placed for want in self.wants):
            return None
        wanted = set(self.wants)
        for row in rows:
            row["wanted"] = bool(row["placed"]) and (row["result"], row["cell"]) in wanted
        return rows


def _verify(board, pools, rank, stream, entry, rows):
    """Replay the recipe through the activation model; a difference would be a defect of the search."""
    from .model import Planting
    plantings = [Planting(row["source"], row["cost"], row["cell"]) for row in reversed(rows) if row["action"] == "evolve"]
    replay, _ = activate(board, pools, plantings, rank, stream, entry)
    keys = ("action", "cell", "kind", "result", "candidates", "start", "end", "placed")
    if [tuple(row[k] for k in keys) for row in replay] != [tuple(row[k] for k in keys) for row in rows]:
        raise RuntimeError("The search accepted a recipe that does not replay")


def _recipe(preview_count, sequence, entry, rows):
    for position, row in enumerate(rows, start=1):
        row["position"] = position
    sources = [row for row in rows if row["action"] == "evolve"]
    planting = [dict(row, step=index) for index, row in enumerate(reversed(sources), start=1)]
    return {"preview_count": preview_count, "preview_sequence": sequence, "level_entry_offset": entry,
            "source_count": len(sources), "processing_order": rows, "planting_order": planting,
            "stream_end": rows[-1]["end"] if rows else entry}
