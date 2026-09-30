import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evolution import load_level, search_recipe
from projections import game_on
from reference_search import FIXTURE, case_request, digest, reference_rows

# Requests whose reference search takes milliseconds per entry: one or two options.
CHEAP = ("uniform ground, rank 1, one Kernel-pult, 1 band", "uniform ground, rank 1, two Kernel-pults, 2 bands",
         "uniform ground, rank 4, one Kernel-pult, 1 band", "uniform ground, rank 4, two Kernel-pults, 2 bands",
         "gravestone bags at entry, rank 1, a Draftodil", "a source with an empty pool, rank 4, a White Melon")


class SearchEqualityTest(unittest.TestCase):
    """At every recorded level entry the merged search must return the recipe that walking every sequence of pool
    options returns: the same sources, cells, order and rows, or no recipe. The walk is tests/reference_search.py, and
    tests/fixtures/search-equality.json holds its recipes for requests on uniform ground, ground with Beach shore,
    Lily Pad cells and Pirate planks, at ranks 1 and 4 with one to eight cost bands, with a level that shuffles
    gravestone bags at entry and with a source whose pool is empty. Among them are three Kernel-pults, and two
    Peashooters with two Burdock batters. The entries were drawn at random, and those added to reach recipes were chosen
    by the reference, never by the search under test."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text())
        cls.game = game_on(cls.fixture["game_version"])

    def test_recipes_equal_the_reference(self):
        for case in self.fixture["cases"]:
            level_id, activation, wants, sources, rank, overrides, max_sources = case_request(case)
            level = load_level(level_id)
            for entry, count, expected in case["entries"]:
                with self.subTest(case=case["name"], entry=entry):
                    match = search_recipe(self.game, level, wants, sources, activation, overrides=overrides, rank=rank,
                                          max_length=0, offset=entry, max_sources=max_sources)["match"]
                    self.assertEqual((match["source_count"], digest(match["processing_order"])) if match else (None, None),
                                     (count, expected))

    def test_the_fixture_holds_the_reference_recipes(self):
        # Where the reference is cheap, run it again at every entry that has a recipe.
        checked = 0
        for case in self.fixture["cases"]:
            if case["name"] in CHEAP:
                for entry, _, expected in case["entries"]:
                    if expected is not None:
                        self.assertEqual(digest(reference_rows(self.game, case, entry)), expected, (case["name"], entry))
                        checked += 1
        self.assertGreater(checked, 40)


if __name__ == "__main__":
    unittest.main()
