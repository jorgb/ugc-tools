import logging
import os
import shutil
import struct
import tempfile
import unittest

from convert.xpj import mapping, writer
from convert.xpj.convert import _pattern_pad, build_model, convert_project

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
        # only the patterns' own sequences are written, each at its pad's index
        self.assertEqual([entry["key"] for entry in data["sequences"]],
                         sorted(s.index for s in model.sequences))
        self.assertEqual(len([s for s in model.sequences if s.index is not None]), len(model.sequences))
        self.assertEqual(data["masterTempo"], 90.0)

        track = data["tracks"][0]
        instruments = track["program"]["drum"]["instruments"]
        # SP404 pad 1 is top-left; on the MPC that is pad 13 (slot 12)
        layer = instruments[12]["layersv"][0]
        self.assertEqual(layer["sampleFile"], "A01 - indust - houst kck - AR.wav")
        self.assertEqual(layer["sampleName"], "indust - houst kck - AR")
        # SP404 bank B pad 1 is MPC bank B pad 13: slot 28
        self.assertEqual(instruments[28]["layersv"][0]["sampleFile"], "B01 - " + model.banks["B"].pads[1].pad.name + ".wav")
        self.assertEqual(model.banks["B"].pads[1].slot, 28)
        # padNoteMap is left at MPC's default: slot 0 plays note 36
        self.assertEqual(track["program"]["padNoteMap"]["noteForPad"]["value0"], 36)
        self.assertEqual(model.banks["A"].pads[1].note, 48)
        self.assertEqual(model.banks["B"].pads[1].note, 64)

    def test_events_on_bank_b_play_bank_b_notes(self):
        """Verify pattern events on SP404 pad B01 are written with MPC note 64 (slot 28), not bank A's notes."""
        model = build_model(FIXTURE_DIR)
        pad_b01 = model.banks["B"].pads[1]
        events = [e for s in model.sequences for e in s.events if e.pad_slot is pad_b01]

        self.assertTrue(events, "fixture should sequence pad B01")
        self.assertTrue(all(e.note == 64 for e in events))
        self.assertTrue(all(e.note == 48 for s in model.sequences for e in s.events
                            if e.pad_slot is model.banks["A"].pads[1]))

    def test_pattern_file_number_is_its_sp404_pad(self):
        """Verify PTN file numbers count 16 pads to a bank, A-J."""
        self.assertEqual(_pattern_pad("PTN00001"), ("A", 1))
        self.assertEqual(_pattern_pad("PTN00013"), ("A", 13))
        self.assertEqual(_pattern_pad("PTN00017"), ("B", 1))
        self.assertEqual(_pattern_pad("PTN00081"), ("F", 1))
        self.assertEqual(_pattern_pad("PTN00160"), ("J", 16))
        self.assertEqual(_pattern_pad("PTN00161"), (None, None))
        self.assertEqual(_pattern_pad("PTN00000"), (None, None))
        self.assertEqual(_pattern_pad("PATTERNCHAIN_00"), (None, None))

    def test_sequences_sit_on_the_mirrored_pattern_pad(self):
        """Verify each pattern is the MPC sequence on the pad in the same grid spot as on the SP404."""
        model = build_model(FIXTURE_DIR)
        sequences = writer.build_project_data(model)["data"]["sequences"]
        name = {entry["key"]: entry["value"]["name"] for entry in sequences}

        # SP404 pattern A01 (top-left) is MPC sequence 13 (top-left); A13 (bottom-left) is sequence 1
        self.assertEqual(name[12], "PTN00001")
        self.assertEqual(name[0], "PTN00013")
        self.assertEqual(name[3], "PTN00016")  # A16, bottom-right, is MPC pad 4
        self.assertNotIn(15, name)  # A04 has no pattern, so no sequence lights its pad
        # bank B: B01 is MPC bank B pad 13, B04 is pad 16
        self.assertEqual(name[28], "PTN00017")
        self.assertEqual(name[31], "PTN00020")

    def test_pads_with_no_pattern_have_no_sequence(self):
        """Verify no empty sequence is written for a pad without a pattern (the MPC lights a pad for every sequence)."""
        model = build_model(FIXTURE_DIR)
        data = writer.build_project_data(model)["data"]
        keys = [entry["key"] for entry in data["sequences"]]

        # A10 (PTN00010) has no pattern: index 5
        self.assertNotIn(5, keys)
        self.assertEqual(len(keys), len(model.sequences))

    def test_sequence_01_is_written_empty_when_no_pattern_sits_on_key_0(self):
        """Verify the MPC's always-present Sequence 01 is added at key 0, empty, 2 bars like MPC's default."""
        model = build_model(PROJECT_DIR)  # its one pattern, PTN00001, is MPC sequence 13 (key 12)
        by_key = {entry["key"]: entry["value"] for entry in writer.build_project_data(model)["data"]["sequences"]}

        self.assertEqual(sorted(by_key), [0, 12])
        self.assertEqual(by_key[0]["name"], "Sequence 01")
        self.assertEqual(by_key[0]["lengthBars"], 2)
        self.assertEqual([len(c["value"]["eventList"]["events"]) for c in by_key[0]["trackClipMaps"][0]],
                         [0, 0, 0, 0])

    def test_project_opens_on_key_0_and_every_track_lists_every_sequence(self):
        """Verify currentSequence is key 0 and each track's transport map has one entry per written sequence."""
        model = build_model(FIXTURE_DIR)
        data = writer.build_project_data(model)["data"]
        keys = [entry["key"] for entry in data["sequences"]]

        self.assertEqual(data["currentSequence"], 0)
        for entry in data["clipPlayerData"]["trackClipTransportMap"]:
            self.assertEqual([e["key"] for e in entry["value"]], keys, entry["key"])

    def test_events_follow_their_sequence_to_the_new_index(self):
        """Verify the events written into a sequence are that pattern's own."""
        model = build_model(FIXTURE_DIR)
        data = writer.build_project_data(model)["data"]
        by_key = {entry["key"]: entry["value"] for entry in data["sequences"]}
        nine = next(s for s in model.sequences if s.name == "PTN00009")

        self.assertEqual(nine.index, 4)  # A09 is MPC pad 5
        clips = {c["key"]: c["value"] for c in by_key[4]["trackClipMaps"][0]}
        self.assertEqual(len(clips["Drum 001"]["eventList"]["events"]), 16)

    def test_convert_project_logs_where_each_pattern_lands(self):
        """Verify a dry run (which logs the whole summary) names the MPC sequence and pad of a pattern."""
        logging.disable(logging.NOTSET)
        with self.assertLogs("convert.xpj.convert", level="INFO") as logs:
            convert_project(FIXTURE_DIR, os.path.join("does", "not", "exist"), dry_run=True)

        text = "\n".join(logs.output)
        self.assertIn("Sequence 'PTN00001' (pattern A01) -> MPC sequence 13 (pad A13)", text)
        self.assertIn("SP404 pattern bank B -> MPC sequence bank B", text)

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


    def test_pad_envelope_reaches_the_mpc_pad(self):
        """Verify a pad with attack 11, hold 46 and release 57 fades and ends like the SP404's."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "PRJ")
            shutil.copytree(PROJECT_DIR, source)
            padconf_path = os.path.join(source, "PADCONF.BIN")
            with open(padconf_path, "rb") as f:
                buf = bytearray(f.read())
            # pad A01 (gate off) and pad A02 (gate on): attack (word 22), hold (word 23), release (word 24)
            for pad_offset, (attack, hold, release) in [(0, (11, 46, 57)), (172, (2, 100, 14))]:
                for word, value in [(22, attack), (23, hold), (24, release)]:
                    struct.pack_into(">L", buf, PAD_RECORDS_OFFSET + pad_offset + word * 4, value)
            with open(padconf_path, "wb") as f:
                f.write(buf)

            model = build_model(source)

        instruments = writer.build_project_data(model)["data"]["tracks"][0]["program"]["drum"]["instruments"]
        pad_a01, pad_a02, untouched = instruments[12], instruments[13], instruments[14]
        frames = model.banks["A"].pads[1].sample_info.size

        # A01: GATE off, so the release is the fade-out at the end, which is at 46 % of the sample
        env = pad_a01["synthSection"]["ampEnvelope"]
        self.assertAlmostEqual(env["Attack"]["value0"], 11 / 127)
        self.assertAlmostEqual(env["Decay"]["value0"], 57 / 127)
        self.assertEqual(env["Release"]["value0"], 0.0)
        self.assertTrue(env["AD"]["value0"])
        self.assertEqual(pad_a01["layersv"][0]["sliceInfo"]["End"], round(frames * 46 / 100) - 1)
        # A02: GATE on, so the release is the fade-out when the pad is let go
        env = pad_a02["synthSection"]["ampEnvelope"]
        self.assertAlmostEqual(env["Attack"]["value0"], 2 / 127)
        self.assertAlmostEqual(env["Release"]["value0"], 14 / 127)
        self.assertFalse(env["AD"]["value0"])
        self.assertFalse(env["OneShot"]["value0"])
        # a pad with the default envelope keeps MPC's own
        self.assertAlmostEqual(untouched["synthSection"]["ampEnvelope"]["Attack"]["value0"], 2 / 127)
        self.assertTrue(untouched["synthSection"]["ampEnvelope"]["AD"]["value0"])

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
        # SP404 pads A01 and A02 are MPC pads 13 and 14 (slots 12 and 13)
        pad_a01, pad_a02 = instruments[12], instruments[13]
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
