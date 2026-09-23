"""One activation of the Evolution artifact, as a function of the board, the plantings and a stream position.

Every rule the predictor asserts is here, with the evidence behind it. The regression
fixtures under tests/fixtures replay the captures named below.

- A transformation shuffles the pool of its source's cell kind and effective cost and
  selects element 0; sources are processed newest planting first (every capture).
- At rank 4 a second pass visits the 3x3 around the activation cell down each column and
  then to the right, skipping positions outside the board, and shuffles for each cell the
  candidates it admits costing at most the preview file's spawn_max_cost. An occupied
  cell admits nothing, except that an occupied shore or water cell admits a Lily Pad
  beneath its plant, a one-candidate shuffle that consumes no outputs (captures 1 to 10,
  follow-ups A and Cactus).
- Effects then run in reverse selection order, and each selected plant is re-checked
  against its cell's kind at that moment: a Lily Pad placed earlier turns its cell into
  beach_pad, which rejects some replacements, and a second Lily Pad on one cell is
  dropped (follow-ups B and Cactus). The `placed` flag of a row records the outcome.
"""

from .level import LILYPAD, format_cell
from .plants import declared_costs, stage_allows
from .stream import shared
from .tiles import NONE

PAD = "beach_pad"
RANKS = (1, 4)

CONDITIONS = [
    "Start after a full process restart (seed 5489, offset 0).",
    "Run exactly the listed previews, each one complete, and nothing else that uses the artifact "
    "before entering the level.",
    "Accepted modeling assumption: entering or restarting a level consumes no shared-engine outputs.",
    "Same level as described, sources at the listed effective cost (no discounts unless included), "
    "activate once while every source remains and before any automatic spawning.",
    "Each cell's kind must match the board at activation: Beach cells right of the coast are shore when dry, "
    "water when flooded without a pad, and pad whenever a Lily Pad is present, bare or occupied. "
    "Keep terrain and supports unchanged until the effects finish, apart from the predicted additions.",
    "Plant exactly the listed sources in the listed order inside the 3x3 around the activation cell; "
    "the newest plant is processed first.",
]


class Planting:
    """One transformation source: alias, effective cost, cell, and optionally the cell's kind for this activation."""

    def __init__(self, source, cost, cell, kind=None):
        self.source = source
        self.cost = int(cost)
        self.cell = tuple(cell)
        self.kind = kind

    def __repr__(self):
        return "Planting(%r, %r, %r, %r)" % (self.source, self.cost, self.cell, self.kind)


def area_around(activation, width=9, height=5):
    """In-bounds cells of the 3x3 around the activation cell, down each column and then to the right."""
    column, row = activation
    if not (1 <= column <= width and 1 <= row <= height):
        raise ValueError("Activation cell %s is outside the board" % format_cell(activation))
    return [(c, r) for c in range(column - 1, column + 2)
            for r in range(row - 1, row + 2) if 1 <= c <= width and 1 <= r <= height]


class Board:
    """A level with this activation's cell-kind overrides and, when known, its activation cell."""

    def __init__(self, level, overrides=None, activation=None):
        self.level = level
        self.overrides = {tuple(cell): kind for cell, kind in (overrides or {}).items()}
        self.activation = tuple(activation) if activation is not None else None
        self.area = area_around(self.activation, level.width, level.height) if self.activation is not None else None

    def contains(self, cell):
        return self.level.contains(cell)

    def kind_at(self, cell):
        return self.level.kind_at(tuple(cell), self.overrides)


class Pools:
    """Every candidate list of one level, computed once. Pools are tuples, so they can key a memo."""

    def __init__(self, document, kinds, level, spawn_max_cost):
        self.document, self.kinds, self.level = document, kinds, level
        self.costs = declared_costs(document)
        self.allowed = {record["plant"] for record in document["plants"]
                        if stage_allows(record, level.stage) and record["plant"] not in level.bans}
        self.spawn_max_cost = spawn_max_cost
        self._pools = {}

    def plantable(self, alias, kind):
        """Whether a player can plant this source on a cell of this kind in this level; a Lily Pad is a kind, not a source."""
        return alias in self.allowed and alias != LILYPAD and self.kinds[kind].admits(alias)

    def candidates(self, kind):
        """Registry-ordered plants a cell of this kind admits in this level."""
        key = ("candidates", kind)
        if key not in self._pools:
            self._pools[key] = tuple(self.level.candidates(kind, self.document, self.kinds))
        return self._pools[key]

    def transformation(self, kind, cost):
        """The pool of a source of this effective cost on a cell of this kind."""
        key = ("evolve", kind, cost)
        if key not in self._pools:
            self._pools[key] = tuple(self.level.pool(kind, cost, self.document, self.kinds))
        return self._pools[key]

    def spawn(self, kind, occupied=False):
        """The rank-4 pool of a cell of this kind, bare or beneath a plant."""
        key = ("spawn", kind, occupied)
        if key not in self._pools:
            self._pools[key] = tuple(self.level.spawn_pool(kind, self.spawn_max_cost, self.document, self.kinds, occupied))
        return self._pools[key]


def selection_row(action, cell, kind, source, cost, candidates, shuffled, start, end):
    """One selection: what was shuffled, what came first, and the offsets the shuffle spanned."""
    return {"action": action, "cell": tuple(cell), "kind": kind, "source": source, "cost": cost,
            "candidates": candidates, "result": shuffled[0] if shuffled else None, "runners_up": shuffled[1:5],
            "start": start, "end": end, "placed": None}


