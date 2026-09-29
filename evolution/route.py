"""A route: the steps run after a full process restart before the level, and the replay of a route and a level.

A route is a sequence of steps. A preview runs on the artifact screen and is named as in
previews: an Evolution rank such as 4, or D1 and D4 for the Devolution previews. A level step
runs in a level and is written LEVEL@CELL: enter the level, activate the Evolution artifact at
rank 4 on CELL with nothing planted, and leave. LEVEL alone enters the level and leaves, so it
draws only the level's entry shuffles, and it is refused for a level that lists none. LEVEL is
a description id in data/levels or a path to one. Each step moves the shared stream by a
replayable amount (model.level_step for a level step), so the route decides where in the fixed
sequence the level after it is entered.

Tapping an artifact plays its rank-1 preview, so the previews after a restart start with 1 or
D1, and so do those after a switch to the other artifact. After a level step the artifact
screen is entered again, so the previews after it start the same way; a level step may follow
anything. A level step is left by restarting its level when the next step, or the level after
the route, is in the same level and that level lists no entry shuffles: in the level-step
capture a restart drew nothing. Otherwise it is left by quitting to the map: entering a level
again from the map repeats its entry shuffles (model.enter_level), and whether a restart
repeats them was not measured.
"""

import re

from .level import format_cell, load_level, parse_cell
from .model import Board, activate, area_around, check_level_rank, enter_level, level_step
from .previews import PREVIEW_NAME, parse_preview
from .stream import shared

_REPEATED = re.compile(r"(.+?)x(\d+)")  # a step name followed by xCOUNT

_CONDITIONS = [
    "Start after a full process restart (seed 5489, offset 0).",
    "Run exactly the listed steps, each preview complete with its placement effects, and nothing else that "
    "uses an artifact before entering the level.",
    "Enter the level once, after the route and any stated extra outputs: its entry runs the gravestone-bag shuffles its "
    "description lists, and nothing else uses the shared engine before the activation. Do not restart a level that "
    "lists entry shuffles: whether a restart repeats them was not measured.",
    "Same level as described, sources at the listed effective cost (no discounts unless included), "
    "activate once while every source remains and before any automatic spawning.",
    "Activate promptly after planting and read the results at once: in one capture, outputs from outside "
    "the artifact followed the selections during the effects, so in-level events can move the stream.",
    "Each cell's kind must match the board at activation: Beach cells right of the coast are shore when dry, "
    "water when flooded without a pad, and pad whenever a Lily Pad is present, bare or occupied. "
    "Keep terrain and supports unchanged until the effects finish, apart from the predicted additions.",
    "Plant exactly the listed sources in the listed order inside the 3x3 around the activation cell; "
    "the newest plant is processed first.",
]
_ACTIVATING_STEP = ("Play each level step with a cell promptly: enter its level, activate the Evolution artifact once at "
                    "rank 4 on that cell with nothing planted, before any automatic spawning, and leave as soon as the "
                    "plants have appeared.")
_ENTRY_STEP = "In a level step without a cell, leave the level as soon as it has loaded."
_LEVEL_STEP_CONDITIONS = [
    "Leave a level step's level by restarting it when the next step, or the level after the route, is the same level "
    "and it lists no entry shuffles, and otherwise by quitting to the map; entering a level from the map runs its "
    "entry shuffles again.",
    "Each level step's level has no tides: the position after a level step was measured only in levels without "
    "tides, and captures in a Beach level with tides recorded outputs from outside the artifact after a level's "
    "effects.",
]


class LevelStep:
    """A step in a level: with a cell, a rank-4 activation there with nothing planted; without one, the entry alone.
    Its name is the level as written, an id or a path, and the cell."""

    def __init__(self, level, cell=None, reference=None):
        reference = reference or level.id
        if cell is None and not level.entry_shuffles:
            raise ValueError("The level step %s would draw nothing, since the level lists no entry shuffles; write "
                             "%s@CELL to activate on CELL" % (reference, reference))
        if cell is not None:
            area_around(cell, level.width, level.height)
        self.level, self.cell = level, None if cell is None else tuple(cell)
        self.name = reference if cell is None else "%s@%s" % (reference, format_cell(cell))

    def __eq__(self, other):
        return isinstance(other, LevelStep) and other.name == self.name

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return "LevelStep(%r)" % self.name

    def run(self, stream, offset, pools):
        """The step at an offset, on its level's pools, as a route entry."""
        entry = {"kind": "level", "name": self.name, "level": self.level.describe(),
                 "activation": {"column": self.cell[0], "row": self.cell[1]} if self.cell else None,
                 "rank": 4 if self.cell else None}
        return dict(entry, **level_step(self.level, self.cell, pools, stream, offset))


def parse_step(text):
    """A step by name: a preview, such as 1, 4 or D1, or a level step, LEVEL@CELL or LEVEL."""
    text = str(text)
    if PREVIEW_NAME.fullmatch(text):
        return parse_preview(text)
    reference, at, cell = text.rpartition("@")
    if not at:
        reference = text
    if not reference:
        raise ValueError("A level step names its level before the cell, as LEVEL@CELL: %r" % text)
    try:
        level = load_level(reference)
    except ValueError as error:
        raise ValueError("A route step is a preview, such as 1, 4 or D1, or a level step, LEVEL@CELL or LEVEL, with a "
                         "level id or a path to a description: %s" % error)
    return LevelStep(level, parse_cell(cell) if at else None, reference)


def as_step(step):
    """A step given by name, as parse_step reads it, or already parsed: a preview's rank or name, or a LevelStep."""
    return step if isinstance(step, (int, LevelStep)) else parse_step(step)


def previews_in(route):
    """A route's previews, in order."""
    return [step for step in route if not isinstance(step, LevelStep)]


