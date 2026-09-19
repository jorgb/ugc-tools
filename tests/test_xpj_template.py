import unittest

from convert.xpj import template


class TestXPJTemplate(unittest.TestCase):

    def test_assign_keeps_the_json_type_the_template_holds(self):
        """Verify assign() converts to the existing value's type (100 stays int, not 100.0)."""
        container = {"percent": 100, "volume": 0.5, "flag": False, "name": ""}
        template.assign(container, "percent", 87.6)
        template.assign(container, "volume", 1)
        template.assign(container, "flag", 1)
        template.assign(container, "name", "kick")

        self.assertEqual(container, {"percent": 88, "volume": 1.0, "flag": True, "name": "kick"})
        self.assertIs(type(container["percent"]), int)
        self.assertIs(type(container["volume"]), float)

    def test_assign_refuses_to_add_a_field(self):
        """Verify assign() raises for a key the template doesn't have, rather than inventing it."""
        with self.assertRaises(KeyError):
            template.assign({"a": 1}, "velocityScale", 100)

    def test_empty_track_is_128_blank_pads(self):
        """Verify the drum track template has 128 pads and none has a sample."""
        track = template.empty_track("A")
        instruments = track["program"]["drum"]["instruments"]

        self.assertEqual((track["name"], track["program"]["name"]), ("A", "A"))
        self.assertEqual(len(instruments), 128)
        self.assertTrue(all(not layer["sampleFile"] for i in instruments for layer in i["layersv"]))
        self.assertEqual(track["samples"], [])

    def test_empty_project_has_only_mpcs_fixed_tracks(self):
        """Verify the project template holds the submix/output tracks, and no samples or sequences."""
        data = template.empty_project()["data"]

        self.assertEqual([t["name"] for t in data["tracks"]], ["Submix 1", "Out 1/2", "Out 3/4"])
        self.assertEqual((data["samples"], data["sequences"]), ([], []))

    def test_pieces_are_independent_copies(self):
        """Verify mutating one returned piece doesn't leak into the next call."""
        template.empty_note_event()["note"]["note"] = 99
        template.empty_track("A")["program"]["drum"]["instruments"][0]["coarseTune"] = 5

        self.assertNotEqual(template.empty_note_event()["note"]["note"], 99)
        self.assertEqual(template.empty_track("B")["program"]["drum"]["instruments"][0]["coarseTune"], 0)

    def test_sequence_has_no_events_and_a_clip_per_fixed_track(self):
        """Verify a new sequence carries empty clips for the fixed tracks, sized to the sequence."""
        sequence = template.empty_sequence("PTN00001", 90.0, 2, 2)
        row = sequence["trackClipMaps"][0]

        self.assertEqual([entry["key"] for entry in row], ["Out 1/2", "Out 3/4", "Submix 1"])
        self.assertTrue(all(e["value"]["eventList"]["events"] == [] for e in row))
        self.assertTrue(all(e["value"]["endPulses"] == 7680 for e in row))
        self.assertEqual((sequence["lengthPulses"], sequence["loopEndPulses"]), (7680, 7680))


if __name__ == '__main__':
    unittest.main()
