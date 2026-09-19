import contextlib
import io
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


if __name__ == "__main__":
    unittest.main()
