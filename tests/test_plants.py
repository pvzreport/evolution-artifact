import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution import (Game, available_levels, funnel, game_versions, load_level, load_plants, load_previews,
                       load_tile_rules, registry_records)
from evolution.plants import EXCLUDED_ALIASES

CAPTURED_ON = "4.2.2"  # the version whose declared data gives the counts asserted below
POOLS = json.loads((Path(__file__).resolve().parent / "fixtures/pools.json").read_text())


class PlantsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_plants(CAPTURED_ON)

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
        pools = Game(POOLS["game_version"]).previews.pools
        self.assertEqual(pools["evolution"], POOLS["pools"]["preview"]["evolution"])
        self.assertEqual(pools["spawn"], POOLS["pools"]["preview"]["spawn"])

    def test_every_version_declares_the_plants_the_shared_data_names(self):
        # The cell kinds, previews and levels are shared by every version; a renamed plant would silently drop a rule.
        named = set(EXCLUDED_ALIASES)
        for kind in load_tile_rules()["kinds"].values():
            named |= set(kind.get("rejects") or ()) | set(kind.get("admits_only") or ())
        for rank in load_previews()["ranks"].values():
            named |= {step["plant"] for step in rank["steps"] if "plant" in step}
        for level in available_levels():
            named |= set(load_level(level).bans)
        for version in game_versions():
            with self.subTest(version=version):
                declared = {record["plant"] for record in load_plants(version)["plants"]}
                self.assertEqual(sorted(named - declared), [])


if __name__ == "__main__":
    unittest.main()
