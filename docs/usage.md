# Using and verifying

Supported Python: 3.9 or newer, standard library only. Use the latest Python for better performance, especially with `plan`. Run it from a checkout with `python3 -m evolution`, or install it editable with `pip install -e .` for the `pvz2-evolution` command. The tests run with `python3 -m unittest discover -s tests`.

## Commands

`predict`, `plan` and `pool` take `--game-version VERSION`, the game version whose plant data to use: one of those in `data/plants`, the newest by default. Use the version your game runs. The versions differ in their plants, so the same route can give different results, and every prediction names the version it assumed in its conditions.

```bash
python3 -m evolution predict --game-version 4.2.2 --previews 1x3
```

`predict` replays a stated route and prints what the game shows: a full restart, a sequence of previews, optionally some extra engine outputs, then an activation in a level.

- `--previews 1x6,4` lists the preview ranks in order; the default is none.
- `--offset N` adds N raw engine outputs consumed between the previews and the level.
- `--level ID` names a description in `data/levels`, or a path to one.
- `--rank 1|4` is the artifact rank of the activation; rank 4 needs `--activate`.
- `--activate COLUMN-ROW` is the activation cell. At rank 1 it only bounds the area; at rank 4 it defines the spawn pass.
- `--plant ALIAS[=COST]@CELL[:KIND]` gives one planted source, repeated in planting order, with its effective cost and optionally the kind of its cell for this activation. `--source ALIAS=COST` supplies a default cost for an alias.
- `--cell CELL=KIND` sets a cell's kind for this activation.
- `--json` prints the full result.

`plan` searches for a route that puts wanted plants on wanted cells: the fewest counted previews, then the fewest sources.

- `--want PLANT@CELL`, repeated. At rank 4 a Lily Pad and an ordinary plant may be wanted on the same cell.
- `--source ALIAS=COST[:KIND,KIND]`, repeated: a source available to plant, with its effective cost and optionally the kinds of cell it may be planted on. Optional at rank 4, where the spawn pass alone may satisfy the wants.
- `--rank`, `--activate` (default `2-2`), `--cell` and `--offset` as for `predict`.
- `--previews SEQ` is a fixed sequence run first; `--preview-rank R` (default 1) is the rank of the counted previews that follow it, tried from `--min-previews` to `--max-previews`.
- `--max-sources N` caps the sources; `--budget N` caps the shuffles tried per preview count (default 30000).
- `--json` prints the full result, including the recipe's complete `preview_sequence`.

`pool` prints an ordered candidate list: `--level`, `--kind` and `--cost` for a level pool, or `--preview evolution|spawn` for a preview pool. `build-plants PLANTTYPES.json PROPERTYSHEETS.json ARTIFACT.json --game-version VERSION --platform iOS|Android` builds one version's plant data from decoded game files into `data/plants/VERSION.json`.

```bash
python3 -m evolution predict --level egypt13 --activate 2-2 \
  --plant wallnut=50@1-1 --plant wallnut=50@2-1 --plant wallnut=50@3-1 \
  --plant wallnut=50@1-2 --plant wallnut=50@2-2 --plant wallnut=50@3-2 \
  --plant wallnut=50@1-3 --plant wallnut=50@2-3 --plant wallnut=50@3-3
```

```bash
python3 -m evolution predict --rank 4 --level beach3 --previews 1x11 --activate 5-3 \
  --plant puffshroom=0@5-3 --plant sunflower=50@6-4 --plant sunflower=50@4-2
```

```bash
python3 -m evolution plan --level memory-lane-s33-6-hard \
  --want aeonium@1-1 --want aeonium@1-3 --source sunflower=50 --source puffshroom=0
```

```bash
python3 -m evolution plan --rank 4 --level egypt13 --want kiwifruit@2-1 --want primalwallnut@3-3 --source wallnut=50
```

```bash
python3 -m evolution plan --level egypt13 --want eagleclaw@2-1 --source wallnut=50 --previews 1 --preview-rank 4
```

## Cells and kinds

Cells are written COLUMN-ROW, one-based, column first: `3-1` is the third column of the first row. The activation area is the 3x3 around the activation cell, clipped at the board's edges, and the rank-4 pass visits it down each column and then to the right.

A level description gives each cell's usual kind. The kinds are `ground`, `beach_shore` (a Beach cell right of the coast while dry, with no Lily Pad), `beach_pad` (a Lily Pad, bare or carrying an ordinary plant, over water or over dry shore), `beach_water` (a flooded cell with no Lily Pad), `pirate_plank`, and `none` (a cell that cannot hold a plant, such as a standing gravestone or open water beside the planks). These are defaults, so override the tide and pads for the activation: `--plant puffshroom=0@3-1:beach_pad` or `--cell 3-1=beach_water`. A destroyed gravestone is `--cell 3-1=ground`. The `--plant` list holds the sources above any pad; the pad itself is a kind, not a plant.

## Previews

A rank-1 preview evolves nine Sunflowers from the evolution pool; a rank-4 preview evolves three, places three Lily Pads, and spawns six plants from the spawn pool. Both pools come from the plant data of the version in use, and `pool --preview evolution|spawn` lists them. Each consumes a data-dependent but exactly replayable number of outputs. `predict --previews 1,4` prints what one rank-1 preview and then one rank-4 preview show after a fresh launch, and the offset the stream reaches after each.

`plan` reports the whole route it assumed as `preview_sequence`: the fixed `--previews` prefix followed by the counted previews of `--preview-rank`. Replay a recipe with exactly that sequence. The artifact screen opens on rank 1, so a route a player can follow starts with a rank-1 preview; the tool does not enforce that, so give `--previews 1` when counting rank-4 previews.

## Reading the output

Every selection is one row, at either rank, with the same fields: `action` (`evolve` for a transformation, `spawn` for a rank-4 addition), `cell`, `kind`, `source` and `cost` (null for a spawn), `candidates`, `result` (null when the pool was empty), `runners_up`, `start` and `end` (the offsets the shuffle spanned), and `placed`, whether the selected plant survived the placement check after the earlier effects. The text output marks a selection that did not survive with `(placement blocked)`; the only cases are a second Lily Pad on one cell and a replacement that a Lily Pad added beneath its source rejects.

A recipe lists its rows in `processing_order`, with the aliases usable on each cell in `sources` and `wanted` set on the rows that deliver a want, and its `planting_order`, the reverse of the transformation rows, which is what to plant, first to last. `stream_end` is the offset after the last selection shuffle.

## Checking a prediction against the game

Every prediction is printed with its conditions. Fully quit and relaunch the game, run exactly the listed previews and nothing else that uses the artifact, enter the level, set up the stated sources, pads and terrain, and activate the artifact at the stated rank once, before any automatic spawning. Save the prediction before playing and compare it with what appears. Reversing the planting order reverses the processing order of the transformations; the rank-4 pass keeps its cell order.

That entering or restarting a level consumes no outputs is an assumption of this workflow, consistent with every capture so far. Two captures recorded a few further outputs after the last selection, during the effects; their rule is not modelled, so `stream_end` does not establish the engine position for a later activation in the same process. For a second activation, restart, or state the extra draws with `--offset` when they are known.

Search prefers fewer previews and then fewer sources, and a recipe always replays through `predict` to the rows it shows: the search replays every recipe it returns. The budget bounds the search at each preview count; the counts at which it ran out are listed, and such a count does not establish that no recipe exists there. A source that cannot stand on any cell of the area is listed as not planned. A source with no candidates transforms into nothing, but at rank 4 it still occupies its cell and moves the spawns, so `plan` may use one.

The data files are described in [data.md](data.md).
