"""The plant data the model runs on, and the cell kinds and previews built on it.

The plant data is the bundled one unless a Game is given another document, read with
load_plants(path), to replay evidence recorded on another game version. The cell kinds,
the preview structure and the level descriptions are not tied to a version. Building the
three together keeps a prediction from mixing one document's plants with another's pools.
"""

from .model import Pools
from .plants import load_plants
from .previews import Previews
from .tiles import tile_kinds


class Game:
    def __init__(self, plants=None):
        """plants: a plant data document as load_plants returns it; by default the bundled data."""
        self.plants = plants if plants is not None else load_plants()
        self.version = self.plants["game"]["version"]
        self.platform = self.plants["game"]["platform"]
        self.kinds = tile_kinds(self.plants)
        self.previews = Previews(self.plants, self.kinds)

    def pools(self, level):
        """Every candidate list of one level under this plant data."""
        return Pools(self.plants, self.kinds, level, self.previews.spawn_max_cost)

    def describe(self):
        return {"version": self.version, "platform": self.platform}
