import os
import tempfile
import unittest

from convert.xpj import banking, reader, writer
from convert.xpj.model import Bank, NoteEvent, PadSlot, ProjectModel, SequenceInfo
from sp404.padconf import Project
from sp404.smp import Sample

PROJECT_DIR = os.path.join("testing", "SP404mk2", "projects", "PRJ7SP404")


def _real_pad_slot(letter, number):
    """A PadSlot built from PRJ7SP404's first pad, so it has a real .SMP to write."""
    smp_path = os.path.join(PROJECT_DIR, "SMPL", "BANK1-01.SMP")
    pad = Project(os.path.join(PROJECT_DIR, "PADCONF.BIN")).pads[0]
    return PadSlot(pad, letter, number, f"{letter}{number:02d} - Kick.wav", smp_path, Sample(smp_path))


def _model(pad_slots):
    model = ProjectModel("test0")
    for pad_slot in pad_slots:
        bank = model.banks.setdefault(pad_slot.bank_letter, Bank(pad_slot.bank_letter, 90.0))
        bank.add_pad(pad_slot)
    return model


class TestXPJWriter(unittest.TestCase):

    def test_sanitize_project_name_strips_spaces(self):
        """Verify project names with spaces are collapsed to underscores."""
        self.assertEqual(writer.sanitize_project_name("test0"), "test0")
        self.assertEqual(writer.sanitize_project_name("My Cool  Project"), "My_Cool_Project")
        self.assertEqual(writer.sanitize_project_name("  padded  "), "padded")

    def test_planned_paths_naming_convention(self):
        """Verify <name>.xpj and <name>_[ProjectData] naming, no spaces."""
        model = ProjectModel("test0")
        xpj_path, project_data_dir, _ = writer.planned_paths(model, "out")

        self.assertEqual(os.path.basename(xpj_path), "test0.xpj")
        self.assertEqual(os.path.basename(project_data_dir), "test0_[ProjectData]")
        self.assertNotIn(" ", os.path.basename(xpj_path))
        self.assertNotIn(" ", os.path.basename(project_data_dir))

    def test_planned_paths_naming_convention_with_spaces_in_project_name(self):
        """Verify a project name with spaces still produces space-free paths."""
        model = ProjectModel("My Cool Project")
        xpj_path, project_data_dir, _ = writer.planned_paths(model, "out")

        self.assertEqual(os.path.basename(xpj_path), "My_Cool_Project.xpj")
        self.assertEqual(os.path.basename(project_data_dir), "My_Cool_Project_[ProjectData]")

    def test_mapped_wavs_are_directly_inside_project_data_dir(self):
        """Verify sample WAVs with an MPC pad are planned directly inside _[ProjectData], not a Samples/ subfolder."""
        pad_slot = _real_pad_slot("A", 1)
        pad_slot.slot = 0
        _, project_data_dir, wav_paths = writer.planned_paths(_model([pad_slot]), "out")

        self.assertEqual(wav_paths, [os.path.join(project_data_dir, "A01 - Kick.wav")])

    def test_unmapped_wavs_are_planned_in_unmapped_samples_folder(self):
        """Verify a pad with no MPC pad is planned inside _[ProjectData]/Unmapped Samples."""
        pad_slot = _real_pad_slot("J", 1)
        _, project_data_dir, wav_paths = writer.planned_paths(_model([pad_slot]), "out")

        self.assertEqual(wav_paths, [os.path.join(project_data_dir, "Unmapped Samples", "J01 - Kick.wav")])

    def test_evicted_and_overflow_pads_end_to_end(self):
        """Verify with all 128 MPC pads taken, a played pad displaces an unplayed one: its events use the new note,
        and the displaced and overflow samples are converted into Unmapped Samples but left out of the XPJ."""
        pads = {f"{letter}{n:02d}": _real_pad_slot(letter, n) for letter in "ABCDEFGH" for n in range(1, 17)}
        for name in ["I01", "I03"]:
            pads[name] = _real_pad_slot(name[0], int(name[1:]))
        model = _model(pads.values())

        sequence = SequenceInfo("PTN00001", 90.0, 1, 1)
        for name, tick in [("A01", 0), ("I03", 480), ("F01", 960), ("G01", 960), ("H01", 960)]:
            sequence.add_event(NoteEvent(pads[name], tick, 1.0, 100))
        model.add_sequence(sequence)
        model.allocation = banking.allocate(model.pads, sequence.used_pads)

        # H16 held the highest slot (127) and nothing plays it, so I03 takes it
        self.assertEqual(pads["I03"].slot, 127)
        self.assertEqual([p.sp404_name for p in model.unmapped_pads], ["H16", "I01"])

        with tempfile.TemporaryDirectory() as output_dir:
            xpj_path, project_data_dir, _ = writer.write_project(model, output_dir)
            _, project = reader.read_project(xpj_path)

            self.assertTrue(os.path.isfile(os.path.join(project_data_dir, "I03 - Kick.wav")))
            for name in ["H16", "I01"]:
                self.assertTrue(os.path.isfile(os.path.join(project_data_dir, "Unmapped Samples", f"{name} - Kick.wav")))
                self.assertFalse(os.path.exists(os.path.join(project_data_dir, f"{name} - Kick.wav")))

        data = project["data"]
        clip = data["sequences"][0]["value"]["trackClipMaps"][0][0]["value"]
        notes = {e["time"]: e["note"]["note"] for e in clip["eventList"]["events"] if e["time"] < 960}
        self.assertEqual(notes, {0: 36, 480: 35})  # slot 127 plays note (36 + 127) % 128

        # only the 128 pads with an MPC pad are in the project's sample pool
        paths = [s["path"] for s in data["samples"]]
        self.assertEqual(len(paths), 128)
        self.assertNotIn("H16 - Kick.wav", paths)
        self.assertNotIn("I01 - Kick.wav", paths)
        instruments = data["tracks"][0]["program"]["drum"]["instruments"]
        self.assertEqual(instruments[127]["layersv"][0]["sampleFile"], "I03 - Kick.wav")


if __name__ == '__main__':
    unittest.main()
