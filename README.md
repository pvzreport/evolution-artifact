# The Evolution artifact is not random

*Independent research. Not affiliated with, endorsed by, or supported by Electronic Arts, PopCap Games, or the operator of the Chinese edition. Plants vs. Zombies is a trademark of Electronic Arts Inc.*

Plants vs. Zombies 2, iOS edition, version 4.2.2.394. The Evolution artifact is meant to turn a plant into a random more expensive plant. Its choice is made with libc++'s deprecated `std::random_shuffle`, whose engine is a function-local `static std::mt19937` inside `std::__rs_default::operator()`: default-seeded with 5489, never reseeded, and shared by every `std::random_shuffle` in the process. After a fresh launch the artifact produces the same results every time, and the artifact's previews on the artifact screen draw from the same engine, so the previews run before entering a level move along the same fixed sequence by a known amount.

This repository reproduces the game's draws offline. It contains only public algorithms and declared game data: MT19937, libc++'s shuffle loop and integer distribution, the plant list with declared costs and flags, and small descriptions of levels and cell kinds read from the game. No game code, assets, or capture tooling is included.

This repository exists so that the behaviour can be verified independently and corrected. It is published to document and help correct a software defect, and it reproduces no copyrighted game code or assets. The correction belongs in the game, in how the generator is seeded; once it is seeded properly, nothing here will match the game any more, which is how the fix can be confirmed.

## How a result is chosen

A candidate list is built per source plant, from the plant registry in a fixed order:

1. Seven declared-data filters remove disabled types, vines, heroes, consumables, and the artifact's own black list.
2. The level's stage rule keeps plants allowed in that world.
3. The level's seed-bank bans are removed.
4. The source's cell runs the game's planting check on every candidate. Its effect depends on the kind of cell: ordinary ground rejects only Cob Cannon, Intensive Carrot, and Lily Pad; a dry Beach shore cell admits Lily Pad; a plant standing on a Lily Pad loses six more plants, over water or over a dry shore cell; a flooded cell without a pad admits only the plants whose sheet declares CanLiveOnWaves; a Pirate plank rejects six plants that the deck admits. See [data/tile-rules.json](data/tile-rules.json).
5. A candidate qualifies when its declared cost is strictly greater than the source's effective cost.

The list is then shuffled with the shared engine and element 0 is the result. The newest plant in the 3x3 around the activation is processed first. Each preview on the artifact screen consumes a replayable number of engine outputs, and entering or restarting a level consumes none, so the previews run before a level decide where in the fixed sequence its activation starts, and the planting order decides which cell receives which result.

## Scope

- Rank-1 artifact activation, fresh launch, direct entry, sources at their stated effective cost. Rank-3 and rank-4 activations in a level also spawn plants from the same engine and are not modelled; only the rank-4 preview is.
- Only the previews are modelled as stream consumers. Other artifacts' previews, Endless mode, and the game's other shuffles use the same engine and are not modelled; the conditions printed with every prediction say what must not happen in between.
- A plant admitted on a flooded cell only by an equipped accessory (the water_master or sky_master boost) is not modelled, and the cells that rank-4 spawns land on are not modelled.
- iOS, and the same app on an Apple Silicon Mac; the engine lives in the system C++ library. Android is not covered.

## Use

[docs/usage.md](docs/usage.md) describes the commands, the cell kinds, and how to check a prediction against the game. [docs/data.md](docs/data.md) describes the data files and how to rebuild the plant file for another game version.

## License

MIT. See [LICENSE](LICENSE).
