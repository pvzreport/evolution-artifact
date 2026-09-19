"""Build data/plants.json from three decoded game files.

The three files are the decoded JSON forms of PLANTTYPES, PROPERTYSHEETS and ARTIFACT
from the game's configuration package. Decoding them is outside this repository. The
projection keeps only the fields the picker and the cell kinds read: each type's alias,
class, declared cost and flags from its property sheet, the configured registry order, and the
artifact's own black list, plus the hash of each source file.
"""

import hashlib
import json
from pathlib import Path

RTID_PREFIX, RTID_SUFFIX = "RTID(", "@PropertySheets)"
SHEET_FIELDS = {"IsConsumable": "is_consumable", "ValidStages": "valid_stages", "BlackListStages": "black_list_stages",
                "CanLiveOnWaves": "can_live_on_waves"}
TYPE_FIELDS = {"Enabled": "enabled", "HeroProperties": "hero_properties"}
ARTIFACT_ALIAS = "artifact_evolution"


def _source(path, document):
    raw = Path(path).read_bytes()
    return {"file": Path(path).name, "sha256": hashlib.sha256(raw).hexdigest(), "objects": len(document["objects"])}


def _sheet_alias(reference):
    if not (isinstance(reference, str) and reference.startswith(RTID_PREFIX) and reference.endswith(RTID_SUFFIX)):
        raise ValueError("Unexpected Properties reference: %r" % (reference,))
    return reference[len(RTID_PREFIX):-len(RTID_SUFFIX)]


def build_plants(planttypes_path, propertysheets_path, artifact_path):
    types = json.loads(Path(planttypes_path).read_text())
    sheets = json.loads(Path(propertysheets_path).read_text())
    artifacts = json.loads(Path(artifact_path).read_text())
    by_alias = {}
    for obj in sheets["objects"]:
        for alias in obj.get("aliases", ()):
            by_alias.setdefault(alias, []).append(obj)

    records = []
    for obj in types["objects"]:
        data = obj.get("objdata", {})
        alias = obj["aliases"][0]
        candidates = by_alias.get(_sheet_alias(data.get("Properties")), [])
        record = {"plant": alias, "type_class": obj["objclass"],
                  "properties_resolution": "unique_in_snapshot" if len(candidates) == 1 else
                  ("missing" if not candidates else "duplicate_alias")}
        if len(candidates) == 1:
            sheet = candidates[0].get("objdata", {})
            record["cost"] = sheet.get("Cost")
        else:
            record["cost"] = None
        for field, key in TYPE_FIELDS.items():
            if field in data:
                record[key] = data[field]
        if len(candidates) == 1:
            for field, key in SHEET_FIELDS.items():
                if field in sheet:
                    record[key] = sheet[field]
        records.append(record)

    game_props = [obj for obj in sheets["objects"]
                  if obj.get("objclass") == "GamePropertySheet" and "DefaultGameProps" in obj.get("aliases", ())]
    if len(game_props) != 1:
        raise ValueError("Expected exactly one DefaultGameProps sheet, found %d" % len(game_props))
    order = game_props[0]["objdata"].get("PlantTypeOrder")
    registry = {"value_status": "declared" if order is not None else "omitted", "configured_types": order,
                "source_namespace": "PropertySheets", "field": "PlantTypeOrder"}

    evolution = [obj for obj in artifacts["objects"] if ARTIFACT_ALIAS in obj.get("aliases", ())]
    if len(evolution) != 1:
        raise ValueError("Expected exactly one %s object, found %d" % (ARTIFACT_ALIAS, len(evolution)))
    artifact = {"alias": ARTIFACT_ALIAS, "objclass": evolution[0]["objclass"], "value_status": "declared",
                "plant_black_list": evolution[0]["objdata"]["plantBlackList"]}

    return {"plant_order": "GamePropertySheet.PlantTypeOrder names first, then the remaining declared types in declaration order",
            "plant_storage_order": "PLANTTYPES.json declaration order",
            "registry_order": registry, "plants": records, "artifact": artifact,
            "sources": [dict(namespace="PlantTypes", **_source(planttypes_path, types)),
                        dict(namespace="PropertySheets", **_source(propertysheets_path, sheets)),
                        dict(namespace="Artifact", **_source(artifact_path, artifacts))]}
