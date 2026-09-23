from collections import Counter
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution import Planting, Previews, load_level, load_plants, parse_cell, scenario, search_recipe, tile_kinds
from evolution.recipe import _assign, _breadth_first


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
        result = self.search("egypt13", [("eagleclaw", (2, 1))], {"wallnut": 50},
                             preview_rank=4, min_previews=2, max_previews=2, max_sources=1)
        self.assertEqual(result["preview_rank"], 4)
        self.assertIsNotNone(result["match"])
        self.assertEqual(result["match"]["preview_rank"], 4)
        match = result["match"]
        self.assertEqual(match["preview_sequence"], [1] + [4] * (match["preview_count"] - 1))
        self.assertEqual(match["level_entry_offset"], 4292)
        plantings = [Planting(s["source"], s["source_cost"], parse_cell(s["cell"])) for s in match["planting_order"]]
        replay = scenario(self.document, self.kinds, self.previews, match["preview_sequence"],
                          load_level("egypt13"), plantings, (2, 2))
        self.assertIn(("eagleclaw", (2, 1)), {(r["result"], r["cell"]) for r in replay["results"] if r["placed"]})

    def test_two_tallnuts_across_ground_and_shore_replay_every_want(self):
        wants = [("tallnut", (3, 2)), ("tallnut", (4, 2))]
        for rank in (1, 4):
            with self.subTest(rank=rank):
                result = self.search("beach3", wants, {"sunflower": 50, "puffshroom": 0},
                                     activation=(4, 2), rank=rank, min_previews=10, max_previews=10)
                match = result["match"]
                self.assertIsNotNone(match)
                self.assertEqual(result["budget_exhausted_counts"], 0)
                plantings = [Planting(s["source"], s["source_cost"], parse_cell(s["cell"])) for s in match["planting_order"]]
                replay = scenario(self.document, self.kinds, self.previews, match["preview_sequence"],
                                  load_level("beach3"), plantings, (4, 2), rank=rank)
                produced = {(r["result"], r["cell"]) for r in replay["results"] if r["placed"]}
                self.assertTrue(set(wants) <= produced)

    def test_grouped_count_defers_cell_kinds_to_matching(self):
        class TwoDrawEngine:
            def __init__(self, draws=0):
                self.draws = draws

            def clone(self):
                return TwoDrawEngine(self.draws)

            def __call__(self):
                value = (0, 1)[self.draws]
                self.draws += 1
                return value

        def option(pool, kinds, alias):
            return {"pool": pool, "kinds": kinds, "cost": 0, "sources": [alias],
                    "sources_by_kind": {kind: [alias] for kind in kinds}}

        options = [option(["tallnut", "wallnut"], ["ground", "beach_shore"], "sunflower"),
                   option(["wallnut", "tallnut"], ["ground"], "puffshroom")]
        cells = [(1, 1), (2, 1)]
        kind_of = {cells[0]: "ground", cells[1]: "beach_shore"}
        wants = [("tallnut", cell) for cell in cells]
        path, exhausted = _breadth_first(TwoDrawEngine(), options, Counter({"tallnut": 2}),
                                        Counter(kind_of.values()), 2, 100, wants, cells, kind_of)
        self.assertFalse(exhausted)
        self.assertIsNotNone(path)
        self.assertEqual([(s["result"], s["cell"]) for s in path], [("tallnut", (2, 1)), ("tallnut", (1, 1))])

    def test_assignment_matches_fillers_and_wants_together(self):
        cells = [(1, 1), (2, 1), (1, 2), (2, 2)]
        kind_of = {cell: "ground" if cell[0] == 1 else "beach_shore" for cell in cells}
        def step(plant, kinds):
            return {"result": plant, "kinds": kinds, "sources_by_kind": {k: ["puffshroom"] for k in kinds}}
        path = [step("tallnut", ["beach_shore"]), step("tallnut", ["ground", "beach_shore"]),
                step("tallnut", ["ground"]), step("wallnut", ["ground"])]
        wants = [("tallnut", (1, 1)), ("tallnut", (2, 1))]
        assigned = _assign(path, wants, cells, kind_of)
        self.assertIsNotNone(assigned)
        self.assertEqual({(s["result"], s["cell"]) for s in assigned if s["wanted"]}, set(wants))
        self.assertEqual(len({s["cell"] for s in assigned}), len(path))
        impossible = [step("tallnut", ["ground"]), step("tallnut", ["ground"]), step("wallnut", ["beach_shore"])]
        self.assertIsNone(_assign(impossible, wants, cells[:3], kind_of))

    def test_invalid_requests_are_rejected(self):
        with self.assertRaises(ValueError):
            self.search("pirate1", [("exorcislily", (6, 3))], {"puffshroom": 0}, activation=(5, 4))
        with self.assertRaises(ValueError):
            self.search("egypt13", [("lilypad", (1, 1))], {"puffshroom": 0})
        with self.assertRaises(ValueError):
            self.search("egypt13", [("kiwifruit", (1, 1))], {})


if __name__ == "__main__":
    unittest.main()
