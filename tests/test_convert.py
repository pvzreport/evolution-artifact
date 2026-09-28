import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution.cli import main
from evolution.convert import PACKAGE_FILES, Package, describe_level
from evolution.level import Level


def objects(*items):
    return {"objects": list(items)}


def obj(objclass, alias, **data):
    return {"aliases": [alias], "objclass": objclass, "objdata": data}


class ConvertTest(unittest.TestCase):
    """Conversions of small level definitions with a package directory of their own, built in each test."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.package = Path(temp.name) / "PACKAGES"
        (self.package / "LEVELS").mkdir(parents=True)
        shared = {
            "LEVELMODULES.json": objects(
                obj("EgyptStageProperties", "EgyptStage", StagePrefix="egypt", BelongsToWorld="egypt"),
                obj("StageModuleProperties", "RiftStage", StagePrefix="rift"),
                obj("StageModuleProperties", "EightiesNight", StagePrefix="summer_night", BelongsToWorld="eighties"),
                obj("SunDropperProperties", "DefaultSunDropper")),
            "LEVELMUTATORTABLES.json": objects(obj("LevelMutatorTableProps", "Traps", Tables=[
                {"Level": 0, "GridMaps": [{"Grid": "TrapsLeft", "Type": "griditems", "Subtype": "flame_spreader_trap"}]},
                {"Level": 2, "GridMaps": [{"Grid": "TrapsRight", "Type": "griditems", "Subtype": "flame_spreader_trap"}]}])),
            "LEVELMUTATORMODULES.json": objects(obj("LevelMutatorStartSunProps", "StartSun50")),
            "BOARDGRIDMAPS.json": objects(
                obj("BoardGridMapProps", "TrapsLeft", Values=[[0] * 9, [0] * 9, [0, 0, 0, 1, 0, 0, 0, 0, 0], [0] * 9, [0] * 9]),
                obj("BoardGridMapProps", "TrapsRight", Values=[[0] * 9, [0] * 9, [0, 0, 0, 0, 1, 0, 1, 0, 0], [0] * 9, [0] * 9])),
            "GRIDITEMTYPES.json": objects(
                obj("GridItemType", "flame_spreader_trap", GridItemClass="GridItemGridRegionAreaOfEffectTrap"),
                obj("GridItemType", "gravestone_dark", GridItemClass="GridItemGravestone"),
                obj("GridItemType", "goldtile")),
        }
        for name, document in shared.items():
            (self.package / name).write_text(json.dumps(document))
        self.definition = {"StageModule": "RTID(EgyptStage@LevelModules)", "Modules": ["RTID(Bank@CurrentLevel)"]}
        self.level = [{"objclass": "LevelDefinition", "objdata": self.definition},
                      obj("SeedBankProperties", "Bank", PlantBlackList=["gravebuster"]),
                      obj("SeedBankProperties", "UnusedBank", PlantBlackList=["peashooter"])]

    def convert(self, *extra, **options):
        self.definition["Modules"] += ["RTID(%s@CurrentLevel)" % item["aliases"][0] for item in extra
                                       if item["objclass"] not in ("WaveManagerProperties", "SpawnGravestonesWaveActionProps")]
        path = self.package / "LEVELS" / "EXAMPLE_1.json"
        path.write_text(json.dumps(objects(*self.level, *extra)))
        return describe_level(path, **options)

    def test_the_active_bank_the_stage_and_the_files_read(self):
        description, warnings = self.convert()
        self.assertEqual((description["id"], description["stage"], description["bans"]), ("example-1", "egypt", ["gravebuster"]))
        self.assertEqual(warnings, [])
        self.assertEqual([r["path"] for r in description["provenance"]["resources"]],
                         ["PACKAGES/LEVELS/EXAMPLE_1.json", "PACKAGES/LEVELMODULES.json"])
        Level(description)

    def test_declared_board_facts_become_cells_and_entry_shuffles(self):
        # Dark Ages 19 declares two of its gravestone actions twice and shuffles the first declaration's bags.
        description, warnings = self.convert(
            obj("PiratePlankProperties", "Planks", PlankRows=[0, 1, 3, 4]),
            obj("GravestoneProperties", "Graves", ForceSpawnData=[{"GridX": 2, "GridY": 0, "TypeName": "gravestone_dark"}]),
            obj("ProtectThePlantChallengeProperties", "Protect", Plants=[{"GridX": 1, "GridY": 2, "PlantType": "magnetshroom"}]),
            obj("WaveManagerModuleProperties", "NewWaves", WaveManagerProps="RTID(Props@CurrentLevel)"),
            obj("WaveManagerProperties", "Props", Waves=[["RTID(Graves1@CurrentLevel)"], ["RTID(Graves2@CurrentLevel)"]]),
            obj("SpawnGravestonesWaveActionProps", "Graves1", GravestonePool=[{"Count": 3}, {"Count": 1}]),
            obj("SpawnGravestonesWaveActionProps", "Graves2", GravestonePool=[{"Count": 2}]),
            obj("SpawnGravestonesWaveActionProps", "Graves1", GravestonePool=[{"Count": 9}]),
            deck_columns=6)
        cells = description["cells"]
        self.assertEqual((cells["7-1"], cells["7-3"], cells["3-1"], cells["2-3"]), ("pirate_plank", "none", "none", "none"))
        self.assertNotIn("6-3", cells)
        self.assertEqual(description["entry_shuffles"], [4, 2])
        self.assertEqual(description["provenance"]["observed"], {"deck_columns": 6})
        self.assertEqual(warnings, [])

    def test_a_tier_is_needed_only_when_the_tiers_differ(self):
        # RIFT_1565 protects its Red Stingers and places its traps per difficulty tier; at tier 2 an activation
        # reported from play spawned on its trap cells.
        self.level.append(obj("LevelMutatorModuleProperties", "Mutator",
                              MutatorTables=["RTID(Traps@LevelMutatorTables)", "RTID(Local@CurrentLevel)"]))
        self.level.append(obj("LevelMutatorTableProps", "Local", Tables=[
            {"Level": 0, "Modules": ["RTID(ProtectLeft@CurrentLevel)"]},
            {"Level": 2, "Modules": ["RTID(ProtectRight@CurrentLevel)", "RTID(StartSun50@LevelMutatorModules)"]}]))
        self.level.append(obj("ProtectThePlantChallengeProperties", "ProtectLeft",
                              Plants=[{"GridX": 4, "GridY": 0, "PlantType": "redstinger"}]))
        self.level.append(obj("ProtectThePlantChallengeProperties", "ProtectRight",
                              Plants=[{"GridX": 5, "GridY": 2, "PlantType": "redstinger"}]))
        self.definition["LevelMutator"] = "RTID(Mutator@CurrentLevel)"
        with self.assertRaisesRegex(ValueError, "choose one with --tier: tier 0: protected plants on 5-1; traps on 4-3; "
                                                "tier 2: protected plants on 6-3; traps on 5-3 and 7-3"):
            self.convert()
        description, warnings = describe_level(self.package / "LEVELS" / "EXAMPLE_1.json", tier=2)
        self.assertEqual((description["id"], description["cells"], description["provenance"]["tier"]),
                         ("example-1-tier2", {"6-3": "none"}, 2))
        self.assertIn("flame_spreader_trap on 5-3 and 7-3. A plant can stand on a trap", description["notes"])
        self.assertEqual(warnings, ["Not described: modules of classes no matched activation has had, which may change the "
                                    "board or draw from the shared engine before the activation: LevelMutatorStartSunProps."])
        with self.assertRaisesRegex(ValueError, "tiers are 0 and 2; it has no tier 1"):
            describe_level(self.package / "LEVELS" / "EXAMPLE_1.json", tier=1)

    def test_what_is_not_described_is_named(self):
        self.level[0]["objdata"]["Modules"].append("RTID(Missing@CurrentLevel)")
        self.level.append(obj("SeedBankProperties", "Bank", PlantBlackList=["cherrybomb"]))
        description, warnings = self.convert(
            obj("InitialPlantProperties", "Plants", InitialPlantPlacements=[{"GridX": 0, "GridY": 1, "TypeName": "wallnut"}]),
            obj("InitialGridItemProperties", "Items", InitialGridItemPlacements=[
                {"GridX": 3, "GridY": 3, "TypeName": "gravestone_dark"}, {"GridX": 4, "GridY": 4, "TypeName": "goldtile"}]),
            obj("TideProperties", "Tide"), obj("RailcartProperties", "Rails"))
        self.assertEqual((description["bans"], description["cells"]), (["gravebuster"], {"4-4": "none"}))
        self.assertEqual(warnings, [
            "Not described: the tide, since the first column that floods, which is observed, was not given.",
            "Not described: grid items at level start: goldtile on 5-5.",
            "Not described: plants placed at level start: wallnut on 1-2.",
            "Not described: modules of classes no matched activation has had, which may change the board or draw from "
            "the shared engine before the activation: RailcartProperties.",
            "Not described: references nothing declares, skipped: RTID(Missing@CurrentLevel).",
            "Not described: the later declarations of RTID(Bank@CurrentLevel), which differ from the first; the first is used."])
        self.assertIn("Not described: the tide", description["notes"])

    def test_the_stage(self):
        self.definition["StageModule"] = "RTID(RiftStage@LevelModules)"
        self.assertEqual(self.convert()[0]["stage"], "rift")
        self.definition["StageModule"] = "RTID(EightiesNight@LevelModules)"
        with self.assertRaisesRegex(ValueError, "differ; supply the stage"):
            self.convert()
        description = self.convert(stage="eighties")[0]
        self.assertEqual((description["stage"], description["provenance"]["stage_override"]), ("eighties", "eighties"))
        del self.definition["StageModule"]
        with self.assertRaisesRegex(ValueError, "names no stage module"):
            self.convert()

    def test_a_level_outside_a_package_uses_the_bundled_extract(self):
        bundled = Package.bundled()
        self.assertEqual([source["path"] for source in bundled.record["sources"]], ["PACKAGES/" + name for name in PACKAGE_FILES])
        path = self.package.parent / "RIFT_9999.json"
        self.definition["StageModule"] = "RTID(RiftStage@LevelModules)"
        path.write_text(json.dumps(objects(*self.level)))
        description, _ = describe_level(path)
        self.assertEqual((description["stage"], description["provenance"]["resources"][1]),
                         ("rift", bundled.sources["LEVELMODULES.json"]))

    def test_the_command_writes_the_description_and_reports_what_it_leaves_out(self):
        path = self.package / "LEVELS" / "EXAMPLE_1.json"
        self.level.append(obj("RailcartProperties", "Rails"))
        self.definition["Modules"].append("RTID(Rails@CurrentLevel)")
        path.write_text(json.dumps(objects(*self.level)))
        out, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(error):
            main(["convert-level", str(path), "--id", "example", "--name", "Example"])
        self.assertEqual(json.loads(out.getvalue())["name"], "Example")
        self.assertIn("warning: Not described: modules of classes", error.getvalue())


class BundledRiftLevelTest(unittest.TestCase):
    def test_the_reported_activation_replays(self):
        # Reported from play in RIFT_1565 at tier 2, with Sunflowers at effective cost 40: after a full restart,
        # 2,480 rank-1 and 22 rank-4 previews, then a Hot Date at cost 200 planted on 6-4 and a rank-4 activation
        # there gave Rheum nobile on 6-4, Peashooter on 5-3 and Burdock batter on 7-3, beside the protected Red
        # Stinger on 6-3.
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["predict", "--level", "rift-1565-tier2", "--previews", "1x2480,4x22", "--preview-cost", "40", "--rank", "4",
                  "--activate", "6-4", "--plant", "hotdate=200@6-4", "--json"])
        results = {tuple(row["cell"]): row["result"] for row in json.loads(out.getvalue())["results"]}
        self.assertEqual((results[(6, 4)], results[(5, 3)], results[(7, 3)]), ("rheumnobile", "peashooter", "burdockbatter"))
        self.assertNotIn((6, 3), results)

    def test_empty_area_activations_checked_in_game(self):
        # Predicted before play from the converted definition and checked in the game on 4.2.4: a rank-4 activation
        # at 6-4 on the empty area, after a fresh launch and after three rank-1 previews with Sunflowers at effective
        # cost 37. Every spawn matched, and the protected Red Stingers on 6-3 and 6-5 took none.
        expected = {"": ["endurian", "puffshroom", "guardshroom", "icelotus", "levitater", "gravitree", "puffshroom"],
                    "1x3": ["celerystalker", "cosmicmushroom", "burdockbatter", "exorcislily", "spikeweed", "peashooter",
                            "streetlamp"]}
        for previews, plants in expected.items():
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                main(["predict", "--level", "rift-1565-tier2", "--previews", previews, "--preview-cost", "37", "--rank", "4",
                      "--activate", "6-4", "--json"])
            rows = json.loads(out.getvalue())["results"]
            self.assertEqual([tuple(row["cell"]) for row in rows], [(5, 3), (5, 4), (5, 5), (6, 4), (7, 3), (7, 4), (7, 5)])
            self.assertEqual([row["result"] for row in rows], plants, previews)


if __name__ == "__main__":
    unittest.main()
