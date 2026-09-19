import os
import unittest

from convert.xpj import writer
from convert.xpj.model import ProjectModel


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

    def test_wav_paths_are_directly_inside_project_data_dir(self):
        """Verify sample WAVs are planned directly inside _[ProjectData], not a Samples/ subfolder."""
        model = ProjectModel("test0")
        model.add_bank(_bank_with_one_pad())
        _, project_data_dir, wav_paths = writer.planned_paths(model, "out")

        self.assertEqual(len(wav_paths), 1)
        self.assertEqual(os.path.dirname(wav_paths[0]), project_data_dir)


def _bank_with_one_pad():
    from convert.xpj.model import BankTrack, PadSlot

    class _FakePad:
        pass

    class _FakeSampleInfo:
        pass

    bank = BankTrack("A", 90.0)
    bank.add_pad(PadSlot(_FakePad(), 1, 37, "A01 - Kick.wav", "unused.SMP", _FakeSampleInfo()))
    return bank


if __name__ == '__main__':
    unittest.main()
