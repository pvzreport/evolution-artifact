"""Replay a stated scenario: previews, then an activation in a level.

Nothing here discovers the game's state. The scenario states it: a full process
restart, a sequence of previews, optionally extra raw outputs, then the plants standing
in the 3x3 around the activation cell in the order they were planted. The result is
what the engine, started from seed 5489, produces for exactly that history. Newly
planted sources are processed newest first, and each source draws from the pool of
its level, its cell's kind, and its effective cost.
"""

from .level import format_cell
from .shuffle import Mt19937, random_shuffle
from .tiles import NONE

CONDITIONS = [
    "Start after a full process restart (seed 5489, offset 0).",
    "Run exactly the listed previews, each one complete, and nothing else that uses the artifact "
    "before entering the level. Entering a level directly, or restarting it, consumes nothing.",
    "Same level as described, sources at the listed effective cost (no discounts unless included), "
    "rank-1 artifact activated once while every source remains.",
    "Each cell's kind must match the board at activation: Beach cells right of the coast are shore when dry, "
    "water when flooded without a pad, and pad when a plant stands on a Lily Pad, whether the cell is flooded or dry.",
    "Plant exactly the listed sources in the listed order inside the 3x3 around the activation cell; "
    "the newest plant is processed first.",
]


class Planting:
    """One planted source: alias, effective cost, cell, and optionally the cell's kind for this activation."""

    def __init__(self, source, cost, cell, kind=None):
        self.source = source
        self.cost = int(cost)
        self.cell = tuple(cell)
        self.kind = kind

    def __repr__(self):
        return "Planting(%r, %r, %r, %r)" % (self.source, self.cost, self.cell, self.kind)


def area_around(activation):
    """The nine cells of the 3x3 around an activation cell, row by row."""
    column, row = activation
    cells = [(c, r) for r in (row - 1, row, row + 1) for c in (column - 1, column, column + 1)]
    if any(value < 1 for cell in cells for value in cell):
        raise ValueError("The 3x3 around the activation cell must stay on the board")
    return cells


def predict_level(document, kinds, level, plantings, engine, activation=None, overrides=None):
    """Results of one activation. Plantings are in planting order; the newest is processed first."""
    if activation is not None:
        area = set(area_around(activation))
        outside = [p for p in plantings if p.cell not in area]
        if outside:
            raise ValueError("Outside the 3x3 around the activation: " + ", ".join(format_cell(p.cell) for p in outside))
    seen = set()
    for planting in plantings:
        if planting.cell in seen:
            raise ValueError("Two plantings on cell " + format_cell(planting.cell))
        seen.add(planting.cell)
    rows = []
    for planting in reversed(plantings):
        kind = planting.kind or level.kind_at(planting.cell, overrides)
        if kind == NONE:
            raise ValueError("Cell %s cannot hold a plant in this level" % format_cell(planting.cell))
        pool = level.pool(kind, planting.cost, document, kinds)
        start = engine.draws
        shuffled = random_shuffle(pool, engine)
        rows.append({"cell": planting.cell, "source": planting.source, "cost": planting.cost, "kind": kind,
                     "candidates": len(pool), "result": shuffled[0] if shuffled else None,
                     "runners_up": shuffled[1:5], "start": start, "end": engine.draws})
    return rows


def scenario(document, kinds, previews, sequence=(), level=None, plantings=(), activation=None,
             overrides=None, offset=0):
    """Replay previews, optional extra raw outputs, then an optional activation."""
    if offset < 0:
        raise ValueError("The extra offset cannot be negative")
    engine = Mt19937()
    preview_rows = previews.advance(engine, list(sequence))
    after_previews = engine.draws
    for _ in range(offset):
        engine()
    entry = engine.draws
    results = predict_level(document, kinds, level, list(plantings), engine, activation, overrides) if level else []
    return {"previews": preview_rows, "offset_after_previews": after_previews, "extra_offset": offset,
            "level": level.describe() if level else None, "level_entry_offset": entry,
            "activation": {"column": activation[0], "row": activation[1]} if activation else None,
            "results": results, "stream_end": engine.draws, "conditions": list(CONDITIONS)}
