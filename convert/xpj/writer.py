"""
Builds the MPC XPJ JSON structure from a ProjectModel and writes it to disk
alongside the project's WAV files.
See convert/xpj/DESIGN.md sections 4, 7 and 9.
"""

import copy
import gzip
import json
import os
import re

from . import mapping
from . import template
from . import wav


def sanitize_project_name(project_name):
    """MPC project names must not contain spaces - collapse whitespace to
    underscores so `<name>.xpj` and `<name>_[ProjectData]` stay valid."""
    return re.sub(r"\s+", "_", project_name.strip())


def _project_data_dir(output_dir, safe_name):
    return os.path.join(output_dir, f"{safe_name}_[ProjectData]")


def build_track(bank_track):
    """Builds one drum track dict for a populated SP404 bank."""
    track = template.empty_track(bank_track.letter)
    program = track["program"]
    drum = program["drum"]
    note_map = program["padNoteMap"]["noteForPad"]

    for local_number, pad_slot in bank_track.pads.items():
        slot_index = local_number - 1
        pad = pad_slot.pad

        note_map[f"value{slot_index}"] = pad_slot.note

        instrument = drum["instruments"][slot_index]
        instrument["coarseTune"] = mapping.clamp(pad.pitch_coarse, mapping.COARSE_TUNE_RANGE)
        instrument["fineTune"] = mapping.clamp(pad.pitch_fine, mapping.FINE_TUNE_RANGE)
        instrument["whichMuteGroup"] = mapping.mute_group_index(pad)
        instrument["triggerMode"] = mapping.trigger_mode(pad)
        instrument["tempo"] = pad.bpm
        instrument["bpmLock"] = pad.bpm_sync
        instrument["warpEnable"] = pad.bpm_sync
        instrument["stretchPercentage"] = pad.time_stretch_perc
        instrument["velocityScale"] = 50 if mapping.is_fixed_velocity(pad) else 100
        instrument["mixable"]["volume"] = mapping.instrument_volume(pad)

        layer = instrument["layersv"][0]
        layer["active"] = True
        layer["sampleName"] = pad.name
        layer["sampleFile"] = pad_slot.wav_filename
        layer["sampleStart"] = pad.sample_start
        layer["sampleEnd"] = pad.sample_end
        layer["loop"] = mapping.is_looping(pad)
        layer["loopStart"] = pad.loop_start
        layer["loopEnd"] = pad.sample_end
        layer["direction"] = mapping.layer_direction(pad)
        layer["rootNote"] = pad_slot.note

        track["samples"].append(template.sample_pool_entry(pad.name, pad_slot.wav_filename, pad.bpm))

    return track


def build_sequence(sequence_info):
    """Builds one sequence dict, with one clip per bank that has events."""
    sequence = template.empty_sequence(sequence_info.name, sequence_info.bpm,
                                        sequence_info.bars, sequence_info.loop_end_bar)

    clips_by_bank = {}
    for event in sequence_info.events:
        clip = clips_by_bank.get(event.bank_letter)
        if clip is None:
            clip = template.empty_clip(sequence_info.name, sequence_info.length_pulses)
            clips_by_bank[event.bank_letter] = clip

        note_event = copy.deepcopy(template.empty_note_event())
        note_event["time"] = event.tick_pulses
        note_event["note"]["note"] = event.note
        note_event["note"]["velocity"] = event.velocity
        note_event["note"]["length"] = event.length_pulses
        clip["eventList"]["events"].append(note_event)

    row = sequence["trackClipMaps"][0]
    for letter in sorted(clips_by_bank.keys()):
        row.append({"key": letter, "value": clips_by_bank[letter]})

    return sequence


def build_project_data(model):
    """Builds the full {"formatVersion": ..., "data": {...}} dict for model."""
    project = template.empty_project()
    data = project["data"]

    if model.used_banks:
        data["masterTempo"] = model.banks[model.used_banks[0]].bpm

    for letter in model.used_banks:
        track = build_track(model.banks[letter])
        data["tracks"].append(track)
        data["samples"].extend(track["samples"])

    for index, sequence_info in enumerate(model.sequences):
        data["sequences"].append({"key": index, "value": build_sequence(sequence_info)})

    return project


def serialize(project_data):
    """Encodes a project dict as gzip-compressed XPJ bytes."""
    header_text = "\n".join(template.HEADER_LINES)
    json_text = json.dumps(project_data, ensure_ascii=False)
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
