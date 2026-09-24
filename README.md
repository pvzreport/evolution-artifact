# The Evolution artifact is not random

*Independent research. Not affiliated with, endorsed by, or supported by Electronic Arts, PopCap Games, or the operator of the Chinese edition. Plants vs. Zombies is a trademark of Electronic Arts Inc.*

Plants vs. Zombies 2, iOS edition. The Evolution artifact is meant to turn a plant into a random more expensive plant. Its choice is made with libc++'s deprecated `std::random_shuffle`, whose engine is a function-local `static std::mt19937` inside `std::__rs_default::operator()`: default-seeded with 5489, never reseeded, and shared by every `std::random_shuffle` in the process. After a fresh launch the artifact produces the same results every time, and the artifact's previews on the artifact screen draw from the same engine, so the previews run before entering a level move along the same fixed sequence by a known amount.

This repository reproduces the game's draws offline. It contains public algorithms, declared game data, and sanitized regression expectations: MT19937, libc++'s shuffle loop and integer distribution, the plant list with declared costs and flags, and small descriptions of levels and cell kinds read from the game. No game code, assets, or capture tooling is included.

This repository exists so that the behaviour can be verified independently and corrected. It is published to document and help correct a software defect, and it reproduces no copyrighted game code or assets. The correction belongs in the game, in how the generator is seeded; once it is seeded properly, nothing here will match the game any more, which is how the fix can be confirmed.

## How a result is chosen

A candidate list is built per source plant, from the plant registry in a fixed order:

1. Seven declared-data filters remove disabled types, vines, heroes, consumables, and the artifact's own black list.
2. The level's stage rule keeps plants allowed in that world.
3. The level's seed-bank bans are removed.
4. The source's cell runs the game's planting check on every candidate. Its effect depends on the kind of cell: ordinary ground rejects only Cob Cannon, Intensive Carrot, and Lily Pad; a dry Beach shore cell admits Lily Pad; a Lily Pad, bare or carrying a plant, rejects seven more plants than ordinary ground, over water or over a dry shore cell; a flooded cell without a pad admits only the plants whose sheet declares CanLiveOnWaves; a Pirate plank rejects six plants that the deck admits. See [data/tile-rules.json](data/tile-rules.json).
5. A candidate qualifies when its declared cost is strictly greater than the source's effective cost.

The list is shuffled with the shared engine and element 0 is the result. The plants in the 3x3 around the activation cell are processed newest first. The artifact screen's previews are the same function on its display board: a rank-1 preview plants nine Sunflowers around cell 4-2 and evolves them, and a rank-4 preview plants three in column 3 and runs the rank-4 pass described below. Their Sunflowers have the account's effective cost, which is an input. Each preview therefore consumes a replayable number of engine outputs, and every capture so far is consistent with entering or restarting a level consuming none, so the previews run before a level decide where in the fixed sequence its activation starts, and the planting order decides which cell receives which result.

At rank 4 a second pass follows. It visits the same 3x3 down each column and then to the right, skips positions outside the board, and for each cell shuffles the candidates the cell admits whose declared cost is at most 100. An occupied cell admits nothing, except that an occupied shore or water cell admits a Lily Pad beneath its plant, a one-candidate shuffle that consumes no outputs. The effects are then applied in reverse selection order, and each selected plant is checked again against its cell at that moment: a Lily Pad placed earlier turns its cell into a pad, which rejects some replacements and leaves the bare pad where the source stood, and a second Lily Pad on one cell is dropped.

The effects can draw from the engine too. Placing a Draftodil shuffles the plant objects of its row: one output per object beyond the first, with the engine's rejection rule, where a Lily Pad, bare or beneath a plant, is not an object, a replaced source is gone, and the Draftodil itself counts. On the display board every plant is known, so a preview that produces a Draftodil is replayed to the output. Each rule above is backed by a capture in the regression fixtures or by a played check recorded with it, including a bare Lily Pad in a Draftodil's row and a row shuffle in which the engine rejected values.

## How the package is put together

The engine is default-seeded once per process and never reseeded, so its raw outputs form one fixed sequence. The package memoises that sequence and addresses it by offset: an engine position is an integer, a shuffle at a position is a pure function of the pool and the position, and the offsets recorded in captures are positions in this sequence.

An activation is one function of the board, the plantings, the rank and a starting offset. It returns one row per selection, in selection order, with the same fields at either rank, including whether the selected plant was placed. A preview is that function applied to the display board, followed by the draws of its placement effects. `predict` prints the result for a stated route.

`plan` searches the same function for a recipe. Transformation results depend only on the sequence of pools shuffled, never on cells, and at rank 4 the spawn pass depends only on which cells are occupied. The search therefore walks sequences of pools breadth first, fewest sources first, and for each sequence whose results cover the wanted plants that no spawn could provide, walks the area deciding each cell occupied or free while carrying the spawn offset. A recipe is accepted only when its full replay places every wanted plant, so a recipe always replays through `predict` to the rows it promised. Preview counts are tried in increasing order.

## Scope

- Rank-1 and rank-4 activations, prediction and recipe search, with stated source costs, board conditions and a stated route. Thirteen captured rank-4 activations in normal levels cover empty and mixed areas, edges, gravestones, planks, water and Lily Pads, including the two placement conflicts; the regression cases reproduce all 100 selections and 10,437 selection draws, and for the three follow-up captures the recorded plant-add order where the terrain stayed unchanged. Two display-board captures reproduce 153 preview selections, all 36,152 recorded outputs including the row shuffles of two Draftodils, and the recorded add order of every preview.
- Preview and activation shuffles are modelled, and the Draftodil placement effect of the previews; no other plant's placement has drawn in any capture. Other artifacts, automatic spawning and any other shared-engine draws must be avoided or stated as an extra offset. A level activation's `stream_end` is the end of its selections: its placement effects depend on every plant in the affected rows, and one capture recorded outputs from outside the artifact during a level's effects, so the engine position after a level activation is not established by this package.
- Plant levels are not modelled; the four rank-4 creation requests captured in Dark Ages 4 passed a level argument of -1 whose final effect is unresolved. A planting permission granted only by an equipped accessory needs the corresponding plant data. Terrain that changes during the activation is not simulated.
- Game versions: the plant data is kept per game version in `data/plants`; the newest is the default, and `--game-version` selects another. A version's declared data is assumed to be the same on every platform. Only the plant data is versioned; the cell kinds, the preview structure and the level descriptions are shared by every version.
- iOS, and the same app on an Apple Silicon Mac; the engine lives in the system C++ library. Android is not covered.

## Use

[docs/usage.md](docs/usage.md) describes the commands, the cell kinds, the output, and how to check a prediction against the game. [docs/data.md](docs/data.md) describes the data files, the level descriptions and the capture fixtures.

## License

MIT. See [LICENSE](LICENSE).
