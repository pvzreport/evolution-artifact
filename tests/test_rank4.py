import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from collections import Counter

from evolution import Board, Planting, Stream, activate, load_level, parse_cell, placement_draws, scenario
from projections import game_on

FIXTURES = Path(__file__).parent / "fixtures"
CAPTURES = [json.loads((FIXTURES / name).read_text()) for name in ("rank4-captures.json", "rank4-followups.json")]


class Rank4Test(unittest.TestCase):
    """Eleven captured rank-4 activations: selections, ordered pools, draw intervals, and the recorded plant-add calls,
    each replayed with the plant data of the game version it was captured on. A case with previews is a route from a
    fresh launch; a case with an offset is an activation at the position identified from its recorded draws, inside the
    level and after its entry, so it is replayed there directly."""

    @classmethod
    def setUpClass(cls):
        games = {version: game_on(version) for version in {fixture["game_version"] for fixture in CAPTURES}}
        cls.cases = [(games[fixture["game_version"]], case) for fixture in CAPTURES for case in fixture["cases"]]

    def test_captured_selections_and_placement_calls(self):
        for game, case in self.cases:
            with self.subTest(capture=case["capture"]):
                level = load_level(case["level"])
                plantings = [Planting(**p) for p in case["plantings"]]
                overrides = {parse_cell(cell): kind for cell, kind in case["cell_kinds"].items()}
                pools = game.pools(level)
                if "previews" in case:
                    result = scenario(game, level=level, plantings=plantings, activation=case["activation"],
                                      overrides=overrides, route=case["previews"], rank=4)
                    self.assertEqual((result["level_entry_offset"], result["activation_offset"]), (case["offset"], case["offset"]))
                    rows, end = result["results"], result["stream_end"]
                else:
                    board = Board(level, overrides, case["activation"])
                    rows, end = activate(board, pools, plantings, 4, Stream(), case["offset"])
                self.assertEqual(end, case["stream_end"])
                self.assertEqual(len(rows), len(case["expected"]))
                occupied = {p.cell for p in plantings}
                for actual, expected in zip(rows, case["expected"]):
                    for key in ("action", "result", "candidates", "start", "end"):
                        self.assertEqual(actual[key], expected[key], (case["capture"], expected["cell"], key))
                    self.assertEqual(list(actual["cell"]), expected["cell"])
                    self.assertEqual(actual["placed"], expected.get("placed", True), (case["capture"], expected["cell"]))
                    if actual["action"] == "evolve":
                        pool = pools.transformation(actual["cell_kind"], actual["cost"])
                    else:
                        pool = pools.spawn(actual["cell_kind"], actual["cell"] in occupied)
                    digest = hashlib.sha256(json.dumps(list(pool), separators=(",", ":")).encode()).hexdigest()
                    self.assertEqual(digest, expected["pool_sha256"], (case["capture"], expected["cell"]))
                if "captured_stream_end" in case:
                    # The sources were the only plants in their rows: the effects pass replays the recorded outputs.
                    _, after = placement_draws(rows, Counter(p.cell[1] for p in plantings), Stream(), end)
                    self.assertEqual(after, case["captured_stream_end"], case["capture"])
                if "plant_add_selection_indices" in case:
                    predicted = [i for i in reversed(range(1, len(rows) + 1)) if rows[i - 1]["placed"]]
                    self.assertEqual(predicted, case["plant_add_selection_indices"], case["capture"])


if __name__ == "__main__":
    unittest.main()
