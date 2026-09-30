import contextlib
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution import Game, Steps, Stream, load_level, parse_route, scenario, search_recipe, shared
from evolution.cli import main
from evolution.route import AFTER_LEVEL, ATTACK, LOADS, PROTECTED, TIDE, UNLISTED

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "level-step-captures.json").read_text())
PREVIEWS = ("E1", "E3", "E4", "D1", "D4")


def predict(*argv):
    """What predict prints as JSON."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main(["predict", *argv, "--json"])
    return json.loads(out.getvalue())


class LevelStepCaptureTest(unittest.TestCase):
    """Routes of level steps captured from a fresh launch, replayed through predict: every spawn with its cell,
    candidates and draw interval, how the player left each step, and every output the capture recorded, which the
    route's draws account for consecutively from 0."""

    def test_captured_routes_replay_through_predict(self):
        for case in FIXTURE["cases"]:
            with self.subTest(capture=case["capture"]):
                out = predict("--route", case["route"])
                self.assertEqual(out["game"]["version"], FIXTURE["game_version"])
                self.assertEqual(out["route"], [step["name"] for step in case["steps"]])
                for entry, expected in zip(out["steps"], case["steps"]):
                    self.assertEqual([(r["cell"], r["candidates"], r["result"], r["start"], r["end"]) for r in entry["results"]],
                                     [(r["cell"], r["candidates"], r["result"], r["start"], r["end"]) for r in expected["rows"]])
                    self.assertEqual(entry["end"], expected["end"])
                    if "leave" in expected:
                        self.assertEqual(entry["leave"], expected["leave"])
                draws = [(draw["start"], draw["end"]) for entry in out["steps"]
                         for part in ("entry_effects", "results", "effects") for draw in entry[part]]
                self.assertEqual([start for start, _ in draws], [0] + [end for _, end in draws[:-1]])
                self.assertEqual((draws[-1][1], out["offset_after_route"]), (case["stream_end"], case["stream_end"]))
                stream = Stream()
                self.assertEqual([stream.output(index) for index in range(case["stream_end"])], case["raw_outputs"])


class LevelStepConditionTest(unittest.TestCase):
    """A prediction states the unmeasured conditions of its level steps exactly when its route relies on them."""

    def test_conditions_follow_what_the_route_relies_on(self):
        game = Game()
        levels = (LOADS, ATTACK, PROTECTED, TIDE, AFTER_LEVEL, UNLISTED)
        cases = [
            ("E1", None, []),
            ("egypt6@9-1x2,egypt13@2-2", None, []),  # the captured route: no bags, no Draftodil, no preview after it
            # From a fresh launch, a Draftodil spawns at 5-3 beside the protected Magnet-shroom at 6-3; nothing follows.
            ("dark19@6-4", None, [ATTACK, PROTECTED]),
            ("dark19@6-4,E1", None, [LOADS, ATTACK, PROTECTED, AFTER_LEVEL]),
            ("dark21@2-2", None, []),  # no Draftodil among its spawns, and nothing follows its leaving
            ("dark21@2-2", "dark21", [LOADS]),  # restarted into the level of the activation
            ("beach3@5-3", None, [ATTACK, TIDE]),  # a Draftodil at 4-3; Beach 3 has no cell a protected plant could hold
            ("E1x23,egypt6@9-1", None, [ATTACK, UNLISTED]),  # a Draftodil at 9-2, whose row holds two gravestones
            ("E1x39,egypt6@9-1", None, [ATTACK]),  # a Draftodil at 8-1, whose row holds no cell a plant cannot stand on
        ]
        for route, level, expected in cases:
            with self.subTest(route=route, level=level):
                if level:
                    out = scenario(game, parse_route(route), load_level(level), [], (2, 2), rank=4)
                else:
                    out = scenario(game, parse_route(route))
                self.assertEqual([line for line in out["conditions"] if line in levels], sorted(expected, key=levels.index))


