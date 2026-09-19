import copy
import logging
import os
import tempfile
import unittest
import wave

from convert.xpj import reader, writer
from convert.xpj.convert import build_model

# The same 3 samples and 2-bar sequence, made once on an SP404mk2 and once by
# hand on a real MPC (see the .txt next to each). The MPC project is known to
# load, so the converter's output must have exactly its shape.
SP404_DIR = os.path.join("testing", "SP404mk2", "projects", "PRJ7SP404")
REFERENCE_XPJ = os.path.join("testing", "MPC", "prj7mpc.xpj")

# the MPC project has its samples on pads 13-15 (slots 12-14): the top-left
# of the pad grid, where the SP404's pads 1-3 are, and where the converter
# puts them
SAMPLE_SLOTS = (12, 13, 14)

# The MPC project has its one sequence in slot 0. The converter puts a pattern
# on the pad it is played from, and PTN00001 is pad A01: MPC sequence 13.
CONVERTED_SEQUENCE_INDEX = 12


def _structure_differences(real, converted, path=""):
    """Every place converted differs from real in keys, key order, JSON type
    (int and float are distinct: MPC parses strictly) or list length."""
    if isinstance(real, dict) and isinstance(converted, dict):
        if list(real) != list(converted):
            return [f"{path}: keys {list(real)[:5]}... != {list(converted)[:5]}..."]
        return [d for key in real for d in _structure_differences(real[key], converted[key], f"{path}.{key}")]
    if isinstance(real, list) and isinstance(converted, list):
        if len(real) != len(converted):
            return [f"{path}: list length {len(real)} != {len(converted)}"]
        return [d for i, (a, b) in enumerate(zip(real, converted))
                for d in _structure_differences(a, b, f"{path}[{i}]")]
    if type(real) is not type(converted):
        return [f"{path}: {type(real).__name__} != {type(converted).__name__}"]
    return []


def _value_differences(real, converted, path=""):
    """Paths whose value differs; assumes the structures already match."""
    if isinstance(real, dict):
        return [d for key in real for d in _value_differences(real[key], converted[key], f"{path}.{key}")]
    if isinstance(real, list):
        return [d for i, (a, b) in enumerate(zip(real, converted))
                for d in _value_differences(a, b, f"{path}[{i}]")]
    return [] if real == converted else [path]


def _keep_only_sequence(project, index):
    """A copy of project with just the sequence at `index`, moved to slot 0, so
    its shape can be compared with a project that has a single sequence. The
    converter fills the sequences around a pattern with empty ones."""
    project = copy.deepcopy(project)
    data = project["data"]
    data["sequences"] = [{"key": 0, "value": data["sequences"][index]["value"]}]
    data["currentSequence"] = 0
    for entry in data["clipPlayerData"]["trackClipTransportMap"]:
        entry["value"] = entry["value"][:1]
    return project


def _drum_events(project):
    clips = project["data"]["sequences"][0]["value"]["trackClipMaps"][0]
    events = clips[0]["value"]["eventList"]["events"]
    return [(e["time"], e["note"]["note"], e["note"]["velocity"], e["note"]["probability"])
            for e in events]


