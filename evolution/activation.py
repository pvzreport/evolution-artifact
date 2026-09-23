"""The active skill: select replacements, select rank-4 additions, then place them.

Cell kinds describe the board before activation. A beach_pad includes an existing
Lily Pad; plantings describe the ordinary plants above any support layer.
"""

from .level import format_cell
from .plants import declared_costs
from .shuffle import random_shuffle
from .tiles import NONE


class Planting:
    """One transformation source, supplied in planting order."""

    def __init__(self, source, cost, cell, kind=None):
        self.source = source
        self.cost = int(cost)
        self.cell = tuple(cell)
        self.kind = kind

    def __repr__(self):
        return "Planting(%r, %r, %r, %r)" % (self.source, self.cost, self.cell, self.kind)


def area_around(activation, width=9, height=5):
    """In-bounds cells of the 3x3, down each column and then to the right."""
    column, row = activation
    if not (1 <= column <= width and 1 <= row <= height):
        raise ValueError("Activation cell is outside the board")
    return [(c, r) for c in range(column - 1, column + 2)
            for r in range(row - 1, row + 2) if 1 <= c <= width and 1 <= r <= height]


class Activation:
    """Shared activation rules and candidate pools for prediction and recipe search."""

    def __init__(self, document, kinds, level, activation=None, overrides=None):
        self.document, self.kinds, self.level = document, kinds, level
        self.cells = area_around(activation, level.width, level.height) if activation is not None else None
        self.overrides = overrides or {}
        self.costs = declared_costs(document)
        self.base = level.base_pool(document)
        self.pools = {}

    def kind_at(self, cell):
        return self.level.kind_at(cell, self.overrides)

    def pool(self, kind, cost=None, occupied=False):
        """A cost requests a transformation pool; None requests rank-4 placement."""
        key = kind, cost, occupied
        if key not in self.pools:
            if kind not in self.kinds:
                raise ValueError("Unknown cell kind: " + kind)
            candidates = self.kinds[kind].filter(self.base)
            if cost is None:
                candidates = [a for a in candidates if self.costs[a] <= 100
                              and (not occupied or a == "lilypad")]
            else:
                candidates = [a for a in candidates if self.costs[a] > cost]
            self.pools[key] = candidates
        return self.pools[key]

    @staticmethod
    def select(pool, engine, cell, kind, source=None, cost=None):
        start = engine.draws
        shuffled = random_shuffle(pool, engine)
        return {"action": "evolve" if source is not None else "spawn", "cell": tuple(cell),
                "source": source, "cost": cost, "kind": kind, "candidates": len(pool),
                "result": shuffled[0] if shuffled else None, "runners_up": shuffled[1:5],
                "start": start, "end": engine.draws}

    def transform(self, planting, engine):
        kind = planting.kind or self.kind_at(planting.cell)
        if kind == NONE:
            raise ValueError("Cell %s cannot hold a plant in this level" % format_cell(planting.cell))
        return self.select(self.pool(kind, planting.cost), engine, planting.cell,
                           kind, planting.source, planting.cost)

    def finish(self, plantings, transformations, engine, rank):
        """Complete a selected prefix against the original board, then resolve effects."""
        if rank not in (1, 4):
            raise ValueError("Supported activation ranks are 1 and 4")
        occupied = {p.cell for p in plantings}
        cell_kinds = {p.cell: p.kind for p in plantings if p.kind}
        rows = [dict(row) for row in transformations]
        if rank == 4:
            if self.cells is None:
                raise ValueError("Rank-4 activation needs an activation cell")
            for cell in self.cells:
                kind = cell_kinds.get(cell) or self.kind_at(cell)
                pool = self.pool(kind, occupied=cell in occupied)
                if pool:
                    rows.append(self.select(pool, engine, cell, kind))

        # Effects are processed in reverse selection order. A new Lily Pad can
        # change the final planting check of a replacement selected over water.
        cells = self.cells or occupied
        pads = {cell for cell in cells if (cell_kinds.get(cell) or self.kind_at(cell)) == "beach_pad"}
        for row in reversed(rows):
            alias, cell = row["result"], row["cell"]
            row["placed"] = False
            if alias is None:
                continue
            if row["action"] == "evolve":
                occupied.discard(cell)
            kind = "beach_pad" if cell in pads else (cell_kinds.get(cell) or self.kind_at(cell))
            layer = pads if alias == "lilypad" else occupied
            if cell not in layer and self.kinds[kind].admits(alias):
                layer.add(cell)
                row["placed"] = True
        return rows

    def run(self, plantings, engine, rank=1):
        cells = [p.cell for p in plantings]
        if len(set(cells)) != len(cells):
            raise ValueError("List at most one transformation source per cell; describe Lily Pads with beach_pad")
        if any(not self.level.contains(cell) or (self.cells is not None and cell not in self.cells) for cell in cells):
            raise ValueError("A source is outside the activation area or board")
        rows = [self.transform(p, engine) for p in reversed(plantings)]
        return self.finish(plantings, rows, engine, rank)


def predict_level(document, kinds, level, plantings, engine, activation=None, overrides=None, rank=1):
    return Activation(document, kinds, level, activation, overrides).run(plantings, engine, rank)
