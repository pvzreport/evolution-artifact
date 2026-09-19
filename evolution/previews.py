"""The artifact screen's previews: what each rank consumes and what it shows.

A preview evolves Sunflowers on a display board and, at rank 4, also spawns plants on
the board's empty cells. Every one of those steps is a shuffle of the shared engine, so
a preview moves the stream by a data-dependent but exactly replayable amount, and the
number and ranks of the previews run before entering a level choose where in the fixed
sequence the level's activation starts. The structures come from data/previews.json,
which was read from captures.
"""

import json
from pathlib import Path

from .level import Level, parse_cell
from .plants import DATA, declared_costs
from .shuffle import random_shuffle


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
        self.board = Level({"id": "preview-board", "name": board.get("name", "artifact screen"),
                            "stage": board["stage"], "bans": board.get("bans", []), "default_kind": board["kind"]})
        costs = declared_costs(document)
        base = kinds[board["kind"]].filter(self.board.base_pool(document))
        self.pools = {"evolution": [a for a in base if costs[a] > self.record["evolution_source_cost"]],
                      "spawn": [a for a in base if costs[a] <= self.record["spawn_max_cost"]]}

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

    def run(self, engine, rank):
        """Advance the engine through one preview and return what it showed, step by step."""
        rows = []
        for label, pool, cell in self.steps(rank):
            start = engine.draws
            shuffled = random_shuffle(pool, engine)
            rows.append({"step": label, "cell": cell, "result": shuffled[0], "candidates": len(pool),
                         "start": start, "end": engine.draws})
        return rows

    def advance(self, engine, sequence):
        """Run a sequence of previews; returns one entry per preview."""
        return [{"preview": index, "rank": rank, "results": self.run(engine, rank)}
                for index, rank in enumerate(sequence, start=1)]
