"""A level: its stage, its seed-bank bans, and the kind of each cell.

A level description is a small JSON file holding declared values only: the stage name,
the banned plants, the default cell kind, and the cells whose kind differs. The tide
state of a Beach cell changes during play, so it is supplied per activation instead of
stored here. Cells are written COLUMN-ROW, one-based, for example 3-1.
"""

import json
from pathlib import Path

from .plants import DATA, declared_costs, model_pool

LEVELS = DATA / "levels"


def parse_cell(text):
    column, _, row = str(text).partition("-")
    if not (column.isdigit() and row.isdigit()) or int(column) < 1 or int(row) < 1:
        raise ValueError("A cell is COLUMN-ROW with one-based integers, for example 3-1: " + repr(text))
    return int(column), int(row)


def format_cell(cell):
    return "%d-%d" % tuple(cell)


class Level:
    def __init__(self, record, path=None):
        self.record = record
        self.path = str(path) if path else None
        self.id = record.get("id") or (Path(path).stem if path else "level")
        self.name = record.get("name", self.id)
        self.stage = record["stage"]
        self.bans = list(record.get("bans") or ())
        self.default_kind = record.get("default_kind", "ground")
        self.width, self.height = record.get("width", 9), record.get("height", 5)
        self.cells = {parse_cell(cell): kind for cell, kind in (record.get("cells") or {}).items()}
        for location, kind in [("default_kind", self.default_kind)] + [(format_cell(cell), kind) for cell, kind in self.cells.items()]:
            if not isinstance(kind, str):
                raise ValueError("Cell kind at %s must be a string, got %r" % (location, kind))
        self.notes = record.get("notes", "")

    def kind_at(self, cell, overrides=None):
        """The kind of a cell: an override for this activation, else the description, else the default."""
        if overrides and cell in overrides:
            return overrides[cell]
        return self.cells.get(tuple(cell), self.default_kind)

    def contains(self, cell):
        return 1 <= cell[0] <= self.width and 1 <= cell[1] <= self.height

    def base_pool(self, document):
        """Registry-ordered candidates after the filters, the stage rule, and the bans."""
        return model_pool(document, self.stage, self.bans)

    def pool(self, kind, source_cost, document, kinds):
        """Candidates for a source of this effective cost standing on a cell of this kind."""
        if kind not in kinds:
            raise ValueError("Unknown cell kind %r; known: %s" % (kind, ", ".join(sorted(kinds))))
        costs = declared_costs(document)
        return [alias for alias in kinds[kind].filter(self.base_pool(document)) if costs[alias] > source_cost]

    def describe(self):
        return {"id": self.id, "name": self.name, "stage": self.stage, "bans": self.bans,
                "default_kind": self.default_kind, "width": self.width, "height": self.height,
                "cells": {format_cell(cell): kind for cell, kind in sorted(self.cells.items())}}


def available_levels():
    return sorted(path.stem for path in LEVELS.glob("*.json"))


def load_level(name):
    """A level by id from data/levels, or by path to a description file."""
    path = Path(name)
    if not path.exists():
        path = LEVELS / (str(name) + ".json")
    if not path.exists():
        raise ValueError("Unknown level %r; available: %s" % (name, ", ".join(available_levels())))
    return Level(json.loads(path.read_text()), path)
