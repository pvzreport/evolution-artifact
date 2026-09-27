"""The recipe search before states were merged, kept as the reference the package's search must equal.

At one activation start it walks every sequence of pool options breadth first, fewest sources
first, and returns the first sequence it accepts. It is the package's search as it stood with an
unlimited budget: the same options, the same capacity check per option and the same acceptance,
with no merging, so its first accepted sequence is the recipe by definition. Its shuffles go
through a memo keyed by pool and offset, which changes no result because a shuffle is a pure
function of both; without it the reference is several times slower.

tests/fixtures/search-equality.json lists the requests and holds the reference's recipes at level
entries drawn for each of them, as its note describes.

    python3 tests/reference_search.py generate   draw the entries of every request and record the reference's recipes,
                                                 comparing the package's search at every draw
    python3 tests/reference_search.py check      recompute every recorded recipe and report any that differ
"""

from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution import Board, Game, load_level, parse_cell, search_recipe
from evolution.level import LILYPAD
from evolution.model import check_board, enter_level, place, select, selection_row
from evolution.search import _check_wants, _options, _spawnable
from evolution.stream import shared
from evolution.tiles import NONE

FIXTURE = Path(__file__).parent / "fixtures" / "search-equality.json"
ROW_KEYS = ("action", "cell", "kind", "source", "cost", "candidates", "result", "runners_up", "start", "end", "placed",
            "beneath", "sources", "wanted")
DRAWN_BELOW = 1000000


def case_request(case):
    """A fixture case as search inputs: level id, activation cell, wants, sources, rank, overrides, max_sources."""
    wants = []
    for text in case["wants"]:
        plant, _, cell = text.partition("@")
        wants.append((plant, parse_cell(cell)))
    sources = {alias: spec if isinstance(spec, int) else (spec[0], list(spec[1])) for alias, spec in case["sources"].items()}
    overrides = {parse_cell(cell): kind for cell, kind in case.get("cells", {}).items()}
    return (case["level"], parse_cell(case["activation"]), wants, sources, case["rank"], overrides or None,
            case["max_sources"])


def draws(case):
    """The level-entry positions drawn for a case, in order."""
    rng = random.Random(case["name"])
    return [rng.randrange(DRAWN_BELOW) for _ in range(case["draws"])]


def digest(rows):
    """A short hash of every field of every row, in order; None when there is no recipe."""
    if rows is None:
        return None
    table = [[list(row[key]) if isinstance(row[key], (list, tuple)) else row[key] for key in ROW_KEYS] for row in rows]
    return hashlib.sha256(json.dumps(table, separators=(",", ":")).encode()).hexdigest()[:16]


def reference_rows(game, case, entry):
    """The reference search's rows at the activation start reached by entering the case's level at `entry`."""
    level_id, activation, wants, sources, rank, overrides, max_sources = case_request(case)
    level = load_level(level_id)
    board = Board(level, overrides, activation)
    check_board(board, game.kinds)
    pools = game.pools(level)
    kind_of = {cell: board.kind_at(cell) for cell in board.area}
    usable = [cell for cell in board.area if kind_of[cell] != NONE]
    _check_wants(wants, usable, pools, rank)
    options, _ = _options(pools, sources, kind_of, usable, rank)
    spawnable = _spawnable(wants, pools, kind_of, rank)
    required = Counter(plant for (plant, cell), ok in spawnable.items() if not ok)
    stream = MemoStream(shared())
    _, start = enter_level(level, stream, entry)
    search = ReferenceSearch(stream, pools, board, kind_of, usable, options, wants, required, spawnable, rank)
    return search.run(start, min(max_sources, len(usable)))


class MemoStream:
    """A stream whose shuffles are memoised by pool and offset. The shuffled lists are shared, and nothing mutates them."""

    def __init__(self, stream):
        self.stream, self.memo = stream, {}

    def shuffle(self, values, offset):
        key = (id(values), offset)
        hit = self.memo.get(key)
        if hit is None or hit[0] is not values:
            hit = self.memo[key] = (values,) + tuple(self.stream.shuffle(values, offset))
        return hit[1], hit[2]


