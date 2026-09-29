"""A route: the steps run after a full process restart before the level, and the replay of a route and a level.

A route is the sequence of previews run on the artifact screen after a full restart, named as
in previews: an Evolution rank such as 4, or D1 and D4 for the Devolution previews. Tapping an
artifact plays its rank-1 preview, so a route starts with 1 or D1, and so does each switch to
the other artifact. Each preview moves the shared stream by a replayable amount, so the route
decides where in the fixed sequence the level after it is entered.
"""

import re

from .model import Board, activate, check_level_rank, enter_level
from .previews import parse_preview
from .stream import shared

_REPEATED = re.compile(r"(.+?)x(\d+)")  # a step name followed by xCOUNT

_CONDITIONS = [
    "Start after a full process restart (seed 5489, offset 0).",
    "Run exactly the listed steps, each preview complete with its placement effects, and nothing else that "
    "uses an artifact before entering the level.",
    "Enter the level once, after the route and any stated extra outputs, and do not restart it: its entry runs the "
    "gravestone-bag shuffles its description lists, and nothing else uses the shared engine before the activation.",
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


def parse_route(text):
    """Steps in order, separated by commas, each NAME or NAMExCOUNT: "1x6,4" is six rank-1 Evolution previews then a
    rank-4 one, "D1x2,1" two Devolution previews then a rank-1 Evolution preview."""
    route = []
    for part in str(text or "").replace(" ", "").split(","):
        if part:
            match = _REPEATED.fullmatch(part)
            name, times = match.groups() if match else (part, 1)
            route.extend([parse_preview(name)] * int(times))
    return route


def format_route(route):
    """Steps as NAME or NAMExCOUNT runs, for example 1x6,4 or D1x2,1; "none" for an empty route."""
    runs = []
    for step in route:
        if runs and runs[-1][0] == step:
            runs[-1][1] += 1
        else:
            runs.append([step, 1])
    return ",".join("%sx%d" % (step, count) if count > 1 else str(step) for step, count in runs) or "none"


def check_route(previews, route):
    """Refuse a route that no player can run."""
    last = None
    for step in route:
        if not previews.follows(last, step):
            raise ValueError("In a route, %s cannot %s: tapping an artifact plays its rank-1 preview, so a route starts "
                             "with %s, and so does each switch to another artifact"
                             % (step, "come first" if last is None else "follow %s" % last,
                                " or ".join(str(name) for name in previews.openers())))
        last = step


def advance(game, stream, offset, route, cost):
    """A route's steps from an offset: one entry per step, and the offset after them."""
    entries = []
    for index, step in enumerate(route, start=1):
        entry = game.previews.run(stream, offset, step, cost)
        entries.append({"step": index, **entry})
        offset = entry["end"]
    return entries, offset


def conditions(game, cost=None, route=()):
    """What a prediction assumes: the game version of its plant data, what its route needs, then the fixed conditions.
    `route` is the route the prediction involves or, for a search without a recipe, every step it could have planned."""
    lines = ["The game runs version %s, the version of the plant data used (read from the %s package)."
             % (game.version, game.platform)]
    return lines + game.previews.conditions(list(route), cost) + _CONDITIONS


def scenario(game, route=(), level=None, plantings=(), activation=None, overrides=None, offset=0, rank=1,
             stream=None, preview_cost=None):
    """Replay a route, optional extra raw outputs, then an optional level entry and activation, from a fresh process,
    with the plant data of `game`; a route that no player can run is refused. `preview_cost` is the Evolution
    previews' effective source cost; the default is the source's declared cost."""
    if offset < 0:
        raise ValueError("The extra offset cannot be negative")
    if level:
        check_level_rank(rank)
    route = list(route)
    check_route(game.previews, route)
    stream = stream or shared()
    cost = game.previews.cost(preview_cost)
    steps, after_route = advance(game, stream, 0, route, cost)
    entry = after_route + offset
    entry_effects, start, results, end = [], entry, [], entry
    if level:
        entry_effects, start = enter_level(level, stream, entry)
        board = Board(level, overrides, activation)
        results, end = activate(board, game.pools(level), plantings, rank, stream, start)
    return {"game": game.describe(), "preview_cost": cost, "steps": steps, "offset_after_route": after_route,
            "extra_offset": offset, "level": level.describe() if level else None, "level_entry_offset": entry,
            "entry_effects": entry_effects, "activation_offset": start,
            "activation": {"column": activation[0], "row": activation[1]} if activation else None, "rank": rank,
            "results": results, "stream_end": end, "conditions": conditions(game, cost, route)}
