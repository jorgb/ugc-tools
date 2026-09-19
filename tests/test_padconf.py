import unittest
from sp404.padconf import Project

class TestSP404Padconf(unittest.TestCase):

    def test_pitch_and_time_stretch_defaults(self):
        """Verify pitch coarse/fine and speed read as untouched defaults."""
        project = Project("testing/SP404mk2/pad-params/PADCONF.BIN")
        pad = project.pads[0]

        self.assertEqual(pad.pitch_coarse, 0)
        self.assertEqual(pad.pitch_fine, 0)
        self.assertEqual(pad.speed_perc, 100.0)

    def test_envelope_defaults(self):
        """Verify attack 0, hold 100 (the whole sample) and release 0 read as untouched defaults."""
        pad = Project("testing/SP404mk2/pad-params/PADCONF.BIN").pads[0]

        self.assertEqual((pad.attack, pad.hold, pad.release), (0, 100, 0))


if __name__ == '__main__':
    unittest.main()