class ReferenceSearch:
    def __init__(self, stream, pools, board, kind_of, usable, options, wants, required, spawnable, rank):
        self.stream, self.pools, self.area, self.kind_of, self.usable = stream, pools, board.area, kind_of, usable
        self.options, self.wants, self.required, self.spawnable, self.rank = options, wants, required, spawnable, rank
        self.reserved = {cell: plant for plant, cell in wants if rank == 1 or plant != LILYPAD}
        self.wants_at = {}
        for plant, cell in wants:
            self.wants_at.setdefault(cell, []).append(plant)
        self.capacity = Counter(kind_of[cell] for cell in usable)
        self.usable_from = [sum(1 for cell in board.area[index:] if kind_of[cell] != NONE)
                            for index in range(len(board.area) + 1)]
        self.spawns = {}

    def run(self, start, max_sources):
        """The accepted rows for an activation starting at this offset, or None."""
        self.spawns = {}
        if not self.required:
            rows = self._evaluate([], start)
            if rows is not None:
                return rows
        frontier = [(start, [], Counter())]
        for _ in range(max_sources):
            following = []
            for position, steps, used in frontier:
                blocked = bool(steps) and not steps[-1]["candidates"]
                for index, option in enumerate(self.options):
                    if blocked and option["pool"]:
                        continue
                    if used[index] + 1 > sum(self.capacity[kind] for kind in option["kinds"]):
                        continue
                    shuffled, end = self.stream.shuffle(option["pool"], position)
                    step = {"option": index, "candidates": len(option["pool"]), "shuffled": shuffled,
                            "result": shuffled[0] if shuffled else None, "start": position, "end": end}
                    path = steps + [step]
                    if self._covers(path):
                        rows = self._evaluate(path, end)
                        if rows is not None:
                            return rows
                    following.append((end, path, used + Counter({index: 1})))
            frontier = following
        return None

    def _covers(self, path):
        counts = Counter(step["result"] for step in path)
        return all(counts[plant] >= needed for plant, needed in self.required.items())

    def _evaluate(self, path, position):
        """Rows of an accepted recipe for this pool sequence, or None."""
        if self.rank == 1:
            cells = self._match(path, self.usable, spare=len(self.usable) - len(path))
            return self._accept(path, cells, []) if cells is not None else None
        return self._walk(path, 0, [], [], position)

    def _walk(self, path, index, occupied, spawned, offset):
        """Decide the cells from `index` on, occupied or free, and return the first accepted leaf."""
        slots = len(path) - len(occupied)
        if slots > self.usable_from[index]:
            return None
        if index == len(self.area):
            cells = self._match(path, occupied, spare=0)
            return self._accept(path, cells, spawned) if cells is not None else None
        cell = self.area[index]
        if self.kind_of[cell] == NONE:
            return self._walk(path, index + 1, occupied, spawned, offset)
        wants = self.wants_at.get(cell, ())
        if all(self.spawnable[(plant, cell)] for plant in wants):
            row = self._spawn(cell, offset, occupied=False)
            if row is None or all(plant == row["result"] for plant in wants):
                rows = self._walk(path, index + 1, occupied, spawned + [row] if row else spawned,
                                  row["end"] if row else offset)
                if rows is not None:
                    return rows
        if slots and self._may_occupy(cell, path):
            row = self._spawn(cell, offset, occupied=True)
            return self._walk(path, index + 1, occupied + [cell], spawned + [row] if row else spawned,
                              row["end"] if row else offset)
        return None

    def _may_occupy(self, cell, path):
        """A wanted cell may hold a source only if some step made its plant, or the pad beneath it is its want."""
        for plant in self.wants_at.get(cell, ()):
            if cell in self.reserved and self.reserved[cell] == plant:
                if not any(step["result"] == plant for step in path):
                    return False
            elif not self.pools.spawn(self.kind_of[cell], occupied=True):
                return False
        return True

    def _spawn(self, cell, offset, occupied):
        """The spawn row of one cell at an offset, or None when its pool is empty; memoised per search."""
        key = (cell, offset, occupied)
        if key not in self.spawns:
            pool = self.pools.spawn(self.kind_of[cell], occupied)
            if pool:
                row, _ = select(self.stream, offset, pool, "spawn", cell, self.kind_of[cell], beneath=occupied)
                row["sources"] = []
                self.spawns[key] = row
            else:
                self.spawns[key] = None
        return self.spawns[key]

    def _match(self, path, cells, spare):
        """Assign each step a distinct cell its option's kinds allow, reserving wanted cells; None if impossible.

        `spare` unused slots take any cell that is not reserved, so every cell is matched.
        """
        reserved, kind_of = self.reserved, self.kind_of
        allowed = [self.options[step["option"]]["kinds"] for step in path] + [None] * spare
        results = [step["result"] for step in path] + [None] * spare
        owner = {}

        def place_slot(index, seen):
            for cell in cells:
                if cell in seen:
                    continue
                if cell in reserved and results[index] != reserved[cell]:
                    continue
                if allowed[index] is not None and kind_of[cell] not in allowed[index]:
                    continue
                seen.add(cell)
                if cell not in owner or place_slot(owner[cell], seen):
                    owner[cell] = index
                    return True
            return False

        for index in range(len(allowed)):
            if not place_slot(index, set()):
                return None
        assigned = [None] * len(allowed)
        for cell, index in owner.items():
            assigned[index] = cell
        return assigned[:len(path)]

    def _accept(self, path, cells, spawned):
        """The placed rows of this assignment if every want is met, else None."""
        rows = []
        for step, cell in zip(path, cells):
            kind = self.kind_of[cell]
            pairs = self.options[step["option"]]["aliases"][kind]
            source, cost = pairs[0]
            row = selection_row("evolve", cell, kind, source, cost, step["candidates"], step["shuffled"],
                                step["start"], step["end"])
            row["sources"] = [alias for alias, _ in pairs]
            rows.append(row)
        rows.extend(dict(row) for row in spawned)
        place(rows, self.kind_of, self.pools.kinds)
        placed = {(row["result"], row["cell"]) for row in rows if row["placed"]}
        if not all(want in placed for want in self.wants):
            return None
        wanted = set(self.wants)
        for row in rows:
            row["wanted"] = bool(row["placed"]) and (row["result"], row["cell"]) in wanted
        return rows


