"""The artifact screen's previews: the Evolution artifact's activations on its display board, and the Devolution
artifact's shuffles.

An Evolution preview plants the source on the display board's listed cells and activates
there, so it is the same function as a level activation: the sources are evolved newest
first and, at rank 4, the spawn pass adds a Lily Pad beneath each source and a spawn on
each free cell of the 3x3. Its placement effects then run like any other activation's,
and because every plant on the display board is known, the draws they consume are known
too. A Devolution preview devolves its zombies with shuffles of fixed sizes. Each preview
therefore moves the shared stream by a replayable amount, and the route run before
entering a level chooses where in the fixed sequence the level's activation starts. The
boards, cells and shuffle sizes come from data/previews.json, which was read from
captures; the Evolution source's effective cost is a route input.
"""

from collections import Counter
import json
from pathlib import Path

from .level import Level, parse_cell
from .model import Board, Planting, Pools, activate, placement_draws
from .plants import DATA


def load_previews(path=None):
    return json.loads(Path(path or DATA / "previews.json").read_text())


class Previews:
    def __init__(self, document, kinds, record=None):
        self.record = record or load_previews()
        evolution = self.record["evolution"]
        board = evolution["board"]
        self.level = Level({"id": "preview-board", "name": board.get("name", "artifact screen"),
                            "stage": board["stage"], "bans": board.get("bans", []), "default_kind": board["kind"]})
        self.activation = parse_cell(evolution["activation"])
        self.source = evolution["source"]
        self.spawn_max_cost = evolution["spawn_max_cost"]
        self.sources = {int(rank): [parse_cell(cell) for cell in spec["sources"]]
                        for rank, spec in evolution["ranks"].items()}
        self.pools = Pools(document, kinds, self.level, self.spawn_max_cost)
        self.declared_cost = self.pools.costs[self.source]
        self.populations = {rank: Counter(cell[1] for cell in cells) for rank, cells in self.sources.items()}
        self.shuffles = {int(rank): tuple(spec["shuffles"]) for rank, spec in self.record["devolution"]["ranks"].items()}

    def evolution_ranks(self):
        """The Evolution ranks whose previews are known."""
        return sorted(self.sources)

    def devolution_ranks(self):
        """The Devolution ranks whose previews are known."""
        return sorted(self.shuffles)

    def cost(self, cost=None):
        """The previews' effective source cost: the given one, else the declared cost."""
        if cost is None:
            return self.declared_cost
        if isinstance(cost, bool) or not isinstance(cost, int) or cost < 0:
            raise ValueError("The preview source cost must be a non-negative integer")
        return cost

    def plantings(self, rank, cost):
        """The display board's sources for one Evolution rank at an effective cost, in planting order."""
        if not self.evolution_pool(cost):
            raise ValueError("A %s at effective cost %d has no evolution candidates" % (self.source, cost))
        return [Planting(self.source, cost, cell) for cell in self.sources[rank]]

    def evolution_pool(self, cost):
        """The display board's evolution pool for a source at this effective cost."""
        return self.pools.transformation(self.level.default_kind, cost)

    def spawn_pool(self):
        """The display board's rank-4 spawn pool for a free cell."""
        return self.pools.spawn(self.level.default_kind)

    def evolve(self, stream, offset, rank, cost):
        """One Evolution preview at an offset: its selection rows, its effect rows, the selection end and the offset
        after the effects."""
        board = Board(self.level, None, self.activation)
        rows, selection_end = activate(board, self.pools, self.plantings(rank, cost), rank, stream, offset)
        effects, end = placement_draws(rows, self.populations[rank], stream, selection_end)
        return rows, effects, selection_end, end

    def devolve(self, stream, offset, rank):
        """One Devolution preview at an offset: its shuffle rows and the offset after them."""
        shuffles = []
        for objects in self.shuffles[rank]:
            _, end = stream.shuffle(range(objects), offset)
            shuffles.append({"action": "shuffle", "objects": objects, "start": offset, "end": end})
            offset = end
        return shuffles, offset
