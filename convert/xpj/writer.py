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

DEFAULT_SEQUENCE_NAME = "Sequence 01"


def sanitize_project_name(project_name):
    """MPC project names must not contain spaces - collapse whitespace to
    underscores so `<name>.xpj` and `<name>_[ProjectData]` stay valid."""
    return re.sub(r"\s+", "_", project_name.strip())


def _project_data_dir(output_dir, safe_name):
    return os.path.join(output_dir, f"{safe_name}_[ProjectData]")


def build_track(bank_track):
    """Builds one drum track dict for a populated SP404 bank.

    Only fields that already exist in the template are set (template.assign),
    and padNoteMap is left at MPC's default: pad n plays note 36 + n - 1.
    """
    assign = template.assign
    track = template.empty_track(bank_track.letter)
    drum = track["program"]["drum"]

    for local_number, pad_slot in bank_track.pads.items():
        slot_index = local_number - 1
        pad = pad_slot.pad

        instrument = template.sampled_instrument()
        drum["instruments"][slot_index] = instrument

        assign(instrument, "coarseTune", mapping.clamp(pad.pitch_coarse, mapping.COARSE_TUNE_RANGE))
        assign(instrument, "fineTune", mapping.clamp(pad.pitch_fine, mapping.FINE_TUNE_RANGE))
        assign(instrument, "whichMuteGroup", mapping.mute_group_index(pad))
        assign(instrument, "triggerMode", mapping.trigger_mode(pad))
        assign(instrument, "stretchPercentage", pad.time_stretch_perc)
        assign(instrument["mixable"], "volume", mapping.instrument_volume(pad))
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


def build_sequence(sequence_info, drum_track_names):
    """Builds one sequence dict. Like MPC, every track gets a clip in every
    sequence (empty unless the bank has events), sorted by track name."""
    assign = template.assign
    sequence = template.empty_sequence(sequence_info.name, sequence_info.bpm,
                                        sequence_info.bars, sequence_info.loop_end_bar)

    clips = {name: template.empty_clip(name, sequence_info.length_pulses)
             for name in drum_track_names}

    for event in sorted(sequence_info.events, key=lambda e: (e.tick_pulses, e.note)):
        note_event = template.empty_note_event()
        assign(note_event, "time", event.tick_pulses)
        assign(note_event["note"], "note", event.note)
        assign(note_event["note"], "velocity", event.velocity)
        assign(note_event["note"], "length", event.length_pulses)
        clips[event.bank_letter]["eventList"]["events"].append(note_event)

    row = sequence["trackClipMaps"][0]
    row.extend({"key": name, "value": clip} for name, clip in clips.items())
    row.sort(key=lambda entry: entry["key"])

    return sequence


def build_project_data(model):
    """Builds the full {"data": {...}} dict for model."""
    project = template.empty_project()
    data = project["data"]

    if model.used_banks:
        template.assign(data, "masterTempo", model.banks[model.used_banks[0]].bpm)

    drum_tracks = []
    for letter in model.used_banks:
        track = build_track(model.banks[letter])
        drum_tracks.append(track)
        data["samples"].extend(track["samples"])
    # MPC keeps its own submix/output tracks after the drum tracks
    data["tracks"][:0] = drum_tracks
    drum_track_names = [track["name"] for track in drum_tracks]

    # an MPC project always has at least one sequence
    sequences = model.sequences or [SequenceInfo(DEFAULT_SEQUENCE_NAME, data["masterTempo"], 1, 1)]
    for index, sequence_info in enumerate(sequences):
        data["sequences"].append({"key": index, "value": build_sequence(sequence_info, drum_track_names)})

    data["clipPlayerData"]["trackClipTransportMap"] = [
        {"key": name, "value": [{"key": index, "value": 0} for index in range(len(sequences))]}
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


def planned_paths(model, output_dir):
    """Computes every path write_project() would write, without touching disk."""
    safe_name = sanitize_project_name(model.project_name)
    xpj_path = os.path.join(output_dir, f"{safe_name}.xpj")
    # samples live directly in _[ProjectData]/, not a Samples/ subfolder -
    # MPC Sample couldn't find them when they were nested one level deeper
    project_data_dir = _project_data_dir(output_dir, safe_name)
    wav_paths = [
        os.path.join(project_data_dir, pad_slot.wav_filename)
        for letter in model.used_banks
        for pad_slot in model.banks[letter].pads.values()
    ]
    return xpj_path, project_data_dir, wav_paths


def write_project(model, output_dir):
    """Writes <name>.xpj and <name>_[ProjectData]/ (with the WAVs directly
    inside it) for model.

    Returns (xpj_path, project_data_dir, wav_paths).
    """
    project_data = build_project_data(model)
    xpj_path, project_data_dir, wav_paths = planned_paths(model, output_dir)

    os.makedirs(output_dir, exist_ok=True)
    with open(xpj_path, 'wb') as f:
        f.write(serialize(project_data))

    os.makedirs(project_data_dir, exist_ok=True)
    for letter in model.used_banks:
        for pad_slot in model.banks[letter].pads.values():
            wav_path = os.path.join(project_data_dir, pad_slot.wav_filename)
            wav.write_wav(pad_slot.sample_info, pad_slot.smp_path, wav_path)

    return xpj_path, project_data_dir, wav_paths
