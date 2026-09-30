# Using and verifying

Supported Python: 3.9 or newer, standard library only. Use the latest Python for better performance, especially with `plan`. Run it from a checkout with `python3 -m evolution`, or install it editable with `pip install -e .` for the `pvz2-evolution` command. The tests run with `python3 -m unittest discover -s tests`.

## Commands

The commands use the bundled plant data, of game version 4.2.4, and every prediction names that version in its conditions. Versions differ in their plants, so on another version the same route can give different results. To replay evidence recorded on another version, run the model from Python on that version's plant data file: `scenario` and `search_recipe` take a `Game`, and `Game(load_plants(path))` is one on the plant data in `path`. The tests replay the captures taken on 4.2.2 this way, with `tests/fixtures/plants/4.2.2.json`.

`predict` replays a stated route and prints what the game shows: a full restart, the route's steps, optionally some extra engine outputs, then the entry of a level and an activation in it.

- `--route E1x6,E4` lists the route's steps in order: the Evolution artifact's rank-1, rank-3 and rank-4 previews as `E1`, `E3` and `E4`, and the Devolution artifact's rank-1 and rank-4 previews as `D1` and `D4`, each optionally repeated as `xCOUNT`. `D1x2,E1,E3` is two Devolution previews, then a rank-1 and a rank-3 Evolution preview. The default is none.
- `--preview-cost COST` is the effective cost of the Evolution previews' Sunflowers, which the account's modifiers can change; the default is the declared cost. `predict` and `plan` point out a listed Sunflower cost that differs from it.
- `--offset N` adds N raw engine outputs consumed between the route and entering the level, before the level's own entry shuffles.
- `--level ID` names a description in `data/levels`, or a path to one.
- `--rank 1|4` is the artifact rank of the activation; rank 4 needs `--activate`.
- `--activate COLUMN-ROW` is the activation cell. At rank 1 it only bounds the area; at rank 4 it defines the spawn pass.
- `--plant ALIAS[=COST]@CELL[:KIND]` gives one planted source, repeated in planting order, with its effective cost and optionally the kind of its cell for this activation. `--source ALIAS=COST` supplies a default cost for an alias.
- `--cell CELL=KIND` sets a cell's kind for this activation.
- `--json` prints the full result.

