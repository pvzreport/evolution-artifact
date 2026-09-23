"""One game version: its plant data, and the cell kinds and previews built on it.

Only the plant data differs between versions. The cell kinds, the preview structure and
the level descriptions are shared by every version, and each measurement records the
version it was taken on. Building the three together keeps a prediction from mixing one
version's plants with another's pools.
"""

from .model import Pools
from .plants import load_plants
from .previews import Previews
from .tiles import tile_kinds


class Game:
    def __init__(self, version=None):
        """version: a game version with plant data in data/plants; by default the newest."""
        self.plants = load_plants(version)
        self.version = self.plants["game"]["version"]
        self.platform = self.plants["game"]["platform"]
        self.kinds = tile_kinds(self.plants)
        self.previews = Previews(self.plants, self.kinds)

    def pools(self, level):
        """Every candidate list of one level under this version's plant data."""
        return Pools(self.plants, self.kinds, level, self.previews.spawn_max_cost)

    def describe(self):
        return {"version": self.version, "platform": self.platform}
