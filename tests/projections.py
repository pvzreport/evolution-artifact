"""The plant data that evidence recorded on a game version is replayed with.

A fixture file names the game version its evidence was recorded on in `game_version`, and a test file with inline
expectations names it in `CAPTURED_ON`. Evidence recorded on the bundled data's version replays with the bundled data.
Evidence recorded on an older version replays with that version's plant data, kept here as fixtures/plants/VERSION.json.
"""

from pathlib import Path

from evolution import Game, load_plants

KEPT = Path(__file__).resolve().parent / "fixtures" / "plants"


def game_on(version):
    """The model on the plant data of a game version: the bundled data, or the projection kept for that version."""
    bundled = load_plants()
    if bundled["game"]["version"] == version:
        return Game(bundled)
    path = KEPT / (version + ".json")
    if not path.is_file():
        raise ValueError("No plant data for game version %s: the bundled data is %s and %s is not kept"
                         % (version, bundled["game"]["version"], path.name))
    game = Game(load_plants(path))
    if game.version != version:
        raise ValueError("%s holds the plant data of game version %s" % (path.name, game.version))
    return game
