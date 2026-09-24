from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
