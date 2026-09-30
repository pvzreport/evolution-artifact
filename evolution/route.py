"""A route: the steps a player runs after a full restart, in order, and what they draw.

A step is a preview on the artifact screen, named by its artifact's letter and its rank:
E1, E3 and E4 are the Evolution artifact's previews, D1 and D4 the Devolution artifact's.
Tapping an artifact plays its rank-1 preview, so the previews after a restart start with
E1 or D1, and the Evolution previews after a Devolution preview start again with E1. A
route is written as step names separated by commas, each optionally repeated with xCOUNT:
E1x6,E4 is six E1 previews and then one E4.

Every step runs from a stream position and returns its entry, what it drew and where the
stream stands after it. A route is replayed from a full restart, and `scenario` follows it
with any stated extra outputs, the entry of a level and an activation there. The route
module also states the conditions a prediction relies on.
"""

import re

from .model import Board, activate, check_level_rank, enter_level
from .stream import shared

PREFIXES = {"evolution": "E", "devolution": "D"}  # a preview's name is its artifact's letter and its rank
_PREVIEW = re.compile(r"([EeDd])(\d+)")
_ITEM = re.compile(r"(.+?)(?:x(\d+))?")

_CONDITIONS = [
    "Start after a full process restart (seed 5489, offset 0).",
    "Run exactly the listed previews, each one complete with its placement effects, and nothing else that uses an "
    "artifact before entering the level.",
    "Enter the level once, after the previews and any stated extra outputs, and do not restart it: its entry runs the "
    "gravestone-bag shuffles its description lists, and nothing else uses the shared engine before the activation.",
    "Same level as described, sources at the listed effective cost (no discounts unless included), "
    "activate once while every source remains and before any automatic spawning.",
    "Activate promptly after planting and read the results at once.",
    "Each cell's kind must match the board at activation: Beach cells right of the coast are shore when dry, "
    "water when flooded without a pad, and pad whenever a Lily Pad is present, bare or occupied. "
    "Keep terrain and supports unchanged until the effects finish, apart from the predicted additions.",
    "Plant exactly the listed sources in the listed order inside the 3x3 around the activation cell; "
    "the newest plant is processed first.",
]


def parse_route(text):
    """The step names of a route as written, one per step run: "E1x6,E4" is six E1 and then one E4."""
    names = []
    for item in str(text or "").replace(" ", "").split(","):
        if item:
            name, times = _ITEM.fullmatch(item).groups()
            names.extend([name] * (int(times) if times is not None else 1))
    return names


def format_route(names):
    """Step names as NAMExCOUNT runs, for example E1x6,E4; "none" for an empty route."""
    runs = []
    for name in names:
        if runs and runs[-1][0] == name:
            runs[-1][1] += 1
        else:
            runs.append([name, 1])
    return ",".join("%sx%d" % (name, count) if count > 1 else name for name, count in runs) or "none"


class Step:
    """One step of a route: its normalised `name`, its `length` in a planned route, whether it may follow a step,
    whether it is a switch after one, and `run`, which draws from a stream position and returns the step's entry."""

    length = 1

    def switch_after(self, last):
        """Whether this step is a switch after `last`, None at a restart: a step that differs from the one before it."""
        return last is not None and last.name != self.name


class Preview(Step):
    """A preview on the artifact screen. Tapping an artifact plays its rank-1 preview, so any other rank needs a preview
    of the same artifact right before it."""

    def __init__(self, artifact, rank):
        self.artifact, self.rank = artifact, rank
        self.name = PREFIXES[artifact] + str(rank)

    def may_follow(self, last):
        """Whether this preview may run after `last`, None at a restart."""
        return self.rank == 1 or (last is not None and last.artifact == self.artifact)

    def entry(self, offset, **drawn):
        return dict({"kind": "preview", "name": self.name, "artifact": self.artifact, "rank": self.rank, "start": offset},
                    **drawn)


class EvolutionPreview(Preview):
    """An Evolution preview: the display board's activation at this rank, with the Sunflowers at the route's cost."""

    def __init__(self, previews, rank, cost):
        super().__init__("evolution", rank)
        self.previews, self.cost = previews, cost
        previews.plantings(rank, cost)  # refuse a cost that leaves the Sunflowers no candidates

    def run(self, stream, offset):
        """Its selection rows, its effect rows, where the selections end, and the offset after the effects."""
        results, effects, selection_end, end = self.previews.evolve(stream, offset, self.rank, self.cost)
        return self.entry(offset, results=results, effects=effects, selection_end=selection_end, end=end)

    def conditions(self):
        return ["The previews' %s sources have effective cost %d." % (self.previews.source, self.cost)]


