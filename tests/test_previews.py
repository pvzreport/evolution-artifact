import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution import Game, scenario

FIXTURE = json.loads((Path(__file__).parent / "fixtures/preview-captures.json").read_text())


class PreviewCaptureTest(unittest.TestCase):
    """Two display-board captures replayed with the plant data of the version they were taken on: every selection
    with its cell, candidates, draw interval and placement, the recorded add order, and the outputs recorded inside
    a Draftodil's add call."""

    @classmethod
    def setUpClass(cls):
        cls.game = Game(FIXTURE["game_version"])

    def test_captured_previews_replay(self):
        keys = ("action", "result", "candidates", "start", "end", "placed")
        for case in FIXTURE["cases"]:
            with self.subTest(capture=case["capture"]):
                out = scenario(self.game, case["previews"], preview_cost=case["preview_cost"])
                first = case["first_captured_preview"]
                if first > 1:
                    self.assertEqual(out["previews"][first - 2]["end"], case["start_offset"])
                for expected in case["expected"]:
                    preview = out["previews"][expected["preview"] - 1]
                    self.assertEqual(preview["rank"], expected["rank"])
                    self.assertEqual([(list(r["cell"]),) + tuple(r[k] for k in keys) for r in preview["results"]],
                                     [(r["cell"],) + tuple(r[k] for k in keys) for r in expected["rows"]], expected["preview"])
                    self.assertEqual([[list(e["cell"]), e["plant"], e["start"], e["end"]] for e in preview["effects"]],
                                     [[e["cell"], e["plant"], e["start"], e["end"]] for e in expected["effects"]], expected["preview"])
                    self.assertEqual((preview["selection_end"], preview["end"]), (expected["selection_end"], expected["end"]))
                    self.assertEqual([list(r["cell"]) for r in reversed(preview["results"]) if r["placed"]],
                                     expected["add_order"], expected["preview"])
                self.assertEqual(out["offset_after_previews"], case["stream_end"])


if __name__ == "__main__":
    unittest.main()