`plan` searches for a route and a recipe that put wanted plants on wanted cells: the shortest route of the chosen style, then the fewest sources. [Planning](#planning) gives the rules.

- `--want PLANT@CELL`, repeated. At rank 4 a Lily Pad and an ordinary plant may be wanted on the same cell.
- `--source ALIAS=COST[:KIND,KIND]`, repeated: a source available to plant, with its effective cost and optionally the kinds of cell it may be planted on. Optional at rank 4, where the spawn pass alone may satisfy the wants.
- `--rank`, `--activate` (default `2-2`), `--cell` and `--offset` as for `predict`.
- `--done ROUTE` lists the steps already run since a full restart, in order, as for `--route`, for example `E1x3,E4` or `D1,E1`; the route continues from there. The default is none.
- `--style simple|shorter|shortest` bounds the switches between the planned steps: at most one, at most three, or any number (default `shorter`).
- `--allow STEPS` lists the steps the planned route may use, for example `E1,E4`; the default is every known preview, `E1,E3,E4,D1,D4`.
- `--max-length N` caps the length planned after the done steps, a preview counting 1 (default 100). `--preview-cost` as for `predict`.
- `--max-sources N` caps the sources (default 9).
- `--json` prints the full result, including the recipe's complete `route`.

`pool` prints an ordered candidate list: `--level`, `--kind` and `--cost` for a level pool, or `--preview evolution|spawn` for a preview pool, where `--cost` is the previews' Sunflower cost. `build-plants PLANTTYPES.json PROPERTYSHEETS.json ARTIFACT.json --game-version VERSION --platform iOS|Android` builds the plant data of the version the decoded game files come from and writes it over `data/plants.json`; [data.md](data.md) describes moving to a newer version.

```bash
python3 -m evolution predict --level egypt13 --activate 2-2 \
  --plant wallnut=50@1-1 --plant wallnut=50@2-1 --plant wallnut=50@3-1 \
  --plant wallnut=50@1-2 --plant wallnut=50@2-2 --plant wallnut=50@3-2 \
  --plant wallnut=50@1-3 --plant wallnut=50@2-3 --plant wallnut=50@3-3
```

```bash
python3 -m evolution predict --rank 4 --level beach3 --route E1x11 --activate 5-3 \
  --plant puffshroom=0@5-3 --plant sunflower=50@6-4 --plant sunflower=50@4-2
```

```bash
python3 -m evolution plan --level memory-lane-s33-6-hard \
  --cell 3-1=beach_shore --cell 3-2=beach_shore --cell 3-3=beach_shore \
  --want aeonium@1-1 --want aeonium@1-3 --source sunflower=50 --source puffshroom=0
```

```bash
python3 -m evolution plan --rank 4 --level egypt13 --want kiwifruit@2-1 --want primalwallnut@3-3 --source wallnut=50
```

```bash
python3 -m evolution plan --level egypt1 --want kernelpult@1-1 --source wallnut=50 --done E1x2
```

## Cells and kinds

Cells are written COLUMN-ROW, one-based, column first: `3-1` is the third column of the first row. The activation area is the 3x3 around the activation cell, clipped at the board's edges, and the rank-4 pass visits it down each column and then to the right.

A level description gives each cell's kind at level start. The kinds are `ground`, `beach_shore` (a Beach cell right of the coast while dry, with no Lily Pad), `beach_pad` (a Lily Pad, bare or carrying an ordinary plant, over water or over dry shore), `beach_water` (a flooded cell with no Lily Pad), `pirate_plank`, and `none` (a cell no source can occupy and no spawn reaches: a standing gravestone, a plant the level protects, or open water beside the planks). These are defaults, so override the tide and pads for the activation: `--plant puffshroom=0@3-1:beach_pad` or `--cell 3-1=beach_water`. A destroyed gravestone is `--cell 3-1=ground`. The `--plant` list holds the sources above any pad; the pad itself is a kind, not a plant.

## Previews

The artifact screen shows each artifact's previews, and tapping an artifact plays its rank-1 preview. An Evolution preview is an activation on the screen's display board, a Beach-stage board of shore cells with the activation cell 4-2. A rank-1 preview evolves nine Sunflowers, processed 5-3, 5-2, 5-1, 4-3, 4-2, 4-1, 3-3, 3-2, 3-1. A rank-3 preview evolves three at 3-3, 3-2, 3-1 and nothing more. A rank-4 preview evolves the same three, then its spawn pass adds a Lily Pad beneath each of them and a spawn on 4-1, 4-2, 4-3, 5-1, 5-2, 5-3. The Sunflowers have the account's effective cost, given with `--preview-cost`; the pools come from the plant data, and `pool --preview evolution --cost COST` and `pool --preview spawn` list them.

The preview's effects then run like a level's: a pad rejects some replacements, so such a cell shows a bare pad, and a placed Draftodil shuffles the plant objects of its row, one output per object beyond the first with the engine's rejection rule, where a Lily Pad, bare or beneath a plant, is not an object. Each Evolution preview entry lists its selections as rows, its `effects` with the number of objects each shuffle covered and the offsets it spanned, its `selection_end`, and its `end`, the position the next action starts from. `predict --route E1,E4 --preview-cost COST` prints what one rank-1 preview and then one rank-4 preview show after a fresh launch at that cost, and the offset the stream reaches after each. To find an account's cost, compare its first preview after a relaunch with that command for the costs in question.

The Devolution artifact's rank-1 preview, `D1`, draws as its three zombies are devolved: for each, a 10-entry shuffle and then a 15-entry shuffle of the same engine, and nothing else. Its rank-4 preview, `D4`, devolves ten zombies the same way, 20 shuffles; tapping rank 4 on the Devolution screen runs it, after the rank-1 preview that tapping the artifact plays. The captures record the shuffles' draws but not their lists; at the seven positions captured for `D1` and the six for `D4`, after a fresh launch, after other Devolution previews and after Evolution previews, only these sizes replay every shuffle. A Devolution entry lists its `shuffles`, with the objects each covered and the offsets it spanned, and its `end`. Each preview, of either artifact, therefore consumes a data-dependent but exactly replayable number of outputs. Every step entry also gives its number in the route, `step`, its `kind`, here `preview`, its `name` as normalised, its `artifact` and `rank`, and `start`, the position it starts from.

A prediction lists its route's step names as `route`, one per step run, their entries as `steps`, and the position after them as `offset_after_route`. `plan` reports the whole route it assumed as the recipe's `route`: the done steps followed by the planned ones, with their entries in `steps`. Replay a recipe with exactly that route.

## Planning

A route is the sequence of steps run after a full restart, from those `--allow` lists. Tapping an artifact plays its rank-1 preview, so a route with previews starts with E1 or D1, the Evolution previews after a D1 start again with E1, and `--done` follows the same rule. A switch is a step that differs from the one before it; the first planned step is compared with the last done one. The styles bound the switches among the planned steps: `simple` allows one, so after a restart its routes are previews of one kind followed by previews of another, such as E1 previews followed by E4 previews; `shorter` allows three; `shortest` any number.

`plan` tries routes in increasing length, a preview counting 1, from the done steps alone up to `--max-length` more, and returns the shortest route of the style that has a recipe. Among the routes of that length it prefers the fewest sources, then the fewest switches, then the first in step order, comparing the planned steps one by one: E1, E3 and E4, then D1 and D4. Routes that reach the same stream position enter the level at the same position, so each distinct position is searched once, for the route this order prefers there. The result lists the route's `planned` steps and `switches`, the `style`, the `allowed` steps, `max_length`, and `entry_positions_searched`, the number of distinct positions searched.

At each entry position the search walks sequences of source pools breadth first, fewest sources first; sources with the same pool count as one, whatever their aliases or costs. A sequence grows only while its sources fit the cells of the area, counted per kind of cell. Whether it or any sequence grown from it yields a recipe depends only on its state: the position its last shuffle ended at and, among its sources that may stand on the same kinds of cell, how many there are and how many of each wanted plant they produced, counted up to the number wanted. The search keeps the first sequence to reach each state and drops the others, so it returns the recipe that walking every sequence returns: the fewest sources at that position, and among those the first sequence, taking larger pools first. A memory guard caps the states stored at one position at 1,000,000. A position where the cap stopped the search is listed in `state_cap_reached` and printed with the number of sources among whose recipes it stopped; a recipe there with that many sources or more may have been missed.

The tests hold this search to the one that walks every sequence. At 34,992 level entries drawn at random for 34 requests, on uniform ground, ground with Beach shore, Lily Pads and Pirate planks, at both ranks and with one to eight cost bands, both returned the same recipe, or none; `tests/fixtures/search-equality.json` keeps 635 of those entries, 389 with a recipe.

Search time, measured in CPython 3.14 in one process, for requests with the default nine sources at most. Sources in n cost bands are the first n of `wallnut=50`, `puffshroom=0`, `potatomine=25`, `holonut=75`, `peashooter=100`, `twinsunflower=125`, `snowpea=150` and `repeater=200`, each band with its own pool. Egypt 1 is activated at 2-2 with Kernel-pults wanted at 1-1, 2-2 and 3-3, or Peashooters at 1-1 and 1-3 and Burdock batters at 3-1 and 3-3; Big Wave Beach 3 is activated at 4-2, with 4-2 given as dry shore, and Kernel-pults wanted on the ground cell 3-1 and the shore cells 4-3 and 5-3. The time per entry position is over 100 positions drawn below 1,000,000; the simple search is `plan` from a restart with `--style simple` and up to length 100, until it returns.

| Request | Per entry position, mean | Slowest of 100 | Simple search up to length 100 |
|---|---|---|---|
| The two Aeoniums of the example above | 5 ms | 7 ms | 0.3 s: 6 previews, 75 positions searched |
| Egypt 1, rank 1, three Kernel-pults, 1 band | 0.6 ms | 0.8 ms | 1.7 s: no recipe, 6,357 positions |
| Egypt 1, rank 1, three Kernel-pults, 4 bands | 10 ms | 13 ms | 0.3 s: 4 previews, 37 positions |
| Egypt 1, rank 1, three Kernel-pults, 8 bands | 38 ms | 43 ms | 1.2 s: 4 previews, 37 positions |
| Egypt 1, rank 4, three Kernel-pults, 8 bands | 71 ms | 134 ms | 0.2 s: 1 preview, 3 positions |
| Egypt 1, rank 1, two Peashooters and two Burdock batters, 4 bands | 10 ms | 13 ms | 2.5 s: 12 previews, 259 positions |
| Egypt 1, rank 1, two Peashooters and two Burdock batters, 8 bands | 40 ms | 44 ms | 4.1 s: 7 previews, 100 positions |
| Egypt 1, rank 4, two Peashooters and two Burdock batters, 8 bands | 58 ms | 96 ms | 2.9 s: 5 previews, 54 positions |
| Big Wave Beach 3, rank 4, three Kernel-pults, 4 bands | 55 ms | 308 ms | 2.2 s: 4 previews, 37 positions |
| Big Wave Beach 3, rank 4, three Kernel-pults, 8 bands | 470 ms | 1.7 s | 12.3 s: 3 previews, 22 positions |

A request without a recipe searches every position its style reaches. Within length 100 that is 6,357 positions for `simple`, 30,493 for `shorter` and 34,470 for `shortest`, or 1,159, 6,443 and 9,337 with `--allow E1,E4`, so such a search takes about that many times the time per entry position. At 20 entry positions of each request, a search stored at most 4,815 states on uniform ground and 38,988 on ground and shore, both with eight bands, against the cap of 1,000,000.

## Reading the output

Every selection is one row, at either rank and in a preview alike, with the same fields: `action` (`evolve` for a transformation, `spawn` for a rank-4 addition), `cell`, `cell_kind`, `source` and `cost` (null for a spawn), `candidates`, `result` (null when the pool was empty), `runners_up`, `start` and `end` (the offsets the shuffle spanned), `placed`, whether the selected plant survived the placement check after the earlier effects, and `beneath`, whether a spawn is the Lily Pad added beneath an occupied cell. The text output marks a selection that did not survive with `(placement blocked)`; the only cases are a second Lily Pad on one cell and a replacement that a Lily Pad added beneath its source rejects. A prediction and a recipe search also report `preview_cost`, the Sunflower cost their previews assumed.

A prediction in a level also reports `level_entry_offset`, the position at which the level is entered, `entry_effects`, one row per gravestone bag its entry shuffled with the bag's object count and the offsets the shuffle spanned, and `activation_offset`, the position the activation's first shuffle starts from; the text output gives the bag sizes, their total draws and the activation offset in one line, and the per-bag offsets only in the JSON. A recipe lists its rows in `processing_order`, with the aliases usable on each cell in `sources` and `wanted` set on the rows that deliver a want, and its `planting_order`, the reverse of the transformation rows, which is what to plant, first to last, together with the same `level_entry_offset`, `entry_effects` and `activation_offset`; its text output prints the entry offset and the activation start. `stream_end` is the offset after the last selection shuffle.

## Checking a prediction against the game

Every prediction is printed with its conditions. Fully quit and relaunch the game, run exactly the route's previews and nothing else that uses an artifact, letting each Evolution preview's effects finish and each Devolution preview devolve its three zombies, enter the level, set up the stated sources, pads and terrain, and activate the artifact at the stated rank once, promptly and before any automatic spawning. Save the prediction before playing and compare it with what appears. Reversing the planting order reverses the processing order of the transformations; the rank-4 pass keeps its cell order.

Entering the level is part of the route. A level whose description lists `entry_shuffles` shuffles those gravestone bags with the shared engine as it loads, before anything is planted, and the model replays them after the route and any `--offset`; a level whose definition declares no such action consumes nothing at entry, as every capture in such levels shows, and a description written by hand or from a capture lists none because none were read. Enter the level once, after the route and any stated extra outputs, and do not restart it: whether a restart repeats the entry shuffles was not measured, so restart the game instead. A level activation's `stream_end` is the end of its selections. Its placement effects can draw further outputs (a Draftodil's row shuffle counts every plant in its row, which only the display board makes known), and a capture has recorded outputs from outside the artifact a few seconds after them, so `stream_end` does not establish the engine position for a later activation in the same process. For a second activation, restart the game.

Search prefers shorter routes and then fewer sources, and a recipe always replays through `predict` to the rows it shows: the search replays every recipe it returns. A position where the state cap stopped the search is listed, and there it does not establish that no recipe exists. A source that cannot stand on any cell of the area is listed as not planned. A source with no candidates transforms into nothing, but at rank 4 it still occupies its cell and moves the spawns, so `plan` may use one.

The data files are described in [data.md](data.md).
