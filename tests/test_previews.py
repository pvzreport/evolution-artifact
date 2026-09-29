import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evolution import scenario
from projections import game_on

FIXTURES = [json.loads((Path(__file__).parent / "fixtures" / name).read_text())
            for name in ("preview-captures.json", "preview-captures-4.2.4.json")]


class PreviewCaptureTest(unittest.TestCase):
    """Display-board captures replayed with the plant data of the version they were taken on: every Evolution selection
    with its cell, candidates, draw interval and placement, the recorded add order, the outputs recorded inside a
    Draftodil's add call, and the draw interval of every shuffle of a Devolution preview."""

    def test_captured_previews_replay(self):
        keys = ("action", "result", "candidates", "start", "end", "placed")
        for fixture in FIXTURES:
            game = game_on(fixture["game_version"])
            for case in fixture["cases"]:
                with self.subTest(capture=case["capture"]):
                    out = scenario(game, case["previews"], preview_cost=case["preview_cost"])
                    first = case["first_captured_preview"]
                    if first > 1:
                        self.assertEqual(out["steps"][first - 2]["end"], case["start_offset"])
                    for expected in case["expected"]:
                        preview = out["steps"][expected["preview"] - 1]
                        self.assertEqual((preview["artifact"], preview["rank"]),
                                         (expected.get("artifact", "evolution"), expected["rank"]))
                        self.assertEqual(preview["end"], expected["end"])
                        if preview["artifact"] == "devolution":
                            self.assertEqual([[s["start"], s["end"]] for s in preview["shuffles"]], expected["shuffles"])
                            continue
                        self.assertEqual([(list(r["cell"]),) + tuple(r[k] for k in keys) for r in preview["results"]],
                                         [(r["cell"],) + tuple(r[k] for k in keys) for r in expected["rows"]], expected["preview"])
                        self.assertEqual([[list(e["cell"]), e["plant"], e["start"], e["end"]] for e in preview["effects"]],
                                         [[e["cell"], e["plant"], e["start"], e["end"]] for e in expected["effects"]], expected["preview"])
                        self.assertEqual(preview["selection_end"], expected["selection_end"])
                        self.assertEqual([list(r["cell"]) for r in reversed(preview["results"]) if r["placed"]],
                                         expected["add_order"], expected["preview"])
                    self.assertEqual(out["offset_after_route"], case["stream_end"])


if __name__ == "__main__":
    unittest.main()
