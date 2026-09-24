"""The artifact screen's previews: what each rank consumes and what it shows.

A preview evolves Sunflowers on a display board and, at rank 4, also spawns plants on
the board's empty cells. Every one of those steps is a shuffle of the shared engine, so
a preview moves the stream by a data-dependent but exactly replayable amount, and the
number and ranks of the previews run before entering a level choose where in the fixed
sequence the level's activation starts. The structures come from data/previews.json,
which was read from captures.
"""

import json
from collections import Counter
from pathlib import Path

from .level import Level, parse_cell
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
    def __init__(self, document, kinds, record=None, source_cost=None):
        self.record = record or load_previews()
        board = self.record["board"]
        self.board = Level({"id": "preview-board", "name": board.get("name", "artifact screen"),
                            "stage": board["stage"], "bans": board.get("bans", []), "default_kind": board["kind"]})
        self.evolution_source_cost = self.record["evolution_source_cost"] if source_cost is None else source_cost
        if type(self.evolution_source_cost) is not int or self.evolution_source_cost < 0:
            raise ValueError("Preview Sunflower cost must be a non-negative integer")
        self.spawn_max_cost = self.record["spawn_max_cost"]
        self.pools = {"evolution": self.board.pool(board["kind"], self.evolution_source_cost, document, kinds),
                      "spawn": self.board.spawn_pool(board["kind"], self.spawn_max_cost, document, kinds)}

    def ranks(self):
        return sorted(int(rank) for rank in self.record["ranks"])

    def steps(self, rank):
        """The shuffles of one preview of this rank, in order: (label, pool, cell or None)."""
        spec = self.record["ranks"].get(str(rank))
        if spec is None:
            raise ValueError("No measured structure for a rank-%s preview; known ranks: %s"
                             % (rank, ", ".join(str(r) for r in self.ranks())))
        steps = []
        for step in spec["steps"]:
            label = step["shuffle"]
            if label == "evolution":
                steps.extend(("evolution", self.pools["evolution"], parse_cell(cell)) for cell in step["cells"])
            elif label == "single":
                steps.extend(("single", [step["plant"]], None) for _ in range(step["count"]))
            elif label == "spawn":
                steps.extend(("spawn", self.pools["spawn"], None) for _ in range(step["count"]))
            else:
                raise ValueError("Unknown preview step: " + label)
        return steps

    def run(self, stream, offset, rank):
        """Selections and the offset after the completed preview, including supported placement draws."""
        rows = []
        for label, pool, cell in self.steps(rank):
            if not pool:
                raise ValueError("The preview Sunflower cost leaves no evolution candidates")
            shuffled, end = stream.shuffle(pool, offset)
            rows.append({"step": label, "cell": cell, "result": shuffled[0], "candidates": len(pool),
                         "start": offset, "end": end})
            offset = end
        # Effects run after all selections. Each rank-1 display row contains three
        # on-board plant objects throughout this replacement pass. Derive that
        # population from the source cells rather than treating Draftodil as +2:
        # shuffling even three objects can reject values and consume extra draws.
        row_counts = Counter(row["cell"][1] for row in rows if row["step"] == "evolution")
        for row in reversed(rows):
            if row["result"] != "draftodil":
                continue
            if rank != 1:
                raise ValueError("Rank-4 preview generates Draftodil, but its row population at placement "
                                 "is not modeled. Use rank-1 previews for this route.")
            _, offset = stream.shuffle(range(row_counts[row["cell"][1]]), offset)
        return rows, offset

    def advance(self, stream, offset, sequence):
        """A sequence of previews from an offset: one entry per preview, and the offset after them."""
        entries = []
        for index, rank in enumerate(sequence, start=1):
            rows, offset = self.run(stream, offset, rank)
            entries.append({"preview": index, "rank": rank, "results": rows,
                            "selection_end": rows[-1]["end"] if rows else offset, "end": offset})
        return entries, offset
