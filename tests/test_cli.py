import contextlib
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution.cli import main


def run(*argv):
    """What a command prints."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main(list(argv))
    return out.getvalue()


class CliTest(unittest.TestCase):
    """The commands run on the bundled plant data, of game version 4.2.4. An expectation was read from the game only
    where its comment says so; the others are the model's values on that data, which the command must print."""

    def assert_error(self, argv, message):
        error = io.StringIO()
        with contextlib.redirect_stderr(error), self.assertRaises(SystemExit) as raised:
            run(*argv)
        self.assertEqual(raised.exception.code, 2)
        self.assertIn(message, error.getvalue())

    def test_predict_level_with_cell_kinds(self):
        text = run("predict", "--level", "memory-lane-s33-6-hard", "--activate", "3-2",
                   "--plant", "sunflower=50@2-1", "--plant", "seashroom=0@3-2:beach_water")
        self.assertIn("(beach_water, 19 candidates)", text)

    def test_predict_rank4_shows_blocked_placements(self):
        # After thirteen previews the Sunflower at 4-2 evolves into a Snap Pea, which the Lily Pad added beneath it rejects.
        text = run("predict", "--rank", "4", "--level", "beach3", "--previews", "E1x13", "--activate", "5-3",
                   "--plant", "puffshroom=0@5-3", "--plant", "sunflower=50@6-4", "--plant", "sunflower=50@4-2",
                   "--cell", "4-2=beach_shore", "--cell", "4-4=beach_shore", "--cell", "6-4=beach_shore")
        self.assertIn("4-2 sunflower, cost 50 (beach_shore, 226 candidates) -> snappea (placement blocked)", text)
        self.assertIn("Selection stream ends at 38734.", text)

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
        text = run("plan", "--level", "egypt13", "--want", "eagleclaw@2-1", "--source", "wallnut=50", "--done", "E1",
                   "--style", "simple", "--max-previews", "1", "--max-sources", "1")
        self.assertIn("Continue from the previews already run since a full relaunch: E1.", text)
        self.assertIn("Run these further previews, each one complete, with sunflower at effective cost 50: E4.", text)
        self.assertIn("eagleclaw  <- wanted", text)

    def test_repeated_source_flags_widen_the_kinds(self):
        plan = json.loads(run("plan", "--level", "memory-lane-s33-6-hard", "--want", "aeonium@1-1", "--max-previews", "12",
                              "--cell", "3-1=beach_shore", "--cell", "3-2=beach_shore", "--cell", "3-3=beach_shore",
                              "--source", "sunflower=50", "--source", "puffshroom=0:ground", "--source", "puffshroom=0:beach_shore", "--json"))
        self.assertEqual(sorted(k for o in plan["options"] if o["sources"] == ["puffshroom"] for k in o["kinds"]), ["beach_shore", "ground"])
        self.assert_error(["plan", "--level", "egypt13", "--want", "kiwifruit@1-1", "--source", "wallnut=50", "--source", "wallnut=75"],
                          "two costs")

    def test_rank4_preview_text_shows_pads_spawns_and_cells(self):
        # Captured on 4.2.4: a rank-1 and a rank-4 preview with Sunflowers at cost 47 end at 4643.
        text = run("predict", "--previews", "E1,E4", "--preview-cost", "47")
        self.assertIn("3-3 deodarcedar, 3-2 beercoconut, 3-1 dmdragonfruit; pads beneath 3-1, 3-2, 3-3; spawns 4-1 cthulhuactinia, "
                      "4-2 bramble, 4-3 scaredyshroom, 5-1 streetlamp, 5-2 moonflower, 5-3 aloes (stream at 4643 after)", text)

    def test_preview_cost_reaches_previews_and_pools(self):
        # Captured on 4.2.4: three rank-1 previews with Sunflowers at cost 47 end at 3135, 6140 and 9152.
        out = json.loads(run("predict", "--previews", "E1x3", "--preview-cost", "47", "--json"))
        self.assertEqual((out["preview_cost"], [p["end"] for p in out["previews"]]), (47, [3135, 6140, 9152]))
        # After five rank-1 previews, a rank-4 preview spawns a Draftodil at 4-3 whose row shuffle of three plant objects
        # rejects one value.
        self.assertIn("draftodil at 4-3 shuffles 3 plant objects (3 draws) (selections end at 16738; stream at 16741 after)",
                      run("predict", "--previews", "E1x5,E4", "--preview-cost", "47"))
        self.assertIn("244 candidates", run("pool", "--preview", "evolution", "--cost", "47"))
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            run("predict", "--level", "dark1", "--activate", "2-2", "--previews", "E1", "--plant", "sunflower=47@1-1")
            run("predict", "--level", "dark1", "--activate", "2-2", "--plant", "sunflower=47@1-1")
            run("predict", "--level", "dark1", "--activate", "2-2", "--previews", "D1", "--plant", "sunflower=47@1-1")
        self.assertEqual(error.getvalue().count("pass --preview-cost"), 1)

    def test_devolution_previews_reach_predict_and_plan(self):
        # Captured on 4.2.4: two Devolution previews after a fresh launch drew 90 and 84 outputs, and a rank-1 preview
        # with Sunflowers at cost 37 after them ended at 3222.
        text = run("predict", "--previews", "D1x2,E1", "--preview-cost", "37")
        self.assertIn("Preview 2 (Devolution rank 1): 6 shuffles of 10 and 15 objects, 84 draws (stream at 174 after)", text)
        self.assertIn("3-1 whitemelon (stream at 3222 after)", text)
        request = ["plan", "--level", "egypt1", "--want", "chestnut@1-1", "--source", "wallnut=50", "--max-sources", "1",
                   "--max-previews", "4"]
        self.assertIn("at effective cost 50: D1,E1,E3;", run(*request))
        self.assertNotIn("D1", run(*request, "--allow", "E1,E4"))
        self.assert_error(request + ["--allow", "E1,D2"], "No measured structure for the preview 'D2'")
        self.assert_error(request + ["--allow", "E3,E4"], "None of the allowed previews E3, E4 can come first")
        self.assert_error(request + ["--done", "D1,E4"], "E4 cannot follow D1")
        self.assert_error(["predict", "--previews", "D1,E3"], "E3 cannot follow D1")

    def test_pool_listing(self):
        text = run("pool", "--level", "pirate1", "--kind", "pirate_plank", "--cost", "0")
        self.assertIn("245 candidates", text)

    def test_level_entry_shuffles_reach_the_output(self):
        # Captured on 4.2.4: Dark Ages 21 shuffles three bags of ten at entry, 42 draws from a fresh launch.
        text = run("predict", "--rank", "4", "--level", "dark21", "--activate", "2-2")
        self.assertIn("Entering the level shuffles gravestone bags of 10, 10, 10 objects (42 draws); "
                      "the activation starts at offset 42.", text)
        self.assertIn("Selection stream ends at 663.", text)
        self.assertIn("Entering the level draws nothing; the activation starts at offset 0.",
                      run("predict", "--rank", "4", "--level", "egypt13", "--activate", "2-2"))
        plan = json.loads(run("plan", "--rank", "4", "--level", "dark21", "--want", "groundcherry@1-1",
                              "--max-sources", "0", "--max-previews", "0", "--json"))
        self.assertEqual((plan["match"]["level_entry_offset"], plan["match"]["activation_offset"]), (0, 42))
        self.assertEqual([s["objects"] for s in plan["match"]["entry_effects"]], [10, 10, 10])
        self.assertIn("the activation starts at 42", run("plan", "--rank", "4", "--level", "dark21", "--want", "groundcherry@1-1",
                                                         "--max-sources", "0", "--max-previews", "0"))

    def test_model_refusals_reach_the_user_as_errors(self):
        self.assert_error(["predict", "--rank", "4", "--level", "beach3", "--activate", "5-3", "--plant", "lilypad=25@5-3"], "cannot stand on")
        self.assert_error(["plan", "--rank", "4", "--level", "beach3", "--activate", "5-3", "--want", "cactus@5-3", "--source", "puffshroom=0"],
                          "can never be placed")


if __name__ == "__main__":
    unittest.main()
