from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution import Game, Planting, Stream, load_level, scenario

CAPTURED_ON = "4.2.2"


def results(rows):
    return [row["result"] for row in rows]


def by_cell(rows):
    return {row["cell"]: row["result"] for row in rows}


class PredictTest(unittest.TestCase):
    """Every expectation below was read from the game, version CAPTURED_ON: a capture, a forecast saved before play
    and then matched, or a played check reported after play; each comment says which."""

    @classmethod
    def setUpClass(cls):
        cls.game = Game(CAPTURED_ON)
        cls.previews = cls.game.previews

    def run_scenario(self, sequence, level, plantings, activation, overrides=None, offset=0, preview_cost=None):
        return scenario(self.game, sequence, load_level(level) if level else None, plantings, activation, overrides,
                        offset, preview_cost=preview_cost)

    def test_fresh_launch_rank1_preview(self):
        # Captured after a fresh launch: nine selections, 2,874 outputs.
        out = self.run_scenario([1], None, [], None)
        self.assertEqual(results(out["previews"][0]["results"]),
                         ["nekotail", "goldmagnet", "passionflower", "kiwifruit", "gluttonydragon",
                          "chomper", "electricitea", "agave", "duckpear"])
        self.assertEqual(out["offset_after_previews"], 2874)

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
        cells = by_cell(out["results"])
        self.assertEqual(cells[(1, 1)], "aeonium")
        self.assertEqual(cells[(1, 3)], "aeonium")
        expected = {(2, 1): "rheumnobile", (1, 2): "megagatling", (2, 2): "jewelrabbit", (3, 2): "bloominghearts",
                    (2, 3): "bubblecoral", (3, 3): "goldencassia"}
        for cell, plant in expected.items():
            self.assertEqual(cells[cell], plant, cell)

    def test_pennys_pursuit_27_preview_recipe(self):
        # Forecast saved before play; both Convallaria Chemists appeared on the iPad, and only those two cells were
        # checked. The forecast omitted the row shuffles of the four Draftodils among these previews; with them the
        # stream re-aligns before the level and only the Cactus cell's result differs, which was not checked.
        plantings = [Planting("cosmicpea", 150, (1, 3)), Planting("cabbagepult", 100, (1, 2)),
                     Planting("cabbagepult", 100, (1, 1)), Planting("cabbagepult", 100, (3, 1)),
                     Planting("cactus", 175, (2, 1))]
        out = self.run_scenario([1] * 27, "pennys-pursuit-dark", plantings, (2, 2))
        cells = by_cell(out["results"])
        self.assertEqual(cells[(1, 1)], "convallariachemist")
        self.assertEqual(cells[(1, 3)], "convallariachemist")

    def test_arthurs_challenge_after_24_discounted_previews(self):
        # Captured 2026-09-24: a rank-1 activation in Arthur's Challenge after 24 reported rank-1 previews with
        # Sunflowers at effective cost 47. The nine selections and all 2,974 recorded outputs match from entry 72725,
        # which the previews reach with or without the draws of their one Draftodil (preview 10): the two routes
        # re-align by the end of preview 11. The Draftodil this activation itself creates at 2-3 drew two more
        # outputs after the selections, which `stream_end` does not include.
        order = [("wallnut", 50, (1, 3)), ("puffshroom", 0, (1, 2)),
                 ("puffshroom", 0, (2, 1)), ("wallnut", 50, (2, 2)),
                 ("puffshroom", 0, (2, 3)), ("puffshroom", 0, (3, 1)),
                 ("puffshroom", 0, (3, 2)), ("puffshroom", 0, (1, 1)),
                 ("wallnut", 50, (3, 3))]
        out = self.run_scenario([1] * 24, "arthurs-challenge", [Planting(*p) for p in order], (2, 2), preview_cost=47)
        self.assertEqual(out["level_entry_offset"], 72725)
        self.assertEqual(results(out["results"]), ["fireshroom", "cthulhuactinia", "monotropa", "sweetpotato",
                                                   "draftodil", "nekotail", "happyleek", "paphiopedilum", "inferno"])
        self.assertEqual(out["stream_end"], 75697)

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
        # Forecast saved before play on 2026-09-19 and matched on the device: the three evolutions and the six spawns
        # in order. The spawn cells were not recorded then; they follow the display-board layout captured later.
        out = self.run_scenario([1, 4], None, [], None)
        second = out["previews"][1]["results"]
        self.assertEqual([(row["cell"], row["result"]) for row in second if row["action"] == "evolve"],
                         [((3, 3), "pinecone"), ((3, 2), "wiregelsemium"), ((3, 1), "peach")])
        self.assertEqual([(row["cell"], row["result"]) for row in second if row["candidates"] == 1],
                         [((3, 1), "lilypad"), ((3, 2), "lilypad"), ((3, 3), "lilypad")])
        self.assertEqual([(row["cell"], row["result"]) for row in second if row["action"] == "spawn" and row["candidates"] > 1],
                         [((4, 1), "buttercup"), ((4, 2), "icelotus"), ((4, 3), "cracker"),
                          ((5, 1), "endurian"), ((5, 2), "streetlamp"), ((5, 3), "wallnut")])
        self.assertEqual(out["offset_after_previews"], 4292)

    def test_two_rank4_previews_and_a_third_start_from_offset_35296(self):
        # Captured 2026-09-19: two complete rank-4 previews and the three evolutions of a third,
        # 3,717 outputs, starting at offset 35,296.
        stream = Stream()
        rows, end = self.previews.advance(stream, 35296, [4, 4])
        evolved = [r["result"] for p in rows for r in p["results"] if r["action"] == "evolve"]
        self.assertEqual(evolved, ["cottonyeti", "inferno", "goldencassia", "elaeocarpus", "waxgourd", "rhubarbarian"])
        spawned = [r["result"] for p in rows for r in p["results"] if r["action"] == "spawn" and r["candidates"] > 1]
        self.assertEqual(spawned, ["wallnut", "pineapple", "lilypad", "garlic", "guardshroom", "cosmicmushroom",
                                   "aloes", "endurian", "heavendatura", "endurian", "turnip", "cosmicmushroom"])
        self.assertEqual(end, 35296 + 2782)
        third, effects, selection_end, _ = self.previews.run(stream, end, 4)
        self.assertEqual([r["result"] for r in third if r["action"] == "evolve"], ["bowlingbulb", "chestnut", "peonychi"])
        self.assertEqual(third[2]["end"], 35296 + 3717)

    def test_display_board_layout_played_check(self):
        # Played 2026-09-24 after a fresh launch with Sunflowers at cost 47: a rank-1 preview, then a rank-4 preview.
        # The screenshot showed these plants on these cells, a Lily Pad beneath each evolved plant, and nothing else.
        out = self.run_scenario([1, 4], None, [], None, preview_cost=47)
        second = out["previews"][1]["results"]
        self.assertEqual([(row["cell"], row["result"]) for row in second if row["action"] == "evolve"],
                         [((3, 3), "exorcislily"), ((3, 2), "mulberry"), ((3, 1), "bonkchoy")])
        self.assertEqual([(row["cell"], row["result"]) for row in second if row["action"] == "spawn"],
                         [((3, 1), "lilypad"), ((3, 2), "lilypad"), ((3, 3), "lilypad"), ((4, 1), "streetlamp"),
                          ((4, 2), "wallnut"), ((4, 3), "scaredyshroom"), ((5, 1), "vanilla"), ((5, 2), "dragonroar"),
                          ((5, 3), "alarmsagittifolia")])

    def test_spawned_draftodil_effect_played_check(self):
        # Played 2026-09-24 after a fresh launch at cost 47, ranks 1,1,1,1,4,4,4,1. Preview 7 showed a bare Lily Pad
        # at 3-2, whose pad rejects jewelrabbit, and preview 8 showed rheumnobile at 5-3: the result of one draw,
        # because the spawned Draftodil at 5-3 was added first, when its row held only the source and itself.
        out = self.run_scenario([1, 1, 1, 1, 4, 4, 4, 1], None, [], None, preview_cost=47)
        seventh = out["previews"][6]
        evolved = {row["cell"]: (row["result"], row["placed"]) for row in seventh["results"] if row["action"] == "evolve"}
        self.assertEqual(evolved, {(3, 3): ("dartichoke", True), (3, 2): ("jewelrabbit", False), (3, 1): ("sugarcane", True)})
        self.assertEqual([(row["cell"], row["result"]) for row in seventh["results"] if row["candidates"] == 1],
                         [((3, 1), "lilypad"), ((3, 2), "lilypad"), ((3, 3), "lilypad")])
        self.assertEqual((seventh["results"][-1]["cell"], seventh["results"][-1]["result"]), ((5, 3), "draftodil"))
        self.assertEqual(seventh["effects"], [{"action": "shuffle", "plant": "draftodil", "cell": (5, 3), "objects": 2,
                                               "start": 16513, "end": 16514}])
        self.assertEqual(by_cell(out["previews"][7]["results"])[(5, 3)], "rheumnobile")

    def test_rank1_rows_one_and_two_played_checks(self):
        # Played 2026-09-24 after fresh launches at cost 47. Ranks 1,1,1,1,1,4,1,1,1,1: preview 9 evolved a Draftodil
        # at 3-1 and preview 10 showed dendrobiumguard at 5-3. Ranks 1,1,1,4,4,1,4,4,1,1,1,1: preview 11 evolved a
        # Draftodil at 4-2 and preview 12 showed darkmatter_dragonfruit at 5-3. Each is the result of two draws,
        # three objects in the row.
        out = self.run_scenario([1, 1, 1, 1, 1, 4, 1, 1, 1, 1], None, [], None, preview_cost=47)
        self.assertEqual(out["previews"][8]["effects"], [{"action": "shuffle", "plant": "draftodil", "cell": (3, 1),
                                                          "objects": 3, "start": 25797, "end": 25799}])
        self.assertEqual(by_cell(out["previews"][9]["results"])[(5, 3)], "dendrobiumguard")
        out = self.run_scenario([1, 1, 1, 4, 4, 1, 4, 4, 1, 1, 1, 1], None, [], None, preview_cost=47)
        self.assertEqual(out["previews"][10]["effects"], [{"action": "shuffle", "plant": "draftodil", "cell": (4, 2),
                                                           "objects": 3, "start": 27173, "end": 27175}])
        self.assertEqual(by_cell(out["previews"][11]["results"])[(5, 3)], "darkmatter_dragonfruit")

    def test_pad_over_a_dry_shore_cell_played_check(self):
        # Played 2026-09-19 after a fresh launch, tide out: Puff-shrooms at 2-1, at 3-1 on bare shore, and at 3-2
        # on a Lily Pad; activation at 2-2. Reported chestnut, bloomerang, agave: the pad kind's results only.
        def play(kind):
            plantings = [Planting("puffshroom", 0, (2, 1)), Planting("puffshroom", 0, (3, 1)),
                         Planting("puffshroom", 0, (3, 2), kind)]
            out = self.run_scenario([], "memory-lane-s33-6-hard", plantings, (2, 2))
            return by_cell(out["results"])
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
