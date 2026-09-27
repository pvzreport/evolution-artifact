from collections import Counter
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution import Game, Planting, Stream, enter_level, load_level, placement_draws, scenario

CAPTURED_ON = "4.2.4"


def by_cell(rows):
    return {row["cell"]: row["result"] for row in rows}


class LevelEntryTest(unittest.TestCase):
    """Entering a level whose wave list references gravestone-spawning wave actions shuffles each action's bag once,
    in wave order, with the shared engine; a level whose definition declares none consumes nothing. Every expectation
    below was read from the game, version CAPTURED_ON unless stated: three fresh-launch activations in Dark Ages 21
    and 19 whose recordings also hold the entry outputs, the entry outputs of two earlier Dark Ages 4 recordings, and
    a recipe planned for Arthur's Challenge, which has no such action, played as written."""

    @classmethod
    def setUpClass(cls):
        cls.game = Game(CAPTURED_ON)

    def test_entry_bags_consume_the_recorded_outputs(self):
        # Dark Ages 21 (bags 10, 10, 10) drew 42 outputs from offset 0; Dark Ages 19 (bags 3, 6, 3) drew 10 from 0 and
        # 9 from 4643, the same bags consuming a different count at another position; Dark Ages 4 (bags 3, 3, 4) drew 8.
        self.assertEqual(load_level("dark21").entry_shuffles, [10, 10, 10])
        self.assertEqual(load_level("dark19").entry_shuffles, [3, 6, 3])
        self.assertEqual(load_level("dark4").entry_shuffles, [3, 3, 4])
        for level, offset, draws in (("dark21", 0, 42), ("dark19", 0, 10), ("dark19", 4643, 9), ("dark4", 0, 8)):
            with self.subTest(level=level, offset=offset):
                effects, end = enter_level(load_level(level), Stream(), offset)
                self.assertEqual(end - offset, draws)
                self.assertEqual(sum(e["end"] - e["start"] for e in effects), draws)
        self.assertEqual(enter_level(load_level("egypt13"), Stream(), 0), ([], 0))

    def test_dark_ages_4_entry_explains_the_gap_between_two_captures(self):
        # Captured on 4.2.2: in one process, a Pirate Seas 2 activation ended at 5269 and the next capture, in Dark Ages 4,
        # began at 5279 with ten unrecorded outputs between them. Entering Dark Ages 4 at 5269 draws exactly those ten,
        # and only the declared bag order does; the four spawns then replay to 5569.
        out = scenario(Game("4.2.2"), [], load_level("dark4"), [], (9, 3), offset=5269, rank=4)
        self.assertEqual((out["level_entry_offset"], out["activation_offset"], out["stream_end"]), (5269, 5279, 5569))
        self.assertEqual([row["result"] for row in out["results"]], ["levitater", "burdockbatter", "icelotus", "marigold"])

    def test_dark_ages_21_rank4_spawns_after_the_entry(self):
        # Captured: fresh launch, no previews, Wall-nuts outside the empty 1-1 to 3-3 area, rank 4 at 2-2. The nine
        # spawns start at 42 and end at 663; one plant appeared twice in the pass.
        out = scenario(self.game, [], load_level("dark21"), [], (2, 2), rank=4)
        self.assertEqual((out["level_entry_offset"], out["activation_offset"], out["stream_end"]), (0, 42, 663))
        self.assertEqual([e["objects"] for e in out["entry_effects"]], [10, 10, 10])
        self.assertEqual(by_cell(out["results"]), {
            (1, 1): "groundcherry", (1, 2): "devilsflower", (1, 3): "kernelpult", (2, 1): "peashooter",
            (2, 2): "gravitree", (2, 3): "groundcherry", (3, 1): "cosmicsaucer", (3, 2): "ents", (3, 3): "aloes"})
        self.assertEqual({row["candidates"] for row in out["results"]}, {53})

    def test_dark_ages_19_after_two_previews_with_a_draftodil_row(self):
        # Captured: a rank-1 preview and a rank-4 preview with Sunflowers at cost 47 (ending at 4643), then the level,
        # Puff-shrooms at 4-4 and 6-4 in row 4 and at 4-3 and 5-5, then Puff-shrooms at 3-4, 2-4, 2-5, 3-3, 3-5 in that
        # order, rank 1 at 2-4. The entry drew 9 outputs; the Draftodil placed at 3-4 shuffled four plant objects, the
        # two sources and the two Puff-shrooms outside the 3x3 in its row, at positions 6407 to 6410.
        plantings = [Planting("puffshroom", 0, cell) for cell in [(3, 4), (2, 4), (2, 5), (3, 3), (3, 5)]]
        out = scenario(self.game, [1, 4], load_level("dark19"), plantings, (2, 4), preview_cost=47)
        self.assertEqual((out["offset_after_previews"], out["activation_offset"], out["stream_end"]), (4643, 4652, 6407))
        self.assertEqual([row["result"] for row in out["results"]],
                         ["nukelauncher", "electriccurrant", "cosmicnut", "pamegranate", "draftodil"])
        self.assertEqual({row["candidates"] for row in out["results"]}, {251})
        effects, end = placement_draws(out["results"], Counter({3: 3, 4: 4, 5: 4, 1: 1}), Stream(), out["stream_end"])
        self.assertEqual(effects, [{"action": "shuffle", "plant": "draftodil", "cell": (3, 4), "objects": 4,
                                    "start": 6407, "end": 6411}])
        self.assertEqual(end, 6411)

    def test_dark_ages_19_protected_plants_inside_the_area(self):
        # Captured: fresh launch, Puff-shrooms at 5-3 then 7-3 on either side of the level's protected Magnet-shroom at
        # 6-3, rank 1 at 6-4, so the protected Magnet-shrooms at 6-3 and 6-5 stood inside the 3x3. Only the two
        # Puff-shrooms were evolved, from 10 to 684; the description keeps those cells as ones no source can occupy.
        level = load_level("dark19")
        plantings = [Planting("puffshroom", 0, (5, 3)), Planting("puffshroom", 0, (7, 3))]
        out = scenario(self.game, [], level, plantings, (6, 4))
        self.assertEqual((out["activation_offset"], out["stream_end"]), (10, 684))
        self.assertEqual(by_cell(out["results"]), {(7, 3): "wintersweet", (5, 3): "akee"})
        with self.assertRaisesRegex(ValueError, "cannot hold a plant"):
            scenario(self.game, [], level, plantings + [Planting("magnetshroom", 100, (6, 3))], (6, 4))

    def test_arthurs_challenge_planned_recipe_starts_where_the_previews_end(self):
        # Forecast by `plan` before play (two Draftodils wanted at 1-1 and 1-2) and matched in the game: three rank-1
        # previews with Sunflowers at cost 47, then Arthur's Challenge, whose definition declares no gravestone action,
        # so the recording holds no output between the previews and the first level selection and the activation
        # starts at 9152, where the previews end; then the seven sources in this order and rank 1 at 2-2. All 34
        # selections matched, and so did the add order and the two Draftodils' row shuffles: one output for the 1-1
        # Draftodil, whose row held it and the source still standing at 3-1, and two for the 1-2 Draftodil in a row of
        # three. Outputs from outside the artifact followed a few seconds after the effects.
        order = [("wallnut", 50, (1, 1)), ("wallnut", 50, (2, 2)), ("puffshroom", 0, (2, 3)), ("puffshroom", 0, (3, 1)),
                 ("puffshroom", 0, (1, 2)), ("peashooter", 100, (3, 2)), ("puffshroom", 0, (3, 3))]
        plantings = [Planting(*p) for p in order]
        out = scenario(self.game, [1, 1, 1], load_level("arthurs-challenge"), plantings, (2, 2), preview_cost=47)
        self.assertEqual([p["end"] for p in out["previews"]], [3135, 6140, 9152])
        self.assertEqual(sum(len(p["effects"]) for p in out["previews"]), 0)
        self.assertEqual((out["level_entry_offset"], out["entry_effects"], out["activation_offset"]), (9152, [], 9152))
        self.assertEqual([(row["cell"], row["result"], row["candidates"]) for row in out["results"]],
                         [((3, 3), "lotusshooter", 251), ((3, 2), "actinostemma", 198), ((1, 2), "draftodil", 251),
                          ((3, 1), "guardshroom", 251), ((2, 3), "coconutcannon", 251), ((2, 2), "peonychi", 227),
                          ((1, 1), "draftodil", 227)])
        self.assertEqual(out["stream_end"], 11455)
        effects, end = placement_draws(out["results"], Counter(p.cell[1] for p in plantings), Stream(), out["stream_end"])
        self.assertEqual([(e["cell"], e["objects"], e["start"], e["end"]) for e in effects],
                         [((1, 1), 2, 11455, 11456), ((1, 2), 3, 11456, 11458)])
        self.assertEqual(end, 11458)


if __name__ == "__main__":
    unittest.main()
