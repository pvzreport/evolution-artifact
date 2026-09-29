import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evolution import Stream, format_route, load_level, parse_route, scenario
from evolution.route import LevelStep, check_route
from projections import game_on

CAPTURE = json.loads((Path(__file__).parent / "fixtures" / "level-step-capture.json").read_text())


class LevelStepCaptureTest(unittest.TestCase):
    """The capture of a route of three level steps, replayed with the plant data of the version it was taken on."""

    def test_the_captured_route_replays(self):
        # Egypt 6 activated on 9-1, restarted and activated on 9-1 again, quit to the map, then Egypt 13 activated on
        # 2-2: every spawn, the draws of every shuffle, and every output from the first to the last, 1,096 in all.
        stream = Stream()
        out = scenario(game_on(CAPTURE["game_version"]), CAPTURE["route"], stream=stream)
        keys = ("candidates", "result", "start", "end")
        for step, expected in zip(out["steps"], CAPTURE["steps"]):
            with self.subTest(step=expected["step"]):
                self.assertEqual([[list(row["cell"])] + [row[k] for k in keys] + [row["end"] - row["start"], row["placed"]]
                                  for row in step["results"]],
                                 [[row["cell"]] + [row[k] for k in keys] + [row["draws"], True] for row in expected["rows"]])
                self.assertEqual((step["entry_effects"], step["effects"], step["end"], step["established"]),
                                 ([], [], expected["end"], True))
        self.assertEqual(len(out["steps"]), len(CAPTURE["steps"]))
        # The route was played with a restart between the two Egypt 6 steps and a quit before Egypt 13.
        self.assertEqual([step["leave"] for step in out["steps"]], ["restart", "quit", "quit"])
        self.assertEqual(out["offset_after_route"], CAPTURE["stream_end"])
        self.assertEqual(CAPTURE["raw_outputs"], [stream.output(i) for i in range(CAPTURE["stream_end"])])


class RouteTest(unittest.TestCase):
    """Routes with level steps on the bundled plant data, of game version 4.2.4; the expectations below are the model's
    values on that data."""

    @classmethod
    def setUpClass(cls):
        cls.game = game_on("4.2.4")

    def test_steps_are_named_as_written(self):
        route = parse_route("1x2,egypt6@9-1x2,dark4,D1")
        self.assertEqual(route[:2] + route[-1:], [1, 1, "D1"])
        self.assertEqual([(step.level.id, step.cell) for step in route[2:5]], [("egypt6", (9, 1))] * 2 + [("dark4", None)])
        self.assertEqual(format_route(route), "1x2,egypt6@9-1x2,dark4,D1")
        # Entering a level that shuffles nothing at entry and leaving would draw nothing, so such a step is refused.
        for text, message in (("egypt6", "would draw nothing"), ("egypt6@10-1", "outside the board"),
                              ("egypt7@2-2", "a level step, LEVEL@CELL or LEVEL"), ("1xa", "Unknown level '1xa'")):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, message):
                parse_route(text)

    def test_previews_after_a_level_step_start_with_an_opener(self):
        # The artifact screen is entered again after a level step, so its previews start as after a restart; a level
        # step may follow anything.
        for text in ("egypt6@9-1,1,4", "D1,D4,dark4,D1,D4", "1,4,egypt6@9-1", "egypt6@9-1,egypt13@2-2,D1"):
            with self.subTest(route=text):
                check_route(self.game.previews, parse_route(text))
        for text, message in (("egypt6@9-1,4", "4 cannot follow egypt6@9-1"), ("1,dark4,3", "3 cannot follow dark4"),
                              ("D1,egypt6@9-1,D4", "D4 cannot follow egypt6@9-1")):
            with self.subTest(route=text), self.assertRaisesRegex(ValueError, message):
                check_route(self.game.previews, parse_route(text))

    def test_a_draftodil_among_the_spawns_ends_what_is_established(self):
        # From a fresh launch, Dark Ages 19 at 6-4 spawns a Draftodil on 5-3. Its row shuffle counts the plants of its
        # row as it is added, last: the level's protected Magnet-shroom on 6-3, the spawn on 7-3 and itself. Its
        # attack is not modelled, so the replay stops there.
        out = scenario(self.game, ["dark19@6-4", 1], load_level("egypt1"), [], (2, 2), rank=4)
        step = out["steps"][0]
        self.assertEqual([(e["plant"], e["cell"], e["objects"]) for e in step["effects"]], [("draftodil", (5, 3), 3)])
        self.assertEqual((step["end"], step["established"]), (step["effects"][-1]["end"], False))
        self.assertEqual((len(out["steps"]), out["offset_after_route"], out["results"]), (1, None, []))
        # Egypt 13's description does not list the plants standing at its start, so the row shuffle of the Draftodil it
        # spawns on 2-1 from a fresh launch cannot be counted.
        step = scenario(self.game, ["egypt13@2-2"])["steps"][0]
        self.assertIn(((2, 1), "draftodil"), [(row["cell"], row["result"]) for row in step["results"]])
        self.assertEqual((step["effects"], step["end"], step["established"]), (None, None, False))


if __name__ == "__main__":
    unittest.main()
