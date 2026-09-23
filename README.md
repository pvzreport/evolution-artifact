# The Evolution artifact is not random

*Independent research. Not affiliated with, endorsed by, or supported by Electronic Arts, PopCap Games, or the operator of the Chinese edition. Plants vs. Zombies is a trademark of Electronic Arts Inc.*

Plants vs. Zombies 2, iOS edition, version 4.2.2.394. The Evolution artifact is meant to turn a plant into a random more expensive plant. Its choice is made with libc++'s deprecated `std::random_shuffle`, whose engine is a function-local `static std::mt19937` inside `std::__rs_default::operator()`: default-seeded with 5489, never reseeded, and shared by every `std::random_shuffle` in the process. After a fresh launch the artifact produces the same results every time, and the artifact's previews on the artifact screen draw from the same engine, so the previews run before entering a level move along the same fixed sequence by a known amount.

This repository reproduces the game's draws offline. It contains public algorithms, declared game data, and sanitized regression expectations: MT19937, libc++'s shuffle loop and integer distribution, the plant list with declared costs and flags, and small descriptions of levels and cell kinds read from the game. No game code, assets, or capture tooling is included.

This repository exists so that the behaviour can be verified independently and corrected. It is published to document and help correct a software defect, and it reproduces no copyrighted game code or assets. The correction belongs in the game, in how the generator is seeded; once it is seeded properly, nothing here will match the game any more, which is how the fix can be confirmed.

## How a result is chosen

A candidate list is built per source plant, from the plant registry in a fixed order:

1. Seven declared-data filters remove disabled types, vines, heroes, consumables, and the artifact's own black list.
2. The level's stage rule keeps plants allowed in that world.
3. The level's seed-bank bans are removed.
4. The source's cell runs the game's planting check on every candidate. Its effect depends on the kind of cell: ordinary ground rejects only Cob Cannon, Intensive Carrot, and Lily Pad; a dry Beach shore cell admits Lily Pad; a Lily Pad rejects seven additional plants compared with ordinary ground, over water or over a dry shore cell; a flooded cell without a pad admits only the plants whose sheet declares CanLiveOnWaves; a Pirate plank rejects six plants that the deck admits. See [data/tile-rules.json](data/tile-rules.json).
5. A candidate qualifies when its declared cost is strictly greater than the source's effective cost.

The list is then shuffled with the shared engine and element 0 is the result. The newest plant in the 3x3 around the activation is processed first. Each preview on the artifact screen consumes a replayable number of engine outputs. Restarting a level does not reset this process-wide stream; previews and any additional shared-engine draws determine the activation's starting offset.

At rank 4, a second pass visits the same 3x3 down each column, then moves right. It skips positions outside the board and selects from eligible plants costing at most 100. The pass sees the original occupants, before the queued transformations finish. An occupied dry-shore or bare-water cell can receive a Lily Pad beneath its source: captures cover Puff-shroom and Sunflower on dry shore, and Sea-shroom over water. A one-candidate pool consumes no random draws. The effects place plants in reverse selection order; the model applies the cell-kind checks again at placement, including a Lily Pad added by an earlier effect. Follow-up captures recorded a selected Lily Pad replacement over water and a selected Cactus replacement on dry shore receiving no plant-add call after the extra pad was added.

## Scope

- Rank-1 and rank-4 active-skill prediction and recipe search, with stated source costs, board conditions, and a known starting offset. Thirteen rank-4, level-30 normal-level captures cover empty and mixed areas, edges, gravestones, planks, water, and Lily Pads; the regression cases reproduce 100 selections and 10,437 selection-shuffle draws.
- Preview and activation shuffles are modelled. Automatic spawning, other artifacts, and unrelated shared-engine draws must be avoided or accounted for in the supplied route. `stream_end` is the end of selection shuffles: follow-ups recorded six further outputs after selection, whose triggering conditions remain outside this model. Passive buffs and resulting plant levels are outside the prediction output; the four rank-4 creation requests captured in Dark Ages 4 passed a level argument of -1, whose final stored-level effect remains unresolved.
- The cell model uses the supplied planting rules. Additional accessory-dependent planting permissions require corresponding plant data; changing terrain or occupants during the activation is not simulated.
- iOS, and the same app on an Apple Silicon Mac; the engine lives in the system C++ library. Android is not covered.

The original ten cases are retrospective replays. Follow-ups B and Cactus used forecasts declared before play after seven and eleven rank-1 previews respectively. All their selections matched. B also matched the placement calls; the Cactus run retained its dry target cell but column 6 flooded, so that column is excluded from placement assertions. Follow-up A confirmed an occupied dry-shore Lily Pad pool after the user removed the initial pads; its species replay remains retrospective. See [the follow-up fixture](tests/fixtures/rank4-followups.json).

## Use

[docs/usage.md](docs/usage.md) describes the commands, the cell kinds, and how to check a prediction against the game. [docs/data.md](docs/data.md) describes the data files and how to rebuild the plant file for another game version.

## License

MIT. See [LICENSE](LICENSE).
