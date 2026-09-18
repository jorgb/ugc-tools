import io
import unittest
from sp404 import spread as spr


class TestSP404Spread(unittest.TestCase):

    def test_read_string_stops_at_first_nul(self):
        """Verify bytes after the first NUL are dropped, not just trailing NULs."""
        # seen in a real pad name field: text, NUL padding, then stale
        # leftover bytes from a previously-written longer name
        buf = b"Backing Sample\x00\x00\x00      \x00"
        f = io.BytesIO(buf)
        self.assertEqual(spr.read_string(f, len(buf)), "Backing Sample")

    def test_read_string_without_nul(self):
        """Verify a fully-used field with no NUL terminator reads unchanged."""
        f = io.BytesIO(b"exactly24characterslong!")
        self.assertEqual(spr.read_string(f, 24), "exactly24characterslong!"[:24])


if __name__ == '__main__':
    unittest.main()