def step_name(step):
    """A step's name as a route writes it: a preview's rank or name, or a level step's name."""
    return step.name if isinstance(step, LevelStep) else step


def parse_route(text):
    """Steps in order, separated by commas, each NAME or NAMExCOUNT: "1x6,4" is six rank-1 Evolution previews then a
    rank-4 one, and "D1,1,egypt6@9-1x2" a Devolution preview, a rank-1 Evolution preview and two level steps in Egypt 6
    on 9-1."""
    route = []
    for part in str(text or "").replace(" ", "").split(","):
        if part:
            match = _REPEATED.fullmatch(part)
            name, times = match.groups() if match else (part, 1)
            route.extend([parse_step(name)] * int(times))
    return route


def format_route(route):
    """Steps as NAME or NAMExCOUNT runs, for example 1x6,4 or D1,1,egypt6@9-1x2; "none" for an empty route."""
    runs = []
    for step in route:
        name = step_name(step)
        if runs and runs[-1][0] == name:
            runs[-1][1] += 1
        else:
            runs.append([name, 1])
    return ",".join("%sx%d" % (name, count) if count > 1 else str(name) for name, count in runs) or "none"


def follows(previews, last, step):
    """Whether a route may run `step` after `last`, None at a restart. A level step may follow anything; after one the
    artifact screen is entered again, so a preview follows it as it follows a restart."""
    if isinstance(step, LevelStep):
        return True
    return previews.follows(None if isinstance(last, LevelStep) else last, step)


def check_route(previews, route):
    """Refuse a route that no player can run."""
    last = None
    for step in route:
        if not follows(previews, last, step):
            raise ValueError("In a route, %s cannot %s: tapping an artifact plays its rank-1 preview, so the previews "
                             "after a restart or a level step start with %s, and so do those after a switch to another "
                             "artifact" % (step, "come first" if last is None else "follow %s" % step_name(last),
                                           " or ".join(str(name) for name in previews.openers())))
        last = step


def run_step(game, stream, offset, step, cost, pools=None):
    """One step at an offset, as a route entry; a level step runs on `pools`, its level's, when given."""
    if isinstance(step, LevelStep):
        return step.run(stream, offset, pools or game.pools(step.level))
    return dict({"kind": "preview"}, **game.previews.run(stream, offset, step, cost))


def leaves(route, level=None):
    """How each step's level is left, None for a preview: "restart" when the next step, or `level` after the route, is
    in the same level and that level lists no entry shuffles, else "quit" to the map."""
    following = [step.level if isinstance(step, LevelStep) else None for step in route[1:]] + [level]
    return [None if not isinstance(step, LevelStep) else
            "restart" if after is not None and after.id == step.level.id and not step.level.entry_shuffles else "quit"
            for step, after in zip(route, following)]


def advance(game, stream, offset, route, cost, level=None):
    """A route's steps from an offset: one entry per step, and the offset after them. The replay stops after the first
    step whose end is not established, and the offset is then None. `level`, the level entered after the route,
    decides how the last level step is left."""
    entries = []
    for index, (step, leave) in enumerate(zip(route, leaves(route, level)), start=1):
        entry = dict({"step": index}, **run_step(game, stream, offset, step, cost))
        if leave:
            entry["leave"] = leave
        entries.append(entry)
        if entry["kind"] == "level" and not entry["established"]:
            return entries, None
        offset = entry["end"]
    return entries, offset


def conditions(game, cost=None, route=()):
    """What a prediction assumes: the game version of its plant data, what its route needs, then the fixed conditions.
    `route` is the route the prediction involves or, for a search without a recipe, every step it could have planned."""
    route = list(route)
    level_steps = [step for step in route if isinstance(step, LevelStep)]
    lines = ["The game runs version %s, the version of the plant data used (read from the %s package)."
             % (game.version, game.platform)]
    lines += game.previews.conditions(previews_in(route), cost) + _CONDITIONS[:2]
    if any(step.cell for step in level_steps):
        lines.append(_ACTIVATING_STEP)
    if any(not step.cell for step in level_steps):
        lines.append(_ENTRY_STEP)
    if level_steps:
        lines += _LEVEL_STEP_CONDITIONS
    return lines + _CONDITIONS[2:]


def scenario(game, route=(), level=None, plantings=(), activation=None, overrides=None, offset=0, rank=1,
             stream=None, preview_cost=None):
    """Replay a route, optional extra raw outputs, then an optional level entry and activation, from a fresh process,
    with the plant data of `game`; a route that no player can run is refused. The route's steps are given by name or
    parsed. The replay stops after a step whose end is not established, and the offsets after it and the level's
    results are then not given. `preview_cost` is the Evolution previews' effective source cost; the default is the
    source's declared cost."""
    if offset < 0:
        raise ValueError("The extra offset cannot be negative")
    if level:
        check_level_rank(rank)
    route = [as_step(step) for step in route]
    check_route(game.previews, route)
    stream = stream or shared()
    cost = game.previews.cost(preview_cost)
    steps, after_route = advance(game, stream, 0, route, cost, level)
    entry = start = end = None
    entry_effects, results = [], []
    if after_route is not None:
        entry = start = end = after_route + offset
        if level:
            entry_effects, start = enter_level(level, stream, entry)
            board = Board(level, overrides, activation)
            results, end = activate(board, game.pools(level), plantings, rank, stream, start)
    return {"game": game.describe(), "preview_cost": cost, "steps": steps, "offset_after_route": after_route,
            "extra_offset": offset, "level": level.describe() if level else None, "level_entry_offset": entry,
            "entry_effects": entry_effects, "activation_offset": start,
            "activation": {"column": activation[0], "row": activation[1]} if activation else None, "rank": rank,
            "results": results, "stream_end": end, "conditions": conditions(game, cost, route)}
