import unittest
from sp404.ptn import PadID, Pattern, PatternEvent

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


if __name__ == '__main__':
    unittest.main()
