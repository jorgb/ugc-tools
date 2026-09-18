import os
import tempfile
import unittest
from sp404.ptn import PadID, Pattern, PatternEvent

# Worked example from testing/SP404mk2/PTN.txt: a 1-bar pattern with pad A01
# kicking on every 16th-note step, plus filler records, an end-of-events
# marker (0x8C) and a trailer. Ticks were hand-verified in that file to sum
# to 1920 and land on multiples of 120.
_KICK_EVERY_STEP_HEX = """
00 2F 00 8D 5A 40 77 00 78 80 00 00 00 00 00 00
78 2F 00 8D 5A 40 77 00 0F 2F 00 8D 5A 40 77 00
69 80 00 00 00 00 00 00 78 2F 00 8D 5A 40 77 00
1E 2F 00 8D 5A 40 77 00 5A 80 00 00 00 00 00 00
78 2F 00 8D 5A 40 77 00 2D 2F 00 8D 5A 40 77 00
4B 80 00 00 00 00 00 00 78 2F 00 8D 5A 40 77 00
3C 2F 00 8D 5A 40 77 00 3C 80 00 00 00 00 00 00
78 2F 00 8D 5A 40 77 00 4B 2F 00 8D 5A 40 77 00
2D 80 00 00 00 00 00 00 78 2F 00 8D 5A 40 77 00
5A 2F 00 8D 5A 40 77 00 1E 80 00 00 00 00 00 00
78 2F 00 8D 5A 40 77 00 69 2F 00 8D 5A 40 77 00
0F 80 00 00 00 00 00 00 78 2F 00 8D 5A 40 77 00
00 8C 00 00 00 00 00 00 01 00 00 00 00 80 01 01
"""


def _write_pattern_fixture(hex_text):
    data = bytes.fromhex("".join(hex_text.split()))
    fd, path = tempfile.mkstemp(suffix=".BIN")
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
    return path


class TestSP404Pattern(unittest.TestCase):

    def test_pad_id_mapping(self):
        """Verify pad number and toggle mapping to bank/pad strings."""
        # Bank A
        self.assertEqual(PadID(0x2f, 0x00).name, "A01")
        self.assertEqual(PadID(0x3e, 0x00).name, "A16")
        
        # Bank B
        self.assertEqual(PadID(0x3f, 0x00).name, "B01")
        
        # Bank E
        self.assertEqual(PadID(0x6f, 0x00).name, "E01")
        
        # Bank F (Toggle 0x01)
        self.assertEqual(PadID(0x2f, 0x01).name, "F01")
        
        # Bank J
        self.assertEqual(PadID(0x6f, 0x01).name, "J01")
        self.assertEqual(PadID(0x7e, 0x01).name, "J16")

    def test_pad_id_ignores_unknown_high_bits(self):
        """Verify bits above the low nibble (e.g. 0x40, seen in real captures) are ignored."""
        self.assertEqual(PadID(0x3b, 0x40).name, "A13")
        self.assertEqual(PadID(0x3b, 0x41).name, "F13")

    def test_pad_id_invalid(self):
        """Verify that invalid pad numbers or toggles raise ValueError."""
        with self.assertRaises(ValueError):
            PadID(0x20, 0x00)  # Below range
        with self.assertRaises(ValueError):
            PadID(0x7f, 0x00)  # Above range
        with self.assertRaises(ValueError):
            PadID(0x2f, 0x02)  # Invalid toggle

    def test_pattern_event_control_change(self):
        """Verify a 0x8E record is parsed as a control change, not a filler."""
        event = PatternEvent(bytes([0x05, 0x8E, 0x01, 0x00, 0x00, 0x40, 0x64, 0x00]))
        self.assertIsNone(event.pad_id)
        self.assertEqual(event.midi_channel, 0x01)
        self.assertEqual(event.controller, 0x40)
        self.assertEqual(event.controller_value, 0x64)

    def test_pattern_event_filler_has_no_control_change(self):
        """Verify a plain filler record is not mistaken for a control change."""
        event = PatternEvent(bytes([0xFF, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]))
        self.assertIsNone(event.pad_id)
        self.assertIsNone(event.controller)

    def test_pattern_absolute_tick_and_filler_removal(self):
        """Verify tick accumulation and filler removal against a known-good pattern."""
        path = _write_pattern_fixture(_KICK_EVERY_STEP_HEX)
        try:
            pattern = Pattern(path)
        finally:
            os.remove(path)

        self.assertEqual(len(pattern.events), 16)
        self.assertTrue(all(e.pad_id.name == "A01" for e in pattern.events))
        self.assertEqual([e.absolute_tick for e in pattern.events],
                          [i * 120 for i in range(16)])
        self.assertTrue(all(e.velocity == 0x5A for e in pattern.events))

    def test_pattern_trailer_decoding(self):
        """Verify bars/time signature/loop bar fields are read from the trailer."""
        path = _write_pattern_fixture(_KICK_EVERY_STEP_HEX)
        try:
            pattern = Pattern(path)
        finally:
            os.remove(path)

        self.assertEqual(pattern.bars, 1)
        self.assertEqual(pattern.time_signature, (4, 4))
        self.assertEqual(pattern.loop_end_bar, 1)


if __name__ == '__main__':
    unittest.main()
