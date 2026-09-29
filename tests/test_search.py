import itertools
import random
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from unittest import mock

from evolution import Board, Level, Planting, Stream, activate, advance, load_level, scenario, search_recipe, shared
from evolution import search as search_module
from evolution.route import LevelStep, as_step, run_step, step_name
from evolution.tiles import NONE
from projections import game_on

# The version whose captures fix the preview counts and offsets asserted below. The route cases show the properties
# their comments name with this version's plant data, not all of them with 4.2.4's.
CAPTURED_ON = "4.2.2"


class SearchTest(unittest.TestCase):
    """Every recipe must replay through `scenario` to the rows it promised, and the search must agree with brute forces
    over plantings and over routes."""

    @classmethod
    def setUpClass(cls):
        cls.game = game_on(CAPTURED_ON)
        cls.previews = cls.game.previews

    def search(self, level, wants, sources, activation=(2, 2), **options):
        if isinstance(level, str):
            level = load_level(level)
        return search_recipe(self.game, level, wants, sources, activation, **options)

    def replay(self, level, match, activation, overrides=None, rank=1, offset=0, preview_cost=None):
        """Replay a recipe exactly as a player would follow it, and check it delivers what it promised."""
        if isinstance(level, str):
            level = load_level(level)
        plantings = [Planting(s["source"], s["cost"], s["cell"]) for s in match["planting_order"]]
        out = scenario(self.game, match["route"], level, plantings, activation, overrides, offset, rank,
                       preview_cost=preview_cost)
        self.assertEqual((out["level_entry_offset"], out["activation_offset"], out["entry_effects"]),
                         (match["level_entry_offset"], match["activation_offset"], match["entry_effects"]))
        self.assertEqual(out["stream_end"], match["stream_end"])
        keys = ("action", "cell", "result", "placed", "start", "end")
        self.assertEqual([tuple(row[k] for k in keys) for row in out["results"]],
                         [tuple(row[k] for k in keys) for row in match["processing_order"]])
        return {(row["result"], row["cell"]) for row in out["results"] if row["placed"]}

    def test_two_aeoniums_in_memory_lane(self):
        wants = [("aeonium", (1, 1)), ("aeonium", (1, 3))]
        result = self.search("memory-lane-s33-6-hard", wants, {"sunflower": 50, "puffshroom": 0}, max_length=12)
        match = result["match"]
        self.assertIsNotNone(match)
        self.assertEqual((match["route"], result["state_cap_reached"]), ([1] * 6, []))
        self.assertTrue(set(wants) <= self.replay("memory-lane-s33-6-hard", match, (2, 2)))
        for row in match["processing_order"]:
            self.assertEqual(row["kind"], "beach_shore" if row["cell"][0] == 3 else "ground")

    def test_recipes_start_after_the_level_entry(self):
        # Dark Ages 19 shuffles bags of 3, 6 and 3 at entry; a recipe found after previews and extra outputs must start
        # where those shuffles end and replay from there through the route a player follows, here one with a rank-3
        # preview.
        result = self.search("dark19", [("draftodil", (2, 4))], {"puffshroom": 0, "wallnut": 50}, activation=(2, 4),
                             done=[1], max_length=3, max_sources=6, offset=3, preview_cost=47)
        match = result["match"]
        self.assertIsNotNone(match)
        self.assertEqual((match["route"], match["source_count"], match["level_entry_offset"], match["activation_offset"]),
                         ([1, 3], 5, 4137, 4148))
        self.assertEqual([e["objects"] for e in match["entry_effects"]], [3, 6, 3])
        self.assertEqual(match["processing_order"][0]["start"], match["activation_offset"])
        self.assertIn(("draftodil", (2, 4)), self.replay("dark19", match, (2, 4), offset=3, preview_cost=47))

    def test_done_previews_include_placement_draws(self):
        # Captured: after ten rank-1 previews with Sunflowers at cost 47 the stream stands at 30335, two draws past
        # the tenth preview's selections. A recipe after those previews enters the level there.
        level = load_level("arthurs-challenge")
        result = self.search(level, [("parsnip", (2, 2))], {"wallnut": 50}, done=[1] * 10, max_length=0,
                             max_sources=1, preview_cost=47)
        match = result["match"]
        self.assertIsNotNone(match)
        self.assertEqual((match["level_entry_offset"], result["preview_cost"]), (30335, 47))
        plantings = [Planting(p["source"], p["cost"], p["cell"]) for p in match["planting_order"]]
        replay = scenario(self.game, match["route"], level, plantings, (2, 2), preview_cost=47)
        self.assertEqual(replay["level_entry_offset"], 30335)
        self.assertEqual(replay["results"][0]["result"], "parsnip")

    def test_wanted_plant_on_a_plank_cell_uses_the_plank_pool(self):
        result = self.search("pirate1", [("exorcislily", (6, 4))], {"puffshroom": 0, "sunflower": 50},
                             activation=(5, 4), max_length=20)
        match = result["match"]
        self.assertIsNotNone(match)
        wanted = next(row for row in match["processing_order"] if row["wanted"])
        self.assertEqual((wanted["cell"], wanted["kind"]), ((6, 4), "pirate_plank"))
        self.assertTrue(all(row["cell"] != (6, 3) for row in match["processing_order"]))
        self.assertIn(("exorcislily", (6, 4)), self.replay("pirate1", match, (5, 4)))

    def test_source_restricted_to_a_kind(self):
        result = self.search("memory-lane-s33-6-hard", [("aeonium", (1, 1))],
                             {"sunflower": 50, "puffshroom": (0, ["ground"])}, max_length=12)
        self.assertIsNotNone(result["match"])
        for row in result["match"]["processing_order"]:
            if "puffshroom" in row["sources"]:
                self.assertEqual(row["kind"], "ground")

    def test_done_previews_of_both_ranks(self):
        # One rank-1 preview then one rank-4 preview end at offset 4,292 (forecast matched in the game).
        result = self.search("egypt13", [("eagleclaw", (2, 1))], {"wallnut": 50}, done=[1, 4], max_length=0, max_sources=1)
        match = result["match"]
        self.assertIsNotNone(match)
        self.assertEqual((match["route"], match["planned_steps"], match["level_entry_offset"]), ([1, 4], [], 4292))
        self.assertIn(("eagleclaw", (2, 1)), self.replay("egypt13", match, (2, 2)))

    def test_two_tallnuts_across_ground_and_shore(self):
        # The same plant wanted on cells of two kinds from sources whose pools span both kinds.
        wants = [("tallnut", (3, 2)), ("tallnut", (4, 2))]
        for rank in (1, 4):
            with self.subTest(rank=rank):
                result = self.search("beach3", wants, {"sunflower": 50, "puffshroom": 0}, activation=(4, 2),
                                     rank=rank, done=[1] * 10, max_length=0)
                self.assertIsNotNone(result["match"])
                self.assertTrue(set(wants) <= self.replay("beach3", result["match"], (4, 2), rank=rank))

    def test_mixed_wants_leave_the_spawn_cell_free(self):
        # Kiwifruit needs a transformation; Primal Wall-nut can only spawn, so 3-3 must stay free.
        wants = [("kiwifruit", (2, 1)), ("primalwallnut", (3, 3))]
        result = self.search("egypt13", wants, {"wallnut": 50}, rank=4, max_length=0)
        match = result["match"]
        self.assertIsNotNone(match)
        self.assertEqual((match["route"], match["source_count"]), ([], 8))
        self.assertTrue(set(wants) <= self.replay("egypt13", match, (2, 2), rank=4))

    def test_empty_area_and_capture_1(self):
        result = self.search("egypt13", [("whitemelon", (1, 1))], {}, rank=4, max_sources=0, max_length=0)
        match = result["match"]
        self.assertIsNotNone(match)
        self.assertEqual((match["source_count"], match["planting_order"], match["stream_end"]), (0, [], 640))
        self.assertIn(("whitemelon", (1, 1)), self.replay("egypt13", match, (2, 2), rank=4))

    def test_lily_pad_and_an_ordinary_plant_on_one_water_cell(self):
        overrides = {(c, r): "beach_water" for c in (4, 5, 6) for r in (2, 3, 4)}
        wants = [("electricpeel", (5, 3)), ("lilypad", (5, 3))]
        result = self.search("beach3", wants, {"seashroom": (0, ["beach_water"])}, activation=(5, 3),
                             overrides=overrides, rank=4, max_sources=1, max_length=99)
        self.assertIsNotNone(result["match"])
        self.assertTrue(set(wants) <= self.replay("beach3", result["match"], (5, 3), overrides, rank=4))

    def test_sources_that_cannot_be_planted_are_reported_not_planned(self):
        # Sea-shroom is Beach-only and Puff-shroom is banned in Egypt 13; neither is an error, neither is planned.
        result = self.search("egypt13", [("kiwifruit", (2, 1))], {"wallnut": 50, "seashroom": (0, ["beach_water"]), "puffshroom": 0},
                             max_length=10)
        self.assertEqual(sorted(result["unusable_sources"]), ["puffshroom", "seashroom"])
        self.assertIsNotNone(result["match"])
        self.assertTrue(all(row["source"] == "wallnut" for row in result["match"]["processing_order"]))

    def test_lily_pad_beneath_an_occupied_shore_cell(self):
        # Follow-up A: a source on dry shore receives a Lily Pad beneath it for no draws.
        result = self.search("beach3", [("lilypad", (5, 3))], {"puffshroom": 0}, activation=(5, 3), rank=4, max_length=0)
        match = result["match"]
        self.assertIsNotNone(match)
        self.assertEqual([(s["source"], s["cell"]) for s in match["planting_order"]], [("puffshroom", (5, 3))])
        self.assertIn(("lilypad", (5, 3)), self.replay("beach3", match, (5, 3), rank=4))

    def test_a_source_with_no_candidates_still_occupies_its_cell(self):
        # Winter Melon at its full cost has no dearer candidate; planted, it only shifts the spawn cells.
        result = self.search("egypt13", [("whitemelon", (1, 2))], {"wintermelon": 500}, rank=4, max_length=0, max_sources=1)
        match = result["match"]
        self.assertIsNotNone(match)
        self.assertEqual([(s["source"], s["cell"], s["result"]) for s in match["planting_order"]], [("wintermelon", (1, 1), None)])
        self.assertIn(("whitemelon", (1, 2)), self.replay("egypt13", match, (2, 2), rank=4))

    def test_extra_offset_between_previews_and_level(self):
        # Capture 4 started at offset 2,874 after a process that had run one rank-1 preview and nothing else.
        result = self.search("egypt1", [("witchhazel", (1, 1))], {"puffshroom": 0}, activation=(2, 1), rank=4,
                             offset=2874, max_length=0, max_sources=1)
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

    def test_each_artifact_starts_with_its_rank_1_preview(self):
        # Tapping an artifact plays its rank-1 preview, so previews run since a restart cannot begin with rank 4, and the
        # Evolution previews after a Devolution preview start again with rank 1. A prediction refuses such a sequence as
        # a search does, and a search refuses allowed previews that can never start its route.
        request = ("egypt13", [("eagleclaw", (2, 1))], {"wallnut": 50})
        for done in ([4, 1], ["D1", 4], [1, "D1", 3]):
            with self.subTest(done=done):
                with self.assertRaisesRegex(ValueError, "cannot"):
                    self.search(*request, done=done)
                with self.assertRaisesRegex(ValueError, "cannot"):
                    scenario(self.game, done)
        for done, allowed in (([], [3, 4]), (["D1"], [3, 4])):
            with self.subTest(done=done, allowed=allowed), self.assertRaisesRegex(ValueError, "None of the allowed"):
                self.search(*request, done=done, allowed=allowed)
        for done in (["D1", 1, 4], [1, 4, "D1", "D1", 1, 3]):
            with self.subTest(done=done):
                self.search(*request, done=done, max_length=0)

    def test_a_level_step_is_planned_only_when_allowed_and_established(self):
        # From a fresh launch, a level step in Egypt 6 on 9-1 ends at 209, where Egypt 1's spawn pass at 2-2 puts Ice
        # Lotus on 1-1 and Levitater on 1-2, and no route of up to 25 rank-1 previews does. A level step is as long as 25
        # previews, so allowed with rank-1 previews it is the route; not allowed, there is none.
        egypt1 = load_level("egypt1")
        wants = [("icelotus", (1, 1)), ("levitater", (1, 2))]
        options = dict(rank=4, max_sources=0, max_length=25, style="shorter")
        match = self.search(egypt1, wants, {}, allowed=[1, "egypt6@9-1"], **options)["match"]
        self.assertEqual((match["route"], match["planned_steps"], match["switches"]), (["egypt6@9-1"], ["egypt6@9-1"], 1))
        self.assertTrue(set(wants) <= self.replay(egypt1, match, (2, 2), rank=4))
        self.assertIsNone(self.search(egypt1, wants, {}, allowed=[1], **options)["match"])
        # Dark Ages 19 at 6-4 spawns a Draftodil from a fresh launch. Where its row shuffle would leave the stream, at
        # 530, Egypt 1 spawns Devil's flower on 1-1 and White Melon on 1-2, but the Draftodil's attack is not modelled,
        # so the step is never taken there: the search stays at the one position a route without it reaches.
        wants = [("devilsflower", (1, 1)), ("whitemelon", (1, 2))]
        self.assertIsNotNone(self.search(egypt1, wants, {}, offset=530, **dict(options, max_length=0))["match"])
        result = self.search(egypt1, wants, {}, allowed=["dark19@6-4"], **options)
        self.assertEqual((result["match"], result["entry_positions_searched"]), (None, 1))
        with self.assertRaisesRegex(ValueError, "after the done step 1, dark19@6-4, is not established"):
            self.search(egypt1, wants, {}, done=["dark19@6-4"], **dict(options, max_length=0))

    def test_a_search_stopped_by_the_state_cap_is_reported(self):
        # Two Kernel-pults at this entry need seven sources. The start is a stored state, so with room for two the
        # search stores one one-source sequence and stops at the second: the entry is listed with the number of sources
        # among whose recipes it stopped, and no recipe is claimed there.
        wants, sources = [("kernelpult", (1, 1)), ("kernelpult", (3, 3))], {"wallnut": 50, "puffshroom": 0}
        full = self.search("egypt1", wants, sources, max_length=0, offset=13958)
        capped = self.search("egypt1", wants, sources, max_length=0, offset=13958, max_states=2)
        self.assertEqual((full["match"]["source_count"], full["state_cap_reached"]), (7, []))
        self.assertIsNone(capped["match"])
        self.assertEqual(capped["state_cap_reached"], [{"route": [], "level_entry_offset": 13958,
                                                        "activation_offset": 13958, "sources": 1}])

    def test_the_preview_cost_is_a_condition_only_of_routes_with_previews(self):
        # A recipe whose route has no previews does not depend on the previews' cost; without a recipe, the cost is
        # stated whenever the search planned previews.
        line = "The previews' sunflower sources have effective cost 50."
        aeoniums = [("aeonium", (1, 1)), ("aeonium", (1, 3))], {"sunflower": 50, "puffshroom": 0}
        three = [("kernelpult", (1, 1)), ("peashooter", (2, 2)), ("burdockbatter", (3, 3))], {}
        cases = [
            (self.search("memory-lane-s33-6-hard", *aeoniums, max_length=12), True),
            (self.search("egypt13", [("whitemelon", (1, 1))], {}, rank=4, max_sources=0, max_length=3), False),
            (self.search("egypt1", *three, rank=4, max_sources=0, max_length=2), True),
            (self.search("egypt1", *three, rank=4, max_sources=0, max_length=0), False),
        ]
        for result, stated in cases:
            with self.subTest(match=result["match"] and result["match"]["route"], max_length=result["max_length"]):
                self.assertEqual(line in result["conditions"], stated)

    def test_routes_agree_with_a_brute_force_over_every_route(self):
        """Every route of up to a few previews is searched on its own. For each style, the route search must return the
        shortest allowed route with a recipe, then the fewest sources, the fewest switches and the first in preview
        order, with that route's own recipe, and must search each position the allowed routes reach once."""
        aeoniums = ("memory-lane-s33-6-hard", [("aeonium", (1, 1)), ("aeonium", (1, 3))], {"sunflower": 50, "puffshroom": 0}, (2, 2))
        kernelpults = ("beach3", [("kernelpult", (3, 1)), ("kernelpult", (5, 3))], {"wallnut": 50, "puffshroom": 0}, (4, 2))
        starfruit = ("pirate1", [("starfruit", (5, 1))], {"wallnut": 50}, (6, 2))
        evolution, every = [1, 4], [1, 3, 4, "D1"]
        cases = [
            (aeoniums, 1, [], evolution, 6, 9),  # the styles differ in length, and switches decide the simple route
            (aeoniums, 1, [1, 4], evolution, 4, 9),  # switches count from the last done preview
            (kernelpults, 4, [], evolution, 6, 9),  # routes of the shortest length differ in switches
            (kernelpults, 1, [], evolution, 5, 9),  # no recipe within the limit
            (("pirate1", [("aeonium", (6, 1))], {"wallnut": 50, "puffshroom": 0, "potatomine": 25}, (6, 2)), 1, [1], evolution, 4, 5),
            (starfruit, 1, [1, 4], evolution, 4, 6),
            # In the last two, fewer sources outweigh a switch, and one switch beats three on a route first in preview
            # order. With every preview, 3,4,D1 beats the simple style's 4,1,1,1 by a preview:
            (starfruit, 1, [1, 4], every, 4, 6),
            (aeoniums, 1, ["D1"], every, 4, 9),  # switches count from a done D1: D1,1,3 makes two
            # 3,D1,1 would be first, but a route cannot start with rank 3:
            (("egypt1", [("chestnut", (1, 1))], {"wallnut": 50}, (2, 2)), 1, [], every, 3, 1),
            # D1,4 would be first, but rank 4 cannot follow D1, and no route within the limit has a recipe:
            (("egypt1", [("broccoli", (1, 1))], {"wallnut": 50}, (2, 2)), 1, [], every, 3, 1),
            # one rank-3 preview after the done D1 would have a recipe, but rank 3 cannot follow D1:
            (("egypt1", [("iceshroom", (1, 1))], {"wallnut": 50}, (2, 2)), 1, ["D1"], every, 3, 1),
            # routes still rank in preview order when --allow lists the previews in another order and leaves out the
            # last done one: 1,D1 comes before D1,1
            (("egypt1", [("tuliptrumpeter", (1, 1))], {"wallnut": 50, "puffshroom": 0}, (2, 2)), 1, [1, 3], ["D1", 4, 1], 2, 2),
            # D4,D4,D4 would be first, but D4 needs a Devolution preview before it; 1,D1,1 is
            (("egypt1", [("snapdragon", (1, 1))], {"wallnut": 50}, (2, 2)), 1, [], every + ["D4"], 3, 1),
            (("egypt1", [("aloes", (1, 1))], {"wallnut": 50}, (2, 2)), 1, [], every + ["D4"], 3, 1),  # 1,D1,D4
        ]
        for request, rank, done, allowed, limit, most in cases:
            self.assert_routes_agree(request, rank, done, allowed, limit, most)

    def test_routes_with_level_steps_agree_with_a_brute_force(self):
        """As above, with level steps allowed. A level step's length is 25; with a length of 2 here, every route within
        the limit stays few enough to search on its own while level steps still mix with previews in routes of one
        length."""
        wallnut = {"wallnut": 50}
        with mock.patch.object(search_module, "LEVEL_STEP_LENGTH", 2):
            for request, rank, done, allowed, limit, most in [
                    # the simple style's one switch is the level step, last
                    (("egypt1", [("toadstool", (1, 1))], wallnut, (2, 2)), 1, [], [1, 4, "egypt6@9-1", "dark4"], 5, 1),
                    # a level step first, and a preview after it, an opener and a switch
                    (("egypt1", [("horsebean", (1, 1))], wallnut, (2, 2)), 1, [], [1, 4, "egypt6@9-1", "dark4"], 5, 1),
                    # a level step between previews makes two switches, so the simple style has no recipe
                    (("egypt1", [("threepeater", (1, 1))], wallnut, (2, 2)), 1, [], [1, 4, "egypt6@9-1", "dark4"], 5, 1),
                    # after a done level step, two entries alone into Dark Ages 4, each a switch
                    (("egypt1", [("splitpea", (1, 1))], wallnut, (2, 2)), 1, ["egypt6@9-1"], [1, "D1", "dark4"], 4, 1),
                    # Egypt 13 at 2-2 spawns a Draftodil after 1,4, so no route takes it there
                    (("egypt1", [("kernelpult", (1, 1))], wallnut, (2, 2)), 1, [], [1, 4, "egypt13@2-2"], 6, 1)]:
                self.assert_routes_agree(request, rank, done, allowed, limit, most)

    def assert_routes_agree(self, request, rank, done, allowed, limit, most):
        level, wants, sources, activation = request
        level, done, allowed = load_level(level), [as_step(step) for step in done], [as_step(step) for step in allowed]
        outcomes = {}
        for planned in self.every_route(done, limit, allowed=allowed):
            end = advance(self.game, shared(), 0, done + planned, 50)[1]
            if end is not None:
                match = self.search(level, wants, sources, activation, rank=rank, done=done + planned, max_length=0,
                                    max_sources=most)["match"]
                outcomes[tuple(planned)] = (end, match)
        for style, switches in (("simple", 1), ("shorter", 3), ("shortest", None)):
            with self.subTest(level=level.id, rank=rank, done=done, allowed=allowed, style=style):
                within = {planned: outcome for planned, outcome in outcomes.items()
                          if switches is None or self.switches(done, planned) <= switches}
                found = sorted((self.length(planned), match["source_count"], self.switches(done, planned),
                                self.preference(planned, allowed), planned)
                               for planned, (_, match) in within.items() if match)
                result = self.search(level, wants, sources, activation, rank=rank, done=done, style=style,
                                     allowed=allowed, max_length=limit, max_sources=most)
                match, length = result["match"], found[0][0] if found else limit
                if found:
                    _, count, switched, _, planned = found[0]
                    self.assertEqual((match["route"], match["planned_steps"], match["source_count"], match["switches"]),
                                     ([step_name(step) for step in done + list(planned)],
                                      [step_name(step) for step in planned], count, switched))
                    keys = ("action", "cell", "result", "start", "end", "placed")
                    self.assertEqual([[row[k] for k in keys] for row in match["processing_order"]],
                                     [[row[k] for k in keys] for row in within[planned][1]["processing_order"]])
                else:
                    self.assertIsNone(match)
                self.assertEqual(result["entry_positions_searched"],
                                 len({end for planned, (end, _) in within.items() if self.length(planned) <= length}))

    def test_every_position_within_the_limit_is_searched_once(self):
        # Three spawns that almost never coincide: no route has a recipe, so each style must search every position its
        # routes reach, and each only once, however many routes reach it. Positions reached with more than one last
        # step occur in these ranges, among them positions that some routes reach with a level step last and others
        # with a preview. A level step's length is 2 here, as in the test above.
        wants = [("kernelpult", (1, 1)), ("peashooter", (2, 2)), ("burdockbatter", (3, 3))]
        evolution, every, levels = [1, 4], [1, 3, 4, "D1"], [1, 4, "egypt6@9-1", "dark4"]
        after = {}
        with mock.patch.object(search_module, "LEVEL_STEP_LENGTH", 2):
            for style, switches, done, allowed, limit in (
                    ("simple", 1, [], evolution, 30), ("simple", 1, [1, 4], evolution, 30), ("shorter", 3, [], evolution, 12),
                    ("shortest", None, [1], evolution, 9), ("simple", 1, [], every, 20), ("shorter", 3, ["D1"], every, 7),
                    ("shortest", None, [1], every, 5), ("simple", 1, [], levels, 16), ("shorter", 3, [], levels, 11),
                    ("shortest", None, ["egypt6@9-1"], [1, "D1", "egypt13@2-2", "dark4"], 8)):
                with self.subTest(style=style, done=done, allowed=allowed):
                    done, allowed = [as_step(step) for step in done], [as_step(step) for step in allowed]
                    origin = advance(self.game, shared(), 0, done, 50)[1]
                    ends = set()
                    for planned in self.every_route(done, limit, switches, allowed):
                        position = origin
                        for step in planned:
                            if (position, step) not in after:
                                entry = run_step(self.game, shared(), position, step, 50)
                                established = entry["kind"] == "preview" or entry["established"]
                                after[(position, step)] = entry["end"] if established else None
                            position = after[(position, step)]
                            if position is None:
                                break
                        if position is not None:
                            ends.add(position)
                    result = self.search("egypt1", wants, {}, rank=4, max_sources=0, done=done, style=style,
                                         allowed=allowed, max_length=limit)
                    self.assertIsNone(result["match"])
                    self.assertEqual(result["entry_positions_searched"], len(ends))

    @staticmethod
    def every_route(done, limit, most=None, allowed=(1, 4)):
        """Every sequence of allowed steps after the done ones, up to a length of `limit`, with at most `most` switches,
        counted from the last done step. Tapping an artifact plays its rank-1 preview, so the previews after a restart
        or a level step start with 1 or D1, and so do those after a switch to another artifact; a level step may follow
        any step."""
        def devolution(step):
            return str(step).startswith("D")

        def extend(route, last, length, switches):
            yield route
            for step in allowed:
                level = isinstance(step, LevelStep)
                count = switches + (level or (last is not None and step != last))
                same_artifact = last is not None and not isinstance(last, LevelStep) and devolution(last) == devolution(step)
                if (length + SearchTest.length([step]) <= limit and (level or step in (1, "D1") or same_artifact)
                        and (most is None or count <= most)):
                    yield from extend(route + [step], step, length + SearchTest.length([step]), count)
        return extend([], done[-1] if done else None, 0, 0)

    @staticmethod
    def length(planned):
        """A preview adds 1 to a route's length and a level step LEVEL_STEP_LENGTH."""
        return sum(search_module.LEVEL_STEP_LENGTH if isinstance(step, LevelStep) else 1 for step in planned)

    @staticmethod
    def switches(done, planned):
        """A preview that differs from the step before it is a switch, the last done step included, and so is every
        level step."""
        last, count = (done[-1] if done else None), 0
        for step in planned:
            count += isinstance(step, LevelStep) or (last is not None and step != last)
            last = step
        return count

    @staticmethod
    def preference(planned, allowed):
        """A route's place in step order, compared step by step: the Evolution ranks from 1 up, the Devolution ones,
        then the level steps in the order allowed."""
        order = [1, 3, 4, "D1", "D4"] + [step for step in allowed if isinstance(step, LevelStep)]
        return [order.index(step) for step in planned]

    def test_each_entry_agrees_with_a_brute_force_on_small_boards(self):
        """On tiny boards every planting is enumerable: after each number of rank-1 previews the search must find the
        fewest sources that place the wants, or report none."""
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
        checked = found = 0
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
            if wants is None:
                continue
            for count, fewest in enumerate(truth):
                result = self.search(level, wants, sources, activation, rank=rank, done=[1] * count, max_length=0,
                                     max_sources=len(usable))
                match = result["match"]
                self.assertEqual(match["source_count"] if match else None, fewest, (wants, sources, rank, activation, count))
                if match:
                    self.assertTrue(set(wants) <= self.replay(level, match, activation, rank=rank))
                    found += 1
            checked += 1
        self.assertGreaterEqual(checked, 25)
        self.assertGreaterEqual(found, 25)

    def brute_force(self, level, board, pools, usable, sources, rank, rng, stream):
        """Pick wants from a random planting so a recipe exists, then the fewest sources placing them after 0 to 3
        rank-1 previews (None where no planting does)."""
        def allowed(alias, cell):
            spec, kind = sources[alias], board.kind_at(cell)
            return (isinstance(spec, int) or kind in spec[1]) and pools.plantable(alias, kind)

        def cost(alias):
            spec = sources[alias]
            return spec if isinstance(spec, int) else spec[0]

        def plantings(count):
            _, offset = advance(self.game, stream, 0, [1] * count, 50)
            for size in range(len(usable) + 1):
                for cells in itertools.permutations(usable, size):
                    choices = [[a for a in sources if allowed(a, cell)] for cell in cells]
                    for aliases in itertools.product(*choices):
                        plan = [Planting(alias, cost(alias), cell) for alias, cell in zip(aliases, cells)]
                        rows, _ = activate(board, pools, plan, rank, stream, offset)
                        yield size, {(row["result"], row["cell"]) for row in rows if row["placed"]}

        candidates = [placed for _, placed in plantings(rng.randint(0, 2)) if placed]
        if not candidates:
            return None, None
        placed = rng.choice(candidates)
        wants = rng.sample(sorted(placed), min(len(placed), rng.randint(1, 2)))
        if len({cell for _, cell in wants}) != len(wants) and (rank == 1 or len(wants) != 2):
            wants = wants[:1]
        truth = [next((size for size, produced in plantings(count) if set(wants) <= produced), None) for count in range(4)]
        return truth, wants


if __name__ == "__main__":
    unittest.main()
