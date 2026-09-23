# Using and verifying

Python 3.9 or newer, standard library only. Run it from a checkout with `python3 -m evolution`, or install it editable with `pip install -e .` for the `pvz2-evolution` command. The tests run with `python3 -m unittest discover -s tests`.

## Commands

- `predict` replays a stated scenario: a full restart, a sequence of previews, then an activation in a level. `--rank 1|4` selects the activation rank (default 1); `--previews 1x6,4` lists preview ranks in order; `--level` names a level description; `--plant ALIAS=COST@CELL[:KIND]` gives each planted source in planting order with its effective cost; `--activate` gives the activation cell; `--cell CELL=KIND` sets a cell's kind for this activation; `--offset` adds extra engine outputs consumed before the level; `--json` prints the full result.
- `plan` searches for a number of previews and a planting order that place wanted plants on wanted cells: `--rank`, `--want PLANT@CELL`, `--source ALIAS=COST[:KIND,KIND]`, `--activate`, `--preview-rank`, and search budgets. Activation rank and preview rank are independent. The first preview is rank 1; `--preview-rank` chooses the rank of later previews, and all counts include the first preview. JSON recipes contain the complete `preview_sequence`. Rank 4 can use zero sources; omit `--source` or use `--max-sources 0` to search only empty-area activations.
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

Cells are written COLUMN-ROW, one-based, column first: `3-1` is the third column of the first row. A level description gives each cell's usual kind. The kinds are `ground`, `beach_shore` (a Beach cell right of the coast while dry, with no Lily Pad), `beach_pad` (a Lily Pad, bare or supporting an ordinary plant), `beach_water` (a flooded cell with no Lily Pad), `pirate_plank`, and `none` (a cell that cannot hold a plant). The tide state of a Beach cell is not stored, so give it per activation: `--plant puffshroom=0@3-1:beach_pad` or `--cell 3-1=beach_water`.

Use `beach_pad` for a Lily Pad even when no ordinary plant stands on it. The `--plant` list contains the transformation sources above any support layer. Describe removed gravestones or changed supports through cell overrides. Edge activations retain their 3x3 area and skip positions outside the board.

## Rank-4 activations

An empty area needs no `--plant` arguments:

```bash
python3 -m evolution predict --rank 4 --level egypt13 --activate 2-2
python3 -m evolution plan --rank 4 --level egypt13 --want whitemelon@1-1 \
  --max-sources 0 --max-previews 0
```

Replay a recorded mixed Beach board at its known starting offset:

```bash
python3 -m evolution predict --rank 4 --level beach3 --activate 4-3 --offset 5740 \
  --plant puffshroom=0@3-2 --plant puffshroom=0@5-2 --plant seashroom=0@5-3 \
  --cell 4-2=beach_water --cell 4-3=beach_pad --cell 4-4=beach_water \
  --cell 5-2=beach_pad --cell 5-3=beach_water --cell 5-4=beach_pad
```

The result lists transformations first and rank-4 selections second. A cell can
receive both a replacement and a Lily Pad. JSON rows identify the `action`, selected
`result`, pool size, and draw interval. `placed` records whether the selected plant
passes the model's final cell check after earlier effects have changed the board.
Search checks this flag before accepting a wanted result. It can target a Lily Pad
and an ordinary plant on the same cell.

The follow-up captures in `tests/fixtures/rank4-followups.json` compare these flags
with actual plant-add calls. The water conflict selected Lily Pad as both the
Sea-shroom replacement and the extra support: the replacement had no add call,
and the user confirmed only a pad remained. The dry-shore Cactus route was:

```bash
python3 -m evolution predict --rank 4 --level beach3 --previews 1x11 --activate 5-3 \
  --plant puffshroom=0@5-3 --plant sunflower=50@6-4 --plant sunflower=50@4-2
```

Cactus was selected at 5-3 but had no add call after the extra pad was added.
The user confirmed column 5 stayed dry. Column 6 became flooded during the run and two
of its selected plants also had no add call; those cells are not evidence of a
complete unchanged-terrain forecast match. Keep the supplied terrain and supports
unchanged through placement when testing the full prediction.

Search prefers fewer previews and then fewer sources. The node budget bounds the
search at each preview count; an exhausted count is reported and does not establish
that no recipe exists there. The bundled normal-level descriptions include Egypt
1, 5, 13 and 14, Pirate Seas 2, Dark Ages 4, and Big Wave Beach 3.

## Previews

A rank-1 preview evolves nine Sunflowers from a 226-entry pool; a rank-4 preview evolves three and then spawns six plants from a 55-entry pool. Each consumes a data-dependent but exactly replayable number of engine outputs. `predict --previews 1,4` prints what one rank-1 preview and then one rank-4 preview show after a fresh launch. Use `--offset` for additional known draws; changing levels does not reset the engine.

The first preview after a fresh launch must be rank 1. For example, a plan with
`--preview-rank 4` and a total preview count of three means `1,4,4`, not three
rank-4 previews. Use the returned `preview_sequence` when replaying a recipe.

## Checking a prediction against the game

Every prediction is printed with its conditions. Fully quit and relaunch the game,
run the listed previews, account for any extra shared-engine draws, and enter the
level. Set up the stated sources, supports and terrain, then activate Evolution at
the requested rank before automatic spawning changes the route. Save the prediction
before playing and compare it with the subsequent result. Reversing source planting
order reverses ordinary processing order; the rank-4 pass keeps its column-first
cell order.

Entering or restarting a level consuming no shared-engine outputs is an accepted
modeling assumption for this workflow. `plan` assumes the stated fresh-launch
route and has no extra-offset input; `predict --offset` can account for known
additional draws. The output field `stream_end` ends at the last selection
shuffle. Captures also recorded extra draws during effects after selection;
their broader rules remain unmodeled, so this value does not by itself establish
the engine position for a later activation.

The data files are described in [data.md](data.md).
