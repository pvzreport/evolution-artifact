import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution.cli import main


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main(list(argv))
    return out.getvalue()


class CliTest(unittest.TestCase):
    def assert_cli_error(self, argv, message):
        error = io.StringIO()
        with contextlib.redirect_stderr(error), self.assertRaises(SystemExit) as raised:
            run(*argv)
        self.assertEqual(raised.exception.code, 2)
        self.assertIn(message, error.getvalue())

    def test_misspelled_sources_and_kinds_are_rejected(self):
        self.assert_cli_error(["predict", "--level", "egypt1", "--activate", "1-1",
                               "--plant", "puffshrom=0@1-1"], "Unknown source plant")
        self.assert_cli_error(["plan", "--level", "egypt1", "--want", "kiwifruit@1-1",
                               "--source", "puffshroom=0:groudn"], "Unknown source kind")

    def test_non_string_level_kind_is_a_cli_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "level.json"
            path.write_text(json.dumps({"stage": "egypt", "cells": {"1-1": []}}))
            self.assert_cli_error(["predict", "--rank", "4", "--level", str(path), "--activate", "1-1"],
                                  "Cell kind at 1-1 must be a string")

    def test_rank4_source_limit_below_required_transformations_is_rejected(self):
        self.assert_cli_error(["plan", "--rank", "4", "--level", "egypt1", "--want", "kiwifruit@1-1",
                               "--source", "wallnut=50", "--max-sources", "0"], "max_sources must be at least 1")

    def test_predict_previews_only(self):
        text = run("predict", "--previews", "1,4")
        self.assertIn("pinecone", text)
        self.assertIn("buttercup", text)

    def test_predict_level_with_cell_kinds(self):
        text = run("predict", "--level", "memory-lane-s33-6-hard", "--activate", "3-2",
                   "--plant", "sunflower=50@2-1", "--plant", "seashroom=0@3-2:beach_water")
        self.assertIn("beach_water", text)
        self.assertIn("17 candidates", text)

    def test_plan_prints_a_recipe(self):
        text = run("plan", "--level", "egypt13", "--want", "kiwifruit@2-1", "--source", "wallnut=50", "--max-previews", "10")
        self.assertIn("Fully quit and relaunch", text)
        self.assertIn("kiwifruit", text)

    def test_pool_listing(self):
        text = run("pool", "--level", "pirate1", "--kind", "pirate_plank", "--cost", "0")
        self.assertIn("242 candidates", text)

    def test_rank4_empty_corner_prediction_and_recipe(self):
        result = json.loads(run("predict", "--rank", "4", "--level", "egypt1", "--activate", "1-1", "--json"))
        self.assertEqual([row["cell"] for row in result["results"]], [[1, 1], [1, 2], [2, 1], [2, 2]])
        text = run("plan", "--rank", "4", "--level", "egypt13", "--want", "whitemelon@1-1",
                   "--max-sources", "0", "--max-previews", "0")
        self.assertIn("leave the activation area empty", text)
        self.assertIn("rank-4 Evolution", text)


if __name__ == "__main__":
    unittest.main()
