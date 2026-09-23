import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution import Planting, Pools, Previews, load_level, load_plants, parse_cell, scenario, tile_kinds

FIXTURES = Path(__file__).parent / "fixtures"
CASES = json.loads((FIXTURES / "rank4-captures.json").read_text())["cases"]
FOLLOWUPS = json.loads((FIXTURES / "rank4-followups.json").read_text())["cases"]


class Rank4Test(unittest.TestCase):
    """Thirteen captured rank-4 activations: selections, ordered pools, draw intervals, and the recorded plant-add calls."""

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
                pools = Pools(self.document, self.kinds, level, self.previews.spawn_max_cost)
                occupied = {p.cell for p in plantings}
                excluded = case.get("placement_excluded_cells", [])
                for actual, expected in zip(result["results"], case["expected"]):
                    for key in ("action", "result", "candidates", "start", "end"):
                        self.assertEqual(actual[key], expected[key], (case["capture"], expected["cell"], key))
                    self.assertEqual(list(actual["cell"]), expected["cell"])
                    if list(actual["cell"]) not in excluded:
                        self.assertEqual(actual["placed"], expected.get("placed", True), (case["capture"], expected["cell"]))
                    if actual["action"] == "evolve":
                        pool = pools.transformation(actual["kind"], actual["cost"])
                    else:
                        pool = pools.spawn(actual["kind"], actual["cell"] in occupied)
                    digest = hashlib.sha256(json.dumps(list(pool), separators=(",", ":")).encode()).hexdigest()
                    self.assertEqual(digest, expected["pool_sha256"], (case["capture"], expected["cell"]))
                if "plant_add_selection_indices" in case:
                    stable = {i for i, r in enumerate(result["results"], 1) if list(r["cell"]) not in excluded}
                    predicted = [i for i in reversed(range(1, len(result["results"]) + 1))
                                 if i in stable and result["results"][i - 1]["placed"]]
                    recorded = [i for i in case["plant_add_selection_indices"] if i in stable]
                    self.assertEqual(predicted, recorded, case["capture"])


if __name__ == "__main__":
    unittest.main()
