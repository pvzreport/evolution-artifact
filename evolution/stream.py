"""The shared engine's outputs as one fixed sequence, addressed by offset.

The game default-seeds its engine once per process and never reseeds it, so every raw
output has a fixed position. A Stream memoises the sequence and runs the shuffle loop at
a position: a position in the stream is an integer, and a shuffle at a position is a
pure function of the pool and the position. The offsets recorded in captures are
positions in this sequence.
"""

from array import array

from .shuffle import DEFAULT_SEED, Mt19937, random_shuffle


class Stream:
    def __init__(self, seed=DEFAULT_SEED):
        self.seed = seed
        self._engine = Mt19937(seed)
        self._outputs = array("I")

    def output(self, position):
        """Raw output number `position`, counted from zero."""
        if position < 0:
            raise ValueError("A stream position cannot be negative")
        outputs, engine = self._outputs, self._engine
        while len(outputs) <= position:
            outputs.append(engine())
        return outputs[position]

    def shuffle(self, values, offset):
        """The permutation std::random_shuffle produces at this offset, and the offset after it."""
        cursor = _Cursor(self, offset)
        return random_shuffle(values, cursor), cursor.position


class _Cursor:
    """Reads the stream forward from a position, as the shuffle loop's draw callable."""

    __slots__ = ("stream", "position")

    def __init__(self, stream, position):
        self.stream, self.position = stream, position

    def __call__(self):
        value = self.stream.output(self.position)
        self.position += 1
        return value


_shared = {}


def shared(seed=DEFAULT_SEED):
    """The process-wide memoised stream for a seed."""
    if seed not in _shared:
        _shared[seed] = Stream(seed)
    return _shared[seed]
