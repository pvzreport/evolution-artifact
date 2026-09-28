"""Describe a level from its decoded level definition.

A level definition is the game's JSON form of one level: objects that refer to each other with
RTID(alias@sheet) references, one of them the LevelDefinition. References to CurrentLevel stay in the
file. The others name objects that every level shares, in the configuration package's LEVELMODULES,
LEVELMUTATORTABLES and LEVELMUTATORMODULES; a mutator table also names grid maps of BOARDGRIDMAPS,
and GRIDITEMTYPES gives each grid item's class. The shared objects come from a decoded package
directory, or from data/level-modules.json, which `build-level-modules` extracts from one.

The conversion follows the definition's active references: its modules and, when its difficulty
tiers differ, the chosen tier's mutator tables. It keeps what the model reads and names in the
description's notes, and returns as warnings, what it finds on the board but does not describe.

- The stage is the stage module's StagePrefix, the name the plant data's stage rules use (roof_night,
  snow_roof); a stage module whose BelongsToWorld names another stage needs the stage supplied.
- The active seed bank's PlantBlackList is the level's bans.
- Gravestones, declared or placed as grid items, hold no plant while they stand (Dark Ages captures),
  and neither do the cells of the plants a level protects: the artifact skips a protected plant as a
  source and its cell holds no other plant (the Dark Ages 19 capture of 2026-09-26). Both are `none`.
- A plant can stand on a trap, so a trap's cell is ground. An activation reported from play in
  RIFT_1565 at tier 2, with spawns on trap cells beside the tier's protected Red Stingers, matched the
  model with the traps as ground and the Red Stingers' cells as `none`.
- Entry shuffles: when a level loads, every SpawnGravestonesWaveActionProps that the wave list
  references builds a bag of its GravestonePool entries, each repeated Count times, and shuffles it
  with the shared engine, in wave order (Dark Ages 4, 19 and 21 captures). An action no wave
  references builds nothing.
- An alias declared twice resolves to its first declaration, as the game resolves a wave's reference
  (Dark Ages 19 declares two of its gravestone actions twice); declarations that differ are reported.
  A reference that nothing declares, the game cannot load either: it is skipped and reported.
- Plank rows are declared; the Pirate deck edge and the Beach shore column are observed, so they are
  inputs, recorded in the description's provenance.
- Not described: other grid items, plants placed at level start, a tide without its shore column,
  and modules of a class no matched activation has had (COVERED), which may change the board or draw
  from the shared engine before the activation.
"""

import hashlib
import json
import re
from pathlib import Path

from .plants import DATA

LEVEL_MODULES = DATA / "level-modules.json"
COLUMNS, ROWS = 9, 5
PACKAGE_FILES = ("LEVELMODULES.json", "LEVELMUTATORTABLES.json", "LEVELMUTATORMODULES.json", "BOARDGRIDMAPS.json",
                 "GRIDITEMTYPES.json")
SHEETS = {"LevelModules": ("level_modules", "LEVELMODULES.json"),
          "LevelMutatorTables": ("mutator_tables", "LEVELMUTATORTABLES.json"),
          "LevelMutatorModules": ("mutator_modules", "LEVELMUTATORMODULES.json")}
SEED_BANKS = ("SeedBankProperties", "RiftSeedBankProperties")
# The fields a description reads, by module class; the extract keeps only these and the stage fields.
READ_FIELDS = dict({bank: ("PlantBlackList",) for bank in SEED_BANKS}, PiratePlankProperties=("PlankRows",),
                   GravestoneProperties=("ForceSpawnData",), ProtectThePlantChallengeProperties=("Plants",),
                   InitialGridItemProperties=("InitialGridItemPlacements",),
                   InitialPlantProperties=("InitialPlantPlacements",), InitialPlantEntryProperties=("Plants",))
