# Data files

Everything the model needs is under `data/`. All of it is declared game data or lists read from the running game; none of it is game code.

`data/plants/` holds the plant registry as the picker sees it, one file per game version, named by the version. `game` gives the version and the platform of the package the data was read from; a version's declared data is assumed to be the same on every platform. `plants` lists every declared plant type in declaration order with its alias, class, declared cost, the flags the filters read (`enabled`, `hero_properties`, `is_consumable`, `valid_stages`, `black_list_stages`), and `can_live_on_waves`, the declared `CanLiveOnWaves` flag that the flooded cell kind reads. `registry_order.configured_types` is the game's `PlantTypeOrder`, which the registry puts first. `artifact.plant_black_list` is the artifact's own black list. `sources` records the three game files the projection came from, with their SHA-256.

To add a version, decode `PLANTTYPES`, `PROPERTYSHEETS` and `ARTIFACT` from its configuration package to JSON, outside this repository, and run `build-plants` with `--game-version` and `--platform`; the result is `data/plants/VERSION.json`. The newest version is the default.

Only the plant data is versioned. `data/tile-rules.json`, `data/previews.json` and the level descriptions are shared by every version and assumed to carry over; each measured record in the two rule files names the game version it was taken on in `game_version`.

`data/tile-rules.json` holds the named cell kinds. Each kind lists the plants its planting check rejects beyond the stage rule and the level's bans (`rejects`), or, for a flooded cell, the plant flag that admits a plant (`admits_flag`, the `can_live_on_waves` field of the plant data); a kind may also list the only plants it admits (`admits_only`). The kind `none` is built in. `measured` names the captures behind a kind and the game version each was taken on. To add a kind, read a source's candidate list on such a cell from the game, diff it against the model's list for that level and cost, and record the difference here.

`data/previews.json` describes what one preview on the artifact screen does: the display board's stage and cell kind, the cost cut of the evolution pool (`evolution_source_cost`) and of the spawn pool (`spawn_max_cost`, which is also the rank-4 spawn cut in a level), and for each rank the ordered steps, where `evolution` steps name their cells in processing order, `single` steps are one-candidate shuffles that consume nothing, and `spawn` steps draw from the spawn pool.

## Level descriptions

`data/levels/*.json` holds one description per level. It is the model's input contract: the declared facts the model reads, and where they came from.

- `id`, `name`, `stage`, `bans` (the seed bank's black list), `default_kind`, and `cells`, a map of COLUMN-ROW to kind for the cells whose kind differs from the default. Optional `width` and `height` default to 9 and 5.
- `provenance` says where the facts came from. A description exported from a decoded level definition has `kind` `declared`, the `exporter`, `resources` with the package path and SHA-256 of each file read, `observed` for the inputs the definition does not declare (the Pirate deck edge as `deck_columns`, the first Beach column that floods as `shore_from`), and `stage_override` when the stage was supplied by hand. A description written from a capture or by hand has `kind` `capture` or `hand` and a `note`.
- `notes` are for the reader.

Declared initial gravestones are `none` cells, which cannot hold a plant; give `ground` for an activation once one has been destroyed. Plank rows are declared; the deck edge and the shore column are observed on the board, which is why they are recorded as observed inputs. Descriptions with declared provenance are generated from decoded level definitions, which are not redistributed, and regenerate identically from their recorded inputs. A level whose file is not at hand can be described by hand from the seed-selection screen, which shows the bans, and from the board.

The Endless examples are `arthurs-challenge` (Dark Ages) and `tiki-torch-er` (Big Wave Beach). Arthur's Challenge uses a ground baseline; supply standing gravestones as `none`. Tiki Torch-er defaults to ground in columns 1–4 and water in columns 5–9; supply `beach_pad` for Lily Pads and `beach_shore` for exposed sand at activation.

## Capture fixtures

Each fixture file names the game version it was read from in `game_version`, and the tests replay it with that version's plant data; the expectations written into the test files name their version in `CAPTURED_ON`. Adding a version therefore changes no expectation. One test covers every version: each plant the shared data names must be declared in it, so a renamed plant cannot silently drop a rule.

`tests/fixtures/pools.json` holds ordered candidate lists read from the running game, keyed by level, cell kind and source cost, plus the two preview pools; the tests require the model to reproduce each of them in order.

`tests/fixtures/rank4-captures.json` retains ten rank-4 activations in normal levels: inputs, selections, ordered-pool hashes, draw intervals and trace hashes, with no process or account data. Some planting orders were reconstructed by reversing the recorded processing order; those cases are marked. The starting offsets were identified from recorded draws, so these are replay cases rather than forecasts. Captures 1 to 3 belong to one process and 4 to 10 to a later one whose capture 4 begins at offset 2,874, with unrecorded gaps of 10 and 78 outputs before captures 7 and 9; what consumed those outputs was not recorded. The model regenerates every draw from the default seed; the fixture supplies none.

`tests/fixtures/rank4-followups.json` retains three Beach activations that test the placement rules: B, a Sea-shroom over water whose replacement and extra support both selected Lily Pad; A, a Puff-shroom on dry shore receiving a Lily Pad beneath it; and Cactus, a dry-shore replacement rejected after the pad appeared. B and Cactus were forecast before play from declared preview sequences; A's offset was identified afterwards. Each case records the plant-add call order, and `placed` expectations are asserted only where the terrain stayed unchanged, so the Cactus case excludes its flooded column 6. `captured_stream_end` counts the outputs recorded after the last selection, which `stream_end` does not.
