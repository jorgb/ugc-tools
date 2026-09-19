import unittest
from convert.xpj import mapping
from sp404.padconf import TrigMode


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
        self.assertEqual(mapping.sample_region(_Pad(sample_start=0, sample_end=7380, hold=100)), (0, 7379))
        self.assertEqual(mapping.sample_region(_Pad(sample_start=100, sample_end=0, hold=100)), (100, 0))

    def test_hold_is_the_share_of_the_region_that_plays(self):
        """Verify HOLD 50 ends the region at its middle, counted from the region's start."""
        self.assertEqual(mapping.sample_region(_Pad(sample_start=0, sample_end=1000, hold=50)), (0, 499))
        self.assertEqual(mapping.sample_region(_Pad(sample_start=200, sample_end=1200, hold=25)), (200, 449))
        self.assertEqual(mapping.sample_region(_Pad(sample_start=0, sample_end=1000, hold=1)), (0, 9))

    def test_hold_never_empties_the_region(self):
        """Verify a very short region still plays at least one frame."""
        self.assertEqual(mapping.sample_region(_Pad(sample_start=0, sample_end=10, hold=1)), (0, 0))

    def test_envelope_of_an_untouched_pad_changes_nothing(self):
        """Verify attack 0 and release 0 (the SP404 defaults) leave MPC's own envelope alone."""
        pad = _Pad(attack=0, hold=100, release=0, gate=True, trig_mode=[TrigMode.NORMAL])
        self.assertEqual(mapping.amp_envelope(pad), {})

    def test_attack_keeps_its_place_on_the_dial(self):
        """Verify attack 0-127 becomes MPC's 0-1 attack in the same proportion."""
        pad = _Pad(attack=11, hold=100, release=0, gate=False, trig_mode=[TrigMode.NORMAL])
        self.assertEqual(mapping.amp_envelope(pad), {"Attack": 11 / 127})
        self.assertEqual(mapping.amp_envelope(_Pad(attack=127, hold=100, release=0, gate=False,
                                                    trig_mode=[TrigMode.NORMAL])), {"Attack": 1.0})

    def test_release_of_a_gated_pad_is_mpcs_release_on_an_adsr_envelope(self):
        """Verify GATE on: the fade-out at pad release is MPC's Release, and the envelope follows note-off."""
        pad = _Pad(attack=2, hold=100, release=14, gate=True, trig_mode=[TrigMode.NORMAL])
        self.assertEqual(mapping.amp_envelope(pad),
                         {"Attack": 2 / 127, "Release": 14 / 127, "AD": False, "OneShot": False})

    def test_release_of_a_one_shot_pad_is_mpcs_decay_from_the_end(self):
        """Verify GATE off: the fade-out at the end of the sound is MPC's Decay, and the envelope stays a one-shot."""
        pad = _Pad(attack=0, hold=100, release=3, gate=False, trig_mode=[TrigMode.NORMAL])
        self.assertEqual(mapping.amp_envelope(pad), {"Decay": 3 / 127})
        # the pad's One Shot flag plays through even with GATE on, so it is treated the same
        flagged = _Pad(attack=0, hold=100, release=3, gate=True, trig_mode=[TrigMode.ONE_SHOT])
        self.assertEqual(mapping.amp_envelope(flagged), {"Decay": 3 / 127})

    def test_sample_tempo_is_zero_unless_bpm_synced(self):
        """Verify the sample tempo stays 0.0 (MPC's "unknown") for unsynced pads."""
        self.assertEqual(mapping.sample_tempo(_Pad(bpm=90.0, bpm_sync=False)), 0.0)
        self.assertEqual(mapping.sample_tempo(_Pad(bpm=90.0, bpm_sync=True)), 90.0)

    def test_gate_maps_to_note_on(self):
        """Verify SP404 GATE on is MPC's Note On; gate off and the One Shot flag are One Shot."""
        gated = _Pad(gate=True, trig_mode=[TrigMode.NORMAL])
        self.assertEqual(mapping.trigger_mode(gated), mapping.TriggerMode.NOTE_ON)
        self.assertEqual(mapping.TriggerMode.NOTE_ON, 2)
        self.assertEqual(mapping.trigger_mode(_Pad(gate=False, trig_mode=[TrigMode.NORMAL])),
                         mapping.TriggerMode.ONE_SHOT)
        self.assertEqual(mapping.trigger_mode(_Pad(gate=True, trig_mode=[TrigMode.ONE_SHOT])),
                         mapping.TriggerMode.ONE_SHOT)

    def test_tuning_reads_pitch_from_the_speed_ratio(self):
        """Verify the SP404's varispeed pitch (2^(n/12) in the Speed field) becomes MPC tune."""
        for semitones, speed_perc in [(-5, 74.91), (-3, 84.08), (-12, 50.0), (7, 149.83), (0, 100.0)]:
            pad = _Pad(pitch_coarse=0, pitch_fine=0, speed_perc=speed_perc, bpm_sync=False)
            self.assertEqual(mapping.tuning(pad), (semitones, 0), f"{semitones} semitones")

    def test_tuning_keeps_the_cents_of_an_in_between_speed(self):
        """Verify a speed that is not a whole semitone splits into coarse and fine tune."""
        pad = _Pad(pitch_coarse=0, pitch_fine=0, speed_perc=92.38, bpm_sync=False)
        self.assertEqual(mapping.tuning(pad), (-1, -37))

    def test_tuning_adds_coarse_and_fine_fields(self):
        pad = _Pad(pitch_coarse=2, pitch_fine=30, speed_perc=100.0, bpm_sync=False)
        self.assertEqual(mapping.tuning(pad), (2, 30))
        pad = _Pad(pitch_coarse=-5, pitch_fine=0, speed_perc=74.91, bpm_sync=False)
        self.assertEqual(mapping.tuning(pad), (-10, 0))

    def test_tuning_ignores_speed_when_bpm_synced(self):
        """Verify a BPM-synced pad's Speed is a time stretch, not pitch."""
        pad = _Pad(pitch_coarse=0, pitch_fine=0, speed_perc=74.91, bpm_sync=True)
        self.assertEqual(mapping.tuning(pad), (0, 0))
        self.assertEqual(mapping.stretch_percentage(pad), 74.91)

    def test_stretch_percentage_is_neutral_when_speed_became_pitch(self):
        pad = _Pad(speed_perc=74.91, bpm_sync=False)
        self.assertEqual(mapping.stretch_percentage(pad), 100.0)


class _Pad:
    def __init__(self, **fields):
        self.__dict__.update(fields)


if __name__ == '__main__':
    unittest.main()