class DevolutionPreview(Preview):
    """A Devolution preview: its shuffles of fixed sizes as it devolves its zombies."""

    def __init__(self, previews, rank):
        super().__init__("devolution", rank)
        self.previews = previews

    def run(self, stream, offset):
        """Its shuffle rows and the offset after them."""
        shuffles, end = self.previews.devolve(stream, offset, self.rank)
        return self.entry(offset, shuffles=shuffles, end=end)

    def conditions(self):
        return ["%s is the Devolution artifact's rank-%d preview; each one is complete once its zombies are devolved."
                % (self.name, self.rank)]


class Steps:
    """The steps a route can name, for one game and one cost of the Evolution previews' Sunflowers (by default the
    declared cost)."""

    def __init__(self, game, preview_cost=None):
        self.previews = game.previews
        self.cost = self.previews.cost(preview_cost)
        self._known = {PREFIXES["evolution"] + str(rank): ("evolution", rank) for rank in self.previews.evolution_ranks()}
        self._known.update((PREFIXES["devolution"] + str(rank), ("devolution", rank))
                           for rank in self.previews.devolution_ranks())
        self._steps = {}

    def names(self):
        """Every known preview, in preference order: the Evolution previews by rank, then the Devolution previews."""
        return list(self._known)

    def openers(self):
        """The previews tapping an artifact plays: each artifact's rank-1 preview."""
        return [name for name, (_, rank) in self._known.items() if rank == 1]

    def get(self, name):
        """The step a name writes, such as E4 or d1."""
        match = _PREVIEW.fullmatch(name)
        if not match:
            raise ValueError("Name a step as a preview, %s, for example E1x6,E4; got %r" % (", ".join(self.names()), name))
        name = match.group(1).upper() + str(int(match.group(2)))
        if name not in self._known:
            raise ValueError("No measured structure for the preview %r; known previews: %s" % (name, ", ".join(self.names())))
        if name not in self._steps:
            artifact, rank = self._known[name]
            self._steps[name] = (EvolutionPreview(self.previews, rank, self.cost) if artifact == "evolution"
                                 else DevolutionPreview(self.previews, rank))
        return self._steps[name]

    def route(self, names, last=None):
        """The steps of a route, each checked to follow the one before it; `last` is the step already run before them,
        None at a restart."""
        steps = []
        for name in names:
            step = self.get(name)
            if not step.may_follow(last):
                raise ValueError("In a route, %s cannot %s: tapping an artifact plays its rank-1 preview, so the previews "
                                 "after a restart start with %s, and so do those after a switch to another artifact"
                                 % (step.name, "come first" if last is None else "follow %s" % last.name,
                                    " or ".join(self.openers())))
            steps.append(step)
            last = step
        return steps


def replay(steps, stream, offset=0):
    """Run steps in order from an offset: each step's entry, numbered from 1, and the offset after the last."""
    entries = []
    for number, step in enumerate(steps, start=1):
        entry = dict(step=number, **step.run(stream, offset))
        entries.append(entry)
        offset = entry["end"]
    return entries, offset


def conditions(game, steps):
    """What a prediction assumes: the game version of its plant data, what its steps need, then the fixed conditions.
    `steps` are the steps the prediction involves: a route or, for a search without a recipe, every step it could have
    planned."""
    lines = ["The game runs version %s, the version of the plant data used (read from the %s package)."
             % (game.version, game.platform)]
    for step in steps:
        lines.extend(line for line in step.conditions() if line not in lines)
    return lines + _CONDITIONS


def scenario(game, route=(), level=None, plantings=(), activation=None, overrides=None, offset=0, rank=1, stream=None,
             preview_cost=None):
    """Replay a route from a full restart, optional extra raw outputs, then an optional level entry and activation, with
    the plant data of `game`. `route` lists step names; a route whose steps cannot run in that order is refused.
    `preview_cost` is the Evolution previews' effective source cost; the default is the source's declared cost."""
    if offset < 0:
        raise ValueError("The extra offset cannot be negative")
    if level:
        check_level_rank(rank)
    steps = Steps(game, preview_cost)
    route = steps.route(route)
    stream = stream or shared()
    entries, after = replay(route, stream)
    entry = after + offset
    entry_effects, start, results, end = [], entry, [], entry
    if level:
        entry_effects, start = enter_level(level, stream, entry)
        results, end = activate(Board(level, overrides, activation), game.pools(level), plantings, rank, stream, start)
    return {"game": game.describe(), "preview_cost": steps.cost, "route": [step.name for step in route], "steps": entries,
            "offset_after_route": after, "extra_offset": offset,
            "level": level.describe() if level else None, "level_entry_offset": entry,
            "entry_effects": entry_effects, "activation_offset": start,
            "activation": {"column": activation[0], "row": activation[1]} if activation else None, "rank": rank,
            "results": results, "stream_end": end, "conditions": conditions(game, route)}