_GAMES = {}


def _game(version):
    if version not in _GAMES:
        _GAMES[version] = Game(version)
    return _GAMES[version]


def _entry(rows):
    """What the fixture records of a recipe: its number of sources and its hash, or two nulls."""
    return [None if rows is None else sum(1 for row in rows if row["action"] == "evolve"), digest(rows)]


def _reference(job):
    """The reference's recipe at one entry, and with `compare` whether the package's search returns the same one."""
    version, case, entry, compare = job
    game = _game(version)
    began = time.perf_counter()
    expected = _entry(reference_rows(game, case, entry))
    seconds = time.perf_counter() - began
    same = None
    if compare:
        level_id, activation, wants, sources, rank, overrides, max_sources = case_request(case)
        match = search_recipe(game, load_level(level_id), wants, sources, activation, overrides=overrides, rank=rank,
                              max_previews=0, offset=entry, max_sources=max_sources)["match"]
        same = _entry(None if match is None else match["processing_order"]) == expected
    return case["name"], entry, expected, same, seconds


def _run(jobs):
    """Every job's result, computed in parallel, keyed by case name and entry."""
    from multiprocessing import Pool
    results = {}
    with Pool() as pool:
        for name, entry, expected, same, seconds in pool.imap_unordered(_reference, jobs, chunksize=1):
            results[(name, entry)] = (expected, same, seconds)
    return results


def generate(fixture):
    """Draw every case's entries, run the reference at each draw, and keep the first random_entries draws and the later
    draws at which it found a recipe, at most found_entries of them. The package's search is compared at every draw.

    Returns the exit status and every draw's result, keyed by case name and entry."""
    version = fixture["game_version"]
    jobs = [(version, case, entry, True) for case in fixture["cases"] for entry in dict.fromkeys(draws(case))]
    jobs.sort(key=lambda job: -len(job[1]["sources"]) ** job[1]["max_sources"])  # the largest trees first
    results = _run(jobs)
    total = equal = 0
    for case in fixture["cases"]:
        drawn = list(dict.fromkeys(draws(case)))
        head, tail = drawn[:case["random_entries"]], drawn[case["random_entries"]:]
        found = [entry for entry in tail if results[(case["name"], entry)][0][0] is not None][:case["found_entries"]]
        case["entries"] = [[entry] + results[(case["name"], entry)][0] for entry in head + found]
        same = sum(1 for entry in drawn if results[(case["name"], entry)][1])
        seconds = sum(results[(case["name"], entry)][2] for entry in drawn)
        recipes = sum(1 for entry in drawn if results[(case["name"], entry)][0][0] is not None)
        print("%s: %d draws, %d with a recipe, package equal at %d, reference %.2f s per draw"
              % (case["name"], len(drawn), recipes, same, seconds / len(drawn)), flush=True)
        total += len(drawn)
        equal += same
    print("The package's search equals the reference at %d of %d draws" % (equal, total))
    return (0 if equal == total else 1), results


def check(fixture):
    """Recompute every recorded entry with the reference and report any that differ."""
    version = fixture["game_version"]
    jobs = [(version, case, entry[0], False) for case in fixture["cases"] for entry in case["entries"]]
    results = _run(jobs)
    differences = 0
    for case in fixture["cases"]:
        for entry in case["entries"]:
            fresh = results[(case["name"], entry[0])][0]
            if entry[1:] != fresh:
                differences += 1
                print("%s: entry %d recorded %s, reference gives %s" % (case["name"], entry[0], entry[1:], fresh))
    print("%d of %d recorded recipes differ from the reference" % (differences, len(jobs)))
    return 1 if differences else 0


def dump(fixture):
    """The fixture as JSON with one field or entry per line; "cases" comes last."""
    lines = ["{"]
    lines += [" %s: %s," % (json.dumps(key), json.dumps(value)) for key, value in fixture.items() if key != "cases"]
    lines.append(' "cases": [')
    for index, case in enumerate(fixture["cases"]):
        lines.append("  {")
        lines += ["   %s: %s," % (json.dumps(key), json.dumps(value)) for key, value in case.items() if key != "entries"]
        lines.append('   "entries": [')
        lines.append(",\n".join("    " + json.dumps(entry) for entry in case["entries"]))
        lines.append("   ]")
        lines.append("  }" + ("," if index < len(fixture["cases"]) - 1 else ""))
    lines += [" ]", "}"]
    return "\n".join(lines) + "\n"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv not in (["generate"], ["check"]):
        print(__doc__.split("\n\n")[-1])
        return 2
    fixture = json.loads(FIXTURE.read_text())
    if argv == ["check"]:
        return check(fixture)
    status, _ = generate(fixture)
    FIXTURE.write_text(dump(fixture))
    return status


if __name__ == "__main__":
    sys.exit(main())