STAGE_FIELDS = ("StagePrefix", "BelongsToWorld")
TABLE_FIELDS = ("Level", "Modules", "GridMaps")
GRID_FIELDS = ("Grid", "Type", "Subtype")
PLANT_PLACEMENTS = ("InitialPlantProperties", "InitialPlantEntryProperties")
# Module classes of the levels whose activations matched the model: the levels behind the declared
# descriptions in data/levels, and RIFT_1565 at tier 2.
COVERED = frozenset({
    "ConveyorSeedBankProperties", "GravestoneProperties", "InitialGridItemProperties", "LastStandMinigameProperties",
    "LawnMowerProperties", "LevelMutatorModuleProperties", "LevelMutatorMowerSpawnProps",
    "LevelMutatorStartingPlantfoodProps", "LevelMutatorZombieCountdownFirstWaveSecsProps", "LevelMutatorZombieLevelProps",
    "LevelScoringModuleProperties", "PerkHandlerModuleProperties", "PiratePlankProperties",
    "PlantfoodTutorialIntroProperties", "ProtectThePlantChallengeProperties", "SeedBankProperties",
    "StandardLevelIntroProperties", "StarChallengeBeatTheLevelProps", "StarChallengeModuleProperties",
    "StarChallengeTargetScoreProps", "SunDropperProperties", "TideProperties", "TimeEnergyModuleProperties",
    "TutorialPeashooterDeathProperties", "WaveManagerModuleProperties", "ZombiesAteYourBrainsProperties",
    "ZombiesDeadWinConProperties"})
GRAVESTONE_CLASS = "GridItemGravestone"
TRAP_CLASSES = ("GridItemGridRegionAreaOfEffectTrap", "GridItemProjectileTrap")
REFERENCE = re.compile(r"RTID\((.+)@([^@]+)\)")


def reference(text):
    """(alias, sheet) of an RTID reference, or (None, None)."""
    match = REFERENCE.fullmatch(text) if isinstance(text, str) else None
    return match.groups() if match else (None, None)


def resource_path(path):
    """A file's path inside the game package, from its PACKAGES directory on, or else its name."""
    parts = Path(path).as_posix().split("/")
    return "/".join(parts[parts.index("PACKAGES"):]) if "PACKAGES" in parts else parts[-1]


def join(items):
    """'a', 'a and b', 'a, b and c'."""
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _cell_text(cell):
    return "%d-%d" % cell


def _cell(item):
    return int(item["GridX"]) + 1, int(item["GridY"]) + 1


def _by_alias(objects, entry):
    table = {}
    for obj in objects:
        for alias in obj.get("aliases") or ():
            table.setdefault(alias, []).append(entry(obj))
    return table


def extract_package(directory):
    """The shared level objects of a decoded configuration package directory, in the form of data/level-modules.json:
    for each sheet, alias -> the objects declaring it (two when an alias is declared twice) with the fields a
    description reads; the cells of the grid maps that mutator tables name; each grid-item type's class; and the path
    and SHA-256 of every file read."""
    directory = Path(directory)
    objects, sources = {}, []
    for name in PACKAGE_FILES:
        raw = (directory / name).read_bytes()
        objects[name] = json.loads(raw)["objects"]
        sources.append({"path": "PACKAGES/" + name, "sha256": hashlib.sha256(raw).hexdigest()})

    def pick(data, fields):
        return {field: data[field] for field in fields if field in data}

    def module(obj):
        fields = READ_FIELDS.get(obj.get("objclass"), ()) + STAGE_FIELDS
        return {"objclass": obj.get("objclass"), "objdata": pick(obj.get("objdata") or {}, fields)}

    def table(obj):
        rows = [dict(pick(row, TABLE_FIELDS), **({"GridMaps": [pick(grid, GRID_FIELDS) for grid in row["GridMaps"]]}
                                                 if row.get("GridMaps") else {}))
                for row in (obj.get("objdata") or {}).get("Tables") or ()]
        return {"objclass": obj.get("objclass"), "objdata": {"Tables": rows}}

    tables = _by_alias(objects["LEVELMUTATORTABLES.json"], table)
    named = {grid.get("Grid") for entries in tables.values() for table in entries
             for row in table["objdata"].get("Tables") or () for grid in row.get("GridMaps") or ()}
    grid_maps = _by_alias([obj for obj in objects["BOARDGRIDMAPS.json"] if set(obj.get("aliases") or ()) & named],
                          lambda obj: [_cell_text((column + 1, row + 1))
                                       for row, values in enumerate((obj.get("objdata") or {}).get("Values") or ())
                                       for column, value in enumerate(values) if value])
    return {"sources": sources,
            "level_modules": _by_alias(objects["LEVELMODULES.json"], module),
            "mutator_tables": tables,
            "mutator_modules": _by_alias(objects["LEVELMUTATORMODULES.json"],
                                         lambda obj: {"objclass": obj.get("objclass"), "objdata": {}}),
            "grid_maps": grid_maps,
            "grid_item_classes": _by_alias(objects["GRIDITEMTYPES.json"],
                                           lambda obj: (obj.get("objdata") or {}).get("GridItemClass"))}


