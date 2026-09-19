import unittest
from convert.xpj import mapping


class TestXPJMapping(unittest.TestCase):

    def test_is_baseline_chromatic_pitch(self):
        """Verify both documented "no pitch shift" encodings count as baseline."""
        self.assertTrue(mapping.is_baseline_chromatic_pitch(0x00))  # plain, unpitched note
        self.assertTrue(mapping.is_baseline_chromatic_pitch(0x8D))  # common default-pitch encoding
        self.assertFalse(mapping.is_baseline_chromatic_pitch(0x87))  # genuinely shifted, e.g. "Pitch Chromatic -6"

    def test_slot_note_is_mpcs_default_pad_note_map(self):
        """Verify slot n plays note (36 + n) % 128, as in the real project's padNoteMap."""
        self.assertEqual(mapping.slot_note(0), 36)
        self.assertEqual(mapping.slot_note(12), 48)  # the real MPC project's pad 13
        self.assertEqual(mapping.slot_note(91), 127)
        self.assertEqual(mapping.slot_note(92), 0)  # the map wraps
        self.assertEqual(mapping.slot_note(127), 35)

    def test_slot_note_is_unique_for_all_128_slots(self):
        """Verify no two pads of a drum program play the same note."""
        self.assertEqual(len({mapping.slot_note(s) for s in range(128)}), 128)

    def test_instrument_volume_uses_mpc_unity_gain(self):
        """Verify SP404 volume 127 is exactly MPC's 0 dB value and lower volumes scale from it."""
        self.assertEqual(mapping.instrument_volume(_Pad(vol=127)), mapping.MPC_UNITY_VOLUME)
        self.assertAlmostEqual(mapping.instrument_volume(_Pad(vol=0)), 0.0)
        self.assertLess(mapping.instrument_volume(_Pad(vol=64)), mapping.MPC_UNITY_VOLUME)

    def test_sample_region_end_is_the_last_frame(self):
        """Verify SP404 sample_end (one past the last frame) becomes MPC's inclusive End."""
        self.assertEqual(mapping.sample_region(_Pad(sample_start=0, sample_end=7380)), (0, 7379))
        self.assertEqual(mapping.sample_region(_Pad(sample_start=100, sample_end=0)), (100, 0))

    def test_sample_tempo_is_zero_unless_bpm_synced(self):
        """Verify the sample tempo stays 0.0 (MPC's "unknown") for unsynced pads."""
        self.assertEqual(mapping.sample_tempo(_Pad(bpm=90.0, bpm_sync=False)), 0.0)
        self.assertEqual(mapping.sample_tempo(_Pad(bpm=90.0, bpm_sync=True)), 90.0)


class _Pad:
    def __init__(self, **fields):
        self.__dict__.update(fields)


if __name__ == '__main__':
    unittest.main()
