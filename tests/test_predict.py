from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution import Game, Planting, Stream, load_level, scenario

CAPTURED_ON = "4.2.2"


def results(rows):
    return [row["result"] for row in rows]


class PredictTest(unittest.TestCase):
    """Recorded outcomes and focused model boundaries; comments distinguish offline probes from gameplay checks."""

    @classmethod
    def setUpClass(cls):
        cls.game = Game(CAPTURED_ON)
        cls.previews = cls.game.previews

    def run_scenario(self, sequence, level, plantings, activation, overrides=None, offset=0):
        return scenario(self.game, sequence, load_level(level) if level else None, plantings, activation, overrides,
                        offset)

    def test_fresh_launch_rank1_preview(self):
        # Captured after a fresh launch: nine selections, 2,874 outputs.
        out = self.run_scenario([1], None, [], None)
        self.assertEqual(results(out["previews"][0]["results"]),
                         ["nekotail", "goldmagnet", "passionflower", "kiwifruit", "gluttonydragon",
                          "chomper", "electricitea", "agave", "duckpear"])
        self.assertEqual(out["offset_after_previews"], 2874)

    def test_discounted_previews_include_placement_draws(self):
        # Recorded consecutive previews: all sources cost 47. Draftodil's
        # placement changes the first two choices of the following preview.
        game = Game(CAPTURED_ON, preview_source_cost=47)
        out = scenario(game, [1] * 11)
        tenth, eleventh = out["previews"][9:11]
        self.assertEqual(tenth["results"][3]["result"], "draftodil")
        self.assertEqual((tenth["selection_end"], tenth["end"]), (30333, 30335))
        self.assertEqual([r["candidates"] for r in tenth["results"]], [243] * 9)
        self.assertEqual(results(eleventh["results"][:2]), ["gatlingpea", "egretflower"])
        self.assertEqual((eleventh["results"][0]["start"], eleventh["end"]), (30335, 33404))

    def test_discounted_preview_route_to_one_activation(self):
        game = Game(CAPTURED_ON, preview_source_cost=47)
        order = [("wallnut", 50, (1, 3)), ("puffshroom", 0, (1, 2)),
                 ("puffshroom", 0, (2, 1)), ("wallnut", 50, (2, 2)),
                 ("puffshroom", 0, (2, 3)), ("puffshroom", 0, (3, 1)),
                 ("puffshroom", 0, (3, 2)), ("puffshroom", 0, (1, 1)),
                 ("wallnut", 50, (3, 3))]
        out = scenario(game, [1] * 24, load_level("arthurs-challenge"),
                       [Planting(*p) for p in order], (2, 2))
        self.assertEqual(out["level_entry_offset"], 72725)
        self.assertEqual(results(out["results"]), ["fireshroom", "cthulhuactinia", "monotropa",
                         "sweetpotato", "draftodil", "nekotail", "happyleek", "paphiopedilum", "inferno"])
        # This API ends at selection, before the final activation's placement effects.
        self.assertEqual(out["stream_end"], 75697)

    def test_rank4_preview_rejects_unknown_draftodil_row_population(self):
        with self.assertRaisesRegex(ValueError, "Rank-4 preview generates Draftodil"):
            self.previews.run(Stream(), 400, 4)

    def test_preview_row_shuffle_consumes_rejected_values(self):
        # Offline probe: after selection, the first two masked values are 3
        # (rejected for a three-object row) and 2. The final swap needs one more.
        game = Game(CAPTURED_ON, preview_source_cost=47)
        rows, end = game.previews.run(Stream(), 239256, 1)
        self.assertEqual(sum(r["result"] == "draftodil" for r in rows), 1)
        self.assertEqual((rows[-1]["end"], end), (242315, 242318))

    def test_fresh_launch_egypt13_grid(self):
        # Captured twice in fresh processes: nine Wall-nuts planted 1-1 to 3-3 in order, activation at 2-2.
        cells = [(c, r) for r in (1, 2, 3) for c in (1, 2, 3)]
        out = self.run_scenario([], "egypt13", [Planting("wallnut", 50, cell) for cell in cells], (2, 2))
        self.assertEqual(results(out["results"]),
                         ["coldsnapdragon", "exorcislily", "vanilla", "wintersweet", "phatbeet",
                          "chomper", "pomegranatejeweler", "kiwifruit", "goldencassia"])
        self.assertEqual(out["stream_end"], 2874)

    def test_memory_lane_six_preview_recipe(self):
        # Forecast saved before play, then both Aeoniums appeared on the iPad. Cell 3-1 is a shore cell;
        # its own result was not checked in that run and is left out here.
        plantings = [Planting("sunflower", 50, c) for c in [(1, 3), (3, 3), (2, 3), (3, 2), (2, 2), (1, 1)]]
        plantings += [Planting("puffshroom", 0, c) for c in [(1, 2), (3, 1), (2, 1)]]
        out = self.run_scenario([1] * 6, "memory-lane-s33-6-hard", plantings, (2, 2))
        by_cell = {row["cell"]: row["result"] for row in out["results"]}
        self.assertEqual(by_cell[(1, 1)], "aeonium")
        self.assertEqual(by_cell[(1, 3)], "aeonium")
        expected = {(2, 1): "rheumnobile", (1, 2): "megagatling", (2, 2): "jewelrabbit", (3, 2): "bloominghearts",
                    (2, 3): "bubblecoral", (3, 3): "goldencassia"}
        for cell, plant in expected.items():
            self.assertEqual(by_cell[cell], plant, cell)

    def test_pennys_pursuit_27_preview_recipe(self):
        # Forecast saved before play; both Convallaria Chemists appeared on the iPad.
        plantings = [Planting("cosmicpea", 150, (1, 3)), Planting("cabbagepult", 100, (1, 2)),
                     Planting("cabbagepult", 100, (1, 1)), Planting("cabbagepult", 100, (3, 1)),
                     Planting("cactus", 175, (2, 1))]
        out = self.run_scenario([1] * 27, "pennys-pursuit-dark", plantings, (2, 2))
        # The two requested cells were verified; the other cells were forecasts.
        # Placement draws in the last preview change an unverified cell.
        by_cell = {row["cell"]: row["result"] for row in out["results"]}
        self.assertEqual(by_cell[(1, 1)], "convallariachemist")
        self.assertEqual(by_cell[(1, 3)], "convallariachemist")

    def test_beach_flooded_capture_from_offset_zero(self):
        # Captured 2026-09-19 with columns 3 and 4 under water; the stream was at offset 0.
        plantings = [Planting("sunflower", 50, (2, 1)), Planting("sunflower", 50, (2, 3)),
                     Planting("sunflower", 50, (4, 1), "beach_pad"), Planting("puffshroom", 0, (2, 2)),
                     Planting("puffshroom", 0, (3, 1), "beach_pad"), Planting("seashroom", 0, (3, 2), "beach_water")]
        out = self.run_scenario([], "memory-lane-s33-6-hard", plantings, (3, 2))
        self.assertEqual(results(out["results"]),
                         ["electricpeel", "sarracenia", "apsarlotus", "convallariachemist", "pomegranatejeweler", "sporeshroom"])
        self.assertEqual([row["candidates"] for row in out["results"]], [17, 233, 239, 213, 217, 217])
        self.assertEqual(out["stream_end"], 1557)

    def test_pirate_capture_from_offset_2667(self):
        # Captured 2026-09-19 in Pirate Seas 1 after other artifact use; the stream was at offset 2,667.
        plantings = [Planting("sunflower", 50, (5, 4)), Planting("puffshroom", 0, (5, 5)),
                     Planting("sunflower", 50, (6, 5)), Planting("puffshroom", 0, (6, 4)),
                     Planting("sunshroom", 25, (5, 3)), Planting("sunflower", 50, (4, 4)), Planting("puffshroom", 0, (4, 3))]
        out = self.run_scenario([], "pirate1", plantings, (5, 4), offset=2667)
        self.assertEqual(results(out["results"]),
                         ["ghostpepper", "lancerhoya", "thundersnapdragon", "exorcislily", "actinostemma", "maybee", "rheumnobile"])
        self.assertEqual([row["kind"] for row in out["results"]],
                         ["ground", "ground", "ground", "pirate_plank", "pirate_plank", "ground", "ground"])
        self.assertEqual(out["stream_end"], 2667 + 2276)

    def test_rank4_preview_after_one_rank1_preview(self):
        # Forecast saved before play on 2026-09-19 and matched on the device.
        out = self.run_scenario([1, 4], None, [], None)
        second = out["previews"][1]["results"]
        self.assertEqual([(row["cell"], row["result"]) for row in second if row["step"] == "evolution"],
                         [((3, 3), "pinecone"), ((3, 2), "wiregelsemium"), ((3, 1), "peach")])
        self.assertEqual([row["result"] for row in second if row["step"] == "single"], ["lilypad"] * 3)
        self.assertEqual([row["result"] for row in second if row["step"] == "spawn"],
                         ["buttercup", "icelotus", "cracker", "endurian", "streetlamp", "wallnut"])
        self.assertEqual(out["offset_after_previews"], 4292)

    def test_two_rank4_previews_and_a_third_start_from_offset_35296(self):
        # Captured 2026-09-19: two complete rank-4 previews and the three evolutions of a third,
        # 3,717 outputs, starting at offset 35,296.
        stream = Stream()
        rows, end = self.previews.advance(stream, 35296, [4, 4])
        evolved = [r["result"] for p in rows for r in p["results"] if r["step"] == "evolution"]
        self.assertEqual(evolved, ["cottonyeti", "inferno", "goldencassia", "elaeocarpus", "waxgourd", "rhubarbarian"])
        spawned = [r["result"] for p in rows for r in p["results"] if r["step"] == "spawn"]
        self.assertEqual(spawned, ["wallnut", "pineapple", "lilypad", "garlic", "guardshroom", "cosmicmushroom",
                                   "aloes", "endurian", "heavendatura", "endurian", "turnip", "cosmicmushroom"])
        self.assertEqual(end, 35296 + 2782)
        third, _ = self.previews.run(stream, end, 4)
        self.assertEqual([r["result"] for r in third if r["step"] == "evolution"], ["bowlingbulb", "chestnut", "peonychi"])
        self.assertEqual(third[2]["end"], 35296 + 3717)

    def test_pad_over_a_dry_shore_cell_played_check(self):
        # Played 2026-09-19 after a fresh launch, tide out: Puff-shrooms at 2-1, at 3-1 on bare shore, and at 3-2
        # on a Lily Pad; activation at 2-2. Reported chestnut, bloomerang, agave: the pad kind's results only.
        def play(kind):
            plantings = [Planting("puffshroom", 0, (2, 1)), Planting("puffshroom", 0, (3, 1)),
                         Planting("puffshroom", 0, (3, 2), kind)]
            out = self.run_scenario([], "memory-lane-s33-6-hard", plantings, (2, 2))
            return {row["cell"]: row["result"] for row in out["results"]}
        self.assertEqual(play("beach_pad"), {(3, 2): "agave", (3, 1): "bloomerang", (2, 1): "chestnut"})
        self.assertEqual(play("ground"), {(3, 2): "pumpkinwitch", (3, 1): "turkeypult", (2, 1): "chestnut"})
        self.assertEqual(play("beach_shore"), {(3, 2): "endurian", (3, 1): "turkeypult", (2, 1): "chestnut"})

    def test_dark_ages_1_gravestone_inside_the_area_played_check(self):
        # Played 2026-09-19 after a fresh launch: Sunflowers at 1-1, 2-1, 1-2, activation at 2-2, with the
        # level's gravestone at 3-1 inside the area. Reported passionflower, goldmagnet, nekotail.
        plantings = [Planting("sunflower", 50, cell) for cell in [(1, 1), (2, 1), (1, 2)]]
        out = self.run_scenario([], "dark1", plantings, (2, 2))
        self.assertEqual(results(out["results"]), ["nekotail", "goldmagnet", "passionflower"])
        self.assertEqual(out["stream_end"], 957)

    def test_rejects_cells_that_cannot_hold_a_plant(self):
        with self.assertRaises(ValueError):
            self.run_scenario([], "pirate1", [Planting("sunflower", 50, (6, 3))], (5, 4))
        with self.assertRaises(ValueError):
            self.run_scenario([], "egypt13", [Planting("sunflower", 50, (5, 5))], (2, 2))


if __name__ == "__main__":
    unittest.main()
