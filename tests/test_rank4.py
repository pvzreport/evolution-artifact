import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution import Level, Planting, Previews, load_level, load_plants, parse_cell, scenario, search_recipe, tile_kinds
from evolution.activation import Activation

CASES = json.loads((Path(__file__).parent / "fixtures/rank4-captures.json").read_text())["cases"]
FOLLOWUPS = json.loads((Path(__file__).parent / "fixtures/rank4-followups.json").read_text())["cases"]


class Rank4Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_plants()
        cls.kinds = tile_kinds(document=cls.document)
        cls.previews = Previews(cls.document, cls.kinds)

    def test_captured_selections_and_placement_calls(self):
        for case in CASES + FOLLOWUPS:
            with self.subTest(capture=case["capture"]):
                level = load_level(case["level"])
                plantings = [Planting(**p) for p in case["plantings"]]
                overrides = {parse_cell(cell): kind for cell, kind in case["cell_kinds"].items()}
                result = scenario(self.document, self.kinds, self.previews, level=level,
                                  plantings=plantings, activation=case["activation"], overrides=overrides,
                                  sequence=case.get("previews", []),
                                  offset=0 if "previews" in case else case["offset"], rank=4)
                self.assertEqual(result["level_entry_offset"], case["offset"])
                self.assertEqual(result["stream_end"], case["stream_end"])
                self.assertEqual(len(result["results"]), len(case["expected"]))
                model = Activation(self.document, self.kinds, level, case["activation"], overrides)
                occupied = {p.cell for p in plantings}
                for actual, expected in zip(result["results"], case["expected"]):
                    for key in ("action", "result", "candidates", "start", "end"):
                        self.assertEqual(actual[key], expected[key], (case["capture"], expected["cell"], key))
                    self.assertEqual(list(actual["cell"]), expected["cell"])
                    if list(actual["cell"]) not in case.get("placement_excluded_cells", []):
                        self.assertEqual(actual["placed"], expected.get("placed", True))
                    pool = model.pool(actual["kind"], actual["cost"],
                                      occupied=actual["action"] == "spawn" and actual["cell"] in occupied)
                    digest = hashlib.sha256(json.dumps(pool, separators=(",", ":")).encode()).hexdigest()
                    self.assertEqual(digest, expected["pool_sha256"])
                if "plant_add_selection_indices" in case:
                    stable = {i for i, r in enumerate(result["results"], 1)
                              if list(r["cell"]) not in case["placement_excluded_cells"]}
                    predicted = [i for i in reversed(range(1, len(result["results"]) + 1))
                                 if i in stable and result["results"][i - 1]["placed"]]
                    recorded = [i for i in case["plant_add_selection_indices"] if i in stable]
                    self.assertEqual(predicted, recorded)

    def test_search_empty_area_reproduces_capture1(self):
        result = search_recipe(self.document, self.kinds, self.previews, load_level("egypt13"),
                               [("whitemelon", (1, 1))], {}, rank=4, max_sources=0, max_previews=0)
        match = result["match"]
        self.assertIsNotNone(match)
        self.assertEqual(match["source_count"], 0)
        self.assertEqual(match["planting_order"], [])
        self.assertEqual(match["stream_end"], 640)
        self.assertEqual([s["result"] for s in match["processing_order"]],
                         [s["result"] for s in CASES[0]["expected"]])

    def test_search_mixed_area_reproduces_capture4(self):
        for wants in ([("witchhazel", (1, 1))], [("witchhazel", (1, 1)), ("cracker", (1, 2))]):
            with self.subTest(wants=wants):
                result = search_recipe(self.document, self.kinds, self.previews, load_level("egypt1"),
                                       wants, {"puffshroom": 0}, activation=(2, 1), rank=4,
                                       min_previews=1, max_previews=1, max_sources=1)
                match = result["match"]
                self.assertIsNotNone(match)
                self.assertEqual(match["source_count"], 1)
                self.assertEqual(match["planting_order"][0]["cell"], "1-1")
                self.assertEqual(match["stream_end"], 3584)
                self.assertEqual([s["result"] for s in match["processing_order"]],
                                 [s["result"] for s in CASES[3]["expected"]])

    def test_search_can_target_both_water_layers_and_replay_its_recipe(self):
        level = load_level("beach3")
        overrides = {(c, r): "beach_water" for c in (4, 5, 6) for r in (2, 3, 4)}
        wants = [("electricpeel", (5, 3)), ("lilypad", (5, 3))]
        result = search_recipe(self.document, self.kinds, self.previews, level, wants,
                               {"seashroom": (0, ["beach_water"])}, activation=(5, 3), overrides=overrides,
                               rank=4, max_sources=1, max_previews=99)
        match = result["match"]
        self.assertIsNotNone(match)
        plantings = [Planting(s["source"], s["source_cost"], parse_cell(s["cell"])) for s in match["planting_order"]]
        replay = scenario(self.document, self.kinds, self.previews, [match["preview_rank"]] * match["preview_count"],
                          level, plantings, (5, 3), overrides, rank=4)
        produced = {(s["result"], s["cell"]) for s in replay["results"] if s["placed"]}
        self.assertTrue(set(wants) <= produced)
        self.assertEqual(replay["stream_end"], match["stream_end"])

    def test_new_pad_can_block_a_replacement_selected_before_it_existed(self):
        # A constructed shuffle selects Lily Pad from the water pool. The
        # rank-4 pad is added before the Sea-shroom replacement's final check.
        class PickLilyPadEngine:
            def __init__(self, index):
                self.index, self.draws = index, 0

            def __call__(self):
                self.draws += 1
                return self.index if self.draws == 1 else 0

        level = Level({"stage": "beach", "width": 1, "height": 1, "default_kind": "beach_water"})
        model = Activation(self.document, self.kinds, level, (1, 1))
        engine = PickLilyPadEngine(model.pool("beach_water", 0).index("lilypad"))
        rows = model.run([Planting("seashroom", 0, (1, 1))], engine, 4)
        self.assertEqual([(r["action"], r["result"], r["placed"]) for r in rows],
                         [("evolve", "lilypad", False), ("spawn", "lilypad", True)])
        self.assertEqual(rows[1]["start"], rows[1]["end"])


if __name__ == "__main__":
    unittest.main()
