"""Replay a stated scenario: previews, then an activation in a level.

Nothing here discovers the game's state. The scenario states it: a full process
restart, a sequence of previews, optionally extra raw outputs, then the plants standing
in the 3x3 around the activation cell in the order they were planted. The result is
what the engine, started from seed 5489, produces for exactly that history. Newly
planted sources are processed newest first, and each source draws from the pool of
its level, its cell's kind, and its effective cost.
"""

from .activation import Planting, area_around, predict_level
from .shuffle import Mt19937

CONDITIONS = [
    "Start after a full process restart (seed 5489, offset 0).",
    "Run exactly the listed previews, each one complete, and nothing else that uses the artifact "
    "before entering the level. The first preview must be rank 1; later previews may be rank 1 or 4.",
    "Accepted modeling assumption: entering or restarting a level consumes no shared-engine outputs.",
    "Same level as described, sources at the listed effective cost (no discounts unless included), "
    "activate once while every source remains and before any automatic spawning.",
    "Each cell's kind must match the board at activation: Beach cells right of the coast are shore when dry, "
    "water when flooded without a pad, and pad whenever a Lily Pad is present, bare or occupied. "
    "Keep terrain and supports unchanged until the effects finish, apart from the predicted additions.",
    "Plant exactly the listed sources in the listed order inside the 3x3 around the activation cell; "
    "the newest plant is processed first.",
]


def scenario(document, kinds, previews, sequence=(), level=None, plantings=(), activation=None,
             overrides=None, offset=0, rank=1):
    """Replay previews, optional extra raw outputs, then an optional activation."""
    if offset < 0:
        raise ValueError("The extra offset cannot be negative")
    engine = Mt19937()
    preview_rows = previews.advance(engine, list(sequence))
    after_previews = engine.draws
    for _ in range(offset):
        engine()
    entry = engine.draws
    results = predict_level(document, kinds, level, list(plantings), engine, activation, overrides, rank) if level else []
    return {"previews": preview_rows, "offset_after_previews": after_previews, "extra_offset": offset,
            "level": level.describe() if level else None, "level_entry_offset": entry,
            "activation": {"column": activation[0], "row": activation[1]} if activation else None, "rank": rank,
            "results": results, "stream_end": engine.draws, "conditions": list(CONDITIONS)}
