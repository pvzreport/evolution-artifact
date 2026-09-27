"""Plan a recipe: which previews to run after a full restart, then which sources to plant on which cells.

An activation's outcome depends on two independent things. Transformation results depend
only on the sequence of pools shuffled, in processing order, from the offset the activation
starts at, after the level's entry shuffles, never on cells. At rank 4 the spawn pass then
depends only on which cells are occupied: it shuffles once per free cell in area order and
adds a zero-draw Lily Pad on each occupied shore or water cell.

At one activation start the search walks sequences of pool options breadth first, fewest
sources first; sources with the same pool are one option, whatever their aliases or costs.
Whenever a sequence's results cover every wanted plant that no spawn could provide, the area
is walked in its order deciding each cell occupied or free while carrying the spawn offset,
so a free wanted cell whose draw misses ends that branch at once. At a leaf, a matching
assigns the steps to the occupied cells by kind, reserving a wanted cell for the step that
produced its plant, and the steps are accepted only when every wanted plant is placed.

Whether a sequence or any sequence grown from it is accepted depends only on its state: the
position its last shuffle ended at and, for each group of options that may stand on the same
kinds of cell, how many sources the group holds and how many of each wanted plant they
produced, counted up to the number wanted. The walk keeps the first sequence to reach each
state and drops the others, so it returns the sequence that walking every sequence returns:
the fewest sources, then the first in option order. A sequence grows only while its sources
fit the cells, counted per cell kind. Shuffles are memoised by position and pool, spawns by
pool and offset. The states stored at one start are capped as a memory guard, and a start
at which the cap stopped the search is reported.

A route is the sequence of previews run after a full restart; the first is the rank-1
preview that plays when the artifact is tapped. Routes continuing the previews already run
are tried in increasing length, and routes that reach the same stream position share one
search there. The shortest route of the chosen style that has a recipe wins; among routes of
that length, the one with the fewest sources, then the fewest rank switches, then the first
in rank order (rank 1 before rank 4). The recipe is replayed through `activate`, which gives
the rows it returns.

A source whose pool is empty transforms into nothing and draws nothing, but at rank 4 it
still occupies its cell and so moves the spawns; all such sources form one option.
"""

from collections import Counter
from itertools import combinations

from .level import LILYPAD, format_cell
from .model import PAD, RANKS, Board, Planting, activate, check_board, conditions, enter_level, place, selection_row
from .stream import shared
from .tiles import NONE

STYLES = {"simple": 1, "shorter": 3, "shortest": None}  # the most rank switches a route of each style may make
MAX_STATES = 1000000


def parse_spec(spec):
    """A source's cost and allowed kinds: `cost` or `(cost, [kinds])`."""
    return (int(spec), None) if isinstance(spec, int) else (int(spec[0]), list(spec[1]))