def select(stream, offset, pool, action, cell, kind, source=None, cost=None):
    """One shuffle at an offset: the row it produces and the offset after it."""
    shuffled, end = stream.shuffle(pool, offset)
    return selection_row(action, cell, kind, source, cost, len(pool), shuffled, offset, end), end


def check_board(board, kinds):
    for cell, kind in board.overrides.items():
        if not board.contains(cell):
            raise ValueError("Override cell %s is outside the board" % format_cell(cell))
        if not isinstance(kind, str) or kind not in kinds:
            raise ValueError("Unknown cell kind %r at %s; known: %s" % (kind, format_cell(cell), ", ".join(sorted(kinds))))


def check_plantings(board, pools, plantings, kind_of):
    cells = [planting.cell for planting in plantings]
    if len(set(cells)) != len(cells):
        raise ValueError("List at most one transformation source per cell; describe Lily Pads with beach_pad")
    for planting in plantings:
        if planting.source not in pools.costs:
            raise ValueError("Unknown source plant %r at %s" % (planting.source, format_cell(planting.cell)))
        if not board.contains(planting.cell) or (board.area is not None and planting.cell not in board.area):
            raise ValueError("Source cell %s is outside the activation area or board" % format_cell(planting.cell))
        kind = kind_of[planting.cell]
        if kind == NONE:
            raise ValueError("Cell %s cannot hold a plant in this level" % format_cell(planting.cell))
        if not isinstance(kind, str) or kind not in pools.kinds:
            raise ValueError("Unknown cell kind %r at %s; known: %s" % (kind, format_cell(planting.cell), ", ".join(sorted(pools.kinds))))
        if not pools.plantable(planting.source, kind):
            raise ValueError("%s cannot stand on %s (%s) in this level" % (planting.source, format_cell(planting.cell), kind))


def kinds_for(board, plantings):
    """The kind of every cell this activation touches; a planting's stated kind wins over the board's."""
    cells = board.area if board.area is not None else [planting.cell for planting in plantings]
    kind_of = {cell: board.kind_at(cell) for cell in cells}
    for planting in plantings:
        kind_of[planting.cell] = planting.kind or board.kind_at(planting.cell)
    return kind_of


def transformations(pools, plantings, kind_of, stream, offset):
    """The transformation rows, newest planting first, and the offset after them."""
    rows = []
    for planting in reversed(plantings):
        kind = kind_of[planting.cell]
        row, offset = select(stream, offset, pools.transformation(kind, planting.cost), "evolve",
                             planting.cell, kind, planting.source, planting.cost)
        rows.append(row)
    return rows, offset


def spawn_pass(pools, area, kind_of, occupied, stream, offset):
    """The rank-4 additions over the area, in its order, and the offset after them."""
    rows = []
    for cell in area:
        pool = pools.spawn(kind_of[cell], cell in occupied)
        if pool:
            row, offset = select(stream, offset, pool, "spawn", cell, kind_of[cell])
            rows.append(row)
    return rows, offset


def place(rows, kind_of, kinds):
    """Resolve the effects in reverse selection order, setting each row's `placed` flag."""
    pads = {cell for cell, kind in kind_of.items() if kind == PAD}
    for row in reversed(rows):
        alias, cell = row["result"], row["cell"]
        kind = PAD if cell in pads else kind_of[cell]
        row["placed"] = alias is not None and not (alias == LILYPAD and cell in pads) and kinds[kind].admits(alias)
        if row["placed"] and alias == LILYPAD:
            pads.add(cell)
    return rows


def activate(board, pools, plantings, rank, stream, offset):
    """The rows of one activation and the offset after its last selection."""
    if rank not in RANKS:
        raise ValueError("Supported activation ranks are 1 and 4")
    plantings = list(plantings)
    check_board(board, pools.kinds)
    kind_of = kinds_for(board, plantings)
    check_plantings(board, pools, plantings, kind_of)
    rows, offset = transformations(pools, plantings, kind_of, stream, offset)
    if rank == 4:
        if board.area is None:
            raise ValueError("Rank-4 activation needs an activation cell")
        spawned, offset = spawn_pass(pools, board.area, kind_of, {p.cell for p in plantings}, stream, offset)
        rows.extend(spawned)
    return place(rows, kind_of, pools.kinds), offset


def scenario(document, kinds, previews, sequence=(), level=None, plantings=(), activation=None,
             overrides=None, offset=0, rank=1, stream=None):
    """Replay previews, optional extra raw outputs, then an optional activation, from a fresh process."""
    if offset < 0:
        raise ValueError("The extra offset cannot be negative")
    stream = stream or shared()
    preview_rows, after_previews = previews.advance(stream, 0, list(sequence))
    entry = after_previews + offset
    results, end = [], entry
    if level:
        board = Board(level, overrides, activation)
        pools = Pools(document, kinds, level, previews.spawn_max_cost)
        results, end = activate(board, pools, plantings, rank, stream, entry)
    return {"previews": preview_rows, "offset_after_previews": after_previews, "extra_offset": offset,
            "level": level.describe() if level else None, "level_entry_offset": entry,
            "activation": {"column": activation[0], "row": activation[1]} if activation else None, "rank": rank,
            "results": results, "stream_end": end, "conditions": list(CONDITIONS)}
