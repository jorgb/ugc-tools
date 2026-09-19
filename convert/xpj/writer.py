"""
Builds the MPC XPJ JSON structure from a ProjectModel and writes it to disk
alongside the project's WAV files.
See convert/xpj/DESIGN.md sections 4, 7 and 9.
"""

import gzip
import json
import os
import re

from . import mapping
from . import template
from . import wav
from .model import SequenceInfo

# MPC's own name for the first drum track
DRUM_TRACK_NAME = "Drum 001"

# samples that have no pad on the MPC go here, inside _[ProjectData]
UNMAPPED_SAMPLES_DIR = "Unmapped Samples"


def sanitize_project_name(project_name):
    """MPC project names must not contain spaces - collapse whitespace to
    underscores so `<name>.xpj` and `<name>_[ProjectData]` stay valid."""
    return re.sub(r"\s+", "_", project_name.strip())


def _project_data_dir(output_dir, safe_name):
    return os.path.join(output_dir, f"{safe_name}_[ProjectData]")


def build_track(model):
    """Builds the one drum track holding every pad that has an MPC slot.

    Only fields that already exist in the template are set (template.assign),
    and padNoteMap is left at MPC's default (mapping.slot_note).
    """
    assign = template.assign
    track = template.empty_track(DRUM_TRACK_NAME)
    drum = track["program"]["drum"]

    for pad_slot in model.mapped_pads:
        slot_index = pad_slot.slot
        pad = pad_slot.pad

        instrument = template.sampled_instrument()
        drum["instruments"][slot_index] = instrument

        coarse_tune, fine_tune = mapping.tuning(pad)
        assign(instrument, "coarseTune", coarse_tune)
        assign(instrument, "fineTune", fine_tune)
        assign(instrument, "whichMuteGroup", mapping.mute_group_index(pad))
        assign(instrument, "triggerMode", mapping.trigger_mode(pad))
        assign(instrument, "stretchPercentage", mapping.stretch_percentage(pad))
        assign(instrument["mixable"], "volume", mapping.instrument_volume(pad))
        amp_envelope = instrument["synthSection"]["ampEnvelope"]
        for name, value in mapping.amp_envelope(pad).items():
            assign(amp_envelope[name], "value0", value)
        if pad.bpm_sync:
            assign(instrument, "tempo", pad.bpm)
            assign(instrument, "bpmLock", True)
            assign(instrument, "warpEnable", True)

        first_frame, last_frame = mapping.sample_region(pad)
        layer = instrument["layersv"][0]
        assign(layer, "sampleName", pad.name)
        assign(layer, "sampleFile", pad_slot.wav_filename)
        assign(layer, "direction", mapping.layer_direction(pad))
        assign(layer["sliceInfo"], "Start", first_frame)
        assign(layer["sliceInfo"], "End", last_frame)
        if mapping.is_looping(pad):
            # unverified: no looping pad in the reference project
            assign(layer, "loop", True)
            assign(layer, "loopStart", pad.loop_start)
            assign(layer, "loopEnd", last_frame)

        track["samples"].append(template.sample_pool_entry(
            pad.name, pad_slot.wav_filename, mapping.sample_tempo(pad)))

    return track


def build_sequence(sequence_info, drum_track_name):
    """Builds one sequence dict. Like MPC, every track gets a clip in every
    sequence (empty for all but the drum track), sorted by track name."""
    assign = template.assign
    sequence = template.empty_sequence(sequence_info.name, sequence_info.bpm,
                                        sequence_info.bars, sequence_info.loop_end_bar)

    clip = template.empty_clip(drum_track_name, sequence_info.length_pulses)
    for event in sorted(sequence_info.events, key=lambda e: (e.tick_pulses, e.note)):
        note_event = template.empty_note_event()
        assign(note_event, "time", event.tick_pulses)
        assign(note_event["note"], "note", event.note)
        assign(note_event["note"], "velocity", event.velocity)
        assign(note_event["note"], "length", event.length_pulses)
        clip["eventList"]["events"].append(note_event)

    row = sequence["trackClipMaps"][0]
    row.append({"key": drum_track_name, "value": clip})
    row.sort(key=lambda entry: entry["key"])

    return sequence


