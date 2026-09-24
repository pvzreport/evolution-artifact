import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution import Game, available_levels, load_level

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


if __name__ == "__main__":
    unittest.main()