class LevelStepPlanTest(unittest.TestCase):
    """The route search with level steps against every route: for each style, the shortest route of allowed steps with
    a recipe, then the fewest sources, the fewest switches and the first in step order, and each position the routes
    reach within that length searched once."""

    @classmethod
    def setUpClass(cls):
        cls.game = Game()
        cls.recipes, cls.ends = {}, {}

    def test_routes_with_level_steps_agree_with_every_route(self):
        three = ["E1", "egypt6@9-1", "dark21"]
        cases = [
            # (wants, done, allowed, max_length, level_length, styles)
            ([("kernelpult", (1, 1))], [], three, 52, 25, None),  # a level step first beats any preview route
            ([("chestnut", (1, 1))], [], three, 52, 25, None),  # the simple style's route is longer, with one switch
            ([("peashooter", (2, 2))], [], three, 52, 25, None),  # no simple route, a shorter one with two switches
            ([("broccoli", (1, 1))], [], three, 52, 25, None),  # no recipe: every position within the limit is searched
            # After a done level step: E4 cannot come next, and switches count from it.
            ([("chestnut", (1, 1))], ["E1", "egypt6@9-1"], ["E1", "E4", "egypt6@9-1"], 27, 25, ("simple", "shorter")),
            ([("peashooter", (2, 2))], ["E1", "egypt6@9-1"], ["E1", "E4", "egypt6@9-1"], 27, 25, ("simple", "shorter")),
            ([("broccoli", (1, 1))], ["E1", "egypt6@9-1"], ["E1", "E4", "egypt6@9-1"], 27, 25, ("simple", "shorter")),
            # At length 1 a route's length is its number of steps.
            ([("kernelpult", (1, 1))], [], ["E1", "D1", "egypt6@9-1", "dark21", "egypt13@2-2"], 4, 1, None),
            ([("chestnut", (1, 1))], [], ["E1", "D1", "egypt6@9-1", "dark21", "egypt13@2-2"], 4, 1, None),
        ]
        limits = {"simple": 1, "shorter": 3, "shortest": None}
        for wants, done, allowed, max_length, level_length, styles in cases:
            for style in styles or limits:
                with self.subTest(wants=wants, done=done, allowed=allowed, level_length=level_length, style=style):
                    best, reached = self.every_route(wants, done, allowed, max_length, level_length, limits[style])
                    result = search_recipe(self.game, load_level("egypt1"), wants, {"wallnut": 50}, (2, 2), done=done,
                                           allowed=allowed, style=style, max_length=max_length, level_length=level_length,
                                           max_sources=1, preview_cost=50)
                    match = result["match"]
                    self.assertEqual(match and (match["length"], match["source_count"], match["switches"], match["planned"]),
                                     best and best[0][:3] + (best[1],))
                    length = best[0][0] if best else max_length
                    self.assertEqual(result["entry_positions_searched"],
                                     len({position for total, position in reached if total <= length}))

    def every_route(self, wants, done, allowed, max_length, level_length, most):
        """The best of every route of allowed steps after the done ones, within max_length and at most `most` switches,
        by the rules usage.md states: a preview counts 1 and a level step level_length; a level step, E1 and D1 may
        follow any step, another preview only one of its own artifact; a switch is a step that differs from the one
        before it, the last done step included; routes rank by length, sources, switches, then step by step in the
        order of the known previews followed by the level steps as allowed. Also every (length, position) reached."""
        steps = Steps(self.game, 50, level_length)
        order = list(PREVIEWS) + [name for name in allowed if name not in PREVIEWS]

        def after(position, name):
            if (position, name) not in self.ends:
                self.ends[(position, name)] = steps.get(name).run(shared(), position)["end"]
            return self.ends[(position, name)]

        def recipe(position):
            key = (tuple(wants), position)
            if key not in self.recipes:
                self.recipes[key] = search_recipe(self.game, load_level("egypt1"), wants, {"wallnut": 50}, (2, 2),
                                                  max_length=0, offset=position, max_sources=1)["match"]
            return self.recipes[key]

        def extend(route, last, position, total, switches):
            yield route, position, total, switches
            for name in allowed:
                length = 1 if name in PREVIEWS else level_length
                count = switches + (last is not None and name != last)
                follows = name not in PREVIEWS or name in ("E1", "D1") or (last in PREVIEWS and last[0] == name[0])
                if follows and total + length <= max_length and (most is None or count <= most):
                    yield from extend(route + [name], name, after(position, name), total + length, count)

        origin = 0
        for name in done:
            origin = after(origin, name)
        best, reached = None, set()
        for route, position, total, switches in extend([], done[-1] if done else None, origin, 0, 0):
            reached.add((total, position))
            match = recipe(position)
            if match:
                key = (total, match["source_count"], switches, [order.index(name) for name in route])
                if best is None or key < best[0]:
                    best = (key, route)
        return best, reached


if __name__ == "__main__":
    unittest.main()
