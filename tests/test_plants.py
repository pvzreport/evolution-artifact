import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evolution import available_levels, funnel, load_level, load_plants, load_previews, load_tile_rules
from evolution.model import ROW_SHUFFLERS
from evolution.plants import EXCLUDED_ALIASES
from projections import KEPT, game_on

POOLS = json.loads((Path(__file__).resolve().parent / "fixtures/pools.json").read_text())


class PlantsTest(unittest.TestCase):
    def test_seven_filters_leave_259_of_385(self):
        document = load_plants()
        self.assertEqual(len(document["plants"]), 385)
        self.assertEqual(len(funnel(document)), 259)

    def test_preview_pools_equal_the_captured_lists(self):
        previews = game_on(POOLS["game_version"]).previews
        self.assertEqual(list(previews.evolution_pool(50)), POOLS["pools"]["preview"]["evolution"])
        self.assertEqual(list(previews.spawn_pool()), POOLS["pools"]["preview"]["spawn"])

    def test_every_plant_data_declares_the_plants_the_shared_data_names(self):
        # The cell kinds, previews and levels are not tied to a version, and they apply to the bundled data and to every
        # projection kept for replaying evidence; a renamed plant would silently drop a rule.
        named = set(EXCLUDED_ALIASES)
        for kind in load_tile_rules()["kinds"].values():
            named |= set(kind.get("rejects") or ()) | set(kind.get("admits_only") or ())
        named.add(load_previews()["evolution"]["source"])
        named |= set(ROW_SHUFFLERS)
        for level in available_levels():
            named |= set(load_level(level).bans)
        for document in [load_plants()] + [load_plants(path) for path in sorted(KEPT.glob("*.json"))]:
            with self.subTest(version=document["game"]["version"]):
                declared = {record["plant"] for record in document["plants"]}
                self.assertEqual(sorted(named - declared), [])


if __name__ == "__main__":
    unittest.main()
