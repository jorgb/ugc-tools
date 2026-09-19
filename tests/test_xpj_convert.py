import logging
import os
import shutil
import struct
import tempfile
import unittest

from convert.xpj import mapping, writer
from convert.xpj.convert import build_model

FIXTURE_DIR = os.path.join("testing", "SP404mk2", "pad-sequencer", "2026-04-08")
PROJECT_DIR = os.path.join("testing", "SP404mk2", "projects", "PRJ7SP404")

PAD_RECORDS_OFFSET = 0xA0


class TestXPJConvert(unittest.TestCase):

    def setUp(self):
        # this fixture deliberately exercises the chromatic-pitch and
        # missing-pad warnings; silence them so test output stays readable
        logging.disable(logging.WARNING)
        self.addCleanup(logging.disable, logging.NOTSET)

    def test_build_model_against_real_fixture(self):
        """Verify the model built from the real PROJECT_08 fixture matches known facts."""
        model = build_model(FIXTURE_DIR)

        self.assertEqual(model.project_name, "PROJECT_08")
        self.assertEqual(sorted(model.banks.keys()), ["A", "B"])
        self.assertEqual(model.banks["A"].pads[1].pad.name, "indust - houst kck - AR")
        self.assertEqual(model.banks["A"].pads[1].sample_info.size, 77051)
        self.assertEqual(model.banks["B"].pads[1].sample_info.size, 73375)
        self.assertEqual(len(model.skipped_pads), 0)

        sequence_names = [s.name for s in model.sequences]
        self.assertIn("PTN00001", sequence_names)
        self.assertIn("PTN00009", sequence_names)

        # PTN00009 is "pad A01 on all 16 steps" per testing/SP404mk2/PTN.txt
        nine = next(s for s in model.sequences if s.name == "PTN00009")
        self.assertEqual(len(nine.events), 16)
        self.assertEqual([e.tick_pulses for e in nine.events],
                          [i * 240 for i in range(16)])

    def test_build_project_data_shape(self):
        """Verify the assembled XPJ dict has the documented top-level shape."""
        model = build_model(FIXTURE_DIR)
        project = writer.build_project_data(model)

        self.assertEqual(list(project), ["data"])
        data = project["data"]
        # one drum track for all banks, then MPC's own fixed submix/output tracks
        self.assertEqual([t["name"] for t in data["tracks"]], ["Drum 001", "Submix 1", "Out 1/2", "Out 3/4"])
        self.assertEqual(len(data["sequences"]), len(model.sequences))
        self.assertEqual(data["masterTempo"], 90.0)

        track = data["tracks"][0]
        instruments = track["program"]["drum"]["instruments"]
        layer = instruments[0]["layersv"][0]
        self.assertEqual(layer["sampleFile"], "A01 - indust - houst kck - AR.wav")
        self.assertEqual(layer["sampleName"], "indust - houst kck - AR")
        # SP404 bank B pad 1 is MPC bank B pad 1: slot 16
        self.assertEqual(instruments[16]["layersv"][0]["sampleFile"], "B01 - " + model.banks["B"].pads[1].pad.name + ".wav")
        self.assertEqual(model.banks["B"].pads[1].slot, 16)
        # padNoteMap is left at MPC's default: slot 0 plays note 36
        self.assertEqual(track["program"]["padNoteMap"]["noteForPad"]["value0"], 36)
        self.assertEqual(model.banks["A"].pads[1].note, 36)
        self.assertEqual(model.banks["B"].pads[1].note, 52)

    def test_events_on_bank_b_play_bank_b_notes(self):
        """Verify pattern events on SP404 pad B01 are written with MPC note 52 (slot 16), not bank A's notes."""
        model = build_model(FIXTURE_DIR)
        pad_b01 = model.banks["B"].pads[1]
        events = [e for s in model.sequences for e in s.events if e.pad_slot is pad_b01]

        self.assertTrue(events, "fixture should sequence pad B01")
        self.assertTrue(all(e.note == 52 for e in events))
        self.assertTrue(all(e.note == 36 for s in model.sequences for e in s.events
                            if e.pad_slot is model.banks["A"].pads[1]))

    def test_every_sequenced_pad_has_an_mpc_pad(self):
        """Verify banking maps every pad a pattern plays, and nothing lands in Unmapped Samples here."""
        model = build_model(FIXTURE_DIR)

        self.assertTrue(all(e.pad_slot.slot is not None for s in model.sequences for e in s.events))
        self.assertEqual(model.unmapped_pads, [])

    def test_planned_paths_match_written_paths(self):
        """Verify dry-run path planning doesn't touch disk but matches what write_project would use."""
        model = build_model(FIXTURE_DIR)
        xpj_path, project_data_dir, wav_paths = writer.planned_paths(model, os.path.join("does", "not", "exist"))

        self.assertTrue(xpj_path.endswith("PROJECT_08.xpj"))
        self.assertEqual(os.path.basename(project_data_dir), "PROJECT_08_[ProjectData]")
        self.assertEqual(len(wav_paths), 2)
        # WAVs live directly inside _[ProjectData], not a Samples/ subfolder
        self.assertTrue(all(os.path.dirname(p) == project_data_dir for p in wav_paths))
        self.assertFalse(os.path.exists(os.path.join("does", "not", "exist")))


    def test_pad_pitch_volume_and_gate_reach_the_mpc_pad(self):
        """Verify a pad set to pitch -5, volume 41 and GATE on lands as tune -5, that level and Note On."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "PRJ")
            shutil.copytree(PROJECT_DIR, source)
            padconf_path = os.path.join(source, "PADCONF.BIN")
            with open(padconf_path, "rb") as f:
                buf = bytearray(f.read())
            # pad A01: level (word 3), gate (word 4) and the Speed field (word 16),
            # where the SP404 stores a -5 semitone pitch as 2^(-5/12) = 74.91%
            struct.pack_into(">L", buf, PAD_RECORDS_OFFSET + 12, 41)
            struct.pack_into(">L", buf, PAD_RECORDS_OFFSET + 16, 1)
            struct.pack_into(">L", buf, PAD_RECORDS_OFFSET + 64, 7491)
            with open(padconf_path, "wb") as f:
                f.write(buf)

            model = build_model(source)

        instruments = writer.build_project_data(model)["data"]["tracks"][0]["program"]["drum"]["instruments"]
        pad_a01, pad_a02 = instruments[0], instruments[1]
        self.assertEqual(pad_a01["coarseTune"], -5)
        self.assertEqual(pad_a01["fineTune"], 0)
        self.assertEqual(pad_a01["triggerMode"], mapping.TriggerMode.NOTE_ON)
        self.assertEqual(pad_a01["stretchPercentage"], 100)
        self.assertAlmostEqual(pad_a01["mixable"]["volume"], mapping.MPC_UNITY_VOLUME * 41 / 127)
        # an untouched pad keeps its own settings
        self.assertEqual(pad_a02["coarseTune"], 0)
        self.assertAlmostEqual(pad_a02["mixable"]["volume"], mapping.MPC_UNITY_VOLUME)


if __name__ == '__main__':
    unittest.main()