def search_recipe(game, level, wants, sources, activation=(2, 2), *, overrides=None, rank=1, done=(), style="simple",
                  max_previews=100, offset=0, max_sources=9, max_states=MAX_STATES, stream=None, preview_cost=None):
    """The shortest preview route of `style` continuing the `done` previews, with the recipe that places every want.

    game: the Game whose plant data the recipe is for. wants: list of (plant, cell). sources:
    {alias: cost} or {alias: (cost, [kinds])} when a source may only be planted on cells of those
    kinds. overrides: {cell: kind} for this activation. done: the ranks of the previews already run
    since a full restart, in order. style: "simple" (at most one rank switch), "shorter" (at most
    three) or "shortest" (any number); a switch counts whenever a planned preview's rank differs
    from the preview before it, the last done preview included. max_previews: the most previews
    planned after the done ones. offset: extra raw outputs consumed between the previews and the
    level, before the level's own entry shuffles. max_states: the most search states stored at one
    entry position. preview_cost: the previews' effective source cost; the default is the source's
    declared cost.
    """
    if rank not in RANKS:
        raise ValueError("Supported activation ranks are 1 and 4")
    if style not in STYLES:
        raise ValueError("Route styles are %s" % ", ".join(STYLES))
    if max_previews < 0 or max_sources < 0 or offset < 0 or max_states < 1:
        raise ValueError("Require max_previews >= 0, max_sources >= 0, offset >= 0 and max_states >= 1")
    previews = game.previews
    cost = previews.cost(preview_cost)
    done = list(done)
    if done[:1] not in ([], [1]):
        raise ValueError("The first preview after a restart is rank 1, the one that plays when the artifact is tapped")
    for preview in sorted(set(done) | ({1, 4} if max_previews else set())):
        previews.plantings(preview, cost)
    board = Board(level, overrides, activation)
    check_board(board, game.kinds)
    pools = game.pools(level)
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
        if rank == 4 and pools.spawn(kind, occupied=True) and not game.kinds[PAD].admits(plant):
            raise ValueError("%s can never be placed on %s at rank 4: the Lily Pad added beneath its source rejects it"
                             % (plant, format_cell(cell)))
    required = Counter(plant for (plant, cell), ok in spawnable.items() if not ok)
    max_sources = min(max_sources, len(usable))
    if sum(required.values()) > max_sources:
        raise ValueError("%d wanted plants need a transformation, more than max_sources allows (%d)"
                         % (sum(required.values()), max_sources))
    stream = stream or shared()
    result = {
        "game": game.describe(), "level": level.describe(),
        "activation": {"column": activation[0], "row": activation[1]}, "rank": rank,
        "cell_kinds": {format_cell(cell): kind_of[cell] for cell in board.area},
        "wants": [{"plant": plant, "cell": cell, "kind": kind_of[cell]} for plant, cell in wants],
        "options": [{"sources": sorted({alias for pairs in o["aliases"].values() for alias, _ in pairs}),
                     "kinds": o["kinds"], "candidates": len(o["pool"])} for o in options],
        "unusable_sources": unusable, "done": done, "style": style, "max_previews": max_previews,
        "extra_offset": offset, "max_sources": max_sources, "max_states": max_states, "preview_cost": cost,
        "entry_positions_searched": 0, "state_cap_reached": [], "conditions": None, "match": None,
    }
    search = _Search(stream, pools, board, kind_of, usable, options, wants, required, spawnable, rank, max_states)
    best = None
    for entries in _routes(previews, stream, cost, done, STYLES[style], max_previews):
        for position, planned, switches in entries:
            if best is not None and best[0] == 0:
                break  # no route of this length can use fewer sources
            entry = position + offset
            entered, start = enter_level(level, stream, entry)
            rows, capped = search.run(start, max_sources if best is None else best[0] - 1)
            result["entry_positions_searched"] += 1
            if capped is not None:
                result["state_cap_reached"].append({"preview_sequence": done + planned, "level_entry_offset": entry,
                                                    "activation_offset": start, "sources": capped})
            if rows is not None:
                best = (sum(1 for row in rows if row["action"] == "evolve"), planned, switches, entry, entered, start, rows)
        if best is not None:
            break
    if best is not None:
        _, planned, switches, entry, entered, start, rows = best
        rows = _replay(board, pools, rank, stream, start, rows)
        result["match"] = _recipe(done, planned, switches, entry, entered, start, rows)
    previews_run = bool(result["match"]["preview_sequence"]) if result["match"] else bool(done) or max_previews > 0
    result["conditions"] = conditions(game, cost, previews_run)
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


