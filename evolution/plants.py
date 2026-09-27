"""Declared plant data: registry order, the seven filters, and the stage rule.

The picker walks the plant registry in a fixed order and keeps the plants that pass
seven declared-data filters, the current stage's plant restrictions, the level's bans,
the artifact's own black list, and a per-tile planting check. A candidate then
qualifies for a given source when its declared cost is strictly greater than the
source's effective cost. Everything in this module is declared data; the per-tile
check is code in the game, so its effect is measured per cell kind in `tiles`.

The declared data changes with the game version. The package bundles one version's, in
data/plants.json, which names the version and platform it was read from; a file of
another version, in the same format, is read with load_plants(path).
"""

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
PLANTS = DATA / "plants.json"
EXCLUDED_ALIASES = ("coffeebean", "pumpkin", "powervine", "peavine")
PARALLEL_PREFIX = "parallel_"
VINE_CLASSES = {"PlantTypeVine", "PlantTypeAquaVine", "PlantTypeMiniShroom", "PlantTypeShinevine"}


def load_plants(path=None):
    """The plant data in a file of the format build-plants writes; by default the bundled data/plants.json."""
    path = Path(path) if path is not None else PLANTS
    document = json.loads(path.read_text())
    game = document.get("game") or {}
    if "version" not in game or "platform" not in game:
        raise ValueError("%s must name its game version and platform; rebuild it with build-plants" % path)
    return document


def declared_costs(document):
    return {record["plant"]: record["cost"] for record in document["plants"]}


def registry_records(document):
    """The plant registry order: configured PlantTypeOrder names first, then the rest."""
    records = document["plants"]
    config = document.get("registry_order", {})
    if config.get("value_status") != "declared":
        return list(records)
    positions = {}
    for index, record in enumerate(records):
        positions.setdefault(record["plant"], []).append(index)
    ordered, used = [], set()
    for name in config["configured_types"]:
        matching = positions.get(name, [])
        if len(matching) > 1:
            raise ValueError("Ambiguous configured PlantType name: " + name)
        if matching:
            ordered.append(records[matching[0]])
            used.add(matching[0])
    ordered.extend(record for index, record in enumerate(records) if index not in used)
    return ordered


def passes(record, blacklist):
    """The seven declared-data filters, in the order the picker applies them."""
    plant = record["plant"]
    return (record.get("enabled") is not False
            and plant not in EXCLUDED_ALIASES
            and record["type_class"] not in VINE_CLASSES
            and "hero_properties" not in record
            and not plant.startswith(PARALLEL_PREFIX)
            and not record.get("is_consumable")
            and plant not in blacklist)


def funnel(document):
    """Records that survive the seven filters, in registry order."""
    blacklist = set(document["artifact"]["plant_black_list"])
    return [record for record in registry_records(document) if passes(record, blacklist)]


def stage_allows(record, stage):
    """The base stage rule: BlackListStages excludes; a non-empty ValidStages must list the stage."""
    if stage in (record.get("black_list_stages") or ()):
        return False
    valid = record.get("valid_stages")
    return not valid or stage in valid


def model_pool(document, stage=None, excluded=()):
    """Ordered aliases after the seven filters, the stage rule, and any further exclusions.

    This is the list before the per-tile check and before the cost comparison.
    """
    excluded = set(excluded)
    return [record["plant"] for record in funnel(document)
            if (stage is None or stage_allows(record, stage)) and record["plant"] not in excluded]
