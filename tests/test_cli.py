import contextlib
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution.cli import main


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main(list(argv))
    return out.getvalue()


class CliTest(unittest.TestCase):
    def assert_error(self, argv, message):
        error = io.StringIO()
        with contextlib.redirect_stderr(error), self.assertRaises(SystemExit) as raised:
            run(*argv)
        self.assertEqual(raised.exception.code, 2)
        self.assertIn(message, error.getvalue())

    def test_predict_previews_only(self):
        text = run("predict", "--previews", "1,4")
        self.assertIn("pinecone", text)
        self.assertIn("buttercup", text)

    def test_predict_level_with_cell_kinds(self):
        text = run("predict", "--level", "memory-lane-s33-6-hard", "--activate", "3-2",
                   "--plant", "sunflower=50@2-1", "--plant", "seashroom=0@3-2:beach_water")
        self.assertIn("beach_water", text)
        self.assertIn("17 candidates", text)

    def test_predict_rank4_shows_blocked_placements(self):
        text = run("predict", "--rank", "4", "--level", "beach3", "--previews", "1x11", "--activate", "5-3",
                   "--plant", "puffshroom=0@5-3", "--plant", "sunflower=50@6-4", "--plant", "sunflower=50@4-2")
        self.assertIn("cactus (placement blocked)", text)
        self.assertIn("Selection stream ends at 32923.", text)

    def test_plan_recipe_replays_through_predict(self):
        plan = json.loads(run("plan", "--rank", "4", "--level", "egypt13", "--want", "kiwifruit@2-1",
                              "--want", "primalwallnut@3-3", "--source", "wallnut=50", "--max-previews", "0", "--json"))
        match = plan["match"]
        argv = ["predict", "--rank", "4", "--level", "egypt13", "--activate", "2-2", "--json"]
        for step in match["planting_order"]:
            argv += ["--plant", "%s=%d@%d-%d" % (step["source"], step["cost"], step["cell"][0], step["cell"][1])]
        replay = json.loads(run(*argv))
        self.assertEqual([(r["result"], r["cell"], r["placed"]) for r in replay["results"]],
                         [(r["result"], r["cell"], r["placed"]) for r in match["processing_order"]])
        self.assertEqual(replay["stream_end"], match["stream_end"])

    def test_plan_text_output(self):
        text = run("plan", "--rank", "4", "--level", "egypt13", "--want", "whitemelon@1-1", "--max-sources", "0", "--max-previews", "0")
        self.assertIn("leave the activation area empty", text)
        self.assertIn("rank-4 Evolution", text)
        text = run("plan", "--level", "egypt13", "--want", "eagleclaw@2-1", "--source", "wallnut=50", "--previews", "1",
                   "--preview-rank", "4", "--min-previews", "1", "--max-previews", "1", "--max-sources", "1")
        self.assertIn("Run these previews, each one complete: 1,4.", text)
        self.assertIn("eagleclaw  <- wanted", text)

    def test_repeated_source_flags_widen_the_kinds(self):
        plan = json.loads(run("plan", "--level", "memory-lane-s33-6-hard", "--want", "aeonium@1-1", "--max-previews", "12",
                              "--source", "sunflower=50", "--source", "puffshroom=0:ground", "--source", "puffshroom=0:beach_shore", "--json"))
        self.assertEqual(sorted(k for o in plan["options"] if o["sources"] == ["puffshroom"] for k in o["kinds"]), ["beach_shore", "ground"])
        self.assert_error(["plan", "--level", "egypt13", "--want", "kiwifruit@1-1", "--source", "wallnut=50", "--source", "wallnut=75"],
                          "two costs")

    def test_pool_listing(self):
        text = run("pool", "--level", "pirate1", "--kind", "pirate_plank", "--cost", "0")
        self.assertIn("242 candidates", text)

    def test_errors_exit_with_code_2(self):
        self.assert_error(["predict", "--level", "egypt1", "--activate", "1-1", "--plant", "puffshrom=0@1-1"], "Unknown source plant")
        self.assert_error(["predict", "--rank", "4", "--level", "egypt1"], "needs --activate")
        self.assert_error(["plan", "--level", "egypt1", "--want", "kiwifruit@1-1", "--source", "puffshroom=0:groudn"], "Unknown cell kind")
        self.assert_error(["predict", "--level", "egypt13", "--activate", "2-2", "--plant", "wallnut=50@1-1", "--cell", "3-3=grund"], "Unknown cell kind")
        self.assert_error(["predict", "--rank", "4", "--level", "beach3", "--activate", "5-3", "--plant", "lilypad=25@5-3"], "cannot stand on")
        self.assert_error(["plan", "--rank", "4", "--level", "beach3", "--activate", "5-3", "--want", "cactus@5-3", "--source", "puffshroom=0"],
                          "can never be placed")


if __name__ == "__main__":
    unittest.main()