class Package:
    """The shared objects levels refer to, and the path and SHA-256 of each file they came from."""

    def __init__(self, record):
        self.record = record
        self.sources = {source["path"].rsplit("/", 1)[-1]: source for source in record["sources"]}

    @classmethod
    def read(cls, directory):
        return cls(extract_package(directory))

    @classmethod
    def bundled(cls):
        return cls(json.loads(LEVEL_MODULES.read_text()))

    @classmethod
    def for_level(cls, path):
        """The package directory holding the level's LEVELS directory when it has every shared file, else the
        bundled extract."""
        directory = Path(path).resolve().parent.parent
        if all((directory / name).is_file() for name in PACKAGE_FILES):
            return cls.read(directory)
        return cls.bundled()


class _Board:
    """What one set of modules and grid maps puts on the board."""

    def __init__(self):
        self.gravestones, self.protected, self.traps, self.items, self.plants = [], [], [], [], []
        self.uncovered = set()

    def key(self):
        return tuple(tuple(sorted(set(part))) for part in
                     (self.gravestones, self.protected, self.traps, self.items, self.plants))

    def extend(self, other):
        for name in ("gravestones", "protected", "traps", "items", "plants"):
            getattr(self, name).extend(getattr(other, name))
        self.uncovered |= other.uncovered


class _Reader:
    """A level file's objects, the shared objects, and the files read so far, in order."""

    def __init__(self, path, package):
        raw = Path(path).read_bytes()
        try:
            document = json.loads(raw)
        except ValueError:
            raise ValueError("%s is not JSON; decode the level definition to JSON first" % path)
        if not isinstance(document, dict) or not isinstance(document.get("objects"), list):
            raise ValueError("%s is not a decoded level definition: it has no objects list" % path)
        self.objects = document["objects"]
        self.index = _by_alias(self.objects, lambda obj: obj)
        self.package = package
        self.resources = [{"path": resource_path(path), "sha256": hashlib.sha256(raw).hexdigest()}]
        self.unresolved, self.differing = [], []

    def use(self, name):
        source = self.package.sources[name]
        if all(resource["path"] != source["path"] for resource in self.resources):
            self.resources.append({"path": source["path"], "sha256": source["sha256"]})

    def resolve(self, text):
        """The object an active reference names: its first declaration, or None when nothing declares it."""
        name, sheet = reference(text)
        if sheet == "CurrentLevel":
            matches = self.index.get(name, [])
        elif sheet in SHEETS:
            key, file = SHEETS[sheet]
            self.use(file)
            matches = self.package.record[key].get(name, [])
        else:
            matches = []
        if not matches:
            self.unresolved.append(str(text))
            return None
        if len({json.dumps([obj.get("objclass"), obj.get("objdata")], sort_keys=True) for obj in matches}) > 1:
            self.differing.append(str(text))
        return matches[0]

    def first(self, text):
        """The first declaration a CurrentLevel reference names, as the game resolves a wave's references."""
        name, sheet = reference(text)
        return self.index.get(name, [None])[0] if sheet == "CurrentLevel" else None

    def grid_cells(self, alias):
        """The cells a grid map marks: its first declaration's, or none when nothing declares it."""
        self.use("BOARDGRIDMAPS.json")
        maps = self.package.record["grid_maps"].get(alias, [])
        if not maps:
            self.unresolved.append("grid map %s" % alias)
            return []
        if any(cells != maps[0] for cells in maps):
            self.differing.append("grid map %s" % alias)
        return [tuple(int(n) for n in cell.split("-")) for cell in maps[0]]

    def item(self, board, cell, item_type):
        """File a grid item under the gravestones, the traps, or the items not described."""
        self.use("GRIDITEMTYPES.json")
        classes = self.package.record["grid_item_classes"].get(item_type, [])
        item_class = classes[0] if len(classes) == 1 else None
        if (item_class or "").startswith(GRAVESTONE_CLASS) or (item_class is None and
                                                               str(item_type).lower().startswith("gravestone")):
            board.gravestones.append(cell)
        elif item_class in TRAP_CLASSES:
            board.traps.append(cell + (item_type,))
        else:
            board.items.append(cell + (str(item_type),))

    def collect(self, board, obj):
        """What a module puts on the board; a class no matched activation has had is noted as uncovered."""
        cls, data = obj.get("objclass"), obj.get("objdata") or {}
        if cls not in COVERED and cls not in PLANT_PLACEMENTS:
            board.uncovered.add(str(cls))
        if cls == "GravestoneProperties":
            board.gravestones.extend(_cell(item) for item in data.get("ForceSpawnData") or ())
        elif cls == "ProtectThePlantChallengeProperties":
            board.protected.extend(_cell(item) + (item.get("PlantType"),) for item in data.get("Plants") or ())
        elif cls == "InitialGridItemProperties":
            for item in data.get("InitialGridItemPlacements") or ():
                self.item(board, _cell(item), item.get("TypeName"))
        elif cls == "InitialPlantProperties":
            board.plants.extend(_cell(item) + (item.get("TypeName"),) for item in data.get("InitialPlantPlacements") or ())
        elif cls == "InitialPlantEntryProperties":
            board.plants.extend(_cell(item) + ("/".join(item.get("PlantTypes") or ()),) for item in data.get("Plants") or ())


