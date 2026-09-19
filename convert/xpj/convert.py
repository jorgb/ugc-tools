"""
Top-level orchestration: reads an SP404mk2 export and converts it to an
MPC XPJ project. See convert/xpj/DESIGN.md.
"""

import logging
import os
import re

from sp404.padconf import BANKS, Project
from sp404.ptn import Pattern
from sp404.smp import Sample

from . import banking
from . import mapping
from . import writer
from .model import Bank, NoteEvent, PadSlot, ProjectModel, SequenceInfo

log = logging.getLogger(__name__)

DEFAULT_BPM = 120.0


def _smp_path(source_dir, letter, local_number):
    bank_number = BANKS.index(letter) + 1
    return os.path.join(source_dir, "SMPL", f"BANK{bank_number}-{local_number:02d}.SMP")


_PATTERN_NAME = re.compile(r"^PTN(\d+)$", re.IGNORECASE)


def _pattern_pad(sequence_name):
    """'PTN00013' -> ('A', 13): a pattern's file number is the SP404 pad that
    plays it, counting 16 pads to a bank (see testing/SP404mk2/PTN.txt).
    (None, None) for a name that isn't a pattern number."""
    match = _PATTERN_NAME.match(sequence_name)
    if match:
        index = int(match.group(1)) - 1
        if 0 <= index < len(BANKS) * banking.PADS_PER_BANK:
            return BANKS[index // banking.PADS_PER_BANK], index % banking.PADS_PER_BANK + 1
    return None, None


def _split_pad_name(name):
    """'B07' -> ('B', 7)."""
    return name[0], int(name[1:])


def _build_banks(source_dir, project):
    """Reads every populated pad and groups them into Bank objects.

    Each populated SP404 pad owns its own dedicated .SMP file (confirmed
    against this repo's own fixtures - see convert/xpj/DESIGN.md section
    5.5), so there is no cross-pad sample deduplication to do here.
    """
    banks = {}
    skipped_pads = []

    for pad in project.pads:
        if not pad.name or not pad.name.strip():
            continue

        bank_idx = (pad.pad_nr - 1) // 16
        local_number = (pad.pad_nr - 1) % 16 + 1
        letter = BANKS[bank_idx]

        smp_path = _smp_path(source_dir, letter, local_number)
        if not os.path.isfile(smp_path):
            log.warning("pad %s%02d ('%s') has no sample file at %s, skipping",
                        letter, local_number, pad.name, smp_path)
            skipped_pads.append((pad, f"missing sample file {smp_path}"))
            continue

        try:
            sample_info = Sample(smp_path)
        except ValueError as exc:
            log.warning("pad %s%02d ('%s') has an unreadable sample file %s (%s), skipping",
                        letter, local_number, pad.name, smp_path, exc)
            skipped_pads.append((pad, str(exc)))
            continue

        bank = banks.get(letter)
        if bank is None:
            bank = Bank(letter, project.bank_bpms.get(letter, DEFAULT_BPM))
            banks[letter] = bank

        wav_filename = f"{letter}{local_number:02d} - {pad.name}.wav"
        bank.add_pad(PadSlot(pad, letter, local_number, wav_filename, smp_path, sample_info))

    return banks, skipped_pads


def _build_sequences(pattern_dir, banks, default_bpm):
    """Reads every PTN/*.BIN pattern and converts its events to sequences."""
    sequences = []
    if not os.path.isdir(pattern_dir):
        return sequences

    for filename in sorted(os.listdir(pattern_dir)):
        if not filename.upper().endswith(".BIN"):
            continue

        pattern = Pattern(os.path.join(pattern_dir, filename))
        sequence_name = os.path.splitext(filename)[0]
        bank_letter, local_number = _pattern_pad(sequence_name)
        sequence = SequenceInfo(sequence_name, default_bpm, pattern.bars, pattern.loop_end_bar,
                                bank_letter, local_number)

        for event in pattern.events:
            if event.controller is not None:
                sequence.control_change_count += 1
                continue
            if event.pad_id is None:
                continue

            letter, local_number = _split_pad_name(event.pad_id.name)
            bank = banks.get(letter)
            if bank is None or local_number not in bank.pads:
                log.warning("sequence %s references pad %s which has no sample, skipping event",
                            sequence_name, event.pad_id.name)
                continue

            if not mapping.is_baseline_chromatic_pitch(event.chromatic_pitch):
                log.warning("sequence %s: pad %s has a non-default chromatic pitch "
                            "(byte=0x%02X), not applied - see DESIGN.md section 11",
                            sequence_name, event.pad_id.name, event.chromatic_pitch)

            pad_slot = bank.pads[local_number]
            sequence.add_event(NoteEvent(
                pad_slot,
                event.absolute_tick * mapping.TICK_SCALE,
                mapping.note_velocity(event.velocity),
                mapping.note_length_pulses(pad_slot.pad, event.gate_ticks),
            ))

        sequences.append(sequence)

    return sequences


def build_model(source_dir, project_name=None):
    """Reads a PADCONF.BIN + SMPL/ + PTN/ export and builds a ProjectModel."""
    project = Project(os.path.join(source_dir, "PADCONF.BIN"))

    model = ProjectModel(project_name or project.project_name)
    banks, skipped_pads = _build_banks(source_dir, project)
    for bank in banks.values():
        model.add_bank(bank)
    model.skipped_pads = skipped_pads

    default_bpm = banks[model.used_banks[0]].bpm if model.used_banks else DEFAULT_BPM
    for sequence in _build_sequences(os.path.join(source_dir, "PTN"), banks, default_bpm):
        model.add_sequence(sequence)

    model.sequence_allocation = banking.allocate_sequences(model.sequences)

    sequenced = set().union(*(sequence.used_pads for sequence in model.sequences))
    model.allocation = banking.allocate(model.pads, sequenced)

    return model


def _log_summary(model):
    log.info("Project '%s': %d SP404 bank(s), %d pad(s), %d sequence(s)",
              model.project_name, len(model.banks), len(model.pads), len(model.sequences))

    allocation = model.allocation
    for letter in model.used_banks:
        bpm = model.banks[letter].bpm
        if letter in allocation.bank_map:
            target = banking.bank_letter(allocation.bank_map[letter])
            log.info("SP404 bank %s (%.2f BPM) -> MPC bank %s%s", letter, bpm,
                     target, "" if target == letter else " (relocated)")
        else:
            log.info("SP404 bank %s (%.2f BPM) -> not placed as a whole bank", letter, bpm)

    for pad_slot in model.pads:
        pad = pad_slot.pad
        duration = pad_slot.sample_info.size / pad_slot.sample_info.samplerate
        trig = "+".join(t.name for t in pad.trig_mode)
        if pad_slot.slot is None:
            where = "UNMAPPED"
        else:
            bank, number = divmod(pad_slot.slot, banking.PADS_PER_BANK)
            where = f"MPC pad {banking.bank_letter(bank)}{number + 1:02d} (note {pad_slot.note})"
        coarse, fine = mapping.tuning(pad)
        log.info("  pad %s '%s' -> %s: %.2fs (%d frames, %s, %d Hz), "
                 "vol %d, tune %+d/%+d, gate=%s -> %s, trig=%s, play=%s -> %s",
                 pad_slot.sp404_name, pad.name, where, duration,
                 pad_slot.sample_info.size, pad_slot.sample_info.mode.name,
                 pad_slot.sample_info.samplerate, pad.vol, coarse, fine,
                 "on" if pad.gate else "off",
                 mapping.TriggerMode(mapping.trigger_mode(pad)).name,
                 trig, pad.play_mode.name, pad_slot.wav_filename)

        if mapping.amp_envelope(pad) or pad.hold < mapping.SP404_HOLD_RANGE[1]:
            log.info("  pad %s: envelope attack %d, hold %d%%, release %d -> amp envelope %s%s",
                     pad_slot.sp404_name, pad.attack, pad.hold, pad.release,
                     ", ".join(f"{k} {v:.3f}" if isinstance(v, float) else f"{k} {v}"
                               for k, v in mapping.amp_envelope(pad).items()) or "unchanged",
                     f", ends at frame {mapping.sample_region(pad)[1]}" if pad.hold < mapping.SP404_HOLD_RANGE[1] else "")

        if mapping.is_fixed_velocity(pad):
            log.warning("  pad %s: FIXED_VELOCITY has no MPC pad field, not applied",
                        pad_slot.sp404_name)

        if mapping.is_pingpong(pad):
            log.warning("  pad %s: %s has no MPC layer equivalent, degraded to %s",
                        pad_slot.sp404_name, pad.play_mode.name,
                        "reverse" if mapping.layer_direction(pad) else "forward")

    for pad_slot in allocation.moved:
        bank, number = divmod(pad_slot.slot, banking.PADS_PER_BANK)
        log.warning("Pad %s is played by a pattern but its bank found no free MPC bank: "
                    "moved to MPC pad %s%02d, its notes follow it",
                    pad_slot.sp404_name, banking.bank_letter(bank), number + 1)

    for pad_slot in allocation.evicted:
        log.warning("Pad %s ('%s') lost its MPC pad to a pad a pattern plays",
                    pad_slot.sp404_name, pad_slot.pad.name)

    unmapped = model.unmapped_pads
    if unmapped:
        log.warning("%d of %d pad(s) have no MPC pad and go to '%s': %s",
                    len(unmapped), len(model.pads), writer.UNMAPPED_SAMPLES_DIR,
                    ", ".join(p.sp404_name for p in unmapped))

    for pad, reason in model.skipped_pads:
        log.warning("Skipped pad %d: %s", pad.pad_nr, reason)

    sequence_allocation = model.sequence_allocation
    for letter, target in sequence_allocation.bank_map.items():
        log.info("SP404 pattern bank %s -> MPC sequence bank %s%s", letter,
                 banking.bank_letter(target), "" if banking.bank_letter(target) == letter else " (relocated)")

    for sequence in model.sequences:
        if sequence.index is None:
            where = "NO MPC SEQUENCE"
        else:
            bank, number = divmod(sequence.index, banking.PADS_PER_BANK)
            where = f"MPC sequence {sequence.index + 1} (pad {banking.bank_letter(bank)}{number + 1:02d})"
        log.info("Sequence '%s' (pattern %s) -> %s: %d bar(s) (%d pulses) @ %.2f BPM, "
                  "%d note event(s) on %d pad(s)",
                  sequence.name, sequence.sp404_name, where, sequence.bars, sequence.length_pulses,
                  sequence.bpm, len(sequence.events), len(sequence.used_pads))
        if sequence.control_change_count:
            log.info("  %d control-change event(s) skipped (no automation mapping yet)",
                      sequence.control_change_count)

    for sequence in sequence_allocation.unplaced:
        log.warning("Pattern %s ('%s') has no MPC sequence (no free sequence bank), skipped",
                    sequence.sp404_name, sequence.name)


def convert_project(source_dir, output_dir, project_name=None, dry_run=False):
    """Converts an SP404mk2 export into an MPC XPJ project.

    Always builds and logs the full model. Only writes files when dry_run
    is False. Returns (model, paths), where paths is None in dry-run mode
    and otherwise (xpj_path, project_data_dir, wav_paths).
    """
    model = build_model(source_dir, project_name)
    _log_summary(model)

    xpj_path, project_data_dir, wav_paths = writer.planned_paths(model, output_dir)

    if dry_run:
        log.info("[DRY RUN] Would write:")
        log.info("  %s", xpj_path)
        for wav_path in wav_paths:
            log.info("  %s", wav_path)
        log.info("[DRY RUN] Nothing written.")
        return model, None

    writer.write_project(model, output_dir)
    log.info("Wrote %s", xpj_path)
    log.info("Wrote %d sample(s) to %s", len(wav_paths), project_data_dir)
    return model, (xpj_path, project_data_dir, wav_paths)
