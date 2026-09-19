"""
Intermediate representation between sp404 parser objects and the MPC XPJ
JSON shape, so writer.py doesn't need to know about SP404 binary formats
and convert.py doesn't need to know about XPJ JSON field names.
See convert/xpj/DESIGN.md section 8.
"""

from . import mapping


class PadSlot:
    """One populated SP404 pad, its sample, and where it lands on the MPC.

    `slot` is the MPC drum program pad (0..127) once banking.allocate() has
    run, or None if the pad has no place there (it is then written to the
    project's "Unmapped Samples" folder instead).
    """
    def __init__(self, pad, bank_letter, local_number, wav_filename, smp_path, sample_info):
        self.pad = pad
        self.bank_letter = bank_letter
        self.local_number = local_number
        self.wav_filename = wav_filename
        self.smp_path = smp_path
        self.sample_info = sample_info
        self.slot = None

    @property
    def sp404_name(self):
        """'F03' - the pad as the SP404 shows it."""
        return f"{self.bank_letter}{self.local_number:02d}"

    @property
    def note(self):
        return None if self.slot is None else mapping.slot_note(self.slot)


class Bank:
    """One SP404 bank that has at least one populated pad."""
    def __init__(self, letter, bpm):
        self.letter = letter
        self.bpm = bpm
        self.pads = {}

    def add_pad(self, pad_slot):
        self.pads[pad_slot.local_number] = pad_slot


class NoteEvent:
    """One pattern note, already scaled to MPC pulses. The MPC note comes
    from the pad it plays, so it follows wherever banking put that pad."""
    def __init__(self, pad_slot, tick_pulses, velocity, length_pulses):
        self.pad_slot = pad_slot
        self.tick_pulses = tick_pulses
        self.velocity = velocity
        self.length_pulses = length_pulses

    @property
    def note(self):
        return self.pad_slot.note


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
    def used_pads(self):
        return {event.pad_slot for event in self.events}


class ProjectModel:
    """Everything writer.py needs to build one MPC XPJ project."""
    def __init__(self, project_name):
        self.project_name = project_name
        self.banks = {}
        self.sequences = []
        # (pad, reason) for pads that couldn't be read, e.g. a missing
        # or unreadable .SMP file
        self.skipped_pads = []
        # banking.Allocation, set once pads have been given MPC slots
        self.allocation = None

    def add_bank(self, bank):
        self.banks[bank.letter] = bank

    def add_sequence(self, sequence_info):
        self.sequences.append(sequence_info)

    @property
    def used_banks(self):
        return sorted(self.banks.keys())

    @property
    def pads(self):
        """Every populated pad, in SP404 order (bank, then pad number)."""
        return [self.banks[letter].pads[number]
                for letter in self.used_banks
                for number in sorted(self.banks[letter].pads)]

    @property
    def mapped_pads(self):
        return sorted((p for p in self.pads if p.slot is not None), key=lambda p: p.slot)

    @property
    def unmapped_pads(self):
        return [p for p in self.pads if p.slot is None]
