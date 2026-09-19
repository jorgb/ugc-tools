"""
Top-level orchestration: reads an SP404mk2 export and converts it to an
MPC XPJ project. See convert/xpj/DESIGN.md.
"""

import logging
import os

from sp404.padconf import BANKS, Project
from sp404.ptn import Pattern
from sp404.smp import Sample

from . import mapping
from . import writer
from .model import BankTrack, NoteEvent, PadSlot, ProjectModel, SequenceInfo

log = logging.getLogger(__name__)

DEFAULT_BPM = 120.0


def _smp_path(source_dir, letter, local_number):
    bank_number = BANKS.index(letter) + 1
    return os.path.join(source_dir, "SMPL", f"BANK{bank_number}-{local_number:02d}.SMP")


def _split_pad_name(name):
    """'B07' -> ('B', 7)."""
    return name[0], int(name[1:])


def _build_banks(source_dir, project):
    """Reads every populated pad and groups them into BankTrack objects.

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

        bank_track = banks.get(letter)
        if bank_track is None:
            bank_track = BankTrack(letter, project.bank_bpms.get(letter, DEFAULT_BPM))
            banks[letter] = bank_track

        note = mapping.pad_note(local_number)
        wav_filename = f"{letter}{local_number:02d} - {pad.name}.wav"
        bank_track.add_pad(PadSlot(pad, local_number, note, wav_filename, smp_path, sample_info))

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
        sequence = SequenceInfo(sequence_name, default_bpm, pattern.bars, pattern.loop_end_bar)

        for event in pattern.events:
            if event.controller is not None:
                sequence.control_change_count += 1
                continue
            if event.pad_id is None:
                continue

            letter, local_number = _split_pad_name(event.pad_id.name)
            bank_track = banks.get(letter)
            if bank_track is None or local_number not in bank_track.pads:
                log.warning("sequence %s references pad %s which has no sample, skipping event",
                            sequence_name, event.pad_id.name)
                continue

            if not mapping.is_baseline_chromatic_pitch(event.chromatic_pitch):
                log.warning("sequence %s: pad %s has a non-default chromatic pitch "
                            "(byte=0x%02X), not applied - see DESIGN.md section 11",
                            sequence_name, event.pad_id.name, event.chromatic_pitch)

            pad_slot = bank_track.pads[local_number]
            sequence.add_event(NoteEvent(
                letter,
                event.absolute_tick * mapping.TICK_SCALE,
                pad_slot.note,
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
    for bank_track in banks.values():
        model.add_bank(bank_track)
    model.skipped_pads = skipped_pads

    default_bpm = banks[model.used_banks[0]].bpm if model.used_banks else DEFAULT_BPM
    for sequence in _build_sequences(os.path.join(source_dir, "PTN"), banks, default_bpm):
        model.add_sequence(sequence)

    return model


def _log_summary(model):
    total_pads = sum(len(bank.pads) for bank in model.banks.values())
    log.info("Project '%s': %d bank(s), %d pad(s), %d sequence(s)",
              model.project_name, len(model.banks), total_pads, len(model.sequences))

    for letter in model.used_banks:
        bank_track = model.banks[letter]
        log.info("Bank %s -> MPC track '%s' (%.2f BPM), %d pad(s)",
                  letter, letter, bank_track.bpm, len(bank_track.pads))

        for local_number in sorted(bank_track.pads):
            pad_slot = bank_track.pads[local_number]
            pad = pad_slot.pad
            duration = pad_slot.sample_info.size / pad_slot.sample_info.samplerate
            trig = "+".join(t.name for t in pad.trig_mode)
            log.info("  pad %s%02d '%s' -> note %d: %.2fs (%d frames, %s, %d Hz), "
                     "vol %d, trig=%s, play=%s -> %s",
                     letter, local_number, pad.name, pad_slot.note, duration,
                     pad_slot.sample_info.size, pad_slot.sample_info.mode.name,
                     pad_slot.sample_info.samplerate, pad.vol, trig,
                     pad.play_mode.name, pad_slot.wav_filename)

            if mapping.is_pingpong(pad):
                log.warning("  pad %s%02d: %s has no MPC layer equivalent, degraded to %s",
                            letter, local_number, pad.play_mode.name,
                            "reverse" if mapping.layer_direction(pad) else "forward")

    for pad, reason in model.skipped_pads:
        log.warning("Skipped pad %d: %s", pad.pad_nr, reason)

    for sequence in model.sequences:
        log.info("Sequence '%s' -> %d bar(s) (%d pulses) @ %.2f BPM, "
                  "%d note event(s) across %d track(s)",
                  sequence.name, sequence.bars, sequence.length_pulses, sequence.bpm,
                  len(sequence.events), len(sequence.used_banks))
        if sequence.control_change_count:
            log.info("  %d control-change event(s) skipped (no automation mapping yet)",
                      sequence.control_change_count)


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
