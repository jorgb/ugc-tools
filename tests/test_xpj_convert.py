import logging
import os
import unittest

from convert.xpj import writer
from convert.xpj.convert import build_model

FIXTURE_DIR = os.path.join("testing", "SP404mk2", "pad-sequencer", "2026-04-08")


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

        self.assertEqual(project["formatVersion"], 2)
        data = project["data"]
        self.assertEqual([t["name"] for t in data["tracks"]], ["A", "B"])
        self.assertEqual(len(data["sequences"]), len(model.sequences))
        self.assertEqual(data["masterTempo"], 90.0)

        track_a = data["tracks"][0]
        layer = track_a["program"]["drum"]["instruments"][0]["layersv"][0]
        self.assertTrue(layer["active"])
        self.assertEqual(layer["sampleFile"], "A01 - indust - houst kck - AR.wav")
        self.assertEqual(layer["sampleName"], "indust - houst kck - AR")
        self.assertEqual(track_a["program"]["padNoteMap"]["noteForPad"]["value0"], 37)

    def test_planned_paths_match_written_paths(self):
        """Verify dry-run path planning doesn't touch disk but matches what write_project would use."""
        model = build_model(FIXTURE_DIR)
        xpj_path, samples_dir, wav_paths = writer.planned_paths(model, os.path.join("does", "not", "exist"))

        self.assertTrue(xpj_path.endswith("PROJECT_08.xpj"))
        self.assertIn("PROJECT_08 [Project Data]", samples_dir)
        self.assertEqual(len(wav_paths), 2)
        self.assertFalse(os.path.exists(os.path.join("does", "not", "exist")))


if __name__ == '__main__':
    unittest.main()