def _routes(previews, stream, cost, done, max_switches, max_previews):
    """For each planned length from 0 up, the entry positions no shorter route reaches, in preference order, each as
    (position, planned ranks, switches) with its preferred route: the fewest switches, then the first in rank order.

    A route's future depends only on its position, its last rank and the switches it has used. A route is therefore
    dropped when another reached the same position with the same last rank and no more switches, in fewer previews or
    earlier in preference order; with no limit on switches, the first route to reach them covers every later one.
    """
    ends = {}

    def after(position, rank):
        if (position, rank) not in ends:
            ends[(position, rank)] = previews.run(stream, position, rank, cost)["end"]
        return ends[(position, rank)]

    origin = previews.advance(stream, 0, done, cost)[1]
    # A route is (position, last rank, switches, planned ranks as a linked list, newest first); a frontier holds the
    # routes of one length in rank order.
    frontier = [(origin, done[-1] if done else None, 0, None)]
    fewest = {(origin, frontier[0][1]): 0}
    known = {origin}
    yield [(origin, [], 0)]
    for _ in range(max_previews):
        children = []
        for order, (position, last, switches, ranks) in enumerate(frontier):
            for rank in (1, 4) if last is not None else (1,):
                count = switches + (last is not None and rank != last)
                if max_switches is None or count <= max_switches:
                    children.append((count, order, rank, position, ranks))
        children.sort(key=lambda child: child[:3])
        kept, entries = [], []
        for count, order, rank, position, ranks in children:
            position, ranks = after(position, rank), (rank, ranks)
            rival = count if max_switches is not None else 0
            if fewest.get((position, rank), rival + 1) <= rival:
                continue
            fewest[(position, rank)] = rival
            kept.append((order, rank, (position, rank, count, ranks)))
            if position not in known:
                known.add(position)
                entries.append((position, _unlink(ranks), count))
        kept.sort(key=lambda route: route[:2])
        frontier = [route for _, _, route in kept]
        yield entries
        if not frontier:
            return


def _unlink(ranks):
    """A linked list of ranks, newest first, as a list in preview order."""
    planned = []
    while ranks is not None:
        rank, ranks = ranks
        planned.append(rank)
    return planned[::-1]


