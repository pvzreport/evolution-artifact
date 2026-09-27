from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution.shuffle import Mt19937, random_shuffle
from evolution.stream import Stream


class StreamTest(unittest.TestCase):
    def test_outputs_are_the_engine_outputs(self):
        engine, stream = Mt19937(), Stream()
        expected = [engine() for _ in range(5000)]
        self.assertEqual([stream.output(i) for i in (4999, 0, 306, 2874)], [expected[i] for i in (4999, 0, 306, 2874)])
        self.assertEqual([stream.output(i) for i in range(5000)], expected)

    def test_shuffle_at_an_offset_matches_the_engine(self):
        stream = Stream()
        for offset in (0, 1, 306, 2874, 35296):
            for size in (1, 2, 55, 226, 249):
                pool = ["p%d" % i for i in range(size)]
                engine = Mt19937()
                for _ in range(offset):
                    engine()
                expected = random_shuffle(pool, engine)
                result, end = stream.shuffle(pool, offset)
                self.assertEqual((result, end), (expected, engine.draws), (offset, size))

    def test_first_element_matches_the_full_shuffle(self):
        # The search reads only element 0 and the end of each shuffle. The fast path must agree with the full loop at
        # every size, including the power-of-two mask boundaries, and extend a stream that holds too few outputs.
        rng = random.Random(5489)
        full, fast = Stream(), Stream()
        for size in [0, 1, 2, 3, 4, 5, 8, 9, 16, 17, 55, 63, 64, 65, 127, 128, 129, 217, 227, 251, 256, 257, 1023, 1024, 1500]:
            pool = ["p%d" % i for i in range(size)]
            for offset in [0] + [rng.randrange(200000) for _ in range(12)]:
                shuffled, end = full.shuffle(pool, offset)
                self.assertEqual(fast.first(pool, offset), (shuffled[0] if shuffled else None, end), (size, offset))


if __name__ == "__main__":
    unittest.main()
