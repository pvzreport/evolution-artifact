"""Cell kinds: what a cell's planting checks reject, measured per kind.

For every candidate, the picker runs the board's planting check on the source's own
cell, ignoring only the "occupied" reason. That check is code, so its effect is read
from captures rather than derived: each kind in data/tile-rules.json lists the plants
it rejects beyond the stage rule and the level's bans, or, for a flooded cell, names
the plant flag that admits a plant (the declared CanLiveOnWaves, carried by
plants.json as can_live_on_waves). The kind "none" is a cell that cannot hold a plant
and is never a target.
"""

import json
from pathlib import Path

from .plants import DATA, load_plants

NONE = "none"


class TileKind:
    def __init__(self, name, record, document=None):
        self.name = name
        self.description = record.get("description", "")
        self.rejects = set(record.get("rejects") or ())
        self.admits_flag = record.get("admits_flag")
        self.admits_only = record.get("admits_only")
        if self.admits_flag:
            if document is None:
                raise ValueError("Kind %r admits by the plant flag %r and needs the plant document" % (name, self.admits_flag))
            self.admits_only = [plant["plant"] for plant in document["plants"] if plant.get(self.admits_flag)]
        self.note = record.get("note", "")

    def admits(self, alias):
        if self.admits_only is not None:
            return alias in self.admits_only
        return alias not in self.rejects

    def filter(self, aliases):
        return [alias for alias in aliases if self.admits(alias)]


def load_tile_rules(path=None):
    return json.loads(Path(path or DATA / "tile-rules.json").read_text())


def tile_kinds(rules=None, document=None):
    """Name -> TileKind, including the built-in "none"; a kind that admits by flag reads the plant document."""
    rules = rules or load_tile_rules()
    if document is None and any(record.get("admits_flag") for record in rules["kinds"].values()):
        document = load_plants()
    kinds = {name: TileKind(name, record, document) for name, record in rules["kinds"].items()}
    kinds[NONE] = TileKind(NONE, {"description": "Open water or another cell that cannot hold a plant; never a target",
                                  "admits_only": []})
    return kinds
