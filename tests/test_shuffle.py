from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evolution import DEFAULT_SEED, Mt19937, random_shuffle
from evolution.shuffle import uniform_int, MASK32

# std::mt19937's first outputs after default construction; also the first eight raw
# outputs recorded in every fresh-launch capture of the game.
FIRST_OUTPUTS = [3499211612, 581869302, 3890346734, 3586334585, 545404204, 4161255391, 3922919429, 949333985]


class ShuffleTest(unittest.TestCase):
    def test_default_seed_and_first_outputs(self):
        self.assertEqual(DEFAULT_SEED, 5489)
        engine = Mt19937()
        self.assertEqual([engine() for _ in FIRST_OUTPUTS], FIRST_OUTPUTS)
        self.assertEqual(engine.draws, len(FIRST_OUTPUTS))

    def test_clone_is_independent(self):
        engine = Mt19937()
        engine()
        copy = engine.clone()
        self.assertEqual([copy() for _ in range(3)], [engine() for _ in range(3)])

    def test_first_shuffle_of_226_consumes_306_outputs(self):
        # Every capture of a fresh-launch first selection from a 226-entry pool consumed 306 outputs.
        engine = Mt19937()
        random_shuffle(range(226), engine)
        self.assertEqual(engine.draws, 306)

    def test_inlined_index_draw_matches_the_generic_distribution(self):
        # The shuffle inlines the distribution for spans below 2**32; both paths must consume
        # the same outputs and return the same indices.
        for span in (2, 3, 7, 55, 226, 240, 1000, 65537):
            generic, inlined = Mt19937(), Mt19937()
            values = [uniform_int(generic, 0, span - 1) for _ in range(200)]
            mask = (1 << (span - 1).bit_length()) - 1
            fast = []
            for _ in range(200):
                while True:
                    index = inlined() & mask
                    if index < span:
                        break
                fast.append(index)
            self.assertEqual(values, fast, span)
            self.assertEqual(generic.draws, inlined.draws, span)

    def test_short_ranges_draw_nothing(self):
        engine = Mt19937()
        self.assertEqual(uniform_int(engine, 3, 3), 3)
        self.assertEqual(random_shuffle([], engine), [])
        self.assertEqual(random_shuffle([7], engine), [7])
        self.assertEqual(engine.draws, 0)


if __name__ == "__main__":
    unittest.main()