class _Search:
    """The recipe search at one activation start; everything that does not depend on the start is prepared once."""

    def __init__(self, stream, pools, board, kind_of, usable, options, wants, required, spawnable, rank, max_states):
        self.stream, self.pools, self.area, self.kind_of, self.usable = stream, pools, board.area, kind_of, usable
        self.options, self.wants, self.required, self.spawnable, self.rank = options, wants, required, spawnable, rank
        self.max_states = max_states
        self.reserved = {cell: plant for plant, cell in wants if rank == 1 or plant != LILYPAD}
        self.wants_at = {}
        for plant, cell in wants:
            self.wants_at.setdefault(cell, []).append(plant)
        self.usable_from = [sum(1 for cell in board.area[index:] if kind_of[cell] != NONE)
                            for index in range(len(board.area) + 1)]
        capacity = Counter(kind_of[cell] for cell in usable)
        # Options that may stand on the same kinds of cell are interchangeable once their results are drawn, so a state
        # counts them together, one group per kinds list. A state is (end, uses, made): uses holds a digit per group, its
        # number of sources, and made a digit per group and wanted plant, how many of that plant the group produced,
        # counted up to the number wanted.
        groups = []
        self.group_of = []
        for option in options:
            kinds = tuple(option["kinds"])
            if kinds not in groups:
                groups.append(kinds)
            self.group_of.append(groups.index(kinds))
        self.use_weight, self.use_radix, weight = [], [], 1
        for kinds in groups:
            self.use_weight.append(weight)
            self.use_radix.append(sum(capacity[kind] for kind in kinds) + 1)
            weight *= self.use_radix[-1]
        wanted = Counter(plant for plant, _ in wants)
        self.plant_index = {plant: index for index, plant in enumerate(sorted(wanted))}
        self.made_digit, weight = [], 1
        for _ in groups:
            digits = []
            for plant in sorted(wanted):
                digits.append((weight, wanted[plant]))
                weight *= wanted[plant] + 1
            self.made_digit.append(digits)
        self.needed = [(self.plant_index[plant], count) for plant, count in required.items()]
        # Sources fit the cells when, for every set of cell kinds, the sources whose options stand only on kinds of that
        # set are no more than its cells (Hall's condition for assigning sources to cells by kind).
        kinds = sorted(capacity)
        self.limits = []
        for size in range(1, len(kinds) + 1):
            for chosen in combinations(kinds, size):
                members = [index for index, own in enumerate(groups) if set(own) <= set(chosen)]
                if members:
                    self.limits.append((members, sum(capacity[kind] for kind in chosen)))
        self.spawn_pools, distinct = {}, []
        for cell in usable:
            for occupied in (False, True):
                pool = pools.spawn(kind_of[cell], occupied)
                if pool not in distinct:
                    distinct.append(pool)
                self.spawn_pools[(cell, occupied)] = (pool, distinct.index(pool))
        self.spawn_count = len(distinct)
        self._children, self._covered = {}, {}
        self._shuffles, self._spawns = {}, {}

    def run(self, start, max_sources):
        """The rows of the first accepted recipe at this activation start, fewest sources first, or None; and the number of
        sources at which the state cap stopped the search, or None if it did not. The rows have no runners-up."""
        self._shuffles, self._spawns = {}, {}
        if not self.required:
            rows = self._evaluate([], start)
            if rows is not None:
                return rows, None
        ends, uses, made, parents, chosen = [start], [0], [0], [-1], [-1]
        low, high = 0, 1
        count = len(self.options)
        pools = [option["pool"] for option in self.options]
        made_digit = [self.made_digit[group] for group in self.group_of]
        plant_index, memo, first = self.plant_index, self._shuffles, self.stream.first
        for depth in range(1, max_sources + 1):
            seen = set()
            for index in range(low, high):
                end, use, product = ends[index], uses[index], made[index]
                children = self._children.get(use)
                if children is None:
                    children = self._child_options(use)
                for option, child_use in children:
                    key = end * count + option
                    shuffled = memo.get(key)
                    if shuffled is None:
                        shuffled = memo[key] = first(pools[option], end)
                    result, child_end = shuffled
                    child_made = product
                    plant = plant_index.get(result)
                    if plant is not None:
                        weight, cap = made_digit[option][plant]
                        if product // weight % (cap + 1) < cap:
                            child_made += weight
                    state = (child_end, child_use, child_made)
                    if state in seen:
                        continue
                    if len(ends) >= self.max_states:
                        return None, depth
                    seen.add(state)
                    ends.append(child_end)
                    uses.append(child_use)
                    made.append(child_made)
                    parents.append(index)
                    chosen.append(option)
                    covered = self._covered.get(child_made)
                    if covered is None:
                        covered = self._covers(child_made)
                    if covered:
                        rows = self._evaluate(self._path(len(ends) - 1, parents, chosen, start), child_end)
                        if rows is not None:
                            return rows, None
            low, high = high, len(ends)
            if low == high:
                break
        return None, None

    def _child_options(self, use):
        """The options a state with these use counts may add, with the use counts after each."""
        counts = [use // weight % radix for weight, radix in zip(self.use_weight, self.use_radix)]
        children = []
        for option, group in enumerate(self.group_of):
            counts[group] += 1
            if all(sum(counts[member] for member in members) <= cells for members, cells in self.limits):
                children.append((option, use + self.use_weight[group]))
            counts[group] -= 1
        self._children[use] = children = tuple(children)
        return children

    def _covers(self, product):
        """Whether the made counts cover every wanted plant that needs a transformation."""
        covered = all(sum(product // digits[plant][0] % (digits[plant][1] + 1) for digits in self.made_digit) >= needed
                      for plant, needed in self.needed)
        self._covered[product] = covered
        return covered

    def _path(self, index, parents, chosen, start):
        """The steps of the sequence that first reached a state, from the memoised shuffles."""
        sequence = []
        while parents[index] >= 0:
            sequence.append(chosen[index])
            index = parents[index]
        path, position = [], start
        for option in reversed(sequence):
            result, end = self._shuffles[position * len(self.options) + option]
            path.append({"option": option, "candidates": len(self.options[option]["pool"]), "result": result,
                         "start": position, "end": end})
            position = end
        return path

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
            spawn = self._spawn(cell, offset, occupied=False)
            if spawn is None or all(plant == spawn["result"] for plant in wants):
                rows = self._walk(path, index + 1, occupied, spawned + [spawn] if spawn else spawned,
                                  spawn["end"] if spawn else offset)
                if rows is not None:
                    return rows
        if slots and self._may_occupy(cell, path):
            spawn = self._spawn(cell, offset, occupied=True)
            return self._walk(path, index + 1, occupied + [cell], spawned + [spawn] if spawn else spawned,
                              spawn["end"] if spawn else offset)
        return None

    def _may_occupy(self, cell, path):
        """A wanted cell may hold a source only if some step made its plant, or the pad beneath it is its want."""
        for plant in self.wants_at.get(cell, ()):
            if cell in self.reserved and self.reserved[cell] == plant:
                if not any(step["result"] == plant for step in path):
                    return False
            elif not self.spawn_pools[(cell, True)][0]:
                return False
        return True

    def _spawn(self, cell, offset, occupied):
        """One cell's spawn at an offset, or None when its pool is empty; shuffles are memoised by pool and offset."""
        pool, index = self.spawn_pools[(cell, occupied)]
        if not pool:
            return None
        key = offset * self.spawn_count + index
        if key not in self._spawns:
            self._spawns[key] = self.stream.first(pool, offset)
        result, end = self._spawns[key]
        return {"cell": cell, "beneath": occupied, "candidates": len(pool), "result": result, "start": offset, "end": end}

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
            row = selection_row("evolve", cell, kind, source, cost, step["candidates"],
                                [step["result"]] if step["result"] is not None else [], step["start"], step["end"])
            row["sources"] = [alias for alias, _ in pairs]
            rows.append(row)
        for spawn in spawned:
            row = selection_row("spawn", spawn["cell"], self.kind_of[spawn["cell"]], None, None, spawn["candidates"],
                                [spawn["result"]], spawn["start"], spawn["end"], beneath=spawn["beneath"])
            row["sources"] = []
            rows.append(row)
        place(rows, self.kind_of, self.pools.kinds)
        placed = {(row["result"], row["cell"]) for row in rows if row["placed"]}
        if not all(want in placed for want in self.wants):
            return None
        wanted = set(self.wants)
        for row in rows:
            row["wanted"] = bool(row["placed"]) and (row["result"], row["cell"]) in wanted
        return rows


def _replay(board, pools, rank, stream, start, rows):
    """The recipe's rows as `activate` computes them, with every shuffle's runners-up and the search's notes on sources and
    wants. A replay that differs from the rows the search accepted would be a defect of the search."""
    plantings = [Planting(row["source"], row["cost"], row["cell"]) for row in reversed(rows) if row["action"] == "evolve"]
    replay, _ = activate(board, pools, plantings, rank, stream, start)
    keys = ("action", "cell", "kind", "source", "cost", "candidates", "result", "start", "end", "placed", "beneath")
    if [tuple(row[k] for k in keys) for row in replay] != [tuple(row[k] for k in keys) for row in rows]:
        raise RuntimeError("The search accepted a recipe that does not replay")
    for row, searched in zip(replay, rows):
        row["sources"], row["wanted"] = searched["sources"], searched["wanted"]
    return replay


def _recipe(done, planned, switches, entry, entered, start, rows):
    for position, row in enumerate(rows, start=1):
        row["position"] = position
    sources = [row for row in rows if row["action"] == "evolve"]
    planting = [dict(row, step=index) for index, row in enumerate(reversed(sources), start=1)]
    return {"preview_sequence": done + planned, "planned_previews": planned, "switches": switches,
            "level_entry_offset": entry, "entry_effects": entered, "activation_offset": start,
            "source_count": len(sources), "processing_order": rows, "planting_order": planting,
            "stream_end": rows[-1]["end"] if rows else start}
