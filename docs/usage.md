# Using and verifying

Python 3.9 or newer, standard library only. Run it from a checkout with `python3 -m evolution`, or install it editable with `pip install -e .` for the `pvz2-evolution` command. The tests run with `python3 -m unittest discover -s tests`.

## Commands

- `predict` replays a stated scenario: a full restart, a sequence of previews, then an activation in a level. `--previews 1x6,4` lists preview ranks in order; `--level` names a level description; `--plant ALIAS=COST@CELL[:KIND]` gives each planted source in planting order with its effective cost; `--activate` gives the activation cell; `--cell CELL=KIND` sets a cell's kind for this activation; `--offset` adds extra engine outputs consumed before the level; `--json` prints the full result.
- `plan` searches for a number of previews and a planting order that place wanted plants on wanted cells: `--want PLANT@CELL`, `--source ALIAS=COST[:KIND,KIND]`, `--activate`, `--preview-rank`, and search budgets.
- `pool` prints an ordered candidate list for a level, a cell kind and a source cost, or a preview pool with `--preview evolution|spawn`.
- `build-plants PLANTTYPES.json PROPERTYSHEETS.json ARTIFACT.json` regenerates `data/plants.json` from decoded game files.

```bash
python3 -m evolution predict --level egypt13 --activate 2-2 \
  --plant wallnut=50@1-1 --plant wallnut=50@2-1 --plant wallnut=50@3-1 \
  --plant wallnut=50@1-2 --plant wallnut=50@2-2 --plant wallnut=50@3-2 \
  --plant wallnut=50@1-3 --plant wallnut=50@2-3 --plant wallnut=50@3-3
```

```bash
python3 -m evolution plan --level memory-lane-s33-6-hard \
  --want aeonium@1-1 --want aeonium@1-3 --source sunflower=50 --source puffshroom=0
```

```bash
python3 -m evolution pool --level pirate1 --kind pirate_plank --cost 0
```

## Cells and kinds

Cells are written COLUMN-ROW, one-based, column first: `3-1` is the third column of the first row. A level description gives each cell's usual kind. The kinds are `ground`, `beach_shore` (a Beach cell right of the coast while dry, with no Lily Pad), `beach_pad` (a plant standing on a Lily Pad), `beach_water` (a flooded cell with no Lily Pad), `pirate_plank`, and `none` (a cell that cannot hold a plant). The tide state of a Beach cell is not stored, so give it per activation: `--plant puffshroom=0@3-1:beach_pad` or `--cell 3-1=beach_water`.

## Previews

A rank-1 preview evolves nine Sunflowers from a 226-entry pool; a rank-4 preview evolves three and then spawns six plants from a 55-entry pool. Each consumes a data-dependent but exactly replayable number of engine outputs. Entering a level, or restarting one, consumes nothing. `predict --previews 1,4` prints what one rank-1 preview and then one rank-4 preview show after a fresh launch.

## Checking a prediction against the game

Every prediction is printed with its conditions. In short: fully quit and relaunch the game, run exactly the listed previews and nothing else that uses the artifact, enter the level directly, plant exactly the listed sources in the listed order inside the 3x3 around the activation cell, start the waves, and activate a rank-1 Evolution artifact once. The printed plants then appear on the printed cells. Repeating after another full restart gives the same results; reversing the planting order mirrors the grid, because the newest plant is processed first.

The data files are described in [data.md](data.md).
