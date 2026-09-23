"""libc++'s two-argument std::random_shuffle, replayed from std::mt19937's default seed.

The game shuffles the Evolution artifact's candidate list with the deprecated
two-argument std::random_shuffle. That overload has no generator parameter: it
draws from a function-local `static std::mt19937` inside libc++'s
`__rs_default::operator()`, which is default-constructed (seed 5489) and never
reseeded. Every std::random_shuffle in the process shares that one engine.

This module reproduces the engine, libc++'s uniform_int_distribution (with its
rejection loop, which is why a shuffle consumes a data-dependent number of
outputs), and the shuffle loop itself.
"""

MASK32 = 0xFFFFFFFF
MASK64 = 0xFFFFFFFFFFFFFFFF
DEFAULT_SEED = 5489  # std::mt19937::default_seed


class Mt19937:
    """The standard MT19937 with std::mt19937's default seed and full 32-bit output."""

    def __init__(self, seed=DEFAULT_SEED):
        self.state = [seed & MASK32]
        for index in range(1, 624):
            previous = self.state[-1]
            self.state.append((1812433253 * (previous ^ (previous >> 30)) + index) & MASK32)
        self.index = 624
        self.draws = 0

    def clone(self):
        """An independent engine at this exact position."""
        copy = Mt19937.__new__(Mt19937)
        copy.state = list(self.state)
        copy.index = self.index
        copy.draws = self.draws
        return copy

    def __call__(self):
        if self.index >= 624:
            for index in range(624):
                combined = (self.state[index] & 0x80000000) | (self.state[(index + 1) % 624] & 0x7FFFFFFF)
                self.state[index] = self.state[(index + 397) % 624] ^ (combined >> 1)
                if combined & 1:
                    self.state[index] ^= 0x9908B0DF
            self.index = 0
        value = self.state[self.index]
        self.index += 1
        self.draws += 1
        value ^= value >> 11
        value ^= (value << 7) & 0x9D2C5680
        value ^= (value << 15) & 0xEFC60000
        value ^= value >> 18
        return value & MASK32


def independent_bits(engine, width):
    """libc++'s __independent_bits_engine over a 32-bit engine, 64-bit result."""
    engine_digits, working_digits = 32, 64
    engine_range = 1 << engine_digits
    per_call_bits = engine_range.bit_length() - 1

    count = width // per_call_bits + (1 if width % per_call_bits else 0)
    if count == 0:
        return 0
    chunk = width // count
    low = (engine_range >> chunk) << chunk if chunk < working_digits else 0
    if engine_range - low > low // count:
        count += 1
        chunk = width // count
        low = (engine_range >> chunk) << chunk if chunk < working_digits else 0
    narrow = count - width % count
    high = (engine_range >> (chunk + 1)) << (chunk + 1) if chunk < working_digits - 1 else 0
    narrow_mask = MASK32 >> (engine_digits - chunk) if chunk > 0 else 0
    wide_mask = MASK32 >> (engine_digits - (chunk + 1)) if chunk < engine_digits - 1 else MASK32

    assembled = 0
    for position in range(count):
        if position < narrow:
            limit, shift, mask = low, chunk, narrow_mask
            shift_fits = chunk < working_digits
        else:
            limit, shift, mask = high, chunk + 1, wide_mask
            shift_fits = chunk < working_digits - 1
        while True:
            value = engine()
            if value < limit:
                break
        assembled = ((assembled << shift) & MASK64) if shift_fits else 0
        assembled += value & mask
    return assembled


def uniform_int(engine, low, high):
    """libc++'s uniform_int_distribution<ptrdiff_t>::operator()(g, {low, high})."""
    if high < low:
        raise ValueError("The distribution requires low <= high")
    span = (high - low + 1) & MASK64
    if span == 1:
        return low
    if span == 0:
        return low + independent_bits(engine, 64)
    width = span.bit_length() - 1
    if span & (MASK64 >> (64 - width)):
        width += 1
    while True:
        value = independent_bits(engine, width)
        if value < span:
            return low + value


def random_shuffle(values, draw):
    """The body of libc++'s two-argument std::random_shuffle, returned as a new list.

    `draw` is any zero-argument callable returning the next raw 32-bit output: an
    engine, a recorded sequence, or a stream cursor. The loop runs forward from the
    front of the range and draws one index per position, so element 0 of the result
    is what the artifact selects. For spans below 2**32 the distribution reduces to
    one masked 32-bit output per attempt, rejected while it is not below the span;
    that path is written out here and checked against `uniform_int` by the tests.
    """
    result = list(values)
    distance = len(result)
    if distance <= 1:
        return result
    first, last = 0, distance - 1
    distance -= 1
    while first < last:
        span = distance + 1
        if span < MASK32:
            mask = (1 << (span - 1).bit_length()) - 1
            while True:
                index = draw() & mask
                if index < span:
                    break
        else:
            index = uniform_int(draw, 0, distance)
        if index != 0:
            result[first], result[first + index] = result[first + index], result[first]
        first += 1
        distance -= 1
    return result
