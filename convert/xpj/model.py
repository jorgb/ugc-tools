"""
Intermediate representation between sp404 parser objects and the MPC XPJ
JSON shape, so writer.py doesn't need to know about SP404 binary formats
and convert.py doesn't need to know about XPJ JSON field names.
See convert/xpj/DESIGN.md section 8.
"""

from . import mapping


class PadSlot:
    """One populated SP404 pad, resolved to its MPC note, sample info and
    the WAV filename it will be written under."""
    def __init__(self, pad, local_number, note, wav_filename, smp_path, sample_info):
        self.pad = pad
        self.local_number = local_number
        self.note = note
        self.wav_filename = wav_filename
        self.smp_path = smp_path
        self.sample_info = sample_info


class BankTrack:
    """One SP404 bank that has at least one populated pad, i.e. one MPC track."""
    def __init__(self, letter, bpm):
        self.letter = letter
        self.bpm = bpm
        self.pads = {}

    def add_pad(self, pad_slot):
        self.pads[pad_slot.local_number] = pad_slot


class NoteEvent:
    """One pattern note, already scaled to MPC pulses and resolved to a bank."""
    def __init__(self, bank_letter, tick_pulses, note, velocity, length_pulses):
        self.bank_letter = bank_letter
        self.tick_pulses = tick_pulses
        self.note = note
        self.velocity = velocity
        self.length_pulses = length_pulses


class SequenceInfo:
    """One SP404 pattern, converted to MPC sequence terms."""
    def __init__(self, name, bpm, bars, loop_end_bar):
        self.name = name
        self.bpm = bpm
        self.bars = bars
        self.loop_end_bar = loop_end_bar
        self.length_pulses = bars * mapping.MPC_PULSES_PER_BAR
        self.events = []
        self.control_change_count = 0

    def add_event(self, event):
        self.events.append(event)

    @property
    def used_banks(self):
        return sorted({event.bank_letter for event in self.events})


class ProjectModel:
    """Everything writer.py needs to build one MPC XPJ project."""
    def __init__(self, project_name):
        self.project_name = project_name
        self.banks = {}
        self.sequences = []
        # (pad, reason) for pads that couldn't be mapped, e.g. a missing
        # or unreadable .SMP file
        self.skipped_pads = []

    def add_bank(self, bank_track):
        self.banks[bank_track.letter] = bank_track

    def add_sequence(self, sequence_info):
        self.sequences.append(sequence_info)

    @property
    def used_banks(self):
        return sorted(self.banks.keys())
