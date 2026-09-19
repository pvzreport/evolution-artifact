import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution import Previews, funnel, load_plants, registry_records, tile_kinds

FIXTURES = json.loads((Path(__file__).resolve().parent / "fixtures/pools.json").read_text())["pools"]


class PlantsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_plants()

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
        previews = Previews(self.document, tile_kinds())
        self.assertEqual(previews.pools["evolution"], FIXTURES["preview"]["evolution"])
        self.assertEqual(previews.pools["spawn"], FIXTURES["preview"]["spawn"])
        self.assertEqual((len(previews.pools["evolution"]), len(previews.pools["spawn"])), (226, 55))


if __name__ == "__main__":
    unittest.main()
