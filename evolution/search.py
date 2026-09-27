"""Plan a recipe: which previews to run, then which sources to plant on which cells.

An activation's outcome depends on two independent things. Transformation results depend
only on the sequence of pools shuffled, in processing order, from the offset the activation
starts at, after the level's entry shuffles, never on cells. At rank 4 the spawn pass then
depends only on which cells are occupied: it shuffles once per free cell in area order and
adds a zero-draw Lily Pad on each occupied shore or water cell.

At one activation start the search walks sequences of pool options breadth first, fewest
sources first; sources with the same pool are one option, whatever their aliases or costs.
Everything below a sequence depends only on its state: the position its last shuffle ended
at, how many times it used each option, and how many of each wanted plant each option
produced, counted up to the number wanted. The walk keeps the first sequence that reaches
each state and drops the others, so it returns the recipe that walking every sequence
returns: the fewest sources, and among those the first sequence in option order. A
sequence grows only while its sources fit the cells their options may stand on, counted
per cell kind. Whenever a state's results cover every wanted plant that no spawn could
provide, the area is walked in its order deciding each cell occupied or free while
carrying the spawn offset, so a free wanted cell whose draw misses ends that branch at
once. At a leaf, a matching assigns the steps to the occupied cells by kind, reserving a
wanted cell for the step that produced its plant, and the rows are accepted only when
every wanted plant is placed. Shuffles are memoised by position and pool. A found recipe
is replayed through `activate` before it is returned.

Preview routes are searched by length. A route continues from the previews already run
since a full restart, and a route with previews starts with rank 1, the preview that
plays when the artifact is tapped. Routes that reach the same stream position are merged,
and each new position is searched once. The shortest route of the chosen style with a
recipe wins; among routes of that length, fewer sources, then fewer rank switches, then
the first route in rank order (rank 1 before rank 4).

A source whose pool is empty transforms into nothing, but at rank 4 it still occupies its
cell and so moves the spawns; all such sources form one option, planned only after every
real source of a sequence, which keeps each sequence unique.
"""

from collections import Counter
from itertools import combinations

from .level import LILYPAD, format_cell
from .model import PAD, RANKS, Board, activate, check_board, conditions, enter_level, place, selection_row
from .stream import shared
from .tiles import NONE

STYLES = {"simple": 1, "shorter": 3, "shortest": None}  # the most rank switches a route of each style may make
MAX_STATES = 1000000


def parse_spec(spec):
    """A source's cost and allowed kinds: `cost` or `(cost, [kinds])`."""
    return (int(spec), None) if isinstance(spec, int) else (int(spec[0]), list(spec[1]))