def build_project_data(model):
    """Builds the full {"data": {...}} dict for model."""
    project = template.empty_project()
    data = project["data"]

    if model.used_banks:
        template.assign(data, "masterTempo", model.banks[model.used_banks[0]].bpm)

    track = build_track(model)
    data["samples"].extend(track["samples"])
    # MPC keeps its own submix/output tracks after the drum tracks
    data["tracks"].insert(0, track)

    # A sequence sits at its own MPC index, which is where its pad is (see
    # banking.allocate_sequences), so the ones between are empty. An MPC
    # project always has at least one sequence.
    placed = model.placed_sequences
    if any(s.index is None for s in model.sequences) and not model.sequence_allocation:
        raise ValueError("sequences have no MPC index: run banking.allocate_sequences() first")
    by_index = {s.index: s for s in placed}
    count = max(by_index) + 1 if by_index else 1
    for index in range(count):
        sequence_info = by_index.get(index) or SequenceInfo(
            f"Sequence {index + 1:02d}", data["masterTempo"], 1, 1)
        data["sequences"].append({"key": index, "value": build_sequence(sequence_info, track["name"])})
    # open on the first sequence that has something in it
    template.assign(data, "currentSequence", min(by_index) if by_index else 0)

    data["clipPlayerData"]["trackClipTransportMap"] = [
        {"key": name, "value": [{"key": index, "value": 0} for index in range(count)]}
        for name in sorted(track["name"] for track in data["tracks"])
    ]

    return project


def serialize(project_data):
    """Encodes a project dict as gzip-compressed XPJ bytes.

    indent=0 reproduces the layout MPC writes (one item per line, no
    indentation); MPC's own files are byte-identical to it apart from the
    last digit of some floats.
    """
    header_text = "\n".join(template.header_lines())
    json_text = json.dumps(project_data, ensure_ascii=False, indent=0)
    payload = f"{header_text}\n{json_text}".encode("utf-8")
    return gzip.compress(payload)


def _wav_path(pad_slot, project_data_dir):
    if pad_slot.slot is None:
        return os.path.join(project_data_dir, UNMAPPED_SAMPLES_DIR, pad_slot.wav_filename)
    return os.path.join(project_data_dir, pad_slot.wav_filename)


def planned_paths(model, output_dir):
    """Computes every path write_project() would write, without touching disk."""
    safe_name = sanitize_project_name(model.project_name)
    xpj_path = os.path.join(output_dir, f"{safe_name}.xpj")
    # samples live directly in _[ProjectData]/, not a Samples/ subfolder -
    # MPC Sample couldn't find them when they were nested one level deeper.
    # Pads with no MPC pad are the exception: they go in "Unmapped Samples".
    project_data_dir = _project_data_dir(output_dir, safe_name)
    wav_paths = [_wav_path(pad_slot, project_data_dir) for pad_slot in model.pads]
    return xpj_path, project_data_dir, wav_paths


def write_project(model, output_dir):
    """Writes <name>.xpj and <name>_[ProjectData]/ (with the WAVs directly
    inside it, and those without an MPC pad in Unmapped Samples/) for model.

    Returns (xpj_path, project_data_dir, wav_paths).
    """
    project_data = build_project_data(model)
    xpj_path, project_data_dir, wav_paths = planned_paths(model, output_dir)

    os.makedirs(output_dir, exist_ok=True)
    with open(xpj_path, 'wb') as f:
        f.write(serialize(project_data))

    for pad_slot, wav_path in zip(model.pads, wav_paths):
        os.makedirs(os.path.dirname(wav_path), exist_ok=True)
        wav.write_wav(pad_slot.sample_info, pad_slot.smp_path, wav_path)

    return xpj_path, project_data_dir, wav_paths
