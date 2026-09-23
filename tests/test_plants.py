import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution import Game, available_plants, funnel, registry_records

POOLS = json.loads((Path(__file__).resolve().parent / "fixtures/pools.json").read_text())


class PlantsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = Game(POOLS["game_version"])
        cls.document = cls.game.plants

    def test_seven_filters_leave_257_of_383(self):
        self.assertEqual(len(self.document["plants"]), 383)
        self.assertEqual(len(funnel(self.document)), 257)

    def test_registry_puts_configured_names_first(self):
        configured = self.document["registry_order"]["configured_types"]
        ordered = [record["plant"] for record in registry_records(self.document)]
        present = [name for name in configured if name in ordered]
        self.assertEqual(ordered[:len(present)], present)
        self.assertEqual(len(ordered), 383)

    def test_preview_pools_equal_the_captured_lists(self):
        pools = self.game.previews.pools
        self.assertEqual(pools["evolution"], POOLS["pools"]["preview"]["evolution"])
        self.assertEqual(pools["spawn"], POOLS["pools"]["preview"]["spawn"])
        self.assertEqual((len(pools["evolution"]), len(pools["spawn"])), (226, 55))

    def test_every_bundled_version_builds_under_its_own_name(self):
        for version in available_plants():
            with self.subTest(version=version):
                self.assertEqual(Game(version).version, version)


if __name__ == "__main__":
    unittest.main()
