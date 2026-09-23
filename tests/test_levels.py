import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution import NONE, Game, TileKind, available_levels, load_level

POOLS = json.loads((Path(__file__).resolve().parent / "fixtures/pools.json").read_text())
FIXTURES = POOLS["pools"]


class LevelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        game = Game(POOLS["game_version"])
        cls.document, cls.kinds = game.plants, game.kinds

    def test_every_description_loads_with_known_kinds(self):
        for name in available_levels():
            level = load_level(name)
            self.assertIn(level.default_kind, self.kinds)
            for kind in level.cells.values():
                self.assertIn(kind, self.kinds)

    def test_model_reproduces_every_captured_list_in_order(self):
        for name, group in FIXTURES.items():
            if name == "preview":
                continue
            level = load_level(name)
            for key, expected in group.items():
                kind, cost = key.split("@")
                with self.subTest(level=name, kind=kind, cost=cost):
                    self.assertEqual(level.pool(kind, int(cost), self.document, self.kinds), expected)

    def test_cell_kinds_of_the_described_boards(self):
        beach = load_level("memory-lane-s33-6-hard")
        self.assertEqual(beach.kind_at((2, 1)), "ground")
        self.assertEqual(beach.kind_at((3, 1)), "beach_shore")
        self.assertEqual(beach.kind_at((3, 1), {(3, 1): "beach_pad"}), "beach_pad")
        pirate = load_level("pirate1")
        self.assertEqual(pirate.kind_at((5, 4)), "ground")
        self.assertEqual(pirate.kind_at((6, 4)), "pirate_plank")
        self.assertEqual(pirate.kind_at((6, 3)), NONE)
        dark = load_level("dark1")
        self.assertEqual(dark.bans, [])
        self.assertEqual(dark.kind_at((3, 1)), NONE)
        self.assertEqual(dark.kind_at((2, 2)), "ground")

    def test_flooded_kind_admits_the_declared_wave_flag(self):
        water = self.kinds["beach_water"]
        flagged = [record["plant"] for record in self.document["plants"] if record.get("can_live_on_waves")]
        self.assertEqual(water.admits_only, flagged)
        self.assertEqual(len(flagged), 32)
        with self.assertRaises(ValueError):
            TileKind("flooded", {"admits_flag": "can_live_on_waves"})

    def test_unknown_level_and_kind_are_rejected(self):
        with self.assertRaises(ValueError):
            load_level("no-such-level")
        with self.assertRaises(ValueError):
            load_level("egypt13").pool("lava", 0, self.document, self.kinds)


if __name__ == "__main__":
    unittest.main()