def entry_shuffles(reader, active):
    """The gravestone bags shuffled at level entry, in wave order: one size per gravestone-spawning wave action the
    active wave manager's wave list references, each the sum of its GravestonePool's Count."""
    waves = []
    for _, manager in active:
        if manager.get("objclass") != "WaveManagerModuleProperties":
            continue
        props_reference = (manager.get("objdata") or {}).get("WaveManagerProps")
        if props_reference is None:
            continue  # dynamically generated waves declare no wave list, so no gravestone action is built
        props = reader.first(props_reference)
        if props is None:
            raise ValueError("Unresolved WaveManagerProps reference %r" % props_reference)
        waves.extend((props.get("objdata") or {}).get("Waves") or [])
    sizes = []
    for wave in waves:
        for text in wave:
            action = reader.first(text)
            if action is not None and action.get("objclass") == "SpawnGravestonesWaveActionProps":
                pool = (action.get("objdata") or {}).get("GravestonePool") or []
                sizes.append(sum(int(entry.get("Count", 0)) for entry in pool))
    return sizes


def tiers(reader, definition):
    """Difficulty tier -> what its mutator tables put on the board, for a level with a level mutator."""
    mutator_reference = definition.get("LevelMutator")
    if not mutator_reference:
        return {}
    mutator = reader.resolve(mutator_reference) or {}
    boards = {}
    for table_reference in (mutator.get("objdata") or {}).get("MutatorTables") or ():
        table = reader.resolve(table_reference) or {}
        for row in (table.get("objdata") or {}).get("Tables") or ():
            board = boards.setdefault(row.get("Level"), _Board())
            for module_reference in row.get("Modules") or ():
                module = reader.resolve(module_reference)
                if module is not None:
                    reader.collect(board, module)
            for grid in row.get("GridMaps") or ():
                for cell in reader.grid_cells(grid.get("Grid")):
                    if grid.get("Type") == "griditems":
                        reader.item(board, cell, grid.get("Subtype"))
                    else:
                        board.items.append(cell + (str(grid.get("Type")),))
    return boards


def _summary(board):
    parts = []
    for label, cells in (("gravestones", board.gravestones), ("protected plants", board.protected),
                         ("traps", board.traps), ("other grid items", board.items), ("plants placed at start", board.plants)):
        if cells:
            parts.append("%s on %s" % (label, join(sorted({_cell_text(cell[:2]) for cell in cells}))))
    return "; ".join(parts) or "nothing"


