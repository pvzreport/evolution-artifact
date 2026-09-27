"""The shared engine's outputs as one fixed sequence, addressed by offset.

The game default-seeds its engine once per process and never reseeds it, so every raw
output has a fixed position. A Stream memoises the sequence and runs the shuffle loop at
a position: a position in the stream is an integer, and a shuffle at a position is a
pure function of the pool and the position. The offsets recorded in captures are
positions in this sequence.
"""

from array import array

from .shuffle import DEFAULT_SEED, Mt19937, random_shuffle

_MASKS = [0, 0] + [(1 << (span - 1).bit_length()) - 1 for span in range(2, 1024)]


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

    def first(self, values, offset):
        """The element std::random_shuffle leaves first at this offset, and the offset after the shuffle.

        The loop fixes element 0 with its first accepted draw and never moves it again, so this runs the
        same draws without building the permutation; it equals the first element and end of `shuffle`.
        """
        if offset < 0:
            raise ValueError("A stream position cannot be negative")
        size = len(values)
        if size <= 1:
            return (values[0] if size else None), offset
        if size >= len(_MASKS):
            shuffled, end = self.shuffle(values, offset)
            return shuffled[0], end
        self.output(offset + 2 * size + 64)
        while True:
            try:
                return _first(values, size, offset, self._outputs)
            except IndexError:
                self.output(2 * len(self._outputs))


class _Cursor:
    """Reads the stream forward from a position, as the shuffle loop's draw callable."""

    __slots__ = ("stream", "position")

    def __init__(self, stream, position):
        self.stream, self.position = stream, position

    def __call__(self):
        value = self.stream.output(self.position)
        self.position += 1
        return value


def _first(values, size, position, outputs, masks=_MASKS):
    """The shuffle loop's draws from `position` for spans size down to 2, keeping only the first index."""
    mask = masks[size]
    while True:
        index = outputs[position] & mask
        position += 1
        if index < size:
            break
    span = size - 1
    while span > 1:
        if outputs[position] & masks[span] < span:
            span -= 1
        position += 1
    return values[index], position


_shared = {}


def shared(seed=DEFAULT_SEED):
    """The process-wide memoised stream for a seed."""
    if seed not in _shared:
        _shared[seed] = Stream(seed)
    return _shared[seed]