def search_recipe(game, level, wants, sources, activation=(2, 2), *, overrides=None, rank=1, done=(), style="simple",
                  max_previews=100, offset=0, max_sources=9, max_states=MAX_STATES, stream=None, preview_cost=None):
    """The shortest preview route of `style` after the `done` previews with a recipe placing every want.

    game: the game version whose data the recipe is for. wants: list of (plant, cell). sources:
    {alias: cost} or {alias: (cost, [kinds])} when a source may only be planted on cells of those
    kinds. overrides: {cell: kind} for this activation. done: the ranks of the previews already
    run since a full restart, in order. style: "simple" (at most one rank switch), "shorter" (at
    most three) or "shortest" (any number); a switch counts whenever a planned preview's rank
    differs from the one before it, the last done preview included. max_previews: the most
    previews planned after the done ones. offset: extra raw outputs consumed between the previews
    and the level, before the level's own entry shuffles. max_states: the most search states kept
    at one entry position, a memory guard; an entry that reaches it is listed in
    state_cap_reached. preview_cost: the previews' effective source cost; the default is the
    source's declared cost.
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
    if done and done[0] != 1:
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
        "entries_searched": 0, "state_cap_reached": [], "conditions": None, "match": None,
    }
    request = _Request(stream, pools, board, kind_of, usable, options, wants, required, spawnable, rank, max_states)
    routes = _Routes(previews, stream, cost, done, STYLES[style], max_previews)
    best = None
    for entries in routes.lengths():
        for position, planned, switches in entries:
            if best is not None and best[0] == 0:
                break
            entry = position + offset
            entered, start = enter_level(level, stream, entry)
            sequence, capped = request.search(start, max_sources if best is None else best[0] - 1)
            result["entries_searched"] += 1
            if capped is not None:
                result["state_cap_reached"].append({"preview_sequence": done + planned, "level_entry_offset": entry,
                                                    "activation_offset": start, "sources": capped})
            if sequence is not None:
                best = (len(sequence), planned, switches, entry, entered, start, sequence)
        if best is not None:
            break
    if best is not None:
        _, planned, switches, entry, entered, start, sequence = best
        rows = request.rows(sequence, start)
        _verify(board, pools, rank, stream, start, rows)
        result["match"] = _recipe(done, planned, switches, entry, entered, start, rows)
    route_has_previews = bool(result["match"]["preview_sequence"]) if best is not None else bool(done) or max_previews > 0
    result["conditions"] = conditions(game, cost, route_has_previews)
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


class _Routes:
    """Preview routes after the done previews, by length, merged on the stream position they reach.

    A route's future depends on its position, its last rank and the switches it has used, so a route is
    dropped when another route reached the same position with the same last rank and no more switches, by
    fewer previews or, at the same length, first by switches and then by rank order. With no limit on
    switches, the first route to reach a position with a last rank covers every later one.
    """

    def __init__(self, previews, stream, cost, done, max_switches, max_previews):
        self.previews, self.stream, self.cost = previews, stream, cost
        self.max_switches, self.max_previews = max_switches, max_previews
        _, self.origin = previews.advance(stream, 0, done, cost)
        self.last = done[-1] if done else None
        self._after = {}

    def after(self, position, rank):
        """The stream position after one complete preview of this rank."""
        key = (position, rank)
        if key not in self._after:
            self._after[key] = self.previews.run(self.stream, position, rank, self.cost)["end"]
        return self._after[key]

    def lengths(self):
        """For each planned length from 0 up, the positions no shorter route reached, in tie-break order, each as
        (position, planned ranks, switches) with its first route by fewest switches, then rank order."""
        positions, lasts, switches, parents = [self.origin], [self.last], [0], [-1]
        best = {(self.origin, self.last): 0}
        known = {self.origin}
        frontier = [0]
        yield [(self.origin, [], 0)]
        for _ in range(self.max_previews):
            children = []
            for order, index in enumerate(frontier):
                last = lasts[index]
                for rank in (1, 4):
                    if last is None and rank != 1:
                        continue
                    count = switches[index] + (last is not None and rank != last)
                    if self.max_switches is None or count <= self.max_switches:
                        children.append((count, order, rank, index))
            children.sort()
            kept, entries = [], []
            for count, order, rank, index in children:
                position = self.after(positions[index], rank)
                rival = count if self.max_switches is not None else 0
                if best.get((position, rank), rival + 1) <= rival:
                    continue
                best[(position, rank)] = rival
                positions.append(position)
                lasts.append(rank)
                switches.append(count)
                parents.append(index)
                kept.append((order, rank, len(positions) - 1))
                if position not in known:
                    known.add(position)
                    entries.append((position, self._route(len(positions) - 1, parents, lasts), count))
            kept.sort()
            frontier = [index for _, _, index in kept]
            yield entries
            if not frontier:
                return

    @staticmethod
    def _route(index, parents, lasts):
        ranks = []
        while parents[index] >= 0:
            ranks.append(lasts[index])
            index = parents[index]
        return ranks[::-1]


class _Request:
    """The search at one activation start, with everything that does not depend on the start prepared once."""

    def __init__(self, stream, pools, board, kind_of, usable, options, wants, required, spawnable, rank, max_states):
        self.stream, self.pools, self.area, self.kind_of, self.usable = stream, pools, board.area, kind_of, usable
        self.options, self.wants, self.required, self.spawnable, self.rank = options, wants, required, spawnable, rank
        self.max_states = max_states
        self.reserved = {cell: plant for plant, cell in wants if rank == 1 or plant != LILYPAD}
        self.wants_at = {}
        for plant, cell in wants:
            self.wants_at.setdefault(cell, []).append(plant)
        self.capacity = Counter(kind_of[cell] for cell in usable)
        self.usable_from = [sum(1 for cell in board.area[index:] if kind_of[cell] != NONE)
                            for index in range(len(board.area) + 1)]
        # A state is (end, uses, made). Options that may stand on the same kinds are interchangeable when steps are
        # assigned to cells, so they share digits: uses holds one digit per such group, its use count, and made one
        # digit per group and wanted plant, how many of that plant the group produced, counted up to the number
        # wanted. The option with an empty pool is a group of its own, since only it may follow itself.
        groups = []
        self.group_of = []
        for option in options:
            name = (tuple(option["kinds"]), bool(option["pool"]))
            if name not in groups:
                groups.append(name)
            self.group_of.append(groups.index(name))
        self.group_kinds = [kinds for kinds, _ in groups]
        self.empty = next((groups.index(name) for name in groups if not name[1]), None)
        wanted = Counter(plant for plant, _ in wants)
        plants = sorted(wanted)
        self.plant_index = {plant: index for index, plant in enumerate(plants)}
        self.use_weight, self.use_radix, weight = [], [], 1
        for kinds in self.group_kinds:
            radix = sum(self.capacity[kind] for kind in kinds) + 1
            self.use_weight.append(weight)
            self.use_radix.append(radix)
            weight *= radix
        self.made_digit, weight = [], 1
        for _ in groups:
            digits = []
            for plant in plants:
                digits.append((weight, wanted[plant]))
                weight *= wanted[plant] + 1
            self.made_digit.append(digits)
        self.needed = [(self.plant_index[plant], count) for plant, count in required.items()]
        # Sources fit the cells when, for every group of kinds, the sources whose options stand only on those kinds
        # are no more than the group's cells (Hall's condition for assigning sources to cells by kind).
        kinds = sorted(self.capacity)
        self.limits = []
        for size in range(1, len(kinds) + 1):
            for chosen in combinations(kinds, size):
                members = [group for group, own in enumerate(self.group_kinds) if set(own) <= set(chosen)]
                if members:
                    self.limits.append((members, sum(self.capacity[kind] for kind in chosen)))
        self.spawn_pools, distinct = {}, []
        for cell in board.area:
            if kind_of[cell] != NONE:
                for occupied in (False, True):
                    pool = pools.spawn(kind_of[cell], occupied)
                    if pool not in distinct:
                        distinct.append(pool)
                    self.spawn_pools[(cell, occupied)] = (pool, distinct.index(pool))
        self.spawn_count = len(distinct)
        self._children, self._covered = {}, {}
        self._shuffles, self._spawns = {}, {}

    def search(self, start, max_sources):
        """The option sequence of the first accepted recipe at this activation start, fewest sources first, or None;
        and the number of sources at which the state cap stopped the search, or None if it did not."""
        self._shuffles, self._spawns = {}, {}
        if not self.required and self._evaluate([], start) is not None:
            return [], None
        ends, uses, made, parents, chosen = [start], [0], [0], [-1], [-1]
        low, high = 0, 1
        count = len(self.options)
        pools = [option["pool"] for option in self.options]
        plant_index = self.plant_index
        made_digit = [self.made_digit[group] for group in self.group_of]
        memo, first = self._shuffles, self.stream.first
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
                        sequence = _sequence(len(ends) - 1, parents, chosen)
                        if self._evaluate(self._path(sequence, start), child_end) is not None:
                            return sequence, None
            low, high = high, len(ends)
            if low == high:
                break
        return None, None

    def rows(self, sequence, start):
        """The accepted rows of an option sequence at this start, with the runners-up of every shuffle."""
        path = self._path(sequence, start)
        rows = self._evaluate(path, path[-1]["end"] if path else start)
        if rows is None:
            raise RuntimeError("The search returned a recipe that it does not accept")
        for row in rows:
            if row["result"] is not None:
                pool = (self.pools.transformation(row["kind"], row["cost"]) if row["action"] == "evolve"
                        else self.pools.spawn(row["kind"], row["beneath"]))
                shuffled, end = self.stream.shuffle(pool, row["start"])
                if (shuffled[0], end) != (row["result"], row["end"]):
                    raise RuntimeError("A memoised shuffle differs from the replayed one")
                row["runners_up"] = shuffled[1:5]
        return rows

    def _child_options(self, use):
        """The options a state with these use counts may add, with the use counts after each."""
        counts = [use // weight % radix for weight, radix in zip(self.use_weight, self.use_radix)]
        blocked = self.empty is not None and counts[self.empty] > 0
        children = []
        for option, group in enumerate(self.group_of):
            if blocked and group != self.empty:
                continue
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

    def _path(self, sequence, start):
        """The steps of an option sequence from a start, from the memoised shuffles."""
        path, position = [], start
        for option in sequence:
            pool = self.options[option]["pool"]
            key = position * len(self.options) + option
            if key not in self._shuffles:
                self._shuffles[key] = self.stream.first(pool, position)
            result, end = self._shuffles[key]
            path.append({"option": option, "candidates": len(pool), "result": result, "start": position, "end": end})
            position = end
        return path

    def _evaluate(self, path, position):
        """Rows of an accepted recipe for this pool sequence, or None; runners-up are left empty."""
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


def _sequence(index, parents, chosen):
    """The options chosen on the way to a state, first to last."""
    options = []
    while parents[index] >= 0:
        options.append(chosen[index])
        index = parents[index]
    return options[::-1]


def _verify(board, pools, rank, stream, start, rows):
    """Replay the recipe through the activation model; a difference would be a defect of the search."""
    from .model import Planting
    plantings = [Planting(row["source"], row["cost"], row["cell"]) for row in reversed(rows) if row["action"] == "evolve"]
    replay, _ = activate(board, pools, plantings, rank, stream, start)
    keys = ("action", "cell", "kind", "result", "candidates", "start", "end", "placed", "runners_up")
    if [tuple(row[k] for k in keys) for row in replay] != [tuple(row[k] for k in keys) for row in rows]:
        raise RuntimeError("The search accepted a recipe that does not replay")


def _recipe(done, planned, switches, entry, entered, start, rows):
    for position, row in enumerate(rows, start=1):
        row["position"] = position
    sources = [row for row in rows if row["action"] == "evolve"]
    planting = [dict(row, step=index) for index, row in enumerate(reversed(sources), start=1)]
    return {"preview_sequence": done + planned, "planned_previews": planned, "switches": switches,
            "level_entry_offset": entry, "entry_effects": entered, "activation_offset": start,
            "source_count": len(sources), "processing_order": rows, "planting_order": planting,
            "stream_end": rows[-1]["end"] if rows else start}