def _grouped(entries):
    """'x on 1-1 and 2-2; y on 3-3' for (column, row, name) entries."""
    names = {}
    for column, row, name in sorted(entries, key=lambda entry: (str(entry[2]), entry[:2])):
        names.setdefault(name, []).append(_cell_text((column, row)))
    return "; ".join("%s on %s" % (name, join(dict.fromkeys(cells))) for name, cells in names.items())


def describe_level(path, package=None, tier=None, level_id=None, name=None, stage=None, deck_columns=5, shore_from=None):
    """The level description of the decoded level definition at `path`, and warnings about what it leaves out.

    package: the shared objects, by default those of the package directory the level sits in, else the bundled
    extract. tier: the difficulty tier, needed when the level's tiers put different things on the board. stage:
    the stage, needed when the stage module's StagePrefix and BelongsToWorld differ. deck_columns and shore_from:
    the observed Pirate deck edge and first Beach column that floods."""
    path = Path(path)
    reader = _Reader(path, package or Package.for_level(path))
    definitions = [obj.get("objdata") or {} for obj in reader.objects if obj.get("objclass") == "LevelDefinition"]
    if len(definitions) != 1:
        raise ValueError("Expected exactly one LevelDefinition")
    definition = definitions[0]
    stage_module = reader.resolve(definition["StageModule"]) if definition.get("StageModule") else None
    if stage_module is None and stage is None:
        raise ValueError("The level's stage module %r is not declared; supply the stage" % definition["StageModule"]
                         if definition.get("StageModule") else "The level names no stage module; supply the stage")
    stage_data = (stage_module or {}).get("objdata") or {}
    active = [(ref, obj) for ref, obj in ((ref, reader.resolve(ref)) for ref in definition.get("Modules") or ())
              if obj is not None]
    board = _Board()
    for _, obj in active:
        reader.collect(board, obj)

    by_tier = tiers(reader, definition)
    if by_tier:
        if tier is None:
            layouts = {level: tier_board.key() for level, tier_board in by_tier.items()}
            if len(set(layouts.values())) > 1:
                raise ValueError("The level's difficulty tiers put different things on the board; choose one with "
                                 "--tier: %s" % "; ".join("tier %s: %s" % (level, _summary(by_tier[level]))
                                                          for level in sorted(by_tier, key=str)))
            first = by_tier[sorted(by_tier, key=str)[0]]
            board.extend(first)
            for tier_board in by_tier.values():
                board.uncovered |= tier_board.uncovered
        elif tier not in by_tier:
            raise ValueError("The level's difficulty tiers are %s; it has no tier %r" % (
                join([str(level) for level in sorted(by_tier, key=str)]), tier))
        else:
            board.extend(by_tier[tier])
    elif tier is not None:
        raise ValueError("The level has no difficulty tiers")

    prefix, world = stage_data.get("StagePrefix"), stage_data.get("BelongsToWorld")
    if stage is None and (not prefix or world not in (None, prefix)):
        raise ValueError("The level's StagePrefix (%r) and BelongsToWorld (%r) differ; supply the stage" % (prefix, world))
    banks = [obj for _, obj in active if obj.get("objclass") in SEED_BANKS]
    if len(banks) > 1:
        raise ValueError("Several seed banks are active; select the effective bank before predicting")
    bans = (banks[0].get("objdata") or {}).get("PlantBlackList", []) if banks else []
    if not isinstance(bans, list) or not all(isinstance(alias, str) for alias in bans):
        raise ValueError("PlantBlackList must be a list of aliases")
    planks = [obj for _, obj in active if obj.get("objclass") == "PiratePlankProperties"]
    plank_rows = (planks[0].get("objdata") or {}).get("PlankRows") if len(planks) == 1 else None
    tide = any(obj.get("objclass") == "TideProperties" for _, obj in active)
    shuffles = entry_shuffles(reader, active)

    cells, notes, warnings = {}, [], []
    if plank_rows is not None:
        rows = {int(row) + 1 for row in plank_rows}
        for row in range(1, ROWS + 1):
            for column in range(deck_columns + 1, COLUMNS + 1):
                cells[_cell_text((column, row))] = "pirate_plank" if row in rows else "none"
        notes.append("Deck columns 1 to %d. Planks on rows %s from column %d; other rows are open water there. "
                     "The plank rows are declared; the deck edge is observed." % (
                         deck_columns, ", ".join(str(row) for row in sorted(rows)), deck_columns + 1))
    if shore_from is not None:
        for row in range(1, ROWS + 1):
            for column in range(shore_from, COLUMNS + 1):
                cells[_cell_text((column, row))] = "beach_shore"
        notes.append("Columns 1 to %d never flood. Columns %d to %d are shore cells when dry; the tide is a "
                     "scheduled level event. For a flooded cell give beach_water (no pad) or beach_pad (plant on a "
                     "Lily Pad) for that activation. The shore column is observed." % (shore_from - 1, shore_from, COLUMNS))
    graves = sorted(set(board.gravestones))
    for cell in graves:
        cells[_cell_text(cell)] = "none"
    if graves:
        notes.append("Gravestones declared at level start on %s hold no plant while they stand; give ground for that "
                     "activation once one has been destroyed." % ", ".join(_cell_text(cell) for cell in graves))
    if board.protected:
        places = {}
        for column, row, plant in board.protected:
            cells[_cell_text((column, row))] = "none"
            places.setdefault(plant, []).append(_cell_text((column, row)))
        notes.append("The level protects %s; the artifact skips a protected plant as a source, and its cell holds no other "
                     "plant while it stands." % " and ".join("%s at %s" % (plant, join(dict.fromkeys(spots)))
                                                             for plant, spots in places.items()))
    if shuffles:
        notes.append("Entering the level shuffles %s with the shared engine, in that order, before anything is planted."
                     % ("a gravestone bag of %d objects" % shuffles[0] if len(shuffles) == 1
                        else "gravestone bags of %s objects" % join([str(n) for n in shuffles])))
    if tier is not None:
        notes.append("The protected plants and grid items are those of the level's difficulty tier %s." % tier)
    if board.traps:
        notes.append("Traps stand at level start: %s. A plant can stand on a trap, so these cells are ground."
                     % _grouped(board.traps))
    left_out = []
    if tide and shore_from is None:
        left_out.append("the tide, since the first column that floods, which is observed, was not given")
    if board.items:
        left_out.append("grid items at level start: %s" % _grouped(board.items))
    if board.plants:
        left_out.append("plants placed at level start: %s" % _grouped(board.plants))
    if board.uncovered:
        left_out.append("modules of classes no matched activation has had, which may change the board or draw from the "
                        "shared engine before the activation: %s" % join(sorted(board.uncovered)))
    if reader.unresolved:
        left_out.append("references nothing declares, skipped: %s" % join(list(dict.fromkeys(reader.unresolved))))
    if reader.differing:
        left_out.append("the later declarations of %s, which differ from the first; the first is used"
                        % join(list(dict.fromkeys(reader.differing))))
    if left_out:
        notes.append("Not described: %s." % "; ".join(left_out))
        warnings.extend("Not described: %s." % part for part in left_out)

    observed = {}
    if plank_rows is not None:
        observed["deck_columns"] = deck_columns
    if shore_from is not None:
        observed["shore_from"] = shore_from
    provenance = {"kind": "declared", "resources": reader.resources}
    if observed:
        provenance["observed"] = observed
    if stage is not None:
        provenance["stage_override"] = stage
    if tier is not None:
        provenance["tier"] = tier
    suffix = "" if tier is None else "-tier%s" % tier
    description = {"id": level_id or path.stem.lower().replace("_", "-") + suffix,
                   "name": name or path.stem + ("" if tier is None else " tier %s" % tier),
                   "stage": stage or prefix, "default_kind": "ground", "bans": list(bans)}
    if cells:
        description["cells"] = {cell: cells[cell] for cell in sorted(cells, key=lambda c: tuple(int(n) for n in c.split("-")))}
    description["entry_shuffles"] = list(shuffles)
    if notes:
        description["notes"] = " ".join(notes)
    description["provenance"] = provenance
    return description, warnings
