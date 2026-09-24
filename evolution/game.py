"""One game version: its plant data, and the cell kinds and previews built on it.

Only the plant data is versioned; the cell kinds, the preview structure and the level
descriptions are shared by every version. Building the three together keeps a prediction
from mixing one version's plants with another's pools.
"""

from .model import Pools
from .plants import load_plants
from .previews import Previews
from .tiles import tile_kinds


class Game:
    def __init__(self, version=None, preview_source_cost=None):
        """A version's data and the preview Sunflowers' effective cost (default: preview data)."""
        self.plants = load_plants(version)
        self.version = self.plants["game"]["version"]
        self.platform = self.plants["game"]["platform"]
        self.kinds = tile_kinds(self.plants)
        self.previews = Previews(self.plants, self.kinds, source_cost=preview_source_cost)

    def pools(self, level):
        """Every candidate list of one level under this version's plant data."""
        return Pools(self.plants, self.kinds, level, self.previews.spawn_max_cost)

    def describe(self):
        return {"version": self.version, "platform": self.platform,
                "preview_source_cost": self.previews.evolution_source_cost}
