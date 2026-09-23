# Data files

Everything the model needs is under `data/`. All of it is declared game data or lists read from the running game; none of it is game code.

`data/plants.json` is the plant registry as the picker sees it. `plants` lists every declared plant type in declaration order with its alias, class, declared cost, the flags the filters read (`enabled`, `hero_properties`, `is_consumable`, `valid_stages`, `black_list_stages`), and `can_live_on_waves`, the declared `CanLiveOnWaves` flag that the flooded cell kind reads. `registry_order.configured_types` is the game's `PlantTypeOrder`, which the registry puts first. `artifact.plant_black_list` is the artifact's own black list. `sources` records the three game files the projection came from, with their SHA-256. To rebuild it for another game version, decode `PLANTTYPES`, `PROPERTYSHEETS` and `ARTIFACT` from the game's configuration package to JSON, outside this repository, and run `build-plants`. A new version changes costs, flags, and the registry order.

`data/tile-rules.json` holds the named cell kinds. Each kind lists the plants its planting check rejects beyond the stage rule and the level's bans (`rejects`), or, for a flooded cell, the plant flag that admits a plant (`admits_flag`, the `can_live_on_waves` field of `plants.json`); a kind may also list the only plants it admits (`admits_only`). The kind `none` is built in. To add a kind, read a source's candidate list on such a cell from the game, diff it against the model's list for that level and cost, and record the difference here.

`data/previews.json` describes what one preview on the artifact screen does: the display board's stage and cell kind, the cost cut of the evolution pool and the spawn pool, and for each rank the ordered steps, where `evolution` steps name their cells in processing order, `single` steps are one-candidate shuffles that consume nothing, and `spawn` steps draw from the spawn pool.

`data/levels/*.json` holds one description per level: `stage`, `bans` (the seed bank's black list), `default_kind`, and `cells`, a map of COLUMN-ROW to kind for the cells whose kind differs from the default. Optional `width` and `height` default to 9 and 5. Declared initial gravestones are `none` cells, which cannot hold a plant; give `ground` for that activation once one has been destroyed. Story levels declare these values in their level definition; a level whose file is not at hand can be described by hand from the seed-selection screen, which shows the bans, and from the board.

`tests/fixtures/pools.json` holds ordered candidate lists read from the running game, keyed by level, cell kind and source cost, plus the two preview pools; the tests require the model to reproduce each of them in order.

`tests/fixtures/rank4-captures.json` retains ten normal-level input scenarios,
selection results, ordered-pool hashes, draw intervals, and trace hashes. It contains
no process or account data. Some source orders were reconstructed by reversing the
recorded processing order; those cases are marked. All starting offsets were
identified from recorded draws, so these are regression inputs rather than forecasts.
The model regenerates the draws from the default seed; the fixture does not supply them.

The original captures are not one continuous route: captures 1-3 belong to one
process, and 4-10 to a later process whose capture 4 begins at offset 2,874.
There are unrecorded gaps of 10 and 78 outputs before captures 7 and 9; what
consumed those outputs was not recorded.

`tests/fixtures/rank4-followups.json` contains the three subsequent Beach cases.
It retains their stated inputs, ordered-pool hashes, draw intervals and observed
plant-add order. B and Cactus include the preview sequences declared before play;
A identifies its offset retrospectively. `placed` expectations are asserted only
where terrain remained unchanged; Cactus's flooded column 6 is explicitly excluded.
`captured_stream_end` includes the separately counted outputs after selection,
while `stream_end` retains the predictor's selection-only meaning. Neither fixture
contains account or process data, and neither supplies captured random numbers to
the model.
