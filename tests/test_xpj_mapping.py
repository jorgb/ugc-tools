import unittest
from convert.xpj import mapping


class TestXPJMapping(unittest.TestCase):

    def test_is_baseline_chromatic_pitch(self):
        """Verify both documented "no pitch shift" encodings count as baseline."""
        self.assertTrue(mapping.is_baseline_chromatic_pitch(0x00))  # plain, unpitched note
        self.assertTrue(mapping.is_baseline_chromatic_pitch(0x8D))  # common default-pitch encoding
        self.assertFalse(mapping.is_baseline_chromatic_pitch(0x87))  # genuinely shifted, e.g. "Pitch Chromatic -6"


if __name__ == '__main__':
    unittest.main()
