"""The artifact screen's previews: the Evolution artifact's activations on its display board, and the Devolution
artifact's shuffles.

An Evolution preview plants the source on the display board's listed cells and activates
there, so it is the same function as a level activation: the sources are evolved newest
first and, at rank 4, the spawn pass adds a Lily Pad beneath each source and a spawn on
each free cell of the 3x3. Its placement effects then run like any other activation's,
and because every plant on the display board is known, the draws they consume are known
too. A Devolution preview devolves its zombies with shuffles of fixed sizes. Each preview
therefore moves the shared stream by a replayable amount, and the previews run before
entering a level choose where in the fixed sequence the level's activation starts.

A preview is named as in a route: an Evolution preview by its rank, a Devolution
preview by D and its rank, so D1 is the Devolution artifact's rank-1 preview. Tapping an
artifact plays its rank-1 preview, so a route starts with a rank-1 preview, and so does
each run of an artifact's previews after another artifact's. The boards, cells and
shuffle sizes come from data/previews.json, which was read from captures; the Evolution
source's effective cost is a route input.
"""

from collections import Counter
import json
from pathlib import Path
import re

from .level import Level, parse_cell
from .model import Board, Planting, Pools, activate, placement_draws
from .plants import DATA

DEVOLUTION_PREFIX = "D"  # a Devolution preview's name is this prefix and its rank
_NAME = re.compile(r"(\d+)|[Dd](\d+)")


def load_previews(path=None):
    return json.loads(Path(path or DATA / "previews.json").read_text())


def parse_preview(text):
    """A preview's name: an Evolution rank such as 4, or D and a Devolution rank such as D1."""
    match = _NAME.fullmatch(text)
    if not match:
        raise ValueError("Name a preview by its Evolution rank, such as 4, or as D1 for the Devolution rank-1 preview")
    evolution, devolution = match.groups()
    return int(evolution) if evolution else DEVOLUTION_PREFIX + str(int(devolution))


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
        devolution = {int(rank): tuple(spec["shuffles"]) for rank, spec in self.record["devolution"]["ranks"].items()}
        self.shuffles = {DEVOLUTION_PREFIX + str(rank): sizes for rank, sizes in devolution.items()}
        # Every known preview by name, in preference order: the Evolution ranks, then the Devolution previews.
        self._known = {rank: ("evolution", rank) for rank in sorted(self.sources)}
        self._known.update((DEVOLUTION_PREFIX + str(rank), ("devolution", rank)) for rank in sorted(devolution))

    def ranks(self):
        """The Evolution ranks whose previews are known."""
        return sorted(self.sources)

    def names(self):
        """Every known preview, in preference order: the Evolution ranks, then the Devolution previews."""
        return list(self._known)

    def identify(self, preview):
        """A preview's artifact and rank."""
        if isinstance(preview, bool) or preview not in self._known:
            raise ValueError("No measured structure for the preview %r; known previews: %s, an Evolution preview named "
                             "by its int rank" % (preview, ", ".join(str(name) for name in self.names())))
        return self._known[preview]

    def artifacts(self, sequence):
        """The artifacts whose previews a sequence runs."""
        return {self.identify(preview)[0] for preview in sequence}

    def openers(self):
        """The previews tapping an artifact plays: each artifact's rank-1 preview."""
        return [name for name, (_, rank) in self._known.items() if rank == 1]

    def follows(self, last, preview):
        """Whether a route may run `preview` after `last`, None at a restart: tapping an artifact plays its rank-1
        preview, so any other rank needs a preview of the same artifact before it."""
        artifact, rank = self.identify(preview)
        return rank == 1 or (last is not None and self.identify(last)[0] == artifact)

    def check_preview(self, preview, cost):
        """Refuse an unknown preview, or an Evolution preview whose source has no candidates at this cost."""
        artifact, rank = self.identify(preview)
        if artifact == "evolution":
            self.plantings(rank, cost)

    def conditions(self, sequence, cost=None):
        """What running these previews assumes: the Evolution previews' source cost, and when each Devolution preview
        is complete."""
        lines = []
        if "evolution" in self.artifacts(sequence):
            lines.append("The previews' %s sources have effective cost %d." % (self.source, self.cost(cost)))
        for name in self.names():
            artifact, rank = self._known[name]
            if artifact == "devolution" and name in sequence:
                lines.append("%s is the Devolution artifact's rank-%d preview; each one is complete once its zombies are "
                             "devolved." % (name, rank))
        return lines

    def cost(self, cost=None):
        """The previews' effective source cost: the given one, else the declared cost."""
        if cost is None:
            return self.declared_cost
        if isinstance(cost, bool) or not isinstance(cost, int) or cost < 0:
            raise ValueError("The preview source cost must be a non-negative integer")
        return cost

    def plantings(self, rank, cost):
        """The display board's sources for one Evolution rank at an effective cost, in planting order."""
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

    def run(self, stream, offset, preview, cost):
        """One preview at an offset: its name, artifact and rank, what it drew, and the offset after it. An Evolution
        preview gives its selection rows, its effect rows and the selection end; a Devolution preview its shuffle rows."""
        artifact, rank = self.identify(preview)
        entry = {"name": preview, "artifact": artifact, "rank": rank}
        if artifact == "devolution":
            shuffles = []
            for objects in self.shuffles[preview]:
                _, end = stream.shuffle(range(objects), offset)
                shuffles.append({"action": "shuffle", "objects": objects, "start": offset, "end": end})
                offset = end
            return dict(entry, shuffles=shuffles, end=offset)
        board = Board(self.level, None, self.activation)
        rows, selection_end = activate(board, self.pools, self.plantings(rank, cost), rank, stream, offset)
        effects, end = placement_draws(rows, self.populations[rank], stream, selection_end)
        return dict(entry, results=rows, effects=effects, selection_end=selection_end, end=end)
