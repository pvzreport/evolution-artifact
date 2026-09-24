"""The artifact screen's previews: activations on its display board.

A preview plants the source on the display board's listed cells and activates there, so
it is the same function as a level activation: the sources are evolved newest first and,
at rank 4, the spawn pass adds a Lily Pad beneath each source and a spawn on each free
cell of the 3x3. Its placement effects then run like any other activation's, and because
every plant on the display board is known, the draws they consume are known too. Each
preview therefore moves the shared stream by a replayable amount, and the previews run
before entering a level choose where in the fixed sequence the level's activation starts.
The board, the activation cell and each rank's source cells come from data/previews.json,
which was read from captures; the source's effective cost is a route input.
"""

from collections import Counter
import json
from pathlib import Path

from .level import Level, parse_cell
from .model import Board, Planting, Pools, activate, placement_draws
from .plants import DATA


def load_previews(path=None):
    return json.loads(Path(path or DATA / "previews.json").read_text())


def parse_sequence(text):
    """Preview ranks in order: "1x6,4" is six rank-1 previews then one rank-4 preview."""
    sequence = []
    for part in str(text or "").replace(" ", "").split(","):
        if not part:
            continue
        rank, _, times = part.partition("x")
        if not rank.isdigit() or (times and not times.isdigit()):
            raise ValueError("A preview sequence lists RANK or RANKxCOUNT items separated by commas, for example 1x6,4")
        sequence.extend([int(rank)] * (int(times) if times else 1))
    return sequence


class Previews:
    def __init__(self, document, kinds, record=None):
        self.record = record or load_previews()
        board = self.record["board"]
        self.level = Level({"id": "preview-board", "name": board.get("name", "artifact screen"),
                            "stage": board["stage"], "bans": board.get("bans", []), "default_kind": board["kind"]})
        self.activation = parse_cell(self.record["activation"])
        self.source = self.record["source"]
        self.spawn_max_cost = self.record["spawn_max_cost"]
        self.sources = {int(rank): [parse_cell(cell) for cell in spec["sources"]]
                        for rank, spec in self.record["ranks"].items()}
        self.pools = Pools(document, kinds, self.level, self.spawn_max_cost)
        self.declared_cost = self.pools.costs[self.source]
        self.populations = {rank: Counter(cell[1] for cell in cells) for rank, cells in self.sources.items()}

    def ranks(self):
        return sorted(self.sources)

    def cost(self, cost=None):
        """The previews' effective source cost: the given one, else the declared cost."""
        if cost is None:
            return self.declared_cost
        if isinstance(cost, bool) or not isinstance(cost, int) or cost < 0:
            raise ValueError("The preview source cost must be a non-negative integer")
        return cost

    def plantings(self, rank, cost):
        """The display board's sources for one rank at an effective cost, in planting order."""
        if rank not in self.sources:
            raise ValueError("No measured structure for a rank-%s preview; known ranks: %s"
                             % (rank, ", ".join(str(r) for r in self.ranks())))
        if not self.evolution_pool(cost):
            raise ValueError("A %s at effective cost %d has no evolution candidates" % (self.source, cost))
        return [Planting(self.source, cost, cell) for cell in self.sources[rank]]

    def evolution_pool(self, cost):
        """The display board's evolution pool for a source at this effective cost."""
        return self.pools.transformation(self.level.default_kind, cost)

    def spawn_pool(self):
        """The display board's rank-4 spawn pool for a free cell."""
        return self.pools.spawn(self.level.default_kind)

    def run(self, stream, offset, rank, cost):
        """One preview at an offset: its selection rows and effect rows, the selection end and the offset after."""
        board = Board(self.level, None, self.activation)
        rows, selection_end = activate(board, self.pools, self.plantings(rank, cost), rank, stream, offset)
        effects, end = placement_draws(rows, self.populations[rank], stream, selection_end)
        return {"results": rows, "effects": effects, "selection_end": selection_end, "end": end}

    def advance(self, stream, offset, sequence, cost):
        """A sequence of previews from an offset: one entry per preview, and the offset after them."""
        entries = []
        for index, rank in enumerate(sequence, start=1):
            entry = self.run(stream, offset, rank, cost)
            entries.append({"preview": index, "rank": rank, **entry})
            offset = entry["end"]
        return entries, offset
