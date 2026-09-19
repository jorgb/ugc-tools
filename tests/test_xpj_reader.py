import gzip
import json
import unittest

from convert.xpj import reader, template, writer


class TestXPJReader(unittest.TestCase):

    def test_round_trips_writer_output(self):
        """Verify parse() returns exactly the header and data writer.serialize() encoded."""
        project = template.empty_project()
        header_lines, project_data = reader.parse(writer.serialize(project))

        self.assertEqual(header_lines, template.HEADER_LINES)
        self.assertEqual(project_data, project)

    def test_accepts_uncompressed_xpj(self):
        """Verify a non-gzipped header+JSON payload is still parsed."""
        payload = "ACVS\n3.7.0.56\nSerialisableProjectData\njson\nLinux\n{\"formatVersion\": 2}".encode("utf-8")
        header_lines, project_data = reader.parse(payload)

        self.assertEqual(header_lines[0], "ACVS")
        self.assertEqual(project_data, {"formatVersion": 2})

    def test_reports_unexpected_header_line_count(self):
        """Verify an extra header line is returned rather than silently dropped."""
        payload = gzip.compress(b"ACVS\n3.8.0.1\nSerialisableProjectData\njson\nLinux\nExtra\n{}")
        header_lines, _ = reader.parse(payload)

        self.assertEqual(len(header_lines), 6)
        self.assertEqual(header_lines[-1], "Extra")

    def test_rejects_xml_projects(self):
        """Verify the older XML (MPC 2.x) format is rejected with a clear message."""
        with self.assertRaises(ValueError) as context:
            reader.parse(b"<?xml version=\"1.0\"?><project/>")
        self.assertIn("2.x", str(context.exception))

    def test_rejects_bad_magic(self):
        """Verify a gzip payload without the ACVS header is rejected."""
        with self.assertRaises(ValueError):
            reader.parse(gzip.compress(b"not a project"))

    def test_rejects_binary_garbage(self):
        """Verify a non-XPJ binary file gives a ValueError, not a decode error."""
        with self.assertRaises(ValueError) as context:
            reader.parse(b"\x00\x01\x02\x80\x81 not text")
        self.assertIn("Not an XPJ file", str(context.exception))

    def test_rejects_missing_json_body(self):
        """Verify a header with no JSON body is rejected."""
        with self.assertRaises(ValueError):
            reader.parse(gzip.compress(b"ACVS\n3.7.0.56\nSerialisableProjectData\njson\nLinux\n"))

    def test_to_json_text_is_indented_and_preserves_key_order(self):
        """Verify pretty-printing keeps the file's key order (no sorting)."""
        text = reader.to_json_text({"b": 1, "a": {"c": 2}})

        self.assertEqual(list(json.loads(text).keys()), ["b", "a"])
        self.assertIn("\n  \"b\": 1", text)
        self.assertTrue(text.endswith("\n"))


if __name__ == '__main__':
    unittest.main()
