import itertools
import random
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution import Board, Game, Level, Planting, Stream, activate, load_level, scenario, search_recipe
from evolution.tiles import NONE

CAPTURED_ON = "4.2.2"  # the version whose captures fix the preview counts and offsets asserted below


class SearchTest(unittest.TestCase):
    """Every recipe must replay through `scenario` to the rows it promised, and the search must agree with a brute force."""

    @classmethod
    def setUpClass(cls):
        cls.game = Game(CAPTURED_ON)
        cls.previews = cls.game.previews

    def search(self, level, wants, sources, activation=(2, 2), **options):
        if isinstance(level, str):
            level = load_level(level)
        return search_recipe(self.game, level, wants, sources, activation, **options)

    def replay(self, level, match, activation, overrides=None, rank=1, offset=0):
        """Replay a recipe exactly as a player would follow it, and check it delivers what it promised."""
        if isinstance(level, str):
            level = load_level(level)
        plantings = [Planting(s["source"], s["cost"], s["cell"]) for s in match["planting_order"]]
        out = scenario(self.game, match["preview_sequence"], level, plantings, activation, overrides, offset, rank)
        self.assertEqual(out["level_entry_offset"], match["level_entry_offset"])
        self.assertEqual(out["stream_end"], match["stream_end"])
        keys = ("action", "cell", "result", "placed", "start", "end")
        self.assertEqual([tuple(row[k] for k in keys) for row in out["results"]],
                         [tuple(row[k] for k in keys) for row in match["processing_order"]])
        return {(row["result"], row["cell"]) for row in out["results"] if row["placed"]}

    def test_two_aeoniums_in_memory_lane(self):
        wants = [("aeonium", (1, 1)), ("aeonium", (1, 3))]
        result = self.search("memory-lane-s33-6-hard", wants, {"sunflower": 50, "puffshroom": 0}, max_previews=12)
        match = result["match"]
        self.assertIsNotNone(match)
        self.assertEqual((match["preview_sequence"], result["budget_exhausted"]), ([1] * 6, []))
        self.assertTrue(set(wants) <= self.replay("memory-lane-s33-6-hard", match, (2, 2)))
        for row in match["processing_order"]:
            self.assertEqual(row["kind"], "beach_shore" if row["cell"][0] == 3 else "ground")

    def test_counted_previews_include_placement_draws(self):
        # Captured: after ten rank-1 previews with Sunflowers at cost 47 the stream stands at 30335, two draws past
        # the tenth preview's selections. A recipe counting those previews enters the level there.
        level = load_level("arthurs-challenge")
        result = self.search(level, [("parsnip", (2, 2))], {"wallnut": 50}, min_previews=10, max_previews=10,
                             max_sources=1, preview_cost=47)
        match = result["match"]
        self.assertIsNotNone(match)
        self.assertEqual((match["level_entry_offset"], result["preview_cost"]), (30335, 47))
        plantings = [Planting(p["source"], p["cost"], p["cell"]) for p in match["planting_order"]]
        replay = scenario(self.game, match["preview_sequence"], level, plantings, (2, 2), preview_cost=47)
        self.assertEqual(replay["level_entry_offset"], 30335)
        self.assertEqual(replay["results"][0]["result"], "parsnip")

    def test_wanted_plant_on_a_plank_cell_uses_the_plank_pool(self):
        result = self.search("pirate1", [("exorcislily", (6, 4))], {"puffshroom": 0, "sunflower": 50},
                             activation=(5, 4), max_previews=20)
        match = result["match"]
        self.assertIsNotNone(match)
        wanted = next(row for row in match["processing_order"] if row["wanted"])
        self.assertEqual((wanted["cell"], wanted["kind"]), ((6, 4), "pirate_plank"))
        self.assertTrue(all(row["cell"] != (6, 3) for row in match["processing_order"]))
        self.assertIn(("exorcislily", (6, 4)), self.replay("pirate1", match, (5, 4)))

    def test_source_restricted_to_a_kind(self):
        result = self.search("memory-lane-s33-6-hard", [("aeonium", (1, 1))],
                             {"sunflower": 50, "puffshroom": (0, ["ground"])}, max_previews=12)
        self.assertIsNotNone(result["match"])
        for row in result["match"]["processing_order"]:
            if "puffshroom" in row["sources"]:
                self.assertEqual(row["kind"], "ground")

    def test_preview_prefix_then_counted_previews_of_another_rank(self):
        # One rank-1 preview then one rank-4 preview end at offset 4,292 (forecast matched on the device).
        result = self.search("egypt13", [("eagleclaw", (2, 1))], {"wallnut": 50}, prefix=[1], preview_rank=4,
                             min_previews=1, max_previews=1, max_sources=1)
        match = result["match"]
        self.assertIsNotNone(match)
        self.assertEqual((match["preview_sequence"], match["level_entry_offset"]), ([1, 4], 4292))
        self.assertIn(("eagleclaw", (2, 1)), self.replay("egypt13", match, (2, 2)))

    def test_two_tallnuts_across_ground_and_shore(self):
        # The same plant wanted on cells of two kinds from sources whose pools span both kinds.
        wants = [("tallnut", (3, 2)), ("tallnut", (4, 2))]
        for rank in (1, 4):
            with self.subTest(rank=rank):
                result = self.search("beach3", wants, {"sunflower": 50, "puffshroom": 0}, activation=(4, 2),
                                     rank=rank, min_previews=10, max_previews=10)
                self.assertIsNotNone(result["match"])
                self.assertTrue(set(wants) <= self.replay("beach3", result["match"], (4, 2), rank=rank))

    def test_mixed_wants_leave_the_spawn_cell_free(self):
        # Kiwifruit needs a transformation; Primal Wall-nut can only spawn, so 3-3 must stay free.
        wants = [("kiwifruit", (2, 1)), ("primalwallnut", (3, 3))]
        result = self.search("egypt13", wants, {"wallnut": 50}, rank=4, max_previews=0)
        match = result["match"]
        self.assertIsNotNone(match)
        self.assertEqual((match["preview_count"], match["source_count"]), (0, 8))
        self.assertTrue(set(wants) <= self.replay("egypt13", match, (2, 2), rank=4))

    def test_empty_area_and_capture_1(self):
        result = self.search("egypt13", [("whitemelon", (1, 1))], {}, rank=4, max_sources=0, max_previews=0)
        match = result["match"]
        self.assertIsNotNone(match)
        self.assertEqual((match["source_count"], match["planting_order"], match["stream_end"]), (0, [], 640))
        self.assertIn(("whitemelon", (1, 1)), self.replay("egypt13", match, (2, 2), rank=4))

    def test_lily_pad_and_an_ordinary_plant_on_one_water_cell(self):
        overrides = {(c, r): "beach_water" for c in (4, 5, 6) for r in (2, 3, 4)}
        wants = [("electricpeel", (5, 3)), ("lilypad", (5, 3))]
        result = self.search("beach3", wants, {"seashroom": (0, ["beach_water"])}, activation=(5, 3),
                             overrides=overrides, rank=4, max_sources=1, max_previews=99)
        self.assertIsNotNone(result["match"])
        self.assertTrue(set(wants) <= self.replay("beach3", result["match"], (5, 3), overrides, rank=4))

    def test_sources_that_cannot_be_planted_are_reported_not_planned(self):
        # Sea-shroom is Beach-only and Puff-shroom is banned in Egypt 13; neither is an error, neither is planned.
        result = self.search("egypt13", [("kiwifruit", (2, 1))], {"wallnut": 50, "seashroom": (0, ["beach_water"]), "puffshroom": 0},
                             max_previews=10)
        self.assertEqual(sorted(result["unusable_sources"]), ["puffshroom", "seashroom"])
        self.assertIsNotNone(result["match"])
        self.assertTrue(all(row["source"] == "wallnut" for row in result["match"]["processing_order"]))

    def test_lily_pad_beneath_an_occupied_shore_cell(self):
        # Follow-up A: a source on dry shore receives a Lily Pad beneath it for no draws.
        result = self.search("beach3", [("lilypad", (5, 3))], {"puffshroom": 0}, activation=(5, 3), rank=4, max_previews=0)
        match = result["match"]
        self.assertIsNotNone(match)
        self.assertEqual([(s["source"], s["cell"]) for s in match["planting_order"]], [("puffshroom", (5, 3))])
        self.assertIn(("lilypad", (5, 3)), self.replay("beach3", match, (5, 3), rank=4))

    def test_a_source_with_no_candidates_still_occupies_its_cell(self):
        # Winter Melon at its full cost has no dearer candidate; planted, it only shifts the spawn cells.
        result = self.search("egypt13", [("whitemelon", (1, 2))], {"wintermelon": 500}, rank=4, max_previews=0, max_sources=1)
        match = result["match"]
        self.assertIsNotNone(match)
        self.assertEqual([(s["source"], s["cell"], s["result"]) for s in match["planting_order"]], [("wintermelon", (1, 1), None)])
        self.assertIn(("whitemelon", (1, 2)), self.replay("egypt13", match, (2, 2), rank=4))

    def test_extra_offset_between_previews_and_level(self):
        # Capture 4 started at offset 2,874 after a process that had run one rank-1 preview and nothing else.
        result = self.search("egypt1", [("witchhazel", (1, 1))], {"puffshroom": 0}, activation=(2, 1), rank=4,
                             offset=2874, max_previews=0, max_sources=1)
        match = result["match"]
        self.assertIsNotNone(match)
        self.assertEqual((match["level_entry_offset"], match["stream_end"]), (2874, 3584))
        self.assertIn(("witchhazel", (1, 1)), self.replay("egypt1", match, (2, 1), rank=4, offset=2874))

    def test_impossible_wants_are_refused_with_the_rule_that_forbids_them(self):
        # Each refusal states a model rule: a Lily Pad is a kind, not a result; a want needs a source whose pool holds
        # it; one cell holds one plant; the pad beneath a rank-4 source rejects some plants; a source cannot be a
        # Lily Pad.
        cases = [
            ("egypt13", [("lilypad", (1, 1))], {"wallnut": 50}, {}, "not obtainable"),
            ("egypt13", [("kiwifruit", (1, 1)), ("eagleclaw", (1, 1))], {"wallnut": 50}, {}, "distinct cells"),
            ("egypt13", [("kiwifruit", (1, 1))], {"puffshroom": 0}, {}, "not obtainable"),
            ("beach3", [("cactus", (5, 3))], {"puffshroom": 0}, dict(activation=(5, 3), rank=4), "can never be placed"),
            ("beach3", [("celerystalker", (5, 3)), ("lilypad", (5, 3))], {"puffshroom": 0}, dict(activation=(5, 3), rank=4), "can never be placed"),
            ("beach3", [("electricpeel", (5, 3))], {"puffshroom": (0, ["beach_water"])}, dict(activation=(5, 3), rank=4,
             overrides={(5, 3): "beach_water"}), "not obtainable"),
            ("memory-lane-s33-6-hard", [("aeonium", (1, 1))], {"sunshroom": 25}, {}, "not obtainable"),
            ("beach3", [("lilypad", (5, 3))], {"lilypad": 25}, dict(activation=(5, 3), rank=4), "not a source"),
        ]
        for level, wants, sources, options, message in cases:
            with self.subTest(wants=wants, sources=sources, options=options):
                with self.assertRaisesRegex(ValueError, message):
                    self.search(level, wants, sources, **options)

    def test_search_agrees_with_a_brute_force_on_small_boards(self):
        """On tiny boards the space of routes is enumerable: the search must return the same fewest previews and sources."""
        rng = random.Random(20260923)
        stream = Stream()
        boards = [
            Level({"stage": "beach", "width": 3, "height": 1, "default_kind": "ground",
                   "cells": {"2-1": "beach_shore", "3-1": "beach_water"}}),
            Level({"stage": "beach", "width": 2, "height": 2, "default_kind": "beach_shore", "cells": {"1-1": "ground"}}),
            Level({"stage": "pirate", "width": 3, "height": 1, "default_kind": "ground",
                   "cells": {"2-1": "pirate_plank", "3-1": "none"}}),
        ]
        source_pool = {"puffshroom": 0, "sunflower": 50, "seashroom": (0, ["beach_water"]), "wintermelon": 500}
        checked = 0
        for _ in range(60):
            level, rank = rng.choice(boards), rng.choice((1, 4))
            activation = (rng.randint(1, level.width), rng.randint(1, level.height))
            board = Board(level, None, activation)
            pools = self.game.pools(level)
            usable = [cell for cell in board.area if board.kind_at(cell) != NONE]
            sources = {alias: source_pool[alias] for alias in rng.sample(sorted(source_pool), rng.randint(1, 3))}
            if rank == 1 and all(alias == "wintermelon" for alias in sources):
                continue
            truth, wants = self.brute_force(level, board, pools, usable, sources, rank, rng, stream)
            if truth is None:
                continue
            result = self.search(level, wants, sources, activation, rank=rank, max_previews=3, max_sources=len(usable))
            match = result["match"]
            self.assertIsNotNone(match, (wants, sources, rank, activation))
            self.assertEqual((match["preview_count"], match["source_count"]), truth, (wants, sources, rank, activation))
            self.assertTrue(set(wants) <= self.replay(level, match, activation, rank=rank))
            checked += 1
        self.assertGreaterEqual(checked, 25)

    def brute_force(self, level, board, pools, usable, sources, rank, rng, stream):
        """Pick wants from a random route so a recipe exists, then find the fewest previews and sources for them."""
        def allowed(alias, cell):
            spec, kind = sources[alias], board.kind_at(cell)
            return (isinstance(spec, int) or kind in spec[1]) and pools.plantable(alias, kind)

        def cost(alias):
            spec = sources[alias]
            return spec if isinstance(spec, int) else spec[0]

        def routes(count):
            _, offset = self.previews.advance(stream, 0, [1] * count, 50)
            for size in range(len(usable) + 1):
                for cells in itertools.permutations(usable, size):
                    choices = [[a for a in sources if allowed(a, cell)] for cell in cells]
                    for aliases in itertools.product(*choices):
                        plantings = [Planting(alias, cost(alias), cell) for alias, cell in zip(aliases, cells)]
                        rows, _ = activate(board, pools, plantings, rank, stream, offset)
                        yield count, size, {(row["result"], row["cell"]) for row in rows if row["placed"]}

        candidates = [placed for _, _, placed in routes(rng.randint(0, 2)) if placed]
        if not candidates:
            return None, None
        placed = rng.choice(candidates)
        wants = rng.sample(sorted(placed), min(len(placed), rng.randint(1, 2)))
        if len({cell for _, cell in wants}) != len(wants) and (rank == 1 or len(wants) != 2):
            wants = wants[:1]
        for count in range(4):
            for _, size, produced in routes(count):
                if set(wants) <= produced:
                    return (count, size), wants
        return None, None


if __name__ == "__main__":
    unittest.main()
