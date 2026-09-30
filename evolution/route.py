"""A route: the steps a player runs after a full restart, in order, and what they draw.

A step is a preview on the artifact screen or a step in a level. A preview is named by its
artifact's letter and its rank: E1, E3 and E4 are the Evolution artifact's previews, D1 and
D4 the Devolution artifact's. A level step is LEVEL@CELL, entering the level, activating
the Evolution artifact at rank 4 on CELL with nothing planted, and leaving, or LEVEL,
entering and leaving; LEVEL is a description id or a path to a description. Tapping an
artifact plays its rank-1 preview, so the previews after a restart start with E1 or D1,
the Evolution previews after a Devolution preview start again with E1, and the previews
after a level step start with E1 or D1 again, since the artifact screen is entered again.
A route is written as step names separated by commas, each optionally repeated with
xCOUNT: E1x6,egypt6@9-1x2 is six E1 previews and then two Egypt 6 steps at 9-1.

Every step runs from a stream position and returns its entry: what it drew, from where to
where. A level step draws as the level loads, one shuffle per gravestone bag; as its
activation spawns, one shuffle per free cell of the 3x3 in the rank-4 pass order; and as
each Draftodil it spawns is placed, a shuffle of the plants standing in its row, the plants
the level protects there and the spawns placed before it. Leaving draws nothing: the
player restarts the level when the next step loads the same level and otherwise quits to
the map. The level's cells are those of the level start, which a level step sees because
it activates promptly after loading. A Draftodil's attack draws too, which is not
modelled: the player leaves before it attacks.

A route is replayed from a full restart, and `scenario` follows it with any stated extra
outputs, the load of a level and an activation there. The conditions state what a
prediction relies on, the unmeasured parts of a route included.
"""

from collections import Counter
import re

from .level import available_levels, format_cell, level_path, load_level, parse_cell
from .model import Board, activate, check_level_rank, enter_level, placement_draws
from .stream import shared
from .tiles import NONE

PREFIXES = {"evolution": "E", "devolution": "D"}  # a preview's name is its artifact's letter and its rank
LEVEL_RANK = 4  # a level step activates the Evolution artifact at this rank
LEVEL_LENGTH = 25  # a level step's length in a planned route, against a preview's 1, unless stated
BEACH = "beach"  # the stage whose tide moves on a level's schedule
_PREVIEW = re.compile(r"([EeDd])(\d+)")
_ITEM = re.compile(r"(.+?)(?:x(\d+))?")

LOADS = ("Every load of a level, by entry or by restart, runs its gravestone bags, and no transition between a level, the "
         "map and the artifact screen draws anything else.")
ATTACK = ("Leave the level before a Draftodil the level step spawned attacks: its attack draws from the shared engine and "
          "is not modelled.")
PROTECTED = "The plants a level protects in a Draftodil's row count as objects of that row."
TIDE = "In a Beach level, activate before the first tide change, with the cells as described at level start."
AFTER_LEVEL = ("The previews after a level step run as when the artifact screen is entered after a relaunch: the first is "
               "E1 or D1, and it draws from where the level step left the stream.")
UNLISTED = "A level description without `protected` is taken to protect nothing."
LEVEL_CONDITIONS = (LOADS, ATTACK, PROTECTED, TIDE, AFTER_LEVEL, UNLISTED)  # in the order they are stated

