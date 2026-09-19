from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution import Previews, load_level, load_plants, search_recipe, tile_kinds


class RecipeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_plants()
        cls.kinds = tile_kinds()
        cls.previews = Previews(cls.document, cls.kinds)

    def search(self, level, wants, sources, activation=(2, 2), **options):
        return search_recipe(self.document, self.kinds, self.previews, load_level(level), wants, sources, activation, **options)

    def test_finds_two_aeoniums_in_memory_lane(self):
        result = self.search("memory-lane-s33-6-hard", [("aeonium", (1, 1)), ("aeonium", (1, 3))],
                             {"sunflower": 50, "puffshroom": 0}, max_previews=12)
        match = result["match"]
        self.assertIsNotNone(match)
        wanted = sorted((s["column"], s["row"]) for s in match["processing_order"] if s["wanted"])
        self.assertEqual(wanted, [(1, 1), (1, 3)])
        self.assertEqual([s["position"] for s in match["planting_order"]], list(range(match["source_count"], 0, -1)))
        for step in match["processing_order"]:
            self.assertIn("beach_shore" if step["column"] == 3 else "ground", step["kinds"])

    def test_wanted_plant_on_a_plank_cell_uses_the_plank_pool(self):
        result = self.search("pirate1", [("exorcislily", (6, 4))], {"puffshroom": 0, "sunflower": 50},
                             activation=(5, 4), max_previews=20)
        match = result["match"]
        self.assertIsNotNone(match)
        step = next(s for s in match["processing_order"] if s["wanted"])
        self.assertEqual(step["cell"], "6-4")
        self.assertIn("pirate_plank", step["kinds"])
        self.assertTrue(all(s["cell"] != "6-3" for s in match["processing_order"]))

    def test_source_restricted_to_a_kind(self):
        result = self.search("memory-lane-s33-6-hard", [("aeonium", (1, 1))],
                             {"sunflower": 50, "puffshroom": (0, ["ground"])}, max_previews=12)
        self.assertIsNotNone(result["match"])
        for step in result["match"]["processing_order"]:
            if "puffshroom" in step["sources"]:
                self.assertEqual(step["kinds"], ["ground"])

    def test_rank4_previews_as_the_dial(self):
        result = self.search("egypt13", [("kiwifruit", (2, 1))], {"wallnut": 50}, preview_rank=4, max_previews=15)
        self.assertEqual(result["preview_rank"], 4)
        self.assertIsNotNone(result["match"])
        self.assertEqual(result["match"]["preview_rank"], 4)

    def test_invalid_requests_are_rejected(self):
        with self.assertRaises(ValueError):
            self.search("pirate1", [("exorcislily", (6, 3))], {"puffshroom": 0}, activation=(5, 4))
        with self.assertRaises(ValueError):
            self.search("egypt13", [("lilypad", (1, 1))], {"puffshroom": 0})
        with self.assertRaises(ValueError):
            self.search("egypt13", [("kiwifruit", (1, 1))], {})


if __name__ == "__main__":
    unittest.main()