class TestReferenceProject(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        logging.disable(logging.WARNING)
        cls.model = build_model(SP404_DIR)
        _, cls.real = reader.read_project(REFERENCE_XPJ)
        # through serialize/parse, so the bytes that reach the MPC are what's checked
        cls.header_lines, cls.full_converted = reader.parse(
            writer.serialize(writer.build_project_data(cls.model)))
        cls.converted = _keep_only_sequence(cls.full_converted, CONVERTED_SEQUENCE_INDEX)

    @classmethod
    def tearDownClass(cls):
        logging.disable(logging.NOTSET)

    def test_header_and_container_match_real_mpc_project(self):
        """Verify the header lines match and there is no formatVersion key (the real file has none)."""
        with open(REFERENCE_XPJ, 'rb') as f:
            real_header_lines, _ = reader.parse(f.read())

        self.assertEqual(self.header_lines, real_header_lines)
        self.assertEqual(list(self.converted), list(self.real))
        self.assertEqual(list(self.converted), ["data"])

    def test_structure_matches_real_mpc_project(self):
        """Verify keys, key order, strict JSON types and list lengths match the real project everywhere."""
        differences = _structure_differences(self.real, self.converted)
        self.assertEqual(differences, [], "\n".join(differences[:20]))

    def test_sequence_events_match_real_mpc_project(self):
        """Verify the identical 2-bar sequence gives the same time/note/velocity for all 24 events."""
        real = _drum_events(self.real)
        converted = _drum_events(self.converted)

        self.assertEqual(len(real), 24)
        self.assertEqual(converted, real)

    def test_pad_note_map_is_left_at_mpc_default(self):
        """Verify padNoteMap equals the real one, so pad n plays note 36 + n - 1."""
        def note_map(project):
            return project["data"]["tracks"][0]["program"]["padNoteMap"]

        self.assertEqual(note_map(self.converted), note_map(self.real))

    def test_instruments_differ_from_real_only_in_sample_specific_fields(self):
        """Verify a converted pad is a real loaded MPC pad except its own sample and the gate setting."""
        def instruments(project):
            return project["data"]["tracks"][0]["program"]["drum"]["instruments"]

        # sampleName is identical (same pad names); sampleFile has our "A01 - " prefix and
        # End counts 48 kHz frames where the MPC project's WAVs were resampled to 44.1 kHz
        sample_fields = {".layersv[0].sampleFile", ".layersv[0].sliceInfo.End"}
        # PRJ7SP404's snare (pad A02) has gate on in its PADCONF.BIN, so it converts to
        # Note On (2) although the MPC project's pads are all One Shot (0)
        first, second, third = SAMPLE_SLOTS
        expected = {first: sample_fields, second: sample_fields | {".triggerMode"}, third: sample_fields}

        for slot, expected_paths in expected.items():
            differences = set(_value_differences(instruments(self.real)[slot], instruments(self.converted)[slot]))
            self.assertEqual(differences, expected_paths, f"slot {slot}")

        # every other pad is untouched and identical to a blank real pad
        blank = instruments(self.real)[0]
        for slot in set(range(128)) - set(SAMPLE_SLOTS):
            self.assertEqual(instruments(self.converted)[slot], blank, f"slot {slot}")

    def test_sample_end_is_last_frame_of_the_written_wav(self):
        """Verify sliceInfo End is frames - 1, like MPC's own (7380 frames -> 7379)."""
        instruments = self.converted["data"]["tracks"][0]["program"]["drum"]["instruments"]
        frames = [slot.sample_info.size for slot in self.model.banks["A"].pads.values()]

        self.assertEqual([instruments[slot]["layersv"][0]["sliceInfo"]["End"] for slot in SAMPLE_SLOTS],
                         [f - 1 for f in frames])

    def test_every_track_has_a_clip_in_every_sequence(self):
        """Verify trackClipMaps and clipPlayerData list every track by name, sorted, like MPC."""
        data = self.converted["data"]
        names = sorted(t["name"] for t in data["tracks"])

        self.assertEqual(names, ["Drum 001", "Out 1/2", "Out 3/4", "Submix 1"])
        for sequence in data["sequences"]:
            self.assertEqual([c["key"] for c in sequence["value"]["trackClipMaps"][0]], names)
        self.assertEqual([e["key"] for e in data["clipPlayerData"]["trackClipTransportMap"]], names)

    def test_written_project_data_folder_holds_every_referenced_wav(self):
        """Verify every sampleFile in the XPJ exists in _[ProjectData] as a WAV with the SP404 sample's frame count."""
        with tempfile.TemporaryDirectory() as output_dir:
            _, project_data_dir, _ = writer.write_project(self.model, output_dir)

            for pad_slot in self.model.banks["A"].pads.values():
                wav_path = os.path.join(project_data_dir, pad_slot.wav_filename)
                with wave.open(wav_path, 'rb') as w:
                    self.assertEqual(w.getnframes(), pad_slot.sample_info.size)

        pool_paths = [s["path"] for s in self.converted["data"]["samples"]]
        self.assertEqual(sorted(pool_paths),
                         sorted(p.wav_filename for p in self.model.banks["A"].pads.values()))


if __name__ == '__main__':
    unittest.main()