_CONDITIONS = [
    "Start after a full process restart (seed 5489, offset 0).",
    "Run exactly the listed steps, each one complete with its placement effects, and nothing else that uses an "
    "artifact or loads a level.",
    "Load the level once, after the route and any stated extra outputs: its load runs the gravestone-bag shuffles its "
    "description lists, and nothing else uses the shared engine before the activation.",
    "Same level as described, sources at the listed effective cost (no discounts unless included), "
    "activate once while every source remains and before any automatic spawning.",
    "Activate promptly, after planting, or in a level step as soon as the waves start, and read the results at once.",
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
    """One step of a route: its normalised `name`; its `length` in a planned route; the `artifact` whose preview it
    plays, if any, and the level it `loads`, if any; whether it may follow a step and whether it is a switch after one;
    `run`, which draws from a stream position and returns the step's entry; `leave`, which records how the player leaves
    it; and the conditions its prediction relies on."""

    artifact = None
    loads = None

    def switch_after(self, last):
        """Whether this step is a switch after `last`, None at a restart: a step that differs from the one before it."""
        return last is not None and last.name != self.name

    def leave(self, entry, following):
        """Record in the entry how the player leaves this step for `following`, the level loaded next if any."""

    def conditions(self, followed):
        """What running this step relies on whatever it draws; `followed` says whether anything runs after it."""
        return []

    def drawn_conditions(self, entry, last):
        """What this step's prediction relies on given what it drew and the step before it, None at a restart."""
        return []


class Preview(Step):
    """A preview on the artifact screen. Tapping an artifact plays its rank-1 preview, so any other rank needs a preview
    of the same artifact right before it."""

    length = 1

    def __init__(self, artifact, rank):
        self.artifact, self.rank = artifact, rank
        self.name = PREFIXES[artifact] + str(rank)

    def may_follow(self, last):
        """Whether this preview may run after `last`, None at a restart."""
        return self.rank == 1 or (last is not None and last.artifact == self.artifact)

    def entry(self, offset, **drawn):
        return dict({"kind": "preview", "name": self.name, "artifact": self.artifact, "rank": self.rank, "start": offset},
                    **drawn)

    def drawn_conditions(self, entry, last):
        return [AFTER_LEVEL] if last is not None and last.loads is not None else []


class EvolutionPreview(Preview):
    """An Evolution preview: the display board's activation at this rank, with the Sunflowers at the route's cost."""

    def __init__(self, previews, rank, cost):
        super().__init__("evolution", rank)
        self.previews, self.cost = previews, cost

    def run(self, stream, offset):
        """Its selection rows, its effect rows, where the selections end, and the offset after the effects."""
        results, effects, selection_end, end = self.previews.evolve(stream, offset, self.rank, self.cost)
        return self.entry(offset, results=results, effects=effects, selection_end=selection_end, end=end)

    def conditions(self, followed):
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

    def conditions(self, followed):
        return ["%s is the Devolution artifact's rank-%d preview; each one is complete once its zombies are devolved."
                % (self.name, self.rank)]


class LevelStep(Step):
    """A level step: load the level, activate at rank 4 on the cell with nothing planted when a cell is given, and
    leave. It may follow any step."""

    def __init__(self, game, level, reference, cell, length):
        self.level = self.loads = level
        self.cell, self.length = cell, length
        self.name = reference if cell is None else "%s@%s" % (reference, format_cell(cell))
        self.board = Board(level, None, cell) if cell is not None else None
        self.pools = game.pools(level)
        self.population = Counter(row for _, row in level.protected)  # the plant objects standing in each row
        # The rows with a cell no plant can be put on, where a plant the description does not list could be protected.
        self.none_rows = {row for row in range(1, level.height + 1)
                          if any(level.kind_at((column, row)) == NONE for column in range(1, level.width + 1))}

    def may_follow(self, last):
        return True

    def run(self, stream, offset):
        """The bags the load shuffled, the spawn rows, the Draftodils' row shuffles, and the offset after them."""
        entry_effects, start = enter_level(self.level, stream, offset)
        results, effects, end = [], [], start
        if self.board is not None:
            results, selection_end = activate(self.board, self.pools, [], LEVEL_RANK, stream, start)
            effects, end = placement_draws(results, self.population, stream, selection_end)
        return {"kind": "level", "name": self.name, "level": self.level.describe(), "entry_effects": entry_effects,
                "activation": {"column": self.cell[0], "row": self.cell[1]} if self.cell else None,
                "results": results, "effects": effects, "start": offset, "end": end}

    def leave(self, entry, following):
        entry["leave"] = "restart" if following is not None and following.id == self.level.id else "quit"

    def conditions(self, followed):
        lines = [LOADS] if self.level.entry_shuffles and followed else []
        return lines + ([TIDE] if self.level.stage == BEACH else [])

    def drawn_conditions(self, entry, last):
        rows = {effect["cell"][1] for effect in entry["effects"]}  # the rows of the Draftodils it placed
        lines = [ATTACK] if rows else []
        if rows & set(self.population):
            lines.append(PROTECTED)
        if not self.level.lists_protected and rows & self.none_rows:
            lines.append(UNLISTED)
        return lines


class Steps:
    """The steps a route can name, for one game, one cost of the Evolution previews' Sunflowers (by default the
    declared cost) and one length of a level step in a planned route."""

    def __init__(self, game, preview_cost=None, level_length=LEVEL_LENGTH):
        if isinstance(level_length, bool) or not isinstance(level_length, int) or level_length < 1:
            raise ValueError("A level step's length is a positive integer")
        self.game, self.previews, self.level_length = game, game.previews, level_length
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
        """The step a name writes: a preview such as E4 or d1, or a level step such as egypt6@9-1 or dark21."""
        match = _PREVIEW.fullmatch(name)
        if match:
            name = match.group(1).upper() + str(int(match.group(2)))
        if name not in self._steps:
            self._steps[name] = self._preview(name) if match else self._level_step(name)
        return self._steps[name]

    def _preview(self, name):
        if name not in self._known:
            raise ValueError("No measured structure for the preview %r; known previews: %s" % (name, ", ".join(self.names())))
        artifact, rank = self._known[name]
        if artifact == "evolution":
            return EvolutionPreview(self.previews, rank, self.cost)
        return DevolutionPreview(self.previews, rank)

    def _level_step(self, name):
        reference, at, cell = name.rpartition("@") if "@" in name else (name, "", "")
        if level_path(reference) is None:
            raise ValueError("No step %r: a step is a preview, %s, or a level step, LEVEL or LEVEL@CELL, where LEVEL is a "
                             "description id, %s, or a path to a description"
                             % (name, ", ".join(self.names()), ", ".join(available_levels())))
        return LevelStep(self.game, load_level(reference), reference, parse_cell(cell) if at else None, self.level_length)

    def route(self, names, last=None):
        """The steps of a route, each checked to follow the one before it; `last` is the step already run before them,
        None at a restart."""
        steps = []
        for name in names:
            step = self.get(name)
            if not step.may_follow(last):
                raise ValueError("In a route, %s cannot %s: tapping an artifact plays its rank-1 preview, so the previews "
                                 "after a restart, after a level step or after a switch to another artifact start with %s"
                                 % (step.name, "come first" if last is None else "follow %s" % last.name,
                                    " or ".join(self.openers())))
            steps.append(step)
            last = step
        return steps


def replay(steps, stream, offset=0, then=None):
    """Run steps in order from an offset: each step's entry, numbered from 1, and the offset after the last. Each level
    step's entry records how the player leaves it; `then` is the level loaded after the steps, if any."""
    entries = []
    for number, step in enumerate(steps, start=1):
        entry = dict(step=number, **step.run(stream, offset))
        entries.append(entry)
        offset = entry["end"]
    for step, entry, following in zip(steps, entries, [step.loads for step in steps[1:]] + [then]):
        step.leave(entry, following)
    return entries, offset


def conditions(game, steps, entries, then=None, candidates=()):
    """What a prediction assumes: the game version of its plant data, what its route relies on, then the fixed
    conditions. `steps` and `entries` are the route and its replay, `then` the level loaded after it, if any, and
    `candidates` further steps a search could have planned after it, whose own conditions are stated too."""
    lines = []

    def add(new):
        lines.extend(line for line in new if line not in lines)

    for index, (step, entry) in enumerate(zip(steps, entries)):
        add(step.conditions(index + 1 < len(steps) or then is not None))
        add(step.drawn_conditions(entry, steps[index - 1] if index else None))
    for step in candidates:
        add(step.conditions(then is not None))
    return (["The game runs version %s, the version of the plant data used (read from the %s package)."
             % (game.version, game.platform)]
            + [line for line in lines if line not in LEVEL_CONDITIONS]
            + [line for line in LEVEL_CONDITIONS if line in lines] + _CONDITIONS)


def scenario(game, route=(), level=None, plantings=(), activation=None, overrides=None, offset=0, rank=1, stream=None,
             preview_cost=None):
    """Replay a route from a full restart, optional extra raw outputs, then an optional level load and activation, with
    the plant data of `game`. `route` lists step names; a route whose steps cannot run in that order is refused.
    `preview_cost` is the Evolution previews' effective source cost; the default is the source's declared cost."""
    if offset < 0:
        raise ValueError("The extra offset cannot be negative")
    if level:
        check_level_rank(rank)
    steps = Steps(game, preview_cost)
    route = steps.route(route)
    stream = stream or shared()
    entries, after = replay(route, stream, then=level)
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
            "results": results, "stream_end": end, "conditions": conditions(game, route, entries, level)}
